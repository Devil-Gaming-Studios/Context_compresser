import { useEffect, useState } from 'react'
import { useScrollReveal } from '../hooks/useApi.js'

const RESULTS_URL = '/benchmarks-results.json'

function pct(n) {
  return n == null ? null : Math.round(n * 1000) / 10
}

export default function Benchmarks() {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)
  const s1 = useScrollReveal()
  const s2 = useScrollReveal()
  const s3 = useScrollReveal()

  useEffect(() => {
    fetch(RESULTS_URL)
      .then((res) => {
        if (!res.ok) throw new Error(`${res.status}`)
        return res.json()
      })
      .then(setData)
      .catch((e) => setError(e.message))
  }, [])

  if (error) {
    return (
      <div className="page docs-page benchmarks-page">
        <h1>Benchmarks</h1>
        <section className="doc-section glass">
          <h2>No results yet</h2>
          <p>
            Run <code>python benchmarks/run_leaderboard.py</code> from the repo root, then copy
            <code> benchmarks/results.json</code> to <code>frontend/public/benchmarks-results.json</code> and reload.
          </p>
        </section>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="page docs-page benchmarks-page">
        <h1>Benchmarks</h1>
        <p className="bench-loading">Loading results…</p>
      </div>
    )
  }

  const rows = Object.entries(data.leaderboard)
    .map(([key, v]) => ({ key, ...v }))
    .sort((a, b) => {
      if (!!a.skipped_reason !== !!b.skipped_reason) return a.skipped_reason ? 1 : -1
      return (b.overall_compression_ratio || 0) - (a.overall_compression_ratio || 0)
    })

  const active = rows.filter((r) => !r.skipped_reason)
  const skipped = rows.filter((r) => r.skipped_reason)
  const ours = rows.find((r) => r.key === 'ours')
  const datasetCount = new Set(data.per_dataset.map((d) => d.dataset)).size

  return (
    <div className="page docs-page benchmarks-page">
      <h1>Benchmarks</h1>
      <p className="bench-intro">
        Compression ratio measured against a naive-truncation floor and a simplified Selective-Context
        reimplementation, on the same core engine that powers this app. Answer-quality retention — whether a model
        still answers correctly off the compressed text — is included when available, since a ratio number alone
        doesn't prove anything was preserved.
      </p>

      <div className="stat-cards bench-stat-cards" ref={s1}>
        <div className="stat-card glass">
          <span className="stat-value">{ours ? `${pct(ours.overall_compression_ratio)}%` : '—'}</span>
          <span className="stat-label">Our compression ratio</span>
        </div>
        <div className="stat-card glass">
          <span className="stat-value">{datasetCount}</span>
          <span className="stat-label">Datasets tested</span>
        </div>
        <div className="stat-card glass">
          <span className="stat-value">{Math.round(data.target_compression * 100)}%</span>
          <span className="stat-label">Target compression</span>
        </div>
        <div className="stat-card glass">
          <span className="stat-value">{data.quality_eval_ran ? 'Yes' : 'Not run'}</span>
          <span className="stat-label">Quality retention</span>
        </div>
      </div>

      {!data.quality_eval_ran && (
        <section className="doc-section glass bench-note" ref={s2}>
          <p>
            This run only measured compression ratio. Retention wasn't measured, so it isn't shown as a number below
            — regenerate with <code>run_leaderboard.py --with-quality</code> and an <code>ANTHROPIC_API_KEY</code> to
            fill it in.
          </p>
        </section>
      )}

      <section className="doc-section glass" ref={s3}>
        <h2>Compression ratio by compressor</h2>
        <div className="bench-bars">
          {active.map((r) => (
            <div className="bench-bar-row" key={r.key}>
              <div className="bench-bar-label">
                <span className={r.key === 'ours' ? 'bench-name bench-name-ours' : 'bench-name'}>
                  {r.adapter_name}
                </span>
                <span className="bench-bar-value">{pct(r.overall_compression_ratio)}%</span>
              </div>
              <div className="bar-chart">
                <div
                  className={r.key === 'ours' ? 'bar-reduced' : 'bar-reduced bar-reduced-muted'}
                  style={{ width: `${Math.min(100, pct(r.overall_compression_ratio) || 0)}%` }}
                />
              </div>
              {r.avg_retention != null && (
                <div className="bench-retention">retention {pct(r.avg_retention)}%</div>
              )}
            </div>
          ))}
        </div>

        {skipped.length > 0 && (
          <div className="bench-skipped">
            {skipped.map((r) => (
              <p key={r.key} className="bench-skipped-row">
                <span className="bench-name">{r.adapter_name}</span> — skipped: {r.skipped_reason}
              </p>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}
