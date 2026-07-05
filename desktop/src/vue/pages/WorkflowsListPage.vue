<script setup lang="ts">
import { ref, onMounted } from 'vue'

/**
 * WorkflowsListPage — Vue 3 port of pages/WorkflowsListPage.tsx
 * Displays a list of saved workflows with create/edit/delete actions.
 * Props-driven: workflows passed from parent (or mock data for demo).
 */

interface Workflow {
  id: string
  name: string
  description: string
  nodes: { id: string; type: string }[]
  edges: { id: string; source: string; target: string }[]
  version: string
}

interface AgentMode {
  id: string
  name: string
  description: string
  category: string
  icon: string
  node_count: number
}

interface WorkflowsListPageProps {
  workflows?: Workflow[]
  modes?: AgentMode[]
  /** If true, fetches from API (optional). Otherwise uses mock data. */
  live?: boolean
}

const props = withDefaults(defineProps<WorkflowsListPageProps>(), {
  workflows: () => [
    { id: '1', name: '文档翻译流水线', description: '自动翻译文档并回写', nodes: [{ id: 'start', type: 'start' }, { id: 'llm', type: 'llm' }, { id: 'end', type: 'end' }], edges: [], version: '1.0' },
    { id: '2', name: '代码审查助手', description: 'Pull Request 自动审查', nodes: [{ id: 'start', type: 'start' }, { id: 'llm', type: 'llm' }], edges: [], version: '1.2' },
    { id: '3', name: '数据提取管道', description: '从网页提取结构化数据', nodes: [{ id: 'start', type: 'start' }], edges: [], version: '0.5' },
  ],
  modes: () => [
    { id: 'researcher', name: '研究者模式', description: '联网搜索 + 推理整合', category: '智能体', icon: 'science', node_count: 8 },
    { id: 'coder', name: '程序员模式', description: '代码生成 + 测试执行', category: '智能体', icon: 'code', node_count: 6 },
    { id: 'writer', name: '写作者模式', description: '长文写作 + 编辑协作', category: '智能体', icon: 'edit_note', node_count: 5 },
    { id: 'qa', name: '测试工程师模式', description: '用例生成 + 自动化测试', category: '智能体', icon: 'bug_report', node_count: 7 },
  ],
  live: false,
})

const loading = ref(true)
const showConfirmDelete = ref(false)
const deletingWorkflow = ref<Workflow | null>(null)

onMounted(() => {
  if (props.live) {
    // Would fetch from API here
  }
  setTimeout(() => loading.value = false, 200)
})

const emit = defineEmits<{
  edit: [workflow: Workflow]
  delete: [workflowId: string]
  create: []
}>()

function handleDelete(wf: Workflow) {
  deletingWorkflow.value = wf
  showConfirmDelete.value = true
}

function confirmDelete() {
  if (deletingWorkflow.value) {
    emit('delete', deletingWorkflow.value.id)
    showConfirmDelete.value = false
    deletingWorkflow.value = null
  }
}
</script>

<template>
  <div class="flex flex-col min-h-0 bg-[var(--color-surface)]">
    <!-- Header -->
    <div class="flex items-center justify-between px-6 py-4 border-b border-[var(--color-border)]">
      <div class="flex items-center gap-3">
        <span class="material-symbols-outlined text-[var(--color-brand)] text-xl">flowchart</span>
        <h1 class="text-lg font-bold text-[var(--color-text-primary)]" style="font-family: var(--font-headline)">工作流</h1>
      </div>
      <button @click="emit('create')"
        class="flex items-center gap-2 px-4 py-2 bg-[image:var(--gradient-btn-primary)] text-[var(--color-btn-primary-fg)] rounded-lg text-sm font-semibold shadow-sm hover:brightness-105 active:scale-95 transition-all">
        <span class="material-symbols-outlined text-sm" style="fontVariationSettings: 'FILL' 1">add</span>
        新建工作流
      </button>
    </div>

    <div class="flex-1 overflow-y-auto p-6">
      <!-- Loading -->
      <div v-if="loading" class="flex items-center justify-center py-12">
        <span class="material-symbols-outlined text-[var(--color-brand)] animate-spin text-2xl">progress_activity</span>
      </div>

      <!-- Empty state -->
      <div v-else-if="props.workflows.length === 0" class="flex flex-col items-center py-12 text-center">
        <div class="p-4 rounded-2xl bg-[var(--color-surface-container)] mb-4">
          <span class="material-symbols-outlined text-[var(--color-text-tertiary)] text-4xl">flowchart</span>
        </div>
        <p class="text-sm text-[var(--color-text-secondary)] mb-4">还没有工作流</p>
        <button @click="emit('create')"
          class="px-4 py-2 bg-[var(--color-brand)] text-[var(--color-on-brand)] rounded-lg text-sm font-semibold hover:brightness-105">
          创建第一个工作流
        </button>
      </div>

      <!-- Workflows grid -->
      <div v-else class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-8">
        <div v-for="wf in props.workflows" :key="wf.id"
          @click="emit('edit', wf)"
          class="cursor-pointer rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)] p-4 hover:border-[var(--color-brand)]/50 transition-colors">
          <div class="flex items-start justify-between mb-2">
            <div class="w-8 h-8 rounded-lg bg-[var(--color-primary-container)] flex items-center justify-center">
              <span class="material-symbols-outlined text-[var(--color-primary)] text-sm">flowchart</span>
            </div>
            <div class="flex gap-1">
              <button @click.stop="emit('edit', wf)" class="p-1.5 hover:bg-[var(--color-surface-hover)] rounded text-[var(--color-text-tertiary)] hover:text-[var(--color-brand)]">
                <span class="material-symbols-outlined text-sm">edit</span>
              </button>
              <button @click.stop="handleDelete(wf)" class="p-1.5 hover:bg-[var(--color-surface-hover)] rounded text-[var(--color-text-tertiary)] hover:text-[var(--color-error)]">
                <span class="material-symbols-outlined text-sm">delete</span>
              </button>
            </div>
          </div>
          <h3 class="text-sm font-semibold text-[var(--color-text-primary)] truncate">{{ wf.name }}</h3>
          <p class="text-[11px] text-[var(--color-text-tertiary)] mt-1 line-clamp-2">{{ wf.description || '无描述' }}</p>
          <div class="flex items-center gap-2 mt-3 text-[10px] text-[var(--color-text-tertiary)]">
            <span class="px-1.5 py-0.5 bg-[var(--color-surface-container-high)] rounded">{{ wf.nodes.length }} 节点</span>
            <span>v{{ wf.version }}</span>
          </div>
        </div>
      </div>

      <!-- Agent Modes -->
      <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-3 flex items-center gap-2">
        <span class="material-symbols-outlined text-[var(--color-tertiary)] text-lg">smart_toy</span>
        模式库
      </h2>
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        <div v-for="mode in props.modes" :key="mode.id"
          class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)] p-3 hover:border-[var(--color-brand)]/50 transition-colors cursor-pointer">
          <div class="flex items-center gap-2 mb-1">
            <span :class="['material-symbols-outlined text-lg', mode.icon]">{{ mode.icon || 'smart_toy' }}</span>
            <span class="text-xs font-semibold text-[var(--color-text-primary)] truncate">{{ mode.name }}</span>
          </div>
          <p class="text-[10px] text-[var(--color-text-tertiary)] line-clamp-2">{{ mode.description }}</p>
          <div class="flex items-center justify-between mt-2 text-[9px] text-[var(--color-text-tertiary)]">
            <span class="px-1.5 py-0.5 bg-[var(--color-secondary-container)] rounded">{{ mode.category }}</span>
            <span>{{ mode.node_count }} 节点</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Delete confirm dialog (simple inline) -->
    <Teleport to="body">
      <div v-if="showConfirmDelete" class="fixed inset-0 z-50 flex items-center justify-center">
        <div class="fixed inset-0 bg-black/50" @click="showConfirmDelete = false" />
        <div class="relative z-10 bg-[var(--color-surface)] rounded-xl border border-[var(--color-border)] p-5 max-w-sm mx-4 shadow-xl">
          <p class="text-sm text-[var(--color-text-primary)] mb-4">确定删除「{{ deletingWorkflow?.name }}」吗？</p>
          <div class="flex justify-end gap-2">
            <button @click="showConfirmDelete = false" class="px-3 py-1.5 text-xs text-[var(--color-text-secondary)] hover:underline">取消</button>
            <button @click="confirmDelete" class="px-3 py-1.5 bg-[var(--color-error)] text-[var(--color-on-error)] rounded text-xs font-semibold">删除</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
