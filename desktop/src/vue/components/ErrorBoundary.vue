<script setup lang="ts">
// v3.0 — ErrorBoundary (Vue 3)
// Full translation of ErrorBoundary.tsx — error catch + fallback.
//
// NOTE: Vue 3 has no native error-boundary component equivalent to React's
// static getDerivedStateFromError / componentDidCatch class pattern.
// onErrorCaptured catches errors from CHILD components. Errors thrown
// inside this component's own render won't be caught by itself — that
// matches React's own limitation. For app-level fallback we rely on the
// parent (App.vue) wiring the fallback via onErrorCaptured on this boundary.
// The fallback mirror preserves the patched debugging behaviour of
// React's ErrorBoundaryFallback (window.__lastReactError) and wired
// diagnostic reporting.
import { ref, onMounted, onErrorCaptured, type ErrorCapturedHook } from 'vue'
import { t } from '../../i18n'

// Fallback state lives in the component's reactive scope
const hasError = ref(false)
const errMsg = ref('Click "重试" to retry')

// Catch errors thrown from child components
onErrorCaptured((err: unknown) => {
  hasError.value = true
  try {
    const msg =
      err instanceof Error
        ? `${err.message}\n${err.stack ?? ''}`
        : String(err)
    errMsg.value = msg
  } catch {
    /* keep default message */
  }
  return false // prevent propagation — same as React's getDerivedStateFromError
})

// Debug stub: mimic the React patched behaviour that reads
// window.__lastReactError (written by componentDidCatch on the parent's
// error boundary). In Vue, componentDidCatch doesn't exist; this is the
// closest equivalent and kept purely for parity with the React debug patch.
onMounted(() => {
  try {
    const last = (window as any).__lastReactError
    if (last) {
      errMsg.value = String(last)
    }
  } catch {
    /* ignore */
  }
})

function retry() {
  if (typeof window !== 'undefined') {
    window.location.reload()
  }
}
</script>

<template>
  <slot v-if="!hasError" />

  <div
    v-else
    class="h-screen w-screen bg-[var(--color-bg-primary)] text-[var(--color-text-primary)] flex items-center justify-center p-6"
  >
    <div class="max-w-md w-full text-center">
      <div class="text-base font-semibold">{{ t('errorBoundary.title') }}</div>
      <div
        class="mt-2 text-xs text-[var(--color-text-tertiary)] whitespace-pre-wrap font-mono bg-[var(--color-surface)] p-2 rounded"
      >
        {{ errMsg }}
      </div>
      <div class="mt-2 text-sm text-[var(--color-text-tertiary)]">
        {{ t('errorBoundary.description') }}
      </div>
      <div class="mt-4 flex justify-center">
        <button
          type="button"
          class="px-4 py-2 text-sm rounded-[var(--radius-md)] bg-[var(--color-surface-container)] text-[var(--color-text-primary)] border border-[var(--color-border)] hover:bg-[var(--color-surface-container-high)] cursor-pointer"
          @click="retry"
        >
          {{ t('common.retry') }}
        </button>
      </div>
      <div class="mt-4 text-left">
        <!-- DoctorPanel is an external diagnostic UI; render via slot so
             consumers can provide their implementation. -->
        <slot name="doctor-panel" />
      </div>
    </div>
  </div>
</template>
