<script setup lang="ts">
// v3.0 — ThinkingBlock (Vue 3)
// Direct translation of ThinkingBlock.tsx — same Tailwind classes, same animations.
import { ref, computed, watch, nextTick } from 'vue'

const props = withDefaults(defineProps<{
  content: string
  isActive?: boolean
}>(), {
  isActive: false,
})

const expanded = ref(false)
const contentRef = ref<HTMLDivElement | null>(null)

const displayContent = computed(() => props.content.replace(/\r\n?/g, '\n').trimEnd())
const hasContent = computed(() => displayContent.value.trim().length > 0)

watch([() => props.content, expanded], async () => {
  if (expanded.value && props.isActive) {
    await nextTick()
    if (contentRef.value) contentRef.value.scrollTop = contentRef.value.scrollHeight
  }
})
</script>

<template>
  <div class="mb-1">
    <button
      type="button"
      @click="expanded = !expanded"
      :aria-expanded="expanded"
      class="flex w-full items-center gap-1.5 rounded-md px-1 py-0.5 text-left text-[12px] text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-secondary)]"
    >
      <span class="text-[10px] text-[var(--color-outline)]">
        {{ expanded ? '▾' : '▸' }}
      </span>
      <span class="shrink-0 font-medium italic">
        {{ isActive ? '思考中' : '思考过程' }}
        <span v-if="isActive" class="thinking-dots" />
      </span>
    </button>
    <div
      v-if="expanded && hasContent"
      ref="contentRef"
      data-thinking-content="expanded"
      class="relative mt-1 max-h-[300px] overflow-y-auto rounded-lg border border-[var(--color-border)]/40 bg-[var(--color-surface-container-lowest)] p-2.5 text-[11px] text-[var(--color-text-secondary)]"
    >
      <pre class="thinking-markdown whitespace-pre-wrap break-words font-sans">{{ displayContent }}</pre>
      <span v-if="isActive" class="thinking-cursor" />
    </div>
  </div>
</template>

<style>
@keyframes thinking-cursor-blink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}
@keyframes thinking-dots-anim {
  0%, 20% { content: ''; }
  40% { content: '.'; }
  60% { content: '..'; }
  80%, 100% { content: '...'; }
}
.thinking-cursor {
  display: inline-block; width: 2px; height: 1em;
  background: var(--color-text-tertiary);
  vertical-align: middle; margin-left: 1px;
  animation: thinking-cursor-blink 1s step-end infinite;
}
.thinking-dots::after {
  content: ''; animation: thinking-dots-anim 1.4s steps(1, end) infinite;
}
</style>
