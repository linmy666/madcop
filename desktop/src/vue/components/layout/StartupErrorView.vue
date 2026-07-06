<script setup lang="ts">
function handleReload() { globalThis.window.location.reload() }
// v3.0 — StartupErrorView (Vue 3)
// Direct translation — same Tailwind classes, same error/logs layout.
import { ref, computed } from 'vue'
import Button from '../shared/Button.vue'

const props = defineProps<{ error: string }>()

const LOG_MARKER = '\n\nRecent server logs:\n'

const parsed = computed(() => {
  const idx = props.error.indexOf(LOG_MARKER)
  if (idx === -1) return { message: props.error, logs: '' }
  return {
    message: props.error.slice(0, idx).trim(),
    logs: props.error.slice(idx + LOG_MARKER.length).trim(),
  }
})

const copied = ref(false)

async function handleCopy() {
  try {
    await navigator.clipboard.writeText(props.error)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1600)
  } catch {}
}
</script>

<template>
  <div class="h-screen flex items-center justify-center bg-[var(--color-surface)] px-6">
    <section class="w-full max-w-3xl rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-6 shadow-md">
      <div class="flex flex-col gap-4">
        <div>
          <h1 class="text-lg font-semibold text-[var(--color-text-primary)]">后端服务启动失败</h1>
          <p class="mt-2 text-sm text-[var(--color-text-secondary)]">MadCop 后端服务未能正确启动。请检查下方错误信息。</p>
        </div>

        <div class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <div class="text-xs font-medium uppercase text-[var(--color-text-tertiary)]">启动错误</div>
          <pre class="mt-2 max-h-28 overflow-auto whitespace-pre-wrap break-words font-mono text-xs text-[var(--color-error)]">{{ parsed.message }}</pre>
        </div>

        <div v-if="parsed.logs" class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <div class="text-xs font-medium uppercase text-[var(--color-text-tertiary)]">服务器日志</div>
          <pre class="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-relaxed text-[var(--color-text-secondary)]">{{ parsed.logs }}</pre>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <Button type="button" variant="secondary" size="sm" @click="handleCopy">
            <template #icon><span class="material-symbols-outlined text-[16px]">content_copy</span></template>
            {{ copied ? '已复制' : '复制诊断信息' }}
          </Button>
          <Button type="button" variant="ghost" size="sm" @click="handleReload">
            <template #icon><span class="material-symbols-outlined text-[16px]">refresh</span></template>
            重试
          </Button>
        </div>
      </div>
    </section>
  </div>
</template>
