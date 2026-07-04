<script setup lang="ts" generic="T extends string">
// v3.0 — Dropdown (Vue 3)
// Direct translation — same Tailwind classes, same click-outside logic.
import { ref, onMounted, onUnmounted } from 'vue'

interface DropdownItem {
  value: string
  label: string
  description?: string
  icon?: string  // material-symbols name
}

const props = withDefaults(defineProps<{
  items: DropdownItem[]
  modelValue: string
  width?: number
  maxHeight?: number
  align?: 'left' | 'right'
  class?: string
}>(), {
  width: 320,
  align: 'left',
})

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const open = ref(false)
const rootRef = ref<HTMLDivElement | null>(null)

function onDocClick(e: MouseEvent) {
  if (rootRef.value && !rootRef.value.contains(e.target as Node)) {
    open.value = false
  }
}
function onEsc(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = false
}
onMounted(() => {
  document.addEventListener('mousedown', onDocClick)
  document.addEventListener('keydown', onEsc)
})
onUnmounted(() => {
  document.removeEventListener('mousedown', onDocClick)
  document.removeEventListener('keydown', onEsc)
})

function select(value: string) {
  emit('update:modelValue', value)
  open.value = false
}
</script>

<template>
  <div ref="rootRef" :class="['relative', $props.class || 'inline-block']">
    <div @click="open = !open" class="cursor-pointer">
      <slot name="trigger" :value="modelValue">
        <span class="text-sm">{{ items.find(i => i.value === modelValue)?.label }}</span>
      </slot>
    </div>

    <Transition name="dropdown">
      <div
        v-if="open"
        :class="[
          'absolute z-50 mt-1 rounded-[var(--radius-lg)] bg-[var(--color-surface-container-lowest)] border border-[var(--color-border)] shadow-[var(--shadow-dropdown)]',
          maxHeight ? 'overflow-y-auto' : 'overflow-hidden',
          align === 'right' ? 'right-0' : 'left-0',
        ]"
        :style="{ width: width + 'px', maxHeight: maxHeight ? maxHeight + 'px' : undefined }"
      >
        <button
          v-for="(item, i) in items" :key="item.value"
          @click="select(item.value)"
          :class="[
            'w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:bg-[var(--color-surface-hover)]',
            item.value === modelValue ? 'bg-[var(--color-model-option-selected-bg)]' : '',
            i > 0 ? 'border-t border-[var(--color-border-separator)]' : '',
          ]"
        >
          <span v-if="item.icon" class="material-symbols-outlined flex h-5 w-5 flex-shrink-0 items-center justify-center text-[var(--color-text-secondary)] text-[16px]">{{ item.icon }}</span>
          <div class="flex-1 min-w-0">
            <div class="text-sm font-medium text-[var(--color-text-primary)]">{{ item.label }}</div>
            <div v-if="item.description" class="text-xs text-[var(--color-text-secondary)] mt-0.5">{{ item.description }}</div>
          </div>
          <span
            v-if="item.value === modelValue"
            class="material-symbols-outlined flex-shrink-0 text-[16px] text-[var(--color-brand)]"
            style="font-variation-settings: 'FILL' 1"
          >check_circle</span>
        </button>
      </div>
    </Transition>
  </div>
</template>

<style>
.dropdown-enter-active, .dropdown-leave-active { transition: all 150ms; }
.dropdown-enter-from, .dropdown-leave-to { opacity: 0; transform: translateY(-4px); }
</style>
