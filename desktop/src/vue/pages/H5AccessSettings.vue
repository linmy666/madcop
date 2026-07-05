<script setup lang="ts">
// v3.0 — H5AccessSettings (Vue 3 SFC translation from React H5AccessSettings)
// Direct translation of src/pages/Settings.tsx lines 3225-3685
//
// This component manages LAN/web mobile device access to the desktop app.
// It handles: enable/disable toggle, QR code generation, token management,
// public URL configuration, fixed port settings, and disconnect grace period.
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { useSettingsStore } from '../stores/settingsStore'
import { useUIStore } from '../stores/uiStore'
import { useTranslation } from '../i18n'
import Input from '../components/shared/Input.vue'
import Button from '../components/shared/Button.vue'
import Modal from '../components/shared/Modal.vue'
import QRCode from 'qrcode'
import { copyTextToClipboard } from '../components/chat/clipboard'

// ─── Pure helper functions (mirrors from React lines 87-182) ──

/**
 * Build the H5 launch URL from a public base URL and token.
 * Appends ?serverUrl=...&h5Token=... as query parameters.
 */
function buildH5LaunchUrl(baseUrl: string | null, token: string | null): string | null {
  if (!baseUrl) return null
  try {
    const url = new URL(baseUrl)
    if (token) {
      url.searchParams.set('serverUrl', baseUrl)
      url.searchParams.set('h5Token', token)
    }
    return url.toString().replace(/\/$/, '')
  } catch {
    return token
      ? `${baseUrl}${baseUrl.includes('?') ? '&' : '?'}serverUrl=${encodeURIComponent(baseUrl)}&h5Token=${encodeURIComponent(token)}`
      : baseUrl
  }
}

function isLanH5BaseUrl(url: URL): boolean {
  return url.protocol === 'http:' &&
    !!url.port &&
    (
      url.hostname === 'localhost' ||
      url.hostname === '127.0.0.1' ||
      url.hostname.startsWith('10.') ||
      url.hostname.startsWith('192.168.') ||
      /^172\.(1[6-9]|2\d|3[0-1])\./.test(url.hostname) ||
      url.hostname.startsWith('169.254.')
    )
}

/**
 * Extract just the hostname from a LAN base URL, or the full URL for non-LAN.
 */
function extractH5AccessAddressDraft(baseUrl: string | null): string {
  if (!baseUrl) return ''
  try {
    const url = new URL(baseUrl)
    return isLanH5BaseUrl(url) ? url.hostname : baseUrl
  } catch {
    return baseUrl
  }
}

/**
 * Extract hostname from a URL string.
 */
function extractHostnameFromUrl(value: string | null): string | null {
  if (!value) return null
  try {
    return new URL(value).hostname || null
  } catch {
    return null
  }
}

/**
 * Extract the port from a base URL.
 */
function extractH5AccessPort(baseUrl: string | null): string | null {
  if (!baseUrl) return null
  try {
    const url = new URL(baseUrl)
    return url.port || null
  } catch {
    return null
  }
}

/**
 * Parse and validate the fixed port draft input.
 * Mirrors server-side h5AccessService MIN/MAX_FIXED_PORT.
 */
function parseH5FixedPortDraft(draft: string): number | null | 'invalid' {
  const trimmed = draft.trim()
  if (!trimmed) return null
  if (!/^\d{1,5}$/.test(trimmed)) return 'invalid'
  const port = Number(trimmed)
  return port >= 1024 && port <= 65535 ? port : 'invalid'
}

/**
 * Parse and validate the disconnect grace draft input.
 * Mirrors server-side h5AccessService MIN/MAX_DISCONNECT_GRACE_SECONDS.
 * Empty means use the built-in 30s default.
 */
function parseH5GraceDraft(draft: string): number | null | 'invalid' {
  const trimmed = draft.trim()
  if (!trimmed) return null
  if (!/^\d{1,5}$/.test(trimmed)) return 'invalid'
  const seconds = Number(trimmed)
  return seconds >= 5 && seconds <= 86400 ? seconds : 'invalid'
}

/**
 * Build the next public base URL from the host draft input and current base URL.
 */
function buildH5PublicBaseUrlFromHostDraft(draft: string, currentBaseUrl: string | null): string | null {
  const trimmed = draft.trim()
  if (!trimmed) return null
  if (/^[a-z][a-z0-9+.-]*:\/\/i.test(trimmed)) return trimmed

  try {
    const current = currentBaseUrl ? new URL(currentBaseUrl) : null
    if (!current) return trimmed

    const port = current.port ? `:${current.port}` : ''
    const path = current.pathname === '/' ? '' : current.pathname.replace(/\/+$/, '')
    return `${current.protocol}//${trimmed}${port}${path}`
  } catch {
    return trimmed
  }
}

// ─── Store and translations ──────────────────────────────────

const settingsStore = useSettingsStore()
const uiStore = useUIStore()
const t = useTranslation()

const h5Access = computed(() => settingsStore.h5Access)
const h5AccessDiagnostics = computed(() => settingsStore.h5AccessDiagnostics)
const h5AccessError = computed(() => settingsStore.h5AccessError)

// ─── Reactive state (mirrors React useState) ─────────────────

const h5PublicBaseUrlDraft = ref(extractH5AccessAddressDraft(h5Access.value.publicBaseUrl))
const h5FixedPortDraft = ref(h5Access.value.fixedPort != null ? String(h5Access.value.fixedPort) : '')
const h5GraceDraft = ref(h5Access.value.disconnectGraceSeconds != null ? String(h5Access.value.disconnectGraceSeconds) : '')
const h5TokenVisible = ref(false)
const h5EnableConfirmOpen = ref(false)
const h5QrDataUrl = ref<string | null>(null)
const h5ActionRunning = ref(false)

const h5AccessUrl = computed(() => h5Access.value.publicBaseUrl)
const h5Token = computed(() => h5Access.value.token)

// The token is persisted server-side, so the QR code and copy actions stay
// available across desktop restarts (issue #767).
const h5LaunchUrl = computed(() => buildH5LaunchUrl(h5AccessUrl.value, h5Token.value))

const h5ActivePort = computed(() => {
  if (h5AccessDiagnostics.value?.activePort != null) {
    return String(h5AccessDiagnostics.value.activePort)
  }
  return extractH5AccessPort(h5AccessUrl.value)
})

const h5NextPublicBaseUrl = computed(() =>
  buildH5PublicBaseUrlFromHostDraft(h5PublicBaseUrlDraft.value, h5Access.value.publicBaseUrl),
)

const h5NextFixedPort = computed(() => parseH5FixedPortDraft(h5FixedPortDraft.value))
const h5FixedPortInvalid = computed(() => h5NextFixedPort.value === 'invalid')

const h5NextGrace = computed(() => parseH5GraceDraft(h5GraceDraft.value))
const h5GraceInvalid = computed(() => h5NextGrace.value === 'invalid')

const h5AccessDirty = computed(() => {
  return (
    h5NextPublicBaseUrl.value !== (h5Access.value.publicBaseUrl ?? null) ||
    (!h5FixedPortInvalid.value && h5NextFixedPort.value !== h5Access.value.fixedPort) ||
    (!h5GraceInvalid.value && h5NextGrace.value !== h5Access.value.disconnectGraceSeconds)
  )
})

const h5FixedPortPendingRestart = computed(() => {
  return (
    h5Access.value.fixedPort != null &&
    h5ActivePort.value != null &&
    String(h5Access.value.fixedPort) !== h5ActivePort.value
  )
})

// ─── Watch: sync drafts when h5Access changes (React useEffect) ──

watch(
  () => h5Access.value,
  (val) => {
    h5PublicBaseUrlDraft.value = extractH5AccessAddressDraft(val.publicBaseUrl)
    h5FixedPortDraft.value = val.fixedPort != null ? String(val.fixedPort) : ''
    h5GraceDraft.value = val.disconnectGraceSeconds != null ? String(val.disconnectGraceSeconds) : ''
  },
  { deep: true },
)

// ─── QR code generation (React useEffect) ────────────────────

let qrCancelled = false

function updateQrCode() {
  qrCancelled = false
  if (!h5Access.value.enabled || !h5LaunchUrl.value || !h5Token.value) {
    h5QrDataUrl.value = null
    return
  }

  QRCode.toDataURL(h5LaunchUrl.value, { margin: 1, width: 192 })
    .then((dataUrl) => {
      if (!qrCancelled) h5QrDataUrl.value = dataUrl
    })
    .catch(() => {
      if (!qrCancelled) h5QrDataUrl.value = null
    })
}

watch([() => h5Access.value.enabled, () => h5LaunchUrl.value, () => h5Token.value], updateQrCode, { immediate: true })

onUnmounted(() => {
  qrCancelled = true
})

// ─── Action runner (mirrors runH5Action) ─────────────────────

async function runH5Action(action: () => Promise<void>): Promise<void> {
  h5ActionRunning.value = true
  try {
    await action()
  } catch {
    // The store owns H5-specific error state.
  } finally {
    h5ActionRunning.value = false
  }
}

// ─── Handlers ────────────────────────────────────────────────

async function handleH5SettingsSave() {
  if (h5FixedPortInvalid.value || h5GraceInvalid.value) return
  await runH5Action(async () => {
    await settingsStore.updateH5AccessSettings({
      publicBaseUrl: h5NextPublicBaseUrl.value,
      fixedPort: h5NextFixedPort.value as number | null,
      disconnectGraceSeconds: h5NextGrace.value as number | null,
    })
  })
}

async function handleH5SwitchToSuggestedHost() {
  const suggested = h5AccessDiagnostics.value?.suggestedHost
  if (!suggested) return
  await runH5Action(async () => {
    const port = extractH5AccessPort(h5Access.value.publicBaseUrl)
    const nextUrl = port ? `http://${suggested}:${port}` : `http://${suggested}`
    await settingsStore.updateH5AccessSettings({ publicBaseUrl: nextUrl })
  })
}

async function handleH5UrlCopy() {
  if (!h5AccessUrl.value) return
  const copied = await copyTextToClipboard(h5AccessUrl.value)
  uiStore.showToast(
    copied ? t('settings.general.h5AccessUrlCopied') : t('common.copyFailed'),
    copied ? 'success' : 'error',
  )
}

async function handleH5LaunchUrlCopy() {
  if (!h5LaunchUrl.value) return
  const copied = await copyTextToClipboard(h5LaunchUrl.value)
  uiStore.showToast(
    copied ? t('settings.general.h5AccessLaunchUrlCopied') : t('common.copyFailed'),
    copied ? 'success' : 'error',
  )
}

async function handleH5EnableConfirm() {
  await runH5Action(async () => {
    await settingsStore.enableH5Access()
    h5TokenVisible.value = false
    h5EnableConfirmOpen.value = false
  })
}

async function handleH5Disable() {
  await runH5Action(async () => {
    await settingsStore.disableH5Access()
    h5TokenVisible.value = false
  })
}

async function handleH5Regenerate() {
  await runH5Action(async () => {
    await settingsStore.regenerateH5AccessToken()
    h5TokenVisible.value = false
  })
}

// ─── Fetch H5 access settings on mount ───────────────────────

onMounted(() => {
  settingsStore.fetchH5Access()
})
</script>

<template>
  <div class="max-w-3xl">
    <section aria-labelledby="h5-access-title" role="region">
      <div class="mb-5 flex items-start gap-3">
        <div class="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] text-[var(--color-brand)]">
          <span class="material-symbols-outlined text-[20px]" aria-hidden="true">qr_code_2</span>
        </div>
        <div class="min-w-0">
          <h2
            id="h5-access-title"
            class="text-base font-semibold text-[var(--color-text-primary)] mb-1"
          >
            {{ t('settings.general.h5AccessTitle') }}
          </h2>
          <p class="text-sm text-[var(--color-text-tertiary)]">
            {{ t('settings.general.h5AccessDescription') }}
          </p>
        </div>
      </div>

      <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-4 py-4">
        <div class="flex items-start justify-between gap-4">
          <label class="flex min-w-0 items-start gap-3">
            <input
              type="checkbox"
              class="mt-1 h-4 w-4 rounded border-[var(--color-border)] accent-[var(--color-primary)]"
              :checked="h5Access.enabled"
              :disabled="h5ActionRunning"
              :aria-label="t('settings.general.h5AccessEnabled')"
              @change="(e) => {
                if ((e.target as HTMLInputElement).checked) {
                  h5EnableConfirmOpen = true
                } else {
                  void handleH5Disable()
                }
              }"
            />
            <span class="min-w-0">
              <span class="block text-sm font-medium text-[var(--color-text-primary)]">
                {{ t('settings.general.h5AccessEnabled') }}
              </span>
              <span class="mt-1 block text-xs leading-5 text-[var(--color-text-tertiary)]">
                {{ t('settings.general.h5AccessEnabledHint') }}
              </span>
            </span>
          </label>
          <span
            :class="[
              'shrink-0 rounded-full px-2 py-0.5 text-xs font-medium',
              h5Access.enabled
                ? 'bg-[var(--color-success)]/10 text-[var(--color-success)]'
                : 'bg-[var(--color-surface)] text-[var(--color-text-tertiary)] border border-[var(--color-border)]',
            ]"
          >
            {{ h5Access.enabled ? t('settings.general.h5AccessStatusEnabled') : t('settings.general.h5AccessDisabledValue') }}
          </span>
        </div>

        <!-- Stale host banner -->
        <div
          v-if="h5AccessDiagnostics?.storedHostStaleness === 'unreachable' && h5AccessDiagnostics.storedPublicBaseUrl"
          data-testid="h5-access-stale-host-banner"
          class="mt-4 rounded-lg border border-[var(--color-warning)]/40 bg-[var(--color-warning)]/10 px-3 py-3 text-xs leading-5 text-[var(--color-text-primary)]"
        >
          <div class="font-semibold">
            {{ t('settings.general.h5AccessStaleHostTitle') }}
          </div>
          <div class="mt-1 text-[var(--color-text-secondary)]">
            {{
              h5AccessDiagnostics.suggestedHost
                ? t('settings.general.h5AccessStaleHostBody', {
                    storedHost: extractHostnameFromUrl(h5AccessDiagnostics.storedPublicBaseUrl) ?? h5AccessDiagnostics.storedPublicBaseUrl,
                  })
                : t('settings.general.h5AccessStaleHostNoSuggestion', {
                    storedHost: extractHostnameFromUrl(h5AccessDiagnostics.storedPublicBaseUrl) ?? h5AccessDiagnostics.storedPublicBaseUrl,
                  })
            }}
          </div>
          <div v-if="h5AccessDiagnostics.suggestedHost" class="mt-2">
            <Button
              size="sm"
              variant="primary"
              :loading="h5ActionRunning"
              @click="() => void handleH5SwitchToSuggestedHost()"
              data-testid="h5-access-stale-host-apply"
            >
              {{
                t('settings.general.h5AccessStaleHostApply', {
                  suggestedHost: h5AccessDiagnostics.suggestedHost,
                })
              }}
            </Button>
          </div>
        </div>

        <!-- Proxy note -->
        <div
          v-if="h5AccessDiagnostics?.storedHostStaleness === 'proxy'"
          data-testid="h5-access-proxy-note"
          class="mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] px-3 py-2 text-xs leading-5 text-[var(--color-text-tertiary)]"
        >
          {{ t('settings.general.h5AccessProxyNote') }}
        </div>

        <!-- Input fields grid -->
        <div class="mt-4 grid grid-cols-1 gap-3">
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-[minmax(0,1fr)_9rem_9rem]">
            <Input
              id="h5-access-public-url"
              :label="t('settings.general.h5AccessPublicHost')"
              :model-value="h5PublicBaseUrlDraft"
              :placeholder="t('settings.general.h5AccessPublicHostPlaceholder')"
              @update:model-value="h5PublicBaseUrlDraft = $event"
            />
            <Input
              id="h5-access-fixed-port"
              :label="t('settings.general.h5AccessFixedPort')"
              :model-value="h5FixedPortDraft"
              :placeholder="t('settings.general.h5AccessFixedPortPlaceholder')"
              input-mode="numeric"
              :error="h5FixedPortInvalid ? t('settings.general.h5AccessFixedPortInvalid') : undefined"
              @update:model-value="h5FixedPortDraft = $event"
            />
            <Input
              id="h5-access-current-port"
              :label="t('settings.general.h5AccessCurrentPort')"
              :model-value="h5ActivePort ?? t('settings.general.h5AccessCurrentPortUnknown')"
              :read-only="true"
              class="text-[var(--color-text-tertiary)]"
            />
          </div>
          <div class="grid grid-cols-1 gap-3 sm:grid-cols-[9rem_minmax(0,1fr)] sm:items-start">
            <Input
              id="h5-access-disconnect-grace"
              :label="t('settings.general.h5AccessDisconnectGrace')"
              :model-value="h5GraceDraft"
              :placeholder="t('settings.general.h5AccessDisconnectGracePlaceholder')"
              input-mode="numeric"
              :error="h5GraceInvalid ? t('settings.general.h5AccessDisconnectGraceInvalid') : undefined"
              @update:model-value="h5GraceDraft = $event"
            />
            <p class="text-xs leading-5 text-[var(--color-text-tertiary)] sm:pt-7">
              {{ t('settings.general.h5AccessDisconnectGraceHint') }}
            </p>
          </div>
          <div class="flex items-center justify-between gap-3">
            <p class="text-xs text-[var(--color-text-tertiary)]">
              {{ t('settings.general.h5AccessOpenHint') }}
              <span>&nbsp;</span>
              {{ t('settings.general.h5AccessFixedPortHint') }}
            </p>
            <Button
              size="sm"
              variant="secondary"
              @click="() => void handleH5SettingsSave()"
              :disabled="!h5AccessDirty || h5FixedPortInvalid || h5GraceInvalid || h5ActionRunning"
              :aria-label="t('settings.general.h5AccessSave')"
            >
              {{ t('settings.general.h5AccessSave') }}
            </Button>
          </div>

          <!-- Fixed port restart note -->
          <div
            v-if="h5FixedPortPendingRestart"
            data-testid="h5-access-fixed-port-restart-note"
            class="rounded-lg border border-[var(--color-warning)]/40 bg-[var(--color-warning)]/10 px-3 py-2 text-xs leading-5 text-[var(--color-text-primary)]"
          >
            {{
              t('settings.general.h5AccessFixedPortRestartNote', {
                fixedPort: String(h5Access.fixedPort),
                activePort: h5ActivePort ?? '',
              })
            }}
          </div>
        </div>

        <!-- Access URL section -->
        <div v-if="h5AccessUrl" class="mt-4 border-t border-[var(--color-border)]/60 pt-4">
          <div class="flex items-center gap-2">
            <div class="flex-1 min-w-0">
              <div class="text-xs uppercase tracking-[0.08em] text-[var(--color-text-tertiary)]">
                {{ t('settings.general.h5AccessUrl') }}
              </div>
              <div class="mt-1 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text-primary)] break-all">
                {{ h5AccessUrl }}
              </div>
            </div>
            <Button
              size="sm"
              variant="secondary"
              class="shrink-0"
              @click="() => void handleH5UrlCopy()"
              :aria-label="t('settings.general.h5AccessCopyUrl')"
            >
              <template #icon>
                <span class="material-symbols-outlined text-[14px]" aria-hidden="true">content_copy</span>
              </template>
              {{ t('settings.general.h5AccessCopy') }}
            </Button>
          </div>
        </div>

        <!-- QR code + launch URL section -->
        <div v-if="h5Access.enabled && h5AccessUrl" class="mt-4 border-t border-[var(--color-border)]/60 pt-4">
          <div class="flex flex-col gap-4 sm:flex-row">
            <div class="flex h-48 w-48 shrink-0 items-center justify-center rounded-lg border border-[var(--color-border)] bg-white p-3">
              <img
                v-if="h5QrDataUrl"
                :src="h5QrDataUrl"
                :alt="t('settings.general.h5AccessQrAlt')"
                class="h-full w-full"
              />
              <div v-else class="flex flex-col items-center gap-3 px-4 text-center">
                <span class="material-symbols-outlined text-[48px] text-neutral-400" aria-hidden="true">qr_code_2</span>
                <p class="text-xs leading-5 text-neutral-500">
                  {{ t('settings.general.h5AccessQrEmptyHint') }}
                </p>
              </div>
            </div>
            <div class="min-w-0 flex-1">
              <div class="text-xs font-medium uppercase text-[var(--color-text-tertiary)]">
                {{ t('settings.general.h5AccessQrTitle') }}
              </div>
              <p class="mt-1 text-xs leading-5 text-[var(--color-text-tertiary)]">
                {{ h5Token ? t('settings.general.h5AccessQrHint') : t('settings.general.h5AccessQrRefreshHint') }}
              </p>
              <div
                v-if="h5LaunchUrl"
                class="mt-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text-primary)] break-all"
              >
                {{ h5LaunchUrl }}
              </div>
              <div class="mt-3 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="secondary"
                  :disabled="!h5LaunchUrl || !h5Token"
                  @click="() => void handleH5LaunchUrlCopy()"
                >
                  <template #icon>
                    <span class="material-symbols-outlined text-[14px]" aria-hidden="true">content_copy</span>
                  </template>
                  {{ t('settings.general.h5AccessCopyLaunchUrl') }}
                </Button>
                <Button
                  size="sm"
                  :variant="h5Token ? 'secondary' : 'primary'"
                  :loading="h5ActionRunning"
                  @click="() => void handleH5Regenerate()"
                >
                  <template #icon>
                    <span class="material-symbols-outlined text-[14px]" aria-hidden="true">refresh</span>
                  </template>
                  {{ h5Token ? t('settings.general.h5AccessRegenerate') : t('settings.general.h5AccessGenerateToken') }}
                </Button>
              </div>
            </div>
          </div>
        </div>

        <!-- Token preview section -->
        <div v-if="h5Access.enabled" class="mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3">
          <div class="flex items-center justify-between gap-3">
            <div class="min-w-0">
              <div class="text-xs font-medium uppercase text-[var(--color-text-tertiary)]">
                {{ t('settings.general.h5AccessTokenPreview') }}
              </div>
              <div class="mt-1 break-all text-sm text-[var(--color-text-primary)]">
                {{
                  h5TokenVisible && h5Token
                    ? h5Token
                    : h5Access.tokenPreview || t('settings.general.h5AccessTokenNotAvailable')
                }}
              </div>
            </div>
            <div class="flex shrink-0 flex-wrap justify-end gap-2">
              <Button
                size="sm"
                variant="secondary"
                :disabled="!h5Token"
                @click="h5TokenVisible = !h5TokenVisible"
              >
                <template #icon>
                  <span class="material-symbols-outlined text-[14px]" aria-hidden="true">
                    {{ h5TokenVisible ? 'visibility_off' : 'visibility' }}
                  </span>
                </template>
                {{ h5TokenVisible ? t('settings.general.h5AccessHideToken') : t('settings.general.h5AccessShowToken') }}
              </Button>
              <Button
                size="sm"
                variant="danger"
                :loading="h5ActionRunning"
                @click="() => void handleH5Disable()"
              >
                <template #icon>
                  <span class="material-symbols-outlined text-[14px]" aria-hidden="true">power_off</span>
                </template>
                {{ t('settings.general.h5AccessDisable') }}
              </Button>
            </div>
          </div>
        </div>

        <!-- Safety note + error -->
        <p class="mt-4 text-xs text-[var(--color-text-tertiary)] leading-5">
          {{ t('settings.general.h5AccessSafetyNote') }}
        </p>
        <p v-if="h5AccessError" class="mt-2 text-xs text-[var(--color-error)]">
          {{ h5AccessError }}
        </p>
      </div>
    </section>

    <!-- Enable confirm dialog -->
    <Modal
      :open="h5EnableConfirmOpen"
      :title="t('settings.general.h5AccessConfirmTitle')"
      :footer="true"
      @close="() => {
        if (!h5ActionRunning) h5EnableConfirmOpen = false
      }"
    >
      <p class="text-sm leading-6 text-[var(--color-text-secondary)]">
        {{ t('settings.general.h5AccessConfirmBody') }}
      </p>
      <template #footer>
        <Button
          variant="secondary"
          :disabled="h5ActionRunning"
          @click="() => { if (!h5ActionRunning) h5EnableConfirmOpen = false }"
        >
          {{ t('common.cancel') }}
        </Button>
        <Button
          variant="danger"
          :loading="h5ActionRunning"
          @click="handleH5EnableConfirm"
        >
          {{ t('settings.general.h5AccessConfirmEnable') }}
        </Button>
      </template>
    </Modal>
  </div>
</template>
