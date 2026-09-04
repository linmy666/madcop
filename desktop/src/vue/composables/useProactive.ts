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
import { getCurrentLocale } from '../i18n'

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
    // Welcome toasts removed by product decision: "已自动开始监控" fired
    // on every useProactive() mount (AppShell + Observer page each mount
    // it) AND on every app launch — the sidebar's 观察器运行中 dot already
    // carries the running state. A background service starting is not
    // toast-worthy news; the onboarding CTA lives on the empty session
    // hero instead.
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

/**
 * Pick the user's language side from a "中文 | English" bilingual string
 * emitted by the proactive backend. Falls back to the original text when
 * there is no separator (older digests, single-language LLM output).
 */
export function pickLocaleText(text: string, locale?: string): string {
  if (!text) return text
  const sep = text.includes(' | ') ? ' | ' : (text.includes('｜') ? '｜' : '')
  if (!sep) return text
  const parts = text.split(sep).map((s) => s.trim()).filter(Boolean)
  if (parts.length < 2) return text
  let loc = locale || ''
  if (!loc) {
    try { loc = getCurrentLocale() } catch { loc = 'zh' }
  }
  const zhSide = parts.find((part) => /[\u4e00-\u9fff]/.test(part)) ?? parts[0] ?? ''
  const enSide = parts.find((part) => !/[\u4e00-\u9fff]/.test(part)) ?? parts[parts.length - 1] ?? ''
  return loc === 'en' ? enSide : zhSide
}
