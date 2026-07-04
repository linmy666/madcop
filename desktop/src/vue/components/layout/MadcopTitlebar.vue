<script setup lang="ts">
// v3.0 — MadCop Titlebar (Vue 3)
// 32px height, center command input, right side controls.

import { ref } from 'vue'

const props = defineProps<{ projectName?: string }>()
const emit = defineEmits<{ (e: 'command', cmd: string): void }>()

const cmd = ref('')

function onEnter() {
  const v = cmd.value.trim()
  if (!v) return
  emit('command', v)
  cmd.value = ''
}
</script>

<template>
  <div class="madcop-titlebar">
    <div class="madcop-titlebar__left">
      <span class="madcop-titlebar__brand">MADCOP</span>
      <span v-if="projectName" class="madcop-titlebar__sep">/</span>
      <span v-if="projectName" class="madcop-titlebar__proj">{{ projectName }}</span>
    </div>

    <div class="madcop-titlebar__center">
      <div class="madcop-titlebar__cmd">
        <span class="madcop-titlebar__cmd-icon">⌕</span>
        <input
          v-model="cmd"
          @keydown.enter="onEnter"
          type="text"
          placeholder="执行命令 — 选模型、写提示、跳转"
          class="madcop-titlebar__cmd-input"
        />
        <kbd class="madcop-titlebar__cmd-kbd">⌘K</kbd>
      </div>
    </div>

    <div class="madcop-titlebar__right">
      <button class="madcop-titlebar__btn" @click="emit('command', 'appearance:toggle')">主题</button>
      <button class="madcop-titlebar__btn" @click="emit('command', 'settings:open')">设置</button>
    </div>
  </div>
</template>

<style scoped>
.madcop-titlebar {
  width: 100%; height: 100%;
  display: flex; align-items: center;
  padding: 0 12px; gap: 12px;
  background: var(--madcop-panel-raised);
  -webkit-app-region: drag;
}
.madcop-titlebar__left  { display: flex; align-items: center; gap: 8px; min-width: 200px; }
.madcop-titlebar__center { flex: 1; display: flex; justify-content: center; }
.madcop-titlebar__right { min-width: 200px; display: flex; justify-content: flex-end; gap: 8px; }

.madcop-titlebar__brand {
  font-family: 'Geist Mono', monospace; font-size: 11px; color: var(--madcop-ink-muted);
  letter-spacing: 0.02em;
}
.madcop-titlebar__sep  { color: var(--madcop-line); }
.madcop-titlebar__proj { font-size: 13px; color: var(--madcop-ink); }

.madcop-titlebar__cmd {
  display: flex; align-items: center; gap: 8px;
  width: 320px; padding: 4px 10px;
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-sunken);
}
.madcop-titlebar__cmd-icon  { color: var(--madcop-ink-muted); font-family: 'Geist Mono', monospace; font-size: 12px; }
.madcop-titlebar__cmd-input { flex: 1; border: none; outline: none; background: transparent; font-size: 13px; color: var(--madcop-ink); }
.madcop-titlebar__cmd-kbd  { font-size: 10px; color: var(--madcop-ink-muted); border: 1px solid var(--madcop-line); padding: 1px 4px; font-family: 'Geist Mono', monospace; }

.madcop-titlebar__btn {
  padding: 4px 10px; border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-raised); color: var(--madcop-ink-muted);
  font-size: 11px; font-family: 'Geist Mono', monospace; cursor: pointer;
  -webkit-app-region: no-drag;
}
</style>
