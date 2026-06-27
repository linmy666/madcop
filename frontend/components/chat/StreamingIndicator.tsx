'use client';

import { useEffect, useState } from 'react';

interface StreamingIndicatorProps {
  /** true while we have not yet received any content token. */
  waitingForFirstToken: boolean;
  /** Set once streaming starts; resets timer. */
  active: boolean;
}

export default function StreamingIndicator({
  waitingForFirstToken,
  active,
}: StreamingIndicatorProps) {
  const [elapsed, setElapsed] = useState(0);
  const [tokenEst, setTokenEst] = useState(0);

  useEffect(() => {
    if (!active) {
      setElapsed(0);
      setTokenEst(0);
      return;
    }

    const startTime = Date.now();
    const interval = setInterval(() => {
      const secs = (Date.now() - startTime) / 1000;
      setElapsed(secs);
      // rough estimate: ~15 tok/s typical streaming speed
      setTokenEst(Math.floor(secs * 15));
    }, 100);

    return () => clearInterval(interval);
  }, [active]);

  if (!active) return null;

  return (
    <div className="flex items-center gap-2 px-1 py-1 text-[11px] text-[var(--text-3)]">
      {waitingForFirstToken ? (
        <>
          {/* Pulsing dots */}
          <span className="flex items-center gap-1">
            <span
              className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--accent)]"
              style={{ animation: 'pulse-dot 1.4s infinite' }}
            />
            <span
              className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--accent)]"
              style={{ animation: 'pulse-dot 1.4s infinite', animationDelay: '.2s' }}
            />
            <span
              className="inline-block h-1.5 w-1.5 rounded-full bg-[var(--accent)]"
              style={{ animation: 'pulse-dot 1.4s infinite', animationDelay: '.4s' }}
            />
          </span>
          <span className="shimmer-text font-medium">等待响应…</span>
        </>
      ) : (
        <>
          <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-[var(--accent)]" />
          <span>
            {elapsed.toFixed(1)}s · ~{tokenEst} tokens
          </span>
        </>
      )}
    </div>
  );
}
