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
import { computed, ref } from 'vue'

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

/** bash/run_command: long command preview with monospace formatting +
 *  a simple risk tag (network / destructive / read-only). User asked
 *  for this after seeing plain "mkdir && ls" cards sit next to
 *  "rm -rf /" cards with no visual distinction. */
const isShell = computed(() => ['bash', 'run_command'].includes(props.toolName))
const cmdText = computed(() => {
  if (!isShell.value) return ''
  const inp = props.input || {}
  return String(inp.command || inp.cmd || '')
})
const cmdExpanded = ref(false)
/** Cheap risk heuristic: destructive (rm -rf, dd to /dev, mkfs),
 *  network (curl|wget|ssh), read-only (ls/cat/grep). Keeps the
 *  card consistent across bash invocations without depending on the
 *  backend's exec_policy engine. */
const cmdRisk = computed<{ level: 'destructive' | 'network' | 'safe'; label: string } | null>(() => {
  if (!isShell.value) return null
  const cmd = cmdText.value.toLowerCase()
  if (/\brm\s+-rf?\b|\bmkfs\b|\bdd\s+if=.+of=\/dev\//.test(cmd)) {
    return { level: 'destructive', label: '高危' }
  }
  if (/\b(curl|wget|ssh|scp|rsync|nc|netcat)\b/.test(cmd)) {
    return { level: 'network', label: '联网' }
  }
  if (/\b(ls|cat|head|tail|grep|find|pwd|echo|which|file)\b/.test(cmd)) {
    return { level: 'safe', label: '只读' }
  }
  return null
})

const showCmdPreview = computed(() => cmdText.value.length > 60)

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
    <div v-if="isShell" class="tcc__cmd">
      <div class="tcc__cmd-meta">
        <span
          v-if="cmdRisk"
          :class="[
            'tcc__risk',
            cmdRisk.level === 'destructive' ? 'tcc__risk--destructive'
              : cmdRisk.level === 'network' ? 'tcc__risk--network'
              : 'tcc__risk--safe'
          ]"
        >{{ cmdRisk.label }}</span>
        <button
          v-if="showCmdPreview"
          type="button"
          class="tcc__cmd-toggle"
          @click="cmdExpanded = !cmdExpanded"
        >{{ cmdExpanded ? '折叠' : '展开' }}</button>
      </div>
      <pre class="tcc__cmd-pre" :class="{ 'tcc__cmd-pre--clamp': !cmdExpanded }">{{ cmdText }}</pre>
    </div>
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
  background: var(--color-surface-hover);
  border-color: var(--color-text-primary, #111);
  color: var(--color-text-primary, #111);
}
.tcc__cmd {
  margin: 8px 0 0;
  border: 1px solid var(--color-border, rgba(128,128,128,0.25));
  border-radius: 6px;
  overflow: hidden;
}
.tcc__cmd-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 10px;
  background: var(--color-surface-container-low, #f4f4f4);
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.tcc__risk {
  display: inline-flex;
  align-items: center;
  padding: 1px 8px;
  border-radius: 999px;
  font-weight: 600;
  font-size: 10px;
  letter-spacing: 0.5px;
}
.tcc__risk--destructive {
  color: var(--color-error, #dc2626);
  background: rgba(220, 38, 38, 0.12);
}
.tcc__risk--network {
  color: #b45309;
  background: rgba(180, 83, 9, 0.12);
}
.tcc__risk--safe {
  color: var(--color-text-tertiary);
  background: var(--color-surface-container);
}
.tcc__cmd-toggle {
  background: transparent;
  border: 0;
  color: var(--color-brand);
  font-size: 11px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
}
.tcc__cmd-toggle:hover {
  background: var(--color-surface-hover);
}
.tcc__cmd-pre {
  margin: 0;
  padding: 8px 10px;
  background: var(--color-surface-container-lowest, #fafafa);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-all;
  color: var(--color-text-primary);
}
.tcc__cmd-pre--clamp {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
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