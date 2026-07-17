<script setup lang="ts">
/**
 * TerminalSettings — 终端设置
 * Controls for shell path, theme, font size, etc.
 */

import { ref, onMounted } from 'vue'
import { getApiUrl } from '../api/client'

const shellPath = ref('/bin/zsh')
const fontSize = ref(14)
const fontFamily = ref('Menlo')
const terminalTheme = ref('dark')
const cursorStyle = ref('block')
const scrollbackLines = ref(5000)

async function loadSettings() {
  try {
    const res = await fetch(getApiUrl('/api/settings/user'))
    if (res.ok) {
      const data = await res.json()
      if (data.shellPath) shellPath.value = data.shellPath
      if (data.terminalFontSize) fontSize.value = data.terminalFontSize
      if (data.terminalFontFamily) fontFamily.value = data.terminalFontFamily
      if (data.terminalTheme) terminalTheme.value = data.terminalTheme
      if (data.cursorStyle) cursorStyle.value = data.cursorStyle
      if (data.scrollbackLines) scrollbackLines.value = data.scrollbackLines
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

onMounted(loadSettings)
</script>

<template>
  <div class="ts mx-auto max-w-2xl space-y-5">
    <header>
      <div class="ts__eyebrow">系统</div>
      <h2 class="ts__title">终端设置</h2>
      <p class="ts__desc">Shell、主题、字体与滚动缓冲</p>
    </header>

    <section class="ts-card">
      <div class="ts-card__head">
        <span class="material-symbols-outlined ts-card__icon">terminal</span>
        <h3 class="ts-card__title">Shell 与外观</h3>
      </div>

      <div class="ts-row">
        <div class="ts-row__info">
          <div class="ts-row__label">Shell 路径</div>
          <div class="ts-row__desc">终端使用的 shell 可执行文件</div>
        </div>
        <input
          v-model="shellPath"
          type="text"
          class="ts-input ts-input--mono"
          @change="saveSetting('shellPath', shellPath)"
        />
      </div>

      <div class="ts-row">
        <div class="ts-row__info">
          <div class="ts-row__label">主题</div>
          <div class="ts-row__desc">终端配色方案</div>
        </div>
        <select
          :value="terminalTheme"
          class="ts-select"
          @change="terminalTheme = ($event.target as HTMLSelectElement).value; saveSetting('terminalTheme', terminalTheme)"
        >
          <option value="dark">深色</option>
          <option value="light">浅色</option>
          <option value="sepia">暖色</option>
        </select>
      </div>

      <div class="ts-row">
        <div class="ts-row__info">
          <div class="ts-row__label">字号</div>
          <div class="ts-row__desc">{{ fontSize }}px</div>
        </div>
        <input
          type="range"
          class="ts-range"
          :value="fontSize"
          min="10"
          max="24"
          step="1"
          @input="fontSize = Number(($event.target as HTMLInputElement).value); saveSetting('terminalFontSize', fontSize)"
        />
      </div>

      <div class="ts-row">
        <div class="ts-row__info">
          <div class="ts-row__label">光标样式</div>
          <div class="ts-row__desc">终端光标外观</div>
        </div>
        <select
          :value="cursorStyle"
          class="ts-select"
          @change="cursorStyle = ($event.target as HTMLSelectElement).value; saveSetting('cursorStyle', cursorStyle)"
        >
          <option value="block">方块</option>
          <option value="underline">下划线</option>
          <option value="bar">竖线</option>
        </select>
      </div>

      <div class="ts-row">
        <div class="ts-row__info">
          <div class="ts-row__label">回滚行数</div>
          <div class="ts-row__desc">终端保留的历史行数</div>
        </div>
        <select
          :value="scrollbackLines"
          class="ts-select"
          @change="scrollbackLines = Number(($event.target as HTMLSelectElement).value); saveSetting('scrollbackLines', scrollbackLines)"
        >
          <option :value="1000">1,000</option>
          <option :value="5000">5,000</option>
          <option :value="10000">10,000</option>
          <option :value="50000">50,000</option>
        </select>
      </div>
    </section>
  </div>
</template>

<style scoped>
.ts__eyebrow {
  font-size: 11px; font-weight: 600; letter-spacing: 0.04em;
  color: var(--color-text-tertiary); margin-bottom: 6px;
}
.ts__title { margin: 0; font-size: 18px; font-weight: 700; color: var(--color-text-primary); }
.ts__desc { margin: 6px 0 0; font-size: 13px; color: var(--color-text-secondary); line-height: 1.45; }

.ts-card {
  border: 1px solid var(--color-border);
  border-radius: 16px;
  background: var(--color-surface);
  overflow: hidden;
}
.ts-card__head {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-container-low);
}
.ts-card__icon { font-size: 18px; color: var(--color-brand); }
.ts-card__title { margin: 0; font-size: 13px; font-weight: 600; color: var(--color-text-primary); }

.ts-row {
  display: flex; align-items: center; justify-content: space-between; gap: 16px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border-separator, var(--color-border));
}
.ts-row:last-child { border-bottom: none; }
.ts-row__info { flex: 1; min-width: 0; }
.ts-row__label { font-size: 13px; font-weight: 500; color: var(--color-text-primary); }
.ts-row__desc { font-size: 11px; color: var(--color-text-tertiary); margin-top: 2px; }

.ts-select, .ts-input {
  padding: 7px 12px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  font-size: 12px;
  background: var(--color-surface-container-lowest, var(--color-surface));
  color: var(--color-text-primary);
  outline: none;
  min-width: 140px;
}
.ts-select:focus, .ts-input:focus { border-color: var(--color-brand); }
.ts-input { width: 200px; min-width: 160px; }
.ts-input--mono { font-family: var(--font-mono); font-size: 11px; }
.ts-range { width: 160px; accent-color: var(--color-brand); }
</style>
