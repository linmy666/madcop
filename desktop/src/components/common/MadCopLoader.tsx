import { useEffect, useState } from 'react'

/**
 * MadCopLoader — a clean, on-brand loading animation that replaces
 * the abstract clover.mp4 / ripple.mp4 videos.
 *
 * Renders the new MadCop mascot (a friendly purple-drop creature
 * with a halo + smile) in three animation states:
 *   - 'ready'    : halo gently rotates (mascot scanning)
 *   - 'thinking' : mascot tilts left-right (considering)
 *   - 'working'  : mascot bobs up and down (executing)
 *
 * The mascot image is selected by theme:
 *   - default / white / dark / light → mascot.png (purple creature)
 *   - theme-stardew                  → mascot-stardew.png
 *   - theme-bauhaus                  → mascot-bauhaus.png
 *
 * Uses inline SVG animations (no external assets, no videos)
 * so it renders instantly, scales perfectly at any size, and
 * never breaks.
 */

export type MadCopState = 'ready' | 'thinking' | 'working'

type Props = {
  state: MadCopState
  className?: string
  size?: number
  label?: string
}

const STAGE_LABELS: Record<MadCopState, string> = {
  ready: 'MadCop 已准备好',
  thinking: 'MadCop 正在思考',
  working: 'MadCop 正在工作',
}

const STAGE_ICONS: Record<MadCopState, string> = {
  ready: '🔍',
  thinking: '✏️',
  working: '⚡',
}

function pickMascotSrc(): string {
  if (typeof document === 'undefined') return './mascot.png'
  if (document.body.classList.contains('theme-bauhaus'))
    return './mascot-bauhaus.png'
  if (document.body.classList.contains('theme-stardew'))
    return './mascot-stardew.png'
  return './mascot.png'
}

export function MadCopLoader({
  state,
  className = '',
  size = 80,
  label,
}: Props) {
  const [mascotSrc, setMascotSrc] = useState('./mascot.png')

  useEffect(() => {
    setMascotSrc(pickMascotSrc())
    // Watch for theme changes
    const obs = new MutationObserver(() => setMascotSrc(pickMascotSrc()))
    obs.observe(document.body, {
      attributes: true,
      attributeFilter: ['class'],
    })
    return () => obs.disconnect()
  }, [])

  // Animation per state
  const animClass =
    state === 'thinking'
      ? 'madcop-anim-think'
      : state === 'working'
        ? 'madcop-anim-work'
        : 'madcop-anim-breathe'

  return (
    <div
      role="img"
      aria-label={label ?? STAGE_LABELS[state]}
      className={`inline-flex flex-col items-center gap-3 ${className}`}
      style={{ width: size + 32 }}
    >
      <div
        className={animClass}
        style={{
          width: size,
          height: size,
        }}
      >
        <img
          src={mascotSrc}
          alt="MadCop mascot"
          className="block w-full h-full"
          style={{
            imageRendering: 'pixelated',
            objectFit: 'contain',
          }}
          draggable={false}
        />
      </div>

      <div
        className="text-center"
        style={{
          fontSize: 13,
          color: 'var(--color-text-secondary)',
          fontWeight: 500,
          maxWidth: size + 32,
        }}
      >
        <span style={{ marginRight: 6 }}>{STAGE_ICONS[state]}</span>
        {label ?? STAGE_LABELS[state]}
      </div>

      <style>{mascotLoaderStyles}</style>
    </div>
  )
}

const mascotLoaderStyles = `
@keyframes madcop-anim-breathe {
  0%, 100% { transform: scale(1) translateY(0); }
  50%      { transform: scale(1.04) translateY(-2px); }
}
@keyframes madcop-anim-think {
  0%, 100% { transform: rotate(-3deg); }
  25%      { transform: rotate(-5deg) scale(1.02); }
  50%      { transform: rotate(0deg)   scale(1.05); }
  75%      { transform: rotate(5deg)  scale(1.02); }
}
@keyframes madcop-anim-work {
  0%, 100% { transform: translateY(0) scale(1); }
  50%      { transform: translateY(-6px) scale(0.96); }
}
.madcop-anim-breathe { animation: madcop-anim-breathe 3s ease-in-out infinite; transform-origin: center; }
.madcop-anim-think   { animation: madcop-anim-think 1.6s ease-in-out infinite; transform-origin: center bottom; }
.madcop-anim-work    { animation: madcop-anim-work 0.8s ease-in-out infinite; transform-origin: center; }
`
