import { useApp } from '../context/AppContext.jsx'

const MODELS = [
  { value: 'default', label: 'Auto' },
  { value: 'gpt-4', label: 'GPT-4' },
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'gpt-3.5', label: 'GPT-3.5' },
  { value: 'claude', label: 'Claude' },
  { value: 'gemini', label: 'Gemini' },
]

export default function ModelSelector() {
  const { model, setModel } = useApp()
  return (
    <div className="model-selector">
      <span className="model-label">Model</span>
      <div className="segmented">
        {MODELS.map((m) => (
          <button key={m.value} className={`seg-btn ${model === m.value ? 'active' : ''}`} onClick={() => setModel(m.value)}>
            {m.label}
          </button>
        ))}
      </div>
    </div>
  )
}
