/**
 * Sprint 5 — useProactive: renderer-side coordinator for the Proactive
 * Observer.
 *
 * Responsibilities:
 *  - Subscribe to `proactive:observation` events and expose the current
 *    observation (so ProactiveToast can render it).
 *  - Whenever the settings toggles or the active workspace change,
 *    push the new config to the Electron main process via
 *    `desktopHost.proactive.setWorkspace(...)` so the FileWatcher + poll
 *    start/stop accordingly.
 *
 * Call `useProactive()` once at app startup (e.g. in AppShell).
 */
import { ref, watch, onMounted, onBeforeUnmount } from 'vue'
import { desktopHost } from '../../lib/desktopHost'
import type { ProactiveObservation } from '../../lib/desktopHost/types'
import { useSettingsStore } from '../stores/settingsStore'
import { useUIStore } from '../stores/uiStore'

const currentObservation = ref<ProactiveObservation | null>(null)
let installed = false
let unlisten: (() => void) | null = null

function getWorkspace(): string {
  try {
    return localStorage.getItem('madcop_workspace_dir') || ''
  } catch {
    return ''
  }
}

export function useProactive() {
  const settings = useSettingsStore()

  async function pushConfig() {
    try {
      await desktopHost.proactive.setWorkspace({
        workspace: getWorkspace(),
        enabled: settings.proactive.enabled,
        observeFiles: settings.proactive.observeFiles,
        observeTerminal: settings.proactive.observeTerminal,
      })
    } catch (e) {
      console.warn('[proactive] failed to push config:', e)
    }
  }

  function dismiss() {
    currentObservation.value = null
  }

  function adoptInto(text: string): string {
    // Caller pastes the suggestion into the chat input.
    return (currentObservation.value?.suggestion || '').trim() || text
  }

  onMounted(async () => {
    if (!installed) {
      installed = true
      try {
        const un = await desktopHost.proactive.onObservation((obs) => {
          currentObservation.value = obs
        })
        unlisten = typeof un === 'function' ? un : null
      } catch (e) {
        console.warn('[proactive] subscribe failed:', e)
      }
    }
    await pushConfig()
    // P2-NS — show a one-time welcome toast the first time we actually
    // start monitoring. If the user picked a workspace and we auto-
    // enabled Observer (改进 1), tell them so they know it's running.
    // If they didn't pick a workspace yet, surface the onboarding CTA
    // so the empty Sidebar card isn't a surprise.
    const ui = useUIStore()
    const ws = getWorkspace()
    if (ws && settings.proactive.enabled) {
      ui.addToast({
        type: 'success',
        message: `已自动开始监控 ${ws.split('/').pop() || ws}`,
      })
    } else if (!ws) {
      ui.addToast({
        type: 'info',
        message: '请在左侧选择项目文件夹，开始使用 MadCop',
      })
    }
  })

  // Re-push whenever toggles change.
  watch(
    () => [settings.proactive.enabled, settings.proactive.observeFiles, settings.proactive.observeTerminal],
    () => { void pushConfig() },
  )
  // Re-push when the workspace changes (localStorage-backed; poll lightly).
  watch(
    () => getWorkspace(),
    () => { void pushConfig() },
  )

  onBeforeUnmount(() => {
    // Keep the global subscription alive across mounts; only the app
    // root's unmount would tear it down, and the app never unmounts.
  })

  return {
    currentObservation,
    dismiss,
    adoptInto,
  }
}

export { currentObservation as proactiveObservation }
