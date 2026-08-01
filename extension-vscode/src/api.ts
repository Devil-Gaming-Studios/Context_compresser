// Thin client for the Context Compressor FastAPI backend. Mirrors the
// request/response shapes in backend/main.py exactly -- keep this in
// sync with CompressRequest / CompressResponse / TokenizeResponse
// there (and with extension/lib/api.js, the Chrome extension's twin).

export class CompressorApiError extends Error {}

export type ModelName = "default" | "gpt-4" | "gpt-4o" | "gpt-3.5" | "claude" | "gemini";
export type PresetName = "conservative" | "balanced" | "aggressive" | "custom";
export type ContentType = "auto" | "code" | "logs" | "prose";

export interface DiffLineOut {
  text: string;
  kept: boolean;
}

export interface CompressResponse {
  original_tokens: number;
  compressed_tokens: number;
  compression_ratio: number;
  chunks_total: number;
  chunks_kept: number;
  near_duplicates_removed: number;
  structural_lines_collapsed: number;
  compressed_text: string;
  notes: string[];
  diff_lines: DiffLineOut[];
}

export interface CompressOptions {
  model?: ModelName;
  preset?: PresetName;
  targetCompression?: number; // 0-100, only sent when preset is 'custom'
  contentType?: ContentType;
}

async function postJson<T>(apiBase: string, path: string, body: unknown): Promise<T> {
  const base = apiBase.replace(/\/$/, "");
  let res: Response;
  try {
    res = await fetch(`${base}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch (err) {
    throw new CompressorApiError(
      `Can't reach the Context Compressor API at ${apiBase}. Is the backend running, and is contextCompressor.apiBase set correctly?`
    );
  }

  if (!res.ok) {
    let detail = `Request failed (${res.status})`;
    try {
      const parsed = (await res.json()) as { detail?: string };
      if (parsed?.detail) detail = parsed.detail;
    } catch {
      /* non-JSON error body, keep default message */
    }
    throw new CompressorApiError(detail);
  }

  return res.json() as Promise<T>;
}

export async function compressText(
  apiBase: string,
  text: string,
  opts: CompressOptions = {}
): Promise<CompressResponse> {
  const { model = "default", preset = "balanced", targetCompression = 70, contentType = "auto" } = opts;

  const body: Record<string, unknown> = {
    text,
    content_type: contentType,
    preset: preset === "custom" ? null : preset,
    model,
  };
  if (preset === "custom") {
    body.target_compression = targetCompression / 100;
  }

  return postJson<CompressResponse>(apiBase, "/compress", body);
}

export interface TokenizeResponse {
  tokens: number;
}

export async function tokenize(apiBase: string, text: string, model: ModelName = "default"): Promise<number> {
  const data = await postJson<TokenizeResponse>(apiBase, "/tokenize", { text, model });
  return data.tokens;
}

export interface SessionTurnOut {
  role: string;
  original_tokens: number;
  compressed_tokens: number;
  action: string;
  content: string;
}

export interface SessionCompressResponse {
  turns: SessionTurnOut[];
  original_tokens: number;
  compressed_tokens: number;
  compression_ratio: number;
  turns_total: number;
  turns_kept: number;
  turns_dropped_duplicate: number;
  notes: string[];
}

export async function compressSession(
  apiBase: string,
  exportJson: string,
  opts: { protectRecent?: number; targetCompression?: number; model?: ModelName } = {}
): Promise<SessionCompressResponse> {
  const { protectRecent = 4, targetCompression = 70, model = "default" } = opts;
  return postJson<SessionCompressResponse>(apiBase, "/compress/session", {
    export: exportJson,
    protect_recent: protectRecent,
    target_compression: targetCompression / 100,
    model,
  });
}

export async function checkHealth(apiBase: string): Promise<boolean> {
  try {
    const res = await fetch(`${apiBase.replace(/\/$/, "")}/health`);
    if (!res.ok) return false;
    const data = (await res.json()) as { status?: string };
    return data?.status === "ok";
  } catch {
    return false;
  }
}
