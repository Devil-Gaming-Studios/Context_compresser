import { useCallback } from 'react'
import { useApp } from '../context/AppContext.jsx'
import { compressText, compressFile } from '../hooks/useApi.js'
import SegmentedControl from './SegmentedControl.jsx'
import FileDropZone from './FileDropZone.jsx'
import StatCards from './StatCards.jsx'
import DiffView from './DiffView.jsx'

const CONTENT_TYPES = [
  { value: 'auto', label: 'Auto' },
  { value: 'code', label: 'Code' },
  { value: 'logs', label: 'Logs' },
  { value: 'prose', label: 'Prose' },
]

const PRESETS = [
  { value: 'custom', label: 'Custom' },
  { value: 'conservative', label: 'Conservative' },
  { value: 'balanced', label: 'Balanced' },
  { value: 'aggressive', label: 'Aggressive' },
]

export default function TextTab() {
  const {
    model,
    textInput, setTextInput,
    textFile, setTextFile,
    textContentType, setTextContentType,
    textPreset, setTextPreset,
    textTarget, setTextTarget,
    textResult, setTextResult,
    textLoading, setTextLoading,
    textError, setTextError,
  } = useApp()

  const handleFile = useCallback((file) => { setTextFile(file); setTextError(null) }, [setTextFile, setTextError])

  const runCompress = useCallback(async () => {
    setTextLoading(true); setTextError(null); setTextResult(null)
    try {
      const payload = {
        model, content_type: textContentType,
        ...(textPreset !== 'custom' ? { preset: textPreset } : { target_compression: textTarget }),
      }
      const data = textFile ? await compressFile(textFile, payload) : await compressText({ ...payload, text: textInput })
      setTextResult(data)
    } catch (err) {
      setTextError(err.message === 'Failed to fetch' ? "Can't reach the API" : err.message)
    } finally { setTextLoading(false) }
  }, [model, textInput, textFile, textContentType, textPreset, textTarget, setTextLoading, setTextError, setTextResult])

  const isCustom = textPreset === 'custom'

  return (
    <div className="tab-panel text-tab">
      <div className="workspace-columns">
        <div className="column glass glass-hover">
          <div className="panel-header">Input</div>
          <textarea className="code-input" placeholder="Paste your context here…" value={textInput} onChange={(e) => setTextInput(e.target.value)} spellCheck={false} />
          <div className="or-divider">or</div>
          <FileDropZone onFile={handleFile} />
          {textFile && <div className="file-chip glass"><span>{textFile.name}</span><button onClick={() => setTextFile(null)}>×</button></div>}
          <div className="controls-stack">
            <label className="control-row"><span>Content type</span><SegmentedControl options={CONTENT_TYPES} value={textContentType} onChange={setTextContentType} /></label>
            <label className="control-row"><span>Preset</span><SegmentedControl options={PRESETS} value={textPreset} onChange={setTextPreset} /></label>
            <label className={`control-row slider-row ${!isCustom ? 'disabled' : ''}`}>
              <span>Target reduction {Math.round(textTarget * 100)}%</span>
              <input type="range" min={5} max={95} step={5} value={Math.round(textTarget * 100)} onChange={(e) => setTextTarget(Number(e.target.value) / 100)} disabled={!isCustom} />
            </label>
            <button className="btn btn-primary btn-full" onClick={runCompress} disabled={textLoading || (!textInput.trim() && !textFile)}>
              {textLoading ? 'Compressing…' : 'Compress →'}
            </button>
            {textError && <div className="alert error">{textError}</div>}
          </div>
        </div>
        <div className="column glass glass-hover">
          <div className="panel-header">Output</div>
          {textResult ? (
            <div className="results-stack">
              <StatCards stats={[
                { label: 'Original tokens', value: textResult.original_tokens?.toLocaleString() ?? '—' },
                { label: 'Compressed tokens', value: textResult.compressed_tokens?.toLocaleString() ?? '—' },
                { label: 'Reduction', value: `${Math.round((textResult.compression_ratio ?? 0) * 100)}%` },
                { label: 'Chunks kept', value: `${textResult.chunks_kept ?? 0} / ${textResult.chunks_total ?? 0}` },
              ]} />
              <div className="bar-chart glass"><div className="bar-reduced" style={{ width: `${(textResult.compression_ratio ?? 0) * 100}%` }} /></div>
              <div className="result-actions">
                <button className="btn btn-ghost" onClick={() => navigator.clipboard.writeText(textResult.compressed_text)}>Copy output</button>
              </div>
              <textarea className="code-input readonly" readOnly value={textResult.compressed_text ?? ''} />
              <DiffView lines={textResult.diff_lines} />
              {textResult.notes && textResult.notes.length > 0 && (
                <details className="notes-details glass"><summary>Pipeline notes ({textResult.notes.length})</summary><ul>{textResult.notes.map((n, i) => <li key={i}>{n}</li>)}</ul></details>
              )}
            </div>
          ) : <div className="empty-state">Results will appear here after compression.</div>}
        </div>
      </div>
    </div>
  )
}
