<script setup lang="ts">
// v3.0 — AboutSettings (Vue 3 SFC)
// Direct translation of React Settings.tsx AboutSettings (lines 4269-4661)
import { ref, onMounted, computed, watch } from 'vue'
import { useSettingsStore, type UpdateProxySettings } from '../stores/settingsStore'
import { useUpdateStore } from '../stores/updateStore'
import { useTranslation } from '../../i18n'
import { getDesktopHost } from '../../lib/desktopHost'
import { publicAssetPath } from '../../lib/publicAsset'
import { formatBytes } from '../../lib/formatBytes'
import Button from '../components/shared/Button.vue'
import Input from '../components/shared/Input.vue'
import MarkdownRenderer from '../components/shared/MarkdownRenderer.vue'

// ─── Constants ───────────────────────────────────────────────
// MadCop Agent — author & project info.
// v2.6.0: Author is 林芮翰 (GitHub @linmy666). B站 is the only Chinese
// social channel; Douyin / Xiaohongshu removed by author request.
const GITHUB_REPO = 'https://github.com/linmy666/madcop'
const GITHUB_ISSUES = `${GITHUB_REPO}/issues`
const GITHUB_RELEASES = `${GITHUB_REPO}/releases`
const AUTHOR_GITHUB = 'https://github.com/linmy666'
const AUTHOR_NAME = '林芮翰'
const SOCIAL_LINKS = [
  {
    // v2.6.0: GitHub removed — already shown in the Author block above
    // (no reason to list it twice).
    name: 'Bilibili',
    icon: '/icons/bilibili.svg',
    url: 'https://space.bilibili.com/262182743',
    label: AUTHOR_NAME,
  },
] as const

// ─── Reactive state ──────────────────────────────────────────
const t = useTranslation()
const settingsStore = useSettingsStore()
const updateStore = useUpdateStore()

const version = ref('')
const showUpdateProxyAdvanced = ref(false)
const updateProxyDraft = ref<UpdateProxySettings>({ ...settingsStore.updateProxy })
const updateProxySaveError = ref<string | null>(null)
const isSavingUpdateProxy = ref(false)

// ─── Lifecycle ───────────────────────────────────────────────
onMounted(async () => {
  try {
    const host = getDesktopHost()
    version.value = await host.app.getVersion()
  } catch {
    version.value = ''
  }

  await updateStore.initialize()
})

// Sync draft when store updateProxy changes
const updateProxy = computed(() => settingsStore.updateProxy)
const updateProxyWatch = updateProxy.value // captured for watch
// We'll use a watcher approach
import { watch } from 'vue'
watch(updateProxy, (newVal) => {
  updateProxyDraft.value = { ...newVal }
  updateProxySaveError.value = null
}, { deep: true })

// ─── Helpers ─────────────────────────────────────────────────
function isValidHttpProxyUrl(value: string): boolean {
  try {
    const url = new URL(value)
    return url.protocol === 'http:' || url.protocol === 'https:'
  } catch {
    return false
  }
}

const openUrl = (url: string) => {
  void getDesktopHost().shell.open(url).catch(() => window.open(url, '_blank'))
}

const checkedAtText = computed(() => {
  if (!updateStore.checkedAt) return null
  return new Date(updateStore.checkedAt).toLocaleString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    month: 'short',
    day: 'numeric',
  })
})

const updateProxyModes = [
  {
    value: 'system' as const,
    label: t('update.proxyModeSystem'),
    description: t('update.proxyModeSystemDescription'),
  },
  {
    value: 'manual' as const,
    label: t('update.proxyModeManual'),
    description: t('update.proxyModeManualDescription'),
  },
]

const manualProxyUrl = computed(() => updateProxyDraft.value.url.trim())
const manualProxyError = computed(() => {
  if (updateProxyDraft.value.mode === 'manual' && !manualProxyUrl.value) {
    return t('update.proxyUrlRequired')
  }
  if (updateProxyDraft.value.mode === 'manual' && !isValidHttpProxyUrl(manualProxyUrl.value)) {
    return t('update.proxyUrlInvalid')
  }
  return null
})

const updateProxyDirty = computed(() => {
  return (
    updateProxyDraft.value.mode !== updateProxy.value.mode ||
    updateProxyDraft.value.url.trim() !== updateProxy.value.url.trim()
  )
})

const saveUpdateProxy = async () => {
  if (manualProxyError.value) {
    updateProxySaveError.value = manualProxyError.value
    return
  }

  isSavingUpdateProxy.value = true
  updateProxySaveError.value = null
  try {
    await settingsStore.setUpdateProxy({
      mode: updateProxyDraft.value.mode,
      url: manualProxyUrl.value,
    })
  } catch (error) {
    updateProxySaveError.value = error instanceof Error ? error.message : String(error)
  } finally {
    isSavingUpdateProxy.value = false
  }
}

const hasKnownProgress = computed(
  () => typeof updateStore.totalBytes === 'number' && updateStore.totalBytes > 0,
)

const downloadedText = computed(() => formatBytes(updateStore.downloadedBytes))

const updateDescription = computed(() => {
  if (updateStore.status === 'checking') return t('update.checking')
  if (updateStore.error) return t('update.failed', { error: updateStore.error })
  if (updateStore.status === 'downloading') {
    return hasKnownProgress.value
      ? t('update.progress', { progress: String(updateStore.progressPercent) })
      : t('update.progressBytes', { downloaded: downloadedText.value })
  }
  if (updateStore.status === 'downloaded') return t('update.downloaded')
  if (updateStore.status === 'installing') return t('update.installing')
  if (updateStore.status === 'restarting') return t('update.restarting')
  if (updateStore.status === 'available' && updateStore.availableVersion) {
    return t('update.newVersion', { version: updateStore.availableVersion })
  }
  if (updateStore.status === 'up-to-date') {
    return t('update.upToDate', { version: version.value || t('update.currentVersionUnknown') })
  }
  return t('update.idle')
})
</script>

<template>
  <div class="w-full min-w-0 max-w-lg mx-auto flex flex-col items-center py-6">
    <!-- Logo + App Name + Version -->
    <img
      :src="publicAssetPath('mascot.png?v=2633')"
      alt="MadCop Agent"
      class="w-20 h-20 mb-4"
    />
    <h1 class="text-xl font-bold text-[var(--color-text-primary)]">MadCop Agent</h1>
    <div v-if="version" class="mt-1 flex items-center gap-2 text-xs text-[var(--color-text-tertiary)]">
      <span>{{ t('settings.about.version') }} {{ version }}</span>
      <span class="text-[var(--color-border)]">·</span>
      <button
        @click="() => openUrl(GITHUB_RELEASES)"
        class="rounded-[var(--radius-sm)] text-[var(--color-text-accent)] transition-colors hover:text-[var(--color-brand)] focus:outline-none focus:shadow-[var(--shadow-focus-ring)]"
      >
        {{ t('settings.about.changelog') }}
      </button>
    </div>

    <!-- GitHub Repo -->
    <div class="mt-6 w-full">
      <button
        @click="() => openUrl(GITHUB_REPO)"
        class="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors cursor-pointer"
      >
        <img :src="publicAssetPath('icons/github.svg')" alt="GitHub" class="w-5 h-5 opacity-70" />
        <div class="flex-1 text-left">
          <div class="text-sm font-medium text-[var(--color-text-primary)]">linmy666/madcop</div>
          <div class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.about.starHint') }}</div>
        </div>
      </button>
    </div>

    <!-- Updates Card -->
    <div class="mt-4 w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-4">
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class="text-sm font-medium text-[var(--color-text-primary)]">{{ t('settings.about.updates') }}</div>
          <div class="text-xs text-[var(--color-text-tertiary)] mt-1">
            {{ t('settings.about.updatesDesc') }}
          </div>
        </div>
        <Button
          size="sm"
          variant="secondary"
          @click="() => updateStore.checkForUpdates()"
          :loading="updateStore.status === 'checking'"
        >
          {{ t('update.checkNow') }}
        </Button>
      </div>

      <div class="mt-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3">
        <div class="flex items-center justify-between gap-3">
          <div>
            <div class="text-xs uppercase tracking-[0.14em] text-[var(--color-text-tertiary)]">
              {{ t('settings.about.version') }}
            </div>
            <div class="text-sm font-medium text-[var(--color-text-primary)] mt-1">
              {{ version || t('update.currentVersionUnknown') }}
            </div>
          </div>

          <div v-if="updateStore.availableVersion" class="text-right">
            <div class="text-xs uppercase tracking-[0.14em] text-[var(--color-text-tertiary)]">
              {{ t('update.availableLabel') }}
            </div>
            <div class="text-sm font-medium text-[var(--color-text-primary)] mt-1">
              {{ updateStore.availableVersion }}
            </div>
          </div>
        </div>

        <p :class="['mt-3 text-sm', updateStore.error ? 'text-[var(--color-error)]' : 'text-[var(--color-text-secondary)]']">
          {{ updateDescription }}
        </p>

        <p v-if="checkedAtText" class="mt-1 text-xs text-[var(--color-text-tertiary)]">
          {{ t('update.checkedAt', { time: checkedAtText }) }}
        </p>

        <!-- Advanced Proxy Section -->
        <div class="mt-3 border-t border-[var(--color-border)]/60 pt-3">
          <button
            type="button"
            @click="showUpdateProxyAdvanced = !showUpdateProxyAdvanced"
            class="flex w-full items-center justify-between gap-3 rounded-md text-left text-xs font-medium text-[var(--color-text-secondary)] transition-colors hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]"
            :aria-expanded="showUpdateProxyAdvanced"
          >
            <span>{{ t('update.proxyAdvanced') }}</span>
            <span class="material-symbols-outlined text-[18px]">
              {{ showUpdateProxyAdvanced ? 'expand_less' : 'expand_more' }}
            </span>
          </button>

          <div v-if="showUpdateProxyAdvanced" class="mt-3 space-y-3">
            <div class="grid grid-cols-2 gap-2">
              <button
                v-for="mode in updateProxyModes"
                :key="mode.value"
                type="button"
                @click="() => { updateProxyDraft = { ...updateProxyDraft, mode: mode.value }; updateProxySaveError = null }"
                :aria-pressed="updateProxyDraft.mode === mode.value"
                :class="[
                  'rounded-lg border px-3 py-2 text-left transition-colors',
                  updateProxyDraft.mode === mode.value
                    ? 'border-[var(--color-brand)] bg-[var(--color-surface-selected)] text-[var(--color-text-primary)]'
                    : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]'
                ]"
              >
                <div class="text-xs font-semibold">{{ mode.label }}</div>
                <div class="mt-1 text-[11px] leading-4 text-[var(--color-text-tertiary)]">
                  {{ mode.description }}
                </div>
              </button>
            </div>

            <div v-if="updateProxyDraft.mode === 'manual'">
              <Input
                id="update-proxy-url"
                :label="t('update.proxyUrl')"
                :model-value="updateProxyDraft.url"
                placeholder="http://127.0.0.1:7890"
                autocomplete="off"
                @update:model-value="(v) => { updateProxyDraft = { ...updateProxyDraft, url: v as string }; updateProxySaveError = null }"
              />
              <p :class="['mt-1 text-[11px] leading-4', manualProxyError ? 'text-[var(--color-error)]' : 'text-[var(--color-text-tertiary)]']">
                {{ manualProxyError ?? t('update.proxyUrlHint') }}
              </p>
            </div>

            <div class="flex items-center justify-between gap-3">
              <p class="min-w-0 text-[11px] leading-4 text-[var(--color-text-tertiary)]">
                {{ t('update.proxyScopeHint') }}
              </p>
              <Button
                size="sm"
                variant="secondary"
                class="min-w-[72px] px-4 whitespace-nowrap"
                :disabled="!updateProxyDirty || !!manualProxyError || isSavingUpdateProxy"
                :loading="isSavingUpdateProxy"
                @click="saveUpdateProxy"
              >
                {{ t('update.proxySave') }}
              </Button>
            </div>

            <p v-if="updateProxySaveError" class="text-[11px] leading-4 text-[var(--color-error)]">
              {{ updateProxySaveError }}
            </p>
          </div>
        </div>

        <!-- Progress Bar -->
        <div
          v-if="updateStore.status === 'downloading' || updateStore.status === 'restarting'"
          class="mt-3"
        >
          <div class="h-1.5 bg-[var(--color-surface-container-low)] rounded-full overflow-hidden">
            <div
              v-if="hasKnownProgress || updateStore.status === 'restarting'"
              class="h-full bg-[var(--color-text-accent)] transition-all duration-300"
              :style="{ width: `${Math.min(updateStore.progressPercent, 100)}%` }"
            />
            <div
              v-else
              class="h-full w-1/3 rounded-full bg-[var(--color-text-accent)]/75 animate-pulse"
            />
          </div>
          <p
            v-if="!hasKnownProgress && updateStore.status === 'downloading' && updateStore.downloadedBytes > 0"
            class="mt-1 text-xs text-[var(--color-text-tertiary)]"
          >
            {{ downloadedText }}
          </p>
        </div>

        <!-- Release Notes -->
        <div
          v-if="updateStore.releaseNotes && updateStore.availableVersion"
          class="mt-3 rounded-lg bg-[var(--color-surface-container-low)] px-3 py-3"
        >
          <div class="text-[11px] uppercase tracking-[0.14em] text-[var(--color-text-tertiary)]">
            {{ t('update.releaseNotes') }}
          </div>
          <MarkdownRenderer
            :content="updateStore.releaseNotes"
            variant="document"
            class="mt-2 text-[13px] leading-6 text-[var(--color-text-secondary)] [&_h1]:text-lg [&_h2]:text-base [&_h3]:text-sm [&_p]:text-[13px] [&_p]:leading-6"
          />
        </div>

        <!-- Install/Download Button -->
        <div v-if="updateStore.availableVersion" class="mt-3 flex justify-end">
          <Button
            size="sm"
            @click="() => updateStore.installUpdate()"
            :loading="updateStore.status === 'downloading' || updateStore.status === 'installing' || updateStore.status === 'restarting'"
            :disabled="updateStore.status === 'checking' || updateStore.status === 'downloading'"
          >
            {{
              updateStore.status === 'downloaded'
                ? t('update.installAndRestart')
                : updateStore.status === 'installing'
                  ? t('update.installing')
                  : updateStore.status === 'restarting'
                    ? t('update.restarting')
                    : t('update.now')
            }}
          </Button>
        </div>
      </div>
    </div>

    <!-- Divider -->
    <div class="w-full border-t border-[var(--color-border)]/40 my-6" />

    <!-- Author -->
    <div class="w-full">
      <h3 class="text-xs font-medium text-[var(--color-text-tertiary)] uppercase tracking-wider mb-3">
        {{ t('settings.about.author') }}
      </h3>
      <button
        @click="() => openUrl(AUTHOR_GITHUB)"
        class="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg hover:bg-[var(--color-surface-hover)] transition-colors cursor-pointer"
      >
        <img :src="publicAssetPath('icons/github.svg')" alt="GitHub" class="w-4 h-4 opacity-60" />
        <span class="text-sm text-[var(--color-text-primary)]">林芮翰</span>
        <span class="text-xs text-[var(--color-text-tertiary)] ml-auto">GitHub</span>
      </button>
    </div>

    <!-- Social Media -->
    <div class="w-full mt-4">
      <h3 class="text-xs font-medium text-[var(--color-text-tertiary)] uppercase tracking-wider mb-3">
        {{ t('settings.about.socialMedia') }}
      </h3>
      <div class="flex flex-col gap-0.5">
        <button
          v-for="link in SOCIAL_LINKS"
          :key="link.name"
          @click="() => openUrl(link.url)"
          class="w-full flex items-center gap-3 px-4 py-2.5 rounded-lg hover:bg-[var(--color-surface-hover)] transition-colors cursor-pointer"
        >
          <img :src="publicAssetPath(link.icon)" :alt="link.name" class="w-4 h-4 opacity-60" />
          <span class="text-sm text-[var(--color-text-primary)]">{{ link.label }}</span>
          <span class="text-xs text-[var(--color-text-tertiary)] ml-auto">{{ link.name }}</span>
        </button>
      </div>
    </div>

    <!-- Feedback -->
    <div class="mt-6 w-full">
      <button
        @click="() => openUrl(GITHUB_ISSUES)"
        class="w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors cursor-pointer"
      >
        <span class="material-symbols-outlined text-[20px] text-[var(--color-text-tertiary)]">feedback</span>
        <div class="flex-1 text-left">
          <div class="text-sm font-medium text-[var(--color-text-primary)]">{{ t('settings.about.feedback') }}</div>
          <div class="text-xs text-[var(--color-text-tertiary)]">{{ t('settings.about.feedbackDesc') }}</div>
        </div>
      </button>
    </div>
  </div>
</template>
