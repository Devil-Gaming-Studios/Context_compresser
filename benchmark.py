"""
Runs ContextCompressor against the sample data and prints a before/after
report: token counts, compression ratio, and what got removed/collapsed.

Usage:
    python benchmark.py
    python benchmark.py path/to/your/file.txt --target 0.6
"""

import argparse
import sys
from pathlib import Path

from context_compressor import ContextCompressor


def run_on_file(path: Path, target_compression: float):
    text = path.read_text()
    compressor = ContextCompressor(target_compression=target_compression)
    report = compressor.compress(text)

    print(f"\n{'=' * 70}")
    print(f"FILE: {path.name}")
    print(f"{'=' * 70}")
    print(f"Original tokens:    {report.original_tokens}")
    print(f"Compressed tokens:  {report.compressed_tokens}")
    print(f"Compression ratio:  {report.compression_ratio * 100:.1f}%")
    print(f"Chunks kept:        {report.chunks_kept}/{report.chunks_total}")
    print(f"Near-dups removed:  {report.near_duplicates_removed}")
    print("\n--- pipeline notes ---")
    for n in report.notes:
        print(f"  - {n}")
    print("\n--- compressed output (preview) ---")
    preview = report.compressed_text[:600]
    print(preview + ("..." if len(report.compressed_text) > 600 else ""))
    return report


def main():
    parser = argparse.ArgumentParser(description="Benchmark the context compressor")
    parser.add_argument("file", nargs="?", help="File to compress (defaults to sample_data/*)")
    parser.add_argument("--target", type=float, default=0.70,
                         help="Target compression fraction, e.g. 0.70 = remove 70%% of tokens")
    args = parser.parse_args()

    if args.file:
        run_on_file(Path(args.file), args.target)
        return

    sample_dir = Path(__file__).parent / "sample_data"
    files = sorted(sample_dir.glob("*"))
    if not files:
        print("No sample files found.", file=sys.stderr)
        sys.exit(1)

    total_orig, total_comp = 0, 0
    for f in files:
        report = run_on_file(f, args.target)
        total_orig += report.original_tokens
        total_comp += report.compressed_tokens

    print(f"\n{'=' * 70}")
    print("OVERALL")
    print(f"{'=' * 70}")
    overall_ratio = 1 - (total_comp / total_orig) if total_orig else 0
    print(f"Total tokens:       {total_orig} -> {total_comp}")
    print(f"Overall reduction:  {overall_ratio * 100:.1f}%")
    print(
        "\nNote: this measures token/compression ratio only. Downstream "
        "answer-accuracy retention (the 95%+ target) requires running the "
        "compressed vs. original context through a real LLM eval -- wire "
        "your Anthropic API key into a small eval harness that asks the "
        "same questions against both versions and compares answers."
    )


if __name__ == "__main__":
    main()
