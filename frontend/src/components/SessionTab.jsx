import { useCallback } from 'react'
import { useApp } from '../context/AppContext.jsx'
import { compressSession } from '../hooks/useApi.js'
import FileDropZone from './FileDropZone.jsx'
import StatCards from './StatCards.jsx'

const ACTION_LABEL = {
  protected_system: 'system prompt',
  protected_recent: 'protected (recent)',
  compressed: 'compressed',
  dropped_duplicate: 'dropped (duplicate)',
}

function clamp(n, min, max) {
  return Math.min(max, Math.max(min, n))
}

export default function SessionTab() {
  const {
    model,
    sessionExport, setSessionExport,
    sessionFileName, setSessionFileName,
    sessionProtectRecent, setSessionProtectRecent,
    sessionTarget, setSessionTarget,
    sessionDedupThreshold, setSessionDedupThreshold,
    sessionResult, setSessionResult,
    sessionLoading, setSessionLoading,
    sessionError, setSessionError,
  } = useApp()

  const handleFile = useCallback((file) => {
    setSessionFileName(file.name)
    setSessionError(null)
    const reader = new FileReader()
    reader.onload = (e) => setSessionExport(e.target.result)
    reader.readAsText(file)
  }, [setSessionExport, setSessionFileName, setSessionError])

  const clearFile = useCallback(() => {
    setSessionFileName('')
    setSessionExport('')
  }, [setSessionFileName, setSessionExport])

  const runCompress = useCallback(async () => {
    setSessionLoading(true); setSessionError(null); setSessionResult(null)
    try {
      const data = await compressSession({
        export: sessionExport,
        protect_recent: sessionProtectRecent,
        target_compression: sessionTarget,
        model,
        dedup_threshold: sessionDedupThreshold,
      })
      setSessionResult(data)
    } catch (err) {
      setSessionError(err.message === 'Failed to fetch' ? "Can't reach the API" : err.message)
    } finally { setSessionLoading(false) }
  }, [sessionExport, sessionProtectRecent, sessionTarget, sessionDedupThreshold, model, setSessionLoading, setSessionError, setSessionResult])

  const copyMessages = useCallback(() => {
    if (!sessionResult) return
    const messages = sessionResult.turns
      .filter((t) => t.action !== 'dropped_duplicate')
      .map((t) => ({ role: t.role, content: t.content }))
    navigator.clipboard.writeText(JSON.stringify(messages, null, 2))
  }, [sessionResult])

  return (
    <div className="tab-panel session-tab">
      <div className="workspace-columns">
        <div className="column glass glass-hover">
          <div className="panel-header">Conversation Export</div>
          <p className="hint">
            Drop a ChatGPT <code>conversations.json</code> export, a claude.ai conversation export, or a
            generic <code>[{'{'}"role", "content"{'}'}, ...]</code> JSON transcript.
          </p>
          <textarea
            className="code-input"
            placeholder="Paste conversation export JSON here…"
            value={sessionExport}
            onChange={(e) => { setSessionExport(e.target.value); setSessionFileName('') }}
            spellCheck={false}
          />
          <div className="or-divider">or</div>
          <FileDropZone onFile={handleFile} accept=".json" label="Drop conversation export (.json) here" />
          {sessionFileName && (
            <div className="file-chip glass">
              <span>{sessionFileName}</span>
              <button onClick={clearFile}>×</button>
            </div>
          )}

          <div className="controls-stack">
            <label className="control-row">
              <span>Protect last N turns (kept verbatim)</span>
              <input
                type="number"
                min={0}
                max={100}
                className="input-glass input-number"
                value={sessionProtectRecent}
                onChange={(e) => setSessionProtectRecent(clamp(Number(e.target.value) || 0, 0, 100))}
              />
            </label>

            <label className="control-row slider-row">
              <span>Target reduction {Math.round(sessionTarget * 100)}%</span>
              <input
                type="range"
                min={5}
                max={95}
                step={5}
                value={Math.round(sessionTarget * 100)}
                onChange={(e) => setSessionTarget(Number(e.target.value) / 100)}
              />
            </label>

            <label className="control-row slider-row">
              <span>Duplicate-turn threshold {Math.round(sessionDedupThreshold * 100)}%</span>
              <input
                type="range"
                min={50}
                max={100}
                step={5}
                value={Math.round(sessionDedupThreshold * 100)}
                onChange={(e) => setSessionDedupThreshold(Number(e.target.value) / 100)}
              />
            </label>

            <button className="btn btn-primary btn-full" onClick={runCompress} disabled={sessionLoading || !sessionExport.trim()}>
              {sessionLoading ? 'Compressing…' : 'Compress session →'}
            </button>
            {sessionError && <div className="alert error">{sessionError}</div>}
          </div>
        </div>

        <div className="column glass glass-hover">
          <div className="panel-header">Output</div>
          {sessionResult ? (
            <div className="results-stack">
              <StatCards stats={[
                { label: 'Original tokens', value: sessionResult.original_tokens?.toLocaleString() ?? '—' },
                { label: 'Compressed tokens', value: sessionResult.compressed_tokens?.toLocaleString() ?? '—' },
                { label: 'Reduction', value: `${Math.round((sessionResult.compression_ratio ?? 0) * 100)}%` },
                { label: 'Turns kept', value: `${sessionResult.turns_kept ?? 0} / ${sessionResult.turns_total ?? 0}` },
              ]} />
              <div className="bar-chart glass"><div className="bar-reduced" style={{ width: `${(sessionResult.compression_ratio ?? 0) * 100}%` }} /></div>

              <div className="result-actions">
                <button className="btn btn-ghost" onClick={copyMessages}>Copy as messages JSON</button>
              </div>

              <div className="file-results">
                {sessionResult.turns?.map((turn, i) => (
                  <details key={i} className="file-result-card glass glass-hover" open={turn.action !== 'compressed'}>
                    <summary>
                      <span className="file-path">
                        <span className={`turn-role-badge role-${turn.role}`}>{turn.role}</span>
                        <span className={`turn-action-badge action-${turn.action}`}>{ACTION_LABEL[turn.action] ?? turn.action}</span>
                      </span>
                      <span className="file-meta">{turn.original_tokens} → {turn.compressed_tokens} tokens</span>
                    </summary>
                    {turn.action === 'dropped_duplicate' ? (
                      <p className="hint">Dropped as a near-duplicate of an earlier {turn.role} turn.</p>
                    ) : (
                      <textarea className="code-input mini readonly" readOnly value={turn.content} />
                    )}
                  </details>
                ))}
              </div>

              {sessionResult.notes && sessionResult.notes.length > 0 && (
                <details className="notes-details glass" open>
                  <summary>Pipeline notes ({sessionResult.notes.length})</summary>
                  <ul>{sessionResult.notes.map((n, i) => <li key={i}>{n}</li>)}</ul>
                </details>
              )}
            </div>
          ) : <div className="empty-state">Results will appear here after compression.</div>}
        </div>
      </div>
    </div>
  )
}
