// Reference data for the "fit into budget" quick buttons and the cost
// calculator. Context windows and prices change over time and vary by
// exact model tier (e.g. gpt-4o vs gpt-4o-mini) — these are reasonable
// defaults, not a live pricing feed. The cost calculator lets the user
// override the $/1M figure for their actual plan/model.

export const MODEL_CONTEXT_WINDOWS = {
  default: 128_000,
  'gpt-4': 8_192,
  'gpt-4o': 128_000,
  'gpt-3.5': 16_385,
  claude: 200_000,
  gemini: 1_000_000,
}

// Approximate USD per 1M input tokens. Treat as a starting point — the
// cost calculator UI lets the user edit this to match their actual plan.
export const MODEL_PRICING_PER_MILLION = {
  default: 3,
  'gpt-4': 30,
  'gpt-4o': 2.5,
  'gpt-3.5': 0.5,
  claude: 3,
  gemini: 1.25,
}

// Common context-window sizes to offer as one-click "fit into" targets,
// regardless of which model is currently selected.
export const COMMON_BUDGETS = [
  { label: '8K', tokens: 8_000 },
  { label: '32K', tokens: 32_000 },
  { label: '128K', tokens: 128_000 },
  { label: '200K', tokens: 200_000 },
]

export function formatTokens(n) {
  if (n == null) return '—'
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n % 1_000_000 === 0 ? 0 : 1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(n % 1_000 === 0 ? 0 : 1)}K`
  return String(n)
}