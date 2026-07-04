// v3.0 — MadCop tab strip.
//
// The previous TabBar held the full tab state machine (draggable
// tab chips, close buttons, +/- for new tabs, activity dots, etc).
// The new one is a simple horizontal list of open "surfaces":
// chat sessions, design pages, workflow editors. Compact 36px
// height, no shadows, separator lines between tabs.

import { madcop, icon } from '../../foundations/tokens'

export type MadcopTabKind = 'chat' | 'design' | 'workflow' | 'trace'

export interface MadcopTab {
  id: string
  kind: MadcopTabKind
  title: string
  dirty?: boolean
  busy?: boolean
}

interface MadcopTabstripProps {
  tabs: MadcopTab[]
  active: string | null
  onSelect: (id: string) => void
  onClose: (id: string) => void
}

export function MadcopTabstrip({ tabs, active, onSelect, onClose }: MadcopTabstripProps) {
  if (tabs.length === 0) {
    return (
      <div style={{
        width: '100%', height: '100%',
        display: 'flex', alignItems: 'center',
        padding: `0 ${madcop.space[4]}`,
        color: 'var(--madcop-ink-muted)', fontSize: madcop.type.size.caption,
        fontFamily: madcop.type.family.mono,
      }}>
        — 无打开的标签 —
      </div>
    )
  }

  return (
    <div style={{
      width: '100%', height: '100%',
      display: 'flex', alignItems: 'stretch',
      overflowX: 'auto', overflowY: 'hidden',
    }}>
      {tabs.map((tab) => {
        const isActive = active === tab.id
        return (
          <div
            key={tab.id}
            onClick={() => onSelect(tab.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: madcop.space[2],
              padding: `0 ${madcop.space[3]}`,
              borderRight: `1.5px solid var(--madcop-line)`,
              background: isActive ? 'var(--madcop-panel)' : 'var(--madcop-panel-raised)',
              color: isActive ? 'var(--madcop-ink)' : 'var(--madcop-ink-body)',
              cursor: 'pointer', position: 'relative',
              fontSize: madcop.type.size.body,
              minWidth: 120, maxWidth: 220,
              borderBottom: isActive
                ? `2px solid var(--madcop-accent)`
                : '2px solid transparent',
            }}
          >
            {/* Kind badge */}
            <span style={{
              fontSize: 10, fontFamily: madcop.type.family.mono,
              color: isActive ? 'var(--madcop-accent)' : 'var(--madcop-ink-muted)',
              textTransform: 'uppercase', letterSpacing: madcop.type.tracking.wide,
            }}>{tab.kind}</span>
            <span style={{
              flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              fontWeight: isActive ? 500 : 400,
            }}>{tab.title}</span>
            {tab.busy && (
              <span style={{
                width: 6, height: 6, borderRadius: '50%',
                background: 'var(--madcop-warn)',
                animation: 'madcop-blink 1s infinite',
              }} />
            )}
            {tab.dirty && <span style={{ color: 'var(--madcop-warn)', fontSize: 10 }}>●</span>}
            <button
              onClick={(e) => { e.stopPropagation(); onClose(tab.id) }}
              style={{
                background: 'transparent', border: 'none', cursor: 'pointer',
                color: 'var(--madcop-ink-muted)', fontSize: 14,
                padding: 0, lineHeight: 1,
              }}
            >{icon.close}</button>
          </div>
        )
      })}
    </div>
  )
}
