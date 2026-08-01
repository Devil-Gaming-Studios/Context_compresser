import { useState, useEffect } from 'react'

const DEFAULT_BACKEND = 'http://localhost:3000'

export default function Settings() {
  const [backendUrl, setBackendUrl] = useState(() => {
    return localStorage.getItem('ctx-backend-url') || DEFAULT_BACKEND
  })
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    window.__BACKEND_URL__ = backendUrl
  }, [backendUrl])

  const handleSave = () => {
    localStorage.setItem('ctx-backend-url', backendUrl)
    window.__BACKEND_URL__ = backendUrl
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="page settings-page">
      <header className="page-header">
        <h1>Settings</h1>
        <p className="subtitle">Configure your backend and preferences</p>
      </header>

      <div className="card settings-card">
        <h3>Backend Connection</h3>
        <label className="field">
          <span>API Base URL</span>
          <input
            type="url"
            value={backendUrl}
            onChange={(e) => setBackendUrl(e.target.value)}
            placeholder="http://localhost:3000"
          />
          <small>The base URL for all HTTP requests to your backend</small>
        </label>

        <div className="settings-actions">
          <button className="btn-primary" onClick={handleSave}>
            {saved ? 'Saved ✓' : 'Save Settings'}
          </button>
        </div>
      </div>

      <div className="card settings-card">
        <h3>Endpoints</h3>
        <div className="endpoint-list">
          <div className="endpoint-row">
            <span className="method">GET</span>
            <code>/api/stats</code>
            <span className="desc">Dashboard statistics</span>
          </div>
          <div className="endpoint-row">
            <span className="method">POST</span>
            <code>/api/compress</code>
            <span className="desc">Run compression job</span>
          </div>
          <div className="endpoint-row">
            <span className="method">GET</span>
            <code>/api/history</code>
            <span className="desc">List past jobs</span>
          </div>
        </div>
        <p className="hint">
          These paths are appended to your Base URL. Adjust them in
          <code>src/hooks/useApi.js</code> to match your existing backend.
        </p>
      </div>
    </div>
  )
}
