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
        {/* Halo — separate animated layer, always present */}
        <div className="madcop-loader-halo" aria-hidden="true" />
        {/* Sparkle particles — visible only in 'working' state via CSS */}
        <div className="madcop-loader-sparkle" aria-hidden="true" />
        <div className="madcop-loader-sparkle" aria-hidden="true" />
        <div className="madcop-loader-sparkle" aria-hidden="true" />
        <div className="madcop-loader-sparkle" aria-hidden="true" />
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
/* The mascot image is rendered inside an animated wrapper div.
   The wrapper handles rotation/scale, the image does the halo. */
.madcop-anim-breathe {
  animation: madcop-anim-breathe 3s ease-in-out infinite;
  transform-origin: center;
  position: relative;
}
.madcop-anim-think {
  animation: madcop-anim-think 1.6s ease-in-out infinite;
  transform-origin: center bottom;
  position: relative;
}
.madcop-anim-work {
  animation: madcop-anim-work 0.8s ease-in-out infinite;
  transform-origin: center;
  position: relative;
}

/* Halo floats above the mascot — separate animated layer */
.madcop-loader-halo {
  position: absolute;
  top: 4%;
  left: 50%;
  transform: translateX(-50%);
  width: 38%;
  height: 14%;
  border: 3px solid rgba(255, 200, 100, 0.85);
  border-radius: 50%;
  box-shadow:
    0 0 12px rgba(255, 200, 100, 0.4),
    inset 0 0 6px rgba(255, 240, 180, 0.5);
  pointer-events: none;
  animation: madcop-halo-pulse 3s ease-in-out infinite;
}
.madcop-anim-think .madcop-loader-halo {
  animation: madcop-halo-think 1.6s ease-in-out infinite;
}
.madcop-anim-work .madcop-loader-halo {
  animation: madcop-halo-work 0.8s ease-in-out infinite;
}

@keyframes madcop-anim-breathe {
  0%, 100% { transform: scale(1)    translateY(0); }
  50%      { transform: scale(1.05) translateY(-3px); }
}
@keyframes madcop-anim-think {
  0%, 100% { transform: rotate(-4deg)  scale(1); }
  25%      { transform: rotate(-6deg)  scale(1.03); }
  50%      { transform: rotate(0deg)   scale(1.06); }
  75%      { transform: rotate(6deg)   scale(1.03); }
}
@keyframes madcop-anim-work {
  0%, 100% { transform: translateY(0)    scale(1); }
  50%      { transform: translateY(-10px) scale(0.94); }
}
@keyframes madcop-halo-pulse {
  0%, 100% { transform: translateX(-50%) scale(1)    rotate(0deg);   opacity: 0.85; }
  50%      { transform: translateX(-50%) scale(1.15) rotate(15deg);  opacity: 1;    }
}
@keyframes madcop-halo-think {
  0%, 100% { transform: translateX(-50%) rotate(0deg); }
  25%      { transform: translateX(-50%) rotate(-20deg); }
  50%      { transform: translateX(-50%) rotate(0deg); }
  75%      { transform: translateX(-50%) rotate(20deg); }
}
@keyframes madcop-halo-work {
  0%, 100% { transform: translateX(-50%) scale(1); }
  50%      { transform: translateX(-50%) scale(1.3); }
}

/* Sparkle particles around the mascot in 'working' state */
.madcop-loader-sparkle {
  position: absolute;
  width: 6px;
  height: 6px;
  background: var(--stardew-gold, #FFD700);
  border-radius: 50%;
  opacity: 0;
  pointer-events: none;
}
.madcop-anim-work .madcop-loader-sparkle {
  animation: madcop-sparkle 0.8s ease-out infinite;
}
.madcop-loader-sparkle:nth-child(2) { top: 10%; left: 10%; animation-delay: 0.1s; }
.madcop-loader-sparkle:nth-child(3) { top: 10%; right: 10%; animation-delay: 0.3s; }
.madcop-loader-sparkle:nth-child(4) { bottom: 20%; left: 5%; animation-delay: 0.5s; }
.madcop-loader-sparkle:nth-child(5) { bottom: 20%; right: 5%; animation-delay: 0.7s; }
@keyframes madcop-sparkle {
  0%   { opacity: 0; transform: scale(0.5) translateY(0); }
  50%  { opacity: 1; transform: scale(1.2) translateY(-6px); }
  100% { opacity: 0; transform: scale(0.5) translateY(-12px); }
}
`
