<script setup lang="ts">
// v3.0 — OpenWithMenu (Vue 3 SFC)
// Teleport-based "open with..." menu. Mirrors React createPortal.
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import type { OpenWithItem } from '../../../../lib/openWithItems'

type Pos = { top: number; left: number }

const props = defineProps<{
  items: OpenWithItem[]
  anchor: { top: number; bottom: number; left: number; right: number }
  triggerEl?: HTMLElement | null
}>()
const emit = defineEmits<{ (e: 'close'): void }>()

const menuRef = ref<HTMLDivElement | null>(null)
const MARGIN = 8
const pos = ref<Pos>({
  top: props.anchor.bottom + 6,
  left: Math.max(MARGIN, Math.min(props.anchor.left, window.innerWidth - 240 - MARGIN)),
})

// Position viewport-aware
onMounted(async () => {
  await nextTick()
  updatePosition()
})

function updatePosition() {
  const el = menuRef.value
  if (!el) return
  const { height, width } = el.getBoundingClientRect()
  const vh = window.innerHeight
  const vw = window.innerWidth
  let top = props.anchor.bottom + 6
  if (height > 0 && top + height > vh - MARGIN) {
    const flipped = props.anchor.top - height - 6
    top = flipped >= MARGIN ? flipped : Math.max(MARGIN, vh - height - MARGIN)
  }
  let left = props.anchor.left
  if (width > 0) left = Math.max(MARGIN, Math.min(left, vw - width - MARGIN))
  pos.value = { top, left }
}

onMounted(() => {
  document.addEventListener('mousedown', onDown)
  document.addEventListener('keydown', onKey)
  window.addEventListener('scroll', onViewportMove, true)
  window.addEventListener('resize', onViewportMove)
})
onBeforeUnmount(() => {
  document.removeEventListener('mousedown', onDown)
  document.removeEventListener('keydown', onKey)
  window.removeEventListener('scroll', onViewportMove, true)
  window.removeEventListener('resize', onViewportMove)
})

function onDown(e: MouseEvent) {
  const target = e.target as Node | null
  if (!target) return
  if (menuRef.value?.contains(target)) return
  if (props.triggerEl && props.triggerEl.contains(target)) return
  emit('close')
}
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') emit('close') }
function onViewportMove() { emit('close') }

// Simple icon rendering based on item.icon
function itemIcon(item: OpenWithItem): string {
  if (item.icon === 'in-app-browser') return 'language'
  if (item.icon === 'preview') return 'article'
  if (item.icon === 'external') return 'open_in_new'
  return 'computer'
}
</script>

<template>
  <Teleport to="body">
    <div
      ref="menuRef"
      role="menu"
      class="fixed min-w-[220px] overflow-hidden rounded-[12px] border border-[var(--color-border)] bg-[var(--color-surface)] py-1 shadow-[var(--shadow-dropdown)]"
      :style="{ top: `${pos.top}px`, left: `${pos.left}px`, zIndex: 1000 }"
    >
      <button
        v-for="item in items"
        :key="item.id"
        type="button"
        role="menuitem"
        @click="() => { item.onSelect(); emit('close') }"
        class="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm font-medium text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-hover)]"
      >
        <span class="flex h-6 w-6 items-center justify-center text-[var(--color-text-secondary)]">
          <span class="material-symbols-outlined text-[18px]">{{ itemIcon(item) }}</span>
        </span>
        <span class="min-w-0 truncate">{{ item.label }}</span>
      </button>
    </div>
  </Teleport>
</template>