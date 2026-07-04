<script setup lang="ts">
// v3.0 — Thinking block (Vue 3)
// Expandable panel for showing the model's "thinking" output. Skips
// markdown rendering — the parent can pass pre-formatted text.
import { ref, watch, nextTick } from 'vue'

const props = withDefaults(defineProps<{
  content: string
  isActive?: boolean
}>(), {
  isActive: false,
})

const expanded = ref(false)
const contentRef = ref<HTMLDivElement | null>(null)

const display = () => props.content.replace(/\r\n?/g, '\n').trimEnd()
const hasContent = () => display().trim().length > 0

watch([() => props.content, expanded], async () => {
  if (expanded.value && props.isActive) {
    await nextTick()
    if (contentRef.value) {
      contentRef.value.scrollTop = contentRef.value.scrollHeight
    }
  }
})
</script>

<template>
  <div class="madcop-thinking">
    <button
      type="button"
      class="madcop-thinking__head"
      :aria-expanded="expanded"
      @click="expanded = !expanded"
    >
      <span class="madcop-thinking__arrow">{{ expanded ? '▾' : '▸' }}</span>
      <span class="madcop-thinking__label">
        {{ isActive ? '思考中' : '思考过程' }}
        <span v-if="isActive" class="madcop-thinking__dots" />
      </span>
    </button>
    <div
      v-if="expanded && hasContent()"
      ref="contentRef"
      class="madcop-thinking__body"
    >
      <pre class="madcop-thinking__text">{{ display() }}<span v-if="isActive" class="madcop-thinking__cursor" /></pre>
    </div>
  </div>
</template>

<style scoped>
.madcop-thinking { margin-bottom: 4px; }
.madcop-thinking__head {
  display: flex; align-items: center; gap: 6px;
  width: 100%; padding: 2px 4px;
  background: transparent; border: none; cursor: pointer; text-align: left;
  font-size: 11px; color: var(--madcop-ink-muted);
}
.madcop-thinking__head:hover { color: var(--madcop-ink-body); }
.madcop-thinking__arrow { font-size: 10px; color: var(--madcop-ink-subtle); }
.madcop-thinking__label { font-style: italic; font-weight: 500; }
.madcop-thinking__dots::after {
  content: '...'; animation: madcop-thinking-dots 1.4s steps(1, end) infinite;
}
@keyframes madcop-thinking-dots {
  0%, 20% { content: ''; }
  40% { content: '.'; }
  60% { content: '..'; }
  80%, 100% { content: '...'; }
}
.madcop-thinking__body {
  position: relative;
  margin-top: 4px;
  max-height: 240px; overflow-y: auto;
  padding: 10px;
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-raised);
  font-size: 11px; color: var(--madcop-ink-body);
}
.madcop-thinking__text {
  margin: 0;
  font-family: 'Geist Mono', monospace;
  line-height: 1.5; white-space: pre-wrap;
}
.madcop-thinking__cursor {
  display: inline-block; width: 6px; height: 1em;
  background: var(--madcop-ink-muted);
  vertical-align: middle; margin-left: 1px;
  animation: madcop-cursor-blink 1s step-end infinite;
}
@keyframes madcop-cursor-blink { 50% { opacity: 0; } }
</style>
