<script setup lang="ts">
/**
 * BrowserSurface — Vue 3 port of components/browser/BrowserSurface.tsx (241 lines)
 *
 * Browser view panel for computer use. Displays a native webview inside the
 * workbench with address bar, navigation controls, and overlay actions.
 * Uses zustand stores directly (compatible via getState + subscribe pattern).
 */

import { ref, computed, onMounted, onUnmounted, nextTick } from 'vue'

// External APIs
import { computeWebviewBounds } from './computeWebviewBounds'
import { getServerBaseUrl, isLoopbackHostname } from '../../lib/desktopRuntime'
import { classifyPreviewLink } from '../../lib/previewLinkRouter'
import { isAbsoluteLocalPath, localFileUrl, previewFsUrl } from '../../lib/handlePreviewLink'
import { previewBridge } from '../../lib/previewBridge'
import { subscribePreviewEvents } from '../../lib/previewEvents'

// zustand stores (accessed via getState + subscribe for Vue compatibility)
import { useBrowserPanelStore, type BrowserSessionState } from '../../stores/browserPanelStore'
import { useOverlayStore } from '../../stores/overlayStore'

const props = defineProps<{
  sessionId: string
}>()

const hostRef = ref<HTMLDivElement | null>(null)
const loadSeqRef = ref(0)

// Reactive session state synced from zustand store
const session = ref<BrowserSessionState | undefined>(useBrowserPanelStore.getState().bySession[props.sessionId])
const overlayCount = ref(useOverlayStore.getState().count)
const store = useBrowserPanelStore.getState()

// Subscribe to zustand store changes to keep Vue reactive
let unsubBrowser: (() => void) | undefined
let unsubOverlay: (() => void) | undefined
let unsubPreview: (() => void) | undefined

function shouldWaitForLocalPreview(url: string): boolean {
  const LOCAL_PREVIEW_PATH_PREFIXES = ['/preview-fs/', '/local-file/']
  try {
    const parsed = new URL(url)
    return isLoopbackHostname(parsed.hostname) &&
      LOCAL_PREVIEW_PATH_PREFIXES.some((prefix) => parsed.pathname.startsWith(prefix))
  } catch {
    return false
  }
}

async function waitForLocalPreview(url: string): Promise<void> {
  const LOCAL_PREVIEW_READY_TIMEOUT_MS = 2500
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), LOCAL_PREVIEW_READY_TIMEOUT_MS)
  try {
    await fetch(url, { method: 'HEAD', cache: 'no-store', signal: controller.signal })
  } catch {
    // Best-effort warmup only. The native webview still navigates so users can
    // see the server's own error page or use Reload if the first probe raced.
  } finally {
    window.clearTimeout(timeout)
  }
}

function resolveBrowserNavigationUrl(input: string, sessionId: string): string {
  const value = input.trim()
  if (!value) return ''
  const classified = classifyPreviewLink(value)
  if (classified.kind === 'browser-file' && classified.path) {
    const serverBaseUrl = getServerBaseUrl()
    return isAbsoluteLocalPath(classified.path)
      ? localFileUrl(serverBaseUrl, classified.path)
      : previewFsUrl(serverBaseUrl, sessionId, classified.path)
  }
  return value
}

const reportBounds = () => {
  const el = hostRef.value
  if (!el) return
  previewBridge.setBounds(computeWebviewBounds(el.getBoundingClientRect()))
}

const loadNativePreview = (
  url: string,
  action: () => Promise<void>,
) => {
  const seq = loadSeqRef.value + 1
  loadSeqRef.value = seq
  ;(async () => {
    if (shouldWaitForLocalPreview(url)) {
      await waitForLocalPreview(url)
    }
    if (loadSeqRef.value !== seq) return
    await action()
  })().catch(() => {
    if (loadSeqRef.value === seq) {
      useBrowserPanelStore.getState().setLoading(props.sessionId, false)
    }
  })
}

const openOrNavigate = (inputUrl: string) => {
  const url = resolveBrowserNavigationUrl(inputUrl, props.sessionId)
  if (!url) return
  const current = useBrowserPanelStore.getState().bySession[props.sessionId]
  store.navigate(props.sessionId, url)
  if (current?.url) {
    loadNativePreview(url, () => previewBridge.navigate(url))
    return
  }
  const el = hostRef.value
  if (el) {
    const bounds = computeWebviewBounds(el.getBoundingClientRect())
    loadNativePreview(url, () => previewBridge.open(url, bounds))
  } else {
    loadNativePreview(url, () => previewBridge.navigate(url))
  }
}

const isLoading = computed(() => session.value?.loading ?? false)
const currentUrl = computed(() => session.value?.url)
const pickerActive = computed(() => session.value?.pickerActive ?? false)

// Lifecycle: sync zustand stores → Vue refs, subscribe to preview events,
// and handle layout effects (initial load + visibility + resize).
onMounted(async () => {
  // Subscribe to browser panel store changes
  unsubBrowser = useBrowserPanelStore.subscribe((state) => {
    session.value = state.bySession[props.sessionId]
  })
  // Subscribe to overlay store changes
  unsubOverlay = useOverlayStore.subscribe((state) => {
    overlayCount.value = state.count
  })

  // Initial layout effect: open webview with session URL
  await nextTick()
  const el = hostRef.value
  if (el && session.value?.url) {
    const bounds = computeWebviewBounds(el.getBoundingClientRect())
    loadNativePreview(session.value.url, () => previewBridge.open(session.value.url, bounds))
  }

  // Subscribe to preview events
  try {
    unsubPreview = await subscribePreviewEvents(props.sessionId)
  } catch {
    // Preview events subscription may fail in non-desktop environments
  }
})

onUnmounted(() => {
  loadSeqRef.value += 1
  previewBridge.close()
  unsubBrowser?.()
  unsubOverlay?.()
  unsubPreview?.()
})

// Visibility-sync: hide webview while overlays (e.g. ImageGalleryModal) are active
const updateVisibility = () => {
  previewBridge.setVisible(overlayCount.value === 0)
}

// Watch overlayCount changes
import { watch } from 'vue'
watch(() => overlayCount.value, updateVisibility)
watch(() => session.value, (s) => {
  if (s) updateVisibility()
})

// Resize observer for bounds reporting
onMounted(() => {
  const el = hostRef.value
  if (!el) return
  const ro = new ResizeObserver(() => reportBounds())
  ro.observe(el)
  window.addEventListener('resize', reportBounds)

  // Cleanup on unmount
  onUnmounted(() => {
    ro.disconnect()
    window.removeEventListener('resize', reportBounds)
  })
})

// Fallback: if loading stays true for ~15s, force it off (CSP may block injected scripts)
import { onActivated } from 'vue'
const loadingTimer = ref<ReturnType<typeof setTimeout> | null>(null)
watch(isLoading, (loading) => {
  if (loadingTimer.value) {
    clearTimeout(loadingTimer.value)
    loadingTimer.value = null
  }
  if (loading) {
    loadingTimer.value = setTimeout(() => {
      useBrowserPanelStore.getState().setLoading(props.sessionId, false)
    }, 15000)
  }
})

if (!session.value) {
  // Render null when no session — Vue renders nothing
}
</script>

<template>
  <!-- Render nothing if no session -->
  <template v-if="session">
    <div class="flex h-full flex-col">
      <!-- BrowserAddressBar is a separate child component -->
      <slot
        name="address-bar"
        :url="session.url"
        :can-go-back="session.canGoBack"
        :can-go-forward="session.canGoForward"
        :loading="session.loading"
        :on-navigate="openOrNavigate"
        :on-back="() => {
          store.goBack(props.sessionId)
          store.setLoading(props.sessionId, true)
          const u = useBrowserPanelStore.getState().bySession[props.sessionId]!.url
          loadNativePreview(u, () => previewBridge.navigate(u))
        }"
        :on-forward="() => {
          store.goForward(props.sessionId)
          store.setLoading(props.sessionId, true)
          const u = useBrowserPanelStore.getState().bySession[props.sessionId]!.url
          loadNativePreview(u, () => previewBridge.navigate(u))
        }"
        :on-reload="() => {
          if (!session?.url) return
          store.setLoading(props.sessionId, true)
          loadNativePreview(session.url, () => previewBridge.navigate(session.url))
        }"
        :preview-actions="true"
      />

      <!-- Preview host — native webview container -->
      <div ref="hostRef" class="relative flex-1 overflow-hidden" data-testid="preview-host">
        <!-- Loading overlay -->
        <div
          v-if="session.loading"
          class="pointer-events-none absolute inset-0 flex items-center justify-center bg-[var(--color-surface)] text-[var(--color-text-tertiary)]"
        >
          <span
            class="material-symbols-outlined animate-spin text-[24px]"
            style="font-variation-settings: 'FILL' 1"
            aria-label="加载中"
          >progress_activity</span>
        </div>
      </div>
    </div>
  </template>
</template>