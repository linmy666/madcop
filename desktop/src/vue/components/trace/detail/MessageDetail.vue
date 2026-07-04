<script setup lang="ts">
// v3.0 — MessageDetail (trace detail, Vue 3)
// Direct translation — same Section usage, same JSON viewer.
import { computed } from 'vue'
import Section from './Section.vue'

const props = defineProps<{
  content?: string
  rawJson?: string
}>()

const hasContent = computed(() => Boolean(props.content && props.content.trim()))
</script>

<template>
  <div data-testid="trace-message-detail">
    <Section section-key="message.content" title="内容" :default-open="true">
      <div v-if="hasContent" class="text-sm leading-relaxed text-[var(--color-text-secondary)] whitespace-pre-wrap break-words">
        {{ content }}
      </div>
      <div v-else class="rounded-[var(--radius-md)] border border-dashed border-[var(--color-border)] px-3 py-3 text-xs text-[var(--color-text-tertiary)]">
        无数据
      </div>
    </Section>
    <Section v-if="rawJson" section-key="message.raw" title="原始 JSON">
      <pre class="font-[var(--font-mono)] text-xs leading-relaxed text-[var(--color-text-secondary)] whitespace-pre-wrap break-words max-h-[400px] overflow-auto">{{ rawJson }}</pre>
    </Section>
  </div>
</template>
