import { useCallback, useState } from 'react'

export default function FileDropZone({ onFile, accept = '.txt,.log,.py,.js,.md,.json,.csv,.diff,.patch', label = 'Drop file here or click to browse' }) {
  const [dragOver, setDragOver] = useState(false)

  const handleDrop = useCallback((e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) onFile(file)
  }, [onFile])

  const handleChange = useCallback((e) => {
    const file = e.target.files[0]
    if (file) onFile(file)
  }, [onFile])

  return (
    <label
      className={`drop-zone ${dragOver ? 'over' : ''}`}
      onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={handleDrop}
    >
      <input type="file" accept={accept} onChange={handleChange} hidden />
      <span className="drop-icon">◫</span>
      <span className="drop-label">{label}</span>
    </label>
  )
}
