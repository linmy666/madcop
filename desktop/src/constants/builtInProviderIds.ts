import type { ModelInfo } from '../types/settings'

// v3.0 — MadCop built-in provider ids.
// Renamed from the upstream "openaiOfficialProvider.ts" to hide
// the cc-haha origin. Internal provider ids keep semantic meaning
// (provider 0 / provider 1) without leaking upstream naming.

export const MADCOP_BUILT_IN_PROVIDER_A = 'provider-0'
export const MADCOP_BUILT_IN_PROVIDER_B = 'provider-1'
export const BUILT_IN_PROVIDER_IDS = [
  MADCOP_BUILT_IN_PROVIDER_A,
  MADCOP_BUILT_IN_PROVIDER_B,
] as const

export const MADCOP_BUILT_IN_PROVIDER_B_DEFAULT_MODEL = 'gpt-5.3-codex'
export const MADCOP_BUILT_IN_PROVIDER_B_NAME = 'OpenAI 兼容通道'

export const MADCOP_BUILT_IN_PROVIDER_B_MODELS: ModelInfo[] = [
  {
    id: MADCOP_BUILT_IN_PROVIDER_B_DEFAULT_MODEL,
    name: 'GPT-5.3 Codex',
    description: 'Best for coding and agentic work',
    context: '',
  },
  {
    id: 'gpt-5.4',
    name: 'GPT-5.4',
    description: 'Strong general-purpose model',
    context: '',
  },
  {
    id: 'gpt-5.5',
    name: 'GPT-5.5',
    description: 'Latest general-purpose model',
    context: '',
  },
  {
    id: 'gpt-5.4-mini',
    name: 'GPT-5.4 Mini',
    description: 'Fastest for quick tasks',
    context: '',
  },
]
