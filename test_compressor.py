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
from context_compressor.git_diff import parse_unified_diff, compress_diff
from context_compressor.session_compressor import compress_session, parse_export


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


_SAMPLE_DIFF = """diff --git a/app.py b/app.py
index 111..222 100644
--- a/app.py
+++ b/app.py
@@ -1,6 +1,7 @@
 import utils


-def compute_total(items):
+def compute_total(items, discount=0):
     total = 0
     for item in items:
         total = utils.add(total, item)
+    total = utils.apply_discount(total, discount)
     return total
diff --git a/utils.py b/utils.py
index 333..444 100644
--- a/utils.py
+++ b/utils.py
@@ -6,3 +6,7 @@ def add(a, b):
 def unrelated_helper(x):
     return x
+
+
+def apply_discount(total, discount):
+    return total * (1 - discount)
"""

_APP_PY_NEW = (
    "import utils\n\n\n"
    "def compute_total(items, discount=0):\n"
    "    total = 0\n"
    "    for item in items:\n"
    "        total = utils.add(total, item)\n"
    "    total = utils.apply_discount(total, discount)\n"
    "    return total\n"
)

_UTILS_PY_NEW = (
    "def add(a, b):\n"
    "    return a + b\n\n\n"
    "def unrelated_helper(x):\n"
    "    return x\n\n\n"
    "def apply_discount(total, discount):\n"
    "    return total * (1 - discount)\n"
)


def test_parse_unified_diff_finds_hunks_per_file():
    parsed = parse_unified_diff(_SAMPLE_DIFF)
    assert set(parsed.keys()) == {"app.py", "utils.py"}
    assert len(parsed["app.py"]) == 1
    assert len(parsed["utils.py"]) == 1
    print("PASS: unified diff parsing finds hunks for each changed file")


def test_compress_diff_keeps_changed_and_cross_file_dependency():
    report = compress_diff(
        diff_text=_SAMPLE_DIFF,
        file_contents={"app.py": _APP_PY_NEW, "utils.py": _UTILS_PY_NEW},
        target_compression=0.5,
    )
    by_path = {f.path: f for f in report.files}
    assert "compute_total" in by_path["app.py"].compressed_text
    assert "apply_discount" in by_path["utils.py"].compressed_text
    # `add` isn't touched by the diff at all, but app.py's changed block
    # still calls utils.add -- cross-file closure must pull it back in.
    assert "def add(" in by_path["utils.py"].compressed_text
    assert by_path["utils.py"].dependency_blocks_restored >= 1
    print("PASS: diff-aware compression keeps changed blocks and restores cross-file dependency")


def test_session_protects_system_and_recent_turns():
    import json

    messages = [
        {"role": "system", "content": "You are a helpful assistant that writes concise answers."},
        {"role": "user", "content": "What's the capital of France, and can you tell me a bit about its history?"},
        {"role": "assistant", "content": "The capital of France is Paris, a city with over two thousand years of history."},
        {"role": "user", "content": "thanks, what about Germany?"},
    ]
    report = compress_session(json.dumps(messages), protect_recent=1, target_compression=0.6)
    assert report.turns[0].action == "protected_system"
    assert report.turns[0].content == messages[0]["content"]
    assert report.turns[-1].action == "protected_recent"
    assert report.turns[-1].content == messages[-1]["content"]
    print("PASS: session compression protects system prompt and recent turns verbatim")


def test_session_drops_duplicate_older_turns():
    import json

    q = "Can you explain how binary search works and why it's O(log n) time complexity?"
    a = "Binary search repeatedly halves the search interval, giving O(log n) time complexity."
    messages = [
        {"role": "user", "content": q},
        {"role": "assistant", "content": a},
        {"role": "user", "content": q},
        {"role": "assistant", "content": a},
        {"role": "user", "content": "got it, thanks"},
    ]
    report = compress_session(json.dumps(messages), protect_recent=1, target_compression=0.5)
    assert report.turns_dropped_duplicate >= 1
    dropped = [t for t in report.turns if t.action == "dropped_duplicate"]
    assert len(dropped) >= 1
    print("PASS: session compression drops duplicate older turns")


def test_session_compresses_older_turns_below_original_size():
    import json

    long_turn = ("I was wondering if you could help me understand how Python's garbage collector "
                 "decides when to reclaim memory. I keep hearing conflicting things about reference "
                 "counting versus the generational collector. Honestly I've read the docs a few times "
                 "already but it still isn't clicking for me. I want to make sure I actually "
                 "understand it properly before my exam next week. Could you walk me through it?")
    messages = [
        {"role": "user", "content": long_turn},
        {"role": "assistant", "content": "Python primarily uses reference counting, with a generational "
                                          "garbage collector to catch reference cycles that counting alone misses."},
        {"role": "user", "content": "makes sense, thanks!"},
    ]
    report = compress_session(json.dumps(messages), protect_recent=1, target_compression=0.6)
    assert report.compressed_tokens < report.original_tokens
    print("PASS: session compression reduces token count on older turns")


def test_parse_export_detects_chatgpt_and_claude_formats():
    import json

    chatgpt_export = {
        "mapping": {
            "root": {"id": "root", "message": None, "parent": None, "children": ["m1"]},
            "m1": {"id": "m1", "parent": "root", "children": [],
                   "message": {"author": {"role": "user"}, "content": {"parts": ["hello"]}}},
        },
        "current_node": "m1",
    }
    turns, fmt = parse_export(json.dumps(chatgpt_export))
    assert fmt == "chatgpt" and turns[0].content == "hello"

    claude_export = {"chat_messages": [{"sender": "human", "text": "hi"}, {"sender": "assistant", "text": "hello!"}]}
    turns, fmt = parse_export(json.dumps(claude_export))
    assert fmt == "claude" and turns[0].role == "user" and turns[1].role == "assistant"

    generic = [{"role": "user", "content": "hi"}]
    turns, fmt = parse_export(json.dumps(generic))
    assert fmt == "generic"
    print("PASS: parse_export auto-detects chatgpt/claude/generic export formats")


def test_session_never_crashes_on_short_transcript():
    import json

    report = compress_session(json.dumps([{"role": "user", "content": "hi"}]), protect_recent=4)
    assert report.turns_total == 1
    assert report.turns[0].action == "protected_recent"
    print("PASS: session compression handles a transcript shorter than protect_recent")


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
    test_parse_unified_diff_finds_hunks_per_file()
    test_compress_diff_keeps_changed_and_cross_file_dependency()
    test_session_protects_system_and_recent_turns()
    test_session_drops_duplicate_older_turns()
    test_session_compresses_older_turns_below_original_size()
    test_parse_export_detects_chatgpt_and_claude_formats()
    test_session_never_crashes_on_short_transcript()
    print("\nAll tests passed.")
