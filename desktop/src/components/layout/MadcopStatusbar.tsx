// v3.0 — MadCop status bar.
//
// 28px height, three-zone layout (left: model+provider, center:
// context, right: tokens + version). Replaces StatusBar.

import { madcop } from '../../foundations/tokens'

interface MadcopStatusbarProps {
  provider?: string
  model?: string
  sessionId?: string
  tokensUsed?: number
  tokensTotal?: number
  version?: string
}

export function MadcopStatusbar({
  provider = 'sensenova', model = 'glm-5.2',
  sessionId, tokensUsed, tokensTotal, version = 'v3.0.0',
}: MadcopStatusbarProps) {
  const tokenPct = tokensTotal ? Math.min(100, ((tokensUsed || 0) / tokensTotal) * 100) : null
  return (
    <div style={{
      width: '100%', height: '100%',
      display: 'flex', alignItems: 'center',
      padding: `0 ${madcop.space[3]}`,
      gap: madcop.space[3],
      background: 'var(--madcop-panel-raised)',
      color: 'var(--madcop-ink-muted)',
      fontSize: madcop.type.size.micro,
      fontFamily: madcop.type.family.mono,
    }}>
      <span style={{ color: 'var(--madcop-success)' }}>●</span>
      <span>{provider}</span>
      <span style={{ color: 'var(--madcop-line)' }}>·</span>
      <span>{model}</span>
      {sessionId && (
        <>
          <span style={{ color: 'var(--madcop-line)' }}>·</span>
          <span title={sessionId}>session {sessionId.slice(0, 8)}</span>
        </>
      )}
      <div style={{ flex: 1 }} />
      {tokenPct !== null && (
        <span title={`${tokensUsed} / ${tokensTotal} tokens`}>
          tokens {(tokensUsed! / 1000).toFixed(1)}k / {(tokensTotal! / 1000).toFixed(0)}k
        </span>
      )}
      <span style={{ color: 'var(--madcop-line)' }}>·</span>
      <span>madcop {version}</span>
    </div>
  )
}
