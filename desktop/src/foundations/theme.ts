// MadCop theme provider. Replaces the previous [data-theme="..."] switcher.
//
// Why a fresh component: the old one was named `ThemeProvider` and
// exposed `theme` (e.g. "white" | "dark"). The new one is called
// `MadcopThemeSurface` and exposes `appearance` (e.g. "light" | "dark"
// | "sepia") — different prop name, different default, different
// state shape. Components that consume it must be rewritten.

import { useCallback, useEffect, useState } from 'react'
import { madcop, type SemanticTokens } from './tokens'

export type MadcopAppearance = 'light' | 'dark' | 'sepia'

const STORAGE_KEY = 'madcop:appearance:v1'
const DEFAULT: MadcopAppearance = 'light'

function readInitial(): MadcopAppearance {
  if (typeof window === 'undefined') return DEFAULT
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'sepia') return stored
  } catch {}
  return DEFAULT
}

/** Mirror the previous color-scheme hook (used by code areas, charts, etc.) */
export function useMadcopTheme() {
  const [appearance, setAppearanceState] = useState<MadcopAppearance>(readInitial)

  // Apply to <html>
  useEffect(() => {
    const html = document.documentElement
    html.setAttribute('data-madcop-theme', appearance)
    html.setAttribute('data-theme', appearance) // keep old selector working during migration
  }, [appearance])

  const setAppearance = useCallback((next: MadcopAppearance) => {
    try { localStorage.setItem(STORAGE_KEY, next) } catch {}
    setAppearanceState(next)
  }, [])

  // Listen for system theme changes
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = (e: MediaQueryListEvent) => {
      // Only auto-switch if user hasn't explicitly chosen
      const stored = localStorage.getItem(STORAGE_KEY)
      if (!stored) setAppearanceState(e.matches ? 'dark' : 'light')
    }
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [])

  // Tokens resolved for the current appearance
  const tokens: SemanticTokens = appearance === 'dark'
    ? madcop.semantic.dark
    : madcop.semantic.light  // sepia overrides via CSS only; JS reads light as fallback

  return { appearance, setAppearance, tokens }
}

/** CSS helpers (kept here so component code doesn't import the whole tokens file) */
export { madcop }
