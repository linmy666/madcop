import { useEffect, useState } from 'react'

/**
 * MadCopLoader — a clean, on-brand loading animation that replaces
 * the abstract clover.mp4 / ripple.mp4 videos.
 *
 * Renders the new MadCop mascot (a friendly purple-drop creature
 * with a halo + smile) in three animation states:
 *   - 'ready'    : mascot gently breathes
 *   - 'thinking' : mascot tilts left-right (considering)
 *   - 'working'  : mascot bobs up and down (executing)
 *
 * v2.6.3.2: simplified to JUST the mascot image with breathing
 * animation. No separate halo layer (mascot already has its own
 * halo baked into the PNG). No sparkle particles. No status
 * icon (user said '不要加任何icon'). Just a clean mascot + a
 * plain text label.
 *
 * The mascot image is selected by theme:
 *   - default / white / dark / light → mascot.png (purple creature)
 *   - theme-stardew                  → mascot-stardew.png
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

function pickMascotSrc(): string {
  // v2.6.3.2: cache-bust so Electron re-fetches the file when it changes.
  // The renderer caches `./mascot.png` aggressively; a timestamp query
  // string forces a fresh load after the user updates the file.
  if (typeof document === 'undefined') return './mascot.png?v=2633'
  if (document.body.classList.contains('theme-stardew'))
    return './mascot-stardew.png?v=2633'
  return './mascot.png?v=2633'
}

export function MadCopLoader({
  state,
  className = '',
  size = 192,
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
      className={`madcop-loader ${className}`}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 12,
        background: 'transparent',
      }}
    >
      <div
        className={animClass}
        style={{
          width: size,
          height: size,
          background: 'transparent',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}
      >
        <img
          src={mascotSrc}
          alt="MadCop mascot"
          className="block"
          style={{
            width: '100%',
            height: '100%',
            imageRendering: 'auto',
            objectFit: 'contain',
            background: 'transparent',
            display: 'block',
          }}
          draggable={false}
        />
      </div>

      <div
        style={{
          fontSize: 16,
          color: 'var(--color-text-secondary)',
          fontWeight: 500,
          textAlign: 'center',
        }}
      >
        {label ?? STAGE_LABELS[state]}
      </div>

      <style>{mascotLoaderStyles}</style>
    </div>
  )
}

const mascotLoaderStyles = `
/* v2.6.3.2: simplified animations. No separate halo, no sparkles.
   The mascot PNG already has its own halo. */
.madcop-anim-breathe {
  animation: madcop-anim-breathe 3s ease-in-out infinite;
  transform-origin: center;
}
.madcop-anim-think {
  animation: madcop-anim-think 1.6s ease-in-out infinite;
  transform-origin: center bottom;
}
.madcop-anim-work {
  animation: madcop-anim-work 0.8s ease-in-out infinite;
  transform-origin: center;
}

@keyframes madcop-anim-breathe {
  0%, 100% { transform: scale(1)    translateY(0); }
  50%      { transform: scale(1.04) translateY(-3px); }
}
@keyframes madcop-anim-think {
  0%, 100% { transform: rotate(-3deg); }
  25%      { transform: rotate(-5deg); }
  50%      { transform: rotate(0deg); }
  75%      { transform: rotate(5deg); }
}
@keyframes madcop-anim-work {
  0%, 100% { transform: translateY(0); }
  50%      { transform: translateY(-8px); }
}
`
