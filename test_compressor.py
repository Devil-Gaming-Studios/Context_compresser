"""
Minimal sanity tests -- not a full test suite, just enough to prove
the pipeline behaves correctly on clear-cut cases.

Run with: python test_compressor.py
"""

from context_compressor import ContextCompressor


def test_repeated_log_lines_collapse():
    text = "\n".join([f"INFO heartbeat ok req_id={i}" for i in range(50)])
    compressor = ContextCompressor(target_compression=0.5)
    report = compressor.compress(text)
    assert report.compressed_tokens < report.original_tokens
    assert "x" in report.compressed_text.lower() or report.chunks_kept < 50
    print("PASS: repeated log lines collapse")


def test_important_line_survives_compression():
    lines = [f"INFO heartbeat ok req_id={i}" for i in range(40)]
    lines.insert(20, "CRITICAL database failover triggered primary lost")
    text = "\n".join(lines)
    compressor = ContextCompressor(target_compression=0.7)
    report = compressor.compress(text)
    assert "CRITICAL" in report.compressed_text
    print("PASS: critical line survives aggressive compression")


def test_empty_input_handled():
    compressor = ContextCompressor()
    report = compressor.compress("")
    assert report.original_tokens == 0
    assert report.compressed_text == ""
    print("PASS: empty input handled without crashing")


def test_never_returns_empty_for_nonempty_input():
    compressor = ContextCompressor(target_compression=0.99)
    report = compressor.compress("just one short line of text here")
    assert report.compressed_text.strip() != ""
    print("PASS: never over-compresses to nothing")


def test_compression_ratio_roughly_matches_target():
    # Mix of genuinely distinct lines so the compressor can't just
    # collapse everything as near-duplicates -- this tests the budget
    # selection logic, not the dedup logic.
    lines = [f"unique topic {i}: {' '.join(['word' + str(j) for j in range(i % 7, i % 7 + 5)])}" for i in range(60)]
    text = "\n".join(lines)
    compressor = ContextCompressor(target_compression=0.6)
    report = compressor.compress(text)
    # allow generous tolerance since chunk granularity affects exact ratio
    assert 0.3 <= report.compression_ratio <= 0.95
    print(f"PASS: compression ratio {report.compression_ratio:.2f} within reasonable band of 0.6 target")


if __name__ == "__main__":
    test_repeated_log_lines_collapse()
    test_important_line_survives_compression()
    test_empty_input_handled()
    test_never_returns_empty_for_nonempty_input()
    test_compression_ratio_roughly_matches_target()
    print("\nAll tests passed.")
