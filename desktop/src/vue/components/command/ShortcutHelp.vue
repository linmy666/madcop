<script setup lang="ts">
/**
 * ShortcutHelp — keyboard shortcut overlay (C-4).
 * Toggled by pressing `?` anywhere. Lists all global shortcuts.
 */
defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const shortcuts = [
  { keys: '⌘ B', desc: '切换侧边栏' },
  { keys: '⌘ N', desc: '新建对话' },
  { keys: '⌘ K', desc: '打开命令面板' },
  { keys: '⇧ ⌘ F', desc: '全局搜索' },
  { keys: '⌘ ,', desc: '打开设置' },
  { keys: '⌘ .', desc: '停止生成' },
  { keys: '?', desc: '显示此帮助' },
  { keys: 'Esc', desc: '关闭弹窗 / 停止' },
]
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="shortcut-overlay" @click="emit('close')">
      <div class="shortcut-modal" @click.stop>
        <h2 class="shortcut-title">键盘快捷键</h2>
        <div class="shortcut-list">
          <div v-for="s in shortcuts" :key="s.keys" class="shortcut-row">
            <kbd class="shortcut-keys">{{ s.keys }}</kbd>
            <span class="shortcut-desc">{{ s.desc }}</span>
          </div>
        </div>
        <button class="shortcut-close" @click="emit('close')">关闭 (Esc)</button>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.shortcut-overlay {
  position: fixed; inset: 0; z-index: 9998;
  background: rgba(0,0,0,0.5); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.shortcut-modal {
  width: 360px; background: var(--color-surface, #1e1e2e); border-radius: 16px;
  padding: 24px; border: 1px solid var(--color-border, rgba(255,255,255,0.1));
  box-shadow: 0 24px 80px rgba(0,0,0,0.4);
}
.shortcut-title { font-size: 16px; font-weight: 700; margin-bottom: 16px; color: var(--color-text, #fff); }
.shortcut-list { display: flex; flex-direction: column; gap: 2px; }
.shortcut-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 4px; border-radius: 6px; }
.shortcut-row:hover { background: var(--color-surface-container, rgba(255,255,255,0.03)); }
.shortcut-keys {
  font-family: var(--font-mono, monospace); font-size: 12px; font-weight: 600;
  padding: 3px 8px; border-radius: 5px; background: var(--color-surface-container, rgba(255,255,255,0.06));
  border: 1px solid var(--color-border, rgba(255,255,255,0.1)); color: var(--color-text, #fff);
}
.shortcut-desc { font-size: 13px; color: var(--color-text-secondary, #aaa); }
.shortcut-close {
  margin-top: 16px; width: 100%; padding: 8px; border-radius: 8px; font-size: 13px; cursor: pointer;
  background: var(--color-surface-container, rgba(255,255,255,0.05)); border: none;
  color: var(--color-text-secondary, #aaa); transition: color .15s;
}
.shortcut-close:hover { color: var(--color-text, #fff); }
</style>
