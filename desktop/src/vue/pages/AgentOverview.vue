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
  <div class="ao-page">
    <!-- Header -->
    <header class="ao-page__head">
      <div>
        <h1 class="ao-page__title">Agent 协作拓扑</h1>
        <p class="ao-page__sub">选择一个预设模板开始，或直接拖拽节点自定义网络</p>
      </div>
      <div class="ao-page__actions">
        <button class="ao-btn" @click="saveAsNew" :disabled="!canSave">
          <span class="material-symbols-outlined" style="font-size:18px">bookmark</span>
          另存为网络
        </button>
        <button class="ao-btn ao-btn--primary" @click="runNetwork" :disabled="!canRun || running">
          <span class="material-symbols-outlined" style="font-size:18px">{{ running ? 'hourglass_top' : 'play_arrow' }}</span>
          {{ running ? '运行中…' : '运行网络' }}
        </button>
      </div>
    </header>

    <!-- Topology preset picker -->
    <section class="ao-presets">
      <header class="ao-section__head">
        <h2 class="ao-section__title">预设拓扑</h2>
        <p class="ao-section__sub">点击下方任一模板，会替换当前画布</p>
      </header>
      <div class="ao-presets-grid">
        <button
          v-for="p in presets"
          :key="p.id"
          :class="['ao-preset', { 'ao-preset--active': selectedPreset === p.id }]"
          @click="applyPreset(p)"
        >
          <div class="ao-preset__head">
            <span class="ao-preset__name">{{ p.name }}</span>
            <span class="ao-preset__nameEn">{{ p.nameEn }}</span>
          </div>
          <p class="ao-preset__desc">{{ p.desc }}</p>
          <div class="ao-preset__viz">
            <svg
              v-for="(n, i) in p.buildNodes().slice(0, 4)"
              :key="`${p.id}-n-${i}`"
              :class="`ao-preset__node ao-preset__node--${i}`"
            >
              <span class="material-symbols-outlined">circle</span>
            </svg>
            <span
              v-for="i in Math.min(p.buildNodes().length - 1, 3)"
              :key="`${p.id}-a-${i}`"
              class="ao-preset__arrow"
            >→</span>
          </div>
        </button>
      </div>
    </section>

    <!-- Graph canvas + side panel -->
    <section class="ao-workspace">
      <div class="ao-canvas-wrap">
        <header class="ao-canvas-head">
          <h3 class="ao-canvas__title">网络画布</h3>
          <span v-if="runResult" class="ao-canvas__status ao-canvas__status--ok">运行完成 · {{ runResult.elapsed_ms }}ms</span>
          <span v-else-if="runError" class="ao-canvas__status ao-canvas__status--err">运行失败：{{ runError }}</span>
        </header>
        <div class="ao-canvas">
          <GraphCanvas
            :nodes="nodes"
            :edges="edges"
            :selected-id="selectedNodeId"
            @select="onSelect"
            @update:nodes="onUpdateNodes"
            @update:edges="onUpdateEdges"
          />
        </div>
      </div>

      <aside class="ao-side">
        <header class="ao-side__head">
          <h3 class="ao-side__title">{{ selectedNode ? '节点配置' : '网络统计' }}</h3>
        </header>

        <div v-if="selectedNode" class="ao-node-form">
          <label class="ao-field">
            <span class="ao-field__label">名称</span>
            <input v-model="selectedNode.label" class="ao-input" />
          </label>
          <label class="ao-field">
            <span class="ao-field__label">角色</span>
            <select v-model="selectedNode.role" class="ao-input">
              <option v-for="r in availableRoles" :key="r" :value="r">{{ r }}</option>
            </select>
          </label>
          <label class="ao-field">
            <span class="ao-field__label">模型</span>
            <select v-model="selectedNode.model" class="ao-input">
              <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
            </select>
          </label>
          <label class="ao-field">
            <span class="ao-field__label">系统提示</span>
            <textarea
              v-model="selectedNode.systemPrompt"
              class="ao-input ao-textarea"
              placeholder="（可选）给该 Agent 的角色/约束描述"
              rows="4"
            />
          </label>
          <label class="ao-field">
            <span class="ao-field__label">可用工具</span>
            <div class="ao-tools">
              <label v-for="t in availableTools" :key="t" class="ao-tool-chip">
                <input type="checkbox" :value="t" v-model="selectedNode.tools" />
                <span>{{ t }}</span>
              </label>
            </div>
          </label>
        </div>

        <div v-else class="ao-stats">
          <div class="ao-stat">
            <div class="ao-stat__num">{{ nodes.length }}</div>
            <div class="ao-stat__label">节点</div>
          </div>
          <div class="ao-stat">
            <div class="ao-stat__num">{{ edges.length }}</div>
            <div class="ao-stat__label">连接</div>
          </div>
          <div class="ao-stat">
            <div class="ao-stat__num">{{ uniqueRoles.length }}</div>
            <div class="ao-stat__label">不同角色</div>
          </div>
          <p class="ao-stat__hint">选中画布上的节点以配置该 Agent</p>
        </div>
      </aside>
    </section>
  </div>
</template>

<style scoped>
/* ── Page layout ─────────────────────────────────────────────────── */
.ao-page { width: 100%; height: 100%; overflow-y: auto; background: var(--color-surface); }
.ao-page__head {
  max-width: 1280px;
  margin: 0 auto;
  padding: 48px 32px 24px;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}
.ao-page__title {
  font-size: 28px;
  font-weight: 600;
  margin: 0 0 4px;
  letter-spacing: -0.01em;
}
.ao-page__sub { margin: 0; font-size: 14px; color: var(--color-text-secondary); }
.ao-page__actions { display: flex; gap: 8px; flex-shrink: 0; }

/* ── Buttons ────────────────────────────────────────────────────── */
.ao-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-primary);
  cursor: pointer;
  font-family: inherit;
  transition: background 120ms, border-color 120ms;
}
.ao-btn:hover:not(:disabled) { background: var(--color-surface-container-low); }
.ao-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.ao-btn--primary {
  background: var(--color-brand, #0a0a0a);
  color: #fff;
  border-color: var(--color-brand, #0a0a0a);
}
.ao-btn--primary:hover:not(:disabled) { background: #1f2937; border-color: #1f2937; }

/* ── Section heading ────────────────────────────────────────────── */
.ao-section__head { margin-bottom: 16px; }
.ao-section__title {
  font-size: 14px;
  font-weight: 600;
  margin: 0 0 4px;
  color: var(--color-text-primary);
}
.ao-section__sub { margin: 0; font-size: 12px; color: var(--color-text-secondary); }

/* ── Preset grid ───────────────────────────────────────────────── */
.ao-presets {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 32px 32px;
}
.ao-presets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}
.ao-preset {
  text-align: left;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px;
  cursor: pointer;
  font-family: inherit;
  color: var(--color-text-primary);
  transition: border-color 140ms, transform 140ms;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.ao-preset:hover { border-color: var(--color-text-tertiary); transform: translateY(-1px); }
.ao-preset--active {
  border-color: var(--color-brand, #0a0a0a);
  background: var(--color-surface-container-lowest);
}
.ao-preset__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.ao-preset__name { font-size: 14px; font-weight: 600; }
.ao-preset__nameEn {
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.ao-preset__desc {
  margin: 0;
  font-size: 12px;
  color: var(--color-text-secondary);
  line-height: 1.5;
  min-height: 36px;
}
.ao-preset__viz {
  display: flex;
  align-items: center;
  gap: 2px;
  flex-wrap: wrap;
  min-height: 16px;
  color: var(--color-text-tertiary);
}
.ao-preset__node { font-size: 10px !important; color: var(--color-text-tertiary); }
.ao-preset__arrow { font-size: 10px; opacity: 0.5; }

/* ── Workspace (canvas + side panel) ──────────────────────────── */
.ao-workspace {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 32px 48px;
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  align-items: start;
}

.ao-canvas-wrap {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  overflow: hidden;
}
.ao-canvas-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
}
.ao-canvas__title { font-size: 14px; font-weight: 600; margin: 0; }
.ao-canvas__status {
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
}
.ao-canvas__status--ok { background: #dcfce7; color: #166534; }
.ao-canvas__status--err { background: #fee2e2; color: #b91c1c; }
.ao-canvas { height: 480px; background: var(--color-surface-container-lowest); }

/* ── Side panel ────────────────────────────────────────────────── */
.ao-side {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 16px;
  min-height: 480px;
}
.ao-side__head { margin-bottom: 16px; padding-bottom: 12px; border-bottom: 1px solid var(--color-border); }
.ao-side__title { font-size: 14px; font-weight: 600; margin: 0; }

/* ── Node form ─────────────────────────────────────────────────── */
.ao-node-form { display: flex; flex-direction: column; gap: 14px; }
.ao-field { display: flex; flex-direction: column; gap: 6px; }
.ao-field__label { font-size: 11px; font-weight: 500; color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: 0.04em; }
.ao-input {
  padding: 7px 10px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--color-surface);
  font-size: 13px;
  color: var(--color-text-primary);
  font-family: inherit;
  outline: none;
  transition: border-color 120ms;
}
.ao-input:focus { border-color: var(--color-text-tertiary); }
.ao-textarea { resize: vertical; min-height: 64px; line-height: 1.5; }
.ao-tools { display: flex; flex-wrap: wrap; gap: 6px; }
.ao-tool-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: var(--color-surface-container);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 12px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background 120ms, color 120ms;
}
.ao-tool-chip:has(input:checked) { background: var(--color-text-primary); color: var(--color-surface); border-color: var(--color-text-primary); }
.ao-tool-chip input { margin: 0; }

/* ── Stats panel (when no node selected) ─────────────────────── */
.ao-stats { display: flex; flex-direction: column; gap: 12px; }
.ao-stat {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  padding: 12px;
  background: var(--color-surface-container-lowest);
  border-radius: 6px;
}
.ao-stat__num { font-size: 24px; font-weight: 600; line-height: 1.2; }
.ao-stat__label { font-size: 11px; color: var(--color-text-secondary); margin-top: 2px; }
.ao-stat__hint {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin: 8px 0 0;
  line-height: 1.5;
}

/* ── Responsive (tablet) ───────────────────────────────────────── */
@media (max-width: 960px) {
  .ao-workspace { grid-template-columns: 1fr; }
  .ao-page__head { flex-direction: column; align-items: stretch; }
}
</style>
