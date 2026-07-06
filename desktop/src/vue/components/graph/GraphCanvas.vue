<script setup lang="ts">
/**
 * GraphCanvas — SVG-based graph visualization for multi-agent topology.
 *
 * Every node is a circle (○), every edge is a line (─).
 * The user can drag nodes, click to select, and watch the graph
 * "evolve" as agents activate.
 *
 * Design: minimal SVG, zero icons, pure geometry.
 * Node colors come from CSS variables so they adapt to theme.
 */

import { ref, computed, onMounted, onUnmounted, watch } from 'vue'

// ─── Types ─────────────────────────────────────────────────────────────

export interface GraphNodeData {
  id: string
  label: string
  detail?: string
  x: number
  y: number
  status?: 'idle' | 'running' | 'completed' | 'failed'
}

export interface GraphEdgeData {
  id: string
  from: string
  to: string
  type?: 'dependency' | 'flow' | 'control'
  label?: string
}

// ─── Props ─────────────────────────────────────────────────────────────

const props = withDefaults(
  defineProps<{
    nodes: GraphNodeData[]
    edges: GraphEdgeData[]
    selectedNodeId?: string | null
    readonly?: boolean
    showGrid?: boolean
  }>(),
  {
    selectedNodeId: null,
    readonly: false,
    showGrid: true,
  },
)

const emit = defineEmits<{
  'select-node': [id: string]
  'update:node-position': [id: string, x: number, y: number]
}>()

// ─── Internal state ────────────────────────────────────────────────────

const svgRef = ref<SVGSVGElement>()
const draggingNode = ref<string | null>(null)
const dragOffset = ref({ x: 0, y: 0 })

// Working copy of node positions (mutable during drag)
const nodePositions = ref<Record<string, { x: number; y: number }>>({})

watch(
  () => props.nodes,
  (nodes) => {
    for (const n of nodes) {
      if (!nodePositions.value[n.id]) {
        nodePositions.value[n.id] = { x: n.x, y: n.y }
      }
    }
  },
  { immediate: true, deep: true },
)

function getPos(id: string) {
  return nodePositions.value[id] ?? { x: 0, y: 0 }
}

// ─── Drag logic ────────────────────────────────────────────────────────

function svgPoint(e: MouseEvent | TouchEvent): { x: number; y: number } {
  const svg = svgRef.value
  if (!svg) return { x: 0, y: 0 }
  const pt = svg.createSVGPoint()
  const clientX = 'touches' in e ? e.touches[0].clientX : e.clientX
  const clientY = 'touches' in e ? e.touches[0].clientY : e.clientY
  pt.x = clientX
  pt.y = clientY
  const ctm = svg.getScreenCTM()
  if (!ctm) return { x: clientX, y: clientY }
  const transformed = pt.matrixTransform(ctm.inverse())
  return { x: transformed.x, y: transformed.y }
}

function startDrag(e: MouseEvent, nodeId: string) {
  if (props.readonly) return
  e.stopPropagation()
  draggingNode.value = nodeId
  const pos = getPos(nodeId)
  const pt = svgPoint(e)
  dragOffset.value = { x: pt.x - pos.x, y: pt.y - pos.y }
}

function onDragMove(e: MouseEvent) {
  if (!draggingNode.value) return
  const pt = svgPoint(e)
  const newX = pt.x - dragOffset.value.x
  const newY = pt.y - dragOffset.value.y
  nodePositions.value[draggingNode.value] = { x: newX, y: newY }
}

function endDrag() {
  if (draggingNode.value) {
    const pos = nodePositions.value[draggingNode.value]
    emit('update:node-position', draggingNode.value, pos.x, pos.y)
    draggingNode.value = null
  }
}

// ─── Edge rendering ────────────────────────────────────────────────────

function edgePath(edge: GraphEdgeData): string {
  const from = getPos(edge.from)
  const to = getPos(edge.to)
  // Straight line — clean, mathematical
  return `M ${from.x} ${from.y} L ${to.x} ${to.y}`
}

function edgeLabelPos(edge: GraphEdgeData): { x: number; y: number } {
  const from = getPos(edge.from)
  const to = getPos(edge.to)
  return { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 }
}

// ─── Node visual ───────────────────────────────────────────────────────

const NODE_RADIUS = 38

function nodeFill(status?: string): string {
  switch (status) {
    case 'running':
      return 'var(--color-brand)'
    case 'completed':
      return 'var(--color-success)'
    case 'failed':
      return 'var(--color-error)'
    default:
      return 'var(--color-surface-container)'
  }
}

function nodeStroke(status?: string, selected = false): string {
  if (selected) return 'var(--color-brand)'
  switch (status) {
    case 'running':
      return 'var(--color-brand)'
    case 'completed':
      return 'var(--color-success)'
    case 'failed':
      return 'var(--color-error)'
    default:
      return 'var(--color-border)'
  }
}

// ─── Cleanup ───────────────────────────────────────────────────────────

onMounted(() => {
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', endDrag)
})
onUnmounted(() => {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', endDrag)
})
</script>

<template>
  <div class="graph-canvas-container relative h-full w-full overflow-hidden">
    <!-- Grid background — subtle dot grid, like graph paper -->
    <div
      v-if="showGrid"
      class="pointer-events-none absolute inset-0 opacity-[0.35]"
      style="
        background-image: radial-gradient(
          circle,
          var(--color-border) 0.5px,
          transparent 0.5px
        );
        background-size: 24px 24px;
      "
    ></div>

    <svg
      ref="svgRef"
      class="relative h-full w-full"
      viewBox="0 0 1000 600"
      preserveAspectRatio="xMidYMid meet"
      @click="emit('select-node', '')"
    >
      <!-- Edges layer (drawn first, below nodes) -->
      <g class="edges-layer">
        <template v-for="edge in edges" :key="edge.id">
          <path
            :d="edgePath(edge)"
            fill="none"
            :stroke="edge.type === 'control' ? 'var(--color-text-tertiary)' : 'var(--color-border)'"
            :stroke-width="edge.type === 'control' ? 1 : 1.5"
            :stroke-dasharray="edge.type === 'control' ? '4 3' : 'none'"
            opacity="0.6"
          />
          <!-- Edge label -->
          <text
            v-if="edge.label"
            :x="edgeLabelPos(edge).x"
            :y="edgeLabelPos(edge).y - 4"
            text-anchor="middle"
            class="edge-label"
            fill="var(--color-text-tertiary)"
          >
            {{ edge.label }}
          </text>
        </template>
      </g>

      <!-- Nodes layer -->
      <g class="nodes-layer">
        <g
          v-for="node in nodes"
          :key="node.id"
          :transform="`translate(${getPos(node.id).x}, ${getPos(node.id).y})`"
          class="node-group"
          :class="{ 'node-group--selected': selectedNodeId === node.id }"
          @click.stop="emit('select-node', node.id)"
          @mousedown="startDrag($event, node.id)"
        >
          <!-- Pulsing ring when running -->
          <circle
            v-if="node.status === 'running'"
            :r="NODE_RADIUS + 6"
            fill="none"
            stroke="var(--color-brand)"
            stroke-width="1"
            opacity="0.3"
            class="pulse-ring"
          />

          <!-- Main circle -->
          <circle
            :r="NODE_RADIUS"
            :fill="nodeFill(node.status)"
            :stroke="nodeStroke(node.status, selectedNodeId === node.id)"
            :stroke-width="selectedNodeId === node.id ? 2.5 : 1.5"
            class="node-circle"
          />

          <!-- Label (inside circle) -->
          <text
            text-anchor="middle"
            dy="-2"
            class="node-label"
            :fill="node.status === 'idle' ? 'var(--color-text-primary)' : '#fff'"
          >
            {{ node.label }}
          </text>

          <!-- Detail (model name, below label) -->
          <text
            v-if="node.detail"
            text-anchor="middle"
            dy="14"
            class="node-detail"
            :fill="node.status === 'idle' ? 'var(--color-text-tertiary)' : 'rgba(255,255,255,0.7)'"
            style="font-family: ui-monospace, 'SF Mono', monospace"
          >
            {{ node.detail }}
          </text>
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.node-circle {
  transition: stroke-width 0.15s ease, fill 0.3s ease;
  cursor: grab;
}
.node-group:hover .node-circle {
  stroke-width: 2.5;
}
.node-group:active .node-circle {
  cursor: grabbing;
}
.node-group--selected .node-circle {
  filter: drop-shadow(0 0 8px var(--color-brand));
}

.node-label {
  font-size: 13px;
  font-weight: 600;
  pointer-events: none;
  user-select: none;
}
.node-detail {
  font-size: 9px;
  pointer-events: none;
  user-select: none;
}
.edge-label {
  font-size: 9px;
  font-family: ui-monospace, 'SF Mono', monospace;
  pointer-events: none;
  user-select: none;
}

/* Running node pulse animation */
@keyframes pulse {
  0% {
    r: 44px;
    opacity: 0.4;
  }
  100% {
    r: 56px;
    opacity: 0;
  }
}
.pulse-ring {
  animation: pulse 1.5s ease-out infinite;
}
</style>
