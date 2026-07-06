<script setup lang="ts">
/**
 * GeneralSettings — 通用设置
 * Language, theme, chat behavior, network, notifications, zoom
 */

import { ref, onMounted, computed } from 'vue'

const t = (key: string) => key

// ── State ──────────────────────────────────────────────────────────────

const locale = ref('zh')
const responseLanguage = ref('follow')
const chatSendBehavior = ref('enter')
const theme = ref('light')
const uiZoom = ref(1.0)
const webSearchEnabled = ref(true)
const networkTimeout = ref(60)

async function loadSettings() {
  try {
    const res = await fetch('/api/settings/user')
    if (res.ok) {
      const data = await res.json()
      if (data.locale) locale.value = data.locale
      if (data.theme) theme.value = data.theme
      if (data.chatSendBehavior) chatSendBehavior.value = data.chatSendBehavior
      if (data.responseLanguage) responseLanguage.value = data.responseLanguage
      if (data.uiZoom) uiZoom.value = data.uiZoom
      if (data.webSearchEnabled !== undefined) webSearchEnabled.value = data.webSearchEnabled
    }
  } catch {}
}

async function saveSetting(key: string, value: any) {
  try {
    await fetch('/api/settings/user', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ [key]: value }),
    })
  } catch {}
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
  theme.value = (e.target as HTMLSelectElement).value
  saveSetting('theme', theme.value)
}

onMounted(loadSettings)
</script>

<template>
  <div style="max-width: 640px;">
    <h2 class="text-[16px] font-semibold text-[var(--color-text-primary)] mb-1">通用设置</h2>
    <p class="text-[13px] text-[var(--color-text-tertiary)] mb-6">语言、主题、行为偏好</p>

    <!-- ═══ Style Row Helper ═══ -->
    <div class="settings-row">
      <div class="settings-row__info">
        <div class="settings-row__label">语言</div>
        <div class="settings-row__desc">界面语言</div>
      </div>
      <select :value="locale" @change="onLocaleChange" class="settings-select">
        <option value="zh">中文</option>
        <option value="en">English</option>
      </select>
    </div>

    <div class="settings-row">
      <div class="settings-row__info">
        <div class="settings-row__label">回复语言</div>
        <div class="settings-row__desc">AI 回复时使用的语言</div>
      </div>
      <select :value="responseLanguage" @change="onResponseLanguageChange" class="settings-select">
        <option value="follow">跟随用户</option>
        <option value="zh">始终中文</option>
        <option value="en">始终英文</option>
      </select>
    </div>

    <div class="settings-row">
      <div class="settings-row__info">
        <div class="settings-row__label">发送快捷键</div>
        <div class="settings-row__desc">发送消息的快捷键方式</div>
      </div>
      <select :value="chatSendBehavior" @change="onSendBehaviorChange" class="settings-select">
        <option value="enter">Enter 发送 / Shift+Enter 换行</option>
        <option value="ctrlEnter">Ctrl+Enter 发送</option>
      </select>
    </div>

    <div class="settings-row">
      <div class="settings-row__info">
        <div class="settings-row__label">主题</div>
        <div class="settings-row__desc">界面主题风格</div>
      </div>
      <select :value="theme" @change="onThemeChange" class="settings-select">
        <option value="light">浅色</option>
        <option value="dark">深色</option>
        <option value="sepia">暖色</option>
      </select>
    </div>

    <div class="settings-row">
      <div class="settings-row__info">
        <div class="settings-row__label">界面缩放</div>
        <div class="settings-row__desc">{{ Math.round(uiZoom * 100) }}%</div>
      </div>
      <input
        type="range"
        :value="uiZoom"
        min="0.5"
        max="2"
        step="0.05"
        style="width: 160px;"
      />
    </div>

    <div class="settings-row">
      <div class="settings-row__info">
        <div class="settings-row__label">联网搜索</div>
        <div class="settings-row__desc">Agent 是否可以使用网页搜索</div>
      </div>
      <div
        :class="['settings-toggle', webSearchEnabled ? 'settings-toggle--on' : '']"
        @click="webSearchEnabled = !webSearchEnabled; saveSetting('webSearchEnabled', webSearchEnabled)"
      >
        <div class="settings-toggle__thumb"></div>
      </div>
    </div>

    <div class="settings-row">
      <div class="settings-row__info">
        <div class="settings-row__label">超时 (秒)</div>
        <div class="settings-row__desc">AI 请求超时时间</div>
      </div>
      <input
        type="number"
        :value="networkTimeout"
        min="10"
        max="300"
        style="width: 80px; padding: 4px 8px; border: 1px solid var(--color-border); border-radius: 4px; font-size: 12px; background: var(--color-surface); color: var(--color-text-primary);"
      />
    </div>
  </div>
</template>

<style scoped>
.settings-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 0;
  border-bottom: 1px solid var(--color-border-separator);
}
.settings-row:last-child { border-bottom: none; }
.settings-row__info { flex: 1; }
.settings-row__label {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}
.settings-row__desc {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
}
.settings-select {
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 12px;
  background: var(--color-surface);
  color: var(--color-text-primary);
  outline: none;
}
.settings-select:focus { border-color: var(--color-brand); }

.settings-toggle {
  width: 36px;
  height: 20px;
  border-radius: 10px;
  background: var(--color-border);
  cursor: pointer;
  position: relative;
  transition: background 0.15s;
}
.settings-toggle--on { background: var(--color-brand); }
.settings-toggle__thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: #fff;
  position: absolute;
  top: 2px;
  left: 2px;
  transition: transform 0.15s;
}
.settings-toggle--on .settings-toggle__thumb { transform: translateX(16px); }
</style>