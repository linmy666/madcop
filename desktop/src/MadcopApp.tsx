// v3.0 — MadCop main app shell — full integration.
//
// This is the new top-level entry that the Electron main.cjs will
// render when [data-madcop-shell=v3] is set. It is independent of
// the old AppShell.tsx and is wired to:
//   - the new Madcop shell + sidebar + titlebar + tabstrip + statusbar
//   - the new Madcop theme provider
//   - the same backend API (GET /api/sessions, etc) so the chat
//     continues to work without backend changes
//
// The legacy AppShell.tsx is left untouched and remains the default
// until you flip the data attribute. This is the safe-migration
// entry point.

import { useState, useEffect, useCallback } from 'react'
import { MadcopShell } from './components/layout/MadcopShell'
import { MadcopSidebar, type MadcopSection } from './components/layout/MadcopSidebar'
import { MadcopTitlebar } from './components/layout/MadcopTitlebar'
import { MadcopTabstrip, type MadcopTab, type MadcopTabKind } from './components/layout/MadcopTabstrip'
import { MadcopStatusbar } from './components/layout/MadcopStatusbar'
import { useMadcopTheme, madcop } from './foundations/theme'
import { getApiUrl } from './api/client'
import { ActiveSession } from './pages/ActiveSession'
import { EmptySession } from './pages/EmptySession'
import { DesignPage } from './pages/DesignPage'

interface MadcopTabInternal {
  id: string
  kind: MadcopTabKind
  title: string
  dirty?: boolean
  busy?: boolean
}

function sectionToKind(sec: MadcopSection): MadcopTabKind {
  if (sec === 'design') return 'design'
  if (sec === 'workflow') return 'workflow'
  if (sec === 'trace') return 'trace'
  return 'chat'
}

export function MadcopApp() {
  useMadcopTheme()  // mount theme provider

  const [section, setSection] = useState<MadcopSection>('chat')
  const [tabs, setTabs] = useState<MadcopTabInternal[]>([])
  const [activeTabId, setActiveTabId] = useState<string | null>(null)
  const [projectName, setProjectName] = useState<string>('无标题项目')

  // Sidebar section click → set section + open a default tab
  const handleSection = useCallback((s: MadcopSection) => {
    setSection(s)
    if (s === 'design') {
      // Open design tab
      const id = `design-${Date.now()}`
      setTabs((prev) => [...prev, { id, kind: 'design', title: '设计工具' }])
      setActiveTabId(id)
    } else if (s === 'chat' && tabs.filter((t) => t.kind === 'chat').length === 0) {
      // New chat tab
      const id = `chat-${Date.now()}`
      setTabs((prev) => [...prev, { id, kind: 'chat', title: '新会话' }])
      setActiveTabId(id)
    } else {
      setActiveTabId(null)
    }
  }, [tabs])

  // Close tab
  const handleCloseTab = useCallback((id: string) => {
    setTabs((prev) => prev.filter((t) => t.id !== id))
    setActiveTabId((cur) => (cur === id ? null : cur))
  }, [])

  // Command palette handlers
  const handleCommand = useCallback((cmd: string) => {
    if (cmd.startsWith('appearance:')) {
      const next = cmd.split(':')[1] as any
      // theme switching is handled via setAppearance in the real app
      console.log('[madcop] appearance switch', next)
      document.documentElement.setAttribute('data-madcop-theme', next)
    } else if (cmd === 'settings:open') {
      setSection('settings')
    } else {
      // Treat as chat input — open a chat tab and seed the prompt
      const id = `chat-${Date.now()}`
      setTabs((prev) => [...prev, { id, kind: 'chat', title: cmd.slice(0, 16), dirty: true }])
      setActiveTabId(id)
    }
  }, [])

  const activeTab = tabs.find((t) => t.id === activeTabId)
  const showChat = section === 'chat' && activeTab?.kind === 'chat'
  const showDesign = section === 'design' && activeTab?.kind === 'design'
  const showEmpty = !activeTab

  return (
    <MadcopShell
      titlebar={<MadcopTitlebar projectName={projectName} onCommand={handleCommand} />}
      sidebar={<MadcopSidebar active={section} onSelect={handleSection} />}
      tabstrip={
        <MadcopTabstrip
          tabs={tabs as MadcopTab[]}
          active={activeTabId}
          onSelect={setActiveTabId}
          onClose={handleCloseTab}
        />
      }
      statusbar={<MadcopStatusbar />}
    >
      {showDesign ? <DesignPage /> : showChat ? <ActiveSession /> : <EmptySession />}
    </MadcopShell>
  )
}
