# Context Compressor

An algorithmic pre-processor that strips redundant, low-information tokens
from large LLM contexts (codebases, logs, long documents) before they're
sent to a model — cutting prompt size while preserving the content that
actually matters.

## How it works

```
raw text
   │
   ▼
1. Structural boilerplate strip     (collapse blank-line runs, collapse
                                      near-identical repeated lines —
                                      e.g. 500 heartbeat logs -> 1 line + count)
   │
   ▼
2. Chunking                         (split into lines for code/logs,
                                      sentences for prose)
   │
   ▼
3. Semantic near-duplicate removal  (TF-IDF cosine similarity between
                                      chunks — catches reworded repeats
                                      exact-match dedup misses)
   │
   ▼
4. Information-density scoring      (TF-IDF mass per chunk, penalized
                                      for known filler patterns like bare
                                      imports/comments/heartbeat logs)
   │
   ▼
5. Budget-constrained selection     (greedily keep highest-scoring chunks,
                                      restored to original order, until
                                      the token budget is hit)
   │
   ▼
compressed text
```

No embedding model download is required — steps 3 and 4 use TF-IDF
statistics computed directly over the input document, so the whole
pipeline runs fully offline.

## Usage

```python
from context_compressor import ContextCompressor

compressor = ContextCompressor(target_compression=0.70)  # remove ~70% of tokens
report = compressor.compress(open("my_logs.txt").read())

print(report.summary())
print(report.compressed_text)
```

### Presets

```python
from context_compressor import ContextCompressor

compressor = ContextCompressor.from_preset("aggressive")  # or "conservative" / "balanced"
report = compressor.compress(text)
```

| preset | target reduction | dedup threshold | accuracy floor |
|---|---|---|---|
| `conservative` | 40% | 0.92 | 0.98 |
| `balanced` (default) | 70% | 0.85 | 0.95 |
| `aggressive` | 85% | 0.75 | 0.90 |

### Code-aware chunking + dependency closure

For code, the compressor doesn't just chunk by line. It groups Python
source into logical blocks (functions/classes) via `ast`, and other
languages into indentation-based blocks. It then builds a symbol table
and runs a **dependency closure** pass: if a kept block still calls a
helper defined elsewhere, that definition is force-kept even if its
own TF-IDF score looked low. This avoids the common failure mode of
extractive code compression -- dropping a one-line helper that's
still called from code you kept, leaving behind code that references
something that no longer exists in the output.

```python
compressor = ContextCompressor(use_code_blocks=True)  # default
```

### Multi-file / repository compression

```python
from context_compressor.multifile import compress_repo

report = compress_repo("./my_project", target_compression=0.7)
print(report.summary())
for file_report in report.files:
    print(file_report.path, file_report.original_tokens, "->", file_report.compressed_tokens)
```

This builds a **repo-wide symbol table** across all files, compresses
each file against a shared token budget proportional to its size, then
runs a cross-file dependency closure: if `app.py` still calls a helper
defined in `utils.py`, that helper survives even if `utils.py`'s own
local budget would have dropped it.

### Diff-aware compression (compress just a PR/commit)

Compressing a whole file (or repo) is the wrong unit of work when what
you actually want is "give the model enough context to review this
change." `compress_diff` parses a unified diff, force-keeps every
logical block the diff touches, restores any symbol those blocks still
depend on (including across files — e.g. an edited function in `app.py`
calling an untouched helper in `utils.py`), and fills whatever budget
is left with the highest-value surrounding context.

```python
from context_compressor.git_diff import compress_diff

# Option A: local git repo -- shells out to `git diff` / `git show` itself
report = compress_diff(repo_path="./my_project", base_ref="HEAD~1")

# Option B: bring your own diff (e.g. downloaded from a GitHub PR's
# `.diff` URL) -- no git repo or network access needed on this end
report = compress_diff(
    diff_text=raw_diff_text,
    file_contents={"app.py": "...full new source of app.py...", "utils.py": "..."},
)

print(report.summary())
for f in report.files:
    print(f.path, f.original_tokens, "->", f.compressed_tokens,
          f"({f.changed_blocks_kept} changed, {f.dependency_blocks_restored} dependency-restored)")
```

This is a heuristic diff-touched-block detector, not a `git blame`-level
tool — it doesn't reach outside the diff's own changed files for
dependencies (a symbol defined in a file the diff never touches won't
be pulled in). `compress_diff` itself still makes no GitHub API or
network calls; point it at a local repo or hand it a diff + file
contents yourself.

#### Option C: point it at a GitHub PR and let it fetch (`github_fetch`)

If you don't want to download the `.diff` and every changed file by
hand, `github_fetch` does that step for you and feeds the result
straight into `compress_diff`:

```python
from context_compressor.github_fetch import fetch_pr_diff_and_files, parse_pr_reference
from context_compressor.git_diff import compress_diff

owner, repo, pr_number = parse_pr_reference("https://github.com/owner/repo/pull/123")
diff_text, file_contents = fetch_pr_diff_and_files(owner, repo, pr_number)
report = compress_diff(diff_text=diff_text, file_contents=file_contents)
```

This is a plain, unauthenticated call to GitHub's public REST API and
`raw.githubusercontent.com` (stdlib `urllib`, no new dependency) — **not**
an OAuth "connect your account" flow, and it doesn't browse repos or list
PRs for you; you still give it one PR reference. It works out of the box
for public repos (capped at 60 requests/hour per IP by GitHub); set the
`GITHUB_TOKEN` env var to a personal access token to reach private repos
or raise that limit to 5000/hour.

### Other options

```python
compressor = ContextCompressor(
    target_compression=0.70,
    dedup_threshold=None,                 # None = adaptive per-document threshold instead of a fixed 0.85 cutoff
    extra_filler_patterns=[r"^\s*MY_NOISE_TAG.*$"],  # extend the built-in filler-pattern list
    model="claude",                       # tokenizer profile: "default" | "gpt-4" | "gpt-4o" | "gpt-3.5" | "claude" | "gemini"
    summarize_log_blocks=True,            # collapse repeated multi-line log records (e.g. a stack trace firing 40x) into one + count
)
```

### Session / conversation-export compression

Compress a ChatGPT or claude.ai conversation export (or a generic
`[{"role": ..., "content": ...}, ...]` transcript) instead of a single
blob of text — useful for trimming a long chat/agent history before
re-feeding it as context. The system prompt and the most recent N
turns are always kept verbatim; older turns are deduped (repeated
questions/answers dropped) and compressed:

```python
from context_compressor.session_compressor import compress_session

report = compress_session(
    raw_export=open("conversation.json").read(),  # ChatGPT export, claude.ai export, or generic messages list
    protect_recent=4,        # always keep the last 4 turns verbatim, in addition to any system prompt
    target_compression=0.70,
)
print(report.summary())
messages = report.to_messages()  # reconstructed [{"role", "content"}, ...] transcript
```

## Run the FastAPI + React app

**Backend** (Python, serves the compression engine over HTTP):
```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend** (React + Vite):
```bash
cd frontend
npm install
npm run dev
```
Open the URL Vite prints (usually `http://localhost:5173`). It talks to the
backend at `http://localhost:8000` by default — copy `.env.example` to
`.env` in `frontend/` to point it elsewhere.

The UI: paste text or drop a file, pick a content type (or leave it on
`auto`), pick a preset or set a custom target reduction with the slider,
and run compression. You'll see token counts before/after, a compression
bar, and a line-by-line diff — kept lines in green, removed lines struck
through in rust.

### API endpoints

- `GET /health` — liveness check
- `GET /presets` — list available presets and their settings
- `POST /compress` — `{text, content_type, preset?, target_compression?, model?}`
- `POST /compress/file` — same, as a multipart file upload
- `POST /compress/diff` — `{diff_text, file_contents, target_compression?, model?}` — diff-aware compression (see below)
- `POST /compress/diff/github` — `{pr, target_compression?, model?}` — same, but fetches the diff + file contents itself from a GitHub PR URL (public repos out of the box; set `GITHUB_TOKEN` server-side for private repos / a higher rate limit)
- `POST /compress/session` — `{export, protect_recent?, target_compression?, model?, dedup_threshold?}` — compress a ChatGPT/claude.ai/generic conversation export (see "Session / conversation-export compression" above)
- `POST /tokenize` — `{text, model?}` — cheap token-count-only endpoint (no compression run), used for live token counters

## Run the CLI (no server needed)

```bash
# single file
python cli.py my_logs.txt --target 0.6 --content-type logs
python cli.py app.py --preset aggressive --out compressed.py
python cli.py app.py --report report.html   # export a shareable diff report (.md or .html)

# whole repo/directory, with cross-file dependency awareness
python cli.py --repo ./my_project --target 0.7 --out ./my_project_compressed

# diff-aware: compress only what changed vs a git ref, plus needed context
python cli.py --repo ./my_project --diff HEAD~1 --target 0.5

# diff-aware from a standalone diff file (e.g. a downloaded GitHub PR .diff),
# with --repo pointing at a checkout containing the new file contents
python cli.py --repo ./my_project --diff-file pr123.diff --target 0.5

# diff-aware straight from a GitHub PR -- fetches the diff + file contents itself,
# no local checkout needed (public repos work out of the box; set GITHUB_TOKEN
# for private repos or a higher rate limit)
python cli.py --github-pr https://github.com/owner/repo/pull/123 --target 0.5

# session-compression: trim a ChatGPT/claude.ai/generic conversation export,
# keeping the system prompt + the last 4 turns verbatim
python cli.py --session conversation.json --protect-recent 4 --target 0.6 --out compressed.json
```

Run `python cli.py --help` for the full option list (presets, dedup
threshold, tokenizer model, quiet mode, etc).

## Run the benchmark

```bash
pip install -r requirements.txt
python benchmark.py                          # runs on sample_data/
python benchmark.py my_file.txt --target 0.6  # run on your own file
```

## Run the downstream-accuracy eval harness

`benchmark.py` measures compression ratio offline. This measures the
metric that actually requires a live model: whether answers to the
same questions still agree after compression.

```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python eval_harness.py my_doc.txt --questions questions.json --target 0.7
```

`questions.json` is a JSON list of question strings. The harness asks
each question against the original text and the compressed text via
the Anthropic API, then uses a judge call to score whether the
compressed-context answer agrees with the original-context answer, and
reports an aggregate retention percentage. It requires a real API key
and will not fabricate results without one.

## Run tests

```bash
python test_compressor.py
```

## Metrics this demonstrates

- **Compression ratio** — measured directly (original vs. compressed token count)
- **Cost / latency reduction** — proportional to compression ratio for API-billed models
- **Reasoning-token retention** — approximated by the guardrail that boosts
  scores for high-density, non-filler chunks, the dependency-closure pass
  that keeps referenced code definitions, and never drops critical-looking
  lines (see `test_important_line_survives_compression`)
- **Downstream answer-accuracy retention** — measured directly via
  `eval_harness.py` against the Anthropic API (requires an API key)

## Project structure

```
context_compressor/
├── context_compressor/         # the compression engine (importable package)
│   ├── __init__.py
│   ├── compressor.py            # main ContextCompressor class
│   ├── boilerplate.py           # structural dedup (blank lines, repeated lines/blocks)
│   ├── dedup.py                  # TF-IDF semantic near-duplicate removal (fixed or adaptive threshold)
│   ├── scoring.py                # information-density scoring, configurable filler patterns
│   ├── tokenizer.py              # token counting (tiktoken w/ fallback, model-aware profiles)
│   ├── code_chunker.py           # AST/indentation block chunking + symbol table + dependency closure
│   ├── presets.py                # conservative / balanced / aggressive presets
│   ├── multifile.py              # repo-wide compression with cross-file dependency closure
│   ├── git_diff.py                # diff-aware compression: compress only what a diff touches + needed context
│   ├── github_fetch.py            # fetch a GitHub PR's diff + changed files via the public REST API (no OAuth)
│   ├── session_compressor.py     # ChatGPT/claude.ai/generic conversation export compression
│   └── diff_export.py            # export a compression diff as Markdown/HTML
├── backend/                     # FastAPI server wrapping the engine
│   ├── main.py
│   ├── requirements.txt
│   └── context_compressor/       # copy of the engine package (self-contained)
├── frontend/                    # React + Vite UI
│   ├── src/App.jsx
│   ├── src/App.css
│   └── ...
├── extension/                    # Chrome/Edge (Manifest V3) browser extension
├── extension-vscode/             # VS Code extension (live token counter, compress selection/file)
├── sample_data/
│   ├── sample_code.py
│   └── sample_logs.txt
├── cli.py                       # command-line interface (single file, --repo, --diff, or --session)
├── eval_harness.py              # downstream answer-accuracy eval against the Anthropic API
├── benchmark.py
├── test_compressor.py
└── requirements.txt
```
