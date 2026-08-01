import { useCallback, useMemo, useRef, useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const MODES = [
  { value: 'text', label: 'text / repo' },
  { value: 'diff', label: 'diff' },
]

const CONTENT_TYPES = [
  { value: 'auto', label: 'auto' },
  { value: 'code', label: 'code' },
  { value: 'logs', label: 'logs' },
  { value: 'prose', label: 'prose' },
]

const PRESETS = [
  { value: 'custom', label: 'custom' },
  { value: 'conservative', label: 'conservative' },
  { value: 'balanced', label: 'balanced' },
  { value: 'aggressive', label: 'aggressive' },
]

// Matches the "+++ b/path/to/file.py" target-side header of a unified
// diff, same format `git diff` / a GitHub PR's .diff URL produce.
const DIFF_FILE_HEADER_RE = /^\+\+\+ b\/(.+)$/gm

function extractDiffPaths(diffText) {
  const paths = []
  let match
  DIFF_FILE_HEADER_RE.lastIndex = 0
  while ((match = DIFF_FILE_HEADER_RE.exec(diffText)) !== null) {
    const p = match[1].trim()
    if (p !== '/dev/null' && !paths.includes(p)) paths.push(p)
  }
  return paths
}

function StatBlock({ label, value, sublabel }) {
  return (
    <div className="stat-block">
      <div className="stat-value">{value}</div>
      <div className="stat-label">{label}</div>
      {sublabel && <div className="stat-sublabel">{sublabel}</div>}
    </div>
  )
}

function CompressionBar({ originalTokens, compressedTokens }) {
  const maxWidth = 100
  const compressedWidth = originalTokens > 0
    ? Math.max(2, (compressedTokens / originalTokens) * maxWidth)
    : 0

  return (
    <div className="bar-stack" aria-hidden="true">
      <div className="bar-row">
        <span className="bar-tag">before</span>
        <div className="bar-track">
          <div className="bar-fill bar-fill--before" style={{ width: `${maxWidth}%` }} />
        </div>
        <span className="bar-count">{originalTokens}</span>
      </div>
      <div className="bar-squeeze">⌄</div>
      <div className="bar-row">
        <span className="bar-tag">after</span>
        <div className="bar-track">
          <div className="bar-fill bar-fill--after" style={{ width: `${compressedWidth}%` }} />
        </div>
        <span className="bar-count">{compressedTokens}</span>
      </div>
    </div>
  )
}

function DiffView({ lines }) {
  if (!lines || lines.length === 0) return null
  return (
    <div className="diff-view">
      {lines.map((line, i) => (
        <div key={i} className={`diff-line ${line.kept ? 'diff-line--kept' : 'diff-line--removed'}`}>
          <span className="diff-gutter">{line.kept ? '+' : '−'}</span>
          <span className="diff-text">{line.text || '\u00A0'}</span>
        </div>
      ))}
    </div>
  )
}

function EmptyState({ mode }) {
  if (mode === 'diff') {
    return (
      <div className="empty-state">
        <pre className="empty-ascii">{`  ┌───┐ ┌───┐        ┌───┐
  │ + │ │ + │  ───▶  │▓▓▓│
  └───┘ └───┘        └───┘`}</pre>
        <p>Paste a unified diff and the new content of each changed file, then run compression to see what survives.</p>
      </div>
    )
  }
  return (
    <div className="empty-state">
      <pre className="empty-ascii">{`  ┌─────────────┐        ┌──────┐
  │ ░░░░░░░░░░░ │  ───▶  │ ▓▓▓▓ │
  └─────────────┘        └──────┘`}</pre>
      <p>Paste text or drop a file, then run compression to see the before / after.</p>
    </div>
  )
}

// ---------- diff-mode: per-changed-file content input ----------

function DiffFileInput({ path, content, onChange }) {
  const inputRef = useRef(null)

  const handleFile = useCallback((file) => {
    if (!file) return
    const reader = new FileReader()
    reader.onload = (e) => onChange(e.target.result)
    reader.readAsText(file)
  }, [onChange])

  const onDrop = useCallback((e) => {
    e.preventDefault()
    e.currentTarget.classList.remove('diff-file-drop--active')
    handleFile(e.dataTransfer.files?.[0])
  }, [handleFile])

  return (
    <div className="diff-file-card">
      <div className="diff-file-card-header">
        <span className="diff-file-path">{path}</span>
        <span className={`diff-file-status ${content ? 'diff-file-status--loaded' : ''}`}>
          {content ? 'loaded' : 'needs content'}
        </span>
      </div>
      <div
        className="diff-file-drop"
        onDragOver={(e) => { e.preventDefault(); e.currentTarget.classList.add('diff-file-drop--active') }}
        onDragLeave={(e) => e.currentTarget.classList.remove('diff-file-drop--active')}
        onDrop={onDrop}
      >
        <textarea
          className="diff-file-textarea"
          placeholder={`paste the full NEW contents of ${path} here, or drop the file`}
          value={content}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
        />
        <label className="file-btn diff-file-browse">
          browse
          <input type="file" onChange={(e) => handleFile(e.target.files?.[0])} ref={inputRef} hidden />
        </label>
      </div>
    </div>
  )
}

// ---------- diff-mode: result for one changed file ----------

function DiffFileResult({ file }) {
  return (
    <details className="diff-file-result" open>
      <summary className="diff-file-result-summary">
        <span className="diff-file-result-path">{file.path}</span>
        <span className="diff-file-result-tokens">{file.original_tokens} → {file.compressed_tokens} tok</span>
      </summary>
      <div className="diff-file-result-stats">
        <span><strong>{file.changed_blocks_kept}</strong> changed</span>
        <span><strong>{file.dependency_blocks_restored}</strong> dependency-restored</span>
        <span><strong>{file.context_blocks_kept}</strong> context</span>
        <span className="diff-file-result-stats-muted">of {file.blocks_total} blocks</span>
      </div>
      <DiffView lines={file.diff_lines} />
    </details>
  )
}

export default function App() {
  const [mode, setMode] = useState('text')

  // -- text/repo mode state --
  const [text, setText] = useState('')
  const [contentType, setContentType] = useState('auto')
  const [fileName, setFileName] = useState(null)
  const dropRef = useRef(null)

  // -- diff mode state --
  const [diffText, setDiffText] = useState('')
  const [fileContents, setFileContents] = useState({})
  const diffPaths = useMemo(() => extractDiffPaths(diffText), [diffText])

  // -- shared state --
  const [preset, setPreset] = useState('custom')
  const [targetCompression, setTargetCompression] = useState(70)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [diffResult, setDiffResult] = useState(null)
  const [copyState, setCopyState] = useState('idle')

  const runTextCompression = useCallback(async () => {
    if (!text.trim()) {
      setError('Paste some text or drop a file first.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/compress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text,
          content_type: contentType,
          preset: preset === 'custom' ? null : preset,
          target_compression: preset === 'custom' ? targetCompression / 100 : undefined,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `Request failed (${res.status})`)
      }
      setResult(await res.json())
      setDiffResult(null)
    } catch (err) {
      setError(err.message === 'Failed to fetch'
        ? `Can't reach the API at ${API_BASE}. Is the backend running?`
        : err.message)
    } finally {
      setLoading(false)
    }
  }, [text, targetCompression, contentType, preset])

  const runDiffCompression = useCallback(async () => {
    if (!diffText.trim()) {
      setError('Paste a unified diff first (e.g. `git diff`, or a GitHub PR\'s .diff URL).')
      return
    }
    if (diffPaths.length === 0) {
      setError("Couldn't find any \"+++ b/...\" file headers in that diff — is it a unified diff?")
      return
    }
    const missing = diffPaths.filter((p) => !fileContents[p]?.trim())
    if (missing.length > 0) {
      setError(`Paste (or drop) the new content for: ${missing.join(', ')}`)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/compress/diff`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          diff_text: diffText,
          file_contents: fileContents,
          target_compression: targetCompression / 100,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `Request failed (${res.status})`)
      }
      setDiffResult(await res.json())
      setResult(null)
    } catch (err) {
      setError(err.message === 'Failed to fetch'
        ? `Can't reach the API at ${API_BASE}. Is the backend running?`
        : err.message)
    } finally {
      setLoading(false)
    }
  }, [diffText, diffPaths, fileContents, targetCompression])

  const handleFile = useCallback((file) => {
    if (!file) return
    setFileName(file.name)
    const reader = new FileReader()
    reader.onload = (e) => setText(e.target.result)
    reader.readAsText(file)
  }, [])

  const onDrop = useCallback((e) => {
    e.preventDefault()
    dropRef.current?.classList.remove('drop-zone--active')
    const file = e.dataTransfer.files?.[0]
    handleFile(file)
  }, [handleFile])

  const handleDiffFile = useCallback((file) => {
    if (!file) return
    const reader = new FileReader()
    reader.onload = (e) => setDiffText(e.target.result)
    reader.readAsText(file)
  }, [])

  const setFileContent = useCallback((path, content) => {
    setFileContents((prev) => ({ ...prev, [path]: content }))
  }, [])

  const activeResult = mode === 'diff' ? diffResult : result

  const copyCompressed = useCallback(() => {
    if (mode === 'text') {
      if (!result) return
      navigator.clipboard.writeText(result.compressed_text).then(() => {
        setCopyState('copied')
        setTimeout(() => setCopyState('idle'), 1500)
      })
    } else {
      if (!diffResult) return
      const combined = diffResult.files
        .map((f) => `----- ${f.path} -----\n${f.compressed_text}`)
        .join('\n\n')
      navigator.clipboard.writeText(combined).then(() => {
        setCopyState('copied')
        setTimeout(() => setCopyState('idle'), 1500)
      })
    }
  }, [mode, result, diffResult])

  const switchMode = useCallback((next) => {
    setMode(next)
    setError(null)
  }, [])

  return (
    <div className="app">
      <header className="header">
        <div className="brand">
          <span className="brand-mark">ctx// compress</span>
          <span className="brand-cursor" aria-hidden="true" />
        </div>
        <p className="tagline">strip the filler. keep the signal.</p>
      </header>

      <main className="layout">
        <section className="panel panel--input">
          <div className="panel-header">
            <span className="panel-title">01 / input</span>
            <div className="segmented" role="tablist" aria-label="Input mode">
              {MODES.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  role="tab"
                  aria-selected={mode === m.value}
                  className={`segmented-btn ${mode === m.value ? 'segmented-btn--active' : ''}`}
                  onClick={() => switchMode(m.value)}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          {mode === 'text' && (
            <>
              <div className="panel-header">
                <span className="panel-title">content type</span>
                <div className="segmented" role="tablist" aria-label="Content type">
                  {CONTENT_TYPES.map((ct) => (
                    <button
                      key={ct.value}
                      type="button"
                      role="tab"
                      aria-selected={contentType === ct.value}
                      className={`segmented-btn ${contentType === ct.value ? 'segmented-btn--active' : ''}`}
                      onClick={() => setContentType(ct.value)}
                    >
                      {ct.label}
                    </button>
                  ))}
                </div>
              </div>

              <div className="panel-header">
                <span className="panel-title">preset</span>
                <div className="segmented" role="tablist" aria-label="Compression preset">
                  {PRESETS.map((p) => (
                    <button
                      key={p.value}
                      type="button"
                      role="tab"
                      aria-selected={preset === p.value}
                      className={`segmented-btn ${preset === p.value ? 'segmented-btn--active' : ''}`}
                      onClick={() => setPreset(p.value)}
                    >
                      {p.label}
                    </button>
                  ))}
                </div>
              </div>

              <div
                ref={dropRef}
                className="drop-zone"
                onDragOver={(e) => { e.preventDefault(); dropRef.current?.classList.add('drop-zone--active') }}
                onDragLeave={() => dropRef.current?.classList.remove('drop-zone--active')}
                onDrop={onDrop}
              >
                <textarea
                  className="text-input"
                  placeholder="Paste logs, code, or long-form text here..."
                  value={text}
                  onChange={(e) => { setText(e.target.value); setFileName(null) }}
                  spellCheck={false}
                />
                <div className="drop-hint">
                  {fileName ? `loaded: ${fileName}` : 'or drop a .txt / .log / .py file anywhere in this box'}
                  <label className="file-btn">
                    browse
                    <input
                      type="file"
                      accept=".txt,.log,.py,.js,.md,.json,.csv"
                      onChange={(e) => handleFile(e.target.files?.[0])}
                      hidden
                    />
                  </label>
                </div>
              </div>
            </>
          )}

          {mode === 'diff' && (
            <>
              <div
                className="drop-zone diff-drop-zone"
                onDrop={(e) => { e.preventDefault(); handleDiffFile(e.dataTransfer.files?.[0]) }}
                onDragOver={(e) => e.preventDefault()}
              >
                <textarea
                  className="text-input"
                  placeholder={'Paste a unified diff here (`git diff`, `git diff HEAD~1`, or a GitHub PR\'s .diff URL contents)...'}
                  value={diffText}
                  onChange={(e) => setDiffText(e.target.value)}
                  spellCheck={false}
                />
                <div className="drop-hint">
                  {diffPaths.length > 0
                    ? `${diffPaths.length} changed file${diffPaths.length === 1 ? '' : 's'} detected`
                    : 'or drop a .diff / .patch file'}
                  <label className="file-btn">
                    browse
                    <input type="file" accept=".diff,.patch,.txt" onChange={(e) => handleDiffFile(e.target.files?.[0])} hidden />
                  </label>
                </div>
              </div>

              {diffPaths.length > 0 && (
                <div className="diff-file-list">
                  <span className="panel-title diff-file-list-title">new content of each changed file</span>
                  {diffPaths.map((path) => (
                    <DiffFileInput
                      key={path}
                      path={path}
                      content={fileContents[path] || ''}
                      onChange={(v) => setFileContent(path, v)}
                    />
                  ))}
                </div>
              )}
            </>
          )}

          <div className="control-row">
            <div className="slider-block">
              <div className="slider-label">
                <span>
                  {mode === 'text' && preset === 'custom' && 'target reduction'}
                  {mode === 'text' && preset !== 'custom' && `target reduction (from "${preset}" preset)`}
                  {mode === 'diff' && 'target reduction'}
                </span>
                <span className="slider-value">
                  {(mode === 'diff' || preset === 'custom') ? `${targetCompression}%` : ''}
                </span>
              </div>
              <input
                type="range"
                min="5"
                max="95"
                step="5"
                value={targetCompression}
                onChange={(e) => setTargetCompression(Number(e.target.value))}
                className="slider"
                disabled={mode === 'text' && preset !== 'custom'}
              />
            </div>
            <button
              type="button"
              className="run-btn"
              onClick={mode === 'diff' ? runDiffCompression : runTextCompression}
              disabled={loading}
            >
              {loading ? 'compressing…' : 'compress →'}
            </button>
          </div>

          {error && <div className="error-banner">{error}</div>}
        </section>

        <section className="panel panel--output">
          <div className="panel-header">
            <span className="panel-title">02 / result</span>
            {activeResult && (
              <button type="button" className="copy-btn" onClick={copyCompressed}>
                {copyState === 'copied' ? 'copied' : 'copy output'}
              </button>
            )}
          </div>

          {!activeResult && <EmptyState mode={mode} />}

          {mode === 'text' && result && (
            <>
              <div className="stats-row">
                <StatBlock label="original" value={result.original_tokens} sublabel="tokens" />
                <StatBlock label="compressed" value={result.compressed_tokens} sublabel="tokens" />
                <StatBlock
                  label="reduction"
                  value={`${(result.compression_ratio * 100).toFixed(1)}%`}
                  sublabel={`${result.chunks_kept}/${result.chunks_total} chunks kept`}
                />
              </div>

              <CompressionBar
                originalTokens={result.original_tokens}
                compressedTokens={result.compressed_tokens}
              />

              <DiffView lines={result.diff_lines} />

              <details className="notes">
                <summary>pipeline notes</summary>
                <ul>
                  {result.notes.map((n, i) => <li key={i}>{n}</li>)}
                </ul>
              </details>
            </>
          )}

          {mode === 'diff' && diffResult && (
            <>
              <div className="stats-row">
                <StatBlock label="files" value={diffResult.files.length} sublabel="changed" />
                <StatBlock label="original" value={diffResult.original_tokens} sublabel="tokens" />
                <StatBlock label="compressed" value={diffResult.compressed_tokens} sublabel="tokens" />
                <StatBlock label="reduction" value={`${(diffResult.compression_ratio * 100).toFixed(1)}%`} />
              </div>

              <CompressionBar
                originalTokens={diffResult.original_tokens}
                compressedTokens={diffResult.compressed_tokens}
              />

              {diffResult.files_skipped.length > 0 && (
                <div className="error-banner">
                  skipped (no content provided): {diffResult.files_skipped.join(', ')}
                </div>
              )}

              <div className="diff-file-result-list">
                {diffResult.files.map((f) => <DiffFileResult key={f.path} file={f} />)}
              </div>

              <details className="notes">
                <summary>pipeline notes</summary>
                <ul>
                  {diffResult.notes.map((n, i) => <li key={i}>{n}</li>)}
                </ul>
              </details>
            </>
          )}
        </section>
      </main>

      <footer className="footer">
        <span>token counts are approximate (tiktoken cl100k, or a word-based fallback).</span>
        <span>answer-accuracy retention requires a downstream LLM eval — not measured here.</span>
      </footer>
    </div>
  )
}
