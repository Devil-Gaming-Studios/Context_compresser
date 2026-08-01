import { useState, useCallback } from 'react'
import { useCompress } from '../hooks/useApi.js'

export default function Compress() {
  const [input, setInput] = useState('')
  const [options, setOptions] = useState({
    aggressive: false,
    preserveStructure: true,
    maxTokens: 4096,
  })
  const { compress, result, loading, error } = useCompress()

  const handleCompress = useCallback(() => {
    if (!input.trim()) return
    compress({ text: input, ...options })
  }, [input, options, compress])

  const ratio = result
    ? ((1 - result.output.length / result.input.length) * 100).toFixed(1)
    : null

  return (
    <div className="page compress-page">
      <header className="page-header">
        <h1>Compress</h1>
        <p className="subtitle">Reduce context size while preserving meaning</p>
      </header>

      <div className="compress-layout">
        <div className="panel input-panel">
          <div className="panel-header">
            <span className="panel-tag">INPUT</span>
            <span className="panel-meta">{input.length} chars</span>
          </div>
          <textarea
            className="code-input"
            placeholder="Paste your context here..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            spellCheck={false}
          />
        </div>

        <div className="panel controls-panel">
          <div className="control-group">
            <label className="toggle">
              <input
                type="checkbox"
                checked={options.aggressive}
                onChange={(e) =>
                  setOptions((o) => ({ ...o, aggressive: e.target.checked }))
                }
              />
              <span>Aggressive mode</span>
            </label>

            <label className="toggle">
              <input
                type="checkbox"
                checked={options.preserveStructure}
                onChange={(e) =>
                  setOptions((o) => ({ ...o, preserveStructure: e.target.checked }))
                }
              />
              <span>Preserve structure</span>
            </label>

            <label className="field">
              <span>Max tokens</span>
              <input
                type="number"
                value={options.maxTokens}
                onChange={(e) =>
                  setOptions((o) => ({ ...o, maxTokens: Number(e.target.value) }))
                }
              />
            </label>
          </div>

          <button
            className="btn-primary"
            onClick={handleCompress}
            disabled={loading || !input.trim()}
          >
            {loading ? 'Compressing…' : 'Run Compression'}
          </button>

          {error && <div className="alert error">{error}</div>}
        </div>

        <div className="panel output-panel">
          <div className="panel-header">
            <span className="panel-tag">OUTPUT</span>
            <span className="panel-meta">
              {result ? `${result.output.length} chars` : '—'}
            </span>
          </div>
          <textarea
            className="code-input"
            readOnly
            value={result?.output ?? ''}
            placeholder="Result will appear here..."
          />
          {result && (
            <div className="result-bar">
              <span className="badge success">−{ratio}%</span>
              <span className="badge">{result.tokens} tokens</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
