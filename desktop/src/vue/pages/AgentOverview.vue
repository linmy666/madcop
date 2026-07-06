<script setup lang="ts">
/**
 * AgentOverview — the "🤖 Agent" main page.
 *
 * Replaces: AgentHub.vue + AgentNetwork.vue + Arena (concept) into one cohesive page.
 * Layout:
 *   Top: 8 graph-theory topology presets (single → chain → parallel → debate → ensemble…)
 *   Center: GraphCanvas (SVG, drag nodes, select to configure)
 *   Right: Node config panel (model, role, tools)
 *   Bottom: Run / Save / Stats
 *
 * All pure text, zero icons. Graph-theory aesthetic.
 */

import { ref, computed } from 'vue'
import GraphCanvas, { type GraphNodeData, type GraphEdgeData } from '../components/graph/GraphCanvas.vue'
import { useTabStore } from '../stores/tabs'

const tabStore = useTabStore()

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
      { id: 'n1', label: 'Agent', detail: 'GLM-5.2', x: 500, y: 300, status: 'idle' },
    ],
    buildEdges: () => [],
  },
  {
    id: 'chain',
    name: '链式',
    nameEn: 'Chain',
    desc: '顺序传递: 规划 → 执行 → 审查',
    buildNodes: () => [
      { id: 'n1', label: '规划', detail: 'GLM-5.2', x: 200, y: 300, status: 'idle' },
      { id: 'n2', label: '执行', detail: 'Qwen3', x: 500, y: 300, status: 'idle' },
      { id: 'n3', label: '审查', detail: 'DeepSeek', x: 800, y: 300, status: 'idle' },
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
      { id: 'n0', label: '分发', detail: 'Router', x: 200, y: 300, status: 'idle' },
      { id: 'n1', label: '前端', detail: 'GLM-5.2', x: 500, y: 150, status: 'idle' },
      { id: 'n2', label: '后端', detail: 'Qwen3', x: 500, y: 300, status: 'idle' },
      { id: 'n3', label: '测试', detail: 'DeepSeek', x: 500, y: 450, status: 'idle' },
      { id: 'n4', label: '聚合', detail: 'GLM-5.2', x: 800, y: 300, status: 'idle' },
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
      { id: 'n1', label: '提议者', detail: 'GLM-5.2', x: 300, y: 200, status: 'idle' },
      { id: 'n2', label: '批判者', detail: 'Qwen3', x: 300, y: 400, status: 'idle' },
      { id: 'n3', label: '评判者', detail: 'DeepSeek', x: 700, y: 300, status: 'idle' },
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
      { id: 'n0', label: '问题', detail: 'input', x: 150, y: 300, status: 'idle' },
      { id: 'n1', label: 'GLM-5.2', detail: '', x: 450, y: 150, status: 'idle' },
      { id: 'n2', label: 'Qwen3', detail: '', x: 450, y: 300, status: 'idle' },
      { id: 'n3', label: 'DeepSeek', detail: '', x: 450, y: 450, status: 'idle' },
      { id: 'n4', label: '评判', detail: 'judge', x: 750, y: 300, status: 'idle' },
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
    id: 'loop',
    name: '环',
    nameEn: 'Loop',
    desc: '迭代优化: 执行 → 评估 → 修正 → 再执行',
    buildNodes: () => [
      { id: 'n1', label: '执行', detail: 'GLM-5.2', x: 250, y: 200, status: 'idle' },
      { id: 'n2', label: '评估', detail: 'Qwen3', x: 650, y: 200, status: 'idle' },
      { id: 'n3', label: '修正', detail: 'DeepSeek', x: 450, y: 450, status: 'idle' },
    ],
    buildEdges: () => [
      { id: 'e1', from: 'n1', to: 'n2', type: 'dependency' },
      { id: 'e2', from: 'n2', to: 'n3', type: 'control', label: '不通过' },
      { id: 'e3', from: 'n3', to: 'n1', type: 'flow', label: '修正后' },
    ],
  },
  {
    id: 'hierarchical',
    name: '层级',
    nameEn: 'Hierarchical',
    desc: '协调者分配子任务给执行者',
    buildNodes: () => [
      { id: 'n0', label: '协调者', detail: 'GLM-5.2', x: 500, y: 120, status: 'idle' },
      { id: 'n1', label: '执行 A', detail: 'Qwen3', x: 250, y: 350, status: 'idle' },
      { id: 'n2', label: '执行 B', detail: 'DeepSeek', x: 500, y: 350, status: 'idle' },
      { id: 'n3', label: '执行 C', detail: 'GLM-5.2', x: 750, y: 350, status: 'idle' },
    ],
    buildEdges: () => [
      { id: 'e1', from: 'n0', to: 'n1', type: 'control', label: '分配' },
      { id: 'e2', from: 'n0', to: 'n2', type: 'control', label: '分配' },
      { id: 'e3', from: 'n0', to: 'n3', type: 'control', label: '分配' },
      { id: 'e4', from: 'n1', to: 'n0', type: 'dependency', label: '汇报' },
      { id: 'e5', from: 'n2', to: 'n0', type: 'dependency', label: '汇报' },
      { id: 'e6', from: 'n3', to: 'n0', type: 'dependency', label: '汇报' },
    ],
  },
  {
    id: 'blackboard',
    name: '黑板',
    nameEn: 'Blackboard',
    desc: '多专家共享上下文，独立读写',
    buildNodes: () => [
      { id: 'n0', label: '黑板', detail: 'shared', x: 500, y: 300, status: 'idle' },
      { id: 'n1', label: '专家 A', detail: 'GLM-5.2', x: 200, y: 150, status: 'idle' },
      { id: 'n2', label: '专家 B', detail: 'Qwen3', x: 800, y: 150, status: 'idle' },
      { id: 'n3', label: '专家 C', detail: 'DeepSeek', x: 200, y: 450, status: 'idle' },
      { id: 'n4', label: '专家 D', detail: 'GLM-5.2', x: 800, y: 450, status: 'idle' },
    ],
    buildEdges: () => [
      { id: 'e1', from: 'n1', to: 'n0', type: 'flow', label: '读写' },
      { id: 'e2', from: 'n2', to: 'n0', type: 'flow', label: '读写' },
      { id: 'e3', from: 'n3', to: 'n0', type: 'flow', label: '读写' },
      { id: 'e4', from: 'n4', to: 'n0', type: 'flow', label: '读写' },
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

// ─── Node config ───────────────────────────────────────────────────────

const selectedNode = computed(() =>
  nodes.value.find((n) => n.id === selectedNodeId.value) ?? null,
)

const availableModels = [
  { id: 'glm52', name: 'GLM-5.2', desc: '强推理 · 工具调用稳定' },
  { id: 'qwen3', name: 'Qwen3-80B', desc: '快 · 代码强' },
  { id: 'deepseek', name: 'DeepSeek-V3', desc: '均衡 · 长上下文' },
]

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
  const hasCycle = activePresetId.value === 'loop' || activePresetId.value === 'debate'
  return { n, e, avgDeg, type: hasCycle ? '有环图' : 'DAG' }
})

// ─── Run simulation ────────────────────────────────────────────────────

const isRunning = ref(false)

async function simulateRun() {
  if (isRunning.value) return
  isRunning.value = true
  // Reset all to idle
  for (const n of nodes.value) n.status = 'idle'
  // Sequentially activate each node with delay
  for (const n of nodes.value) {
    n.status = 'running'
    await sleep(800)
    n.status = 'completed'
  }
  isRunning.value = false
}

function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}
</script>

<template>
  <div class="flex h-full flex-col bg-[var(--color-surface)]">
    <!-- Header bar: title + graph metrics in monospace -->
    <header class="flex items-center justify-between border-b border-[var(--color-border)] px-6 py-4">
      <div>
        <h1 class="text-[18px] font-semibold tracking-tight text-[var(--color-text-primary)]">Agent</h1>
        <p class="mt-0.5 text-[11px] text-[var(--color-text-tertiary)]">选择图拓扑 · 配置节点 · 执行协作</p>
      </div>
      <!-- Graph theory metrics, engineer style -->
      <div
        class="flex items-center gap-5 text-[11px] tabular-nums text-[var(--color-text-tertiary)]"
        style="font-family: ui-monospace, 'SF Mono', monospace"
      >
        <span>{{ graphMetrics.n }} nodes</span>
        <span>{{ graphMetrics.e }} edges</span>
        <span>deg {{ graphMetrics.avgDeg }}</span>
        <span
          class="rounded px-1.5 py-0.5"
          :class="graphMetrics.type === 'DAG' ? 'bg-[var(--color-success)]/10 text-[var(--color-success)]' : 'bg-[var(--color-warning)]/10 text-[var(--color-warning)]'"
        >
          {{ graphMetrics.type }}
        </span>
      </div>
    </header>

    <!-- Topology selector — horizontal text chips, no icons -->
    <div class="flex items-center gap-1 border-b border-[var(--color-border-separator)] px-6 py-2.5">
      <span
        class="mr-3 text-[10px] uppercase tracking-[0.14em] text-[var(--color-text-tertiary)]"
        style="font-family: ui-monospace, 'SF Mono', monospace"
      >
        拓扑
      </span>
      <button
        v-for="preset in presets"
        :key="preset.id"
        type="button"
        :class="[
          'rounded-md px-3 py-1.5 text-[12px] font-medium transition-colors',
          activePresetId === preset.id
            ? 'bg-[var(--color-brand)] text-white'
            : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-container)] hover:text-[var(--color-text-primary)]',
        ]"
        @click="applyPreset(preset)"
      >
        {{ preset.name }}
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
        class="w-[280px] flex-shrink-0 border-l border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-4 overflow-y-auto"
      >
        <div class="mb-4">
          <div
            class="text-[10px] uppercase tracking-[0.14em] text-[var(--color-text-tertiary)]"
            style="font-family: ui-monospace, 'SF Mono', monospace"
          >
            节点配置
          </div>
          <div class="mt-1 text-[16px] font-semibold text-[var(--color-text-primary)]">
            {{ selectedNode.label }}
          </div>
        </div>

        <!-- Model selector -->
        <div class="mb-5">
          <label class="mb-2 block text-[11px] font-medium text-[var(--color-text-secondary)]">模型</label>
          <div class="space-y-1">
            <button
              v-for="model in availableModels"
              :key="model.id"
              type="button"
              :class="[
                'flex w-full items-center justify-between rounded-lg border px-3 py-2 text-left transition-colors',
                (selectedNode.detail || '') === model.name
                  ? 'border-[var(--color-brand)] bg-[var(--color-brand)]/5'
                  : 'border-[var(--color-border)] hover:border-[var(--color-border-focus)]',
              ]"
              @click="setNodeModel(selectedNode.id, model.name)"
            >
              <span class="text-[12px] font-medium text-[var(--color-text-primary)]">{{ model.name }}</span>
              <span class="text-[10px] text-[var(--color-text-tertiary)]">{{ model.desc }}</span>
            </button>
          </div>
        </div>

        <!-- Node info in monospace -->
        <div
          class="rounded-lg bg-[var(--color-surface)] p-3 text-[10px] text-[var(--color-text-tertiary)]"
          style="font-family: ui-monospace, 'SF Mono', monospace"
        >
          <div class="flex justify-between py-0.5">
            <span>id</span>
            <span>{{ selectedNode.id }}</span>
          </div>
          <div class="flex justify-between py-0.5">
            <span>status</span>
            <span>{{ selectedNode.status || 'idle' }}</span>
          </div>
          <div class="flex justify-between py-0.5">
            <span>pos</span>
            <span>{{ Math.round(selectedNode.x) }}, {{ Math.round(selectedNode.y) }}</span>
          </div>
        </div>
      </aside>

      <!-- Empty hint when no node selected -->
      <aside
        v-else
        class="w-[280px] flex-shrink-0 border-l border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-4"
      >
        <div class="flex h-full flex-col items-center justify-center text-center">
          <div class="text-[12px] text-[var(--color-text-tertiary)]">点击图中的节点进行配置</div>
          <div
            class="mt-2 text-[10px] uppercase tracking-[0.14em] text-[var(--color-text-tertiary)] opacity-50"
            style="font-family: ui-monospace, 'SF Mono', monospace"
          >
            select a node ○
          </div>
        </div>
      </aside>
    </div>

    <!-- Bottom bar: run button + stats -->
    <footer class="flex items-center justify-between border-t border-[var(--color-border)] px-6 py-3">
      <div class="flex items-center gap-4 text-[11px] text-[var(--color-text-tertiary)]">
        <span>预估 Token: <span class="tabular-nums" style="font-family: ui-monospace, monospace">~{{ nodes.length * 2000 }}</span></span>
      </div>
      <button
        type="button"
        :disabled="isRunning"
        :class="[
          'rounded-lg px-6 py-2 text-[13px] font-medium transition-all',
          isRunning
            ? 'cursor-not-allowed bg-[var(--color-surface-container)] text-[var(--color-text-tertiary)]'
            : 'bg-[var(--color-brand)] text-white hover:opacity-90',
        ]"
        @click="simulateRun"
      >
        {{ isRunning ? '执行中…' : '执行协作' }}
      </button>
    </footer>
  </div>
</template>
