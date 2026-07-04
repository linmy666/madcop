// v3.0 — MadCop: a fresh shell skeleton.
//
// This replaces the previous AppShell. The new component:
//  - takes a `sidebar`, `titlebar`, `tabstrip`, `statusbar` slot
//  - reads the appearance from the new Madcop theme provider
//  - uses the madcop-* CSS variable namespace (not --color-*)
//
// The legacy AppShell is still imported by tests; we keep it
// around for now and route the live app to this one.

import { useMadcopTheme } from '../../foundations/theme'
import { madcop } from '../../foundations/tokens'
import type { ReactNode } from 'react'

interface MadcopShellProps {
  titlebar?: ReactNode
  sidebar?: ReactNode
  tabstrip?: ReactNode
  statusbar?: ReactNode
  children?: ReactNode
  sidebarCollapsed?: boolean
}

export function MadcopShell({
  titlebar, sidebar, tabstrip, statusbar, children, sidebarCollapsed,
}: MadcopShellProps) {
  // We read the hook so the shell re-renders when theme changes
  useMadcopTheme()

  const s = sidebarCollapsed
    ? { ...madcop.layout, sidebar: `${madcop.layout.sidebarCollapsed}px` }
    : madcop.layout

  const gridStyle: React.CSSProperties = {
    display: 'grid',
    gridTemplateRows: `${s.titlebarHeight}px ${s.tabstripHeight}px 1fr ${s.statusbarHeight}px`,
    gridTemplateColumns: `${s.sidebarWidth}px 1fr`,
    gridTemplateAreas: sidebarCollapsed
      ? `"title title" "side tabstrip" "side main" "status status"`
      : `"title title" "side tabstrip" "side main" "status status"`,
    height: '100vh',
    width: '100vw',
    overflow: 'hidden',
  }

  return (
    <div className="madcop-shell" style={gridStyle}>
      {titlebar && <header className="madcop-shell__titlebar">{titlebar}</header>}
      {sidebar && <aside className="madcop-shell__sidebar">{sidebar}</aside>}
      {tabstrip && <nav className="madcop-shell__tabstrip" style={{
        borderBottom: '1.5px solid var(--madcop-line)',
        background: 'var(--madcop-panel-raised)',
        display: 'flex',
        alignItems: 'center',
        overflow: 'hidden',
      }}>{tabstrip}</nav>}
      <main className="madcop-shell__main">{children}</main>
      {statusbar && <footer className="madcop-shell__statusbar">{statusbar}</footer>}
    </div>
  )
}
