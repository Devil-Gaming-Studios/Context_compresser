// Shared settings helper used by background, popup, and options pages.
// Everything lives in chrome.storage.sync so settings follow the user
// across machines where they're signed into the same browser profile.

export const DEFAULT_SETTINGS = {
  apiBase: 'http://localhost:8000',
  model: 'default',          // default | gpt-4 | gpt-4o | gpt-3.5 | claude | gemini
  preset: 'balanced',        // custom | conservative | balanced | aggressive
  targetCompression: 70,     // used only when preset === 'custom', 5-95
  contentType: 'auto',       // auto | code | logs | prose
  enabledSites: {
    'chatgpt.com': true,
    'chat.openai.com': true,
    'claude.ai': true,
    'gemini.google.com': true,
    'www.perplexity.ai': true,
  },
  showToastStats: true,
}

export async function getSettings() {
  const stored = await chrome.storage.sync.get(DEFAULT_SETTINGS)
  return { ...DEFAULT_SETTINGS, ...stored }
}

export async function setSettings(partial) {
  await chrome.storage.sync.set(partial)
  return getSettings()
}

export function onSettingsChanged(callback) {
  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== 'sync') return
    callback(changes)
  })
}
