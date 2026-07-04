import { useEffect, useState } from 'react'
import { AppShell } from './components/layout/AppShell'
import { MadcopApp } from './MadcopApp'
import { useScheduledTaskDesktopNotifications } from './hooks/useScheduledTaskDesktopNotifications'
import { installDesktopNotificationNavigation } from './lib/desktopNotificationNavigation'

const FLAG = 'madcop:v3:enabled'

export function App() {
  useScheduledTaskDesktopNotifications()
  useEffect(() => {
    let cleanup: (() => void) | undefined
    let cancelled = false
    installDesktopNotificationNavigation()
      .then((fn) => {
        if (cancelled) { fn() } else { cleanup = fn }
      })
      .catch(() => {})
    return () => { cancelled = true; cleanup?.() }
  }, [])

  // Read flag once on mount; default to v3 ON (the migration target).
  const [v3, setV3] = useState<boolean>(() => {
    try {
      const v = localStorage.getItem(FLAG)
      // v3 is default; opt-out by setting '0'
      return v !== '0'
    } catch { return true }
  })

  // Allow dev to toggle via console: localStorage.setItem('madcop:v3:enabled','0')
  useEffect(() => {
    const onStorage = () => {
      try { setV3(localStorage.getItem(FLAG) !== '0') } catch {}
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  // v3 wraps the legacy AppShell in Madcop theme CSS, so the
  // legacy component already picks up the new colors. When
  // localStorage flag is set, the full MadcopApp takes over.
  if (v3) {
    // Mount both: MadcopApp is the new top-level. We keep AppShell
    // importable so other places (tests, etc) still work.
    return <MadcopApp />
  }
  return <AppShell />
}
