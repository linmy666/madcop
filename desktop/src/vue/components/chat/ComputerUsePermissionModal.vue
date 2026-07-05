<script setup lang="ts">
/**
 * ComputerUsePermissionModal — Vue 3 full port of components/chat/ComputerUsePermissionModal.tsx (311 lines)
 * macOS system permission modal for Computer Use feature.
 * Prop-driven: parent passes t(), onSubmit() (maps to respondToComputerUsePermission), and openSettings().
 *
 * Translations rules:
 *   - className → class
 *   - useState → ref()
 *   - useMemo → computed()
 *   - createPortal → <teleport to="body">
 *   - lucide-react → <span class="material-symbols-outlined">
 *   - ALL Tailwind classes and --color-* variables kept VERBATIM
 */
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { computerUseApi } from '../../api/computerUse'
import type {
  ComputerUsePermissionRequest,
  ComputerUsePermissionResponse,
} from '../../types/chat'

const DEFAULT_GRANT_FLAGS = {
  clipboardRead: false,
  clipboardWrite: false,
  systemKeyCombos: false,
} as const

export interface ComputerUsePermissionModalProps {
  sessionId: string
  request: ComputerUsePermissionRequest | null
  t?: (key: string, params?: Record<string, unknown>) => string
  onSubmit?: (response: ComputerUsePermissionResponse) => void
  openSettings?: (pane: 'Privacy_Accessibility' | 'Privacy_ScreenCapture') => Promise<void>
}

const props = withDefaults(defineProps<ComputerUsePermissionModalProps>(), {
  t: () => '',
  onSubmit: () => {},
  openSettings: async () => {},
})

/** ── Local state ─────────────────────────────────────────────────────────── */
const openingPane = ref<'Privacy_Accessibility' | 'Privacy_ScreenCapture' | null>(null)

/** ── Computed: list of enabled requested flags ─────────────────────────── */
const requestedFlags = computed(() => {
  if (!props.request) return []
  return Object.entries(props.request.requestedFlags)
    .filter(([, enabled]) => enabled)
    .map(([flag]) => flag)
})

/** ── Helpers ─────────────────────────────────────────────────────────────── */
function denyAllResponse(): ComputerUsePermissionResponse {
  return {
    granted: [],
    denied: [],
    flags: { ...DEFAULT_GRANT_FLAGS },
    userConsented: false,
  }
}

function buildAllowResponse(request: ComputerUsePermissionRequest): ComputerUsePermissionResponse {
  const now = Date.now()
  const granted = request.apps.flatMap((app) => {
    if (!app.resolved || app.alreadyGranted) return []
    return [{
      bundleId: app.resolved.bundleId,
      displayName: app.resolved.displayName,
      grantedAt: now,
      tier: app.proposedTier,
    }]
  })

  const denied = request.apps.flatMap((app) => {
    if (app.resolved) return []
    return [{
      bundleId: app.requestedName,
      reason: 'not_installed' as const,
    }]
  })

  const flags = {
    ...DEFAULT_GRANT_FLAGS,
    ...Object.fromEntries(
      Object.entries(request.requestedFlags).filter(([, value]) => value === true),
    ),
  }

  return {
    granted,
    denied,
    flags,
    userConsented: true,
  }
}

/** ── Event handlers ─────────────────────────────────────────────────────── */
function handleDeny() {
  if (!props.request) return
  props.onSubmit(denyAllResponse())
}

function handleAllow() {
  if (!props.request) return
  props.onSubmit(buildAllowResponse(props.request))
}

async function handleOpenSettings(
  pane: 'Privacy_Accessibility' | 'Privacy_ScreenCapture',
) {
  openingPane.value = pane
  try {
    await props.openSettings(pane)
  } finally {
    openingPane.value = null
  }
}

/** ── Escape key handler (mirrors Modal's useEffect) ────────────────────── */
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    handleDeny()
  }
}

onMounted(() => document.addEventListener('keydown', onKeydown))
onUnmounted(() => document.removeEventListener('keydown', onKeydown))
</script>

<template>
  <!-- createPortal → <teleport to="body"> -->
  <teleport to="body">
    <div
      v-if="request"
      class="fixed inset-0 z-50 flex items-center justify-center"
    >
      <!-- Backdrop -->
      <div
        class="absolute inset-0 bg-[var(--color-overlay-scrim)] transition-opacity duration-200"
        @click="handleDeny"
      />

      <!-- Modal content -->
      <div
        class="glass-panel relative rounded-[var(--radius-xl)] max-h-[85vh] flex flex-col"
        :style="{ width: 640, maxWidth: 'calc(100vw - 48px)' }"
        role="dialog"
        aria-modal="true"
        :aria-label="request.tccState ? t('computerUseApproval.titleTcc') : t('computerUseApproval.titleApps')"
      >
        <!-- Header -->
        <div class="flex items-start justify-between gap-4 px-6 pt-6 pb-0">
          <h2 class="text-xl font-bold text-[var(--color-text-primary)]">
            {{ request.tccState ? t('computerUseApproval.titleTcc') : t('computerUseApproval.titleApps') }}
          </h2>
          <button
            type="button"
            @click="handleDeny"
            aria-label="Close dialog"
            class="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
          >
            <span class="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>

        <!-- Body -->
        <div class="px-6 py-4 overflow-y-auto flex-1">
          <template v-if="request.tccState">
            <div class="space-y-4">
              <p class="text-sm text-[var(--color-text-secondary)]">
                {{ t('computerUseApproval.tccHint') }}
              </p>

              <div class="space-y-3">
                <!-- Accessibility row -->
                <div class="flex items-center justify-between gap-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3">
                  <div>
                    <div class="text-sm font-semibold text-[var(--color-text-primary)]">
                      {{ t('computerUseApproval.accessibility') }}
                    </div>
                    <div class="mt-1 text-xs text-[var(--color-text-tertiary)]">
                      {{ request.tccState.accessibility ? t('computerUseApproval.granted') : t('computerUseApproval.notGranted') }}
                    </div>
                  </div>
                  <button
                    v-if="!request.tccState.accessibility"
                    type="button"
                    :disabled="openingPane !== null"
                    @click="handleOpenSettings('Privacy_Accessibility')"
                    class="inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-md)] px-2 py-1 text-xs font-medium transition-colors duration-150 cursor-pointer bg-[var(--color-surface)] text-[var(--color-text-primary)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <svg
                      v-if="openingPane === 'Privacy_Accessibility'"
                      class="animate-spin h-4 w-4"
                      viewBox="0 0 24 24"
                      fill="none"
                    >
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    {{ t('computerUseApproval.openAccessibility') }}
                  </button>
                </div>

                <!-- Screen Recording row -->
                <div class="flex items-center justify-between gap-4 rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3">
                  <div>
                    <div class="text-sm font-semibold text-[var(--color-text-primary)]">
                      {{ t('computerUseApproval.screenRecording') }}
                    </div>
                    <div class="mt-1 text-xs text-[var(--color-text-tertiary)]">
                      {{ request.tccState.screenRecording ? t('computerUseApproval.granted') : t('computerUseApproval.notGranted') }}
                    </div>
                  </div>
                  <button
                    v-if="!request.tccState.screenRecording"
                    type="button"
                    :disabled="openingPane !== null"
                    @click="handleOpenSettings('Privacy_ScreenCapture')"
                    class="inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-md)] px-2 py-1 text-xs font-medium transition-colors duration-150 cursor-pointer bg-[var(--color-surface)] text-[var(--color-text-primary)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    <svg
                      v-if="openingPane === 'Privacy_ScreenCapture'"
                      class="animate-spin h-4 w-4"
                      viewBox="0 0 24 24"
                      fill="none"
                    >
                      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
                      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
                    </svg>
                    {{ t('computerUseApproval.openScreenRecording') }}
                  </button>
                </div>
              </div>

              <div class="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3 text-xs text-[var(--color-text-tertiary)]">
                {{ t('computerUseApproval.tryAgainHint') }}
              </div>

              <div class="flex justify-end">
                <button
                  type="button"
                  @click="handleDeny"
                  class="inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-md)] px-2 py-1 text-xs font-medium transition-colors duration-150 cursor-pointer bg-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                >
                  {{ t('computerUseApproval.tryAgain') }}
                </button>
              </div>
            </div>
          </template>

          <template v-else>
            <div class="space-y-4">
              <!-- Reason box -->
              <div
                v-if="request.reason"
                class="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3"
              >
                <div class="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">
                  {{ t('computerUseApproval.reason') }}
                </div>
                <div class="mt-1 text-sm text-[var(--color-text-primary)]">
                  {{ request.reason }}
                </div>
              </div>

              <!-- App rows -->
              <div class="space-y-2">
                <div
                  v-for="app in request.apps"
                  :key="app.resolved?.bundleId ?? app.requestedName"
                  class="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3"
                >
                  <div class="flex items-start justify-between gap-3">
                    <div>
                      <div class="text-sm font-semibold text-[var(--color-text-primary)]">
                        {{ app.resolved?.displayName ?? app.requestedName }}
                      </div>
                      <div class="mt-1 text-xs text-[var(--color-text-tertiary)]">
                        {{ app.resolved?.bundleId ?? t('computerUseApproval.notInstalled') }}
                      </div>
                    </div>
                    <span class="rounded-full bg-[var(--color-surface-container)] px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-[var(--color-text-secondary)]">
                      {{ app.proposedTier }}
                    </span>
                  </div>

                  <p v-if="!app.resolved" class="mt-2 text-xs text-[var(--color-error)]">
                    {{ t('computerUseApproval.notInstalled') }}
                  </p>
                  <p v-if="app.alreadyGranted" class="mt-2 text-xs text-[var(--color-success)]">
                    {{ t('computerUseApproval.alreadyGranted') }}
                  </p>
                  <p v-else-if="app.isSentinel" class="mt-2 text-xs text-[var(--color-warning)]">
                    {{ t('computerUseApproval.sensitiveApp') }}
                  </p>
                </div>
              </div>

              <!-- Requested flags -->
              <div
                v-if="requestedFlags.length > 0"
                class="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3"
              >
                <div class="text-xs font-semibold uppercase tracking-wide text-[var(--color-text-tertiary)]">
                  {{ t('computerUseApproval.alsoRequested') }}
                </div>
                <div class="mt-2 flex flex-wrap gap-2">
                  <span
                    v-for="flag in requestedFlags"
                    :key="flag"
                    class="rounded-full bg-[var(--color-surface-container)] px-2 py-1 text-[11px] text-[var(--color-text-secondary)]"
                  >
                    {{ flag }}
                  </span>
                </div>
              </div>

              <!-- Hide while working -->
              <div
                v-if="request.willHide && request.willHide.length > 0"
                class="rounded-[var(--radius-lg)] border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-3 text-sm text-[var(--color-text-secondary)]"
              >
                {{
                  request.autoUnhideEnabled
                    ? t('computerUseApproval.hideWhileWorkingRestore', { count: request.willHide.length })
                    : t('computerUseApproval.hideWhileWorking', { count: request.willHide.length })
                }}
              </div>
            </div>
          </template>
        </div>

        <!-- Footer -->
        <div class="px-6 pb-6 pt-0 flex justify-end gap-2">
          <template v-if="request.tccState">
            <button
              type="button"
              @click="handleDeny"
              class="inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-md)] px-2 py-1 text-xs font-medium transition-colors duration-150 cursor-pointer bg-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
            >
              {{ t('computerUseApproval.deny') }}
            </button>
          </template>
          <template v-else>
            <button
              type="button"
              @click="handleDeny"
              class="inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-md)] px-2 py-1 text-xs font-medium transition-colors duration-150 cursor-pointer bg-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
            >
              {{ t('computerUseApproval.deny') }}
            </button>
            <button
              type="button"
              @click="handleAllow"
              class="inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-md)] px-4 py-2 text-sm font-medium transition-colors duration-150 cursor-pointer bg-[image:var(--gradient-btn-primary)] text-[var(--color-btn-primary-fg)] shadow-[var(--shadow-button-primary)] hover:bg-[image:var(--gradient-btn-primary-hover)] hover:brightness-105 active:translate-y-[1px]"
            >
              {{ t('computerUseApproval.allow') }}
            </button>
          </template>
        </div>
      </div>
    </div>
  </teleport>
</template>
