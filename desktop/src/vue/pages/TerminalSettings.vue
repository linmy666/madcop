<script setup lang="ts">
/**
 * TerminalSettings — 终端设置
 * Controls for shell path, theme, font size, etc.
 */

import { ref, onMounted } from 'vue'

const shellPath = ref('/bin/zsh')
const fontSize = ref(14)
const fontFamily = ref('Menlo')
const terminalTheme = ref('dark')
const cursorStyle = ref('block')
const scrollbackLines = ref(5000)

async function loadSettings() {
  try {
    const res = await fetch('/api/settings/user')
    if (res.ok) {
      const data = await res.json()
      if (data.shellPath) shellPath.value = data.shellPath
      if (data.terminalFontSize) fontSize.value = data.terminalFontSize
      if (data.terminalTheme) terminalTheme.value = data.terminalTheme
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

onMounted(loadSettings)
</script>

<template>
  <div style="max-width: 640px;">
    <h2 class="text-[16px] font-semibold text-[var(--color-text-primary)] mb-1">终端设置</h2>
    <p class="text-[13px] text-[var(--color-text-tertiary)] mb-6">Shell、主题、字体偏好</p>

    <div class="settings-row">
      <div class="settings-row__info">
        <div class="settings-row__label">Shell 路径</div>
        <div class="settings-row__desc">终端使用的 shell</div>
      </div>
      <input
        v-model="shellPath"
        type="text"
        style="width: 200px; padding: 6px 10px; border: 1px solid var(--color-border); border-radius: 4px; font-size: 12px; background: var(--color-surface); color: var(--color-text-primary); font-family: var(--font-mono);"
        @change="saveSetting('shellPath', shellPath)"
      />
    </div>

    <div class="settings-row">
      <div class="settings-row__info">
        <div class="settings-row__label">主题</div>
        <div class="settings-row__desc">终端配色方案</div>
      </div>
      <select :value="terminalTheme" @change="terminalTheme = ($event.target as HTMLSelectElement).value; saveSetting('terminalTheme', terminalTheme)" class="settings-select">
        <option value="dark">深色</option>
        <option value="light">浅色</option>
        <option value="sepia">暖色</option>
      </select>
    </div>

    <div class="settings-row">
      <div class="settings-row__info">
        <div class="settings-row__label">字号</div>
        <div class="settings-row__desc">{{ fontSize }}px</div>
      </div>
      <input
        type="range"
        :value="fontSize"
        min="10"
        max="24"
        step="1"
        style="width: 160px;"
        @input="fontSize = Number(($event.target as HTMLInputElement).value); saveSetting('terminalFontSize', fontSize)"
      />
    </div>

    <div class="settings-row">
      <div class="settings-row__info">
        <div class="settings-row__label">光标样式</div>
        <div class="settings-row__desc">终端光标外观</div>
      </div>
      <select :value="cursorStyle" @change="cursorStyle = ($event.target as HTMLSelectElement).value" class="settings-select">
        <option value="block">方块</option>
        <option value="underline">下划线</option>
        <option value="bar">竖线</option>
      </select>
    </div>

    <div class="settings-row">
      <div class="settings-row__info">
        <div class="settings-row__label">回滚行数</div>
        <div class="settings-row__desc">终端保留的历史行数</div>
      </div>
      <select :value="scrollbackLines" @change="scrollbackLines = Number(($event.target as HTMLSelectElement).value)" class="settings-select">
        <option :value="1000">1,000</option>
        <option :value="5000">5,000</option>
        <option :value="10000">10,000</option>
        <option :value="50000">50,000</option>
      </select>
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
.settings-row__label { font-size: 13px; font-weight: 500; color: var(--color-text-primary); }
.settings-row__desc { font-size: 11px; color: var(--color-text-tertiary); margin-top: 2px; }
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
</style>