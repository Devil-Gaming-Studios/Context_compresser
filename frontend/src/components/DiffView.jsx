export default function DiffView({ lines }) {
  if (!lines || lines.length === 0) return null
  return (
    <div className="diff-view">
      {lines.map((line, i) => (
        <div key={i} className={`diff-line ${line.kept ? 'kept' : 'removed'}`}>
          <span className="diff-marker">{line.kept ? '+' : '−'}</span>
          <span className="diff-text">{line.text}</span>
        </div>
      ))}
    </div>
  )
}
