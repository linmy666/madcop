<!--
  v2.7.0 — WorkflowEditor (Vue 3 SFC) — drag-drop + SVG edges
  Built on top of the existing Coze/AG-style editor.
  Adds:
    - Node drag (mousedown/mousemove/mouseup)
    - SVG edge layer with auto-routing
    - Edge creation (click output port → click input port)
    - Zoom/pan (mouse wheel + space)
-->
<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick, type Ref } from 'vue'
import { useTranslation } from '../i18n'
import { listNodeTypes, type NodeTypeMeta } from '../api/workflow'

// ── Types ───────────────────────────────────────────────────────────────────
interface NodeData extends Record<string, unknown> {
  label?: string
  type?: string
  prompt?: string
  system?: string
  params?: any
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

const NODE_W = 200
const NODE_H = 80
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

// ── Events ───────────────────────────────────────────────────────────────────
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

// Viewport
const canvasRef = ref<HTMLDivElement>()
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)

// Drag state
const dragging = ref<{
  nodeId: string
  startX: number
  startY: number
  origX: number
  origY: number
} | null>(null)

// Edge-creation state
const connecting = ref<{
  fromNodeId: string
  pointerX: number
  pointerY: number
} | null>(null)

// Pan state
const panning = ref<{
  startX: number
  startY: number
  origPanX: number
  origPanY: number
} | null>(null)

// ── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const types = await listNodeTypes()
    nodeTypes.value = types
  } catch {
    nodeTypes.value = []
  }
  window.addEventListener('mousemove', onWindowMouseMove)
  window.addEventListener('mouseup', onWindowMouseUp)
})

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onWindowMouseMove)
  window.removeEventListener('mouseup', onWindowMouseUp)
})

// ── Computed ─────────────────────────────────────────────────────────────────
const selectedNode = computed<WfNode | undefined>(() =>
  nodes.value.find((n) => n.id === selectedNodeId.value)
)

const currentNode = computed<WfNode | undefined>(() => {
  if (!props.currentNodeId) return undefined
  return nodes.value.find((n) => n.id === props.currentNodeId)
})

// ── Helpers ──────────────────────────────────────────────────────────────────
function getColorForType(type: string): string {
  return COLOR_BY_TYPE[type] || '#64748b'
}

function getNodeBounds(n: WfNode): { x: number; y: number; w: number; h: number } {
  return { x: n.position.x, y: n.position.y, w: NODE_W, h: NODE_H }
}

// Output port is on the right side, input port on the left
function getOutputPort(n: WfNode): { x: number; y: number } {
  const b = getNodeBounds(n)
  return { x: b.x + b.w, y: b.y + b.h / 2 }
}
function getInputPort(n: WfNode): { x: number; y: number } {
  const b = getNodeBounds(n)
  return { x: b.x, y: b.y + b.h / 2 }
}

// Cubic bezier path with horizontal control points
function edgePath(src: { x: number; y: number }, tgt: { x: number; y: number }): string {
  const dx = Math.max(40, Math.abs(tgt.x - src.x) * 0.4)
  return `M ${src.x} ${src.y} C ${src.x + dx} ${src.y}, ${tgt.x - dx} ${tgt.y}, ${tgt.x} ${tgt.y}`
}

// SVG viewbox = full canvas including panned area
const viewBox = computed(() => {
  // Use a fixed coordinate system; CSS transform handles zoom/pan
  // Compute bounds from nodes
  if (nodes.value.length === 0) {
    return { x: 0, y: 0, w: 2000, h: 1000 }
  }
  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
  for (const n of nodes.value) {
    minX = Math.min(minX, n.position.x)
    minY = Math.min(minY, n.position.y)
    maxX = Math.max(maxX, n.position.x + NODE_W)
    maxY = Math.max(maxY, n.position.y + NODE_H)
  }
  const padding = 200
  return {
    x: minX - padding,
    y: minY - padding,
    w: (maxX - minX) + padding * 2,
    h: (maxY - minY) + padding * 2,
  }
})

// Compute SVG paths for all edges
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

// ── Coordinate transforms ─────────────────────────────────────────────────────
// Convert viewport (client) coords to canvas (world) coords
function clientToWorld(clientX: number, clientY: number): { x: number; y: number } {
  const canvas = canvasRef.value
  if (!canvas) return { x: 0, y: 0 }
  const rect = canvas.getBoundingClientRect()
  const localX = clientX - rect.left
  const localY = clientY - rect.top
  // Reverse the pan/zoom
  return {
    x: (localX - panX.value) / zoom.value,
    y: (localY - panY.value) / zoom.value,
  }
}

// ── Node management ───────────────────────────────────────────────────────────
function addNode(type: string) {
  const id = `n-${type}-${Date.now()}`
  // Place near viewport center
  const cx = -panX.value / zoom.value + 200
  const cy = -panY.value / zoom.value + 200
  nodes.value = [
    ...nodes.value,
    {
      id,
      type,
      position: {
        x: cx + Math.random() * 100,
        y: cy + Math.random() * 100,
      },
      data: { label: type, type, prompt: '', system: '' },
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

// ── Mouse handlers ────────────────────────────────────────────────────────────
function onNodeMouseDown(e: MouseEvent, node: WfNode) {
  e.stopPropagation()
  if (e.button !== 0) return
  selectedNodeId.value = node.id
  const world = clientToWorld(e.clientX, e.clientY)
  dragging.value = {
    nodeId: node.id,
    startX: world.x,
    startY: world.y,
    origX: node.position.x,
    origY: node.position.y,
  }
}

function onOutputPortMouseDown(e: MouseEvent, node: WfNode) {
  e.stopPropagation()
  e.preventDefault()
  if (e.button !== 0) return
  const world = clientToWorld(e.clientX, e.clientY)
  connecting.value = {
    fromNodeId: node.id,
    pointerX: world.x,
    pointerY: world.y,
  }
}

function onInputPortMouseUp(e: MouseEvent, targetNode: WfNode) {
  if (!connecting.value) return
  if (connecting.value.fromNodeId === targetNode.id) {
    connecting.value = null
    return
  }
  // Avoid self-loop, avoid duplicate
  const exists = edges.value.some(
    (e) => e.source === connecting.value!.fromNodeId && e.target === targetNode.id
  )
  if (!exists) {
    edges.value = [
      ...edges.value,
      {
        id: `e-${Date.now()}`,
        source: connecting.value!.fromNodeId,
        target: targetNode.id,
      },
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
    // Middle click or Alt+click = pan
    panning.value = {
      startX: e.clientX,
      startY: e.clientY,
      origPanX: panX.value,
      origPanY: panY.value,
    }
    e.preventDefault()
    return
  }
  if (e.button === 0) {
    // Click empty canvas = deselect
    selectedNodeId.value = null
  }
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const delta = e.deltaY > 0 ? 0.9 : 1.1
  const newZoom = Math.max(0.3, Math.min(2.5, zoom.value * delta))
  // Zoom toward cursor
  const canvas = canvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top
  // World point under cursor before zoom
  const wx = (mx - panX.value) / zoom.value
  const wy = (my - panY.value) / zoom.value
  zoom.value = newZoom
  // Adjust pan so the world point stays under cursor
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

function handleToolParamsChange(event: Event) {
  if (!selectedNode.value) return
  const value = (event.target as HTMLTextAreaElement).value
  try {
    const parsed = JSON.parse(value)
    updateNodeData(selectedNode.value.id, { params: parsed })
  } catch {
    // Allow typing invalid JSON
  }
}

function handleGenericConfigChange(event: Event) {
  if (!selectedNode.value) return
  const value = (event.target as HTMLTextAreaElement).value
  try {
    const parsed = JSON.parse(value)
    updateNodeData(selectedNode.value.id, parsed)
  } catch {
    // Allow typing invalid JSON
  }
}

// Delete with keyboard
function onKeyDown(e: KeyboardEvent) {
  if ((e.key === 'Delete' || e.key === 'Backspace') && selectedNodeId.value) {
    deleteSelectedNode()
  }
}
onMounted(() => window.addEventListener('keydown', onKeyDown))
onBeforeUnmount(() => window.removeEventListener('keydown', onKeyDown))
</script>

<template>
  <div style="height: 100vh; display: flex; flex-direction: column;">
    <!-- Top toolbar -->
    <div
      style="display: flex; align-items: center; padding: 8px 16px; border-bottom: 1px solid var(--color-border); background: var(--color-surface); gap: 12px;"
    >
      <button
        @click="handleBack"
        class="workflow-btn"
      >
        返回
      </button>
      <h2
        style="margin: 0; font-size: 16px; font-weight: 600; flex: 1; color: var(--color-text-primary);"
      >
        {{ workflowName || '新工作流' }}
      </h2>
      <span style="font-size: 11px; color: var(--color-text-tertiary);">
        {{ zoom.toFixed(0) }}%
      </span>
      <button @click="resetView" class="workflow-btn">重置视图</button>
      <button
        @click="handleSave"
        :disabled="isRunning"
        class="workflow-btn"
      >
        {{ saveStatus === 'saving' ? '保存中…' : saveStatus === 'saved' ? '已保存' : '保存' }}
      </button>
      <button
        @click="handleRun"
        :disabled="isRunning"
        :class="['workflow-btn', isRunning ? 'workflow-btn--disabled' : 'workflow-btn--primary']"
      >
        {{ isRunning ? '运行中…' : '▶ 运行' }}
      </button>
    </div>

    <!-- Main area: sidebar + canvas + config panel -->
    <div style="flex: 1; display: flex; min-height: 0;">
      <!-- Left: node library -->
      <div
        style="width: 180px; background: var(--color-surface-container-lowest); border-right: 1px solid var(--color-border); padding: 12px; flex-shrink: 0;"
      >
        <div class="workflow-section-title">节点库</div>
        <div style="display: flex; flex-direction: column; gap: 6px;">
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

        <div class="workflow-section-title" style="margin-top: 24px;">提示</div>
        <div style="font-size: 11px; color: var(--color-text-tertiary); line-height: 1.6;">
          <div>· 拖拽节点移动位置</div>
          <div>· 从节点右边端口拖到目标节点左边端口创建连线</div>
          <div>· 鼠标滚轮缩放，Alt+拖动平移</div>
          <div>· Delete 删除选中节点</div>
          <div>· 选中后右侧编辑属性</div>
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
        <!-- Dot grid background -->
        <div
          style="position: absolute; inset: 0; background-image: radial-gradient(var(--color-border) 1px, transparent 1px); background-size: 24px 24px; pointer-events: none;"
        />

        <!-- Edge layer (SVG) -->
        <svg
          :viewBox="`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`"
          style="position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none;"
          preserveAspectRatio="xMidYMid meet"
        >
          <!-- Existing edges -->
          <g v-for="ep in edgePaths" :key="ep.id">
            <path
              :d="ep.d"
              fill="none"
              stroke="var(--color-border)"
              stroke-width="1.5"
              style="pointer-events: stroke; cursor: pointer;"
              @click.stop="deleteEdge(ep.id)"
            />
          </g>
          <!-- In-progress edge -->
          <path
            v-if="connectingPath"
            :d="connectingPath"
            fill="none"
            stroke="var(--color-brand)"
            stroke-width="2"
            stroke-dasharray="6 4"
          />
          <!-- In-progress edge endpoints (visual feedback) -->
          <circle
            v-if="connecting"
            :cx="connecting.pointerX"
            :cy="connecting.pointerY"
            r="5"
            fill="var(--color-brand)"
          />
        </svg>

        <!-- Node layer (divs) -->
        <div
          style="position: absolute; inset: 0; transform-origin: 0 0;"
          :style="{ transform: `translate(${panX}px, ${panY}px) scale(${zoom})` }"
        >
          <div
            v-for="node in nodes"
            :key="node.id"
            :style="{
              position: 'absolute',
              left: node.position.x + 'px',
              top: node.position.y + 'px',
              width: NODE_W + 'px',
              height: NODE_H + 'px',
            }"
            :class="[
              'workflow-node',
              selectedNodeId === node.id ? 'workflow-node--selected' : '',
              currentNode && currentNode.id === node.id ? 'workflow-node--running' : '',
            ]"
            @mousedown.stop="onNodeMouseDown($event, node)"
            @click.stop="selectedNodeId = node.id"
          >
            <!-- Header bar with color -->
            <div
              :style="{
                height: '20px',
                background: getColorForType(node.type),
                borderRadius: '6px 6px 0 0',
                display: 'flex',
                alignItems: 'center',
                padding: '0 8px',
                fontSize: '10px',
                color: '#fff',
                fontWeight: 600,
                textTransform: 'uppercase',
                letterSpacing: '0.5px',
              }"
            >
              {{ node.type }}
            </div>
            <!-- Body -->
            <div
              style="padding: 6px 10px; background: var(--color-surface); border: 1px solid var(--color-border); border-top: 0; border-radius: 0 0 6px 6px; height: calc(100% - 20px); display: flex; flex-direction: column; gap: 2px;"
            >
              <div style="font-size: 12px; font-weight: 500; color: var(--color-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ node.data.label || node.type }}
              </div>
              <div style="font-size: 10px; color: var(--color-text-tertiary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                {{ node.data.prompt || '点击右侧编辑' }}
              </div>
            </div>
            <!-- Input port (left) -->
            <div
              v-if="node.type !== 'start'"
              :style="{
                position: 'absolute',
                left: -PORT_R + 'px',
                top: (NODE_H / 2 - PORT_R) + 'px',
                width: (PORT_R * 2) + 'px',
                height: (PORT_R * 2) + 'px',
                borderRadius: '50%',
                background: 'var(--color-surface)',
                border: '2px solid var(--color-text-tertiary)',
                cursor: 'crosshair',
              }"
              @mouseup.stop="onInputPortMouseUp($event, node)"
            ></div>
            <!-- Output port (right) -->
            <div
              v-if="node.type !== 'end'"
              :style="{
                position: 'absolute',
                right: -PORT_R + 'px',
                top: (NODE_H / 2 - PORT_R) + 'px',
                width: (PORT_R * 2) + 'px',
                height: (PORT_R * 2) + 'px',
                borderRadius: '50%',
                background: 'var(--color-surface)',
                border: '2px solid var(--color-text-tertiary)',
                cursor: 'crosshair',
              }"
              @mousedown.stop="onOutputPortMouseDown($event, node)"
            ></div>
          </div>
        </div>
      </div>

      <!-- Right: config panel -->
      <div
        v-if="selectedNode"
        style="width: 300px; background: var(--color-surface-container-lowest); border-left: 1px solid var(--color-border); padding: 12px; flex-shrink: 0; overflow-y: auto;"
      >
        <div class="workflow-section-title">节点配置</div>
        <div style="display: flex; flex-direction: column; gap: 10px;">
          <div>
            <label class="workflow-label">类型</label>
            <div style="font-size: 12px; color: var(--color-text-secondary); padding: 4px 8px; background: var(--color-surface); border-radius: 4px; font-family: ui-monospace, monospace;">
              {{ selectedNode.type }}
            </div>
          </div>
          <div>
            <label class="workflow-label">名称</label>
            <input
              type="text"
              :value="selectedNode.data.label"
              @input="(e) => updateNodeData(selectedNode.id, { label: (e.target as HTMLInputElement).value })"
              class="workflow-input"
            />
          </div>
          <div>
            <label class="workflow-label">Prompt</label>
            <textarea
              :value="selectedNode.data.prompt"
              @input="(e) => updateNodeData(selectedNode.id, { prompt: (e.target as HTMLTextAreaElement).value })"
              class="workflow-textarea"
              rows="4"
              placeholder="输入此节点的 prompt..."
            ></textarea>
          </div>
          <div>
            <label class="workflow-label">System (可选)</label>
            <textarea
              :value="selectedNode.data.system"
              @input="(e) => updateNodeData(selectedNode.id, { system: (e.target as HTMLTextAreaElement).value })"
              class="workflow-textarea"
              rows="3"
              placeholder="System prompt..."
            ></textarea>
          </div>
          <div>
            <label class="workflow-label">其他配置 (JSON)</label>
            <textarea
              :value="JSON.stringify({ ...selectedNode.data, label: undefined, prompt: undefined, system: undefined, type: undefined }, null, 2)"
              @change="handleGenericConfigChange"
              class="workflow-textarea"
              rows="4"
              placeholder="{}"
            ></textarea>
          </div>
          <button
            @click="deleteSelectedNode"
            class="workflow-btn workflow-btn--danger"
            style="margin-top: 12px;"
          >
            删除节点
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.workflow-btn {
  padding: 6px 14px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.workflow-btn:hover {
  background: var(--color-surface-container);
  border-color: var(--color-border-focus);
}
.workflow-btn--primary {
  background: var(--color-brand);
  color: #fff;
  border-color: var(--color-brand);
}
.workflow-btn--primary:hover {
  opacity: 0.9;
}
.workflow-btn--disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.workflow-btn--danger {
  color: var(--color-error);
  border-color: color-mix(in srgb, var(--color-error) 30%, transparent);
}
.workflow-btn--danger:hover {
  background: color-mix(in srgb, var(--color-error) 5%, transparent);
}

.workflow-section-title {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--color-text-tertiary);
  margin-bottom: 8px;
}

.workflow-node-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 10px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-primary);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
}
.workflow-node-chip:hover {
  background: var(--color-surface-container);
  border-color: var(--color-border-focus);
}
.workflow-node-chip__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.workflow-node {
  user-select: none;
  cursor: grab;
  transition: box-shadow 0.15s;
}
.workflow-node:hover {
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.12);
}
.workflow-node:active {
  cursor: grabbing;
}
.workflow-node--selected {
  outline: 2px solid var(--color-brand);
  outline-offset: 2px;
}
.workflow-node--running {
  outline: 2px solid var(--color-success);
  outline-offset: 2px;
  animation: workflow-pulse 1.5s ease-in-out infinite;
}

@keyframes workflow-pulse {
  0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--color-success) 30%, transparent); }
  50% { box-shadow: 0 0 0 8px color-mix(in srgb, var(--color-success) 0%, transparent); }
}

.workflow-label {
  display: block;
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}

.workflow-input,
.workflow-textarea {
  width: 100%;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  padding: 6px 8px;
  font-size: 12px;
  color: var(--color-text-primary);
  font-family: inherit;
  resize: vertical;
}
.workflow-input:focus,
.workflow-textarea:focus {
  outline: none;
  border-color: var(--color-brand);
}
.workflow-textarea {
  font-family: ui-monospace, 'SF Mono', monospace;
  font-size: 11px;
}
</style>
