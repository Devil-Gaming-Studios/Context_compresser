import { useState, useCallback, useEffect } from 'react'

function getBase() {
  return typeof window !== 'undefined'
    ? window.__BACKEND_URL__ || localStorage.getItem('ctx-backend-url') || ''
    : ''
}

async function api(path, options = {}) {
  const base = getBase()
  const url = `${base}${path}`
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

// ─── Stats ─────────────────────────────────────────────────────────
export function useStats() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    api('/api/stats')
      .then((d) => { if (!cancelled) setData(d) })
      .catch(() => { if (!cancelled) setData({ totalJobs: 0, compressed: 0, savedBytes: '0 B', avgRatio: '0%' }) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  return { data, loading }
}

// ─── Compress ──────────────────────────────────────────────────────
export function useCompress() {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const compress = useCallback(async (payload) => {
    setLoading(true)
    setError(null)
    try {
      const data = await api('/api/compress', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setResult(data)
      return data
    } catch (err) {
      setError(err.message)
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  return { compress, result, loading, error }
}

// ─── History ───────────────────────────────────────────────────────
export function useHistory() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    api('/api/history')
      .then((d) => { if (!cancelled) setData(d) })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  return { data, loading, error }
}
