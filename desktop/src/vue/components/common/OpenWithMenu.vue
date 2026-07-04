<script setup lang="ts">
// v3.0 — OpenWithMenu (Vue 3)
// Simplified port — same Tailwind classes, Teleport replaces createPortal.
// Positioning logic is simplified (no useLayoutEffect flip calculation).
import { ref, onMounted, onUnmounted } from 'vue'
import TargetIcon from './TargetIcon.vue'

interface OpenWithItem {
  id: string
  label: string
  icon: string  // 'ide' | 'file-manager' | 'in-app-browser' | 'preview' | 'external'
  target?: { iconUrl?: string; kind: 'ide' | 'file_manager' }
}

const props = defineProps<{
  items: OpenWithItem[]
  anchor: { top: number; bottom: number; left: number; right: number }
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select', id: string): void
}>()

const menuRef = ref<HTMLDivElement | null>(null)

function onDocClick(e: MouseEvent) {
  if (menuRef.value && !menuRef.value.contains(e.target as Node)) emit('close')
}
function onEsc(e: KeyboardEvent) { if (e.key === 'Escape') emit('close') }

onMounted(() => {
  document.addEventListener('mousedown', onDocClick)
  document.addEventListener('keydown', onEsc)
})
onUnmounted(() => {
  document.removeEventListener('mousedown', onDocClick)
  document.removeEventListener('keydown', onEsc)
})

const iconMap: Record<string, string> = {
  'in-app-browser': 'public',
  'preview': 'description',
  'external': 'open_in_new',
}

function iconFor(item: OpenWithItem): string {
  return iconMap[item.icon] || 'open_in_new'
}
</script>

<template>
  <Teleport to="body">
    <div
      ref="menuRef"
      class="fixed z-50 min-w-[200px] overflow-hidden rounded-[12px] border border-[var(--color-border)] bg-[var(--color-surface)] py-1 shadow-[var(--shadow-dropdown)]"
      :style="{ top: anchor.bottom + 6 + 'px', left: Math.max(8, Math.min(anchor.left, window.innerWidth - 240 - 8)) + 'px' }"
    >
      <button
        v-for="item in items" :key="item.id"
        type="button"
        @click="emit('select', item.id)"
        class="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm font-medium text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-hover)]"
      >
        <span class="flex h-5 w-5 items-center justify-center text-[var(--color-text-secondary)]">
          <TargetIcon v-if="item.target" :icon-url="item.target.iconUrl" :kind="item.target.kind" :size="20" />
          <span v-else class="material-symbols-outlined text-[18px]">{{ iconFor(item) }}</span>
        </span>
        <span class="min-w-0 truncate">{{ item.label }}</span>
      </button>
    </div>
  </Teleport>
</template>
