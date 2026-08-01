import { useCallback, useState } from 'react'

export default function FileDropZone({ onFile, accept = '.txt,.log,.py,.js,.md,.json,.csv,.diff,.patch', label = 'Drop file here or click to browse' }) {
  const [dragOver, setDragOver] = useState(false)
  const handleDrop = useCallback((e) => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) onFile(f) }, [onFile])
  const handleChange = useCallback((e) => { const f = e.target.files[0]; if (f) onFile(f) }, [onFile])
  return (
    <label className={`drop-zone glass ${dragOver ? 'over' : ''}`} onDragOver={(e) => { e.preventDefault(); setDragOver(true) }} onDragLeave={() => setDragOver(false)} onDrop={handleDrop}>
      <input type="file" accept={accept} onChange={handleChange} hidden />
      <span className="drop-icon">◫</span>
      <span className="drop-label">{label}</span>
    </label>
  )
}
