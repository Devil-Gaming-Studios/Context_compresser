import { useCallback, useEffect, useRef, useState } from 'react'
import { useApp } from '../context/AppContext.jsx'
import { compressText, compressFile, tokenize, useDebouncedValue, usePresets } from '../hooks/useApi.js'
import { MODELS } from './ModelSelector.jsx'
import { MODEL_CONTEXT_WINDOWS, MODEL_PRICING_PER_MILLION, COMMON_BUDGETS, formatTokens } from '../utils/modelInfo.js'
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

// Fallback if /presets hasn't loaded yet — matches backend/context_compressor/presets.py
const PRESET_TARGET_FALLBACK = { conservative: 0.40, balanced: 0.70, aggressive: 0.85 }

function clamp(n, min, max) {
  return Math.min(max, Math.max(min, n))
}

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

  const { presets, fetchPresets } = usePresets()
  useEffect(() => { fetchPresets().catch(() => {}) }, [fetchPresets])

  // ── Live token counter (feature: live preview while typing) ──────────
  const [liveTokens, setLiveTokens] = useState(null)
  const [liveTokensLoading, setLiveTokensLoading] = useState(false)
  const debouncedText = useDebouncedValue(textInput, 450)
  const tokenizeRequestId = useRef(0)

  useEffect(() => {
    if (textFile || !debouncedText.trim()) { setLiveTokens(null); setLiveTokensLoading(false); return }
    const requestId = ++tokenizeRequestId.current
    setLiveTokensLoading(true)
    tokenize({ text: debouncedText, model })
      .then((data) => { if (tokenizeRequestId.current === requestId) setLiveTokens(data.tokens) })
      .catch(() => { if (tokenizeRequestId.current === requestId) setLiveTokens(null) })
      .finally(() => { if (tokenizeRequestId.current === requestId) setLiveTokensLoading(false) })
  }, [debouncedText, model, textFile])

  const isCustom = textPreset === 'custom'
  const effectiveTarget = isCustom
    ? textTarget
    : (presets?.[textPreset]?.target_compression ?? PRESET_TARGET_FALLBACK[textPreset] ?? textTarget)

  const estimatedCompressedTokens = liveTokens != null ? Math.max(0, Math.round(liveTokens * (1 - effectiveTarget))) : null

  // ── Budget-fit quick buttons (feature: per-model + common budgets) ───
  const modelLabel = MODELS.find((m) => m.value === model)?.label ?? model
  const modelBudget = MODEL_CONTEXT_WINDOWS[model] ?? MODEL_CONTEXT_WINDOWS.default
  const budgetOptions = [{ label: `Fit ${modelLabel} (${formatTokens(modelBudget)})`, tokens: modelBudget, highlight: true }, ...COMMON_BUDGETS]

  const applyBudget = useCallback((budgetTokens) => {
    if (!liveTokens) return
    const target = clamp(1 - budgetTokens / liveTokens, 0.05, 0.95)
    setTextPreset('custom')
    setTextTarget(target)
  }, [liveTokens, setTextPreset, setTextTarget])

  // ── Cost calculator (feature: $ saved, editable $/1M rate) ───────────
  const [costPerMillion, setCostPerMillion] = useState(MODEL_PRICING_PER_MILLION[model] ?? MODEL_PRICING_PER_MILLION.default)
  const [costTouched, setCostTouched] = useState(false)
  useEffect(() => {
    if (!costTouched) setCostPerMillion(MODEL_PRICING_PER_MILLION[model] ?? MODEL_PRICING_PER_MILLION.default)
  }, [model, costTouched])

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

  const originalCost = textResult ? (textResult.original_tokens / 1_000_000) * costPerMillion : null
  const compressedCost = textResult ? (textResult.compressed_tokens / 1_000_000) * costPerMillion : null
  const savedCost = originalCost != null && compressedCost != null ? originalCost - compressedCost : null

  return (
    <div className="tab-panel text-tab">
      <div className="workspace-columns">
        <div className="column glass glass-hover">
          <div className="panel-header">Input</div>
          <textarea className="code-input" placeholder="Paste your context here…" value={textInput} onChange={(e) => setTextInput(e.target.value)} spellCheck={false} />
          <div className="or-divider">or</div>
          <FileDropZone onFile={handleFile} />
          {textFile && <div className="file-chip glass"><span>{textFile.name}</span><button onClick={() => setTextFile(null)}>×</button></div>}

          {!textFile && (
            <div className="live-preview glass">
              <div className="live-preview-row">
                <span className="live-preview-label">Input</span>
                <span className="live-preview-value">
                  {liveTokensLoading ? 'counting…' : liveTokens != null ? `~${liveTokens.toLocaleString()} tokens` : '—'}
                </span>
              </div>
              <div className="live-preview-arrow">→</div>
              <div className="live-preview-row">
                <span className="live-preview-label">Est. after compression ({Math.round(effectiveTarget * 100)}% reduction)</span>
                <span className="live-preview-value accent">
                  {estimatedCompressedTokens != null ? `~${estimatedCompressedTokens.toLocaleString()} tokens` : '—'}
                </span>
              </div>
            </div>
          )}

          <div className="controls-stack">
            <label className="control-row"><span>Content type</span><SegmentedControl options={CONTENT_TYPES} value={textContentType} onChange={setTextContentType} /></label>
            <label className="control-row"><span>Preset</span><SegmentedControl options={PRESETS} value={textPreset} onChange={setTextPreset} /></label>
            <label className={`control-row slider-row ${!isCustom ? 'disabled' : ''}`}>
              <span>Target reduction {Math.round(textTarget * 100)}%</span>
              <input type="range" min={5} max={95} step={5} value={Math.round(textTarget * 100)} onChange={(e) => { setTextPreset('custom'); setTextTarget(Number(e.target.value) / 100) }} disabled={!isCustom} />
            </label>

            <div className="control-row budget-row">
              <span>Fit into budget</span>
              <div className="budget-buttons">
                {budgetOptions.map((b) => (
                  <button
                    key={b.label}
                    type="button"
                    className={`budget-btn ${b.highlight ? 'highlight' : ''}`}
                    onClick={() => applyBudget(b.tokens)}
                    disabled={!liveTokens}
                    title={liveTokens ? `Set target reduction to fit ~${b.tokens.toLocaleString()} tokens` : 'Type or paste text to enable'}
                  >
                    {b.label}
                  </button>
                ))}
              </div>
            </div>

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

              <div className="cost-calc glass">
                <div className="cost-calc-header">
                  <span>Estimated cost savings</span>
                  <label className="cost-calc-rate">
                    $
                    <input
                      type="number"
                      min={0}
                      step={0.1}
                      value={costPerMillion}
                      onChange={(e) => { setCostTouched(true); setCostPerMillion(Number(e.target.value)) }}
                    />
                    / 1M tokens
                  </label>
                </div>
                <StatCards stats={[
                  { label: 'Original cost', value: `$${originalCost?.toFixed(4) ?? '0.0000'}` },
                  { label: 'Compressed cost', value: `$${compressedCost?.toFixed(4) ?? '0.0000'}` },
                  { label: 'Saved', value: `$${savedCost?.toFixed(4) ?? '0.0000'}` },
                  { label: 'Saved / 1K runs', value: `$${((savedCost ?? 0) * 1000).toFixed(2)}` },
                ]} />
                <p className="cost-calc-note">Estimated using an editable rate — actual pricing varies by model tier and plan.</p>
              </div>

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