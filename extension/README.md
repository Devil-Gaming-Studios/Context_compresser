# Context Compressor — Browser Extension

Compress a prompt without leaving the page you're typing it in. Works
alongside the web app and CLI — same backend, same `/compress` endpoint.

## Install (unpacked, for development)

1. Make sure the backend is running: `uvicorn main:app --reload --port 8000`
   from `backend/` (see the project's main README).
2. Open `chrome://extensions` (or `edge://extensions` — this is a
   standard Manifest V3 extension, Chromium-based browsers only for now).
3. Enable **Developer mode** (top right).
4. Click **Load unpacked**, and select this `extension/` folder.
5. Pin the extension (puzzle-piece icon → pin) so it's visible in the
   toolbar.

## How to use it

Three ways to compress a prompt, depending on where you are:

- **On a supported chat site** (chatgpt.com, claude.ai, gemini.google.com,
  perplexity.ai) — a small `⇥ compress` button appears pinned above the
  prompt box. Click it to compress whatever's currently typed (or just
  your current text selection, if you have one selected) in place.
- **Anywhere else** — select some text, right-click, choose **"Compress
  with Context Compressor."** Works in any editable field on any site.
- **Keyboard shortcut** — `Ctrl+Shift+K` (`Cmd+Shift+K` on Mac) compresses
  whatever field currently has focus, on any page. Remap it at
  `chrome://extensions/shortcuts` if it collides with something else.
- **Popup** (toolbar icon, or `Ctrl+Shift+L`) — a standalone compress box
  for pasting text that isn't in a page field yet, with a "copy output"
  button and an "insert into page" button that writes the result into
  whatever field is currently focused in your active tab.

## Settings

Click the ⚙ in the popup, or right-click the extension icon → Options.

- **API base URL** — defaults to `http://localhost:8000`. Pointing it at
  anything other than `localhost`/`127.0.0.1` will prompt the browser to
  ask you to grant this extension permission for that origin (it can't
  silently reach arbitrary domains).
- **Default model / preset / target reduction / content type** — same
  options as the web app, used by every entry point above.
- **Enabled sites** — turn the floating button off per-site without
  disabling the whole extension.

## Architecture notes

- `background.js` (service worker) is the only place that calls the
  compress API — content scripts and the popup route through it via
  `chrome.runtime.sendMessage`. One fetch path, one CORS/permission
  surface, easier to reason about.
- `content.js` only runs on the sites listed in `manifest.json`'s
  `content_scripts.matches`. It owns the floating button and knows a
  few site-specific selectors for finding the "main" prompt field, with
  a generic largest-visible-editable-element fallback if those drift
  (these sites change their DOM often).
- For sites with no content script, the context menu and keyboard
  shortcut fall back to a generic flow in `background.js` that grabs
  `document.activeElement` via `chrome.scripting.executeScript`,
  compresses it, and writes it back the same way.
- Text is written back using `document.execCommand('insertText', …)`
  where possible — this fires real native `input` events, so
  React-controlled fields (ChatGPT, Claude, Gemini all use these) pick
  up the change correctly instead of silently ignoring a raw `.value =`
  assignment.

## Known limitations

- Selection-based replacement can lose the selection if there's a long
  delay between clicking and the API responding and you click elsewhere
  in the meantime — the field-based flows (floating button, keyboard
  shortcut) are more robust since they re-focus the field explicitly.
- Site selectors for chat sites are best-effort; if a site redesigns its
  input area, the generic "largest visible editable element" fallback
  should still find it, but the floating button's position may need a
  selector update in `content.js`'s `SITE_SELECTORS`.
- Manifest V3 / Chromium only in this build. A Firefox port would need
  `browser.*` namespacing and a `background.scripts` array instead of a
  module service worker, but the rest of the logic carries over as-is.
