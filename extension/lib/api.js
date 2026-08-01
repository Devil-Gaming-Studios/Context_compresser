// Thin client for the Context Compressor FastAPI backend. Mirrors the
// request/response shapes in backend/main.py exactly -- see
// CompressRequest / CompressResponse there if this ever drifts.

export class CompressorApiError extends Error {}

/**
 * @param {string} apiBase        e.g. "http://localhost:8000"
 * @param {string} text           prompt text to compress
 * @param {object} opts
 * @param {string} [opts.model]           default | gpt-4 | gpt-4o | gpt-3.5 | claude | gemini
 * @param {string} [opts.preset]          custom | conservative | balanced | aggressive
 * @param {number} [opts.targetCompression] 0-100, only sent when preset is 'custom'
 * @param {string} [opts.contentType]     auto | code | logs | prose
 */
export async function compressText(apiBase, text, opts = {}) {
  const { model = 'default', preset = 'balanced', targetCompression = 70, contentType = 'auto' } = opts

  const body = {
    text,
    content_type: contentType,
    preset: preset === 'custom' ? null : preset,
    model,
  }
  if (preset === 'custom') {
    body.target_compression = targetCompression / 100
  }

  let res
  try {
    res = await fetch(`${apiBase.replace(/\/$/, '')}/compress`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (err) {
    throw new CompressorApiError(
      `Can't reach the Context Compressor API at ${apiBase}. Is the backend running, and is this origin allowed?`
    )
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const parsed = await res.json()
      if (parsed?.detail) detail = parsed.detail
    } catch {
      /* non-JSON error body, keep default message */
    }
    throw new CompressorApiError(detail)
  }

  return res.json() // CompressResponse shape
}

export async function checkHealth(apiBase) {
  try {
    const res = await fetch(`${apiBase.replace(/\/$/, '')}/health`)
    if (!res.ok) return false
    const data = await res.json()
    return data?.status === 'ok'
  } catch {
    return false
  }
}
