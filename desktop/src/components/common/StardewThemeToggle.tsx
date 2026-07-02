import { useEffect, useState } from 'react'

/**
 * StardewThemeToggle — v2.6.0
 * A small switch that toggles the .theme-stardew class on <body>,
 * turning the whole app into a Stardew-Valley-style pixel art skin.
 *
 * The toggle is persisted to localStorage and re-applied on every
 * applyTheme() call (which runs whenever the user changes the
 * light/dark theme too).
 */
export function StardewThemeToggle() {
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    try {
      const stored = localStorage.getItem('madcop-theme-stardew') === '1'
      setEnabled(stored)
      document.body.classList.toggle('theme-stardew', stored)
    } catch { /* noop */ }
  }, [])

  const toggle = () => {
    const next = !enabled
    setEnabled(next)
    try { localStorage.setItem('madcop-theme-stardew', next ? '1' : '0') } catch {}
    document.body.classList.toggle('theme-stardew', next)
  }

  return (
    <div
      role="group"
      aria-label="像素 Pixel theme"
      className="mb-8 flex items-center gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3"
    >
      <img
        src="./mascot-stardew.png"
        alt="Stardew Valley pixel mascot"
        className="h-12 w-12 shrink-0"
        style={{ imageRendering: 'pixelated' }}
      />
      <div className="flex-1">
        <h3 className="text-sm font-semibold text-[var(--color-text-primary)]">
          像素 Pixel
        </h3>
        <p className="text-xs text-[var(--color-text-tertiary)]">
          16-bit 像素风皮肤 — 暖羊皮纸 + 棕木 + 草地 + 金色高亮
          （致敬复古 RPG 美术风格）。
        </p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={enabled}
        onClick={toggle}
        className={`relative h-7 w-12 shrink-0 rounded-full border-2 transition-colors ${
          enabled
            ? 'border-[var(--stardew-wood-dark,#5C2A20)] bg-[var(--stardew-gold,#FFD76E)]'
            : 'border-[var(--color-border)] bg-[var(--color-surface-container)]'
        }`}
        title={enabled ? 'Click to turn off Stardew theme' : 'Click to turn on Stardew theme'}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-full border border-current transition-transform ${
            enabled
              ? 'translate-x-6 bg-[var(--stardew-wood-dark,#5C2A20)]'
              : 'translate-x-0.5 bg-[var(--color-text-secondary)]'
          }`}
        />
      </button>
    </div>
  )
}
