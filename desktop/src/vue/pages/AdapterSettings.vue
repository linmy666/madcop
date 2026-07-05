<script setup lang="ts">
// v3.0 — AdapterSettings (Vue 3 SFC translation from React pages/AdapterSettings.tsx, 1034 lines)
// IM adapter settings page: pairing, Telegram/Feishu/WeChat/WhatsApp/DingTalk configuration.

import { ref, onMounted, watch, computed } from 'vue'
import { useAdapterStore } from '../stores/adapterStore'
import { useTranslation } from '../../i18n'
import Input from '../components/shared/Input.vue'
import Button from '../components/shared/Button.vue'
import DirectoryPicker from '../components/shared/DirectoryPicker.vue'
import ConfirmDialog from '../components/chat/ConfirmDialog.vue'
import QRCode from 'qrcode'

// ─── Types (from React lines 10-12) ─────────────────────────────
type ImTab = 'telegram' | 'feishu' | 'wechat' | 'dingtalk' | 'whatsapp'
type ImPlatform = 'telegram' | 'feishu' | 'wechat' | 'dingtalk' | 'whatsapp'
type AdapterUnbindTarget = 'wechatAccount' | 'dingtalkBot' | 'whatsappAccount'

// ─── Constants (from React lines 14-15) ─────────────────────────
const FEISHU_CREATE_BOT_URL = 'https://open.feishu.cn/page/openclaw?form=multiAgent'
const IM_CONFIG_DOCS_URL = 'https://madcop-haha.relakkesyang.org/im/'

// ─── Store ──────────────────────────────────────────────────────
const adapterStore = useAdapterStore()
const t = useTranslation()

// ─── Local state ────────────────────────────────────────────────
// Active IM tab
const activeIm = ref<ImTab>('telegram')

// Server —— serverUrl 不再暴露在 UI 里（见下方 Server URL 注释），
// 桌面端用 sidecar env var 注入动态端口。
const defaultProjectDir = ref('')

// Telegram
const tgBotToken = ref('')
const tgAllowedUsers = ref('')

// Feishu
const fsAppId = ref('')
const fsAppSecret = ref('')
const fsEncryptKey = ref('')
const fsVerificationToken = ref('')
const fsAllowedUsers = ref('')
const fsStreamingCard = ref(false)

// WeChat
const wcAllowedUsers = ref('')
const wechatQrUrl = ref<string | null>(null)
const wechatSessionKey = ref<string | null>(null)
const wechatStatus = ref('')
const isWechatBinding = ref(false)
const isUnbindingWechatAccount = ref(false)

// WhatsApp
const waAllowedUsers = ref('')
const whatsappQrUrl = ref<string | null>(null)
const whatsappSessionKey = ref<string | null>(null)
const whatsappStatus = ref('')
const isWhatsAppBinding = ref(false)
const isUnbindingWhatsAppAccount = ref(false)

// DingTalk
const dtClientId = ref('')
const dtClientSecret = ref('')
const dtAllowedUsers = ref('')
const dtEndpoint = ref('')
const dtPermissionCardTemplateId = ref('')
const dtRegistration = ref<{
  deviceCode: string
  verificationUriComplete: string
  qrDataUrl?: string
  intervalSeconds: number
  expiresAt: number
} | null>(null)
const dtAuthStatus = ref<'idle' | 'waiting' | 'bound' | 'error'>('idle')
const dtAuthError = ref('')
const isStartingDtAuth = ref(false)
const isUnbindingDtBot = ref(false)

// Save status
const isSaving = ref(false)
const saveStatus = ref<'idle' | 'saved' | 'error'>('idle')
const saveError = ref('')

// Pairing
const pairingCode = ref<string | null>(null)
const isGenerating = ref(false)
const pendingUnbind = ref<{ platform: ImPlatform; userId: string | number } | null>(null)
const pendingAdapterUnbind = ref<AdapterUnbindTarget | null>(null)
const isUnbinding = ref(false)

// ─── Lifecycle: fetch config on mount ───────────────────────────
onMounted(() => {
  adapterStore.fetchConfig()
})

// ─── Sync form state when config is loaded ──────────────────────
watch(
  () => adapterStore.config,
  (config) => {
    defaultProjectDir.value = config.defaultProjectDir ?? ''
    tgBotToken.value = config.telegram?.botToken ?? ''
    tgAllowedUsers.value = config.telegram?.allowedUsers?.join(', ') ?? ''
    fsAppId.value = config.feishu?.appId ?? ''
    fsAppSecret.value = config.feishu?.appSecret ?? ''
    fsEncryptKey.value = config.feishu?.encryptKey ?? ''
    fsVerificationToken.value = config.feishu?.verificationToken ?? ''
    fsAllowedUsers.value = config.feishu?.allowedUsers?.join(', ') ?? ''
    fsStreamingCard.value = config.feishu?.streamingCard ?? false
    wcAllowedUsers.value = config.wechat?.allowedUsers?.join(', ') ?? ''
    waAllowedUsers.value = config.whatsapp?.allowedUsers?.join(', ') ?? ''
    dtClientId.value = config.dingtalk?.clientId ?? ''
    dtClientSecret.value = config.dingtalk?.clientSecret ?? ''
    dtAllowedUsers.value = config.dingtalk?.allowedUsers?.join(', ') ?? ''
    dtEndpoint.value = config.dingtalk?.endpoint ?? ''
    dtPermissionCardTemplateId.value = config.dingtalk?.permissionCardTemplateId ?? ''
  },
  { immediate: false }
)

// ─── Poll WeChat login ──────────────────────────────────────────
watch(
  () => wechatSessionKey.value,
  async (key) => {
    if (!key) return

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const poll = async () => {
      try {
        const result = await adapterStore.pollWechatLogin(key!)
        if (cancelled) return
        if (result.connected) {
          wechatStatus.value = t('settings.adapters.wechatBindSuccess')
          wechatQrUrl.value = null
          wechatSessionKey.value = null
          isWechatBinding.value = false
          return
        }
        if (result.message) {
          wechatStatus.value = result.message
        }
        if (result.status === 'expired' || result.status === 'not_started') {
          wechatQrUrl.value = null
          wechatSessionKey.value = null
          isWechatBinding.value = false
          return
        }
      } catch (err) {
        if (!cancelled) wechatStatus.value = err instanceof Error ? err.message : 'WeChat bind failed'
      }

      if (!cancelled) {
        timer = setTimeout(() => void poll(), 1200)
      }
    }

    timer = setTimeout(() => void poll(), 1200)

    // Return cleanup function
    return () => {
      cancelled = true
      if (timer != null) clearTimeout(timer)
    }
  }
)

// ─── Poll WhatsApp login ────────────────────────────────────────
watch(
  () => whatsappSessionKey.value,
  async (key) => {
    if (!key) return

    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | null = null

    const poll = async () => {
      try {
        const result = await adapterStore.pollWhatsAppLogin(key!)
        if (cancelled) return
        if (result.connected) {
          whatsappStatus.value = t('settings.adapters.whatsappBindSuccess')
          whatsappQrUrl.value = null
          whatsappSessionKey.value = null
          isWhatsAppBinding.value = false
          return
        }
        if (result.qrDataUrl) {
          whatsappQrUrl.value = result.qrDataUrl
        }
        if (result.message) {
          whatsappStatus.value = result.message
        }
        if (result.status === 'expired' || result.status === 'error') {
          whatsappSessionKey.value = null
          isWhatsAppBinding.value = false
          return
        }
      } catch (err) {
        if (!cancelled) whatsappStatus.value = err instanceof Error ? err.message : t('settings.adapters.whatsappBindFailed')
      }

      if (!cancelled) {
        timer = setTimeout(() => void poll(), 1200)
      }
    }

    timer = setTimeout(() => void poll(), 1200)

    return () => {
      cancelled = true
      if (timer != null) clearTimeout(timer)
    }
  }
)

// ─── Poll DingTalk registration ─────────────────────────────────
watch(
  () => [dtRegistration.value, dtAuthStatus.value] as const,
  ([registration, status]) => {
    if (!registration || status !== 'waiting') return

    let cancelled = false
    const poll = async () => {
      if (Date.now() > registration.expiresAt) {
        dtAuthStatus.value = 'error'
        dtAuthError.value = t('settings.adapters.dingtalkAuthExpired')
        dtRegistration.value = null
        return
      }

      try {
        const result = await adapterStore.pollDingtalkRegistration(registration.deviceCode)
        if (cancelled) return
        if (result.status === 'SUCCESS') {
          dtAuthStatus.value = 'bound'
          dtRegistration.value = null
          dtAuthError.value = ''
          await adapterStore.fetchConfig()
        } else if (result.status === 'FAIL' || result.status === 'EXPIRED') {
          dtAuthStatus.value = 'error'
          dtAuthError.value = result.failReason || t('settings.adapters.dingtalkAuthFailed')
          dtRegistration.value = null
        }
      } catch (err) {
        if (!cancelled) {
          dtAuthStatus.value = 'error'
          dtAuthError.value = err instanceof Error ? err.message : t('settings.adapters.dingtalkAuthFailed')
        }
      }
    }

    const timer = setInterval(poll, Math.max(1, registration.intervalSeconds) * 1000)
    void poll()
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }
)

// ─── Actions ────────────────────────────────────────────────────
async function handleSave() {
  isSaving.value = true
  saveStatus.value = 'idle'
  saveError.value = ''
  try {
    const patch: Record<string, unknown> = {}
    const config = adapterStore.config

    if (defaultProjectDir.value) patch.defaultProjectDir = defaultProjectDir.value

    const tgUsers = tgAllowedUsers.value
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .map(Number)
      .filter((n) => !isNaN(n))

    patch.telegram = {
      botToken: tgBotToken.value || undefined,
      allowedUsers: tgUsers.length ? tgUsers : [],
    }

    const fsUsers = fsAllowedUsers.value
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

    patch.feishu = {
      appId: fsAppId.value || undefined,
      appSecret: fsAppSecret.value || undefined,
      encryptKey: fsEncryptKey.value || undefined,
      verificationToken: fsVerificationToken.value || undefined,
      allowedUsers: fsUsers.length ? fsUsers : [],
      streamingCard: fsStreamingCard.value,
    }

    const wcUsers = wcAllowedUsers.value
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

    patch.wechat = {
      ...config.wechat,
      allowedUsers: wcUsers.length ? wcUsers : [],
    }

    const waUsers = waAllowedUsers.value
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

    patch.whatsapp = {
      ...config.whatsapp,
      allowedUsers: waUsers.length ? waUsers : [],
    }

    const dtUsers = dtAllowedUsers.value
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)

    patch.dingtalk = {
      clientId: dtClientId.value || undefined,
      clientSecret: dtClientSecret.value || undefined,
      allowedUsers: dtUsers.length ? dtUsers : [],
      endpoint: dtEndpoint.value || undefined,
      permissionCardTemplateId: dtPermissionCardTemplateId.value || undefined,
    }

    await adapterStore.updateConfig(patch)
    saveStatus.value = 'saved'
    setTimeout(() => (saveStatus.value = 'idle'), 2000)
  } catch (err) {
    saveStatus.value = 'error'
    saveError.value = err instanceof Error ? err.message : 'Save failed'
  } finally {
    isSaving.value = false
  }
}

async function handleGenerateCode() {
  isGenerating.value = true
  try {
    const code = await adapterStore.generatePairingCode()
    pairingCode.value = code
  } catch (err) {
    console.error('Failed to generate pairing code:', err)
  } finally {
    isGenerating.value = false
  }
}

async function handleWechatBind() {
  isWechatBinding.value = true
  wechatStatus.value = ''
  try {
    const result = await adapterStore.startWechatLogin()
    if (!result.qrcodeUrl) {
      throw new Error(result.message || 'WeChat QR URL missing')
    }
    const qrDataUrl = await QRCode.toDataURL(result.qrcodeUrl, {
      errorCorrectionLevel: 'M',
      margin: 1,
      scale: 8,
    })
    wechatQrUrl.value = qrDataUrl
    wechatSessionKey.value = result.sessionKey
    wechatStatus.value = result.message
  } catch (err) {
    wechatStatus.value = err instanceof Error ? err.message : 'WeChat bind failed'
    isWechatBinding.value = false
  }
}

async function handleWhatsAppBind() {
  isWhatsAppBinding.value = true
  whatsappStatus.value = ''
  try {
    const result = await adapterStore.startWhatsAppLogin()
    if (result.qrDataUrl) {
      whatsappQrUrl.value = result.qrDataUrl
    }
    whatsappSessionKey.value = result.sessionKey
    whatsappStatus.value = result.message
  } catch (err) {
    whatsappStatus.value = err instanceof Error ? err.message : t('settings.adapters.whatsappBindFailed')
    isWhatsAppBinding.value = false
  }
}

async function handleStartDingtalkAuth() {
  isStartingDtAuth.value = true
  dtAuthStatus.value = 'idle'
  dtAuthError.value = ''
  try {
    const begin = await adapterStore.beginDingtalkRegistration()
    dtRegistration.value = {
      deviceCode: begin.deviceCode,
      verificationUriComplete: begin.verificationUriComplete,
      qrDataUrl: begin.qrDataUrl,
      intervalSeconds: begin.intervalSeconds,
      expiresAt: Date.now() + begin.expiresInSeconds * 1000,
    }
    dtAuthStatus.value = 'waiting'
  } catch (err) {
    dtAuthStatus.value = 'error'
    dtAuthError.value = err instanceof Error ? err.message : t('settings.adapters.dingtalkAuthFailed')
  } finally {
    isStartingDtAuth.value = false
  }
}

async function handleUnbindWechatAccount() {
  isUnbindingWechatAccount.value = true
  wechatStatus.value = ''
  try {
    await adapterStore.unbindWechatAccount()
    await adapterStore.fetchConfig()
    wechatQrUrl.value = null
    wechatSessionKey.value = null
    wechatStatus.value = t('settings.adapters.wechatUnbound')
  } catch (err) {
    wechatStatus.value = err instanceof Error ? err.message : t('settings.adapters.wechatUnbindFailed')
  } finally {
    isUnbindingWechatAccount.value = false
    isWechatBinding.value = false
    pendingAdapterUnbind.value = null
  }
}

async function handleUnbindDingtalkBot() {
  isUnbindingDtBot.value = true
  dtAuthError.value = ''
  try {
    await adapterStore.unbindDingtalkBot()
    dtAuthStatus.value = 'idle'
    dtRegistration.value = null
    await adapterStore.fetchConfig()
  } catch (err) {
    dtAuthStatus.value = 'error'
    dtAuthError.value = err instanceof Error ? err.message : t('settings.adapters.dingtalkUnbindFailed')
  } finally {
    isUnbindingDtBot.value = false
    pendingAdapterUnbind.value = null
  }
}

async function handleUnbindWhatsAppAccount() {
  isUnbindingWhatsAppAccount.value = true
  whatsappStatus.value = ''
  try {
    await adapterStore.unbindWhatsAppAccount()
    await adapterStore.fetchConfig()
    whatsappQrUrl.value = null
    whatsappSessionKey.value = null
    whatsappStatus.value = t('settings.adapters.whatsappUnbound')
  } catch (err) {
    whatsappStatus.value = err instanceof Error ? err.message : t('settings.adapters.whatsappUnbindFailed')
  } finally {
    isUnbindingWhatsAppAccount.value = false
    isWhatsAppBinding.value = false
    pendingAdapterUnbind.value = null
  }
}

function handleUnbind(platform: ImPlatform, userId: string | number) {
  pendingUnbind.value = { platform, userId }
}

async function confirmUnbind() {
  if (!pendingUnbind.value) return
  isUnbinding.value = true
  try {
    await adapterStore.removePairedUser(pendingUnbind.value.platform, pendingUnbind.value.userId)
    await adapterStore.fetchConfig()
    pendingUnbind.value = null
  } finally {
    isUnbinding.value = false
  }
}

// ─── Computed ───────────────────────────────────────────────────
const allPairedUsers = computed(() => {
  const config = adapterStore.config
  return [
    ...(config.telegram?.pairedUsers ?? []).map((u) => ({ ...u, platform: 'telegram' as const })),
    ...(config.feishu?.pairedUsers ?? []).map((u) => ({ ...u, platform: 'feishu' as const })),
    ...(config.wechat?.pairedUsers ?? []).map((u) => ({ ...u, platform: 'wechat' as const })),
    ...(config.dingtalk?.pairedUsers ?? []).map((u) => ({ ...u, platform: 'dingtalk' as const })),
    ...(config.whatsapp?.pairedUsers ?? []).map((u) => ({ ...u, platform: 'whatsapp' as const })),
  ]
})

const pairingExpiry = computed(() => {
  return adapterStore.config.pairing?.expiresAt
})

const isPairingActive = computed(() => {
  return pairingExpiry.value ? Date.now() < pairingExpiry.value : false
})

const minutesLeft = computed(() => {
  return pairingExpiry.value ? Math.max(0, Math.ceil((pairingExpiry.value - Date.now()) / 60000)) : 0
})

const hasSavedFeishuCredentials = computed(() => {
  return Boolean(adapterStore.config.feishu?.appId && adapterStore.config.feishu?.appSecret)
})

// ─── Helper: ImTabButton inline render ──────────────────────────
function getTabButtonClass(active: boolean): string {
  return `relative px-4 py-2.5 text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)] focus-visible:ring-inset ${
    active
      ? 'text-[var(--color-text-primary)] font-semibold after:absolute after:left-3 after:right-3 after:bottom-0 after:h-[2px] after:bg-[var(--color-brand)]'
      : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]'
  }`
}

</script>

<template>
  <!-- Loading state -->
  <div v-if="adapterStore.isLoading" class="flex items-center justify-center py-12 text-[var(--color-text-tertiary)]">
    <span class="material-symbols-outlined animate-spin text-[20px] mr-2">progress_activity</span>
    Loading...
  </div>

  <!-- Main content -->
  <div v-else class="max-w-2xl space-y-8">
    <!-- Description -->
    <div>
      <p class="text-sm leading-6 text-[var(--color-text-secondary)]">
        {{ t('settings.adapters.description') }}
        <a
          :href="IM_CONFIG_DOCS_URL"
          target="_blank"
          rel="noopener noreferrer"
          class="inline-flex items-center gap-1 font-medium text-[var(--color-brand)] transition-colors hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-bg)]"
        >
          {{ t('settings.adapters.configurationDocs') }}
          <span class="material-symbols-outlined text-[14px]" aria-hidden="true">open_in_new</span>
        </a>
        {{ t('settings.adapters.descriptionAfterDocs') }}
      </p>
    </div>

    <!-- Pairing -->
    <section class="rounded-xl border border-[var(--color-border)] overflow-hidden">
      <div class="flex items-center gap-2 px-4 py-3 bg-[var(--color-surface-hover)] border-b border-[var(--color-border)]">
        <span class="material-symbols-outlined text-[18px] text-[var(--color-text-secondary)]">link</span>
        <span class="text-sm font-semibold text-[var(--color-text-primary)]">{{ t('settings.adapters.pairing') }}</span>
      </div>
      <div class="p-4 space-y-4">
        <p class="text-sm text-[var(--color-text-secondary)]">{{ t('settings.adapters.pairingDesc') }}</p>

        <!-- Generate code -->
        <div class="flex items-center gap-3">
          <Button @click="handleGenerateCode" :loading="isGenerating">
            {{ pairingCode || isPairingActive ? t('settings.adapters.regenerateCode') : t('settings.adapters.generateCode') }}
          </Button>
          <div v-if="pairingCode" class="flex items-center gap-2">
            <span class="font-mono text-2xl font-bold tracking-[0.3em] text-[var(--color-brand)]">
              {{ pairingCode }}
            </span>
            <span class="text-xs text-[var(--color-text-tertiary)]">
              {{ t('settings.adapters.codeExpiresIn') }} 60 {{ t('settings.adapters.minutes') }}
            </span>
          </div>
          <span v-else-if="isPairingActive" class="text-xs text-[var(--color-text-tertiary)]">
            {{ t('settings.adapters.codeExpiresIn') }} {{ minutesLeft }} {{ t('settings.adapters.minutes') }}
          </span>
        </div>
        <p v-if="pairingCode" class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.adapters.pairingCodeHint') }}</p>

        <!-- Paired users list -->
        <div>
          <h4 class="text-sm font-medium text-[var(--color-text-primary)] mb-2">{{ t('settings.adapters.pairedUsers') }}</h4>
          <p v-if="allPairedUsers.length === 0" class="text-sm text-[var(--color-text-tertiary)]">{{ t('settings.adapters.noPairedUsers') }}</p>
          <div v-else class="space-y-2">
            <div
              v-for="user in allPairedUsers"
              :key="`${user.platform}-${user.userId}`"
              class="flex items-center justify-between px-3 py-2 rounded-lg bg-[var(--color-surface-hover)]"
            >
              <div class="flex items-center gap-2">
                <span class="text-xs px-1.5 py-0.5 rounded bg-[var(--color-surface)] text-[var(--color-text-secondary)]">
                  {{ t(`settings.adapters.platform.${user.platform}`) }}
                </span>
                <span class="text-sm text-[var(--color-text-primary)]">{{ user.displayName }}</span>
                <span class="text-xs text-[var(--color-text-tertiary)]">
                  {{ new Date(user.pairedAt).toLocaleDateString() }}
                </span>
              </div>
              <button
                @click="handleUnbind(user.platform, user.userId)"
                class="text-xs text-[var(--color-error)] hover:underline cursor-pointer"
              >
                {{ t('settings.adapters.unbind') }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Default Project -->
    <div class="flex flex-col gap-1">
      <label class="text-sm font-medium text-[var(--color-text-primary)]">
        {{ t('settings.adapters.defaultProject') }}
      </label>
      <DirectoryPicker :value="defaultProjectDir" @change="defaultProjectDir = $event" />
      <p class="text-xs text-[var(--color-text-tertiary)]">
        {{ t('settings.adapters.defaultProjectHint') }}
      </p>
    </div>

    <!-- IM Adapter Tabs -->
    <section class="rounded-xl border border-[var(--color-border)] overflow-hidden">
      <div role="tablist" aria-label="IM adapter" class="flex items-stretch border-b border-[var(--color-border)] bg-[var(--color-surface-hover)]">
        <button
          type="button"
          role="tab"
          :aria-selected="activeIm === 'telegram'"
          @click="activeIm = 'telegram'"
          :class="getTabButtonClass(activeIm === 'telegram')"
        >
          {{ t('settings.adapters.telegram') }}
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="activeIm === 'feishu'"
          @click="activeIm = 'feishu'"
          :class="getTabButtonClass(activeIm === 'feishu')"
        >
          {{ t('settings.adapters.feishu') }}
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="activeIm === 'wechat'"
          @click="activeIm = 'wechat'"
          :class="getTabButtonClass(activeIm === 'wechat')"
        >
          {{ t('settings.adapters.wechat') }}
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="activeIm === 'dingtalk'"
          @click="activeIm = 'dingtalk'"
          :class="getTabButtonClass(activeIm === 'dingtalk')"
        >
          {{ t('settings.adapters.dingtalk') }}
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="activeIm === 'whatsapp'"
          @click="activeIm = 'whatsapp'"
          :class="getTabButtonClass(activeIm === 'whatsapp')"
        >
          {{ t('settings.adapters.whatsapp') }}
        </button>
      </div>

      <!-- Feishu tab -->
      <div v-if="activeIm === 'feishu'" class="p-4 space-y-4">
        <div v-if="!hasSavedFeishuCredentials" class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div class="flex min-w-0 gap-3">
              <span class="material-symbols-outlined mt-0.5 text-[20px] text-[var(--color-brand)]">smart_toy</span>
              <div class="min-w-0">
                <h4 class="text-sm font-semibold text-[var(--color-text-primary)]">{{ t('settings.adapters.feishuCreateBotTitle') }}</h4>
                <p class="mt-1 text-xs leading-5 text-[var(--color-text-tertiary)]">{{ t('settings.adapters.feishuCreateBotDesc') }}</p>
                <ol class="mt-2 space-y-1 text-xs leading-5 text-[var(--color-text-secondary)]">
                  <li>1. {{ t('settings.adapters.feishuCreateBotStepCreate') }}</li>
                  <li>2. {{ t('settings.adapters.feishuCreateBotStepFill') }}</li>
                </ol>
              </div>
            </div>
            <a
              :href="FEISHU_CREATE_BOT_URL"
              target="_blank"
              rel="noopener noreferrer"
              class="inline-flex h-9 shrink-0 items-center justify-center gap-1.5 rounded-[var(--radius-md)] bg-[image:var(--gradient-btn-primary)] px-3 text-xs font-medium text-[var(--color-btn-primary-fg)] shadow-[var(--shadow-button-primary)] transition-colors hover:bg-[image:var(--gradient-btn-primary-hover)] hover:brightness-105 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--color-surface)]"
            >
              {{ t('settings.adapters.feishuCreateBotAction') }}
              <span class="material-symbols-outlined text-[14px]">open_in_new</span>
            </a>
          </div>
        </div>
        <div class="grid grid-cols-2 gap-4">
          <Input
            :label="t('settings.adapters.appId')"
            :value="fsAppId"
            @update:value="fsAppId = $event"
            :placeholder="t('settings.adapters.appIdPlaceholder')"
          />
          <Input
            :label="t('settings.adapters.appSecret')"
            type="password"
            :value="fsAppSecret"
            @update:value="fsAppSecret = $event"
            :placeholder="t('settings.adapters.appSecretPlaceholder')"
          />
        </div>
        <div class="grid grid-cols-2 gap-4">
          <Input
            :label="t('settings.adapters.encryptKey')"
            type="password"
            :value="fsEncryptKey"
            @update:value="fsEncryptKey = $event"
            :placeholder="t('settings.adapters.encryptKeyPlaceholder')"
          />
          <Input
            :label="t('settings.adapters.verificationToken')"
            type="password"
            :value="fsVerificationToken"
            @update:value="fsVerificationToken = $event"
            :placeholder="t('settings.adapters.verificationTokenPlaceholder')"
          />
        </div>
        <div class="flex flex-col gap-1">
          <Input
            :label="t('settings.adapters.allowedUsers')"
            :value="fsAllowedUsers"
            @update:value="fsAllowedUsers = $event"
            :placeholder="t('settings.adapters.fsAllowedUsersPlaceholder')"
          />
          <p class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.adapters.allowedUsersHint') }}</p>
        </div>
        <label class="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            :checked="fsStreamingCard"
            @change="fsStreamingCard = ($event.target as HTMLInputElement).checked"
            class="w-4 h-4 rounded border-[var(--color-border)] accent-[var(--color-brand)]"
          />
          <div>
            <span class="text-sm text-[var(--color-text-primary)]">{{ t('settings.adapters.streamingCard') }}</span>
            <p class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.adapters.streamingCardDesc') }}</p>
          </div>
        </label>
      </div>

      <!-- WeChat tab -->
      <div v-else-if="activeIm === 'wechat'" class="p-4 space-y-4">
        <div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3">
          <div class="flex items-center justify-between gap-4">
            <div>
              <div class="text-sm font-medium text-[var(--color-text-primary)]">
                {{ adapterStore.config.wechat?.accountId ? t('settings.adapters.wechatConnected') : t('settings.adapters.wechatNotConnected') }}
              </div>
              <p class="text-xs text-[var(--color-text-tertiary)]">
                {{ t('settings.adapters.wechatQrHint') }}
              </p>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <Button @click="handleWechatBind" :loading="isWechatBinding && !wechatQrUrl" size="sm">
                {{ adapterStore.config.wechat?.accountId ? t('settings.adapters.wechatRebind') : t('settings.adapters.wechatBind') }}
              </Button>
              <Button
                v-if="adapterStore.config.wechat?.accountId"
                @click="pendingAdapterUnbind = 'wechatAccount'"
                :loading="isUnbindingWechatAccount"
                size="sm"
                variant="danger"
              >
                {{ t('settings.adapters.wechatUnbindAccount') }}
              </Button>
            </div>
          </div>

          <div v-if="wechatQrUrl" class="flex items-start gap-4">
            <img
              :src="wechatQrUrl"
              :alt="t('settings.adapters.wechatQrAlt')"
              class="h-40 w-40 rounded-lg border border-[var(--color-border)] bg-white object-contain p-2"
            />
            <div class="pt-2 text-sm text-[var(--color-text-secondary)]">
              {{ wechatStatus || t('settings.adapters.wechatWaiting') }}
            </div>
          </div>

          <p v-else-if="wechatStatus" class="text-sm text-[var(--color-text-secondary)]">{{ wechatStatus }}</p>
        </div>

        <div class="flex flex-col gap-1">
          <Input
            :label="t('settings.adapters.allowedUsers')"
            :value="wcAllowedUsers"
            @update:value="wcAllowedUsers = $event"
            :placeholder="t('settings.adapters.wcAllowedUsersPlaceholder')"
          />
          <p class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.adapters.wechatAllowedUsersHint') }}</p>
        </div>
      </div>

      <!-- DingTalk tab -->
      <div v-else-if="activeIm === 'dingtalk'" class="p-4 space-y-4">
        <div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3">
          <div class="flex items-start justify-between gap-4">
            <div>
              <h4 class="text-sm font-semibold text-[var(--color-text-primary)]">{{ t('settings.adapters.dingtalkQrTitle') }}</h4>
              <p class="mt-1 text-xs text-[var(--color-text-tertiary)]">{{ t('settings.adapters.dingtalkQrDesc') }}</p>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <Button @click="handleStartDingtalkAuth" :loading="isStartingDtAuth" size="sm">
                {{ t('settings.adapters.dingtalkStartAuth') }}
              </Button>
              <Button
                v-if="adapterStore.config.dingtalk?.clientId || dtClientId"
                @click="pendingAdapterUnbind = 'dingtalkBot'"
                :loading="isUnbindingDtBot"
                size="sm"
                variant="danger"
              >
                {{ t('settings.adapters.dingtalkUnbindBot') }}
              </Button>
            </div>
          </div>

          <div v-if="dtRegistration" class="flex flex-wrap items-center gap-4">
            <img
              v-if="dtRegistration.qrDataUrl"
              :src="dtRegistration.qrDataUrl"
              :alt="t('settings.adapters.dingtalkQrAlt')"
              class="h-40 w-40 rounded-lg border border-[var(--color-border)] bg-white object-contain p-2"
            />
            <div class="min-w-0 flex-1 space-y-2">
              <p class="text-sm text-[var(--color-text-primary)]">{{ t('settings.adapters.dingtalkWaiting') }}</p>
              <a
                :href="dtRegistration.verificationUriComplete"
                target="_blank"
                rel="noreferrer"
                class="block truncate text-xs text-[var(--color-brand)] hover:underline"
              >
                {{ dtRegistration.verificationUriComplete }}
              </a>
            </div>
          </div>

          <p v-if="dtAuthStatus === 'bound'" class="text-sm text-[var(--color-success)]">{{ t('settings.adapters.dingtalkBound') }}</p>
          <p v-if="dtAuthStatus === 'error'" class="text-sm text-[var(--color-error)]">{{ dtAuthError }}</p>
        </div>

        <div class="grid grid-cols-2 gap-4">
          <Input
            :label="t('settings.adapters.dingtalkClientId')"
            :value="dtClientId"
            @update:value="dtClientId = $event"
            :placeholder="t('settings.adapters.dingtalkClientIdPlaceholder')"
          />
          <Input
            :label="t('settings.adapters.dingtalkClientSecret')"
            type="password"
            :value="dtClientSecret"
            @update:value="dtClientSecret = $event"
            :placeholder="t('settings.adapters.dingtalkClientSecretPlaceholder')"
          />
        </div>
        <Input
          :label="t('settings.adapters.dingtalkEndpoint')"
          :value="dtEndpoint"
          @update:value="dtEndpoint = $event"
          :placeholder="t('settings.adapters.dingtalkEndpointPlaceholder')"
        />
        <div class="flex flex-col gap-1">
          <Input
            :label="t('settings.adapters.dingtalkPermissionCardTemplateId')"
            :value="dtPermissionCardTemplateId"
            @update:value="dtPermissionCardTemplateId = $event"
            :placeholder="t('settings.adapters.dingtalkPermissionCardTemplateIdPlaceholder')"
          />
          <p class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.adapters.dingtalkPermissionCardTemplateIdHint') }}</p>
        </div>
        <div class="flex flex-col gap-1">
          <Input
            :label="t('settings.adapters.allowedUsers')"
            :value="dtAllowedUsers"
            @update:value="dtAllowedUsers = $event"
            :placeholder="t('settings.adapters.dtAllowedUsersPlaceholder')"
          />
          <p class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.adapters.allowedUsersHint') }}</p>
        </div>
      </div>

      <!-- Telegram tab -->
      <div v-else-if="activeIm === 'telegram'" class="p-4 space-y-4">
        <Input
          :label="t('settings.adapters.botToken')"
          type="password"
          :value="tgBotToken"
          @update:value="tgBotToken = $event"
          :placeholder="t('settings.adapters.botTokenPlaceholder')"
        />
        <div class="flex flex-col gap-1">
          <Input
            :label="t('settings.adapters.allowedUsers')"
            :value="tgAllowedUsers"
            @update:value="tgAllowedUsers = $event"
            :placeholder="t('settings.adapters.tgAllowedUsersPlaceholder')"
          />
          <p class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.adapters.allowedUsersHint') }}</p>
        </div>
      </div>

      <!-- WhatsApp tab -->
      <div v-else-if="activeIm === 'whatsapp'" class="p-4 space-y-4">
        <div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4 space-y-3">
          <div class="flex items-center justify-between gap-4">
            <div>
              <div class="text-sm font-medium text-[var(--color-text-primary)]">
                {{ adapterStore.config.whatsapp?.accountJid ? t('settings.adapters.whatsappConnected') : t('settings.adapters.whatsappNotConnected') }}
              </div>
              <p class="text-xs text-[var(--color-text-tertiary)]">
                {{ t('settings.adapters.whatsappQrHint') }}
              </p>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <Button @click="handleWhatsAppBind" :loading="isWhatsAppBinding && !whatsappQrUrl" size="sm">
                {{ adapterStore.config.whatsapp?.accountJid ? t('settings.adapters.whatsappRebind') : t('settings.adapters.whatsappBind') }}
              </Button>
              <Button
                v-if="adapterStore.config.whatsapp?.accountJid"
                @click="pendingAdapterUnbind = 'whatsappAccount'"
                :loading="isUnbindingWhatsAppAccount"
                size="sm"
                variant="danger"
              >
                {{ t('settings.adapters.whatsappUnbindAccount') }}
              </Button>
            </div>
          </div>

          <p v-if="adapterStore.config.whatsapp?.accountJid" class="text-xs text-[var(--color-text-tertiary)]">
            {{ adapterStore.config.whatsapp.accountJid }}
          </p>

          <div v-if="whatsappQrUrl" class="flex items-start gap-4">
            <img
              :src="whatsappQrUrl"
              :alt="t('settings.adapters.whatsappQrAlt')"
              class="h-40 w-40 rounded-lg border border-[var(--color-border)] bg-white object-contain p-2"
            />
            <div class="pt-2 text-sm text-[var(--color-text-secondary)]">
              {{ whatsappStatus || t('settings.adapters.whatsappWaiting') }}
            </div>
          </div>

          <p v-else-if="whatsappStatus" class="text-sm text-[var(--color-text-secondary)]">{{ whatsappStatus }}</p>
        </div>

        <div class="flex flex-col gap-1">
          <Input
            :label="t('settings.adapters.allowedUsers')"
            :value="waAllowedUsers"
            @update:value="waAllowedUsers = $event"
            :placeholder="t('settings.adapters.waAllowedUsersPlaceholder')"
          />
          <p class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.adapters.whatsappAllowedUsersHint') }}</p>
        </div>
      </div>
    </section>

    <!-- Save -->
    <div class="flex items-center gap-3">
      <Button @click="handleSave" :loading="isSaving">
        {{ saveStatus === 'saved' ? t('settings.adapters.saved') : t('settings.adapters.save') }}
      </Button>
      <span v-if="saveStatus === 'saved'" class="text-sm text-[var(--color-success)]">
        <span class="material-symbols-outlined text-[16px] align-middle mr-1">check_circle</span>
        {{ t('settings.adapters.saved') }}
      </span>
      <span v-else-if="saveStatus === 'error'" class="text-sm text-[var(--color-error)]">
        <span class="material-symbols-outlined text-[16px] align-middle mr-1">error</span>
        {{ saveError }}
      </span>
    </div>

    <!-- ConfirmDialog: unbind user -->
    <ConfirmDialog
      :open="pendingUnbind !== null"
      @close="() => {
        if (isUnbinding) return
        pendingUnbind = null
      }"
      @confirm="confirmUnbind"
      :title="t('settings.adapters.unbind')"
      :body="t('settings.adapters.unbindConfirm')"
      :confirm-label="t('settings.adapters.unbind')"
      :cancel-label="t('common.cancel')"
      confirm-variant="danger"
      :loading="isUnbinding"
    />

    <!-- ConfirmDialog: unbind adapter account -->
    <ConfirmDialog
      :open="pendingAdapterUnbind !== null"
      @close="() => {
        if (isUnbindingWechatAccount || isUnbindingDtBot || isUnbindingWhatsAppAccount) return
        pendingAdapterUnbind = null
      }"
      @confirm="pendingAdapterUnbind === 'wechatAccount'
        ? handleUnbindWechatAccount
        : pendingAdapterUnbind === 'whatsappAccount'
          ? handleUnbindWhatsAppAccount
          : handleUnbindDingtalkBot"
      :title="pendingAdapterUnbind === 'wechatAccount'
        ? t('settings.adapters.wechatUnbindAccount')
        : pendingAdapterUnbind === 'whatsappAccount'
          ? t('settings.adapters.whatsappUnbindAccount')
          : t('settings.adapters.dingtalkUnbindBot')"
      :body="pendingAdapterUnbind === 'wechatAccount'
        ? t('settings.adapters.wechatUnbindAccountConfirm')
        : pendingAdapterUnbind === 'whatsappAccount'
          ? t('settings.adapters.whatsappUnbindAccountConfirm')
          : t('settings.adapters.dingtalkUnbindBotConfirm')"
      :confirm-label="pendingAdapterUnbind === 'wechatAccount'
        ? t('settings.adapters.wechatUnbindAccount')
        : pendingAdapterUnbind === 'whatsappAccount'
          ? t('settings.adapters.whatsappUnbindAccount')
          : t('settings.adapters.dingtalkUnbindBot')"
      :cancel-label="t('common.cancel')"
      confirm-variant="danger"
      :loading="isUnbindingWechatAccount || isUnbindingDtBot || isUnbindingWhatsAppAccount"
    />
  </div>
</template>
