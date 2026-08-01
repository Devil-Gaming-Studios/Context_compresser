import { useEffect, useCallback } from 'react'
import { useApp } from '../context/AppContext.jsx'

const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function api(path, options = {}) {
  const url = `${BASE}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json().catch(() => ({}))
}

// ── Health ──────────────────────────────────────────────────────────
export function useHealth() {
  const { setApiConnected } = useApp()

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      try {
        await api('/health', { method: 'GET' })
        if (!cancelled) setApiConnected(true)
      } catch {
        if (!cancelled) setApiConnected(false)
      }
    }
    check()
    const id = setInterval(check, 10000)
    return () => { cancelled = true; clearInterval(id) }
  }, [setApiConnected])
}

// ── Presets ─────────────────────────────────────────────────────────
export function usePresets() {
  const { presets, setPresets } = useApp()

  const fetchPresets = useCallback(async () => {
    if (presets) return presets
    const data = await api('/presets')
    setPresets(data)
    return data
  }, [presets, setPresets])

  return { presets, fetchPresets }
}

// ── Compress text ───────────────────────────────────────────────────
export async function compressText(payload) {
  return api('/compress', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function compressFile(file, payload) {
  const form = new FormData()
  form.append('file', file)
  if (payload.target_compression != null) form.append('target_compression', String(payload.target_compression))
  if (payload.content_type) form.append('content_type', payload.content_type)
  if (payload.preset) form.append('preset', payload.preset)
  if (payload.model) form.append('model', payload.model)

  const url = `${BASE}/compress/file`
  const res = await fetch(url, { method: 'POST', body: form })
  if (!res.ok) {
    const text = await res.text().catch(() => 'Unknown error')
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

// ── Compress diff ───────────────────────────────────────────────────
export async function compressDiff(payload) {
  return api('/compress/diff', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export async function compressDiffGithub(payload) {
  return api('/compress/diff/github', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}
