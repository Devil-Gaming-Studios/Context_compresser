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
`auto`), set a target reduction with the slider, and run compression. You'll
see token counts before/after, a compression bar, and a line-by-line diff —
kept lines in green, removed lines struck through in rust.

## Run the CLI (no server needed)

## Run the benchmark

```bash
pip install -r requirements.txt
python benchmark.py                          # runs on sample_data/
python benchmark.py my_file.txt --target 0.6  # run on your own file
```

## Run tests

```bash
python test_compressor.py
```

## Metrics this demonstrates

- **Compression ratio** — measured directly (original vs. compressed token count)
- **Cost / latency reduction** — proportional to compression ratio for API-billed models
- **Reasoning-token retention** — approximated by the guardrail that boosts
  scores for high-density, non-filler chunks and never drops critical-looking
  lines (see `test_important_line_survives_compression`)

## Honest limitation

**Downstream answer-accuracy retention (the 95%+ target) is not measured
here** — that requires running the same questions against both the original
and compressed context through a real LLM and comparing answers. This repo
gives you the compression engine; wiring it into an eval harness against
the Anthropic API (ask N questions against full context, ask the same N
against compressed context, compare answer quality) is the natural next
step once you have an API key and a question set to test against.

## Project structure

```
context_compressor/
├── context_compressor/    # the compression engine (importable package)
│   ├── __init__.py
│   ├── compressor.py       # main ContextCompressor class
│   ├── boilerplate.py      # structural dedup (blank lines, repeated lines)
│   ├── dedup.py             # TF-IDF semantic near-duplicate removal
│   ├── scoring.py           # information-density scoring
│   └── tokenizer.py         # token counting (tiktoken w/ fallback)
├── backend/                # FastAPI server wrapping the engine
│   ├── main.py
│   ├── requirements.txt
│   └── context_compressor/  # copy of the engine package (self-contained)
├── frontend/                # React + Vite UI
│   ├── src/App.jsx
│   ├── src/App.css
│   └── ...
├── sample_data/
│   ├── sample_code.py
│   └── sample_logs.txt
├── benchmark.py
├── test_compressor.py
└── requirements.txt
```
