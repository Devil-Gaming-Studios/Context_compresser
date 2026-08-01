import { useApp } from '../context/AppContext.jsx'

const MODELS = [
  { value: 'default', label: 'default', hint: 'auto-detect tokenizer' },
  { value: 'gpt-4', label: 'gpt-4', hint: 'cl100k_base' },
  { value: 'gpt-4o', label: 'gpt-4o', hint: 'o200k_base' },
  { value: 'gpt-3.5', label: 'gpt-3.5', hint: 'cl100k_base' },
  { value: 'claude', label: 'claude', hint: '~3.8 chars/token approx.' },
  { value: 'gemini', label: 'gemini', hint: '~3.8 chars/token approx.' },
]

export default function ModelSelector() {
  const { model, setModel } = useApp()

  return (
    <div className="model-selector">
      <span className="model-label">Model</span>
      <div className="segmented model-seg">
        {MODELS.map((m) => (
          <button
            key={m.value}
            className={`seg-btn ${model === m.value ? 'active' : ''}`}
            onClick={() => setModel(m.value)}
            title={m.hint}
          >
            {m.label}
          </button>
        ))}
      </div>
      <span className="model-hint">
        {MODELS.find((m) => m.value === model)?.hint}
      </span>
    </div>
  )
}
