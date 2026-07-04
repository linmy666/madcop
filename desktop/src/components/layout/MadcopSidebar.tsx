// v3.0 — MadCop sidebar.
//
// The previous Sidebar (Sidebar.tsx, ~2000 lines) was a stack of
// section components with hover-revealed filters, accordion sessions,
// draggable rails, and a context menu. The new one is much more
// honest: a flat list of nav links, a session switcher, and a
// search field. Visually it's narrower, sharper, with a 3px
// cyan rail on the active item instead of a tinted background.

import { useState } from 'react'
import { madcop, icon } from '../../foundations/tokens'
import { useMadcopTheme } from '../../foundations/theme'

export type MadcopSection =
  | 'chat' | 'threads' | 'skills' | 'memory' | 'agents'
  | 'workflow' | 'design' | 'trace' | 'teams'
  | 'doctor' | 'diagnostics' | 'activity' | 'schedule'
  | 'browser' | 'terminal'
  | 'settings'

export interface MadcopNavLink {
  id: MadcopSection
  label: string
  glyph: string  // ASCII / system icon
  group: 'work' | 'tools' | 'system'
}

const NAV: MadcopNavLink[] = [
  { id: 'chat',        label: '会话',   glyph: icon.chat,       group: 'work' },
  { id: 'threads',     label: '主题',   glyph: icon.threads,    group: 'work' },
  { id: 'skills',      label: '技能',   glyph: icon.skills,     group: 'work' },
  { id: 'memory',      label: '记忆',   glyph: icon.memory,     group: 'work' },
  { id: 'agents',      label: '代理',   glyph: icon.agent,      group: 'work' },
  { id: 'workflow',    label: '工作流', glyph: icon.workflow,   group: 'tools' },
  { id: 'design',      label: '设计',   glyph: icon.design,     group: 'tools' },
  { id: 'trace',       label: '追踪',   glyph: icon.trace,      group: 'tools' },
  { id: 'teams',       label: '团队',   glyph: icon.teams,       group: 'tools' },
  { id: 'browser',     label: '浏览器', glyph: icon.browser,     group: 'system' },
  { id: 'terminal',    label: '终端',   glyph: icon.terminal,    group: 'system' },
  { id: 'doctor',      label: '诊断',   glyph: icon.doctor,      group: 'system' },
  { id: 'diagnostics', label: '日志',   glyph: icon.diagnostics, group: 'system' },
  { id: 'activity',    label: '活动',   glyph: icon.activity,    group: 'system' },
  { id: 'schedule',    label: '计划',   glyph: icon.schedule,    group: 'system' },
  { id: 'settings',    label: '设置',   glyph: icon.settings,    group: 'system' },
]

const GROUP_LABELS = { work: '工作区', tools: '工具', system: '系统' } as const

interface MadcopSidebarProps {
  active: MadcopSection
  onSelect: (id: MadcopSection) => void
  collapsed?: boolean
}

export function MadcopSidebar({ active, onSelect, collapsed }: MadcopSidebarProps) {
  useMadcopTheme()  // re-render on theme change
  const [query, setQuery] = useState('')

  const q = query.trim().toLowerCase()
  const filtered = q ? NAV.filter((n) => n.label.toLowerCase().includes(q)) : NAV

  const groups: Array<'work' | 'tools' | 'system'> = ['work', 'tools', 'system']

  return (
    <div style={{
      width: '100%', height: '100%', display: 'flex', flexDirection: 'column',
      background: 'var(--madcop-panel-raised)',
      fontSize: madcop.type.size.body,
    }}>
      {/* Brand mark */}
      <div style={{
        padding: `${madcop.space[3]} ${madcop.space[4]}`,
        borderBottom: `1.5px solid var(--madcop-line)`,
        display: 'flex', alignItems: 'center', gap: madcop.space[2],
        minHeight: madcop.layout.titlebarHeight,
      }}>
        <div style={{
          width: 20, height: 20, background: 'var(--madcop-accent)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--madcop-accent-ink)', fontWeight: 700, fontSize: 11,
          fontFamily: madcop.type.family.mono,
        }}>M</div>
        {!collapsed && (
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
            <span style={{ fontWeight: 600, fontSize: madcop.type.size.base, color: 'var(--madcop-ink)' }}>MadCop</span>
            <span style={{ fontSize: 10, color: 'var(--madcop-ink-muted)', fontFamily: madcop.type.family.mono }}>v3.0 · engineering</span>
          </div>
        )}
      </div>

      {/* Search */}
      {!collapsed && (
        <div style={{ padding: madcop.space[3] }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: madcop.space[2],
            padding: `6px 10px`, border: `1.5px solid var(--madcop-line)`,
            background: 'var(--madcop-panel-sunken)',
          }}>
            <span style={{ color: 'var(--madcop-ink-muted)', fontSize: 13 }}>{icon.find}</span>
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索面板..."
              style={{
                border: 'none', outline: 'none', background: 'transparent',
                flex: 1, fontSize: madcop.type.size.body, color: 'var(--madcop-ink)',
              }}
            />
          </div>
        </div>
      )}

      {/* Nav groups */}
      <nav style={{ flex: 1, overflowY: 'auto', padding: `${madcop.space[2]} 0` }}>
        {groups.map((g) => {
          const items = filtered.filter((n) => n.group === g)
          if (items.length === 0) return null
          return (
            <div key={g} style={{ marginBottom: madcop.space[3] }}>
              {!collapsed && (
                <div className="madcop-eyebrow" style={{ padding: `0 ${madcop.space[4]}`, marginBottom: 6 }}>
                  {GROUP_LABELS[g]}
                </div>
              )}
              {items.map((link) => {
                const isActive = active === link.id
                return (
                  <button
                    key={link.id}
                    onClick={() => onSelect(link.id)}
                    title={collapsed ? link.label : undefined}
                    style={{
                      display: 'flex', alignItems: 'center', gap: madcop.space[3],
                      width: '100%',
                      padding: collapsed
                        ? `${madcop.space[2]} 0`
                        : `6px ${madcop.space[4]}`,
                      border: 'none', cursor: 'pointer', textAlign: 'left',
                      background: 'transparent', position: 'relative',
                      color: isActive ? 'var(--madcop-accent)' : 'var(--madcop-ink-body)',
                      fontWeight: isActive ? 600 : 400,
                      fontSize: madcop.type.size.body,
                      justifyContent: collapsed ? 'center' : 'flex-start',
                    }}
                    onMouseEnter={(e) => {
                      if (!isActive) e.currentTarget.style.background = 'var(--madcop-panel-sunken)'
                    }}
                    onMouseLeave={(e) => {
                      if (!isActive) e.currentTarget.style.background = 'transparent'
                    }}
                  >
                    {/* Active rail */}
                    {isActive && (
                      <span style={{
                        position: 'absolute', left: 0, top: 0, bottom: 0,
                        width: 3, background: 'var(--madcop-accent)',
                      }} />
                    )}
                    <span style={{
                      width: 16, fontSize: 14, textAlign: 'center',
                      fontFamily: madcop.type.family.mono,
                      opacity: isActive ? 1 : 0.7,
                    }}>{link.glyph}</span>
                    {!collapsed && <span>{link.label}</span>}
                  </button>
                )
              })}
            </div>
          )
        })}
      </nav>
    </div>
  )
}
