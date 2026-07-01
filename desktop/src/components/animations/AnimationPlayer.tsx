import React from 'react'

type AnimationName = 'clover' | 'ripple' | 'spinner'

type Props = {
  name: AnimationName
  className?: string
  ariaLabel?: string
  loop?: boolean
}

const VIDEO_SRC: Record<AnimationName, string> = {
  clover: './animations/clover.mp4',
  ripple: './animations/ripple.mp4',
  spinner: './animations/spinner.mp4',
}

const ARIA_LABEL: Record<AnimationName, string> = {
  clover: 'MadCop is ready',
  ripple: 'MadCop is thinking',
  spinner: 'MadCop is working',
}

export function AnimationPlayer({ name, className, ariaLabel, loop = true }: Props) {
  const [failed, setFailed] = React.useState(false)
  const label = ariaLabel ?? ARIA_LABEL[name]

  if (failed) {
    return <SpinnerFallback name={name} className={className} label={label} />
  }

  return (
    <video
      className={className}
      src={VIDEO_SRC[name]}
      autoPlay
      loop={loop}
      muted
      playsInline
      aria-label={label}
      onError={() => setFailed(true)}
    />
  )
}

function SpinnerFallback({ name, className, label }: { name: AnimationName; className?: string; label: string }) {
  if (name === 'clover') {
    return (
      <div className={className} role="img" aria-label={label} style={{
        width: '100%', height: '100%',
        background: 'radial-gradient(circle at 50% 50%, #5EEAD4 0%, #14B8A6 35%, #0F766E 60%, transparent 75%)',
        animation: 'madcop-clover-pulse 2.5s ease-in-out infinite',
      }} />
    )
  }
  if (name === 'ripple') {
    return (
      <div className={className} role="img" aria-label={label} style={{
        width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', position: 'relative',
      }}>
        <div style={{ width: '40%', height: '40%', border: '2px solid #14B8A6', borderRadius: '50%', animation: 'madcop-ripple-out 1.6s ease-out infinite', position: 'absolute' }} />
        <div style={{ width: '40%', height: '40%', border: '2px solid #5EEAD4', borderRadius: '50%', animation: 'madcop-ripple-out 1.6s ease-out 0.4s infinite', position: 'absolute' }} />
      </div>
    )
  }
  return (
    <div className={className} role="img" aria-label={label} style={{
      width: '100%', height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
    }}>
      {[0, 1, 2].map((i) => (
        <div key={i} style={{
          width: 8, height: 8, background: '#14B8A6', borderRadius: '50%',
          animation: `madcop-dot-bounce 1.2s ${i * 0.15}s ease-in-out infinite`,
        }} />
      ))}
    </div>
  )
}

let KEYFRAMES_INJECTED = false
function injectKeyframes() {
  if (KEYFRAMES_INJECTED || typeof document === 'undefined') return
  KEYFRAMES_INJECTED = true
  const id = 'madcop-animation-keyframes'
  if (document.getElementById(id)) return
  const style = document.createElement('style')
  style.id = id
  style.textContent = `
@keyframes madcop-clover-pulse {
  0%, 100% { transform: scale(1); opacity: 0.85; }
  50%      { transform: scale(1.08); opacity: 1; }
}
@keyframes madcop-ripple-out {
  0%   { transform: scale(0.4); opacity: 1; }
  100% { transform: scale(1.4); opacity: 0; }
}
@keyframes madcop-dot-bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.6; }
  40%           { transform: translateY(-6px); opacity: 1; }
}
`
  document.head.appendChild(style)
}

export function useMadcopAnimations() {
  React.useEffect(() => {
    injectKeyframes()
  }, [])
}
