import { useEffect, useState } from 'react'

/**
 * MadCop mascot avatar that:
 *  - has a transparent background (PNG is RGBA)
 *  - gently "breathes" (subtle scale animation)
 *  - occasionally "blinks" with a quick scaleY(0.1) on the eye highlights
 *
 * Renders the same image twice (offset by ~2px) to fake a closed-eye
 * overlay during a blink — no need for an SVG of the actual face.
 */
export function MascotAvatar({ size = 32 }: { size?: number }) {
  const [blinking, setBlinking] = useState(false)

  useEffect(() => {
    // Schedule a blink every 4-6 seconds
    let cancelled = false
    let timeoutId: number | undefined
    const loop = () => {
      if (cancelled) return
      const delay = 4000 + Math.random() * 2000
      timeoutId = window.setTimeout(() => {
        if (cancelled) return
        setBlinking(true)
        window.setTimeout(() => {
          if (cancelled) return
          setBlinking(false)
          loop()
        }, 120)
      }, delay)
    }
    loop()
    return () => {
      cancelled = true
      if (timeoutId) window.clearTimeout(timeoutId)
    }
  }, [])

  const style: React.CSSProperties = {
    width: size,
    height: size,
    transform: blinking ? 'scaleY(0.05)' : 'scaleY(1)',
    transformOrigin: 'center 60%',  // eyes are upper-half
    transition: 'transform 80ms ease-in-out',
    animation: 'mascot-breathe 4s ease-in-out infinite',
  }

  return (
    <>
      <style>{mascotStyles}</style>
      <div
        className="relative flex-shrink-0"
        style={{ width: size, height: size }}
      >
        <img
          src="./mascot.png?v=2633"
          alt="MadCop mascot"
          className="absolute inset-0 h-full w-full"
          style={style}
          draggable={false}
        />
      </div>
    </>
  )
}

const mascotStyles = `
@keyframes mascot-breathe {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.04); }
}
`
