<script setup lang="ts">
// v3.0 — ErrorBoundary (Vue 3)
// Vue 3 uses onErrorCaptured instead of React's error boundary class.
import { ref, onErrorCaptured } from 'vue'

const hasError = ref(false)
const errMsg = ref('点击"重试"重试')

onErrorCaptured((err: unknown) => {
  hasError.value = true
  try {
    errMsg.value = err instanceof Error ? `${err.message}\n${err.stack ?? ''}` : String(err)
  } catch {}
  return false  // prevent error from propagating
})

function retry() {
  hasError.value = false
  errMsg.value = ''
  if (typeof window !== 'undefined') window.location.reload()
}
</script>

<template>
  <div v-if="hasError" class="h-screen w-screen bg-[var(--color-bg-primary)] text-[var(--color-text-primary)] flex items-center justify-center p-6">
    <div class="max-w-md w-full text-center">
      <div class="text-base font-semibold">页面出错了</div>
      <div class="mt-2 text-xs text-[var(--color-text-tertiary)] whitespace-pre-wrap font-mono bg-[var(--color-surface)] p-2 rounded">
        {{ errMsg }}
      </div>
      <div class="mt-2 text-sm text-[var(--color-text-tertiary)]">
        如果持续出现，请尝试重启 MadCop。
      </div>
      <div class="mt-4 flex justify-center">
        <button
          type="button"
          class="px-4 py-2 text-sm rounded-[var(--radius-md)] bg-[var(--color-surface)] text-[var(--color-text-primary)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] cursor-pointer"
          @click="retry"
        >重试</button>
      </div>
    </div>
  </div>
  <slot v-else />
</template>
