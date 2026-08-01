export default function SegmentedControl({ options, value, onChange, disabled = false }) {
  return (
    <div className={`segmented ${disabled ? 'disabled' : ''}`}>
      {options.map((opt) => (
        <button
          key={opt.value}
          className={`seg-btn ${value === opt.value ? 'active' : ''}`}
          onClick={() => !disabled && onChange(opt.value)}
          disabled={disabled}
          title={opt.hint || opt.label}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}
