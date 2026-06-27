'use client';

interface ContextUsageIndicatorProps {
  /** Usage fraction 0–1 (clamped). */
  used?: number;
  /** Optional label for the max capacity in tokens. */
  maxTokens?: number;
}

function getColor(pct: number): string {
  if (pct >= 0.8) return 'var(--danger)';
  if (pct >= 0.5) return 'var(--warn)';
  return 'var(--accent)';
}

function formatTokens(n: number): string {
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return `${n}`;
}

export default function ContextUsageIndicator({
  used,
  maxTokens,
}: ContextUsageIndicatorProps) {
  const pct = Math.min(1, Math.max(0, used ?? 0));
  const color = getColor(pct);

  return (
    <div className="flex items-center gap-2 px-1 text-[11px] text-[var(--text-3)]">
      <span className="font-medium whitespace-nowrap">怒气值</span>

      {/* Progress bar */}
      <div
        className="relative h-1.5 w-20 overflow-hidden rounded-full"
        style={{ background: 'var(--surface-3)' }}
      >
        <div
          className="absolute left-0 top-0 h-full rounded-full transition-all duration-300"
          style={{
            width: `${pct * 100}%`,
            background: color,
          }}
        />
      </div>

      {/* Percentage label */}
      <span style={{ color }} className="font-mono font-medium tabular-nums">
        {Math.round(pct * 100)}%
      </span>

      {/* Optional token count */}
      {maxTokens && (
        <span className="text-[var(--text-faint)]">
          {formatTokens(Math.round(pct * maxTokens))}/{formatTokens(maxTokens)}
        </span>
      )}
    </div>
  );
}
