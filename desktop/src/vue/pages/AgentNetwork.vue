<script setup lang="ts">
// v3.0 — Agent Network Canvas: visual orchestration of multi-agent workflows.
// Each node is an agent, edges represent message flow / delegation.
// Drag-and-drop to connect agents. Right-click to configure.

import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

interface AgentNode {
  id: string
  name: string
  icon: string
  color: string
  x: number
  y: number
}

interface Edge {
  from: string
  to: string
  label: string
}

const agents: AgentNode[] = [
  { id: 'input',  name: '用户输入',   icon: 'person',     color: '#7C3AED', x: 50,  y: 200 },
  { id: 'router', name: '路由分配',   icon: 'alt_route',  color: '#0E7490', x: 250, y: 100 },
  { id: 'coder',  name: '编码专家',   icon: 'code',       color: '#059669', x: 450, y: 50 },
  { id: 'design', name: '设计助手',   icon: 'palette',    color: '#B45309', x: 450, y: 150 },
  { id: 'search', name: '研究员',     icon: 'travel_explore', color: '#1D4ED8', x: 450, y: 250 },
  { id: 'review', name: '审查员',     icon: 'rate_review', color: '#DC2626', x: 650, y: 100 },
  { id: 'merge',  name: '合并输出',   icon: 'merge',      color: '#7C3AED', x: 850, y: 200 },
]

const edges = ref<Edge[]>([
  { from: 'input',  to: 'router', label: '任务' },
  { from: 'router', to: 'coder',  label: '开发任务' },
  { from: 'router', to: 'design', label: '设计任务' },
  { from: 'router', to: 'search', label: '调研任务' },
  { from: 'coder',  to: 'review', label: '代码审查' },
  { from: 'design', to: 'review', label: '设计审查' },
  { from: 'search', to: 'merge',  label: '调研报告' },
  { from: 'review', to: 'merge',  label: '最终交付' },
])

const canvasRef = ref<HTMLDivElement | null>(null)
const connecting = ref(false)
const connectFrom = ref<string | null>(null)

function onNodeClick(id: string, e: MouseEvent) {
  e.stopPropagation()
  if (connecting.value && connectFrom.value && connectFrom.value !== id) {
    edges.value.push({ from: connectFrom.value, to: id, label: 'delegate' })
    connecting.value = false
    connectFrom.value = null
    return
  }
  connectFrom.value = id
  connecting.value = true
}

function onCanvasClick() {
  connecting.value = false
  connectFrom.value = null
}

function removeEdge(i: number) {
  edges.value.splice(i, 1)
}

function runNetwork() {
  // In real app: POST /api/agents/network/run
}
</script>

<template>
  <div class="network-canvas">
    <div class="network-canvas__head">
      <div>
        <h1 class="network-canvas__title">Agent Network</h1>
        <p class="network-canvas__sub">点击一个 agent → 再点击另一个 agent → 建立连接</p>
      </div>
      <div class="network-canvas__actions">
        <button class="network-canvas__btn" @click="runNetwork">
          <span class="material-symbols-outlined text-[16px]">play_arrow</span>
          执行
        </button>
        <button class="network-canvas__btn network-canvas__btn--outline" @click="() => {}">
          <span class="material-symbols-outlined text-[16px]">save</span>
          保存
        </button>
      </div>
    </div>

    <div ref="canvasRef" class="network-canvas__area" @click="onCanvasClick">
      <svg class="network-canvas__svg">
        <!-- Edges -->
        <line
          v-for="(edge, i) in edges" :key="i"
          :x1="agents.find(a => a.id === edge.from)!.x + 60"
          :y1="agents.find(a => a.id === edge.from)!.y + 24"
          :x2="agents.find(a => a.id === edge.to)!.x"
          :y2="agents.find(a => a.id === edge.to)!.y + 24"
          stroke="#D1D5DB" stroke-width="2" stroke-dasharray="6,3"
        />
        <!-- Edge labels -->
        <text
          v-for="(edge, i) in edges" :key="'t'+i"
          :x="(agents.find(a => a.id === edge.from)!.x + agents.find(a => a.id === edge.to)!.x + 60) / 2 - 20"
          :y="(agents.find(a => a.id === edge.from)!.y + agents.find(a => a.id === edge.to)!.y) / 2 - 4"
          font-size="9" fill="#9CA3AF"
        >{{ edge.label }}</text>
      </svg>

      <!-- Agent nodes -->
      <div
        v-for="agent in agents" :key="agent.id"
        class="network-node"
        :class="{ 'network-node--selected': connecting && connectFrom === agent.id }"
        :style="{ left: agent.x + 'px', top: agent.y + 'px' }"
        @click="(e) => onNodeClick(agent.id, e)"
      >
        <div class="network-node__icon" :style="{ background: agent.color }">
          <span class="material-symbols-outlined text-[20px] text-white">{{ agent.icon }}</span>
        </div>
        <div class="network-node__name">{{ agent.name }}</div>
        <div v-if="agent.id === 'router'" class="network-node__badge">orchestrator</div>
      </div>

      <!-- Instructions -->
      <div v-if="connecting" class="network-canvas__hint">
        点击另一个 agent 以建立连接，或点击空白处取消。
      </div>
    </div>

    <!-- Legend -->
    <div class="network-canvas__legend">
      <div class="network-canvas__legend-title">连接管理</div>
      <div class="network-canvas__legend-row" v-for="(edge, i) in edges" :key="i">
        <span class="network-canvas__legend-edge">{{ agents.find(a => a.id === edge.from)?.name }} → {{ agents.find(a => a.id === edge.to)?.name }}</span>
        <input v-model="edge.label" class="network-canvas__legend-input" placeholder="描述…" />
        <button class="network-canvas__legend-del" @click="removeEdge(i)">×</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.network-canvas {
  width: 100%; height: 100%;
  display: flex; flex-direction: column;
  background: var(--color-surface);
}
.network-canvas__head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 24px; border-bottom: 1.5px solid var(--color-border);
}
.network-canvas__title { font-size: 20px; font-weight: 700; color: var(--color-text-primary); margin: 0; }
.network-canvas__sub   { font-size: 12px; color: var(--color-text-tertiary); margin-top: 2px; }
.network-canvas__actions { display: flex; gap: 8px; }
.network-canvas__btn {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 16px; font-size: 13px; font-weight: 500; cursor: pointer;
  border: 1.5px solid var(--color-primary);
  background: var(--color-primary); color: var(--color-on-primary);
}
.network-canvas__btn--outline { background: transparent; color: var(--color-text-primary); border-color: var(--color-border); }

.network-canvas__area {
  flex: 1; position: relative; overflow: auto;
  background-image: radial-gradient(circle, var(--color-border) 1px, transparent 1px);
  background-size: 24px 24px;
  background-color: var(--color-surface-container-low);
  min-height: 400px;
}
.network-canvas__svg { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }

.network-node {
  position: absolute;
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  width: 120px; padding: 12px 0; cursor: pointer;
  background: var(--color-surface-container-lowest);
  border: 1.5px solid var(--color-border);
  transition: border-color 140ms, box-shadow 140ms;
}
.network-node:hover { border-color: var(--color-primary); }
.network-node--selected { border-color: var(--color-primary); box-shadow: 0 0 0 3px rgba(124,58,237,0.2); }
.network-node__icon {
  width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;
}
.network-node__name { font-size: 12px; font-weight: 600; color: var(--color-text-primary); }
.network-node__badge {
  font-size: 9px; text-transform: uppercase; letter-spacing: 0.05em;
  padding: 1px 6px; color: #fff; font-weight: 700;
  background: var(--color-primary);
}

.network-canvas__hint {
  position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%);
  padding: 8px 16px; background: var(--color-primary); color: #fff;
  font-size: 12px; border-radius: 6px; white-space: nowrap;
}

.network-canvas__legend {
  padding: 12px 24px; border-top: 1.5px solid var(--color-border);
  background: var(--color-surface-container-lowest);
  max-height: 160px; overflow-y: auto;
}
.network-canvas__legend-title { font-size: 11px; font-weight: 600; color: var(--color-text-tertiary); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
.network-canvas__legend-row { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.network-canvas__legend-edge { font-size: 11px; color: var(--color-text-secondary); min-width: 120px; }
.network-canvas__legend-input {
  flex: 1; padding: 2px 6px; border: 1px solid var(--color-border);
  font-size: 11px; background: transparent; outline: none; max-width: 160px;
}
.network-canvas__legend-del { background: transparent; border: none; cursor: pointer; color: var(--color-text-tertiary); font-size: 14px; }
</style>