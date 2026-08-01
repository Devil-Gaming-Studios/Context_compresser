import { getSettings, setSettings } from './lib/storage.js'
import { checkHealth } from './lib/api.js'

const MODELS = [
  { value: 'default', label: 'auto / generic' },
  { value: 'gpt-4', label: 'GPT-4' },
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'gpt-3.5', label: 'GPT-3.5' },
  { value: 'claude', label: 'Claude' },
  { value: 'gemini', label: 'Gemini' },
]

const PRESETS = [
  { value: 'conservative', label: 'conservative (40%)' },
  { value: 'balanced', label: 'balanced (70%)' },
  { value: 'aggressive', label: 'aggressive (85%)' },
  { value: 'custom', label: 'custom' },
]

const el = (id) => document.getElementById(id)
const modelSelect = el('model-select')
const presetSelect = el('preset-select')
const sliderRow = el('slider-row')
const slider = el('target-slider')
const sliderValue = el('slider-value')
const promptInput = el('prompt-input')
const compressBtn = el('compress-btn')
const insertBtn = el('insert-btn')
const errorBanner = el('error-banner')
const resultBox = el('result')
const resultText = el('result-text')
const copyBtn = el('copy-btn')
const settingsBtn = el('settings-btn')
const healthDot = el('health-dot')
const healthLabel = el('health-label')

let settings = null
let lastResult = null

async function init() {
  settings = await getSettings()

  for (const m of MODELS) modelSelect.append(new Option(m.label, m.value))
  for (const p of PRESETS) presetSelect.append(new Option(p.label, p.value))
  modelSelect.value = settings.model
  presetSelect.value = settings.preset
  slider.value = settings.targetCompression
  sliderValue.textContent = `${settings.targetCompression}%`
  sliderRow.hidden = settings.preset !== 'custom'

  modelSelect.addEventListener('change', () => persist({ model: modelSelect.value }))
  presetSelect.addEventListener('change', () => {
    sliderRow.hidden = presetSelect.value !== 'custom'
    persist({ preset: presetSelect.value })
  })
  slider.addEventListener('input', () => {
    sliderValue.textContent = `${slider.value}%`
  })
  slider.addEventListener('change', () => persist({ targetCompression: Number(slider.value) }))

  settingsBtn.addEventListener('click', () => chrome.runtime.openOptionsPage())
  compressBtn.addEventListener('click', runCompress)
  insertBtn.addEventListener('click', insertIntoPage)
  copyBtn.addEventListener('click', copyResult)

  runHealthCheck()
}

async function persist(partial) {
  settings = await setSettings(partial)
}

function showError(message) {
  errorBanner.textContent = message
  errorBanner.hidden = false
}

function clearError() {
  errorBanner.hidden = true
}

async function runCompress() {
  const text = promptInput.value.trim()
  if (!text) return showError('Paste some text first.')

  clearError()
  resultBox.hidden = true
  compressBtn.disabled = true
  compressBtn.textContent = 'compressing…'

  try {
    const resp = await sendToBackground({ type: 'CC_COMPRESS', text })
    if (!resp?.ok) throw new Error(resp?.error || 'Compression failed.')
    lastResult = resp.data
    renderResult(resp.data)
  } catch (err) {
    showError(err.message)
  } finally {
    compressBtn.disabled = false
    compressBtn.textContent = 'compress →'
  }
}

function renderResult(data) {
  el('stat-original').textContent = data.original_tokens
  el('stat-compressed').textContent = data.compressed_tokens
  el('stat-ratio').textContent = `${(data.compression_ratio * 100).toFixed(1)}%`
  resultText.value = data.compressed_text
  resultBox.hidden = false
}

async function copyResult() {
  if (!lastResult) return
  await navigator.clipboard.writeText(lastResult.compressed_text)
  copyBtn.textContent = 'copied'
  setTimeout(() => (copyBtn.textContent = 'copy output'), 1200)
}

async function insertIntoPage() {
  if (!lastResult) return showError('Compress something first.')
  clearError()
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true })
    if (!tab?.id) throw new Error('No active tab.')
    await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: writeIntoFocusedField,
      args: [lastResult.compressed_text],
    })
  } catch (err) {
    showError(`Couldn't write into the page: ${err.message}`)
  }
}

// Injected into the page -- must be self-contained.
function writeIntoFocusedField(newText) {
  const elActive = document.activeElement
  if (!elActive) return
  try {
    if (elActive.tagName === 'TEXTAREA' || elActive.tagName === 'INPUT') {
      elActive.focus()
      elActive.select()
      const ok = document.execCommand('insertText', false, newText)
      if (!ok) {
        const proto = elActive.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(elActive, newText)
        elActive.dispatchEvent(new Event('input', { bubbles: true }))
      }
    } else if (elActive.isContentEditable) {
      elActive.focus()
      const range = document.createRange()
      range.selectNodeContents(elActive)
      const sel = window.getSelection()
      sel.removeAllRanges()
      sel.addRange(range)
      const ok = document.execCommand('insertText', false, newText)
      if (!ok) {
        elActive.innerText = newText
        elActive.dispatchEvent(new Event('input', { bubbles: true }))
      }
    }
  } catch {
    /* best-effort */
  }
}

async function runHealthCheck() {
  const ok = await checkHealth(settings.apiBase)
  healthDot.className = `health-dot ${ok ? 'health-dot--ok' : 'health-dot--err'}`
  healthLabel.textContent = ok ? `connected · ${settings.apiBase}` : `unreachable · ${settings.apiBase}`
}

function sendToBackground(message) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(message, (resp) => {
      if (chrome.runtime.lastError) {
        resolve({ ok: false, error: chrome.runtime.lastError.message })
        return
      }
      resolve(resp)
    })
  })
}

init()
