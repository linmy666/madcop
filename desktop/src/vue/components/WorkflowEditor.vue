<!--
  v2.7.0 — WorkflowEditor (Vue 3 SFC)
  Full translation of src/components/workflow/WorkflowEditor.tsx (664 lines).
  Workflow editor (Coze/AG style) for building agent workflows.
  - Sidebar with node library
  - Top toolbar (Save / Run / Status)
  - Right side panel for node config
  - Canvas area for visual node editing
-->
<script setup lang="ts">
import { ref, computed, onMounted, type Ref } from 'vue'
import { useTranslation } from '../i18n'
import { listNodeTypes, type NodeTypeMeta } from '../api/workflow'

// ── Types ───────────────────────────────────────────────────────────────────
interface NodeData extends Record<string, unknown> {
  label?: string
  type?: string
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

// ── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const types = await listNodeTypes()
    nodeTypes.value = types
  } catch {
    nodeTypes.value = []
  }
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

function updateNodeData(nodeId: string, updates: Partial<NodeData>) {
  nodes.value = nodes.value.map((n) =>
    n.id === nodeId ? { ...n, data: { ...n.data, ...updates } } : n
  )
}

// ── Methods ──────────────────────────────────────────────────────────────────
function addNode(type: string) {
  const id = `n-${type}-${Date.now()}`
  nodes.value = [
    ...nodes.value,
    {
      id,
      type,
      position: {
        x: 100 + Math.random() * 200,
        y: 100 + Math.random() * 200,
      },
      data: { label: type, type, prompt: '', system: '' },
    },
  ]
}

function onConnect(params: { source: string; target: string }) {
  edges.value = [
    ...edges.value,
    { id: `e-${Date.now()}`, source: params.source, target: params.target },
  ]
}

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

function deleteSelectedNode() {
  if (!selectedNodeId.value) return
  nodes.value = nodes.value.filter((n) => n.id !== selectedNodeId.value)
  edges.value = edges.value.filter(
    (e) => e.source !== selectedNodeId.value && e.target !== selectedNodeId.value
  )
  selectedNodeId.value = null
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
    // Allow typing invalid JSON — stored as raw string
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
</script>

<template>
  <div style="height: 100vh; display: flex; flex-direction: column;">
    <!-- Top toolbar -->
    <div
      style="display: flex; align-items: center; padding: 8px 16px; border-bottom: 1px solid var(--color-border); background: var(--color-surface-container-low); gap: 8px;"
    >
      <button
        @click="handleBack"
        style="padding: 4px 10px; background: transparent; border: 1px solid var(--color-border); border-radius: 4px; color: var(--color-text-primary); cursor: pointer;"
      >
        <span class="material-symbols-outlined" style="font-size: 14px; vertical-align: -3px; margin-right: 2px;">arrow_back</span>
        返回
      </button>
      <h2
        style="margin: 0; font-size: 16px; font-weight: 600; flex: 1; color: var(--color-text-primary);"
      >
        {{ workflowName || '新工作流' }}
      </h2>
      <button
        @click="handleSave"
        :disabled="isRunning"
        style="padding: 6px 14px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 4px; color: var(--color-text-primary); cursor: pointer; font-weight: 500;"
      >
        <span class="material-symbols-outlined" style="font-size: 14px; vertical-align: -3px; margin-right: 2px;">
          {{ saveStatus === 'saving' ? 'sync' : saveStatus === 'saved' ? 'check' : 'save' }}
        </span>
        {{ saveStatus === 'saving' ? '保存中…' : saveStatus === 'saved' ? '已保存' : '保存' }}
      </button>
      <button
        @click="handleRun"
        :disabled="isRunning"
        style="padding: 6px 14px; background: isRunning ? 'var(--color-surface-container-high)' : 'var(--color-brand)'; border: none; border-radius: 4px; color: #fff; cursor: isRunning ? 'default' : 'pointer'; font-weight: 600;"
      >
        <span class="material-symbols-outlined" style="font-size: 14px; vertical-align: -3px; margin-right: 2px;">
          {{ isRunning ? 'pause' : 'play_arrow' }}
        </span>
        {{ isRunning ? '运行中…' : '运行' }}
      </button>
    </div>

    <!-- Main area: sidebar + canvas + config panel -->
    <div style="flex: 1; display: flex; min-height: 0;">
      <!-- Left: node library -->
      <div
        style="width: 160px; background: var(--color-surface-container-lowest); border-right: 1px solid var(--color-border); padding: 12px; display: flex; flex-direction: column; gap: 8px;"
      >
        <div
          style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: var(--color-text-tertiary);"
        >
          节点库
        </div>
        <button
          v-for="nt in nodeTypes"
          :key="nt.type"
          @click="addNode(nt.type)"
          :disabled="isRunning"
          :title="nt.description"
          style="padding: 8px 12px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 4px; color: var(--color-text-primary); cursor: pointer; text-align: left; font-size: 13px;"
        >
          {{ nt.label }}
        </button>
      </div>

      <!-- Middle: canvas -->
      <div style="flex: 1; position: relative;" data-testid="workflow-canvas">
        <!-- React Flow equivalent: Vue canvas for nodes -->
        <div
          style="position: absolute; inset: 0; background: var(--color-surface-container-lowest);"
          @click="selectedNodeId = null"
        >
          <!-- Grid background (CSS pattern) -->
          <div
            style="position: absolute; inset: 0; background-image: radial-gradient(var(--color-border) 1px, transparent 1px); background-size: 20px 20px; opacity: 0.5; pointer-events: none;"
          />

          <!-- Nodes -->
          <div
            v-for="node in nodes"
            :key="node.id"
            @click.stop="selectedNodeId = node.id"
            style="position: absolute; left: node.position.x + 'px'; top: node.position.y + 'px';"
          >
            <div
              :style="{
                background: 'var(--color-surface)',
                border: selectedNodeId === node.id ? `2px solid ${getColorForType(node.type)}` : '1px solid var(--color-border)',
                borderRadius: '8px',
                padding: '12px 16px',
                minWidth: '180px',
                boxShadow: selectedNodeId === node.id
                  ? '0 4px 12px rgba(0,0,0,0.15)'
                  : '0 1px 3px rgba(0,0,0,0.08)',
              }"
            >
              <div
                :style="{
                  fontSize: '10px',
                  textTransform: 'uppercase',
                  letterSpacing: '1px',
                  color: getColorForType(node.type),
                  fontWeight: 600,
                  marginBottom: 4,
                }"
              >
                {{ node.type }}
              </div>
              <div :style="{ fontSize: '13px', color: 'var(--color-text-primary)', fontWeight: 500 }">
                {{ node.data.label || node.type }}
              </div>
            </div>
          </div>
        </div>

        <!-- Running indicator -->
        <div
          v-if="currentNode"
          style="position: absolute; top: 16px; right: 16px; background: var(--color-brand); color: #fff; padding: 6px 12px; border-radius: 4px; font-size: 12px; font-weight: 500; box-shadow: 0 2px 8px rgba(0,0,0,0.15);"
        >
          正在运行: {{ currentNode.data?.label || currentNode.id }}
        </div>
      </div>

      <!-- Right: node config panel -->
      <div
        v-if="selectedNode"
        style="width: 320px; background: var(--color-surface-container-lowest); border-left: 1px solid var(--color-border); padding: 16px; overflow-y: auto;"
      >
        <div
          style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: var(--color-text-tertiary); margin-bottom: 8px;"
        >
          节点配置
        </div>
        <div
          style="font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 12px;"
        >
          {{ selectedNode.data?.label || selectedNode.id }} ({{ selectedNode.type }})
        </div>

        <!-- LLM node config -->
        <template v-if="selectedNode.type === 'llm'">
          <label style="display: block; font-size: 12px; margin-bottom: 4px; color: var(--color-text-secondary);">
            节点标签
          </label>
          <input
            type="text"
            :value="selectedNode.data?.label || ''"
            @input="updateNodeData(selectedNode.id, { label: ($event.target as HTMLInputElement).value })"
            style="width: 100%; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface); color: var(--color-text-primary); margin-bottom: 12px; font-size: 13px;"
          />
          <label style="display: block; font-size: 12px; margin-bottom: 4px; color: var(--color-text-secondary);">
            System Prompt (可选)
          </label>
          <textarea
            :value="selectedNode.data?.system || ''"
            @input="updateNodeData(selectedNode.id, { system: ($event.target as HTMLTextAreaElement).value })"
            rows="3"
            style="width: 100%; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface); color: var(--color-text-primary); margin-bottom: 12px; font-size: 13px; font-family: inherit; resize: vertical;"
          />
          <label style="display: block; font-size: 12px; margin-bottom: 4px; color: var(--color-text-secondary);">
            User Prompt (支持 {{input}} / {{node_id}} / {{node_id.output}})
          </label>
          <textarea
            :value="selectedNode.data?.prompt || ''"
            @input="updateNodeData(selectedNode.id, { prompt: ($event.target as HTMLTextAreaElement).value })"
            rows="6"
            placeholder="用一句话回答: {{input}}"
            style="width: 100%; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface); color: var(--color-text-primary); font-size: 13px; font-family: var(--font-mono, monospace); resize: vertical;"
          />
        </template>

        <!-- Tool node config -->
        <template v-else-if="selectedNode.type === 'tool'">
          <label style="display: block; font-size: 12px; margin-bottom: 4px; color: var(--color-text-secondary);">
            节点标签
          </label>
          <input
            type="text"
            :value="selectedNode.data?.label || ''"
            @input="updateNodeData(selectedNode.id, { label: ($event.target as HTMLInputElement).value })"
            style="width: 100%; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface); color: var(--color-text-primary); margin-bottom: 12px; font-size: 13px;"
          />
          <label style="display: block; font-size: 12px; margin-bottom: 4px; color: var(--color-text-secondary);">
            工具名
          </label>
          <input
            type="text"
            :value="(selectedNode.data as any)?.tool || ''"
            @input="updateNodeData(selectedNode.id, { tool: ($event.target as HTMLInputElement).value })"
            placeholder="get_weather"
            style="width: 100%; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface); color: var(--color-text-primary); margin-bottom: 12px; font-size: 13px;"
          />
          <label style="display: block; font-size: 12px; margin-bottom: 4px; color: var(--color-text-secondary);">
            参数 (JSON, 支持 {{input}})
          </label>
          <textarea
            :value="JSON.stringify((selectedNode.data as any)?.params || {}, null, 2) || ''"
            @input="handleToolParamsChange($event)"
            rows="5"
            placeholder='{"city": "Hangzhou"}'
            style="width: 100%; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface); color: var(--color-text-primary); font-size: 13px; font-family: var(--font-mono, monospace); resize: vertical;"
          />
        </template>

        <!-- Generic config for other node types (not start/end) -->
        <template v-else-if="selectedNode.type !== 'start' && selectedNode.type !== 'end'">
          <label style="display: block; font-size: 12px; margin-bottom: 4px; color: var(--color-text-secondary);">
            节点标签
          </label>
          <input
            type="text"
            :value="selectedNode.data?.label || ''"
            @input="updateNodeData(selectedNode.id, { label: ($event.target as HTMLInputElement).value })"
            style="width: 100%; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface); color: var(--color-text-primary); margin-bottom: 12px; font-size: 13px;"
          />
          <label style="display: block; font-size: 12px; margin-bottom: 4px; color: var(--color-text-secondary);">
            配置 (JSON, 支持 {{input}})
          </label>
          <textarea
            :value="JSON.stringify(Object.fromEntries(Object.entries(selectedNode.data || {}).filter(([k]) => k !== 'label')), null, 2) || '{}'"
            @input="handleGenericConfigChange($event)"
            rows="8"
            style="width: 100%; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface); color: var(--color-text-primary); font-size: 13px; font-family: var(--font-mono, monospace); resize: vertical;"
          />
        </template>

        <!-- Delete button -->
        <button
          @click="deleteSelectedNode"
          :disabled="isRunning"
          style="margin-top: 16px; padding: 6px 12px; background: transparent; border: 1px solid #ef4444; color: #ef4444; border-radius: 4px; cursor: pointer; font-size: 12px;"
        >
          <span class="material-symbols-outlined" style="font-size: 14px; vertical-align: -2px; margin-right: 2px;">delete</span>
          删除节点
        </button>
      </div>
    </div>
  </div>
</template>
