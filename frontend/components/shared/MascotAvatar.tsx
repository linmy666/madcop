'use client';

import { useEffect, useState } from 'react';
import { BRAND } from '@/lib/i18n';

interface Props {
  /** Size in pixels. */
  size?: number;
  /** Rounded corner radius. */
  rounded?: boolean;
  /** When true (default), the avatar plays a "blink" loop using
   *  the video asset every 8s for ~2s. Desktop only. */
  animated?: boolean;
  className?: string;
}

/**
 * Unified mascot avatar — shared between web + desktop.
 *
 * On desktop the assets live at `/public/mascot*.mp4` so we can
 * import them via Vite's asset pipeline (fast, no network).
 *
 * On web we fall back to the PNG served by the FastAPI server.
 */
export function MascotAvatar({ size = 28, rounded = true, animated = true, className }: Props) {
  const [phase, setPhase] = useState<'idle' | 'blink' | 'nod'>('idle');
  const [locale] = useState<'en' | 'zh'>('en');
  // Detect language from html lang attribute (set by app/layout.tsx)
  useEffect(() => {
    if (typeof document !== 'undefined') {
      const lang = document.documentElement.lang;
      if (lang === 'zh-CN' || lang === 'zh') setLocale('zh');
      else setLocale('en');
    }
  }, []);

  // Periodic blink loop — every 8s, 2s of video
  useEffect(() => {
    if (!animated) return;
    const cycle = () => {
      setPhase('blink');
      setTimeout(() => setPhase('idle'), 2000);
    };
    const id = setInterval(cycle, 8000);
    // First cycle kicks off after 4s
    const initial = setTimeout(cycle, 4000);
    return () => {
      clearInterval(id);
      clearTimeout(initial);
    };
  }, [animated]);

  const radius = rounded ? '50%' : '6px';
  const brand = BRAND[locale];

  return (
    <span
      className={className}
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        borderRadius: radius,
        overflow: 'hidden',
        position: 'relative',
        flexShrink: 0,
      }}
      title={brand.name}
    >
      {/* Static image — always visible (acts as poster + fallback) */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/mascot.png"
        alt={brand.name}
        width={size}
        height={size}
        style={{
          position: 'absolute',
          inset: 0,
          width: '100%',
          height: '100%',
          objectFit: 'cover',
        }}
      />
      {/* Video overlay — only show during active animation phase */}
      {animated && (phase === 'blink' || phase === 'nod') && (
        <video
          src={phase === 'blink' ? '/mascot-blink.mp4' : '/mascot-nod.mp4'}
          autoPlay
          muted
          playsInline
          width={size}
          height={size}
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
          }}
        />
      )}
    </span>
  );
}
