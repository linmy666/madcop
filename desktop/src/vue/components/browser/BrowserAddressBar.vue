<script setup lang="ts">
// v3.0 — BrowserAddressBar (Vue 3)
// Direct translation — same Tailwind classes, same nav logic.
// Uses material-symbols instead of lucide-react icons.
import { ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  url: string
  canGoBack: boolean
  canGoForward: boolean
  loading?: boolean
}>(), {
  loading: false,
})

const emit = defineEmits<{
  (e: 'navigate', url: string): void
  (e: 'back'): void
  (e: 'forward'): void
  (e: 'reload'): void
}>()

const draft = ref(props.url)
watch(() => props.url, (v) => { draft.value = v })

function normalizeBrowserAddress(input: string): string {
  const value = input.trim()
  if (!value) return ''
  if (/^[a-z][a-z\d+-.]*:\/\//i.test(value) || /^(about|data|file):/i.test(value)) return value
  if (/^(localhost|127(?:\.\d{1,3}){3}|\[::1\]|::1)(?::\d+)?(?:[/?#].*)?$/i.test(value)) {
    return `http://${value}`
  }
  return `https://${value}`
}

function submit(e: Event) {
  e.preventDefault()
  emit('navigate', normalizeBrowserAddress(draft.value))
}
</script>

<template>
  <div
    data-testid="browser-address-bar"
    class="relative flex h-11 items-center gap-1 border-b border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] px-2"
  >
    <button aria-label="后退" :disabled="!canGoBack" @click="emit('back')" class="p-1 disabled:opacity-40">
      <span class="material-symbols-outlined text-[16px]">arrow_back</span>
    </button>
    <button aria-label="前进" :disabled="!canGoForward" @click="emit('forward')" class="p-1 disabled:opacity-40">
      <span class="material-symbols-outlined text-[16px]">arrow_forward</span>
    </button>
    <button aria-label="刷新" :aria-busy="loading" @click="emit('reload')" class="p-1">
      <span v-if="loading" class="material-symbols-outlined text-[16px] animate-spin">progress_activity</span>
      <span v-else class="material-symbols-outlined text-[16px]">refresh</span>
    </button>
    <form class="min-w-0 flex-1" @submit="submit">
      <input
        class="w-full rounded-md bg-[var(--color-surface)] px-2 py-1 text-xs text-[var(--color-text-primary)]"
        v-model="draft"
        placeholder="输入网址..."
        spellcheck="false"
      />
    </form>
    <div v-if="$slots.default" data-testid="browser-toolbar-actions" class="ml-1 flex shrink-0 items-center gap-1">
      <slot />
    </div>
    <div
      v-if="loading"
      role="progressbar"
      aria-label="加载中"
      data-testid="browser-loading-bar"
      class="progress-indeterminate-track pointer-events-none absolute inset-x-0 bottom-0 h-0.5"
    />
  </div>
</template>
