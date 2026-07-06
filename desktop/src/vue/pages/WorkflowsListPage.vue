<!--
  v2.7.0 — WorkflowsListPage (Vue 3 SFC)
  Full translation of src/pages/WorkflowsListPage.tsx (347 lines).
  Shows all saved workflows + create new. Also shows mode library.
-->
<script setup lang="ts">
import { ref, onMounted, type Ref } from 'vue'
import {
  listWorkflows,
  createWorkflow,
  deleteWorkflow,
  runWorkflow,
  type Workflow,
  type NodeTypeMeta,
} from '../api/workflow'
import { listNodeTypes } from '../api/workflow'
import { getApiUrl } from '../api/client'
import { defineAsyncComponent } from 'vue'
const WorkflowEditor = defineAsyncComponent(() => import('../components/WorkflowEditor.vue'))

interface AgentMode {
  id: string
  name: string
  description: string
  category: string
  icon: string
  node_count: number
}

const workflows: Ref<Workflow[]> = ref([])
const nodeTypes: Ref<NodeTypeMeta[]> = ref([])
const editingId: Ref<string | null> = ref(null)
const editingName: Ref<string> = ref('')
const editingNodes: Ref<any[]> = ref([])
const editingEdges: Ref<any[]> = ref([])
const loading: Ref<boolean> = ref(true)
const isRunning: Ref<boolean> = ref(false)
const currentNodeId: Ref<string | null> = ref(null)
const runResult: Ref<string | null> = ref(null)
const modes: Ref<AgentMode[]> = ref([])

const refresh = async () => {
  loading.value = true
  try {
    const [list, types, modesData] = await Promise.all([
      listWorkflows(),
      listNodeTypes(),
      fetch(getApiUrl('/api/workflows/modes'))
        .then(r => r.json())
        .then(d => d.modes || [])
        .catch(() => []),
    ])
    workflows.value = list
    nodeTypes.value = types
    modes.value = modesData
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  refresh()
})

const handleNew = async () => {
  // v2.7.0: Always include start + end nodes; LLM node added in editor.
  // Don't depend on nodeTypes.length — if the metadata API was
  // slow / failed, the user can still create a workflow.
  const wf = await createWorkflow({
    name: '未命名工作流',
    description: '',
    nodes: [
      { id: 'start-1', type: 'start', position: { x: 100, y: 200 }, data: { label: '开始' } },
      { id: 'end-1', type: 'end', position: { x: 500, y: 200 }, data: { label: '结束' } },
    ],
    edges: [],
  } as any)
  await refresh()
  editingId.value = (wf as any).id
  editingName.value = (wf as any).name
  editingNodes.value = (wf as any).nodes
  editingEdges.value = (wf as any).edges
}

const handleEdit = (wf: Workflow) => {
  editingId.value = wf.id
  editingName.value = wf.name
  editingNodes.value = wf.nodes as any[]
  editingEdges.value = wf.edges as any[]
}

const handleDelete = async (id: string) => {
  if (!confirm('确定删除这个工作流？')) return
  await deleteWorkflow(id)
  await refresh()
}

const handleSave = async (nodes: any[], edges: any[]) => {
  if (!editingId.value) return
  const r = await fetch(`/api/workflows/${editingId.value}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      name: editingName.value,
      nodes: nodes.map((n: any) => ({
        id: n.id,
        type: n.type,
        position: n.position,
        data: n.data,
      })),
      edges: edges.map((e: any) => ({
        id: e.id,
        source: e.source,
        target: e.target,
      })),
    }),
  })
  if (!r.ok) throw new Error(`Save failed: ${r.status}`)
  await refresh()
}

const handleRun = async () => {
  if (!editingId.value) return
  isRunning.value = true
  currentNodeId.value = null
  runResult.value = null
  try {
    const run = await runWorkflow(editingId.value, { input: '你好' })
    runResult.value = JSON.stringify(run, null, 2)
  } catch (e: any) {
    runResult.value = `Error: ${e.message}`
  } finally {
    isRunning.value = false
  }
}

const handleBack = async () => {
  editingId.value = null
  editingName.value = ''
  editingNodes.value = []
  editingEdges.value = []
  runResult.value = null
  await refresh()
}
</script>

<template>
  <!-- Editing mode: show WorkflowEditor full-screen -->
  <div v-if="editingId" style="width: 100%; height: 100vh">
    <WorkflowEditor
      :workflowId="editingId"
      :workflowName="editingName"
      :initialNodes="editingNodes"
      :initialEdges="editingEdges"
      :onSave="handleSave"
      :onRun="handleRun"
      :isRunning="isRunning"
      :currentNodeId="currentNodeId"
      :onBack="handleBack"
    />
    <!-- Run result floating panel (createPortal → teleport) -->
    <Teleport to="body">
      <div
        v-if="runResult"
        @click="runResult = null"
        style="
          position: fixed;
          bottom: 16px;
          left: 50%;
          transform: translateX(-50%);
          background: var(--color-surface);
          border: 1px solid var(--color-border);
          border-radius: 8px;
          padding: 16px;
          max-width: 720px;
          max-height: 240px;
          overflow: auto;
          box-shadow: 0 4px 16px rgba(0,0,0,0.15);
          font-size: 12px;
          font-family: monospace;
          color: var(--color-text-primary);
          white-space: pre-wrap;
          z-index: 50;
        "
      >
        <strong>运行结果 (点击关闭):</strong>
        <pre style="margin: 8px 0 0; font-size: 11px">{{ runResult }}</pre>
      </div>
    </Teleport>
  </div>

  <!-- List mode: workflows + mode library -->
  <div
    v-else
    style="
      max-width: 960px;
      margin: 0 auto;
      padding: 40px 20px;
      color: var(--color-text-primary);
      height: 100%;
      overflow-y: auto;
    "
  >
    <!-- Header -->
    <div
      style="
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 24px;
      "
    >
      <h1 style="font-size: 24px; font-weight: 700; margin: 0">工作流</h1>
      <button
        @click="handleNew"
        style="
          padding: 8px 16px;
          background: var(--color-brand);
          color: #fff;
          border: none;
          border-radius: 4px;
          cursor: pointer;
          font-weight: 600;
          font-size: 14px;
          opacity: nodeTypes.length === 0 ? 0.7 : 1;
        "
      >
        + 新建工作流
      </button>
    </div>

    <!-- Loading state -->
    <div v-if="loading" style="color: var(--color-text-secondary)">加载中…</div>

    <!-- Empty state -->
    <div
      v-else-if="workflows.length === 0"
      style="
        padding: 40px 20px;
        text-align: center;
        color: var(--color-text-secondary);
        background: var(--color-surface-container-low);
        border-radius: 8px;
      "
    >
      还没有工作流。点"新建工作流"创建一个。
    </div>

    <!-- Workflows grid -->
    <div
      v-else
      style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px"
    >
      <div
        v-for="wf in workflows"
        :key="wf.id"
        @click="handleEdit(wf)"
        style="
          background: var(--color-surface);
          border: 1px solid var(--color-border);
          border-radius: 8px;
          padding: 16px;
          cursor: pointer;
        "
      >
        <div style="font-size: 15px; font-weight: 600; margin-bottom: 4px">{{ wf.name }}</div>
        <div
          style="font-size: 12px; color: var(--color-text-tertiary); margin-bottom: 12px"
        >
          {{ wf.description || '无描述' }} · {{ wf.nodes.length }} 节点 · v{{ wf.version }}
        </div>
        <div style="display: flex; gap: 8px">
          <button
            @click.stop="handleEdit(wf)"
            style="
              padding: 4px 10px;
              background: var(--color-surface-container-high);
              border: 1px solid var(--color-border);
              border-radius: 4px;
              color: var(--color-text-primary);
              cursor: pointer;
              font-size: 12px;
            "
          >
            编辑
          </button>
          <button
            @click.stop="handleDelete(wf.id)"
            style="
              padding: 4px 10px;
              background: transparent;
              border: 1px solid #ef4444;
              color: #ef4444;
              border-radius: 4px;
              cursor: pointer;
              font-size: 12px;
            "
          >
            删除
          </button>
        </div>
      </div>
    </div>

    <!-- Mode library -->
    <h2 style="font-size: 18px; font-weight: 700; margin: 32px 0 16px">模式库</h2>
    <div
      style="display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px"
    >
      <div
        v-for="mode in modes"
        :key="mode.id"
        style="
          background: var(--color-surface);
          border: 1px solid var(--color-border);
          border-radius: 8px;
          padding: 14px;
        "
      >
        <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 6px">
          <span
            style="font-size: 18px; font-weight: 600; color: var(--color-brand)"
            v-text="
              mode.id === 'single_agent'
                ? '1'
                : mode.id === 'sequential'
                  ? '→'
                  : mode.id === 'parallel'
                    ? '∥'
                    : mode.id === 'loop'
                      ? '↻'
                      : mode.id === 'review_critique'
                        ? '✓'
                        : mode.id === 'iterative_refine'
                          ? '↑'
                          : mode.id === 'coordinator'
                            ? '◎'
                            : mode.id === 'hierarchical'
                              ? '⊞'
                              : mode.id === 'swarm'
                                ? '∞'
                                : mode.id === 'react'
                                  ? '◉'
                                  : mode.id === 'human_in_loop'
                                    ? '◎'
                                    : '⚙'
            "
          ></span>
          <span style="font-size: 14px; font-weight: 600">{{ mode.name }}</span>
        </div>
        <div
          style="
            font-size: 12px;
            color: var(--color-text-tertiary);
            margin-bottom: 10px;
            line-height: 1.4;
          "
        >
          {{ mode.description }}
        </div>
        <div
          style="font-size: 11px; color: var(--color-text-disabled); margin-bottom: 8px"
        >
          {{ mode.node_count }} 节点 ·
          {{
            mode.category === 'basic'
              ? '基础'
              : mode.category === 'multi_agent'
                ? '多 Agent'
                : '高级'
          }}
        </div>
        <button
          @click="
            async () => {
              try {
                const r = await fetch(
                  getApiUrl(`/api/workflows/modes/${mode.id}/instantiate`),
                  { method: 'POST' }
                )
                if (r.ok) {
                  const wf = await r.json()
                  handleEdit(wf)
                  await refresh()
                }
              } catch {}
            }
          "
          style="
            padding: 4px 12px;
            background: var(--color-brand);
            color: #fff;
            border: none;
            border-radius: 4px;
            cursor: pointer;
            font-size: 12px;
            font-weight: 600;
          "
        >
          使用此模式
        </button>
      </div>
    </div>
  </div>
</template>