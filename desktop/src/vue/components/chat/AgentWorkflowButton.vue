<script setup lang="ts">
/**
 * AgentWorkflowButton — chat composer button to invoke a saved workflow.
 *
 * Click → list of saved workflows (fetched from /api/workflows) → pick one
 * → runs it via /api/workflows/{id}/run with current input as workflow input
 * → emits the result as a chat message.
 */

import { ref, onMounted } from 'vue'

interface Workflow {
  id: string
  name: string
  description: string
  nodes: any[]
  edges: any[]
}

const emit = defineEmits<{
  invoke: [workflowId: string, workflowName: string, userInput: string]
}>()

const props = defineProps<{
  currentInput: string
}>()

const open = ref(false)
const workflows = ref<Workflow[]>([])
const loading = ref(false)
const running = ref<string | null>(null)
const error = ref<string | null>(null)

async function loadWorkflows() {
  loading.value = true
  try {
    const res = await fetch('/api/workflows')
    if (res.ok) {
      const data = await res.json()
      workflows.value = data.workflows || []
    }
  } catch {
    // ignore
  } finally {
    loading.value = false
  }
}

async function runWorkflow(wf: Workflow) {
  if (!props.currentInput.trim()) {
    error.value = '请先在输入框中输入消息'
    return
  }
  running.value = wf.id
  error.value = null
  try {
    const res = await fetch(`/api/workflows/${wf.id}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input: { input: props.currentInput } }),
    })
    if (!res.ok) {
      const t = await res.text().catch(() => '')
      error.value = `运行失败: ${res.status} ${t}`
      return
    }
    const result = await res.json()
    // Extract the final output from the run result
    let finalOutput = ''
    if (result.outputs) {
      const endNodeId = result.end_node_id || 'end-1'
      finalOutput = result.outputs[endNodeId] || JSON.stringify(result.outputs, null, 2)
    } else if (result.output) {
      finalOutput = typeof result.output === 'string' ? result.output : JSON.stringify(result.output, null, 2)
    } else {
      finalOutput = JSON.stringify(result, null, 2)
    }
    // Emit the result as a chat message via the parent
    emit('invoke', wf.id, wf.name, finalOutput)
    open.value = false
  } catch (e) {
    error.value = `网络错误: ${String(e)}`
  } finally {
    running.value = null
  }
}

function toggle() {
  if (!open.value) loadWorkflows()
  open.value = !open.value
}

onMounted(loadWorkflows)
</script>

<template>
  <div style="position: relative;">
    <!-- Trigger button -->
    <button
      type="button"
      class="agent-btn"
      :class="{ 'agent-btn--active': open }"
      title="调用保存的工作流"
      @click="toggle"
    >
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </svg>
      <span>Agent</span>
    </button>

    <!-- Picker popover -->
    <div
      v-if="open"
      class="agent-picker"
    >
      <div class="agent-picker__title">
        选择工作流
        <button @click="loadWorkflows" class="agent-picker__refresh" title="刷新"><span class="material-symbols-outlined text-[15px]">refresh</span></button>
      </div>

      <div v-if="loading" class="agent-picker__loading">加载中…</div>

      <div v-else-if="workflows.length === 0" class="agent-picker__empty">
        <div>还没有工作流</div>
        <div style="font-size: 11px; margin-top: 4px; opacity: 0.7;">
          去「工作流」页创建一个
        </div>
      </div>

      <div v-else class="agent-picker__list">
        <button
          v-for="wf in workflows"
          :key="wf.id"
          :disabled="running === wf.id"
          :class="['agent-picker__item', { 'agent-picker__item--running': running === wf.id }]"
          @click="runWorkflow(wf)"
        >
          <div class="agent-picker__item-name">
            <span v-if="running === wf.id" class="material-symbols-outlined text-[14px] animate-spin text-[var(--color-primary)]">progress_activity</span>
            {{ wf.name || '未命名' }}
          </div>
          <div class="agent-picker__item-meta">
            {{ wf.nodes?.length || 0 }} 节点 ·
            <span v-if="wf.description">{{ wf.description.slice(0, 40) }}</span>
            <span v-else>点击运行</span>
          </div>
        </button>
      </div>

      <div v-if="error" class="agent-picker__error">{{ error }}</div>
    </div>
  </div>
</template>

<style scoped>
.agent-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-secondary);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s;
}
.agent-btn:hover {
  background: var(--color-surface-container);
  border-color: var(--color-border-focus);
  color: var(--color-text-primary);
}
.agent-btn--active {
  background: var(--color-brand);
  color: white;
  border-color: var(--color-brand);
}

.agent-picker {
  position: absolute;
  bottom: calc(100% + 8px);
  left: 0;
  width: 280px;
  max-height: 320px;
  overflow-y: auto;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);
  z-index: 100;
  padding: 8px;
}

.agent-picker__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--color-text-tertiary);
  padding: 4px 6px 8px;
  border-bottom: 1px solid var(--color-border-separator);
  margin-bottom: 6px;
}
.agent-picker__refresh {
  background: none;
  border: none;
  color: var(--color-text-tertiary);
  cursor: pointer;
  font-size: 14px;
  padding: 2px 4px;
}
.agent-picker__refresh:hover { color: var(--color-text-primary); }

.agent-picker__loading,
.agent-picker__empty {
  text-align: center;
  padding: 24px 12px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}

.agent-picker__list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-picker__item {
  text-align: left;
  padding: 8px 10px;
  background: var(--color-surface-container-lowest);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}
.agent-picker__item:hover {
  background: var(--color-surface-container);
  border-color: var(--color-brand);
}
.agent-picker__item--running {
  opacity: 0.6;
  cursor: wait;
}
.agent-picker__item-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: 4px;
}
.agent-picker__item-spinner {
  color: var(--color-brand);
  animation: spin 1s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.agent-picker__item-meta {
  font-size: 10px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
}

.agent-picker__error {
  margin-top: 8px;
  padding: 6px 8px;
  font-size: 11px;
  color: var(--color-error);
  background: color-mix(in srgb, var(--color-error) 10%, transparent);
  border-radius: 4px;
}
</style>
