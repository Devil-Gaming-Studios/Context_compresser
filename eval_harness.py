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
  2. Asks a set of questions against the ORIGINAL text via the
     Anthropic API and records the answers as a reference.
  3. Asks the same questions against the COMPRESSED text.
  4. Uses a judge call (same model) to score each compressed-context
     answer against the original-context answer for factual agreement.
  5. Reports per-question and aggregate retention.

Requires: `pip install anthropic` and an ANTHROPIC_API_KEY environment
variable. Without a key, this script will explain that and exit --
it will not fabricate results.

Usage:
    export ANTHROPIC_API_KEY=sk-ant-...
    python eval_harness.py my_doc.txt --questions questions.json --target 0.7

questions.json format:
    ["What error caused the outage?", "Which service failed first?", ...]
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

from context_compressor import ContextCompressor

MODEL = "claude-sonnet-4-5"  # override with --model if desired

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


def _get_client():
    try:
        import anthropic
    except ImportError:
        print(
            "error: the 'anthropic' package is required for eval_harness.py.\n"
            "  pip install anthropic",
            file=sys.stderr,
        )
        sys.exit(1)

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print(
            "error: ANTHROPIC_API_KEY is not set. This harness makes real API\n"
            "calls to measure downstream answer accuracy -- it can't run without\n"
            "a key, and it won't fabricate results.\n"
            "  export ANTHROPIC_API_KEY=sk-ant-...",
            file=sys.stderr,
        )
        sys.exit(1)
    return anthropic.Anthropic(api_key=api_key)


def _ask(client, context: str, question: str, model: str) -> str:
    resp = client.messages.create(
        model=model,
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"Context:\n---\n{context}\n---\n\nQuestion: {question}\n\n"
                       f"Answer using only the context above. Be concise.",
        }],
    )
    return "".join(block.text for block in resp.content if hasattr(block, "text")).strip()


def _judge(client, question: str, reference: str, candidate: str, model: str) -> QuestionResult:
    prompt = JUDGE_PROMPT.format(reference=reference, candidate=candidate, question=question)
    resp = client.messages.create(
        model=model,
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = "".join(block.text for block in resp.content if hasattr(block, "text")).strip()
    raw = raw.strip("`").removeprefix("json").strip()
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
    model: str = MODEL,
    preset: Optional[str] = None,
) -> EvalReport:
    client = _get_client()

    compressor = (
        ContextCompressor.from_preset(preset, target_compression=target_compression)
        if preset else ContextCompressor(target_compression=target_compression)
    )
    report = compressor.compress(text)

    results = []
    for q in questions:
        reference = _ask(client, text, q, model)
        candidate = _ask(client, report.compressed_text, q, model)
        results.append(_judge(client, q, reference, candidate, model))

    return EvalReport(
        compression_ratio=report.compression_ratio,
        original_tokens=report.original_tokens,
        compressed_tokens=report.compressed_tokens,
        results=results,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="Document to test compression accuracy on")
    parser.add_argument("--questions", required=True, help="JSON file: a list of question strings")
    parser.add_argument("--target", type=float, default=0.70)
    parser.add_argument("--preset", choices=["conservative", "balanced", "aggressive"], default=None)
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args(argv)

    with open(args.file, "r", encoding="utf-8", errors="ignore") as f:
        text = f.read()
    with open(args.questions, "r", encoding="utf-8") as f:
        questions = json.load(f)

    report = run_eval(text, questions, target_compression=args.target, model=args.model, preset=args.preset)

    print(report.summary())
    print()
    for r in report.results:
        mark = "PASS" if r.agrees else "FAIL"
        print(f"[{mark}] {r.question}")
        print(f"   reason: {r.reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
