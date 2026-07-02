import { useEffect, useState } from 'react'

/**
 * MadCopLoader — a clean, on-brand loading animation that replaces
 * the abstract clover.mp4 / ripple.mp4 videos.
 *
 * Three states: 'ready' (idle, mascot scanning), 'thinking'
 * (mascot working), 'working' (mascot executing a tool call).
 *
 * Uses inline SVG (no external assets, no videos) so it renders
 * instantly, scales perfectly at any size, and never breaks.
 *
 * Design language:
 *   - Brand color: #14B8A6 (teal, the MadCop accent)
 *   - Hand-drawn detective / inspector motif (hat + magnifying glass)
 *   - Wobble animation: subtle 1.2px translate + 1deg rotate
 *     gives a "hand-sketched" feel without being abstract
 *   - Stage labels: 需求调研 / 上网搜索 / 写代码 / 等等 (i18n)
 */
export type MadCopState = 'ready' | 'thinking' | 'working'

type Props = {
  state: MadCopState
  className?: string
  size?: number
  label?: string  // override the default stage label
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

export function MadCopLoader({
  state,
  className = '',
  size = 80,
  label,
}: Props) {
  const [rotation, setRotation] = useState(0)

  // Subtle "scanning" rotation when ready (mascot scans left/right)
  useEffect(() => {
    if (state !== 'ready') return
    const t = setInterval(() => {
      setRotation((r) => (r + 1) % 360)
    }, 80)
    return () => clearInterval(t)
  }, [state])

  return (
    <div
      role="img"
      aria-label={label ?? STAGE_LABELS[state]}
      className={`inline-flex flex-col items-center gap-3 ${className}`}
      style={{ width: size + 32 }}
    >
      <div
        className="relative"
        style={{
          width: size,
          height: size,
          animation:
            state === 'thinking'
              ? 'madcop-loader-think 1.2s ease-in-out infinite'
              : state === 'working'
                ? 'madcop-loader-work 0.8s ease-in-out infinite'
                : 'madcop-loader-breathe 3.5s ease-in-out infinite',
        }}
      >
        <svg
          viewBox="0 0 100 100"
          width={size}
          height={size}
          fill="none"
          stroke="#14B8A6"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          {/* Outer ring (brand circle) — opacity pulses with state */}
          <circle
            cx="50"
            cy="50"
            r="46"
            stroke="#14B8A6"
            strokeWidth="1.5"
            opacity={state === 'ready' ? 0.3 : 0.5}
            strokeDasharray={state === 'working' ? '4 4' : undefined}
          />

          {/* Detective hat (fedora) — fixed pose */}
          <ellipse cx="50" cy="22" rx="22" ry="3" fill="#2c3e50" stroke="#2c3e50" />
          <path
            d="M 28 22 Q 28 8 50 8 Q 72 8 72 22 Z"
            fill="#2c3e50"
            stroke="#2c3e50"
          />
          <path d="M 32 15 Q 50 13 68 15" stroke="#14B8A6" strokeWidth="1.2" fill="none" />

          {/* Head (round) */}
          <circle cx="50" cy="48" r="18" stroke="#2c3e50" strokeWidth="2" />

          {/* Eyes — blink occasionally in ready state */}
          <g
            style={{
              transform: 'scaleY(1)',
              transformOrigin: 'center',
              animation: state === 'ready' ? 'madcop-blink 5s ease-in-out infinite' : 'none',
            }}
          >
            <circle cx="40" cy="46" r="2" fill="#2c3e50" />
            <circle cx="60" cy="46" r="2" fill="#2c3e50" />
          </g>

          {/* Smile */}
          <path
            d="M 42 56 Q 50 60 58 56"
            stroke="#2c3e50"
            strokeWidth="1.5"
            fill="none"
          />

          {/* Body / coat (V shape) */}
          <path d="M 50 66 L 50 88" stroke="#2c3e50" strokeWidth="2" />
          <path d="M 38 76 L 50 66 L 62 76" stroke="#2c3e50" strokeWidth="2" />

          {/* Magnifying glass — moves based on state */}
          <g
            style={{
              transformOrigin: '70px 80px',
              animation:
                state === 'ready'
                  ? `rotate(${rotation}deg)`
                  : state === 'thinking'
                    ? 'madcop-glass-pendulum 1.6s ease-in-out infinite'
                    : 'madcop-glass-shake 0.4s ease-in-out infinite',
              transition: 'transform 0.3s',
            }}
          >
            <circle cx="78" cy="84" r="9" fill="#dbeafe" stroke="#14B8A6" strokeWidth="2" />
            <circle cx="78" cy="84" r="6.5" stroke="#14B8A6" strokeWidth="1" fill="none" opacity="0.5" />
            <ellipse cx="74.5" cy="80.5" rx="2.5" ry="1.5" fill="white" opacity="0.7" />
            <line x1="85" y1="91" x2="91" y2="97" stroke="#2c3e50" strokeWidth="2.5" />
          </g>
        </svg>
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

      <style>{madcopLoaderStyles}</style>
    </div>
  )
}

const madcopLoaderStyles = `
@keyframes madcop-loader-breathe {
  0%, 100% { transform: scale(1); }
  50%      { transform: scale(1.04); }
}
@keyframes madcop-loader-think {
  0%, 100% { transform: scale(1) rotate(0deg); }
  25%      { transform: scale(1.05) rotate(-1.5deg); }
  75%      { transform: scale(1.05) rotate(1.5deg); }
}
@keyframes madcop-loader-work {
  0%, 100% { transform: scale(1); }
  50%      { transform: scale(0.96); }
}
@keyframes madcop-blink {
  0%, 92%, 100% { transform: scaleY(1); }
  94%, 98%   { transform: scaleY(0.05); }
}
@keyframes madcop-glass-pendulum {
  0%, 100% { transform: rotate(-15deg); }
  50%      { transform: rotate(15deg); }
}
@keyframes madcop-glass-shake {
  0%, 100% { transform: translate(0, 0) rotate(0deg); }
  25%      { transform: translate(-0.5px, 0.5px) rotate(-2deg); }
  50%      { transform: translate(0.5px, -0.5px) rotate(0deg); }
  75%      { transform: translate(-0.3px, 0.3px) rotate(1deg); }
}
`
