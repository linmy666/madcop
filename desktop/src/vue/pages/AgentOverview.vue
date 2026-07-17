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
import SpriteStudioScene from '../components/studio/SpriteStudioScene.vue'
import TopologyMiniGraph from '../components/studio/TopologyMiniGraph.vue'
import { getApiUrl } from '../api/client'
import { providersApi } from '../api/providers'
import { useChatStore } from '../stores/chatStore'
import { useTabStore } from '../stores/tabs'
import {
  buildSpriteRoster,
  loadAgentHubView,
  saveAgentHubView,
  type SpriteAgent,
} from '../lib/spriteStudio'
import { buildRunAdhocPayload, applyStepStatuses } from '../lib/topologyPayload'
import { sanitizeAgentDisplayText } from '../lib/agentDisplayText'

function mkNode(
  partial: GraphNodeData & { agentId?: string },
): GraphNodeData {
  return {
    status: 'idle',
    tools: [],
    systemPrompt: '',
    model: '',
    role: partial.agentId || partial.role || partial.id,
    agentId: partial.agentId || partial.role || partial.id,
    detail: '',
    ...partial,
  }
}

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
      mkNode({
        id: 'n1',
        label: '助手',
        agentId: 'assistant',
        x: 500,
        y: 300,
        systemPrompt: '你是 MadCop 正义助手，清晰、可靠地完成用户任务。',
      }),
    ],
    buildEdges: () => [],
  },
  {
    id: 'chain',
    name: '链式',
    nameEn: 'Chain',
    desc: '顺序传递: 规划 → 写码 → 审查',
    buildNodes: () => [
      mkNode({
        id: 'n1',
        label: '规划',
        agentId: 'planner',
        x: 200,
        y: 300,
        systemPrompt: '你是规划专家，拆解任务为可执行步骤。',
      }),
      mkNode({
        id: 'n2',
        label: '写码',
        agentId: 'coder',
        x: 500,
        y: 300,
        systemPrompt: '你是工程师，根据规划输出实现方案或代码。',
        tools: ['read_file', 'write_file'],
      }),
      mkNode({
        id: 'n3',
        label: '审查',
        agentId: 'reviewer',
        x: 800,
        y: 300,
        systemPrompt: '你是审查员，挑错并给出改进建议。',
      }),
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
      mkNode({ id: 'n0', label: '分发', agentId: 'planner', x: 200, y: 300 }),
      mkNode({ id: 'n1', label: '前端', agentId: 'designer', x: 500, y: 150 }),
      mkNode({ id: 'n2', label: '后端', agentId: 'coder', x: 500, y: 300 }),
      mkNode({ id: 'n3', label: '测试', agentId: 'reviewer', x: 500, y: 450 }),
      mkNode({ id: 'n4', label: '聚合', agentId: 'synthesizer', x: 800, y: 300 }),
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
      mkNode({ id: 'n1', label: '提议者', agentId: 'planner', x: 300, y: 200 }),
      mkNode({ id: 'n2', label: '批判者', agentId: 'reviewer', x: 300, y: 400 }),
      mkNode({ id: 'n3', label: '评判者', agentId: 'synthesizer', x: 700, y: 300 }),
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
      mkNode({ id: 'n0', label: '问题', agentId: 'input', x: 150, y: 300 }),
      mkNode({ id: 'n1', label: '回答 A', agentId: 'assistant', x: 450, y: 150 }),
      mkNode({ id: 'n2', label: '回答 B', agentId: 'coder', x: 450, y: 300 }),
      mkNode({ id: 'n3', label: '回答 C', agentId: 'researcher', x: 450, y: 450 }),
      mkNode({ id: 'n4', label: '评判', agentId: 'synthesizer', x: 750, y: 300 }),
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

/** Hub views: classic topology editor vs P1 sprite studio */
const hubView = ref<'topology' | 'studio'>(loadAgentHubView())
function setHubView(v: 'topology' | 'studio') {
  hubView.value = v
  saveAgentHubView(v)
}

const chatStore = useChatStore()
const tabStore = useTabStore()
const liveSessionId = computed(() => {
  // Prefer active chat session for live multi-agent roster
  const id = tabStore.activeTabId
  if (id && chatStore.sessions[id]) return id
  // Fall back to any session with agentStreams / deepRoute
  for (const [sid, s] of Object.entries(chatStore.sessions)) {
    if (s?.agentStreams && Object.keys(s.agentStreams).length) return sid
    if (s?.deepRoute?.specialists?.length) return sid
  }
  return id || null
})
const liveSession = computed(() =>
  liveSessionId.value ? chatStore.sessions[liveSessionId.value] : null,
)
const studioRoster = computed<SpriteAgent[]>(() =>
  buildSpriteRoster({
    agentStreams: liveSession.value?.agentStreams,
    deepRoute: liveSession.value?.deepRoute,
    clarificationPending: liveSession.value?.clarificationPending,
    activeToolName: liveSession.value?.activeToolName,
    chatState: liveSession.value?.chatState,
    assignedSpriteId: null, // assignment is local inside SpriteStudioScene
  }),
)
const studioRouteLabel = computed(
  () => liveSession.value?.deepRoute?.label_zh || liveSession.value?.deepRoute?.category || null,
)
const studioRouteReason = computed(() => liveSession.value?.deepRoute?.reason || null)

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

// Load models from active providers (real settings path)
async function loadUserModels() {
  try {
    const list = await providersApi.list()
    const names: string[] = []
    const providers = (list as any)?.providers || []
    for (const p of providers as any[]) {
      const models = p.models || p.model_ids || []
      if (Array.isArray(models)) {
        for (const m of models) names.push(typeof m === 'string' ? m : m.id || m.name)
      }
      if (p.model) names.push(String(p.model))
      if (p.defaultModel) names.push(String(p.defaultModel))
    }
    userConfiguredModels.value = [...new Set(names.filter(Boolean))]
  } catch {
    userConfiguredModels.value = []
  }
}

async function loadSavedNetworks() {
  try {
    const res = await fetch(getApiUrl('/api/agents/networks'))
    if (res.ok) savedNetworks.value = await res.json()
  } catch {
    savedNetworks.value = []
  }
}

onMounted(() => {
  loadUserModels()
  loadSavedNetworks()
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
const runResult = ref<{ status: string; steps: any[]; elapsed_ms: number; outputs?: Record<string, string> } | null>(null)
const runError = ref<string | null>(null)
const runTaskInput = ref('帮我分析并完成这个任务')
const saveMsg = ref<string | null>(null)
const savedNetworks = ref<any[]>([])

async function runNetwork() {
  if (isRunning.value || nodes.value.length === 0) return
  isRunning.value = true
  runError.value = null
  runResult.value = null
  for (const n of nodes.value) n.status = 'running'

  const body = buildRunAdhocPayload(
    runTaskInput.value,
    nodes.value,
    edges.value,
    activePreset.value?.name || 'Ad-hoc',
  )

  try {
    const res = await fetch(getApiUrl('/api/agents/networks/run-adhoc'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      const t = await res.text().catch(() => '')
      throw new Error(sanitizeAgentDisplayText(t || `HTTP ${res.status}`, 120))
    }
    const data = await res.json()
    runResult.value = data
    nodes.value = applyStepStatuses(nodes.value, data.steps || []) as GraphNodeData[]
  } catch (e: any) {
    runError.value = sanitizeAgentDisplayText(e?.message || '执行失败', 160)
    for (const n of nodes.value) {
      if (n.status === 'running') n.status = 'failed'
    }
  } finally {
    isRunning.value = false
  }
}

const running = isRunning
const canRun = computed(() => nodes.value.length > 0 && !isRunning.value)
const canSave = computed(() => nodes.value.length > 0)
const selectedPreset = activePresetId
const models = userConfiguredModels
const availableRoles = [
  { id: 'planner', label: '规划' },
  { id: 'coder', label: '写码' },
  { id: 'designer', label: '设计' },
  { id: 'researcher', label: '调研' },
  { id: 'reviewer', label: '审查' },
  { id: 'synthesizer', label: '合成' },
  { id: 'assistant', label: '助手' },
]
const availableTools = ['read_file', 'write_file', 'web_search', 'web_fetch', 'edit_file']
const uniqueRoles = computed(() => {
  const set = new Set(nodes.value.map((n) => n.agentId || n.role || n.label).filter(Boolean))
  return [...set]
})

function onSelect(id: string | null) {
  selectedNodeId.value = id || null
}

function onNodePosition(id: string, x: number, y: number) {
  const n = nodes.value.find((node) => node.id === id)
  if (n) {
    n.x = x
    n.y = y
  }
}

function onRoleChange(roleId: string) {
  if (!selectedNode.value) return
  selectedNode.value.agentId = roleId
  selectedNode.value.role = roleId
  const meta = availableRoles.find((r) => r.id === roleId)
  if (meta && (!selectedNode.value.label || selectedNode.value.label === selectedNode.value.id)) {
    selectedNode.value.label = meta.label
  }
}

function toggleTool(tool: string, on: boolean) {
  if (!selectedNode.value) return
  const tools = [...(selectedNode.value.tools || [])]
  const i = tools.indexOf(tool)
  if (on && i < 0) tools.push(tool)
  if (!on && i >= 0) tools.splice(i, 1)
  selectedNode.value.tools = tools
}

async function saveAsNew() {
  saveMsg.value = null
  if (!nodes.value.length) return
  try {
    const res = await fetch(getApiUrl('/api/agents/networks'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: `网络 ${new Date().toLocaleString('zh-CN')}`,
        nodes: nodes.value,
        edges: edges.value,
      }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    saveMsg.value = '已保存到本机网络列表'
    await loadSavedNetworks()
  } catch (e: any) {
    saveMsg.value = `保存失败: ${e?.message || e}`
  }
}

function loadNetwork(net: any) {
  if (!net) return
  nodes.value = (net.nodes || []).map((n: any) =>
    mkNode({
      id: n.id,
      label: n.label || n.name || n.id,
      agentId: n.agentId || n.role || n.id,
      role: n.role || n.agentId,
      model: n.model || '',
      systemPrompt: n.systemPrompt || '',
      tools: n.tools || [],
      x: n.x ?? 400,
      y: n.y ?? 300,
      status: 'idle',
    }),
  )
  edges.value = (net.edges || []).map((e: any, i: number) => ({
    id: e.id || `e${i}`,
    from: e.from,
    to: e.to,
    type: e.type || 'dependency',
    label: e.label,
  }))
  selectedNodeId.value = null
  saveMsg.value = `已加载「${net.name}」`
}
</script>

<template>
  <div class="ao-page">
    <!-- Header -->
    <header class="ao-page__head">
      <div>
        <h1 class="ao-page__title">{{ hubView === 'studio' ? '精灵工作室' : 'Agent 协作拓扑' }}</h1>
        <p class="ao-page__sub">
          {{
            hubView === 'studio'
              ? '把多 Agent 状态投到工位上 — 与会话 agentStreams 同源'
              : '选择一个预设模板开始，或直接拖拽节点自定义网络'
          }}
        </p>
        <div class="ao-hub-tabs" role="tablist">
          <button
            type="button"
            role="tab"
            :class="['ao-hub-tab', { 'ao-hub-tab--on': hubView === 'topology' }]"
            :aria-selected="hubView === 'topology'"
            @click="setHubView('topology')"
          >
            拓扑网络
          </button>
          <button
            type="button"
            role="tab"
            :class="['ao-hub-tab', { 'ao-hub-tab--on': hubView === 'studio' }]"
            :aria-selected="hubView === 'studio'"
            @click="setHubView('studio')"
          >
            精灵工作室
          </button>
        </div>
      </div>
      <div v-if="hubView === 'topology'" class="ao-page__actions">
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

    <!-- P1 Sprite Studio -->
    <section v-if="hubView === 'studio'" class="ao-studio-wrap">
      <SpriteStudioScene
        :roster="studioRoster"
        :route-label="studioRouteLabel"
        :route-reason="studioRouteReason"
        :active-tool-name="liveSession?.activeToolName || null"
      />
    </section>

    <template v-if="hubView === 'topology'">

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
          type="button"
          :class="['ao-preset', { 'ao-preset--active': selectedPreset === p.id }]"
          @click="applyPreset(p)"
        >
          <TopologyMiniGraph :kind="p.id" />
          <div class="ao-preset__head">
            <span class="ao-preset__name">{{ p.name }}</span>
            <span class="ao-preset__nameEn">{{ p.nameEn }}</span>
          </div>
          <p class="ao-preset__desc">{{ p.desc }}</p>
        </button>
      </div>
    </section>

    <!-- Task input + save feedback -->
    <section class="ao-runbar">
      <label class="ao-runbar__label">任务</label>
      <input
        v-model="runTaskInput"
        type="text"
        class="ao-input ao-runbar__input"
        placeholder="输入要让网络执行的任务…"
        :disabled="running"
        @keydown.enter="runNetwork"
      />
      <span v-if="saveMsg" class="ao-runbar__msg">{{ saveMsg }}</span>
    </section>

    <!-- Graph canvas + side panel -->
    <section class="ao-workspace">
      <div class="ao-canvas-wrap">
        <header class="ao-canvas-head">
          <h3 class="ao-canvas__title">网络画布</h3>
          <span v-if="runResult" class="ao-canvas__status ao-canvas__status--ok">
            {{ runResult.status || '完成' }} · {{ Math.round(runResult.elapsed_ms || 0) }}ms
          </span>
          <span v-else-if="runError" class="ao-canvas__status ao-canvas__status--err">{{ runError }}</span>
        </header>
        <div class="ao-canvas">
          <GraphCanvas
            :nodes="nodes"
            :edges="edges"
            :selected-node-id="selectedNodeId"
            @select="onSelect"
            @select-node="onSelect"
            @update:node-position="onNodePosition"
          />
        </div>

        <!-- Step results -->
        <div v-if="runResult?.steps?.length" class="ao-results">
          <h4 class="ao-results__title">运行结果</h4>
          <div
            v-for="(step, i) in runResult.steps"
            :key="i"
            class="ao-step"
            :class="{ 'ao-step--err': step.status === 'error' }"
          >
            <div class="ao-step__head">
              <strong>{{ step.agent_name || step.node_id }}</strong>
              <span>{{ step.status }} · {{ Math.round(step.elapsed_ms || 0) }}ms</span>
            </div>
            <pre class="ao-step__out">{{ sanitizeAgentDisplayText(step.output || step.error || '—', 600) }}</pre>
          </div>
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
            <span class="ao-field__label">角色 (agentId)</span>
            <select
              class="ao-input"
              :value="selectedNode.agentId || selectedNode.role"
              @change="onRoleChange(($event.target as HTMLSelectElement).value)"
            >
              <option v-for="r in availableRoles" :key="r.id" :value="r.id">{{ r.label }} ({{ r.id }})</option>
            </select>
          </label>
          <label class="ao-field">
            <span class="ao-field__label">模型</span>
            <select v-model="selectedNode.model" class="ao-input">
              <option value="">默认（当前 Provider）</option>
              <option v-for="m in models" :key="m" :value="m">{{ m }}</option>
            </select>
          </label>
          <label class="ao-field">
            <span class="ao-field__label">系统提示</span>
            <textarea
              v-model="selectedNode.systemPrompt"
              class="ao-input ao-textarea"
              placeholder="该节点的角色与约束（会发给引擎）"
              rows="4"
            />
          </label>
          <label class="ao-field">
            <span class="ao-field__label">可用工具</span>
            <div class="ao-tools">
              <label v-for="t in availableTools" :key="t" class="ao-tool-chip">
                <input
                  type="checkbox"
                  :checked="(selectedNode.tools || []).includes(t)"
                  @change="toggleTool(t, ($event.target as HTMLInputElement).checked)"
                />
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
          <p class="ao-stat__hint">点选画布节点配置角色/提示词；拖拽改位置</p>
        </div>

        <div v-if="savedNetworks.length" class="ao-saved">
          <h4 class="ao-saved__title">已保存网络</h4>
          <button
            v-for="net in savedNetworks"
            :key="net.id"
            type="button"
            class="ao-saved__item"
            @click="loadNetwork(net)"
          >
            {{ net.name }}
          </button>
        </div>
      </aside>
    </section>
    </template>
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
.ao-hub-tabs {
  display: inline-flex;
  gap: 4px;
  margin-top: 14px;
  padding: 3px;
  background: var(--color-surface-container-low, #f3f4f6);
  border-radius: 10px;
}
.ao-hub-tab {
  border: none;
  background: transparent;
  padding: 7px 14px;
  border-radius: 8px;
  font-size: 13px;
  cursor: pointer;
  color: var(--color-text-secondary);
}
.ao-hub-tab--on {
  background: var(--color-surface, #fff);
  color: var(--color-brand, #7c3aed);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}
.ao-studio-wrap {
  max-width: 1280px;
  margin: 0 auto;
  padding: 0 32px 48px;
  height: min(780px, calc(100vh - 160px));
  min-height: 560px;
}
.ao-runbar {
  max-width: 1280px;
  margin: 0 auto 16px;
  padding: 0 32px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.ao-runbar__label {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-secondary);
  flex-shrink: 0;
}
.ao-runbar__input {
  flex: 1;
}
.ao-runbar__msg {
  font-size: 12px;
  color: var(--color-text-tertiary);
  flex-shrink: 0;
}
.ao-results {
  border-top: 1px solid var(--color-border);
  padding: 12px 14px 16px;
  max-height: 240px;
  overflow-y: auto;
  background: var(--color-surface-container-lowest, #fff);
}
.ao-results__title {
  margin: 0 0 10px;
  font-size: 12px;
  font-weight: 700;
}
.ao-step {
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 10px;
  margin-bottom: 8px;
}
.ao-step--err {
  border-color: color-mix(in srgb, var(--color-error, #ef4444) 40%, var(--color-border));
}
.ao-step__head {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  margin-bottom: 6px;
  color: var(--color-text-secondary);
}
.ao-step__out {
  margin: 0;
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  max-height: 100px;
  overflow: auto;
}
.ao-saved {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
}
.ao-saved__title {
  margin: 0 0 8px;
  font-size: 11px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.ao-saved__item {
  display: block;
  width: 100%;
  text-align: left;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  border-radius: 8px;
  padding: 8px 10px;
  margin-bottom: 6px;
  font-size: 12px;
  cursor: pointer;
}
.ao-saved__item:hover {
  border-color: var(--color-brand, #7c3aed);
}

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
  gap: 14px;
}
.ao-preset {
  text-align: left;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 14px;
  padding: 12px 12px 14px;
  cursor: pointer;
  font-family: inherit;
  color: var(--color-text-primary);
  transition: border-color 140ms, transform 140ms, box-shadow 140ms;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 0;
}
.ao-preset:hover {
  border-color: color-mix(in srgb, var(--color-brand, #7c3aed) 45%, var(--color-border));
  transform: translateY(-2px);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
}
.ao-preset--active {
  border-color: var(--color-brand, #7c3aed);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-brand, #7c3aed) 18%, transparent);
}
.ao-preset__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}
.ao-preset__name {
  font-size: 14px;
  font-weight: 700;
}
.ao-preset__nameEn {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.06em;
  color: var(--color-text-tertiary);
}
.ao-preset__desc {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--color-text-secondary);
}
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
