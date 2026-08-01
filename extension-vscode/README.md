# Context Compressor — VS Code Extension

Compress code/log/prose selections without leaving the editor — the
place people actually paste large files into Claude, Cursor, or Copilot
Chat. Same backend, same `/compress` and `/compress/session` endpoints
as the CLI, web app, and browser extension.

## Install (unpacked, for development)

1. Make sure the backend is running:
   `uvicorn main:app --reload --port 8000` from `backend/` (see the
   project's main README).
2. `cd extension-vscode && npm install && npm run compile`
3. Press `F5` in VS Code (with this folder open) to launch an Extension
   Development Host with the extension loaded, or run
   `npx vsce package` to build a `.vsix` and install it via
   **Extensions → … → Install from VSIX**.

## How to use it

- **Status bar (live token counter)** — while `contextCompressor.liveTokenCounter`
  is on (default), the status bar shows a live token count for your
  current selection (or the whole file, if nothing's selected), plus
  how much of a model's context budget that represents, e.g.
  `12,480 tok (selection) · 6% of Claude 200K`. Updates as you select or
  type, debounced so it doesn't hammer the backend on every keystroke.
  Click it to compress-and-copy the same text it's counting.
- **Right-click a selection → "Compress Selection & Copy to Clipboard"** —
  compresses the selection (or, with confirmation, the whole file if
  nothing's selected) and puts the compressed text on your clipboard,
  ready to paste into a chat window.
- **Right-click a selection → "Compress Selection In Place"** — replaces
  the selected text with its compressed version directly in the editor.
  Offers an "Undo" button in case the result isn't what you wanted.
- **Command Palette → "Context Compressor: Compress Active File (Preview)"** —
  compresses the whole active file and opens the result in a read-only
  preview beside it, without touching your actual file.
- **Command Palette → "Context Compressor: Show Last Compression Report"** —
  opens an output channel with the full report from your most recent
  compression: token counts, chunks kept/dropped, near-duplicates
  removed, and a `+`/`-` diff of every chunk.

## Settings

`Ctrl+,` (`Cmd+,`) → search "Context Compressor", or edit `settings.json`:

| Setting | Default | Notes |
|---|---|---|
| `contextCompressor.apiBase` | `http://localhost:8000` | Where the backend is running |
| `contextCompressor.model` | `claude` | Tokenizer profile — `default`, `gpt-4`, `gpt-4o`, `gpt-3.5`, `claude`, `gemini` |
| `contextCompressor.preset` | `balanced` | `conservative` / `balanced` / `aggressive` / `custom` |
| `contextCompressor.targetCompression` | `70` | Only used when `preset` is `custom` (5–98) |
| `contextCompressor.contentType` | `auto` | `auto` / `code` / `logs` / `prose` |
| `contextCompressor.liveTokenCounter` | `true` | Toggle the status bar counter |
| `contextCompressor.budgetPreset` | `claude-200k` | Context-window budget shown next to the live count — `claude-200k`, `gpt4o-128k`, `gpt4-8k`, `gemini-1m`, or `none` |

## Architecture notes

- `src/api.ts` is a straight TypeScript port of `extension/lib/api.js`
  (the Chrome extension's client) — same request/response shapes as
  `backend/main.py`. Keep the three in sync if the backend's contract
  changes.
- The live counter calls the cheap `/tokenize` endpoint (no compression
  pipeline run), same as the web app's live counter — see
  `backend/main.py`'s `/tokenize` handler.
- Each token-count request carries a generation counter so a slow
  response for an old selection can't clobber the status bar after a
  newer selection's response has already landed.
- Compression itself always goes through `/compress`; there's
  intentionally no local/offline compression path in the extension, to
  keep exactly one implementation of the pipeline to reason about.

## Known limitations

- Like the CLI and web app, this only works with a backend reachable
  from your machine — there's no bundled/offline compressor.
- The "Compress Active File (Preview)" command opens an unsaved,
  read-only-by-convention preview document; nothing about the extension
  stops you from editing or saving it as a new file, but it never
  touches your original file.
- No conversation-export command yet — `/compress/session` (compressing
  a ChatGPT/Claude JSON export) is currently CLI/API-only; wiring it up
  to "pick a `.json` export from the file picker" in this extension is
  a natural follow-up.
