<div align="center">

# 🗜️ Context Compressor

### Shrink giant LLM contexts without losing what matters.

*Codebases. Logs. Long documents. Chat histories. Diffs. All compressible — algorithmically, offline, in milliseconds.*

[![No embeddings required](https://img.shields.io/badge/embeddings-none%20required-6f42c1)](#how-it-works)
[![Runs offline](https://img.shields.io/badge/runs-100%25%20offline-2ea44f)](#how-it-works)
[![Presets](https://img.shields.io/badge/presets-conservative%20%7C%20balanced%20%7C%20aggressive-0366d6)](#presets)
[![CLI](https://img.shields.io/badge/interface-CLI%20%7C%20API%20%7C%20Web%20UI-orange)](#run-the-cli-no-server-needed)

</div>

---

## ✨ Why this exists

Every extra token you send to an LLM costs money, latency, and — past a point — *attention*. Most large contexts are mostly noise: repeated log lines, boilerplate imports, restated questions in a long chat, unchanged code sitting next to a three-line diff. **Context Compressor** finds the signal and throws the rest away, on purpose, with receipts.

> No embedding model, no GPU, no network call required for the core engine — steps 3 and 4 of the pipeline run on TF-IDF statistics computed directly over *your* document.

---

## 🧭 How it works

```
raw text
   │
   ▼
① Structural boilerplate strip      collapse blank-line runs · collapse near-identical
                                     repeated lines (500 heartbeat logs → 1 line + count)
   │
   ▼
② Chunking                          lines for code/logs · sentences for prose
   │
   ▼
③ Semantic near-duplicate removal   TF-IDF cosine similarity between chunks — catches
                                     reworded repeats that exact-match dedup misses
   │
   ▼
④ Information-density scoring       TF-IDF mass per chunk, penalized for filler
                                     patterns (bare imports, comments, heartbeat logs)
   │
   ▼
⑤ Budget-constrained selection      greedily keep the highest-scoring chunks, restore
                                     original order, stop at the token budget
   │
   ▼
compressed text ✅
```

---

## 🚀 Quick start

```python
from context_compressor import ContextCompressor

compressor = ContextCompressor(target_compression=0.70)  # remove ~70% of tokens
report = compressor.compress(open("my_logs.txt").read())

print(report.summary())
print(report.compressed_text)
```

### 🎚️ Presets

```python
from context_compressor import ContextCompressor

compressor = ContextCompressor.from_preset("aggressive")  # or "conservative" / "balanced"
report = compressor.compress(text)
```

| Preset | Target reduction | Dedup threshold | Accuracy floor |
|---|:---:|:---:|:---:|
| 🐢 `conservative` | 40% | 0.92 | 0.98 |
| ⚖️ `balanced` *(default)* | 70% | 0.85 | 0.95 |
| 🐇 `aggressive` | 85% | 0.75 | 0.90 |

---

## 🧩 Code-aware chunking + dependency closure

Code isn't just chopped by line. Python is parsed into logical blocks (functions/classes) via `ast`; other languages use indentation-based blocks. A **symbol table** is then built and a **dependency closure** pass runs: if a kept block still calls a helper defined elsewhere, that helper is force-kept — even with a low TF-IDF score.

> 🛡️ This closes the classic failure mode of extractive code compression: dropping a one-line helper that's still called from code you kept, leaving output that references something which no longer exists.

```python
compressor = ContextCompressor(use_code_blocks=True)  # default
```

---

## 📦 Multi-file / repository compression

```python
from context_compressor.multifile import compress_repo

report = compress_repo("./my_project", target_compression=0.7)
print(report.summary())
for file_report in report.files:
    print(file_report.path, file_report.original_tokens, "->", file_report.compressed_tokens)
```

Builds a **repo-wide symbol table** across every file, compresses each file against a shared token budget proportional to its size, then runs a **cross-file** dependency closure — if `app.py` calls a helper in `utils.py`, that helper survives even if `utils.py`'s own local budget would've dropped it.

---

## 🔀 Diff-aware compression (compress just a PR/commit)

Compressing a whole file — or repo — is the wrong unit of work when what you actually want is *"give the model enough context to review this change."* `compress_diff` parses a unified diff, force-keeps every logical block the diff touches, restores any symbol those blocks still depend on (including across files), and fills the remaining budget with the highest-value surrounding context.

```python
from context_compressor.git_diff import compress_diff

# Option A — local git repo (shells out to `git diff` / `git show` itself)
report = compress_diff(repo_path="./my_project", base_ref="HEAD~1")

# Option B — bring your own diff (e.g. downloaded from a GitHub PR's .diff URL),
# no git repo or network access needed on this end
report = compress_diff(
    diff_text=raw_diff_text,
    file_contents={"app.py": "...full new source of app.py...", "utils.py": "..."},
)

print(report.summary())
for f in report.files:
    print(f.path, f.original_tokens, "->", f.compressed_tokens,
          f"({f.changed_blocks_kept} changed, {f.dependency_blocks_restored} dependency-restored)")
```

> ℹ️ This is a heuristic diff-touched-block detector, not `git blame`-level — it won't reach outside the diff's own changed files for dependencies. `compress_diff` itself makes no network calls; point it at a local repo or hand it a diff + file contents yourself.

### 🌐 Option C — point it at a GitHub PR and let it fetch (`github_fetch`)

Skip downloading the `.diff` and every changed file by hand — `github_fetch` does it for you and feeds the result straight into `compress_diff`:

```python
from context_compressor.github_fetch import fetch_pr_diff_and_files, parse_pr_reference
from context_compressor.git_diff import compress_diff

owner, repo, pr_number = parse_pr_reference("https://github.com/owner/repo/pull/123")
diff_text, file_contents = fetch_pr_diff_and_files(owner, repo, pr_number)
report = compress_diff(diff_text=diff_text, file_contents=file_contents)
```

A plain, unauthenticated call to GitHub's public REST API + `raw.githubusercontent.com` (stdlib `urllib`, zero new dependencies) — **not** an OAuth "connect your account" flow, and it won't browse repos or list PRs for you. Works out of the box for public repos (60 requests/hour/IP). Set `GITHUB_TOKEN` for private repos or a 5000/hour limit.

---

## ⚙️ Other options

```python
compressor = ContextCompressor(
    target_compression=0.70,
    dedup_threshold=None,                            # None = adaptive per-document threshold
    extra_filler_patterns=[r"^\s*MY_NOISE_TAG.*$"],   # extend the built-in filler-pattern list
    model="claude",                                   # tokenizer: default | gpt-4 | gpt-4o | gpt-3.5 | claude | gemini
    summarize_log_blocks=True,                        # collapse a 40x-repeated stack trace into one + count
)
```

---

## 💬 Session / conversation-export compression

Compress a ChatGPT or claude.ai export (or a generic `[{"role": ..., "content": ...}, ...]` transcript) instead of a text blob — great for trimming a long chat/agent history before re-feeding it as context. The system prompt and the most recent *N* turns are always kept verbatim; older turns are deduped and compressed.

```python
from context_compressor.session_compressor import compress_session

report = compress_session(
    raw_export=open("conversation.json").read(),  # ChatGPT, claude.ai, or generic messages list
    protect_recent=4,        # always keep the last 4 turns verbatim, plus any system prompt
    target_compression=0.70,
)
print(report.summary())
messages = report.to_messages()  # reconstructed [{"role", "content"}, ...] transcript
```

---

## 🖥️ Run the FastAPI + React app

**Backend** — serves the compression engine over HTTP:

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend** — React + Vite:

```bash
cd frontend
npm install
npm run dev
```

Open the URL Vite prints (usually `http://localhost:5173`). It talks to the backend at `http://localhost:8000` by default — copy `.env.example` to `.env` in `frontend/` to point it elsewhere.

**The UI:** paste text or drop a file → pick a content type (or `auto`) → pick a preset or set a custom reduction target with the slider → run. See token counts before/after, a compression bar, and a line-by-line diff — kept lines in green, removed lines struck through in rust.

| Tab | What it's for |
|---|---|
| 📄 **Text / Repo** | Paste or drop a single file/blob and compress it |
| 🔀 **Diff / PR** | Paste a unified diff (or GitHub PR URL) and compress just the changed blocks + dependencies |
| 💬 **Chat History** | Paste/drop a ChatGPT · claude.ai · generic export, set turns-to-protect + dup threshold, and compress the rest — with per-turn breakdown and a "Copy as messages JSON" button |
| 🎛️ **Presets & Models** | Inspect built-in presets and tokenizer profiles |

### 🧷 Browser & editor extensions

One-click downloads in the header for the browser extension (`.zip` — load unpacked into Chrome/Edge) and the VS Code extension (`.vsix` — install via **Extensions → … → Install from VSIX…**). No build-from-source needed. Both talk to the same backend as the web app and CLI — see `extension/README.md` and `extension-vscode/README.md`.

### 🔌 API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `GET` | `/presets` | List available presets and settings |
| `POST` | `/compress` | `{text, content_type, preset?, target_compression?, model?}` |
| `POST` | `/compress/file` | Same, as a multipart file upload |
| `POST` | `/compress/diff` | `{diff_text, file_contents, target_compression?, model?}` — diff-aware compression |
| `POST` | `/compress/diff/github` | `{pr, target_compression?, model?}` — fetches diff + files from a GitHub PR URL itself |
| `POST` | `/compress/session` | `{export, protect_recent?, target_compression?, model?, dedup_threshold?}` — conversation export compression |
| `POST` | `/tokenize` | `{text, model?}` — cheap token-count-only endpoint for live counters |

---

## ⌨️ Run the CLI (no server needed)

```bash
# single file
python cli.py my_logs.txt --target 0.6 --content-type logs
python cli.py app.py --preset aggressive --out compressed.py
python cli.py app.py --report report.html   # shareable diff report (.md or .html)

# whole repo/directory, with cross-file dependency awareness
python cli.py --repo ./my_project --target 0.7 --out ./my_project_compressed

# diff-aware: compress only what changed vs a git ref, plus needed context
python cli.py --repo ./my_project --diff HEAD~1 --target 0.5

# diff-aware from a standalone diff file (e.g. a downloaded GitHub PR .diff),
# --repo points at a checkout containing the new file contents
python cli.py --repo ./my_project --diff-file pr123.diff --target 0.5

# diff-aware straight from a GitHub PR -- fetches diff + file contents itself,
# no local checkout needed (public repos work out of the box; GITHUB_TOKEN for more)
python cli.py --github-pr https://github.com/owner/repo/pull/123 --target 0.5

# session-compression: trim a ChatGPT/claude.ai/generic conversation export,
# keeping the system prompt + the last 4 turns verbatim
python cli.py --session conversation.json --protect-recent 4 --target 0.6 --out compressed.json
```

Run `python cli.py --help` for the full option list (presets, dedup threshold, tokenizer model, quiet mode, etc).

---

## 📊 Run the benchmark

```bash
pip install -r requirements.txt
python benchmark.py                           # runs on sample_data/
python benchmark.py my_file.txt --target 0.6  # run on your own file
```

## 🧪 Run the downstream-accuracy eval harness

`benchmark.py` measures compression ratio offline. This measures the metric that actually needs a live model: **do answers to the same questions still agree after compression?**

```bash
pip install groq rich
$env:GROQ_API_KEY = "gsk_..."
python eval_harness.py sample_data\sample_logs.txt --questions questions.json --target 0.7
```

`questions.json` is a JSON list of question strings. The harness asks each question against the original text and the compressed text via the Anthropic API, then uses a judge call to score agreement, and reports an aggregate retention percentage. It requires a real API key and will not fabricate results without one.

## ✅ Run tests

```bash
python test_compressor.py
```

---

## 📈 Metrics this demonstrates

- **Compression ratio** — measured directly (original vs. compressed token count)
- **Cost / latency reduction** — proportional to compression ratio for API-billed models
- **Reasoning-token retention** — approximated by the guardrail boosting scores for high-density, non-filler chunks; the dependency-closure pass that keeps referenced code definitions; and never dropping critical-looking lines (see `test_important_line_survives_compression`)
- **Downstream answer-accuracy retention** — measured directly via `eval_harness.py` against the Anthropic API (requires an API key)

---

## 🗂️ Project structure

```
context_compressor/
├── context_compressor/          # the compression engine (importable package)
│   ├── __init__.py
│   ├── compressor.py             # main ContextCompressor class
│   ├── boilerplate.py            # structural dedup (blank lines, repeated lines/blocks)
│   ├── dedup.py                  # TF-IDF semantic near-duplicate removal (fixed or adaptive threshold)
│   ├── scoring.py                # information-density scoring, configurable filler patterns
│   ├── tokenizer.py              # token counting (tiktoken w/ fallback, model-aware profiles)
│   ├── code_chunker.py           # AST/indentation block chunking + symbol table + dependency closure
│   ├── presets.py                # conservative / balanced / aggressive presets
│   ├── multifile.py              # repo-wide compression with cross-file dependency closure
│   ├── git_diff.py               # diff-aware compression: only what a diff touches + needed context
│   ├── github_fetch.py           # fetch a GitHub PR's diff + changed files via public REST API (no OAuth)
│   ├── session_compressor.py     # ChatGPT/claude.ai/generic conversation export compression
│   └── diff_export.py            # export a compression diff as Markdown/HTML
├── backend/                      # FastAPI server wrapping the engine
│   ├── main.py
│   ├── requirements.txt
│   └── context_compressor/       # copy of the engine package (self-contained)
├── frontend/                     # React + Vite UI
│   ├── src/App.jsx
│   ├── src/App.css
│   └── ...
├── extension/                    # Chrome/Edge (Manifest V3) browser extension
├── extension-vscode/             # VS Code extension (live token counter, compress selection/file)
├── sample_data/
│   ├── sample_code.py
│   └── sample_logs.txt
├── cli.py                        # command-line interface (single file, --repo, --diff, or --session)
├── eval_harness.py               # downstream answer-accuracy eval against the Anthropic API
├── benchmark.py
├── test_compressor.py
└── requirements.txt
```

<div align="center">

---

*Built for contexts that got out of hand.* 🗜️

</div>
