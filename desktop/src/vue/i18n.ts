/**
 * Minimal i18n module for the Vue chat components.
 * Provides a `useTranslation()` hook returning a `t(key, params?)` function.
 * For now, returns keys as-is (no actual translation dictionary loaded).
 * TODO: wire up to the app's real i18n system (vue-i18n / i18next).
 */

type TranslationKey = string

export function useTranslation() {
  function t(key: TranslationKey, params?: Record<string, string | number>): string {
    if (!params) return key
    let result = key
    for (const [param, value] of Object.entries(params)) {
      result = result.replace(`{${param}}`, String(value))
    }
    return result
  }
  return t
}

/**
 * Format a token count with human-readable suffixes.
 * Mirrors lib/formatTokenCount from the React app.
 */
export function formatTokenCount(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(1)}M`
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}K`
  return String(count)
}