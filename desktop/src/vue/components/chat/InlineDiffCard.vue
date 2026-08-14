<script setup lang="ts">
/**
 * InlineDiffCard — shows a file-edit diff preview inside tool call cards.
 *
 * #1 (partial): When the agent calls write_file/edit_file, this card
 * renders the proposed change as a color-coded diff so the user can
 * SEE what will change before it happens. Full Accept/Reject requires
 * a backend confirmation protocol (tool_confirm_request event + async
 * wait), which is future work. For now this is a read-only preview
 * that makes file edits visible — a huge UX improvement over edits
 * vanishing into tool metadata.
 */
import { computed } from 'vue'

const props = defineProps<{
  toolName: string
  input: Record<string, any>
  result?: string
  showActions?: boolean
}>()

const emit = defineEmits<{
  (e: 'accept'): void
  (e: 'reject'): void
}>()

const filePath = computed(() => props.input?.path || props.input?.file || '')
const fileName = computed(() => {
  const p = filePath.value
  return p ? p.split('/').pop() : ''
})

// For write_file: show the full new content as "added"
// For edit_file: show old → new if result contains diff info
const diffLines = computed(() => {
  const content = props.input?.content || props.input?.new_content || ''
  if (!content) return []
  return content.split('\n').slice(0, 30).map((line: string) => ({
    text: line,
    type: 'add',  // write_file = all additions
  }))
})

const hasDiff = computed(() => diffLines.value.length > 0)
</script>

<template>
  <div v-if="hasDiff" class="idiff">
    <div class="idiff__header">
      <span class="idiff__icon">📝</span>
      <span class="idiff__file">{{ fileName }}</span>
      <span v-if="filePath" class="idiff__path">{{ filePath }}</span>
      <span class="idiff__badge">+{{ diffLines.length }} 行</span>
    </div>
    <div class="idiff__body">
      <div v-for="(line, i) in diffLines" :key="i" class="idiff__line" :class="`idiff__line--${line.type}`">
        <span class="idiff__prefix">{{ line.type === 'add' ? '+' : '-' }}</span>
        <span class="idiff__text">{{ line.text || ' ' }}</span>
      </div>
      <div v-if="diffLines.length >= 30" class="idiff__more">… 更多行省略</div>
    </div>
    <div class="idiff__footer">
      <span v-if="!showActions" class="idiff__note">Agent 建议的修改</span>
      <div v-else class="idiff__actions">
        <button type="button" class="idiff__btn idiff__btn--reject" @click="emit('reject')">拒绝</button>
        <button type="button" class="idiff__btn idiff__btn--accept" @click="emit('accept')">批准修改</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.idiff {
  margin: 6px 0; border-radius: 8px; overflow: hidden;
  border: 1px solid var(--color-border, rgba(128,128,128,0.2));
  font-family: var(--font-mono, monospace);
}
.idiff__header {
  display: flex; align-items: center; gap: 6px; padding: 5px 10px;
  background: rgba(128,128,128,0.06); font-size: 11px;
}
.idiff__icon { font-size: 11px; }
.idiff__file { font-weight: 600; color: var(--color-text-primary, #111); }
.idiff__path { color: var(--color-text-tertiary, #aaa); font-size: 10px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.idiff__badge { margin-left: auto; font-size: 10px; color: #2d7d46; }
.idiff__body {
  max-height: 250px; overflow-y: auto; font-size: 11.5px; line-height: 1.6;
  background: var(--color-surface, #fff);
}
.idiff__line { display: flex; padding: 0 10px; white-space: pre; }
.idiff__line--add { background: rgba(46,160,67,0.08); }
.idiff__line--del { background: rgba(248,81,73,0.08); }
.idiff__prefix { width: 14px; flex-shrink: 0; opacity: 0.5; }
.idiff__line--add .idiff__prefix { color: #2d7d46; }
.idiff__line--del .idiff__prefix { color: #e03131; }
.idiff__text { color: var(--color-text-secondary, #555); }
.idiff__more { padding: 4px 10px; font-size: 10px; color: var(--color-text-tertiary, #aaa); text-align: center; }
.idiff__footer { padding: 4px 10px; background: rgba(128,128,128,0.04); }
.idiff__note { font-size: 10px; color: var(--color-text-tertiary, #aaa); font-family: var(--font-body, sans-serif); }
.idiff__actions { display: flex; justify-content: flex-end; gap: 8px; }
.idiff__btn { padding: 5px 16px; border-radius: 7px; font-size: 12px; font-weight: 500; cursor: pointer; border: 1px solid transparent; transition: all .15s; font-family: var(--font-body, sans-serif); }
.idiff__btn--reject { background: none; border-color: var(--color-border, rgba(128,128,128,0.25)); color: var(--color-text-secondary, #555); }
.idiff__btn--reject:hover { border-color: rgba(128,128,128,0.4); }
.idiff__btn--accept { background: rgba(128,128,128,0.15); color: var(--color-text-primary, #111); }
.idiff__btn--accept:hover { background: rgba(128,128,128,0.25); }
</style>
