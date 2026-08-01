// Runs on chatgpt.com, claude.ai, gemini.google.com, perplexity.ai (see
// manifest.json content_scripts.matches). Finds the site's main prompt
// field, pins a small floating "compress" button next to it, and wires
// it up to the background service worker for the actual API call.

;(() => {
  const HOST = location.hostname

  // Hints per site, tried in order. Falls back to a generic finder below
  // if none match (these SPAs change their DOM structure over time).
  const SITE_SELECTORS = {
    'chatgpt.com': ['#prompt-textarea', 'div[contenteditable="true"]', 'textarea'],
    'chat.openai.com': ['#prompt-textarea', 'div[contenteditable="true"]', 'textarea'],
    'claude.ai': ['div[contenteditable="true"].ProseMirror', 'div[contenteditable="true"]', 'textarea'],
    'gemini.google.com': ['rich-textarea div[contenteditable="true"]', 'div[contenteditable="true"]', 'textarea'],
    'www.perplexity.ai': ['textarea', 'div[contenteditable="true"]'],
  }

  let settingsCache = null
  let btn = null
  let statusEl = null
  let currentField = null
  let pollTimer = null

  init()

  async function init() {
    settingsCache = await sendToBackground({ type: 'CC_GET_SETTINGS' })
    if (!settingsCache?.ok) return
    if (settingsCache.data.enabledSites?.[HOST] === false) return // user turned this site off

    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== 'sync') return
      if (changes.enabledSites) {
        const stillEnabled = changes.enabledSites.newValue?.[HOST] !== false
        toggleUi(stillEnabled)
      }
      if (settingsCache) {
        for (const [key, { newValue }] of Object.entries(changes)) {
          settingsCache.data[key] = newValue
        }
      }
    })

    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      if (message?.type === 'CC_TRIGGER_COMPRESS') {
        sendResponse({ ok: true }) // acknowledge so background doesn't fall back to generic mode
        runCompressFlow()
        return
      }
    })

    ensureUi()
    pollTimer = setInterval(ensureUi, 600) // SPA re-renders constantly; cheap poll beats a brittle MutationObserver
    window.addEventListener('scroll', positionButton, true)
    window.addEventListener('resize', positionButton)
  }

  function toggleUi(enabled) {
    if (enabled) {
      ensureUi()
      if (!pollTimer) pollTimer = setInterval(ensureUi, 600)
    } else {
      clearInterval(pollTimer)
      pollTimer = null
      btn?.remove()
      statusEl?.remove()
      btn = null
      statusEl = null
    }
  }

  function findPromptField() {
    const hints = SITE_SELECTORS[HOST] || []
    for (const sel of hints) {
      const el = document.querySelector(sel)
      if (el && isVisible(el)) return el
    }
    // Generic fallback: largest visible textarea/contenteditable on the page
    const candidates = [...document.querySelectorAll('textarea, [contenteditable="true"]')].filter(isVisible)
    if (candidates.length === 0) return null
    candidates.sort((a, b) => area(b) - area(a))
    return candidates[0]
  }

  function isVisible(el) {
    return !!(el.offsetParent || el.getClientRects().length)
  }

  function area(el) {
    const r = el.getBoundingClientRect()
    return r.width * r.height
  }

  function ensureUi() {
    const field = findPromptField()
    if (!field) {
      btn?.remove()
      btn = null
      currentField = null
      return
    }
    currentField = field
    if (!btn) {
      btn = document.createElement('button')
      btn.id = 'cc-float-btn'
      btn.type = 'button'
      btn.textContent = '⇥ compress'
      btn.title = 'Compress this prompt (Context Compressor)'
      btn.addEventListener('click', (e) => {
        e.preventDefault()
        e.stopPropagation()
        runCompressFlow()
      })
      document.documentElement.appendChild(btn)
    }
    positionButton()
  }

  function positionButton() {
    if (!btn || !currentField || !document.body.contains(currentField)) return
    const r = currentField.getBoundingClientRect()
    if (r.width === 0 && r.height === 0) return
    btn.style.top = `${Math.max(8, r.top - 34)}px`
    btn.style.left = `${Math.min(window.innerWidth - 140, r.right - 118)}px`
  }

  function getFieldText(el) {
    const sel = window.getSelection ? window.getSelection().toString() : ''
    if (sel && sel.trim().length > 0 && el.contains?.(window.getSelection().anchorNode)) {
      return { mode: 'selection', text: sel }
    }
    if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') return { mode: 'field', text: el.value }
    if (el.isContentEditable) return { mode: 'field', text: el.innerText }
    return { mode: 'none', text: '' }
  }

  function setFieldText(el, mode, text) {
    try {
      el.focus()
      if (mode === 'selection') {
        const ok = document.execCommand('insertText', false, text)
        if (ok) return true
      }
      if (el.tagName === 'TEXTAREA' || el.tagName === 'INPUT') {
        el.select()
        const ok = document.execCommand('insertText', false, text)
        if (!ok) {
          const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype
          Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, text)
          el.dispatchEvent(new Event('input', { bubbles: true }))
        }
        return true
      }
      if (el.isContentEditable) {
        const range = document.createRange()
        range.selectNodeContents(el)
        const s = window.getSelection()
        s.removeAllRanges()
        s.addRange(range)
        const ok = document.execCommand('insertText', false, text)
        if (!ok) {
          el.innerText = text
          el.dispatchEvent(new Event('input', { bubbles: true }))
        }
        return true
      }
    } catch {
      return false
    }
    return false
  }

  async function runCompressFlow() {
    const field = currentField || findPromptField()
    if (!field) return showStatus('No prompt field found on this page.', false)

    const { mode, text } = getFieldText(field)
    if (!text || !text.trim()) return showStatus('Field is empty — nothing to compress.', false)

    showStatus('compressing…', null)
    setBtnLoading(true)
    const resp = await sendToBackground({ type: 'CC_COMPRESS', text })
    setBtnLoading(false)

    if (!resp?.ok) {
      showStatus(resp?.error || 'Compression failed.', false)
      return
    }

    const data = resp.data
    setFieldText(field, mode, data.compressed_text)
    const pct = (data.compression_ratio * 100).toFixed(1)
    showStatus(`${data.original_tokens} → ${data.compressed_tokens} tok (−${pct}%)`, true)
  }

  function setBtnLoading(loading) {
    if (!btn) return
    btn.disabled = loading
    btn.textContent = loading ? '…' : '⇥ compress'
  }

  function showStatus(message, success) {
    if (!statusEl) {
      statusEl = document.createElement('div')
      statusEl.id = 'cc-status-toast'
      document.documentElement.appendChild(statusEl)
    }
    statusEl.textContent = message
    statusEl.classList.remove('cc-toast--ok', 'cc-toast--err', 'cc-toast--pending')
    statusEl.classList.add(success === true ? 'cc-toast--ok' : success === false ? 'cc-toast--err' : 'cc-toast--pending')
    statusEl.classList.add('cc-toast--visible')
    if (btn) {
      const r = btn.getBoundingClientRect()
      statusEl.style.top = `${r.bottom + 6}px`
      statusEl.style.left = `${Math.max(8, r.right - 220)}px`
    }
    clearTimeout(showStatus._t)
    if (success !== null) {
      showStatus._t = setTimeout(() => statusEl.classList.remove('cc-toast--visible'), 3200)
    }
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
})()
