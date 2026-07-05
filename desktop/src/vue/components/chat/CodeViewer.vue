<script setup lang="ts">
import { ref, computed } from 'vue'

/**
 * CodeViewer — Vue 3 port of components/chat/CodeViewer.tsx
 * Code block with language label and copy button.
 */

export interface CodeViewerProps {
  code: string
  language?: string
  fileName?: string
}

const props = withDefaults(defineProps<CodeViewerProps>(), { language: 'text' })
const copied = ref(false)

function copyCode() {
  navigator.clipboard?.writeText(props.code).catch(() => {
    const ta = document.createElement('textarea'); ta.value = props.code
    ta.style.position = 'fixed'; ta.style.opacity = '0'
    document.body.appendChild(ta); ta.select(); document.execCommand('copy')
    document.body.removeChild(ta)
  })
  copied.value = true
  setTimeout(() => { copied.value = false }, 2000)
}

const languageLabel = computed(() => props.language.replace(/\b\w/g, (c) => c.toUpperCase()))
</script>

<template>
  <div class="overflow-hidden rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-terminal-bg)]">
    <div class="flex items-center justify-between border-b border-[var(--color-border)]/65 bg-[var(--color-surface-container)] px-3 py-1.5">
      <div class="flex items-center gap-2">
        <span v-if="fileName" class="font-[var(--font-mono)] text-[10px] text-[var(--color-text-tertiary)]">{{ fileName }}</span>
        <span class="rounded-full bg-[var(--color-brand)]/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-[var(--color-brand)]">{{ languageLabel }}</span>
      </div>
      <button type="button" @click="copyCode" class="rounded-md px-2 py-1 text-[10px] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-container-low)] hover:text-[var(--color-text-primary)]">
        <span class="material-symbols-outlined text-[13px] mr-1">{{ copied ? 'check' : 'content_copy' }}</span>
        {{ copied ? 'Copied!' : 'Copy' }}
      </button>
    </div>
    <pre class="overflow-x-auto p-3 font-[var(--font-mono)] text-[12px] leading-relaxed text-[var(--color-text-primary)]"><code>{{ code }}</code></pre>
  </div>
</template>
