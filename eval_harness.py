#!/usr/bin/env python3
"""
Eval harness -- measures the one metric the README explicitly calls out
as NOT covered by benchmark.py: downstream answer-accuracy retention.

Compression ratio is easy to measure offline (before/after token
counts). Whether the *model* still gets the right answer after you've
thrown away 70% of its context is a different question, and the only
way to answer it is to actually ask.

This script:
  1. Compresses a document with ContextCompressor.
  2. Asks a set of questions against the ORIGINAL text via a live LLM
     and records the answers as a reference.
  3. Asks the same questions against the COMPRESSED text.
  4. Uses a judge call (same model) to score each compressed-context
     answer against the original-context answer for factual agreement.
  5. Reports per-question and aggregate retention, in a colored
     progress bar + table + summary panel (via `rich`) if available,
     or plain text otherwise.

Two providers are supported -- pick with --provider:

  groq (default)  -- genuinely free, no credit card, open-weight models
                      (Llama, GPT-OSS, etc.) served on Groq's fast LPU
                      hardware. Get a key: https://console.groq.com/keys
                      `pip install groq`, then `export GROQ_API_KEY=gsk_...`

  gemini          -- Google's Gemini API free tier (Flash/Flash-Lite
                      models). Get a key: https://aistudio.google.com/apikey
                      `pip install google-genai`, then `export GEMINI_API_KEY=AIza...`

Both free tiers are rate-limited (requests/tokens per minute); this
script paces calls proactively and backs off/retries on 429s rather
than failing the whole run. Without a key for the chosen provider,
this script will explain that and exit -- it will not fabricate
results.

Usage:
    export GROQ_API_KEY=gsk_...
    python eval_harness.py my_doc.txt --questions questions.json --target 0.7

    # or, using Gemini instead:
    export GEMINI_API_KEY=AIza...
    python eval_harness.py my_doc.txt --questions questions.json --provider gemini

questions.json format:
    ["What error caused the outage?", "Which service failed first?", ...]
"""

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import List, Optional

from context_compressor import ContextCompressor

# Per-provider defaults. Model names and free-tier limits shift often --
# these are reasonable choices as of mid/late 2026, override with --model.
PROVIDER_DEFAULTS = {
    "groq": {
        "model": "llama-3.3-70b-versatile",   # free tier: ~30 RPM, 1K RPD, 12K TPM
        "delay": 2.5,
    },
    "gemini": {
        "model": "gemini-2.5-flash-lite",     # free tier: ~15 RPM
        "delay": 5.0,
    },
}

JUDGE_PROMPT = """You are grading whether two answers to the same question agree on the \
key facts. Reference answer (from the FULL, uncompressed context):
---
{reference}
---

Candidate answer (from a COMPRESSED version of the context):
---
{candidate}
---

Question: {question}

Does the candidate answer convey the same key facts as the reference \
answer, even if worded differently? Respond with ONLY a JSON object: \
{{"agrees": true|false, "reason": "<one short sentence>"}}"""


# ─── Optional rich CLI (falls back to plain prints if not installed) ───────
try:
    from rich.console import Console
    from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    HAVE_RICH = True
    console = Console()
except ImportError:
    HAVE_RICH = False
    console = None


@dataclass
class QuestionResult:
    question: str
    reference_answer: str
    compressed_answer: str
    agrees: bool
    reason: str = ""


@dataclass
class EvalReport:
    compression_ratio: float
    original_tokens: int
    compressed_tokens: int
    results: List[QuestionResult] = field(default_factory=list)

    @property
    def retention(self) -> float:
        if not self.results:
            return 0.0
        return sum(1 for r in self.results if r.agrees) / len(self.results)

    def summary(self) -> str:
        return (
            f"compression: {self.compression_ratio*100:.1f}% reduction "
            f"({self.original_tokens} -> {self.compressed_tokens} tokens)\n"
            f"answer-accuracy retention: {self.retention*100:.1f}% "
            f"({sum(1 for r in self.results if r.agrees)}/{len(self.results)} questions agree)"
        )


def _print_err(msg: str) -> None:
    if HAVE_RICH:
        console.print(f"[bold red]{msg}[/bold red]")
    else:
        print(msg, file=sys.stderr)


# Minimum seconds between successive LLM calls. Free-tier RPM limits vary
# by provider/model and shift over time -- pacing proactively avoids
# tripping them on every call, rather than only reacting after a 429.
# Overridden by --delay (see main()).
MIN_CALL_INTERVAL_SECONDS = 3.0
_last_call_time = [0.0]


def _pace() -> None:
    elapsed = time.time() - _last_call_time[0]
    if elapsed < MIN_CALL_INTERVAL_SECONDS:
        time.sleep(MIN_CALL_INTERVAL_SECONDS - elapsed)
    _last_call_time[0] = time.time()


def _call_with_retry(fn, *args, max_retries: int = 5, **kwargs):
    """Free tiers have tight per-minute rate limits -- pace calls
    proactively (via _pace, called by callers before this) and back
    off/retry on top of that instead of failing the whole run on a
    transient 429."""
    delay = 5.0
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # broad: SDK exception types vary by provider/version
            is_rate_limit = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e).upper() or "rate_limit" in str(e).lower() or "quota" in str(e).lower()
            if is_rate_limit and attempt < max_retries - 1:
                if HAVE_RICH:
                    console.print(f"  [yellow]rate limited, retrying in {delay:.0f}s...[/yellow]")
                else:
                    print(f"  rate limited, retrying in {delay:.0f}s...", file=sys.stderr)
                time.sleep(delay)
                delay *= 2
                continue
            raise


# ─── Provider backends ──────────────────────────────────────────────────
# Each backend exposes .generate(prompt, json_mode=False) -> str, so the
# ask/judge logic below doesn't need to know which provider it's talking to.

class GroqBackend:
    def __init__(self, model: str):
        try:
            from groq import Groq
        except ImportError:
            _print_err("error: the 'groq' package is required for --provider groq.\n  pip install groq")
            sys.exit(1)
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            _print_err(
                "error: GROQ_API_KEY is not set. This harness makes real API\n"
                "calls to measure downstream answer accuracy -- it can't run without\n"
                "a key, and it won't fabricate results.\n"
                "  Get a free key (no credit card) at https://console.groq.com/keys\n"
                "  export GROQ_API_KEY=gsk_..."
            )
            sys.exit(1)
        self.client = Groq(api_key=api_key)
        self.model = model

    def generate(self, prompt: str, json_mode: bool = False) -> str:
        kwargs = {"response_format": {"type": "json_object"}} if json_mode else {}
        _pace()
        resp = _call_with_retry(
            self.client.chat.completions.create,
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            **kwargs,
        )
        return (resp.choices[0].message.content or "").strip()


class GeminiBackend:
    def __init__(self, model: str):
        try:
            from google import genai
        except ImportError:
            _print_err("error: the 'google-genai' package is required for --provider gemini.\n  pip install google-genai")
            sys.exit(1)
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            _print_err(
                "error: GEMINI_API_KEY is not set. This harness makes real API\n"
                "calls to measure downstream answer accuracy -- it can't run without\n"
                "a key, and it won't fabricate results.\n"
                "  Get a free key at https://aistudio.google.com/apikey\n"
                "  export GEMINI_API_KEY=AIza..."
            )
            sys.exit(1)
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def generate(self, prompt: str, json_mode: bool = False) -> str:
        from google.genai import types
        config = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
        _pace()
        resp = _call_with_retry(self.client.models.generate_content, model=self.model, contents=prompt, config=config)
        return (resp.text or "").strip()


def _get_backend(provider: str, model: str):
    if provider == "groq":
        return GroqBackend(model)
    if provider == "gemini":
        return GeminiBackend(model)
    raise ValueError(f"unknown provider: {provider}")


def _ask(backend, context: str, question: str) -> str:
    prompt = (
        f"Context:\n---\n{context}\n---\n\nQuestion: {question}\n\n"
        f"Answer using only the context above. Be concise."
    )
    return backend.generate(prompt)


def _judge(backend, question: str, reference: str, candidate: str) -> QuestionResult:
    prompt = JUDGE_PROMPT.format(reference=reference, candidate=candidate, question=question)
    raw = backend.generate(prompt, json_mode=True)
    try:
        parsed = json.loads(raw)
        agrees = bool(parsed.get("agrees", False))
        reason = str(parsed.get("reason", ""))
    except (json.JSONDecodeError, AttributeError):
        agrees = "true" in raw.lower()[:20]
        reason = "judge response was not valid JSON; fell back to keyword match"
    return QuestionResult(question=question, reference_answer=reference,
                           compressed_answer=candidate, agrees=agrees, reason=reason)


def run_eval(
    text: str,
    questions: List[str],
    target_compression: float = 0.70,
    provider: str = "groq",
    model: Optional[str] = None,
    preset: Optional[str] = None,
) -> EvalReport:
    model = model or PROVIDER_DEFAULTS[provider]["model"]
    backend = _get_backend(provider, model)

    compressor = (
        ContextCompressor.from_preset(preset, target_compression=target_compression)
        if preset else ContextCompressor(target_compression=target_compression)
    )
    report = compressor.compress(text)

    results: List[QuestionResult] = []

    if HAVE_RICH:
        with Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=30),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Evaluating questions...", total=len(questions))
            for q in questions:
                progress.update(task, description=f"[bold cyan]Asking:[/bold cyan] {q[:50]}")
                reference = _ask(backend, text, q)
                candidate = _ask(backend, report.compressed_text, q)
                results.append(_judge(backend, q, reference, candidate))
                progress.advance(task)
    else:
        for i, q in enumerate(questions, 1):
            print(f"[{i}/{len(questions)}] asking: {q}", file=sys.stderr)
            reference = _ask(backend, text, q)
            candidate = _ask(backend, report.compressed_text, q)
            results.append(_judge(backend, q, reference, candidate))

    return EvalReport(
        compression_ratio=report.compression_ratio,
        original_tokens=report.original_tokens,
        compressed_tokens=report.compressed_tokens,
        results=results,
    )


def _print_report_rich(report: EvalReport) -> None:
    retention_pct = report.retention * 100
    color = "green" if retention_pct >= 80 else "yellow" if retention_pct >= 50 else "red"

    table = Table(box=box.ROUNDED, show_lines=True, expand=True)
    table.add_column("Result", justify="center", width=6)
    table.add_column("Question", ratio=2)
    table.add_column("Judge reason", ratio=3, style="dim")

    for r in report.results:
        mark = "[bold green]PASS[/bold green]" if r.agrees else "[bold red]FAIL[/bold red]"
        table.add_row(mark, r.question, r.reason)

    console.print(table)

    passed = sum(1 for r in report.results if r.agrees)
    summary_text = (
        f"[bold]Compression:[/bold] {report.compression_ratio*100:.1f}% reduction "
        f"({report.original_tokens:,} -> {report.compressed_tokens:,} tokens)\n"
        f"[bold]Answer-accuracy retention:[/bold] "
        f"[{color}]{retention_pct:.1f}%[/{color}] ({passed}/{len(report.results)} questions agree)"
    )
    console.print(Panel(summary_text, title="Eval Summary", border_style=color, box=box.ROUNDED))


def _print_report_plain(report: EvalReport) -> None:
    print(report.summary())
    print()
    for r in report.results:
        mark = "PASS" if r.agrees else "FAIL"
        print(f"[{mark}] {r.question}")
        print(f"   reason: {r.reason}")


def main(argv=None) -> int:
    global MIN_CALL_INTERVAL_SECONDS
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="Document to test compression accuracy on")
    parser.add_argument("--questions", required=True, help="JSON file: a list of question strings")
    parser.add_argument("--target", type=float, default=0.70)
    parser.add_argument("--preset", choices=["conservative", "balanced", "aggressive"], default=None)
    parser.add_argument("--provider", choices=list(PROVIDER_DEFAULTS), default="groq",
                         help="Which LLM API to use (default: groq -- free, no credit card)")
    parser.add_argument("--model", default=None,
                         help="Model name to use (default: provider's free-tier default)")
    parser.add_argument("--delay", type=float, default=None,
                         help="Minimum seconds between API calls, to stay under free-tier rate limits "
                              "(default: provider-specific)")
    args = parser.parse_args(argv)

    model = args.model or PROVIDER_DEFAULTS[args.provider]["model"]
    MIN_CALL_INTERVAL_SECONDS = args.delay if args.delay is not None else PROVIDER_DEFAULTS[args.provider]["delay"]

    with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    with open(args.questions, "r", encoding="utf-8") as f:
        questions = json.load(f)

    if HAVE_RICH:
        console.print(Panel(
            f"[bold]{args.file}[/bold]  ->  target {args.target*100:.0f}% reduction  "
            f"({args.preset or 'custom'} preset, provider: {args.provider}, model: {model})",
            title="Context Compressor -- Downstream Accuracy Eval",
            border_style="cyan", box=box.ROUNDED,
        ))

    report = run_eval(text, questions, target_compression=args.target, provider=args.provider, model=model, preset=args.preset)

    if HAVE_RICH:
        _print_report_rich(report)
    else:
        _print_report_plain(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
