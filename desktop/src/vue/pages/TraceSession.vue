<script setup lang="ts">
// TraceSession — replay view for one conversation's agent-step DAG.
// Fetches /api/sessions/{id}/trace and renders the TraceNode timeline
// (user input → llm_call → tool_call → tool_result) with status, timing,
// and expandable input/output.
import { ref, computed, watch } from 'vue'
import { tracesApi, type TraceNode } from '../api/traces'

const props = defineProps<{ sessionId: string }>()

const nodes = ref<TraceNode[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const expanded = ref<Set<string>>(new Set())

async function load() {
  loading.value = true
  error.value = null
  try {
    nodes.value = await tracesApi.getSession(props.sessionId)
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}
watch(() => props.sessionId, load, { immediate: true })

// Topologically sorted by depth then created_at — the backend already
// returns them in execution order, but we normalize just in case.
const sorted = computed(() =>
  [...nodes.value].sort((a, b) => (a.depth - b.depth) || (a.created_at - b.created_at)),
)

const typeIcons: Record<string, string> = {
  user_input: 'person',
  llm_call: 'psychology',
  tool_call: 'build',
  tool_result: 'check_circle',
  synthesis: 'hub',
}
const typeLabels: Record<string, string> = {
  user_input: '用户输入',
  llm_call: 'LLM 调用',
  tool_call: '工具调用',
  tool_result: '工具结果',
  synthesis: '汇总',
}
const statusColors: Record<string, string> = {
  done: 'var(--color-success)',
  running: 'var(--color-warning)',
  error: 'var(--color-error)',
  pending: 'var(--color-text-tertiary)',
  superseded: 'var(--color-text-tertiary)',
}

function toggle(id: string) {
  const next = new Set(expanded.value)
  if (next.has(id)) next.delete(id); else next.add(id)
  expanded.value = next
}

function fmtMs(node: TraceNode): string {
  if (!node.completed_at) return '—'
  const ms = Math.round((node.completed_at - node.created_at) * 1000)
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`
}
function trunc(s: string, n: number): string {
  const t = (s || '').trim()
  return t.length > n ? t.slice(0, n) + '…' : t
}
</script>

<template>
  <div class="trace-session">
    <div class="trace-session__inner">
      <div class="trace-session__head">
        <h1 class="trace-session__title">执行轨迹</h1>
        <p class="trace-session__sub">{{ nodes.length }} 个步骤 · {{ sessionId.slice(0, 16) }}</p>
      </div>

      <div v-if="loading" class="trace-session__state">
        <span class="material-symbols-outlined animate-spin text-[32px] text-[var(--color-text-tertiary)]">progress_activity</span>
        <p>加载轨迹…</p>
      </div>

      <div v-else-if="error" class="trace-session__state trace-session__state--err">
        <span class="material-symbols-outlined text-[32px] text-[var(--color-error)]">error</span>
        <p>{{ error }}</p>
        <button class="trace-session__retry" @click="load">重试</button>
      </div>

      <div v-else-if="!sorted.length" class="trace-session__state">
        <span class="material-symbols-outlined text-[48px] text-[var(--color-text-tertiary)]">timeline</span>
        <p>此会话暂无轨迹数据。</p>
      </div>

      <div v-else class="trace-timeline">
        <div
          v-for="node in sorted"
          :key="node.id"
          class="trace-node"
          :style="{ '--depth': node.depth }"
        >
          <div class="trace-node__rail">
            <span class="material-symbols-outlined text-[18px]" :style="{ color: statusColors[node.status] || 'var(--color-text-tertiary)' }">
              {{ typeIcons[node.node_type] || 'circle' }}
            </span>
            <span v-if="node.status === 'running'" class="trace-node__pulse" />
          </div>
          <div class="trace-node__card" @click="toggle(node.id)">
            <div class="trace-node__head">
              <span class="trace-node__type">{{ typeLabels[node.node_type] || node.node_type }}</span>
              <span class="trace-node__label" :title="node.label">{{ trunc(node.label || '(无标签)', 80) }}</span>
              <span class="trace-node__meta">
                <span class="trace-node__status" :style="{ color: statusColors[node.status] || 'var(--color-text-tertiary)' }">{{ node.status }}</span>
                <span class="trace-node__time">{{ fmtMs(node) }}</span>
              </span>
              <span
                v-if="node.input || node.output || node.error"
                class="material-symbols-outlined text-[16px] trace-node__chevron"
                :class="{ 'trace-node__chevron--open': expanded.has(node.id) }"
              >expand_more</span>
            </div>
            <Transition name="trace-expand">
              <div v-if="expanded.has(node.id)" class="trace-node__detail">
                <div v-if="node.error" class="trace-node__field trace-node__field--err">
                  <div class="trace-node__field-label">错误</div>
                  <pre>{{ node.error }}</pre>
                </div>
                <div v-if="node.input" class="trace-node__field">
                  <div class="trace-node__field-label">输入</div>
                  <pre>{{ trunc(node.input, 1200) }}</pre>
                </div>
                <div v-if="node.output" class="trace-node__field">
                  <div class="trace-node__field-label">输出</div>
                  <pre>{{ trunc(node.output, 1200) }}</pre>
                </div>
              </div>
            </Transition>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.trace-session { width: 100%; height: 100%; overflow-y: auto; background: var(--color-surface); }
.trace-session__inner { max-width: 860px; margin: 0 auto; padding: 24px 20px; }
.trace-session__head { margin-bottom: 20px; }
.trace-session__title { font-size: 22px; font-weight: 700; color: var(--color-text-primary); margin: 0; }
.trace-session__sub { font-size: 12px; color: var(--color-text-secondary); margin-top: 4px; font-family: var(--font-mono); }

.trace-session__state { text-align: center; padding: 60px 20px; color: var(--color-text-secondary); font-size: 14px; }
.trace-session__state span { display: block; margin-bottom: 12px; }
.trace-session__state--err p { color: var(--color-error); }
.trace-session__retry { margin-top: 12px; padding: 6px 16px; background: var(--color-primary); color: var(--color-on-primary); border: none; cursor: pointer; font-size: 13px; }

.trace-timeline { display: flex; flex-direction: column; gap: 8px; }
.trace-node { display: flex; gap: 12px; padding-left: calc(var(--depth, 0) * 20px); }
.trace-node__rail { position: relative; display: flex; align-items: flex-start; padding-top: 14px; flex-shrink: 0; width: 24px; justify-content: center; }
.trace-node__pulse { position: absolute; width: 8px; height: 8px; border-radius: 50%; background: var(--color-warning); top: 22px; left: 8px; animation: trace-pulse 1.2s infinite; }
@keyframes trace-pulse { 0%, 100% { opacity: 0.4; } 50% { opacity: 1; } }

.trace-node__card {
  flex: 1; min-width: 0; padding: 10px 14px;
  background: var(--color-surface-container-lowest);
  border: 1px solid var(--color-border);
  cursor: pointer; transition: border-color 140ms;
}
.trace-node__card:hover { border-color: var(--color-primary); }
.trace-node__head { display: flex; align-items: center; gap: 10px; }
.trace-node__type { font-size: 11px; font-weight: 600; color: var(--color-primary); background: var(--color-primary-fixed); padding: 2px 8px; flex-shrink: 0; }
.trace-node__label { flex: 1; min-width: 0; font-size: 13px; color: var(--color-text-primary); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.trace-node__meta { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.trace-node__status { font-size: 10px; font-weight: 600; text-transform: uppercase; }
.trace-node__time { font-size: 11px; color: var(--color-text-tertiary); font-family: var(--font-mono); }
.trace-node__chevron { color: var(--color-text-tertiary); transition: transform 140ms; flex-shrink: 0; }
.trace-node__chevron--open { transform: rotate(180deg); }

.trace-node__detail { margin-top: 10px; display: flex; flex-direction: column; gap: 10px; }
.trace-node__field-label { font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; color: var(--color-text-tertiary); margin-bottom: 4px; }
.trace-node__field pre { margin: 0; padding: 10px; background: var(--color-code-bg); color: var(--color-code-fg); font-family: var(--font-mono); font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-word; max-height: 300px; overflow: auto; }
.trace-node__field--err pre { background: color-mix(in srgb, var(--color-error) 8%, var(--color-surface)); color: var(--color-error); }

.trace-expand-enter-active, .trace-expand-leave-active { transition: all 160ms; overflow: hidden; }
.trace-expand-enter-from, .trace-expand-leave-to { opacity: 0; max-height: 0; }
</style>
