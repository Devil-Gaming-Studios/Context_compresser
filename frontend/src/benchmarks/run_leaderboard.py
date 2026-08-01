#!/usr/bin/env python3
"""
Public benchmark leaderboard runner.

Two things get measured, and they're reported separately because they
answer different questions:

  1. Compression ratio (always runs, no API key needed) -- how much
     smaller is the output, in tokens, at a fixed target.
  2. Answer-quality retention (only runs with --with-quality and an
     ANTHROPIC_API_KEY) -- does a real model still answer correctly off
     the compressed text. This reuses the same judge-call approach as
     eval_harness.py, just fanned out across every adapter in
     benchmarks/adapters.py instead of only ours.

A compression ratio number with no retention number next to it is a
vanity metric -- you can hit 99% by deleting everything. This script
refuses to publish one without clearly labelling the other as
"not run" rather than inventing a number.

Usage:
    python benchmarks/run_leaderboard.py
    python benchmarks/run_leaderboard.py --with-quality --target 0.7
    python benchmarks/run_leaderboard.py --only ours,naive_truncation
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters import get_adapters, Adapter  # noqa: E402

DATASETS_DIR = Path(__file__).parent.parent / "sample_data"
EXTRA_DATASETS = [Path(__file__).parent.parent / "README.md"]
QUESTIONS_DIR = Path(__file__).parent / "questions"
RESULTS_PATH = Path(__file__).parent / "results.json"
FRONTEND_PUBLIC_COPY = Path(__file__).parent.parent / "frontend" / "public" / "benchmarks-results.json"


@dataclass
class DatasetResult:
    dataset: str
    adapter_key: str
    adapter_name: str
    adapter_url: str
    original_tokens: int
    compressed_tokens: int
    compression_ratio: float
    retention: Optional[float] = None
    retention_questions: Optional[int] = None
    skipped_reason: Optional[str] = None


def _list_datasets() -> List[Path]:
    files = sorted(DATASETS_DIR.glob("*")) if DATASETS_DIR.exists() else []
    return files + [p for p in EXTRA_DATASETS if p.exists()]


def _run_quality_eval(adapter: Adapter, text: str, compressed_text: str, questions: List[str],
                       model: str) -> Optional[float]:
    """Reuses eval_harness's ask+judge pattern against one adapter's output."""
    from eval_harness import _get_client, _ask, _judge  # local import: needs anthropic + key

    client = _get_client()
    agrees = 0
    for q in questions:
        reference = _ask(client, text, q, model)
        candidate = _ask(client, compressed_text, q, model)
        result = _judge(client, q, reference, candidate, model)
        agrees += int(result.agrees)
    return agrees / len(questions) if questions else None


def run(target: float, with_quality: bool, only: Optional[List[str]], model: str) -> List[DatasetResult]:
    adapters = get_adapters(only)
    results: List[DatasetResult] = []

    for dataset_path in _list_datasets():
        text = dataset_path.read_text(encoding="utf-8", errors="ignore")
        questions_path = QUESTIONS_DIR / f"{dataset_path.stem}.json"
        questions = json.loads(questions_path.read_text()) if questions_path.exists() else []

        for adapter in adapters:
            if not adapter.available():
                results.append(DatasetResult(
                    dataset=dataset_path.name, adapter_key=adapter.key,
                    adapter_name=adapter.display_name, adapter_url=adapter.url,
                    original_tokens=0, compressed_tokens=0, compression_ratio=0.0,
                    skipped_reason=adapter.availability_note,
                ))
                print(f"[skip] {adapter.display_name} on {dataset_path.name}: {adapter.availability_note}")
                continue

            try:
                out = adapter.compress(text, target)
            except Exception as e:  # baseline models can fail offline; don't kill the whole run
                results.append(DatasetResult(
                    dataset=dataset_path.name, adapter_key=adapter.key,
                    adapter_name=adapter.display_name, adapter_url=adapter.url,
                    original_tokens=0, compressed_tokens=0, compression_ratio=0.0,
                    skipped_reason=f"error: {e}",
                ))
                print(f"[error] {adapter.display_name} on {dataset_path.name}: {e}")
                continue

            retention = None
            n_q = None
            if with_quality and questions:
                retention = _run_quality_eval(adapter, text, out.compressed_text, questions, model)
                n_q = len(questions)

            r = DatasetResult(
                dataset=dataset_path.name, adapter_key=adapter.key,
                adapter_name=adapter.display_name, adapter_url=adapter.url,
                original_tokens=out.original_tokens, compressed_tokens=out.compressed_tokens,
                compression_ratio=out.compression_ratio, retention=retention, retention_questions=n_q,
            )
            results.append(r)
            ratio_str = f"{r.compression_ratio * 100:.1f}%"
            ret_str = f", retention {retention*100:.1f}%" if retention is not None else ""
            print(f"[ok]   {adapter.display_name:38s} {dataset_path.name:20s} ratio {ratio_str}{ret_str}")

    return results


def aggregate(results: List[DatasetResult]) -> Dict[str, dict]:
    """Per-adapter rollup across all datasets, for the leaderboard table."""
    by_adapter: Dict[str, dict] = {}
    for r in results:
        if r.skipped_reason:
            by_adapter.setdefault(r.adapter_key, {
                "adapter_name": r.adapter_name, "adapter_url": r.adapter_url,
                "skipped_reason": r.skipped_reason, "datasets": 0,
                "total_original": 0, "total_compressed": 0, "retentions": [],
            })
            continue
        entry = by_adapter.setdefault(r.adapter_key, {
            "adapter_name": r.adapter_name, "adapter_url": r.adapter_url,
            "skipped_reason": None, "datasets": 0,
            "total_original": 0, "total_compressed": 0, "retentions": [],
        })
        entry["datasets"] += 1
        entry["total_original"] += r.original_tokens
        entry["total_compressed"] += r.compressed_tokens
        if r.retention is not None:
            entry["retentions"].append(r.retention)

    summary = {}
    for key, entry in by_adapter.items():
        ratio = (1 - entry["total_compressed"] / entry["total_original"]) if entry["total_original"] else None
        avg_retention = sum(entry["retentions"]) / len(entry["retentions"]) if entry["retentions"] else None
        summary[key] = {
            "adapter_name": entry["adapter_name"],
            "adapter_url": entry["adapter_url"],
            "skipped_reason": entry["skipped_reason"],
            "datasets_evaluated": entry["datasets"],
            "overall_compression_ratio": ratio,
            "avg_retention": avg_retention,
        }
    return summary


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--target", type=float, default=0.70, help="Target compression fraction")
    parser.add_argument("--with-quality", action="store_true",
                         help="Also run LLM-judged answer retention (needs ANTHROPIC_API_KEY + questions/*.json)")
    parser.add_argument("--only", default=None, help="Comma-separated adapter keys to run")
    parser.add_argument("--model", default="claude-sonnet-4-5")
    args = parser.parse_args(argv)

    only = args.only.split(",") if args.only else None
    results = run(target=args.target, with_quality=args.with_quality, only=only, model=args.model)
    summary = aggregate(results)

    payload = {
        "target_compression": args.target,
        "quality_eval_ran": args.with_quality,
        "per_dataset": [asdict(r) for r in results],
        "leaderboard": summary,
    }
    serialized = json.dumps(payload, indent=2)
    RESULTS_PATH.write_text(serialized)
    print(f"\nWrote {RESULTS_PATH}")
    print("Open benchmarks/leaderboard.html (served, not file://) to view it.")

    if FRONTEND_PUBLIC_COPY.parent.exists():
        FRONTEND_PUBLIC_COPY.write_text(serialized)
        print(f"Also updated {FRONTEND_PUBLIC_COPY} -- the in-app /benchmarks page will reflect this run.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
