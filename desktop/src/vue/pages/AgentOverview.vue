<script setup lang="ts">
/**
 * AgentOverview — the "🤖 Agent" main page.
 *
 * Replaces: AgentHub.vue + AgentNetwork.vue + Arena (concept) into one cohesive page.
 * Layout:
 *   Top: 5 graph-theory topology presets (single → chain → parallel → debate → ensemble)
 *   Center: GraphCanvas (SVG, drag nodes, select to configure)
 *   Right: Node config panel (model, role, tools)
 *   Bottom: Run / Save / Stats
 *
 * All pure text, zero icons. Graph-theory aesthetic.
 */

import { ref, computed, onMounted } from 'vue'
import GraphCanvas, { type GraphNodeData, type GraphEdgeData } from '../components/graph/GraphCanvas.vue'
import { getApiUrl } from '../api/client'

// ─── Topology presets ──────────────────────────────────────────────────

interface TopologyPreset {
  id: string
  name: string
  nameEn: string
  desc: string
  buildNodes: () => GraphNodeData[]
  buildEdges: () => GraphEdgeData[]
}

const presets: TopologyPreset[] = [
  {
    id: 'single',
    name: '单节点',
    nameEn: 'Single',
    desc: '一个 LLM 独立完成所有任务',
    buildNodes: () => [
      { id: 'n1', label: 'Agent', detail: '', x: 500, y: 300, status: 'idle' },
    ],
    buildEdges: () => [],
  },
  {
    id: 'chain',
    name: '链式',
    nameEn: 'Chain',
    desc: '顺序传递: 规划 → 执行 → 审查',
    buildNodes: () => [
      { id: 'n1', label: '规划', detail: '', x: 200, y: 300, status: 'idle' },
      { id: 'n2', label: '执行', detail: '', x: 500, y: 300, status: 'idle' },
      { id: 'n3', label: '审查', detail: '', x: 800, y: 300, status: 'idle' },
    ],
    buildEdges: () => [
      { id: 'e1', from: 'n1', to: 'n2', type: 'dependency' },
      { id: 'e2', from: 'n2', to: 'n3', type: 'dependency' },
    ],
  },
  {
    id: 'parallel',
    name: '并行',
    nameEn: 'Parallel',
    desc: '多 Agent 同时工作，结果汇聚',
    buildNodes: () => [
      { id: 'n0', label: '分发', detail: '', x: 200, y: 300, status: 'idle' },
      { id: 'n1', label: '前端', detail: '', x: 500, y: 150, status: 'idle' },
      { id: 'n2', label: '后端', detail: '', x: 500, y: 300, status: 'idle' },
      { id: 'n3', label: '测试', detail: '', x: 500, y: 450, status: 'idle' },
      { id: 'n4', label: '聚合', detail: '', x: 800, y: 300, status: 'idle' },
    ],
    buildEdges: () => [
      { id: 'e1', from: 'n0', to: 'n1', type: 'flow' },
      { id: 'e2', from: 'n0', to: 'n2', type: 'flow' },
      { id: 'e3', from: 'n0', to: 'n3', type: 'flow' },
      { id: 'e4', from: 'n1', to: 'n4', type: 'dependency' },
      { id: 'e5', from: 'n2', to: 'n4', type: 'dependency' },
      { id: 'e6', from: 'n3', to: 'n4', type: 'dependency' },
    ],
  },
  {
    id: 'debate',
    name: '辩论',
    nameEn: 'Debate',
    desc: '提议者 ↔ 批判者对抗，评判者裁决',
    buildNodes: () => [
      { id: 'n1', label: '提议者', detail: '', x: 300, y: 200, status: 'idle' },
      { id: 'n2', label: '批判者', detail: '', x: 300, y: 400, status: 'idle' },
      { id: 'n3', label: '评判者', detail: '', x: 700, y: 300, status: 'idle' },
    ],
    buildEdges: () => [
      { id: 'e1', from: 'n1', to: 'n2', type: 'flow', label: '提议' },
      { id: 'e2', from: 'n2', to: 'n1', type: 'flow', label: '反驳' },
      { id: 'e3', from: 'n1', to: 'n3', type: 'dependency' },
      { id: 'e4', from: 'n2', to: 'n3', type: 'dependency' },
    ],
  },
  {
    id: 'ensemble',
    name: '集成',
    nameEn: 'Ensemble',
    desc: '同一问题问 N 个模型，投票选优',
    buildNodes: () => [
      { id: 'n0', label: '问题', detail: '', x: 150, y: 300, status: 'idle' },
      { id: 'n1', label: '回答 A', detail: '', x: 450, y: 150, status: 'idle' },
      { id: 'n2', label: '回答 B', detail: '', x: 450, y: 300, status: 'idle' },
      { id: 'n3', label: '回答 C', detail: '', x: 450, y: 450, status: 'idle' },
      { id: 'n4', label: '评判', detail: '', x: 750, y: 300, status: 'idle' },
    ],
    buildEdges: () => [
      { id: 'e1', from: 'n0', to: 'n1', type: 'flow' },
      { id: 'e2', from: 'n0', to: 'n2', type: 'flow' },
      { id: 'e3', from: 'n0', to: 'n3', type: 'flow' },
      { id: 'e4', from: 'n1', to: 'n4', type: 'dependency' },
      { id: 'e5', from: 'n2', to: 'n4', type: 'dependency' },
      { id: 'e6', from: 'n3', to: 'n4', type: 'dependency' },
    ],
  },
]

// ─── Active state ──────────────────────────────────────────────────────

const activePresetId = ref('chain')
const nodes = ref<GraphNodeData[]>([])
const edges = ref<GraphEdgeData[]>([])
const selectedNodeId = ref<string | null>(null)

const activePreset = computed(
  () => presets.find((p) => p.id === activePresetId.value) ?? presets[0],
)

function applyPreset(preset: TopologyPreset) {
  activePresetId.value = preset.id
  nodes.value = preset.buildNodes()
  edges.value = preset.buildEdges()
  selectedNodeId.value = null
}

// Init with default
applyPreset(presets[1]) // chain

// Load user's configured models from settings
async function loadUserModels() {
  try {
    const res = await fetch('/api/settings/models')
    if (res.ok) {
      const data = await res.json()
      // User might have configured multiple model providers
      userConfiguredModels.value = (data.models ?? []).map((m: any) => m.name || m.id)
    }
  } catch {
    // Silently ignore — user can configure in Settings later
  }
}
onMounted(() => {
  loadUserModels()
})

// ─── Node config ───────────────────────────────────────────────────────

const selectedNode = computed(() =>
  nodes.value.find((n) => n.id === selectedNodeId.value) ?? null,
)

// Models are user-configured in Settings. The graph only shows the
// selected model name; the user picks which model to attach per node.
const userConfiguredModels = ref<string[]>([])

function setNodeModel(nodeId: string, modelName: string) {
  const node = nodes.value.find((n) => n.id === nodeId)
  if (node) {
    node.detail = modelName
  }
}

// ─── Graph metrics (graph theory numbers) ──────────────────────────────

const graphMetrics = computed(() => {
  const n = nodes.value.length
  const e = edges.value.length
  // Average degree
  const avgDeg = n > 0 ? ((e * 2) / n).toFixed(1) : '0'
  // Is it a DAG? (no cycles — simplified check)
  const hasCycle = activePresetId.value === 'debate'
  return { n, e, avgDeg, type: hasCycle ? '有环图' : 'DAG' }
})

// ─── Run (real engine) ─────────────────────────────────────────────────

const isRunning = ref(false)
const runResult = ref<{ status: string; steps: any[]; elapsed_ms: number } | null>(null)
const runError = ref<string | null>(null)
const runTaskInput = ref('帮我分析并完成这个任务')

async function simulateRun() {
  if (isRunning.value) return
  isRunning.value = true
  runError.value = null
  runResult.value = null
  for (const n of nodes.value) n.status = 'idle'

  // Mark all nodes as running up-front (the engine runs them concurrently
  // per wave; without per-step streaming we show a collective "running").
  for (const n of nodes.value) n.status = 'running'

  try {
    const res = await fetch(getApiUrl('/api/agents/networks/run-adhoc'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input: runTaskInput.value || '执行任务',
        nodes: nodes.value.map(n => ({ id: n.id, name: n.label, agentId: n.id })),
        edges: edges.value.map(e => ({ from: e.from, to: e.to, label: e.label })),
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    runResult.value = data
    // Light up nodes according to each step's status.
    for (const step of (data.steps || [])) {
      const node = nodes.value.find(n => n.id === step.node_id)
      if (node) node.status = step.status === 'error' ? 'failed' : 'completed'
    }
    // Any node not mentioned by a step defaults to completed.
    for (const n of nodes.value) if (n.status === 'running') n.status = 'completed'
  } catch (e: any) {
    runError.value = e?.message || '执行失败'
    for (const n of nodes.value) if (n.status === 'running') n.status = 'failed'
  } finally {
    isRunning.value = false
  }
}
</script>

<template>
  <div class="flex h-full flex-col bg-[var(--color-surface)]">
    <!-- Header bar: title + graph metrics -->
    <header class="flex items-center justify-between gap-4 border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-6 py-4">
      <div class="min-w-0">
        <div class="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]">协作网络</div>
        <h1 class="text-[18px] font-semibold tracking-tight text-[var(--color-text-primary)]">Agent</h1>
        <p class="mt-0.5 text-[12px] text-[var(--color-text-secondary)]">选择图拓扑 · 配置节点 · 执行协作</p>
      </div>
      <div class="flex flex-wrap items-center gap-2 text-[11px] tabular-nums" style="font-family: var(--font-mono)">
        <span class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[var(--color-text-secondary)]">
          {{ graphMetrics.n }} nodes
        </span>
        <span class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[var(--color-text-secondary)]">
          {{ graphMetrics.e }} edges
        </span>
        <span class="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[var(--color-text-secondary)]">
          deg {{ graphMetrics.avgDeg }}
        </span>
        <span
          class="rounded-lg px-2.5 py-1 font-semibold"
          :class="graphMetrics.type === 'DAG' ? 'bg-[var(--color-success)]/10 text-[var(--color-success)]' : 'bg-[var(--color-warning)]/10 text-[var(--color-warning)]'"
        >
          {{ graphMetrics.type }}
        </span>
      </div>
    </header>

    <!-- Topology selector -->
    <div class="flex items-center gap-1.5 border-b border-[var(--color-border-separator)] px-6 py-2.5">
      <span
        class="mr-2 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-tertiary)]"
        style="font-family: var(--font-mono)"
      >
        拓扑
      </span>
      <button
        v-for="preset in presets"
        :key="preset.id"
        type="button"
        :class="[
          'rounded-xl px-3.5 py-1.5 text-[12px] font-medium transition-all',
          activePresetId === preset.id
            ? 'bg-[var(--color-brand)] text-white shadow-sm'
            : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-container)] hover:text-[var(--color-text-primary)]',
        ]"
        :title="preset.desc"
        @click="applyPreset(preset)"
      >
        {{ preset.name }}
        <span class="ml-1 opacity-60" style="font-family: var(--font-mono); font-size: 10px">{{ preset.nameEn }}</span>
      </button>
    </div>

    <!-- Main content: canvas (left) + config panel (right) -->
    <div class="flex flex-1 min-h-0">
      <!-- Canvas area -->
      <div class="flex-1 relative min-w-0">
        <GraphCanvas
          :nodes="nodes"
          :edges="edges"
          :selected-node-id="selectedNodeId"
          @select-node="(id: string) => (selectedNodeId = id || null)"
        />
        <!-- Preset description overlay (bottom-left) -->
        <div class="pointer-events-none absolute bottom-4 left-4 max-w-xs">
          <div class="text-[12px] font-medium text-[var(--color-text-secondary)]">
            {{ activePreset.name }} · {{ activePreset.nameEn }}
          </div>
          <div class="mt-0.5 text-[11px] text-[var(--color-text-tertiary)]">
            {{ activePreset.desc }}
          </div>
        </div>
      </div>

      <!-- Node config panel (right) -->
      <aside
        v-if="selectedNode"
        class="w-[300px] flex-shrink-0 overflow-y-auto border-l border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-4"
      >
        <div class="mb-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-3">
          <div
            class="text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text-tertiary)]"
            style="font-family: var(--font-mono)"
          >
            节点配置
          </div>
          <div class="mt-1.5 text-[16px] font-semibold text-[var(--color-text-primary)]">
            {{ selectedNode.label }}
          </div>
        </div>

        <div class="mb-5">
          <label class="mb-2 block text-[11px] font-medium text-[var(--color-text-secondary)]">模型（来自设置）</label>
          <div class="space-y-1.5">
            <button
              v-for="modelName in userConfiguredModels"
              :key="modelName"
              type="button"
              :class="[
                'flex w-full items-center rounded-xl border px-3 py-2.5 text-left transition-colors',
                (selectedNode.detail || '') === modelName
                  ? 'border-[var(--color-brand)] bg-[var(--color-brand)]/5 shadow-sm'
                  : 'border-[var(--color-border)] bg-[var(--color-surface)] hover:border-[var(--color-border-focus)]',
              ]"
              @click="setNodeModel(selectedNode.id, modelName)"
            >
              <span class="text-[12px] font-medium text-[var(--color-text-primary)]">{{ modelName }}</span>
            </button>
            <div
              v-if="userConfiguredModels.length === 0"
              class="rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-center"
            >
              <div class="text-[12px] font-medium text-[var(--color-text-secondary)]">尚未配置模型</div>
              <div class="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
                请在设置 → 模型供应商中添加
              </div>
            </div>
          </div>
        </div>

        <div
          class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-[10px] text-[var(--color-text-tertiary)]"
          style="font-family: var(--font-mono)"
        >
          <div class="flex justify-between py-1">
            <span>id</span>
            <span class="text-[var(--color-text-secondary)]">{{ selectedNode.id }}</span>
          </div>
          <div class="flex justify-between py-1">
            <span>status</span>
            <span class="text-[var(--color-text-secondary)]">{{ selectedNode.status || 'idle' }}</span>
          </div>
          <div class="flex justify-between py-1">
            <span>pos</span>
            <span class="text-[var(--color-text-secondary)]">{{ Math.round(selectedNode.x) }}, {{ Math.round(selectedNode.y) }}</span>
          </div>
        </div>
      </aside>

      <aside
        v-else
        class="w-[300px] flex-shrink-0 border-l border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-4"
      >
        <div class="flex h-full flex-col items-center justify-center rounded-xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)]/50 text-center">
          <span class="material-symbols-outlined mb-2 text-[28px] text-[var(--color-text-tertiary)] opacity-50">touch_app</span>
          <div class="text-[12px] text-[var(--color-text-secondary)]">点击图中的节点进行配置</div>
          <div
            class="mt-2 text-[10px] uppercase tracking-[0.14em] text-[var(--color-text-tertiary)] opacity-50"
            style="font-family: var(--font-mono)"
          >
            select a node
          </div>
        </div>
      </aside>
    </div>

    <!-- Bottom bar -->
    <footer class="border-t border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-6 py-3.5">
      <div class="flex items-center gap-3">
        <input
          v-model="runTaskInput"
          :disabled="isRunning"
          placeholder="输入要让 agent 协作完成的任务…"
          class="flex-1 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 py-2.5 text-[13px] text-[var(--color-text-primary)] outline-none transition-colors focus:border-[var(--color-brand)]"
          @keydown.enter="simulateRun"
        />
        <button
          type="button"
          :disabled="isRunning"
          :class="[
            'inline-flex items-center gap-1.5 rounded-xl px-5 py-2.5 text-[13px] font-semibold transition-all',
            isRunning
              ? 'cursor-not-allowed bg-[var(--color-surface-container)] text-[var(--color-text-tertiary)]'
              : 'bg-[var(--color-brand)] text-white shadow-sm hover:opacity-90',
          ]"
          @click="simulateRun"
        >
          <span class="material-symbols-outlined text-[16px]">{{ isRunning ? 'progress_activity' : 'play_arrow' }}</span>
          {{ isRunning ? '执行中…' : '执行协作' }}
        </button>
      </div>

      <!-- Run result -->
      <div v-if="runResult" class="mt-3 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] p-3">
        <div class="mb-2 flex items-center gap-3 text-[11px] text-[var(--color-text-tertiary)]">
          <span class="font-semibold uppercase tracking-wider">{{ runResult.status }}</span>
          <span>{{ runResult.elapsed_ms }}ms</span>
          <span>{{ (runResult.steps || []).length }} 步</span>
        </div>
        <div class="flex flex-col gap-2">
          <div
            v-for="step in (runResult.steps || []).filter((s: any) => s.node_id !== 'input' && s.node_id !== 'output')"
            :key="step.node_id"
            class="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-2"
          >
            <div class="mb-1 flex items-center gap-2 text-[12px]">
              <span class="font-semibold text-[var(--color-text-primary)]">{{ step.agent_name || step.node_id }}</span>
              <span :style="{ color: step.status === 'error' ? 'var(--color-error)' : 'var(--color-success)' }" class="text-[10px] uppercase">{{ step.status }}</span>
            </div>
            <pre class="max-h-[120px] overflow-auto whitespace-pre-wrap break-words font-[var(--font-mono)] text-[11px] text-[var(--color-text-secondary)]">{{ (step.output || '').slice(0, 400) }}</pre>
          </div>
        </div>
      </div>

      <!-- Run error -->
      <div v-if="runError" class="mt-3 rounded-[var(--radius-md)] bg-[color-mix(in_srgb,var(--color-error)_10%,transparent)] p-3 text-[12px] text-[var(--color-error)]">
        执行失败：{{ runError }}
      </div>
    </footer>
  </div>
</template>
