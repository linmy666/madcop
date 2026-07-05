<script setup lang="ts">
import { ref, computed } from 'vue'

/**
 * ComputerUsePermissionModal — Vue 3 port of components/chat/ComputerUsePermissionModal.tsx
 * macOS system permission modal for Computer Use feature.
 * Prop-driven: no React stores, no Modal component dependency.
 */

export interface ComputerUsePermissionModalProps {
  request: {
    requestId: string
    apps: Array<{
      requestedName: string
      resolved?: { bundleId: string; displayName: string }
      alreadyGranted?: boolean
      proposedTier: string
      isSentinel?: boolean
    }>
    requestedFlags: Record<string, boolean>
    tccState?: { accessibility: boolean; screenRecording: boolean }
    reason?: string
    willHide?: string[]
    autoUnhideEnabled?: boolean
  } | null
  t?: (key: string, params?: Record<string, unknown>) => string
  onSubmit?: (response: unknown) => void
}

const props = withDefaults(defineProps<ComputerUsePermissionModalProps>(), {
  t: () => '',
  onSubmit: () => {},
})

const openingPane = ref<string | null>(null)
const open = computed(() => !!props.request)

if (!props.request) throw new Error('ComputerUsePermissionModal requires request prop')

function buildAllowResponse() {
  const req = props.request!
  const now = Date.now()
  const granted = req.apps.flatMap((app) => {
    if (!app.resolved || app.alreadyGranted) return []
    return [{ bundleId: app.resolved.bundleId, displayName: app.resolved.displayName, grantedAt: now, tier: app.proposedTier }]
  })
  const denied = req.apps.flatMap((app) => {
    if (app.resolved) return []
    return [{ bundleId: app.requestedName, reason: 'not_installed' }]
  })
  const flags = { ...Object.fromEntries(Object.entries(req.requestedFlags).filter(([, v]) => v === true)) }
  return { granted, denied, flags, userConsented: true }
}

function denyAllResponse() {
  return { granted: [], denied: [], flags: { clipboardRead: false, clipboardWrite: false, systemKeyCombos: false }, userConsented: false }
}

const requestedFlags = computed(() => {
  if (!props.request) return []
  return Object.entries(props.request.requestedFlags).filter(([, enabled]) => enabled).map(([flag]) => flag)
})

function handleDeny() { if (props.onSubmit) props.onSubmit(denyAllResponse()) }
function handleAllow() { if (props.onSubmit) props.onSubmit(buildAllowResponse()) }
</script>

<template>
  <div v-if="request" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
    <div class="w-[640px] max-w-[calc(100vw-2rem)] max-h-[calc(100vh-2rem)] overflow-auto rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-[var(--shadow-dropdown)]">
      <!-- Header -->
      <div class="flex items-center justify-between border-b border-[var(--color-outline-variant)]/20 px-4 py-3">
        <h3 class="text-sm font-semibold text-[var(--color-text-primary)]">
          {{ request.tccState ? t('computerUseApproval.titleTcc') : t('computerUseApproval.titleApps') }}
        </h3>
        <button @click="handleDeny" class="rounded-full p-1 text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]">
          <span class="material-symbols-outlined text-[18px]">close</span>
        </button>
      </div>

      <!-- Body -->
      <div class="px-4 py-3">
        <template v-if="request.tccState">
          <p class="text-sm text-[var(--color-text-secondary)]">{{ t('computerUseApproval.tccHint') }}</p>
          <div class="mt-3 space-y-3">
            <div class="flex items-center justify-between gap-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3">
              <div>
                <div class="text-sm font-semibold text-[var(--color-text-primary)]">{{ t('computerUseApproval.accessibility') }}</div>
                <div class="mt-1 text-xs text-[var(--color-text-tertiary)]">{{ request.tccState.accessibility ? t('computerUseApproval.granted') : t('computerUseApproval.notGranted') }}</div>
              </div>
              <button v-if="!request.tccState.accessibility" @click="openingPane = 'Privacy_Accessibility'"
                :disabled="openingPane !== null"
                class="rounded-md bg-[var(--color-surface-container)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-container-high)]">
                <span v-if="openingPane" class="animate-spin mr-1">↻</span>
                {{ t('computerUseApproval.openAccessibility') }}
              </button>
            </div>
            <div class="flex items-center justify-between gap-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3">
              <div>
                <div class="text-sm font-semibold text-[var(--color-text-primary)]">{{ t('computerUseApproval.screenRecording') }}</div>
                <div class="mt-1 text-xs text-[var(--color-text-tertiary)]">{{ request.tccState.screenRecording ? t('computerUseApproval.granted') : t('computerUseApproval.notGranted') }}</div>
              </div>
              <button v-if="!request.tccState.screenRecording" @click="openingPane = 'Privacy_ScreenCapture'"
                :disabled="openingPane !== null"
                class="rounded-md bg-[var(--color-surface-container)] px-3 py-1.5 text-xs font-medium text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-container-high)]">
                {{ t('computerUseApproval.openScreenRecording') }}
              </button>
            </div>
          </div>
          <div class="mt-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3 text-xs text-[var(--color-text-tertiary)]">
            {{ t('computerUseApproval.tryAgainHint') }}
          </div>
        </template>

        <template v-else>
          <div v-if="request.reason" class="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3">
            <div class="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">{{ t('computerUseApproval.reason') }}</div>
            <div class="mt-1 text-sm text-[var(--color-text-primary)]">{{ request.reason }}</div>
          </div>

          <div class="mt-3 space-y-2">
            <div v-for="app in request.apps" :key="app.resolved?.bundleId ?? app.requestedName"
              class="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3">
              <div class="flex items-start justify-between gap-3">
                <div>
                  <div class="text-sm font-semibold text-[var(--color-text-primary)]">{{ app.resolved?.displayName ?? app.requestedName }}</div>
                  <div class="mt-1 text-xs text-[var(--color-text-tertiary)]">{{ app.resolved?.bundleId ?? t('computerUseApproval.notInstalled') }}</div>
                </div>
                <span class="rounded-full bg-[var(--color-surface-container)] px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">{{ app.proposedTier }}</span>
              </div>
              <p v-if="!app.resolved" class="mt-2 text-xs text-[var(--color-error)]">{{ t('computerUseApproval.notInstalled') }}</p>
              <p v-if="app.alreadyGranted" class="mt-2 text-xs text-[var(--color-success)]">{{ t('computerUseApproval.alreadyGranted') }}</p>
              <p v-if="app.isSentinel" class="mt-2 text-xs text-[var(--color-warning)]">{{ t('computerUseApproval.sensitiveApp') }}</p>
            </div>
          </div>

          <div v-if="requestedFlags.length > 0" class="mt-3 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3">
            <div class="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">{{ t('computerUseApproval.alsoRequested') }}</div>
            <div class="mt-2 flex flex-wrap gap-2">
              <span v-for="flag in requestedFlags" :key="flag" class="rounded-full bg-[var(--color-surface-container)] px-2 py-1 text-[11px] text-[var(--color-text-secondary)]">{{ flag }}</span>
            </div>
          </div>
        </template>
      </div>

      <!-- Footer -->
      <div class="flex items-center justify-end gap-2 border-t border-[var(--color-outline-variant)]/20 bg-[var(--color-surface-container-low)] px-4 py-3">
        <button @click="handleDeny"
          class="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-[12px] font-medium text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-container)]">
          {{ t('computerUseApproval.deny') }}
        </button>
        <button v-if="!request.tccState" @click="handleAllow"
          class="rounded-md bg-[var(--color-brand)] px-3 py-1.5 text-[12px] font-medium text-white transition-colors hover:bg-[var(--color-brand)]/85">
          {{ t('computerUseApproval.allow') }}
        </button>
      </div>
    </div>
  </div>
</template>
