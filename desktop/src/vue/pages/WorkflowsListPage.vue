<!--
  v2.7.0 — WorkflowsListPage (Vue 3 SFC)
  Full translation of src/pages/WorkflowsListPage.tsx (347 lines).
  Shows all saved workflows + create new. Also shows mode library.
-->
<script setup lang="ts">
import { ref, onMounted, type Ref } from 'vue'
import {
  listWorkflows,
  createWorkflow,
  deleteWorkflow,
  runWorkflow,
  type Workflow,
  type NodeTypeMeta,
} from '../api/workflow'
import { listNodeTypes } from '../api/workflow'
import { getApiUrl } from '../api/client'
import { defineAsyncComponent } from 'vue'
const WorkflowEditor = defineAsyncComponent(() => import('../components/WorkflowEditor.vue'))

interface AgentMode {
  id: string
  name: string
  description: string
  category: string
  icon: string
  node_count: number
}

const workflows: Ref<Workflow[]> = ref([])
const nodeTypes: Ref<NodeTypeMeta[]> = ref([])
const editingId: Ref<string | null> = ref(null)
const editingName: Ref<string> = ref('')
const editingNodes: Ref<any[]> = ref([])
const editingEdges: Ref<any[]> = ref([])
const loading: Ref<boolean> = ref(true)
const isRunning: Ref<boolean> = ref(false)
const currentNodeId: Ref<string | null> = ref(null)
const runResult: Ref<string | null> = ref(null)
const modes: Ref<AgentMode[]> = ref([])

// Map mode id → Material Symbols icon name. Single source of truth
// instead of a nested ternary in the template.
const MODE_ICONS: Record<string, string> = {
  single_agent: 'person',
  sequential: 'arrow_forward',
  parallel: 'call_split',
  loop: 'loop',
  review_critique: 'rule',
  iterative_refine: 'upgrade',
  coordinator: 'hub',
  hierarchical: 'account_tree',
  swarm: 'all_inclusive',
  react: 'psychology',
  human_in_loop: 'pan_tool',
}

const refresh = async () => {
  loading.value = true
  try {
    const [list, types, modesData] = await Promise.all([
      listWorkflows(),
      listNodeTypes(),
      fetch(getApiUrl('/api/workflows/modes'))
        .then(r => r.json())
        .then(d => d.modes || [])
        .catch(() => []),
    ])
    workflows.value = list
    nodeTypes.value = types
    modes.value = modesData
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refresh()
})

const handleNew = async () => {
  // v2.7.0: Always include start + end nodes; LLM node added in editor.
  // Don't depend on nodeTypes.length — if the metadata API was
  // slow / failed, the user can still create a workflow.
  const wf = await createWorkflow({
    name: '未命名工作流',
    description: '',
    nodes: [
      { id: 'start-1', type: 'start', position: { x: 100, y: 200 }, data: { label: '开始' } },
      { id: 'end-1', type: 'end', position: { x: 500, y: 200 }, data: { label: '结束' } },
    ],
    edges: [],
  } as any)
  await refresh()
  editingId.value = (wf as any).id
  editingName.value = (wf as any).name
  editingNodes.value = (wf as any).nodes
  editingEdges.value = (wf as any).edges
}

const handleEdit = (wf: Workflow) => {
  editingId.value = wf.id
  editingName.value = wf.name
  editingNodes.value = wf.nodes as any[]
  editingEdges.value = wf.edges as any[]
}

const handleDelete = async (id: string) => {
  if (!confirm('确定删除这个工作流？')) return
  await deleteWorkflow(id)
  await refresh()
}

const handleSave = async (nodes: any[], edges: any[]) => {
  if (!editingId.value) return
  const r = await fetch(getApiUrl(`/api/workflows/${editingId.value}`), {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: editingName.value,
      nodes: nodes.map((n: any) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: n.data,
      })),
      edges: edges.map((e: any) => ({
        id: e.id,
        source: e.source,
        target: e.target,
      })),
    }),
  })
  if (!r.ok) throw new Error(`Save failed: ${r.status}`)
  await refresh()
}

const handleRun = async () => {
  if (!editingId.value) return
  isRunning.value = true
  currentNodeId.value = null
  runResult.value = null
  try {
    const run = await runWorkflow(editingId.value, { input: '你好' })
    runResult.value = JSON.stringify(run, null, 2)
  } catch (e: any) {
    runResult.value = `Error: ${e.message}`
  } finally {
    isRunning.value = false
  }
}

// ─── Invoke workflow dialog state ─────────────────────────────────────
import { ref as _ref } from 'vue'
const invokingWorkflow = _ref<any>(null)
const invokeInput = _ref('')
const invokeResult = _ref('')
const invokeError = _ref('')
const invokeRunning = _ref(false)

function openInvokeDialog(wf: any) {
  invokingWorkflow.value = wf
  invokeInput.value = ''
  invokeResult.value = ''
  invokeError.value = ''
}

function closeInvokeDialog() {
  invokingWorkflow.value = null
}

async function runInvokedWorkflow() {
  if (!invokingWorkflow.value || !invokeInput.value.trim()) return
  invokeRunning.value = true
  invokeError.value = ''
  invokeResult.value = ''
  try {
    const wf = invokingWorkflow.value
    const res = await fetch(getApiUrl(`/api/workflows/${wf.id}/run`), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: { input: invokeInput.value } }),
    })
    if (!res.ok) {
      const t = await res.text().catch(() => '')
      invokeError.value = `${res.status}: ${t}`
      return
    }
    const result = await res.json()
    // Pretty-print
    if (result.outputs) {
      const endNodeId = result.end_node_id || 'end-1'
      const endOutput = result.outputs[endNodeId]
      if (typeof endOutput === 'string') {
        invokeResult.value = endOutput
      } else if (endOutput && typeof endOutput === 'object') {
        // Try common fields
        invokeResult.value = endOutput.output || endOutput.text || endOutput.result || JSON.stringify(endOutput, null, 2)
      } else {
        invokeResult.value = JSON.stringify(result.outputs, null, 2)
      }
    } else if (typeof result.output === 'string') {
      invokeResult.value = result.output
    } else {
      invokeResult.value = JSON.stringify(result, null, 2)
    }
  } catch (e: any) {
    invokeError.value = `错误: ${e?.message || e}`
  } finally {
    invokeRunning.value = false
  }
}

const handleBack = async () => {
  editingId.value = null
  editingName.value = ''
  editingNodes.value = []
  editingEdges.value = []
  runResult.value = null
  await refresh()
}
</script>

<template>
  <div class="wf-page">
    <!-- Header -->
    <header class="wf-page__head">
      <div>
        <h1 class="wf-page__title">工作流</h1>
        <p class="wf-page__sub">组合节点搭建自动化流程，或挑选内置模式直接运行</p>
      </div>
      <button
        class="wf-btn wf-btn--primary"
        :disabled="loading && nodeTypes.length === 0"
        @click="handleNew"
      >
        <span class="material-symbols-outlined" style="font-size:18px">add</span>
        新建工作流
      </button>
    </header>

    <!-- Loading skeleton -->
    <div v-if="loading && workflows.length === 0" class="wf-skel-grid">
      <div v-for="i in 3" :key="i" class="wf-skel-card">
        <div class="wf-skel-line wf-skel-line--lg"></div>
        <div class="wf-skel-line wf-skel-line--md"></div>
        <div class="wf-skel-line wf-skel-line--sm"></div>
      </div>
    </div>

    <!-- Empty state -->
    <div
      v-else-if="workflows.length === 0"
      class="wf-empty"
    >
      <div class="wf-empty__icon">
        <span class="material-symbols-outlined">account_tree</span>
      </div>
      <h2 class="wf-empty__title">还没有工作流</h2>
      <p class="wf-empty__sub">点"新建工作流"创建一个，或从下方模式库挑选一个起点</p>
      <button class="wf-btn wf-btn--primary" @click="handleNew">
        <span class="material-symbols-outlined" style="font-size:18px">add</span>
        新建工作流
      </button>
    </div>

    <!-- Workflows grid -->
    <div v-else class="wf-grid">
      <article
        v-for="wf in workflows"
        :key="wf.id"
        class="wf-card"
        @click="handleEdit(wf)"
      >
        <header class="wf-card__head">
          <div class="wf-card__icon">
            <span class="material-symbols-outlined">account_tree</span>
          </div>
          <div class="wf-card__meta">
            <h3 class="wf-card__name">{{ wf.name }}</h3>
            <p class="wf-card__desc">{{ wf.description || '无描述' }}</p>
          </div>
        </header>
        <footer class="wf-card__foot">
          <span class="wf-card__chip">{{ wf.nodes.length }} 节点</span>
          <span class="wf-card__chip">v{{ wf.version }}</span>
        </footer>
        <div class="wf-card__actions" @click.stop>
          <button class="wf-card__action" @click="handleEdit(wf)">编辑</button>
          <button class="wf-card__action wf-card__action--accent" @click="openInvokeDialog(wf)">运行</button>
          <button class="wf-card__action wf-card__action--danger" @click="handleDelete(wf.id)">删除</button>
        </div>
      </article>
    </div>

    <!-- Mode library -->
    <section class="wf-modes">
      <header class="wf-section__head">
        <h2 class="wf-section__title">模式库</h2>
        <p class="wf-section__sub">预置的协作模式，可直接运行或作为模板修改</p>
      </header>
      <div class="wf-modes-grid">
        <div v-for="mode in modes" :key="mode.id" class="wf-mode">
          <div class="wf-mode__icon">
            <span class="material-symbols-outlined">{{ MODE_ICONS[mode.id] || 'tune' }}</span>
          </div>
          <div class="wf-mode__body">
            <div class="wf-mode__head">
              <span class="wf-mode__name">{{ mode.name }}</span>
              <span v-if="mode.node_count" class="wf-mode__count">{{ mode.node_count }} 节点</span>
            </div>
            <p class="wf-mode__desc">{{ mode.description }}</p>
            <div class="wf-mode__cat" v-if="mode.category">{{ mode.category }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Invoke dialog (kept original behavior) -->
    <Teleport to="body" v-if="showInvokeDialog && invokeWorkflow">
      <div
        @click.self="showInvokeDialog = false"
        style="
          position: fixed; inset: 0; z-index: 100;
          background: rgba(0,0,0,0.4);
          display: flex; align-items: center; justify-content: center;
        "
      >
        <div
          style="
            background: var(--color-surface);
            border: 1px solid var(--color-border);
            border-radius: 8px;
            padding: 24px;
            min-width: 400px;
            max-width: 600px;
          "
        >
          <h3 style="margin: 0 0 12px; font-size: 16px; font-weight: 600">运行：{{ invokeWorkflow.name }}</h3>
          <input
            v-model="invokeInput"
            placeholder='输入参数（JSON 格式）例如 {"topic": "AI"}'
            style="
              width: 100%;
              padding: 8px 12px;
              font-family: var(--font-mono);
              font-size: 13px;
              border: 1px solid var(--color-border);
              border-radius: 4px;
              background: var(--color-surface);
              color: var(--color-text-primary);
            "
            @keydown.enter="confirmInvoke"
          />
          <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px">
            <button
              @click="showInvokeDialog = false"
              style="
                padding: 8px 16px; background: transparent; border: 1px solid var(--color-border);
                border-radius: 4px; cursor: pointer; color: var(--color-text-primary);
              "
            >取消</button>
            <button
              @click="confirmInvoke"
              :disabled="invokeRunning || !invokeInput.trim()"
              :style="
                'padding: 8px 16px; background: var(--color-brand); color: #fff; border: none;'
                + ' border-radius: 4px; cursor: pointer; font-weight: 500;'
                + ' opacity: ' + ((invokeRunning || !invokeInput.trim()) ? '0.5' : '1')
              "
            >{{ invokeRunning ? '运行中…' : '▶ 运行' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
/* ── Page layout ─────────────────────────────────────────────────── */
.wf-page {
  max-width: 960px;
  margin: 0 auto;
  padding: 48px 32px 64px;
  color: var(--color-text-primary);
  height: 100%;
  overflow-y: auto;
}

.wf-page__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 32px;
}

.wf-page__title {
  font-size: 28px;
  font-weight: 600;
  margin: 0 0 4px;
  letter-spacing: -0.01em;
}

.wf-page__sub {
  margin: 0;
  font-size: 14px;
  color: var(--color-text-secondary);
}

/* ── Buttons (compact 4px, no gradients) ─────────────────────────── */
.wf-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: 1px solid transparent;
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  background: var(--color-surface);
  color: var(--color-text-primary);
  transition: background 120ms, border-color 120ms;
  font-family: inherit;
}
.wf-btn:hover { background: var(--color-surface-container-low); }
.wf-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.wf-btn--primary {
  background: var(--color-brand, #0a0a0a);
  color: #fff;
  border-color: var(--color-brand, #0a0a0a);
}
.wf-btn--primary:hover { background: #1f2937; border-color: #1f2937; }

/* ── Skeleton (loading) ──────────────────────────────────────────── */
.wf-skel-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}
.wf-skel-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.wf-skel-line {
  height: 12px;
  background: var(--color-surface-container);
  border-radius: 4px;
  animation: wf-skel-pulse 1.4s ease-in-out infinite;
}
.wf-skel-line--lg { width: 60%; height: 16px; }
.wf-skel-line--md { width: 90%; }
.wf-skel-line--sm { width: 40%; }
@keyframes wf-skel-pulse {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 0.9; }
}

/* ── Empty state ─────────────────────────────────────────────────── */
.wf-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 80px 24px;
  background: var(--color-surface-container-lowest);
  border: 1px dashed var(--color-border);
  border-radius: 12px;
  margin-bottom: 48px;
}
.wf-empty__icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--color-surface-container-low);
  margin-bottom: 16px;
}
.wf-empty__icon .material-symbols-outlined {
  font-size: 28px;
  color: var(--color-text-tertiary);
}
.wf-empty__title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 4px;
}
.wf-empty__sub {
  margin: 0 0 20px;
  font-size: 14px;
  color: var(--color-text-secondary);
}

/* ── Workflows grid ─────────────────────────────────────────────── */
.wf-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
  margin-bottom: 56px;
}
.wf-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 20px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 16px;
  transition: border-color 140ms, transform 140ms;
}
.wf-card:hover {
  border-color: var(--color-text-tertiary);
  transform: translateY(-1px);
}
.wf-card__head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.wf-card__icon {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface-container-low);
  border-radius: 6px;
}
.wf-card__icon .material-symbols-outlined {
  font-size: 20px;
  color: var(--color-text-secondary);
}
.wf-card__meta { min-width: 0; flex: 1; }
.wf-card__name {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 4px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wf-card__desc {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.wf-card__foot {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.wf-card__chip {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  background: var(--color-surface-container);
  color: var(--color-text-secondary);
  border-radius: 999px;
}
.wf-card__actions {
  display: flex;
  gap: 4px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
  margin-top: 4px;
}
.wf-card__action {
  flex: 1;
  padding: 6px 10px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-family: inherit;
  transition: background 120ms, color 120ms;
}
.wf-card__action:hover { background: var(--color-surface-container); color: var(--color-text-primary); }
.wf-card__action--accent { color: var(--color-brand, #0a0a0a); font-weight: 600; }
.wf-card__action--accent:hover { background: var(--color-brand, #0a0a0a); color: #fff; }
.wf-card__action--danger { color: #b91c1c; }
.wf-card__action--danger:hover { background: #fee2e2; color: #b91c1c; }

/* ── Section header (Mode library) ──────────────────────────────── */
.wf-modes { margin-top: 16px; }
.wf-section__head { margin-bottom: 20px; }
.wf-section__title {
  font-size: 18px;
  font-weight: 600;
  margin: 0 0 4px;
  letter-spacing: -0.01em;
}
.wf-section__sub {
  margin: 0;
  font-size: 13px;
  color: var(--color-text-secondary);
}
.wf-modes-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.wf-mode {
  display: flex;
  gap: 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px;
  transition: border-color 140ms;
}
.wf-mode:hover { border-color: var(--color-text-tertiary); }
.wf-mode__icon {
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface-container-low);
  border-radius: 6px;
}
.wf-mode__icon .material-symbols-outlined {
  font-size: 18px;
  color: var(--color-text-secondary);
}
.wf-mode__body { min-width: 0; flex: 1; }
.wf-mode__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.wf-mode__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.wf-mode__count {
  font-size: 11px;
  color: var(--color-text-tertiary);
  white-space: nowrap;
}
.wf-mode__desc {
  margin: 0 0 6px;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}
.wf-mode__cat {
  display: inline-block;
  font-size: 10px;
  font-weight: 500;
  padding: 1px 6px;
  background: var(--color-surface-container);
  color: var(--color-text-tertiary);
  border-radius: 4px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
</style>