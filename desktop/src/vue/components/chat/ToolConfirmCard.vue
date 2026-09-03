<script setup lang="ts">
/**
 * ToolConfirmCard — HITL approval card for mutating tool calls.
 *
 * Design language: thin border, monospace tool name, minimal icon (line
 * style, single accent color), no cartoon imagery. Matches the
 * ToolCallInline aesthetic.
 *
 * Qoder-style scoped approval: for file tools the approve button offers
 * "仅此一次" and "本会话始终允许此目录" — the latter records a dir-prefix
 * approval server-side so a 20-file build doesn't pop 20 identical cards.
 */
import { computed } from 'vue'

const props = defineProps<{
  toolName: string
  input: Record<string, unknown>
  /** P0-3: total queued confirmations — >1 shows a waiting counter. */
  queueCount?: number
}>()

const emit = defineEmits<{
  (e: 'respond', approved: boolean, scope: 'once' | 'session'): void
}>()

const detail = computed(() => {
  const inp = props.input || {}
  const path = inp.path || inp.file_path || inp.filePath
  if (typeof path === 'string' && path) return path
  const query = inp.query || inp.command || inp.cmd
  if (typeof query === 'string' && query) return query.slice(0, 60)
  const keys = Object.keys(inp).slice(0, 3)
  return keys.join(', ')
})

/** File tools whose target path can carry a directory scope. */
const FILE_TOOLS = new Set(['write_file', 'edit_file', 'write_xlsx', 'write_pptx', 'apply_patch'])

/** apply_patch: parse the patch body into colored diff lines so the
 *  card previews what will change before approval (codex parity). */
const patchLines = computed<{ op: string; text: string }[]>(() => {
  if (props.toolName !== 'apply_patch') return []
  const inp = props.input || {}
  const patch = typeof inp.patch === 'string' ? inp.patch : ''
  if (!patch.trim()) return []
  const out: { op: string; text: string }[] = []
  for (const raw of patch.replace(/\r\n/g, '\n').split('\n')) {
    if (raw.startsWith('*** Begin Patch') || raw.startsWith('*** End Patch')) continue
    if (raw.startsWith('*** ')) { out.push({ op: 'hdr', text: raw.slice(4) }); continue }
    if (raw.startsWith('+')) out.push({ op: 'add', text: raw.slice(1) })
    else if (raw.startsWith('-')) out.push({ op: 'del', text: raw.slice(1) })
    else if (raw.startsWith('@@')) out.push({ op: 'anchor', text: raw })
    else out.push({ op: 'ctx', text: raw.replace(/^ /, '') })
  }
  return out.slice(0, 60)
})

const targetDir = computed(() => {
  if (!FILE_TOOLS.has(props.toolName)) return ''
  const inp = props.input || {}
  const p = String(inp.path || inp.file_path || inp.filePath || '')
  if (!p) return ''
  const i = Math.max(p.lastIndexOf('/'), p.lastIndexOf('\\'))
  return i > 0 ? p.slice(0, i) : ''
})

const sizeHint = computed(() => {
  const inp = props.input || {}
  const content = inp.content
  if (typeof content === 'string' && content.length > 0) {
    return `${Math.round(content.length / 1024)}KB`
  }
  return ''
})
</script>

<template>
  <div class="tcc" data-testid="tool-confirm-card">
    <div class="tcc__header">
      <span class="tcc__icon" aria-hidden="true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>
        </svg>
      </span>
      <span class="tcc__label">需要确认</span>
      <span class="tcc__tool">{{ toolName }}</span>
      <span v-if="queueCount && queueCount > 1" class="tcc__queue">+{{ queueCount - 1 }} 待确认</span>
      <span v-if="sizeHint" class="tcc__size">{{ sizeHint }}</span>
    </div>
    <div v-if="detail" class="tcc__detail">{{ detail }}</div>
    <pre v-if="patchLines.length" class="tcc__patch"><code
      v-for="(ln, i) in patchLines"
      :key="i"
      :class="`tcc__patch-line tcc__patch-line--${ln.op}`"
    >{{ ln.text }}</code></pre>
    <div class="tcc__actions">
      <button type="button" class="tcc__btn tcc__btn--deny" @click="emit('respond', false, 'once')">拒绝</button>
      <button
        v-if="targetDir"
        type="button"
        class="tcc__btn tcc__btn--scope"
        :title="`本会话内 ${targetDir} 下的 ${toolName} 不再逐次确认`"
        @click="emit('respond', true, 'session')"
      >本会话允许此目录</button>
      <button type="button" class="tcc__btn tcc__btn--approve" @click="emit('respond', true, 'once')">仅此一次</button>
    </div>
  </div>
</template>

<style scoped>
.tcc {
  margin: 6px 0;
  padding: 10px 14px;
  border: 1px solid var(--color-border, rgba(128,128,128,0.25));
  border-radius: 8px;
  background: var(--color-surface, #fafafa);
}
.tcc__header {
  display: flex;
  align-items: center;
  gap: 6px;
}
.tcc__icon {
  display: flex;
  color: var(--color-text-secondary, #666);
}
.tcc__label {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-primary, #111);
}
.tcc__tool {
  font-family: var(--font-mono, monospace);
  font-size: 12px;
  color: var(--color-text-secondary, #555);
}
.tcc__queue {
  font-size: 10px;
  color: var(--color-text-tertiary, #999);
  padding: 1px 6px;
  border: 1px solid var(--color-border, rgba(128,128,128,0.25));
  border-radius: 999px;
}
.tcc__size {
  margin-left: auto;
  font-size: 10px;
  color: var(--color-text-tertiary, #999);
}
.tcc__detail {
  margin-top: 6px;
  font-family: var(--font-mono, monospace);
  font-size: 11px;
  color: var(--color-text-tertiary, #888);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tcc__actions {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}
.tcc__btn {
  padding: 5px 16px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.15s;
}
.tcc__btn--deny {
  background: none;
  border-color: var(--color-border, rgba(128,128,128,0.25));
  color: var(--color-text-secondary, #555);
}
.tcc__btn--deny:hover {
  border-color: var(--color-text-tertiary, #999);
}
.tcc__btn--scope {
  background: none;
  border-color: var(--color-border, rgba(128,128,128,0.25));
  color: var(--color-text-secondary, #555);
}
.tcc__btn--scope:hover {
  border-color: var(--color-text-primary, #111);
  color: var(--color-text-primary, #111);
}
.tcc__btn--approve {
  background: var(--color-text-primary, #111);
  color: var(--color-surface, #fff);
}
.tcc__btn--approve:hover {
  opacity: 0.85;
}

.tcc__patch {
  margin: 8px 0 0;
  max-height: 180px;
  overflow: auto;
  padding: 8px 10px;
  border: 1px solid var(--color-border, rgba(128,128,128,0.25));
  border-radius: 6px;
  background: var(--color-surface-container-low, #f4f4f4);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre;
}
.tcc__patch-line { display: block; }
.tcc__patch-line--add { color: #16a34a; background: rgba(22,163,74,0.08); }
.tcc__patch-line--del { color: var(--color-error, #dc2626); background: rgba(220,38,38,0.07); text-decoration: line-through; }
.tcc__patch-line--hdr { color: var(--color-text-primary, #111); font-weight: 600; }
.tcc__patch-line--anchor { color: var(--color-text-tertiary, #888); }
.tcc__patch-line--ctx { color: var(--color-text-secondary, #555); }
</style>