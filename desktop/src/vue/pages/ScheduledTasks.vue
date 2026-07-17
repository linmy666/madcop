<script setup lang="ts">
/**
 * Scheduled tasks — wired to taskStore → /api/scheduled-tasks.
 */
import { ref, onMounted, computed } from 'vue'
import { useTaskStore } from '../stores/taskStore'
import { useUIStore } from '../stores/uiStore'

const taskStore = useTaskStore()
const uiStore = useUIStore()

const showCreate = ref(false)
const creating = ref(false)
const runningId = ref<string | null>(null)
const draft = ref({
  name: '',
  cron: '0 9 * * *',
  prompt: '',
})

const tasks = computed(() => taskStore.tasks)
const loading = computed(() => taskStore.isLoading)
const recentRuns = computed(() => taskStore.recentRuns.slice(0, 8))

onMounted(async () => {
  await Promise.all([taskStore.fetchTasks(), taskStore.fetchRecentRuns()])
})

async function createTask() {
  if (!draft.value.name.trim() || !draft.value.prompt.trim()) {
    uiStore.addToast({ type: 'error', message: '请填写名称与 Prompt' })
    return
  }
  creating.value = true
  try {
    await taskStore.createTask({
      name: draft.value.name.trim(),
      cron: draft.value.cron.trim() || '0 9 * * *',
      prompt: draft.value.prompt.trim(),
      enabled: true,
    })
    uiStore.addToast({ type: 'success', message: '任务已创建' })
    draft.value = { name: '', cron: '0 9 * * *', prompt: '' }
    showCreate.value = false
  } catch (e) {
    uiStore.addToast({
      type: 'error',
      message: e instanceof Error ? e.message : '创建失败',
    })
  } finally {
    creating.value = false
  }
}

async function runTask(id: string) {
  runningId.value = id
  try {
    await taskStore.runTask(id)
    await taskStore.fetchRecentRuns()
    uiStore.addToast({ type: 'success', message: '已触发运行' })
  } catch (e) {
    uiStore.addToast({
      type: 'error',
      message: e instanceof Error ? e.message : '运行失败',
    })
  } finally {
    runningId.value = null
  }
}

async function toggleEnabled(id: string, enabled: boolean) {
  await taskStore.updateTask(id, { enabled })
}

async function removeTask(id: string) {
  await taskStore.deleteTask(id)
  uiStore.addToast({ type: 'info', message: '已删除任务' })
}
</script>

<template>
  <div class="scheduled">
    <div class="scheduled__inner">
      <div class="scheduled__head">
        <div>
          <h1 class="scheduled__title">计划任务</h1>
          <p class="scheduled__sub">
            管理定时 Prompt。也可用聊天命令
            <code>/schedule &lt;cron&gt; &lt;prompt&gt;</code> 创建。
          </p>
        </div>
        <button class="scheduled__btn" type="button" @click="showCreate = !showCreate">
          {{ showCreate ? '取消' : '新建任务' }}
        </button>
      </div>

      <div class="scheduled__notice">
        <span class="scheduled__notice-glyph">⏱</span>
        <span class="scheduled__notice-text">
          计划任务在桌面端后端运行时可用；任务与运行记录保存在
          <code>~/.madcop/scheduled_tasks.json</code>。
        </span>
      </div>

      <div v-if="showCreate" class="scheduled__form">
        <label>
          <span>名称</span>
          <input v-model="draft.name" placeholder="例如：每日站会摘要" />
        </label>
        <label>
          <span>Cron</span>
          <input v-model="draft.cron" placeholder="0 9 * * *" class="mono" />
        </label>
        <label class="full">
          <span>Prompt</span>
          <textarea v-model="draft.prompt" rows="3" placeholder="要执行的指令…" />
        </label>
        <div class="scheduled__form-actions">
          <button type="button" class="scheduled__btn" :disabled="creating" @click="createTask">
            {{ creating ? '创建中…' : '保存' }}
          </button>
        </div>
      </div>

      <div v-if="loading" class="scheduled__loading">加载中…</div>

      <div v-else-if="tasks.length === 0" class="scheduled__empty">
        <p>暂无计划任务。点「新建任务」或在聊天中用 <code>/schedule</code> 创建。</p>
      </div>

      <ul v-else class="scheduled__list">
        <li v-for="t in tasks" :key="t.id" class="scheduled__item">
          <div class="scheduled__item-main">
            <div class="scheduled__item-title">
              <span class="name">{{ t.name }}</span>
              <span class="cron mono">{{ t.cron }}</span>
              <span :class="['badge', t.enabled ? 'on' : 'off']">
                {{ t.enabled ? '启用' : '停用' }}
              </span>
            </div>
            <p class="prompt">{{ t.prompt }}</p>
          </div>
          <div class="scheduled__item-actions">
            <button type="button" class="ghost" @click="toggleEnabled(t.id, !t.enabled)">
              {{ t.enabled ? '停用' : '启用' }}
            </button>
            <button
              type="button"
              class="ghost"
              :disabled="runningId === t.id"
              @click="runTask(t.id)"
            >
              {{ runningId === t.id ? '运行中…' : '立即运行' }}
            </button>
            <button type="button" class="ghost danger" @click="removeTask(t.id)">删除</button>
          </div>
        </li>
      </ul>

      <section v-if="recentRuns.length" class="scheduled__runs">
        <h2>最近运行</h2>
        <ul>
          <li v-for="r in recentRuns" :key="r.id">
            <span class="mono">{{ r.status }}</span>
            <span>{{ r.taskName || r.taskId }}</span>
            <span class="muted">{{ r.startedAt }}</span>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>

<style scoped>
.scheduled { flex: 1; overflow-y: auto; background: var(--color-surface, var(--madcop-panel)); }
.scheduled__inner { padding: 32px 40px; max-width: 880px; }
.scheduled__head {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px; gap: 12px;
}
.scheduled__title { font-size: 24px; font-weight: 700; color: var(--color-text-primary, var(--madcop-ink)); margin: 0; }
.scheduled__sub   { font-size: 13px; color: var(--color-text-secondary, var(--madcop-ink-body)); margin: 4px 0 0; }
.scheduled__sub code, .scheduled__notice-text code, .scheduled__empty code, .mono {
  background: var(--color-surface-container-low, var(--madcop-panel-sunken)); padding: 1px 4px;
  font-family: ui-monospace, 'Geist Mono', monospace; font-size: 12px;
}
.scheduled__btn {
  padding: 6px 14px;
  background: var(--color-brand, var(--madcop-accent)); color: #fff;
  border: 1px solid transparent;
  border-radius: 8px;
  font-size: 13px; cursor: pointer;
}
.scheduled__btn:disabled { opacity: 0.6; cursor: wait; }
.scheduled__notice {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; margin-bottom: 20px;
  background: rgba(180, 83, 9, 0.06);
  border: 1px solid rgba(180, 83, 9, 0.15);
  border-radius: 10px;
}
.scheduled__notice-glyph { color: var(--color-warning, #b45309); font-size: 16px; }
.scheduled__notice-text { font-size: 12px; color: var(--color-text-secondary); }
.scheduled__loading { padding: 60px 20px; text-align: center; color: var(--color-text-tertiary); }
.scheduled__empty {
  padding: 40px 20px; text-align: center;
  color: var(--color-text-tertiary); font-size: 13px;
  border: 1.5px dashed var(--color-border);
  border-radius: 12px;
}
.scheduled__form {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 20px;
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface-container-low);
}
.scheduled__form label { display: flex; flex-direction: column; gap: 6px; font-size: 12px; color: var(--color-text-secondary); }
.scheduled__form label.full { grid-column: 1 / -1; }
.scheduled__form input, .scheduled__form textarea {
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 8px 10px;
  background: var(--color-surface);
  color: var(--color-text-primary);
  font-size: 13px;
}
.scheduled__form-actions { grid-column: 1 / -1; display: flex; justify-content: flex-end; }
.scheduled__list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 10px; }
.scheduled__item {
  display: flex; justify-content: space-between; gap: 12px; align-items: flex-start;
  padding: 14px 16px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
}
.scheduled__item-title { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 6px; }
.scheduled__item-title .name { font-weight: 600; color: var(--color-text-primary); }
.scheduled__item-title .prompt, .prompt {
  margin: 0; font-size: 13px; color: var(--color-text-secondary);
  white-space: pre-wrap; word-break: break-word;
}
.badge { font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--color-border); }
.badge.on { color: var(--color-success, #059669); }
.badge.off { color: var(--color-text-tertiary); }
.scheduled__item-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.ghost {
  border: 1px solid var(--color-border);
  background: transparent;
  border-radius: 8px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  color: var(--color-text-secondary);
}
.ghost:hover { color: var(--color-text-primary); background: var(--color-surface-hover, rgba(0,0,0,0.03)); }
.ghost.danger { color: var(--color-error, #dc2626); }
.scheduled__runs { margin-top: 28px; }
.scheduled__runs h2 { font-size: 14px; margin: 0 0 10px; color: var(--color-text-primary); }
.scheduled__runs ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.scheduled__runs li {
  display: flex; gap: 12px; font-size: 12px; color: var(--color-text-secondary);
  padding: 8px 10px; border-radius: 8px; background: var(--color-surface-container-low);
}
.muted { color: var(--color-text-tertiary); }
</style>
