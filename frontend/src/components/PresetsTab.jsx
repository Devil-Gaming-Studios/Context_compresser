import { useEffect } from 'react'
import { usePresets } from '../hooks/useApi.js'

const MODELS = [
  { name: 'default', tokenizer: 'auto-detect', note: 'Best guess based on content' },
  { name: 'gpt-4', tokenizer: 'cl100k_base', note: 'OpenAI GPT-4 family' },
  { name: 'gpt-4o', tokenizer: 'o200k_base', note: 'OpenAI GPT-4o' },
  { name: 'gpt-3.5', tokenizer: 'cl100k_base', note: 'OpenAI GPT-3.5' },
  { name: 'claude', tokenizer: '~3.8 chars/token', note: 'Anthropic Claude approx.' },
  { name: 'gemini', tokenizer: '~3.8 chars/token', note: 'Google Gemini approx.' },
]

export default function PresetsTab() {
  const { presets, fetchPresets } = usePresets()

  useEffect(() => {
    fetchPresets().catch(() => {})
  }, [fetchPresets])

  return (
    <div className="tab-panel presets-tab">
      <section className="preset-section">
        <h2>Compression presets</h2>
        <p className="section-desc">Fetched live from <code>GET /presets</code></p>

        {presets ? (
          <div className="table-wrap">
            <table className="data-table preset-table">
              <thead>
                <tr>
                  <th>Preset</th>
                  <th>Target reduction</th>
                  <th>Dedup threshold</th>
                  <th>Accuracy floor</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(presets).map(([key, p]) => (
                  <tr key={key}>
                    <td className="mono cap">{key}</td>
                    <td>{Math.round((p.target_compression ?? 0) * 100)}%</td>
                    <td>{p.dedup_threshold ?? '—'}</td>
                    <td>{p.accuracy_floor ?? '—'}%</td>
                    <td>{p.description ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="skeleton-list" />
        )}
      </section>

      <section className="preset-section">
        <h2>Model tokenizer reference</h2>
        <p className="section-desc">Selecting a model changes which tokenizer profile is used to count tokens.</p>
        <div className="table-wrap">
          <table className="data-table model-table">
            <thead>
              <tr>
                <th>Model</th>
                <th>Tokenizer</th>
                <th>Note</th>
              </tr>
            </thead>
            <tbody>
              {MODELS.map((m) => (
                <tr key={m.name}>
                  <td className="mono">{m.name}</td>
                  <td className="mono">{m.tokenizer}</td>
                  <td>{m.note}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
