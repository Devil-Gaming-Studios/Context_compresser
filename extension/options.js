import { getSettings, setSettings, DEFAULT_SETTINGS } from './lib/storage.js'
import { checkHealth } from './lib/api.js'

const MODELS = [
  { value: 'default', label: 'auto / generic — cl100k_base fallback' },
  { value: 'gpt-4', label: 'GPT-4 — cl100k_base' },
  { value: 'gpt-4o', label: 'GPT-4o — o200k_base' },
  { value: 'gpt-3.5', label: 'GPT-3.5 — cl100k_base' },
  { value: 'claude', label: 'Claude — ~3.8 chars/token approx.' },
  { value: 'gemini', label: 'Gemini — ~4.0 chars/token approx.' },
]

const PRESETS = [
  { value: 'conservative', label: 'conservative — 40% reduction, accuracy-first' },
  { value: 'balanced', label: 'balanced — 70% reduction (default)' },
  { value: 'aggressive', label: 'aggressive — 85% reduction, max size cut' },
  { value: 'custom', label: 'custom — set your own %' },
]

const CONTENT_TYPES = [
  { value: 'auto', label: 'auto-detect' },
  { value: 'code', label: 'code' },
  { value: 'logs', label: 'logs' },
  { value: 'prose', label: 'prose' },
]

const el = (id) => document.getElementById(id)
const apiBaseInput = el('api-base')
const testBtn = el('test-connection')
const connectionStatus = el('connection-status')
const modelSelect = el('model-select')
const presetSelect = el('preset-select')
const sliderField = el('slider-field')
const slider = el('target-slider')
const sliderValue = el('slider-value')
const contentTypeSelect = el('content-type-select')
const siteToggles = el('site-toggles')
const savedToast = el('saved-toast')

async function init() {
  const settings = await getSettings()

  apiBaseInput.value = settings.apiBase
  for (const m of MODELS) modelSelect.append(new Option(m.label, m.value))
  for (const p of PRESETS) presetSelect.append(new Option(p.label, p.value))
  for (const c of CONTENT_TYPES) contentTypeSelect.append(new Option(c.label, c.value))
  modelSelect.value = settings.model
  presetSelect.value = settings.preset
  contentTypeSelect.value = settings.contentType
  slider.value = settings.targetCompression
  sliderValue.textContent = `${settings.targetCompression}%`
  sliderField.style.opacity = settings.preset === 'custom' ? '1' : '0.45'

  renderSiteToggles(settings.enabledSites)

  apiBaseInput.addEventListener('change', onApiBaseChange)
  testBtn.addEventListener('click', testConnection)
  modelSelect.addEventListener('change', () => save({ model: modelSelect.value }))
  presetSelect.addEventListener('change', () => {
    sliderField.style.opacity = presetSelect.value === 'custom' ? '1' : '0.45'
    save({ preset: presetSelect.value })
  })
  slider.addEventListener('input', () => (sliderValue.textContent = `${slider.value}%`))
  slider.addEventListener('change', () => save({ targetCompression: Number(slider.value) }))
  contentTypeSelect.addEventListener('change', () => save({ contentType: contentTypeSelect.value }))

  testConnection()
}

function renderSiteToggles(enabledSites) {
  siteToggles.innerHTML = ''
  const sites = { ...DEFAULT_SETTINGS.enabledSites, ...enabledSites }
  for (const [host, enabled] of Object.entries(sites)) {
    const row = document.createElement('div')
    row.className = 'site-toggle'

    const name = document.createElement('span')
    name.className = 'site-toggle-name'
    name.textContent = host

    const label = document.createElement('label')
    label.className = 'switch'
    const input = document.createElement('input')
    input.type = 'checkbox'
    input.checked = enabled !== false
    input.addEventListener('change', async () => {
      const current = await getSettings()
      const nextSites = { ...current.enabledSites, [host]: input.checked }
      await save({ enabledSites: nextSites })
    })
    const track = document.createElement('span')
    track.className = 'switch-track'
    label.append(input, track)

    row.append(name, label)
    siteToggles.append(row)
  }
}

async function onApiBaseChange() {
  const value = apiBaseInput.value.trim().replace(/\/$/, '')
  if (!value) return

  let origin
  try {
    origin = new URL(value).origin
  } catch {
    connectionStatus.textContent = 'invalid URL'
    connectionStatus.className = 'status status--err'
    return
  }

  const isLocalhost = /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(origin)
  if (!isLocalhost) {
    // Non-localhost origins need an explicit, user-granted permission --
    // request it here rather than silently failing later at fetch time.
    const granted = await chrome.permissions.request({ origins: [`${origin}/*`] })
    if (!granted) {
      connectionStatus.textContent = 'permission denied for that origin'
      connectionStatus.className = 'status status--err'
      return
    }
  }

  await save({ apiBase: value })
  testConnection()
}

async function testConnection() {
  connectionStatus.textContent = 'checking…'
  connectionStatus.className = 'status'
  const settings = await getSettings()
  const ok = await checkHealth(settings.apiBase)
  connectionStatus.textContent = ok ? 'connected' : 'unreachable'
  connectionStatus.className = `status ${ok ? 'status--ok' : 'status--err'}`
}

async function save(partial) {
  await setSettings(partial)
  flashSaved()
}

function flashSaved() {
  savedToast.hidden = false
  clearTimeout(flashSaved._t)
  flashSaved._t = setTimeout(() => (savedToast.hidden = true), 1200)
}

init()
