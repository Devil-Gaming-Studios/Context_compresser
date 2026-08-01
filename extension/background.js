import { getSettings } from './lib/storage.js'
import { compressText } from './lib/api.js'

const CONTEXT_MENU_ID = 'cc-compress-selection'

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: CONTEXT_MENU_ID,
    title: 'Compress with Context Compressor',
    contexts: ['selection', 'editable'],
  })
})

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId === CONTEXT_MENU_ID && tab?.id) {
    runCompressFlow(tab.id)
  }
})

chrome.commands.onCommand.addListener((command, tab) => {
  if (command === 'compress-active-field' && tab?.id) {
    runCompressFlow(tab.id)
  }
})

// Message hub -- content scripts and the popup route their API calls
// and settings reads through here so there's a single fetch path and a
// single CORS/host-permission surface to reason about.
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type === 'CC_COMPRESS') {
    handleCompressText(message.text)
      .then((data) => sendResponse({ ok: true, data }))
      .catch((err) => sendResponse({ ok: false, error: err.message }))
    return true // keep the message channel open for the async response
  }
  if (message?.type === 'CC_GET_SETTINGS') {
    getSettings().then((data) => sendResponse({ ok: true, data }))
    return true
  }
  return undefined
})

async function handleCompressText(text) {
  const settings = await getSettings()
  return compressText(settings.apiBase, text, {
    model: settings.model,
    preset: settings.preset,
    targetCompression: settings.targetCompression,
    contentType: settings.contentType,
  })
}

/**
 * Entry point for both the context menu and the keyboard shortcut.
 * Prefers the rich, site-aware content-script flow (floating button's
 * own logic) when one is already injected on the page; falls back to a
 * generic activeElement-based injection for any other site.
 */
async function runCompressFlow(tabId) {
  try {
    const resp = await chrome.tabs.sendMessage(tabId, { type: 'CC_TRIGGER_COMPRESS' })
    if (resp?.ok) return
  } catch {
    // No content script listening on this tab (not one of the matched
    // sites, or the page hasn't loaded content.js) -- fall through.
  }
  await runGenericCompressFlow(tabId)
}

async function runGenericCompressFlow(tabId) {
  let extracted
  try {
    const [{ result } = {}] = await chrome.scripting.executeScript({
      target: { tabId },
      func: extractActiveFieldText,
    })
    extracted = result
  } catch (err) {
    // Most likely: no activeTab grant yet, or a restricted page
    // (chrome://, the Chrome Web Store, etc.) where scripting is blocked.
    return
  }

  if (!extracted || !extracted.text || !extracted.text.trim()) {
    await safeInject(tabId, showGenericToast, ['No text found in the focused field.', false])
    return
  }

  try {
    const data = await handleCompressText(extracted.text)
    await safeInject(tabId, applyCompressedText, [data.compressed_text, extracted.mode])
    const pct = (data.compression_ratio * 100).toFixed(1)
    await safeInject(tabId, showGenericToast, [
      `${data.original_tokens} \u2192 ${data.compressed_tokens} tok (\u2212${pct}%)`,
      true,
    ])
  } catch (err) {
    await safeInject(tabId, showGenericToast, [err.message || 'Compression failed.', false])
  }
}

async function safeInject(tabId, func, args) {
  try {
    await chrome.scripting.executeScript({ target: { tabId }, func, args })
  } catch {
    /* best-effort; page may have navigated away mid-flow */
  }
}

// ---------------------------------------------------------------------
// Functions below are injected into the page via chrome.scripting and
// must be fully self-contained (no closures over this file's scope).
// ---------------------------------------------------------------------

function extractActiveFieldText() {
  const el = document.activeElement
  const selection = window.getSelection ? window.getSelection().toString() : ''
  if (selection && selection.trim().length > 0) return { mode: 'selection', text: selection }
  if (!el) return { mode: 'none', text: '' }
  if (el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && (el.type === 'text' || el.type === 'search'))) {
    return { mode: 'field', text: el.value }
  }
  if (el.isContentEditable) return { mode: 'field', text: el.innerText }
  return { mode: 'none', text: '' }
}

function applyCompressedText(newText, mode) {
  const el = document.activeElement
  if (!el) return
  try {
    if (mode === 'selection') {
      document.execCommand('insertText', false, newText)
      return
    }
    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
      el.focus()
      el.select()
      const ok = document.execCommand('insertText', false, newText)
      if (!ok) {
        const proto = el.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, newText)
        el.dispatchEvent(new Event('input', { bubbles: true }))
      }
      return
    }
    if (el.isContentEditable) {
      el.focus()
      const range = document.createRange()
      range.selectNodeContents(el)
      const sel = window.getSelection()
      sel.removeAllRanges()
      sel.addRange(range)
      const ok = document.execCommand('insertText', false, newText)
      if (!ok) {
        el.innerText = newText
        el.dispatchEvent(new Event('input', { bubbles: true }))
      }
    }
  } catch {
    /* best-effort DOM write */
  }
}

function showGenericToast(message, success) {
  const id = '__cc-generic-toast'
  let toast = document.getElementById(id)
  if (!toast) {
    toast = document.createElement('div')
    toast.id = id
    document.documentElement.appendChild(toast)
  }
  toast.textContent = message
  toast.style.cssText =
    'position:fixed;bottom:20px;right:20px;z-index:2147483647;' +
    'background:#121815;color:' + (success ? '#5fe6a4' : '#c97a5a') + ';' +
    'border:1px solid #263029;border-radius:8px;padding:10px 14px;' +
    'font-family:ui-monospace,monospace;font-size:13px;max-width:320px;' +
    'box-shadow:0 8px 24px rgba(0,0,0,0.4);'
  clearTimeout(window.__ccToastTimer)
  window.__ccToastTimer = setTimeout(() => toast.remove(), 3200)
}
