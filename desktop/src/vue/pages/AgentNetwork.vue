<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getApiUrl } from '../api/client'

interface AgentNode {
  id: string
  name: string
  icon: string
  color: string
  x: number
  y: number
  agentId: string
}

interface Edge {
  from: string
  to: string
  label: string
}

const agents = ref<AgentNode[]>([
  { id: 'input',  name: '用户输入',   icon: 'person',     color: '#7C3AED', x: 50,  y: 200, agentId: 'input' },
  { id: 'coder',  name: '编码专家',   icon: 'code',       color: '#059669', x: 450, y: 50,  agentId: 'coder' },
  { id: 'review', name: '审查员',     icon: 'rate_review', color: '#DC2626', x: 650, y: 100, agentId: 'reviewer' },
  { id: 'merge',  name: '合并输出',   icon: 'merge',      color: '#7C3AED', x: 850, y: 200, agentId: 'merge' },
])

const edges = ref<Edge[]>([
  { from: 'input',  to: 'coder',  label: '任务' },
  { from: 'coder',  to: 'review', label: '代码审查' },
  { from: 'review', to: 'merge',  label: '最终交付' },
])

const userInput = ref('')
const isRunning = ref(false)
const runResult = ref<any>(null)
const runError = ref<string | null>(null)
const canvasRef = ref<HTMLDivElement | null>(null)
const connecting = ref(false)
const connectFrom = ref<string | null>(null)

const inputNode = computed(() => agents.value.find(a => a.id === 'input'))

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

async function runNetwork() {
  if (!userInput.value.trim()) {
    runError.value = '请先输入任务描述'
    return
  }
  isRunning.value = true
  runError.value = null
  runResult.value = null
  try {
    const res = await fetch(getApiUrl('/api/agents/networks/run-adhoc'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        input: userInput.value,
        nodes: agents.value.map(a => ({ id: a.id, name: a.name, agentId: a.agentId })),
        edges: edges.value.map(e => ({ from: e.from, to: e.to, label: e.label })),
      }),
    })
    if (!res.ok) {
      const t = await res.text().catch(() => '')
      runError.value = `执行失败 (${res.status}): ${t}`
      return
    }
    runResult.value = await res.json()
  } catch (e: any) {
    runError.value = e?.message || '网络错误'
  } finally {
    isRunning.value = false
  }
}

async function saveNetwork() {
  try {
    const res = await fetch(getApiUrl('/api/agents/networks'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: `Network-${Date.now()}`,
        nodes: agents.value.map(a => ({ id: a.id, name: a.name, agentId: a.agentId })),
        edges: edges.value.map(e => ({ from: e.from, to: e.to, label: e.label })),
      }),
    })
    if (res.ok) {
      const data = await res.json()
      runError.value = null
    }
  } catch {}
}

onMounted(() => {
  // Agents are built-in defaults; could fetch from /api/agents in future
})
</script>

<template>
  <div class="network-canvas">
    <div class="network-canvas__head">
      <div>
        <h1 class="network-canvas__title">Agent Network</h1>
        <p class="network-canvas__sub">连接 agent 组成流水线，输入任务后点击执行</p>
      </div>
      <div class="network-canvas__actions">
        <button class="network-canvas__btn" :disabled="isRunning" @click="runNetwork">
          <span class="material-symbols-outlined text-[16px]">{{ isRunning ? 'hourglass_empty' : 'play_arrow' }}</span>
          {{ isRunning ? '执行中…' : '执行' }}
        </button>
        <button class="network-canvas__btn network-canvas__btn--outline" @click="saveNetwork">
          <span class="material-symbols-outlined text-[16px]">save</span>
          保存
        </button>
      </div>
    </div>

    <!-- Task input bar -->
    <div class="network-canvas__input-bar">
      <input
        v-model="userInput"
        type="text"
        placeholder="描述你要完成的任务，例如：写一个贪吃蛇游戏"
        class="network-canvas__input"
        @keydown.enter="runNetwork"
      />
    </div>

    <div ref="canvasRef" class="network-canvas__area" @click="onCanvasClick">
      <svg class="network-canvas__svg">
        <line
          v-for="(edge, i) in edges" :key="i"
          :x1="agents.find(a => a.id === edge.from)?.x + 60 || 0"
          :y1="agents.find(a => a.id === edge.from)?.y + 24 || 0"
          :x2="agents.find(a => a.id === edge.to)?.x || 0"
          :y2="agents.find(a => a.id === edge.to)?.y + 24 || 0"
          stroke="#D1D5DB" stroke-width="2" stroke-dasharray="6,3"
        />
        <text
          v-for="(edge, i) in edges" :key="'t'+i"
          :x="((agents.find(a => a.id === edge.from)?.x || 0) + (agents.find(a => a.id === edge.to)?.x || 0) + 60) / 2 - 20"
          :y="((agents.find(a => a.id === edge.from)?.y || 0) + (agents.find(a => a.id === edge.to)?.y || 0)) / 2 - 4"
          font-size="9" fill="#9CA3AF"
        >{{ edge.label }}</text>
      </svg>

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
      </div>

      <div v-if="connecting" class="network-canvas__hint">
        点击另一个 agent 建立连接，或点击空白处取消
      </div>
    </div>

    <!-- Execution results -->
    <div v-if="runResult || runError" class="network-canvas__results">
      <div v-if="runError" class="network-canvas__error">{{ runError }}</div>
      <div v-if="runResult" class="network-canvas__result-list">
        <div class="network-canvas__result-header">
          执行结果 ({{ runResult.status }} · {{ runResult.elapsed_ms?.toFixed(0) }}ms)
        </div>
        <div
          v-for="step in runResult.steps"
          :key="step.node_id"
          class="network-canvas__result-item"
          :class="{ 'network-canvas__result-item--error': step.status === 'error' }"
        >
          <div class="network-canvas__result-agent">
            <span class="material-symbols-outlined text-[14px]" :style="{ color: step.status === 'error' ? '#DC2626' : '#059669' }">
              {{ step.status === 'error' ? 'error' : 'check_circle' }}
            </span>
            {{ step.agent_name }} ({{ step.elapsed_ms?.toFixed(0) }}ms)
          </div>
          <pre class="network-canvas__result-output">{{ step.output }}</pre>
        </div>
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
.network-canvas__btn:disabled { opacity: 0.5; cursor: not-allowed; }
.network-canvas__btn--outline { background: transparent; color: var(--color-text-primary); border-color: var(--color-border); }

.network-canvas__input-bar {
  padding: 12px 24px; border-bottom: 1px solid var(--color-border);
}
.network-canvas__input {
  width: 100%; padding: 8px 12px; font-size: 13px;
  border: 1px solid var(--color-border); background: var(--color-surface-container-lowest);
  color: var(--color-text-primary); outline: none;
}
.network-canvas__input:focus { border-color: var(--color-primary); }

.network-canvas__area {
  flex: 1; position: relative; overflow: auto;
  background-image: radial-gradient(circle, var(--color-border) 1px, transparent 1px);
  background-size: 24px 24px;
  background-color: var(--color-surface-container-low);
  min-height: 300px;
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

.network-canvas__hint {
  position: absolute; bottom: 16px; left: 50%; transform: translateX(-50%);
  padding: 8px 16px; background: var(--color-primary); color: #fff;
  font-size: 12px; border-radius: 6px; white-space: nowrap;
}

.network-canvas__results {
  max-height: 300px; overflow-y: auto;
  border-top: 1.5px solid var(--color-border);
  background: var(--color-surface-container-lowest);
}
.network-canvas__result-header {
  padding: 8px 24px; font-size: 12px; font-weight: 600;
  color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border);
}
.network-canvas__result-item {
  padding: 10px 24px; border-bottom: 1px solid var(--color-border-separator);
}
.network-canvas__result-item--error { background: rgba(220,38,38,0.05); }
.network-canvas__result-agent {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 6px;
}
.network-canvas__result-output {
  font-size: 12px; line-height: 1.6; color: var(--color-text-secondary);
  white-space: pre-wrap; word-break: break-word;
  font-family: var(--font-mono, monospace); margin: 0;
  max-height: 200px; overflow-y: auto;
}
.network-canvas__error {
  padding: 12px 24px; color: var(--color-error, #DC2626); font-size: 13px;
}

.network-canvas__legend {
  padding: 12px 24px; border-top: 1.5px solid var(--color-border);
  background: var(--color-surface-container-lowest);
  max-height: 120px; overflow-y: auto;
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
