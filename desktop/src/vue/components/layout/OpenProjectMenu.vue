<script setup lang="ts">
// v3.0 — OpenProjectMenu (Vue 3)
// Direct translation — same Tailwind classes, Teleport replaces createPortal.
import { ref, onMounted, onUnmounted, computed } from 'vue'
import TargetIcon from '../common/TargetIcon.vue'

interface OpenTarget {
  id: string
  label: string
  iconUrl?: string
  kind: 'ide' | 'file_manager'
}

const props = defineProps<{
  path?: string | null
  targets?: OpenTarget[]
}>()

const emit = defineEmits<{ (e: 'open', targetId: string, path: string): void }>()

const open = ref(false)
const buttonRef = ref<HTMLButtonElement | null>(null)

const targets = computed(() => props.targets ?? [])
const hasMenu = computed(() => targets.value.length > 1)
const primaryTarget = computed(() => targets.value[0] ?? null)
const buttonLabel = computed(() => hasMenu.value ? '打开项目' : `在 ${primaryTarget.value?.label} 中打开`)

function onDocClick(e: MouseEvent) {
  const target = e.target as Node
  if (buttonRef.value?.contains(target)) return
  const menu = document.querySelector('[data-open-project-menu]')
  if (menu && menu.contains(target)) return
  open.value = false
}
function onEsc(e: KeyboardEvent) { if (e.key === 'Escape') open.value = false }
onMounted(() => { document.addEventListener('mousedown', onDocClick); document.addEventListener('keydown', onEsc) })
onUnmounted(() => { document.removeEventListener('mousedown', onDocClick); document.removeEventListener('keydown', onEsc) })

function handleClick() {
  if (hasMenu.value) { open.value = !open.value; return }
  if (primaryTarget.value && props.path) emit('open', primaryTarget.value.id, props.path)
}
function handleSelect(id: string) {
  if (props.path) emit('open', id, props.path)
  open.value = false
}
</script>

<template>
  <div v-if="path && primaryTarget" class="relative flex items-center">
    <button
      ref="buttonRef"
      type="button"
      :aria-label="buttonLabel"
      :aria-haspopup="hasMenu ? 'menu' : undefined"
      :aria-expanded="hasMenu ? open : undefined"
      :title="buttonLabel"
      @click="handleClick"
      :class="[
        'inline-flex h-8 items-center justify-center gap-1 rounded-[10px] border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] text-[var(--color-text-tertiary)] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]',
        hasMenu ? 'min-w-[2.75rem] px-2 hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]' : 'w-8 hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]',
      ]"
    >
      <TargetIcon :icon-url="primaryTarget.iconUrl" :kind="primaryTarget.kind" :size="18" />
      <span v-if="hasMenu" class="material-symbols-outlined text-[14px]">expand_more</span>
    </button>

    <Teleport to="body">
      <div
        v-if="open && hasMenu"
        data-open-project-menu
        role="menu"
        class="fixed z-50 min-w-[220px] overflow-hidden rounded-[12px] border border-[var(--color-border)] bg-[var(--color-surface)] py-1 shadow-[var(--shadow-dropdown)]"
        :style="{ top: (buttonRef?.getBoundingClientRect().bottom ?? 0) + 6 + 'px', right: Math.max(12, window.innerWidth - (buttonRef?.getBoundingClientRect().right ?? 0)) + 'px' }"
      >
        <button
          v-for="target in targets" :key="target.id"
          type="button"
          role="menuitem"
          @click="handleSelect(target.id)"
          class="flex w-full items-center gap-3 px-3 py-2.5 text-left text-sm font-medium text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:bg-[var(--color-surface-hover)]"
        >
          <span class="flex h-7 w-7 items-center justify-center text-[var(--color-text-secondary)]">
            <TargetIcon :icon-url="target.iconUrl" :kind="target.kind" :size="24" />
          </span>
          <span class="min-w-0 truncate">{{ target.label }}</span>
        </button>
      </div>
    </Teleport>
  </div>
</template>
