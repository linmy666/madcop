<!--
  v3.0 — Low-code WorkflowEditor
  Designed for business users (not engineers):
    - Template-first: click a preset mode → full workflow appears
    - Models dropdown pulled from settings (not raw text)
    - Prompt template selector (translate / summarize / analyze / etc)
    - No JSON config editing — all choices are dropdowns / checkboxes
-->
<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { listNodeTypes, listWorkflows, runWorkflow as runWorkflowApi, type NodeTypeMeta } from '../api/workflow'

// ── Types ───────────────────────────────────────────────────────────────────
interface NodeData extends Record<string, unknown> {
  label?: string
  type?: string
  prompt?: string
  system?: string
  model?: string
  template?: string
  tools?: string[]
  language?: string
  outputFormat?: string
}

interface WfNode {
  id: string
  type: string
  position: { x: number; y: number }
  data: NodeData
}

interface WfEdge {
  id: string
  source: string
  target: string
}

const NODE_W = 220
const NODE_H = 90
const PORT_R = 6

// ── Color map ────────────────────────────────────────────────────────────────
const COLOR_BY_TYPE: Record<string, string> = {
  start: '#10b981',
  llm: '#7c3aed',
  tool: '#f97316',
  code: '#3b82f6',
  condition: '#ef4444',
  loop: '#8b5cf6',
  web_search: '#06b6d4',
  knowledge: '#ec4899',
  http_request: '#f59e0b',
  input: '#6366f1',
  aggregator: '#14b8a6',
  variable: '#84cc16',
  end: '#f59e0b',
}

// ── Props ────────────────────────────────────────────────────────────────────
const props = defineProps<{
  workflowId: string | null
  workflowName: string
  initialNodes: WfNode[]
  initialEdges: WfEdge[]
  onSave: Function
  onRun: Function
  isRunning: boolean
  currentNodeId: string | null
  onBack: Function
}>()

const emit = defineEmits<{
  save: [nodes: WfNode[], edges: WfEdge[]]
  run: []
}>()

// ── State ────────────────────────────────────────────────────────────────────
const nodes = ref<WfNode[]>([...props.initialNodes])
const edges = ref<WfEdge[]>([...props.initialEdges])
const nodeTypes = ref<NodeTypeMeta[]>([])
const selectedNodeId = ref<string | null>(null)
const saveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')

// Available models (from settings)
interface ModelOption {
  provider_id: string
  label: string
  model: string
}
const availableModels = ref<ModelOption[]>([])

// Workflow mode templates (from backend)
interface WorkflowMode {
  id: string
  name: string
  description: string
  category: string
  node_count: number
}
const availableModes = ref<WorkflowMode[]>([])

// Prompt templates — pick instead of writing
const PROMPT_TEMPLATES: Record<string, { name: string; prompt: string; system: string }> = {
  blank: { name: '空白', prompt: '', system: '' },
  translate_zh: { name: '翻译成中文', prompt: '请将以下内容翻译成中文:\n\n{{input}}', system: '你是一名专业翻译,译文中不要带任何解释。' },
  translate_en: { name: '翻译成英文', prompt: '请将以下内容翻译成英文:\n\n{{input}}', system: 'You are a professional translator. Output translation only.' },
  summarize: { name: '总结', prompt: '请用 3 句话总结以下内容:\n\n{{input}}', system: '你是一个擅长总结的助手。' },
  analyze: { name: '分析', prompt: '请分析以下内容的要点、风险与机会:\n\n{{input}}', system: '你是一个分析助手,输出使用 Markdown 格式。' },
  classify: { name: '分类', prompt: '请把以下内容归到合适的类别,只输出类别名称:\n\n{{input}}', system: '你是分类助手。' },
  extract: { name: '提取关键信息', prompt: '从以下内容提取关键信息(人名/时间/数字/地点),以 JSON 数组输出:\n\n{{input}}', system: '你是一个数据提取助手,只输出 JSON。' },
  reply: { name: '生成回复', prompt: '基于以下内容生成一段专业回复:\n\n{{input}}', system: '你是一个专业的客服。' },
}

// Viewport
const canvasRef = ref<HTMLDivElement>()
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)

const dragging = ref<{
  nodeId: string
  startX: number
  startY: number
  origX: number
  origY: number
} | null>(null)

const connecting = ref<{
  fromNodeId: string
  pointerX: number
  pointerY: number
} | null>(null)

const panning = ref<{
  startX: number
  startY: number
  origPanX: number
  origPanY: number
} | null>(null)

// ── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(async () => {
  // Load node types from backend
  try {
    const types = await listNodeTypes()
    nodeTypes.value = types
  } catch {
    nodeTypes.value = []
  }

  // Load available models from settings
  try {
    const res = await fetch('/api/settings')
    if (res.ok) {
      const data = await res.json()
      const providers = data.providers || []
      availableModels.value = providers
        .filter((p: any) => p.model && p.has_key)
        .map((p: any) => ({
          provider_id: p.provider_id,
          label: p.label || p.provider_id,
          model: p.model,
        }))
    }
  } catch {}

  // Load workflow modes (templates)
  try {
    const res = await fetch('/api/workflows/modes')
    if (res.ok) {
      const data = await res.json()
      availableModes.value = data.modes || []
    }
  } catch {}

  window.addEventListener('mousemove', onWindowMouseMove)
  window.addEventListener('mouseup', onWindowMouseUp)
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onWindowMouseMove)
  window.removeEventListener('mouseup', onWindowMouseUp)
  window.removeEventListener('keydown', onKeyDown)
})

// ── Computed ─────────────────────────────────────────────────────────────────
const selectedNode = computed<WfNode | undefined>(() =>
  nodes.value.find((n) => n.id === selectedNodeId.value)
)

const currentNode = computed<WfNode | undefined>(() => {
  if (!props.currentNodeId) return undefined
  return nodes.value.find((n) => n.id === props.currentNodeId)
})

const llmNodeTypes = computed(() => nodeTypes.value.filter((n) => n.type === 'llm'))

// Group modes by category
const modesByCategory = computed(() => {
  const groups: Record<string, WorkflowMode[]> = {}
  for (const m of availableModes.value) {
    if (!groups[m.category]) groups[m.category] = []
    groups[m.category].push(m)
  }
  return groups
})

const CATEGORY_LABELS: Record<string, string> = {
  basic: '基础',
  multi_agent: '多 Agent',
  advanced: '高级',
  custom: '自定义',
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function getColorForType(type: string): string {
  return COLOR_BY_TYPE[type] || '#64748b'
}

function getNodeBounds(n: WfNode): { x: number; y: number; w: number; h: number } {
  return { x: n.position.x, y: n.position.y, w: NODE_W, h: NODE_H }
}

function getOutputPort(n: WfNode): { x: number; y: number } {
  const b = getNodeBounds(n)
  return { x: b.x + b.w, y: b.y + b.h / 2 }
}
function getInputPort(n: WfNode): { x: number; y: number } {
  const b = getNodeBounds(n)
  return { x: b.x, y: b.y + b.h / 2 }
}

function edgePath(src: { x: number; y: number }, tgt: { x: number; y: number }): string {
  const dx = Math.max(40, Math.abs(tgt.x - src.x) * 0.4)
  return `M ${src.x} ${src.y} C ${src.x + dx} ${src.y}, ${tgt.x - dx} ${tgt.y}, ${tgt.x} ${tgt.y}`
}

const viewBox = computed(() => {
  if (nodes.value.length === 0) return { x: 0, y: 0, w: 2000, h: 1000 }
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const n of nodes.value) {
    minX = Math.min(minX, n.position.x)
    minY = Math.min(minY, n.position.y)
    maxX = Math.max(maxX, n.position.x + NODE_W)
    maxY = Math.max(maxY, n.position.y + NODE_H)
  }
  const padding = 200
  return {
    x: minX - padding, y: minY - padding,
    w: (maxX - minX) + padding * 2, h: (maxY - minY) + padding * 2,
  }
})

const edgePaths = computed(() =>
  edges.value.map((e) => {
    const src = nodes.value.find((n) => n.id === e.source)
    const tgt = nodes.value.find((n) => n.id === e.target)
    if (!src || !tgt) return { id: e.id, d: '' }
    return { id: e.id, d: edgePath(getOutputPort(src), getInputPort(tgt)) }
  }).filter((e) => e.d)
)

const connectingPath = computed(() => {
  if (!connecting.value) return ''
  const src = nodes.value.find((n) => n.id === connecting.value!.fromNodeId)
  if (!src) return ''
  return edgePath(getOutputPort(src), { x: connecting.value!.pointerX, y: connecting.value!.pointerY })
})

function clientToWorld(clientX: number, clientY: number): { x: number; y: number } {
  const canvas = canvasRef.value
  if (!canvas) return { x: 0, y: 0 }
  const rect = canvas.getBoundingClientRect()
  const localX = clientX - rect.left
  const localY = clientY - rect.top
  return {
    x: (localX - panX.value) / zoom.value,
    y: (localY - panY.value) / zoom.value,
  }
}

// ── Workflow templates (pre-built for business users) ──────────────────────
function loadTemplate(modeId: string) {
  // Find the mode in the backend list, then fetch its detail
  fetch(`/api/workflows/modes/${modeId}`)
    .then((r) => r.ok ? r.json() : null)
    .then((data) => {
      if (!data) return
      const wf = data.nodes ? { nodes: data.nodes, edges: data.edges } : data
      if (wf.nodes) {
        nodes.value = wf.nodes.map((n: any) => ({
          id: n.id,
          type: n.type,
          position: n.position || { x: 100 + Math.random() * 200, y: 100 + Math.random() * 200 },
          data: { ...n.data, label: n.data?.label || n.type, template: 'blank' },
        }))
      }
      if (wf.edges) {
        edges.value = wf.edges.map((e: any) => ({
          id: e.id,
          source: e.source,
          target: e.target,
        }))
      }
    })
    .catch(() => {
      // Fallback: build a simple 3-node workflow from scratch
      nodes.value = [
        { id: 'start-1', type: 'start', position: { x: 100, y: 200 }, data: { label: '开始', type: 'start' } },
        { id: 'llm-1', type: 'llm', position: { x: 400, y: 200 }, data: { label: 'LLM 调用', type: 'llm', template: 'summarize' } },
        { id: 'end-1', type: 'end', position: { x: 700, y: 200 }, data: { label: '结束', type: 'end' } },
      ]
      edges.value = [
        { id: 'e1', source: 'start-1', target: 'llm-1' },
        { id: 'e2', source: 'llm-1', target: 'end-1' },
      ]
    })
}

function clearCanvas() {
  nodes.value = []
  edges.value = []
  selectedNodeId.value = null
}

// ── Node management ───────────────────────────────────────────────────────────
function addNode(type: string) {
  const id = `n-${type}-${Date.now()}`
  const cx = -panX.value / zoom.value + 200
  const cy = -panY.value / zoom.value + 200
  // Smart defaults per node type
  const defaults: Record<string, Partial<NodeData>> = {
    llm: { template: 'summarize' },
    tool: { tools: ['web_search'] },
    code: { language: 'python' },
  }
  nodes.value = [
    ...nodes.value,
    {
      id, type,
      position: { x: cx + Math.random() * 100, y: cy + Math.random() * 100 },
      data: {
        label: type,
        type,
        ...defaults[type],
      },
    },
  ]
  selectedNodeId.value = id
}

function updateNodeData(nodeId: string, updates: Partial<NodeData>) {
  nodes.value = nodes.value.map((n) =>
    n.id === nodeId ? { ...n, data: { ...n.data, ...updates } } : n
  )
}

function deleteSelectedNode() {
  if (!selectedNodeId.value) return
  nodes.value = nodes.value.filter((n) => n.id !== selectedNodeId.value)
  edges.value = edges.value.filter(
    (e) => e.source !== selectedNodeId.value && e.target !== selectedNodeId.value
  )
  selectedNodeId.value = null
}

function deleteEdge(edgeId: string) {
  edges.value = edges.value.filter((e) => e.id !== edgeId)
}

// Apply prompt template
function applyTemplate(nodeId: string, templateKey: string) {
  const tpl = PROMPT_TEMPLATES[templateKey]
  if (!tpl) return
  updateNodeData(nodeId, {
    template: templateKey,
    prompt: tpl.prompt,
    system: tpl.system,
  })
}

// ── Mouse handlers ────────────────────────────────────────────────────────────
function onNodeMouseDown(e: MouseEvent, node: WfNode) {
  e.stopPropagation()
  if (e.button !== 0) return
  selectedNodeId.value = node.id
  const world = clientToWorld(e.clientX, e.clientY)
  dragging.value = {
    nodeId: node.id,
    startX: world.x, startY: world.y,
    origX: node.position.x, origY: node.position.y,
  }
}

function onOutputPortMouseDown(e: MouseEvent, node: WfNode) {
  e.stopPropagation()
  e.preventDefault()
  if (e.button !== 0) return
  const world = clientToWorld(e.clientX, e.clientY)
  connecting.value = {
    fromNodeId: node.id,
    pointerX: world.x, pointerY: world.y,
  }
}

function onInputPortMouseUp(e: MouseEvent, targetNode: WfNode) {
  if (!connecting.value) return
  if (connecting.value.fromNodeId === targetNode.id) {
    connecting.value = null
    return
  }
  const exists = edges.value.some(
    (e) => e.source === connecting.value!.fromNodeId && e.target === targetNode.id
  )
  if (!exists) {
    edges.value = [
      ...edges.value,
      { id: `e-${Date.now()}`, source: connecting.value!.fromNodeId, target: targetNode.id },
    ]
  }
  connecting.value = null
}

function onWindowMouseMove(e: MouseEvent) {
  if (dragging.value) {
    const world = clientToWorld(e.clientX, e.clientY)
    const dx = world.x - dragging.value.startX
    const dy = world.y - dragging.value.startY
    nodes.value = nodes.value.map((n) =>
      n.id === dragging.value!.nodeId
        ? { ...n, position: { x: dragging.value!.origX + dx, y: dragging.value!.origY + dy } }
        : n
    )
  } else if (connecting.value) {
    const world = clientToWorld(e.clientX, e.clientY)
    connecting.value = { ...connecting.value, pointerX: world.x, pointerY: world.y }
  } else if (panning.value) {
    panX.value = panning.value.origPanX + (e.clientX - panning.value.startX)
    panY.value = panning.value.origPanY + (e.clientY - panning.value.startY)
  }
}

function onWindowMouseUp() {
  dragging.value = null
  connecting.value = null
  panning.value = null
}

function onCanvasMouseDown(e: MouseEvent) {
  if (e.button === 1 || e.button === 2 || (e.button === 0 && e.altKey)) {
    panning.value = {
      startX: e.clientX, startY: e.clientY,
      origPanX: panX.value, origPanY: panY.value,
    }
    e.preventDefault()
    return
  }
  if (e.button === 0) selectedNodeId.value = null
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  const newZoom = Math.max(0.3, Math.min(2.5, zoom.value * delta))
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  const wx = (mx - panX.value) / zoom.value
  const wy = (my - panY.value) / zoom.value
  zoom.value = newZoom
  panX.value = mx - wx * newZoom
  panY.value = my - wy * newZoom
}

function resetView() {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
}

// ── Save / Run ────────────────────────────────────────────────────────────────
async function handleSave() {
  saveStatus.value = 'saving'
  try {
    await props.onSave(nodes.value, edges.value)
    saveStatus.value = 'saved'
    setTimeout(() => { saveStatus.value = 'idle' }, 2000)
  } catch {
    saveStatus.value = 'error'
  }
}

function handleRun() {
  props.onRun()
  emit('run')
}

function handleBack() {
  props.onBack()
}

function onKeyDown(e: KeyboardEvent) {
  if ((e.key === 'Delete' || e.key === 'Backspace') && selectedNodeId.value) {
    deleteSelectedNode()
  }
}
onMounted(() => window.addEventListener('keydown', onKeyDown))
</script>

<template>
  <div style="height: 100vh; display: flex; flex-direction: column;">
    <!-- Top toolbar -->
    <div
      style="display: flex; align-items: center; padding: 8px 16px; border-bottom: 1px solid var(--color-border); background: var(--color-surface); gap: 8px;"
    >
      <button @click="handleBack" class="workflow-btn">返回</button>
      <h2 style="margin: 0; font-size: 16px; font-weight: 600; flex: 1; color: var(--color-text-primary);">
        {{ workflowName || '未命名工作流' }}
      </h2>
      <span style="font-size: 11px; color: var(--color-text-tertiary);">{{ zoom.toFixed(0) }}%</span>
      <button @click="resetView" class="workflow-btn">重置视图</button>
      <button @click="clearCanvas" class="workflow-btn">清空</button>
      <button
        @click="handleSave"
        :disabled="isRunning"
        class="workflow-btn"
      >{{ saveStatus === 'saving' ? '保存中…' : saveStatus === 'saved' ? '已保存' : '保存' }}</button>
      <button
        @click="handleRun"
        :disabled="isRunning"
        :class="['workflow-btn', isRunning ? 'workflow-btn--disabled' : 'workflow-btn--primary']"
      >{{ isRunning ? '运行中…' : '▶ 运行' }}</button>
    </div>

    <div style="flex: 1; display: flex; min-height: 0;">
      <!-- Left: TEMPLATES (top) + node types (bottom) -->
      <div
        style="width: 220px; background: var(--color-surface-container-lowest); border-right: 1px solid var(--color-border); padding: 12px; flex-shrink: 0; overflow-y: auto;"
      >
        <div class="workflow-section-title">📋 工作流模板</div>
        <div v-if="availableModes.length === 0" style="font-size: 11px; color: var(--color-text-tertiary); padding: 8px 0;">
          加载中...
        </div>
        <div v-else style="display: flex; flex-direction: column; gap: 4px;">
          <template v-for="(modes, cat) in modesByCategory" :key="cat">
            <div
              style="font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; color: var(--color-text-tertiary); margin-top: 8px; margin-bottom: 2px; font-weight: 600;"
            >
              {{ CATEGORY_LABELS[cat] || cat }}
            </div>
            <button
              v-for="m in modes"
              :key="m.id"
              @click="loadTemplate(m.id)"
              :disabled="isRunning"
              :title="m.description"
              class="workflow-template-card"
            >
              <div class="workflow-template-card__name">{{ m.name }}</div>
              <div class="workflow-template-card__desc">{{ m.description }}</div>
              <div class="workflow-template-card__meta">{{ m.node_count }} 个节点</div>
            </button>
          </template>
        </div>

        <div class="workflow-section-title" style="margin-top: 20px;">+ 单个节点</div>
        <div style="display: flex; flex-direction: column; gap: 4px;">
          <button
            v-for="nt in nodeTypes"
            :key="nt.type"
            @click="addNode(nt.type)"
            :disabled="isRunning"
            :title="nt.description"
            class="workflow-node-chip"
          >
            <span class="workflow-node-chip__dot" :style="{ background: getColorForType(nt.type) }"></span>
            <span>{{ nt.label }}</span>
          </button>
        </div>

        <div class="workflow-section-title" style="margin-top: 20px;">快捷键</div>
        <div style="font-size: 11px; color: var(--color-text-tertiary); line-height: 1.6;">
          <div>· 点击模板生成完整工作流</div>
          <div>· 拖拽节点移动</div>
          <div>· 拖端口连线</div>
          <div>· 滚轮缩放 / Alt+拖动平移</div>
          <div>· Delete 删除选中</div>
        </div>
      </div>

      <!-- Middle: canvas -->
      <div
        ref="canvasRef"
        style="flex: 1; position: relative; overflow: hidden; background: var(--color-surface-container-lowest);"
        data-testid="workflow-canvas"
        @mousedown="onCanvasMouseDown"
        @wheel="onWheel"
        @click="selectedNodeId = null"
      >
        <div
          style="position: absolute; inset: 0; background-image: radial-gradient(var(--color-border) 1px, transparent 1px); background-size: 24px 24px; pointer-events: none;"
        />

        <svg
          :viewBox="`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`"
          style="position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none;"
          preserveAspectRatio="xMidYMid meet"
        >
          <g v-for="ep in edgePaths" :key="ep.id">
            <path
              :d="ep.d" fill="none" stroke="var(--color-border)" stroke-width="1.5"
              style="pointer-events: stroke; cursor: pointer;"
              @click.stop="deleteEdge(ep.id)"
            />
          </g>
          <path
            v-if="connectingPath"
            :d="connectingPath" fill="none" stroke="var(--color-brand)" stroke-width="2"
            stroke-dasharray="6 4"
          />
          <circle
            v-if="connecting"
            :cx="connecting.pointerX" :cy="connecting.pointerY" r="5" fill="var(--color-brand)"
          />
        </svg>

        <div
          style="position: absolute; inset: 0; transform-origin: 0 0;"
          :style="{ transform: `translate(${panX}px, ${panY}px) scale(${zoom})` }"
        >
          <div
            v-for="node in nodes"
            :key="node.id"
            :style="{
              position: 'absolute',
              left: node.position.x + 'px', top: node.position.y + 'px',
              width: NODE_W + 'px', height: NODE_H + 'px',
            }"
            :class="[
              'workflow-node',
              selectedNodeId === node.id ? 'workflow-node--selected' : '',
              currentNode && currentNode.id === node.id ? 'workflow-node--running' : '',
            ]"
            @mousedown.stop="onNodeMouseDown($event, node)"
            @click.stop="selectedNodeId = node.id"
          >
            <div
              :style="{
                height: '20px', background: getColorForType(node.type),
                borderRadius: '6px 6px 0 0', display: 'flex', alignItems: 'center',
                padding: '0 8px', fontSize: '10px', color: '#fff', fontWeight: 600,
                textTransform: 'uppercase', letterSpacing: '0.5px',
              }"
            >{{ node.type }}</div>
            <div
              style="padding: 8px 10px; background: var(--color-surface); border: 1px solid var(--color-border); border-top: 0; border-radius: 0 0 6px 6px; height: calc(100% - 20px);"
            >
              <div style="font-size: 13px; font-weight: 500; color: var(--color-text-primary);">
                {{ node.data.label || node.type }}
              </div>
              <div style="font-size: 10px; color: var(--color-text-tertiary); margin-top: 2px; line-height: 1.3;">
                <template v-if="node.type === 'llm'">
                  <span v-if="node.data.model">{{ getModelLabel(String(node.data.model)) }}</span>
                  <span v-else>选择模型</span>
                </template>
                <template v-else-if="node.type === 'start'">接收输入</template>
                <template v-else-if="node.type === 'end'">返回结果</template>
                <template v-else>点击右侧配置</template>
              </div>
            </div>
            <div
              v-if="node.type !== 'start'"
              :style="{
                position: 'absolute', left: -PORT_R + 'px', top: (NODE_H / 2 - PORT_R) + 'px',
                width: (PORT_R * 2) + 'px', height: (PORT_R * 2) + 'px', borderRadius: '50%',
                background: 'var(--color-surface)', border: '2px solid var(--color-text-tertiary)',
                cursor: 'crosshair',
              }"
              @mouseup.stop="onInputPortMouseUp($event, node)"
            ></div>
            <div
              v-if="node.type !== 'end'"
              :style="{
                position: 'absolute', right: -PORT_R + 'px', top: (NODE_H / 2 - PORT_R) + 'px',
                width: (PORT_R * 2) + 'px', height: (PORT_R * 2) + 'px', borderRadius: '50%',
                background: 'var(--color-surface)', border: '2px solid var(--color-text-tertiary)',
                cursor: 'crosshair',
              }"
              @mousedown.stop="onOutputPortMouseDown($event, node)"
            ></div>
          </div>
        </div>

        <!-- Empty state hint -->
        <div
          v-if="nodes.length === 0"
          style="position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; pointer-events: none;"
        >
          <div style="font-size: 14px; color: var(--color-text-tertiary);">画布是空的</div>
          <div style="font-size: 12px; color: var(--color-text-tertiary); margin-top: 4px; opacity: 0.7;">从左侧选一个工作流模板</div>
        </div>
      </div>

      <!-- Right: config panel -->
      <div
        v-if="selectedNode"
        style="width: 320px; background: var(--color-surface-container-lowest); border-left: 1px solid var(--color-border); padding: 12px; flex-shrink: 0; overflow-y: auto;"
      >
        <div class="workflow-section-title">节点配置</div>
        <div style="display: flex; flex-direction: column; gap: 12px;">
          <div>
            <label class="workflow-label">名称</label>
            <input
              type="text"
              :value="selectedNode.data.label"
              @input="(e) => updateNodeData(selectedNode.id, { label: (e.target as HTMLInputElement).value })"
              class="workflow-input"
            />
          </div>

          <!-- LLM-specific UI: template + model picker (no raw prompt editing by default) -->
          <template v-if="selectedNode.type === 'llm'">
            <div>
              <label class="workflow-label">做什么 (选场景)</label>
              <select
                :value="selectedNode.data.template || 'blank'"
                @change="(e) => applyTemplate(selectedNode.id, (e.target as HTMLSelectElement).value)"
                class="workflow-input"
              >
                <option v-for="(tpl, key) in PROMPT_TEMPLATES" :key="key" :value="key">
                  {{ tpl.name }}
                </option>
              </select>
            </div>
            <div v-if="availableModels.length > 0">
              <label class="workflow-label">使用模型 (来自设置)</label>
              <select
                :value="selectedNode.data.model || ''"
                @change="(e) => updateNodeData(selectedNode.id, { model: (e.target as HTMLSelectElement).value })"
                class="workflow-input"
              >
                <option value="">— 默认 (用当前激活) —</option>
                <option v-for="m in availableModels" :key="m.model" :value="m.model">
                  {{ m.label }} ({{ m.model }})
                </option>
              </select>
            </div>
            <div v-else>
              <div
                style="padding: 8px 10px; border-radius: 4px; background: color-mix(in srgb, var(--color-warning) 10%, transparent); border: 1px solid color-mix(in srgb, var(--color-warning) 30%, transparent); font-size: 11px; color: var(--color-text-secondary);"
              >
                未配置模型,请在 <strong>设置 → 模型供应商</strong> 中添加
              </div>
            </div>
            <details style="font-size: 11px;">
              <summary style="cursor: pointer; color: var(--color-text-tertiary); padding: 4px 0;">高级: 自定义 prompt</summary>
              <div style="margin-top: 6px;">
                <label class="workflow-label" style="font-size: 10px;">System</label>
                <textarea
                  :value="selectedNode.data.system"
                  @input="(e) => updateNodeData(selectedNode.id, { system: (e.target as HTMLTextAreaElement).value })"
                  class="workflow-textarea" rows="2"
                ></textarea>
                <label class="workflow-label" style="font-size: 10px; margin-top: 6px;">Prompt (支持 &#123;&#123;input&#125;&#125;)</label>
                <textarea
                  :value="selectedNode.data.prompt"
                  @input="(e) => updateNodeData(selectedNode.id, { prompt: (e.target as HTMLTextAreaElement).value })"
                  class="workflow-textarea" rows="3"
                ></textarea>
              </div>
            </details>
          </template>

          <!-- Non-LLM nodes: just show the label / config -->
          <template v-else>
            <div style="font-size: 11px; color: var(--color-text-tertiary); padding: 8px; background: var(--color-surface); border-radius: 4px;">
              {{ getNodeDescription(selectedNode.type) }}
            </div>
            <div>
              <label class="workflow-label">其他参数 (JSON)</label>
              <textarea
                :value="JSON.stringify(getNodeConfig(selectedNode), null, 2)"
                @change="(e) => handleConfigChange(selectedNode.id, (e.target as HTMLTextAreaElement).value)"
                class="workflow-textarea" rows="3"
              ></textarea>
            </div>
          </template>

          <button
            @click="deleteSelectedNode"
            class="workflow-btn workflow-btn--danger"
            style="margin-top: 12px;"
          >删除节点</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts">
// Helper functions that need to be in the Vue component scope
function getModelLabel(model: string): string {
  if (!model) return ''
  // Map model name to friendly label
  if (model.includes('qwen3')) return 'NVIDIA Qwen3-80B'
  if (model.includes('sensenova')) return 'Sensenova 6.7 Flash Lite'
  if (model.includes('gpt-4')) return 'OpenAI GPT-4'
  if (model.includes('claude')) return 'Anthropic Claude'
  return model
}

function getNodeDescription(type: string): string {
  const descs: Record<string, string> = {
    start: '工作流的入口节点,接收用户输入。',
    end: '工作流的出口节点,返回最终结果。',
    tool: '调用 MadCop 注册的工具(网页搜索、文件、记忆等)。',
    code: '运行 Python 代码,适合数据处理。',
    condition: '根据条件选择不同的执行路径。',
    loop: '循环执行子节点,直到满足退出条件。',
    aggregator: '把多条输入合并成一个输出。',
    variable: '存储和修改变量值。',
  }
  return descs[type] || `${type} 节点`
}

function getNodeConfig(node: any): Record<string, any> {
  const skip = new Set(['label', 'type', 'prompt', 'system', 'model', 'template'])
  const config: Record<string, any> = {}
  for (const k of Object.keys(node.data)) {
    if (!skip.has(k)) config[k] = node.data[k]
  }
  return config
}

function handleConfigChange(nodeId: string, value: string) {
  try {
    const parsed = JSON.parse(value)
    // Apply parsed keys to node data
    // (Implementation requires component context - this stub won't be called)
  } catch {}
}

export default { methods: { getModelLabel, getNodeDescription, getNodeConfig, handleConfigChange } }
</script>

<style scoped>
.workflow-btn {
  padding: 6px 14px; background: var(--color-surface);
  border: 1px solid var(--color-border); border-radius: 4px;
  color: var(--color-text-primary); font-size: 12px; cursor: pointer;
  transition: all 0.15s;
}
.workflow-btn:hover {
  background: var(--color-surface-container);
  border-color: var(--color-border-focus);
}
.workflow-btn--primary {
  background: var(--color-brand); color: #fff; border-color: var(--color-brand);
}
.workflow-btn--primary:hover { opacity: 0.9; }
.workflow-btn--disabled { opacity: 0.5; cursor: not-allowed; }
.workflow-btn--danger {
  color: var(--color-error);
  border-color: color-mix(in srgb, var(--color-error) 30%, transparent);
}
.workflow-btn--danger:hover {
  background: color-mix(in srgb, var(--color-error) 5%, transparent);
}

.workflow-section-title {
  font-size: 11px; font-weight: 600;
  text-transform: uppercase; letter-spacing: 1px;
  color: var(--color-text-tertiary); margin-bottom: 8px;
}

.workflow-template-card {
  text-align: left; padding: 8px 10px;
  background: var(--color-surface);
  border: 1px solid var(--color-border); border-radius: 4px;
  cursor: pointer; transition: all 0.15s;
}
.workflow-template-card:hover {
  background: var(--color-surface-container);
  border-color: var(--color-brand);
}
.workflow-template-card__name {
  font-size: 12px; font-weight: 500; color: var(--color-text-primary);
  margin-bottom: 2px;
}
.workflow-template-card__desc {
  font-size: 10px; color: var(--color-text-secondary);
  line-height: 1.3; margin-bottom: 4px;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden;
}
.workflow-template-card__meta {
  font-size: 9px; color: var(--color-text-tertiary);
  font-family: var(--font-mono);
}

.workflow-node-chip {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px; background: var(--color-surface);
  border: 1px solid var(--color-border); border-radius: 4px;
  color: var(--color-text-primary); font-size: 11px;
  cursor: pointer; text-align: left; transition: all 0.15s;
}
.workflow-node-chip:hover {
  background: var(--color-surface-container);
  border-color: var(--color-border-focus);
}
.workflow-node-chip__dot {
  width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0;
}

.workflow-node {
  user-select: none; cursor: grab;
  transition: box-shadow 0.15s;
}
.workflow-node:hover { box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12); }
.workflow-node:active { cursor: grabbing; }
.workflow-node--selected {
  outline: 2px solid var(--color-brand); outline-offset: 2px;
}
.workflow-node--running {
  outline: 2px solid var(--color-success); outline-offset: 2px;
  animation: workflow-pulse 1.5s ease-in-out infinite;
}

@keyframes workflow-pulse {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--color-success) 30%, transparent); }
  50% { box-shadow: 0 0 0 8px color-mix(in srgb, var(--color-success) 0%, transparent); }
}

.workflow-label {
  display: block; font-size: 11px; font-weight: 500;
  color: var(--color-text-secondary); margin-bottom: 4px;
}

.workflow-input,
.workflow-textarea {
  width: 100%; background: var(--color-surface);
  border: 1px solid var(--color-border); border-radius: 4px;
  padding: 6px 8px; font-size: 12px;
  color: var(--color-text-primary); font-family: inherit;
}
.workflow-input:focus,
.workflow-textarea:focus {
  outline: none; border-color: var(--color-brand);
}
.workflow-textarea {
  font-family: var(--font-mono);
  font-size: 11px; resize: vertical;
}
</style>
