// v3.0 — MadCop Card.
//
// Hairline border, square corners, optional eyebrow title + footer
// slot. No shadow, no gradient. Use <MadcopCard.Section> to split
// the body into horizontal bands.

import { type ReactNode } from 'react'
import { madcop } from '../../foundations/tokens'

export interface MadcopCardProps {
  title?: ReactNode
  eyebrow?: ReactNode
  footer?: ReactNode
  children: ReactNode
  pad?: boolean
  tone?: 'default' | 'subtle' | 'accent' | 'danger'
}

export function MadcopCard({ title, eyebrow, footer, children, pad = true, tone = 'default' }: MadcopCardProps) {
  const bg = tone === 'subtle' ? 'var(--madcop-panel-sunken)'
    : tone === 'accent' ? 'var(--madcop-accent-subtle)'
    : tone === 'danger' ? 'var(--madcop-danger-subtle)'
    : 'var(--madcop-panel-raised)'
  return (
    <div style={{
      border: `1.5px solid var(--madcop-line)`,
      background: bg,
    }}>
      {(title || eyebrow) && (
        <div style={{
          padding: `8px ${madcop.space[4]}`,
          borderBottom: `1.5px solid var(--madcop-line)`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div>
            {eyebrow && <div className="madcop-eyebrow" style={{ marginBottom: 2 }}>{eyebrow}</div>}
            {title && <div style={{ fontSize: madcop.type.size.base, fontWeight: 600, color: 'var(--madcop-ink)' }}>{title}</div>}
          </div>
        </div>
      )}
      <div style={{ padding: pad ? madcop.space[4] : 0 }}>{children}</div>
      {footer && (
        <div style={{
          padding: `8px ${madcop.space[4]}`,
          borderTop: `1.5px solid var(--madcop-line)`,
          color: 'var(--madcop-ink-muted)', fontSize: madcop.type.size.micro,
        }}>{footer}</div>
      )}
    </div>
  )
}

export function MadcopCardSection({ children }: { children: ReactNode }) {
  return (
    <div style={{ padding: madcop.space[4], borderTop: `1.5px solid var(--madcop-line)` }}>
      {children}
    </div>
  )
}

MadcopCard.Section = MadcopCardSection
