<script setup lang="ts">
/**
 * GeneralSettings — 通用设置
 * Language, theme, chat behavior, network, notifications, zoom
 */

import { ref, onMounted } from 'vue'
import { useAppearance } from '../../composables/useAppearance'
import { getApiUrl } from '../../api/client'
import { useTranslation } from '../../i18n'
import LanguageSwitcher from '../../components/controls/LanguageSwitcher.vue'

const t = useTranslation()

const locale = ref('zh')
const responseLanguage = ref('follow')
const chatSendBehavior = ref('enter')
const theme = ref('light')
const uiZoom = ref(1.0)
const webSearchEnabled = ref(true)
const networkTimeout = ref(60)

const { appearance, setAppearance } = useAppearance()

async function loadSettings() {
  try {
    const res = await fetch(getApiUrl('/api/settings/user'))
    if (res.ok) {
      const data = await res.json()
      if (data.locale) locale.value = data.locale
      // Legacy stored values ("white") predate the current palette —
      // anything unknown falls back to the live appearance value so the
      // select never renders blank.
      const t = data.theme
      theme.value = (t === 'light' || t === 'dark' || t === 'sepia') ? t : appearance.value
      setAppearance(theme.value as 'light' | 'dark' | 'sepia')
      if (data.chatSendBehavior) chatSendBehavior.value = data.chatSendBehavior
      if (data.responseLanguage) responseLanguage.value = data.responseLanguage
      if (data.uiZoom) uiZoom.value = data.uiZoom
      if (data.webSearchEnabled !== undefined) webSearchEnabled.value = data.webSearchEnabled
      if (data.networkTimeout) networkTimeout.value = data.networkTimeout
    }
  } catch { /* ignore */ }
}

async function saveSetting(key: string, value: unknown) {
  try {
    await fetch(getApiUrl('/api/settings/user'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [key]: value }),
    })
  } catch { /* ignore */ }
}

function onLocaleChange(e: Event) {
  locale.value = (e.target as HTMLSelectElement).value
  saveSetting('locale', locale.value)
}
function onResponseLanguageChange(e: Event) {
  responseLanguage.value = (e.target as HTMLSelectElement).value
  saveSetting('responseLanguage', responseLanguage.value)
}
function onSendBehaviorChange(e: Event) {
  chatSendBehavior.value = (e.target as HTMLSelectElement).value
  saveSetting('chatSendBehavior', chatSendBehavior.value)
}
function onThemeChange(e: Event) {
  const v = (e.target as HTMLSelectElement).value as 'light' | 'dark' | 'sepia'
  theme.value = v
  setAppearance(v)
  saveSetting('theme', v)
}
function onZoomChange(e: Event) {
  uiZoom.value = Number((e.target as HTMLInputElement).value)
  saveSetting('uiZoom', uiZoom.value)
}
function onTimeoutChange(e: Event) {
  networkTimeout.value = Number((e.target as HTMLInputElement).value)
  saveSetting('networkTimeout', networkTimeout.value)
}
function toggleWebSearch() {
  webSearchEnabled.value = !webSearchEnabled.value
  saveSetting('webSearchEnabled', webSearchEnabled.value)
}

onMounted(loadSettings)
</script>

<template>
  <div class="gs mx-auto max-w-2xl space-y-5">
    <header class="gs__header">
      <div class="gs__eyebrow">{{ t('settings.nav.core') || '核心' }}</div>
      <h2 class="gs__title">{{ t('settings.nav.general') || '通用设置' }}</h2>
      <p class="gs__desc">{{ t('general.desc') }}</p>
    </header>

    <!-- Language -->
    <section class="gs-card">
      <div class="gs-card__head">
        <span class="material-symbols-outlined gs-card__icon">translate</span>
        <h3 class="gs-card__title">{{ t('general.langReply') }}</h3>
      </div>
      <div class="gs-row">
        <div class="gs-row__info">
          <div class="gs-row__label">{{ t('general.replyLanguage') }}</div>
          <div class="gs-row__desc">{{ t('general.replyLanguageDesc') }}</div>
        </div>
        <select :value="responseLanguage" class="gs-select" @change="onResponseLanguageChange">
          <option value="follow">{{ t('general.followUser') }}</option>
          <option value="zh">{{ t('general.alwaysZh') }}</option>
          <option value="en">{{ t('general.alwaysEn') }}</option>
        </select>
      </div>
    </section>

    <!-- Chat & theme -->
    <section class="gs-card">
      <div class="gs-card__head">
        <span class="material-symbols-outlined gs-card__icon">tune</span>
        <h3 class="gs-card__title">{{ t('general.interaction') }}</h3>
      </div>
      <div class="gs-row">
        <div class="gs-row__info">
          <div class="gs-row__label">{{ t('general.sendKey') }}</div>
          <div class="gs-row__desc">{{ t('general.sendKeyDesc') }}</div>
        </div>
        <select :value="chatSendBehavior" class="gs-select" @change="onSendBehaviorChange">
          <option value="enter">{{ t('general.enterSend') }}</option>
          <option value="ctrlEnter">{{ t('general.ctrlEnterSend') }}</option>
        </select>
      </div>
      <div class="gs-row">
        <div class="gs-row__info">
          <div class="gs-row__label">{{ t('general.theme') }}</div>
          <div class="gs-row__desc">{{ t('general.themeDesc') }}</div>
        </div>
        <select :value="theme" class="gs-select" @change="onThemeChange">
          <option value="light">{{ t('general.themeLight') }}</option>
          <option value="dark">{{ t('general.themeDark') }}</option>
          <option value="sepia">{{ t('general.themeSepia') }}</option>
        </select>
      </div>
      <div class="gs-row">
        <div class="gs-row__info">
          <div class="gs-row__label">{{ t('general.uiZoom') }}</div>
          <div class="gs-row__desc">{{ Math.round(uiZoom * 100) }}%</div>
        </div>
        <input
          type="range"
          class="gs-range"
          :value="uiZoom"
          min="0.5"
          max="2"
          step="0.05"
          @input="onZoomChange"
        />
      </div>
      <div class="gs-row">
        <div class="gs-row__info">
          <div class="gs-row__label">{{ t('general.langToggle') }}</div>
          <div class="gs-row__desc">{{ t('general.langToggleDesc') }}</div>
        </div>
        <LanguageSwitcher />
      </div>
    </section>

    <!-- Network -->
    <section class="gs-card">
      <div class="gs-card__head">
        <span class="material-symbols-outlined gs-card__icon">public</span>
        <h3 class="gs-card__title">{{ t('general.network') }}</h3>
      </div>
      <div class="gs-row">
        <div class="gs-row__info">
          <div class="gs-row__label">{{ t('general.webSearch') }}</div>
          <div class="gs-row__desc">{{ t('general.webSearchDesc') }}</div>
        </div>
        <button
          type="button"
          role="switch"
          class="gs-toggle"
          :class="{ 'gs-toggle--on': webSearchEnabled }"
          :aria-checked="webSearchEnabled"
          @click="toggleWebSearch"
        >
          <span class="gs-toggle__thumb" />
        </button>
      </div>
      <div class="gs-row">
        <div class="gs-row__info">
          <div class="gs-row__label">{{ t('general.timeout') }}</div>
          <div class="gs-row__desc">{{ t('general.timeoutDesc') }}</div>
        </div>
        <input
          type="number"
          class="gs-input"
          :value="networkTimeout"
          min="10"
          max="300"
          @change="onTimeoutChange"
        />
      </div>
    </section>
  </div>
</template>

<style scoped>
.gs__header { margin-bottom: 4px; }
.gs__eyebrow {
  font-size: 11px; font-weight: 600; letter-spacing: 0.04em;
  color: var(--color-text-tertiary); margin-bottom: 6px;
}
.gs__title {
  margin: 0; font-size: 18px; font-weight: 700; color: var(--color-text-primary);
}
.gs__desc {
  margin: 6px 0 0; font-size: 13px; color: var(--color-text-secondary); line-height: 1.45;
}

.gs-card {
  border: 1px solid var(--color-border);
  border-radius: 16px;
  background: var(--color-surface);
  overflow: hidden;
}
.gs-card__head {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-container-low);
}
.gs-card__icon { font-size: 18px; color: var(--color-brand); }
.gs-card__title { margin: 0; font-size: 13px; font-weight: 600; color: var(--color-text-primary); }

.gs-row {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border-separator, var(--color-border));
}
.gs-row:last-child { border-bottom: none; }
.gs-row__info { flex: 1; min-width: 0; }
.gs-row__label { font-size: 13px; font-weight: 500; color: var(--color-text-primary); }
.gs-row__desc { font-size: 11px; color: var(--color-text-tertiary); margin-top: 2px; }

.gs-select, .gs-input {
  padding: 7px 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  font-size: 12px;
  background: var(--color-surface-container-lowest, var(--color-surface));
  color: var(--color-text-primary);
  outline: none;
  min-width: 160px;
}
.gs-select:focus, .gs-input:focus { border-color: var(--color-brand); }
.gs-input { width: 88px; min-width: 88px; text-align: center; }
.gs-range { width: 160px; accent-color: var(--color-brand); }

.gs-toggle {
  position: relative; width: 40px; height: 22px; padding: 0; border: none;
  border-radius: 11px; background: var(--color-border); cursor: pointer;
  transition: background 0.15s; flex-shrink: 0;
}
.gs-toggle--on { background: var(--color-brand); }
.gs-toggle__thumb {
  position: absolute; top: 3px; left: 3px;
  width: 16px; height: 16px; border-radius: 50%;
  background: var(--color-switch-thumb, #fff);
  transition: transform 0.15s; display: block;
}
.gs-toggle--on .gs-toggle__thumb { transform: translateX(18px); }
</style>
