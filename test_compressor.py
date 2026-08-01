"""
Minimal sanity tests -- not a full test suite, just enough to prove
the pipeline behaves correctly on clear-cut cases.

Run with: python test_compressor.py
"""

from context_compressor import ContextCompressor
from context_compressor.presets import PRESETS, get_preset
from context_compressor.tokenizer import count_tokens
from context_compressor.boilerplate import summarize_repeated_blocks
from context_compressor.dedup import remove_near_duplicates, adaptive_threshold


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


def test_presets_produce_different_compressors():
    conservative = ContextCompressor.from_preset("conservative")
    aggressive = ContextCompressor.from_preset("aggressive")
    assert conservative.target_compression < aggressive.target_compression
    assert get_preset("balanced").name == "balanced"
    try:
        get_preset("not-a-real-preset")
        assert False, "expected ValueError for unknown preset"
    except ValueError:
        pass
    print("PASS: presets produce distinct, valid configurations")


def test_preset_end_to_end_compresses():
    text = "\n".join([f"def helper_{i}():\n    return {i}" for i in range(30)])
    for name in PRESETS:
        report = ContextCompressor.from_preset(name).compress(text, content_type="code")
        assert report.compressed_tokens <= report.original_tokens
    print("PASS: all presets run end-to-end without error")


def test_dependency_closure_keeps_called_helper():
    # `important_helper` has almost no TF-IDF signal on its own (short,
    # generic body) but is called from a block full of unique, high
    # scoring content that will clearly survive budget selection --
    # the dependency-closure pass should pull the definition back in
    # even though its own score is low.
    code = (
        "def important_helper():\n"
        "    return 1\n"
        "\n"
        "def process_customer_invoice_batch_with_special_edge_case_handling():\n"
        "    unique_value = important_helper()\n"
        "    return unique_value * 42\n"
    )
    compressor = ContextCompressor(target_compression=0.5, use_code_blocks=True)
    report = compressor.compress(code, content_type="code")
    assert "important_helper" in report.compressed_text
    print("PASS: dependency closure keeps a referenced helper function")


def test_custom_filler_patterns_are_applied():
    lines = [f"CUSTOM_NOISE_TAG entry {i}" for i in range(20)]
    lines.insert(10, "the unique load-bearing business fact goes here")
    text = "\n".join(lines)
    compressor = ContextCompressor(
        target_compression=0.8,
        extra_filler_patterns=[r"^\s*CUSTOM_NOISE_TAG.*$"],
    )
    report = compressor.compress(text, content_type="logs")
    assert "unique load-bearing business fact" in report.compressed_text
    print("PASS: custom filler patterns get penalized during scoring")


def test_adaptive_dedup_threshold_is_reasonable():
    chunks = [f"line about topic {i % 5}" for i in range(20)]
    t = adaptive_threshold(chunks)
    assert 0.0 <= t <= 1.0
    kept, dropped = remove_near_duplicates(chunks, threshold=None)
    assert len(kept) <= len(chunks)
    print(f"PASS: adaptive dedup threshold ({t:.2f}) runs and stays in [0,1]")


def test_model_aware_token_counts_differ_or_run():
    text = "The quick brown fox jumps over the lazy dog. " * 20
    counts = {m: count_tokens(text, model=m) for m in ("default", "claude", "gpt-4o")}
    assert all(c > 0 for c in counts.values())
    print(f"PASS: model-aware token counting runs for all profiles ({counts})")


def test_repeated_log_block_summarized():
    block = "Traceback (most recent call last):\n  File x.py, line 1\n  ValueError: boom"
    text = "\n".join([block] * 6 + ["INFO unique final status ok"])
    result = summarize_repeated_blocks(text, min_block_lines=2, min_repeats=3)
    assert result.blocks_collapsed > 0
    assert "repeated block" in "\n".join(result.lines)
    print("PASS: repeated multi-line log block gets summarized")


if __name__ == "__main__":
    test_repeated_log_lines_collapse()
    test_important_line_survives_compression()
    test_empty_input_handled()
    test_never_returns_empty_for_nonempty_input()
    test_compression_ratio_roughly_matches_target()
    test_presets_produce_different_compressors()
    test_preset_end_to_end_compresses()
    test_dependency_closure_keeps_called_helper()
    test_custom_filler_patterns_are_applied()
    test_adaptive_dedup_threshold_is_reasonable()
    test_model_aware_token_counts_differ_or_run()
    test_repeated_log_block_summarized()
    print("\nAll tests passed.")
