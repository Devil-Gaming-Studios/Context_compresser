import { useCallback, useRef, useState } from 'react'
import './App.css'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

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

function EmptyState() {
  return (
    <div className="empty-state">
      <pre className="empty-ascii">{`  ┌─────────────┐        ┌──────┐
  │ ░░░░░░░░░░░ │  ───▶  │ ▓▓▓▓ │
  └─────────────┘        └──────┘`}</pre>
      <p>Paste text or drop a file, then run compression to see the before / after.</p>
    </div>
  )
}

export default function App() {
  const [text, setText] = useState('')
  const [contentType, setContentType] = useState('auto')
  const [preset, setPreset] = useState('custom')
  const [targetCompression, setTargetCompression] = useState(70)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [fileName, setFileName] = useState(null)
  const [copyState, setCopyState] = useState('idle')
  const dropRef = useRef(null)

  const runCompression = useCallback(async () => {
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
          // When a preset is selected, let the backend use the preset's
          // own target_compression unless the slider was moved after
          // picking it -- always sending the slider value keeps things
          // simple and predictable for the "custom" case.
          target_compression: preset === 'custom' ? targetCompression / 100 : undefined,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || `Request failed (${res.status})`)
      }
      const data = await res.json()
      setResult(data)
    } catch (err) {
      setError(err.message === 'Failed to fetch'
        ? `Can't reach the API at ${API_BASE}. Is the backend running?`
        : err.message)
    } finally {
      setLoading(false)
    }
  }, [text, targetCompression, contentType, preset])

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

  const copyCompressed = useCallback(() => {
    if (!result) return
    navigator.clipboard.writeText(result.compressed_text).then(() => {
      setCopyState('copied')
      setTimeout(() => setCopyState('idle'), 1500)
    })
  }, [result])

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

          <div className="control-row">
            <div className="slider-block">
              <div className="slider-label">
                <span>{preset === 'custom' ? 'target reduction' : `target reduction (from "${preset}" preset)`}</span>
                <span className="slider-value">{preset === 'custom' ? `${targetCompression}%` : ''}</span>
              </div>
              <input
                type="range"
                min="5"
                max="95"
                step="5"
                value={targetCompression}
                onChange={(e) => setTargetCompression(Number(e.target.value))}
                className="slider"
                disabled={preset !== 'custom'}
              />
            </div>
            <button
              type="button"
              className="run-btn"
              onClick={runCompression}
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
            {result && (
              <button type="button" className="copy-btn" onClick={copyCompressed}>
                {copyState === 'copied' ? 'copied' : 'copy output'}
              </button>
            )}
          </div>

          {!result && <EmptyState />}

          {result && (
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
        </section>
      </main>

      <footer className="footer">
        <span>token counts are approximate (tiktoken cl100k, or a word-based fallback).</span>
        <span>answer-accuracy retention requires a downstream LLM eval — not measured here.</span>
      </footer>
    </div>
  )
}
