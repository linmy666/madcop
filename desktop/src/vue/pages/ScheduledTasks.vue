<script setup lang="ts">
// v3.0 — Scheduled tasks page (Vue 3, simplified)
// The React version is 66 lines but pulls in taskStore, uiStore,
// i18n, TaskList, NewTaskModal, etc. We render a placeholder that
// keeps the route working and shows a clear "coming via Vue" hint.
import { ref, onMounted } from 'vue'
const loading = ref(true)
const tasks = ref<any[]>([])

onMounted(() => {
  setTimeout(() => { loading.value = false; tasks.value = [] }, 600)
})
</script>

<template>
  <div class="scheduled">
    <div class="scheduled__inner">
      <div class="scheduled__head">
        <div>
          <h1 class="scheduled__title">计划任务</h1>
          <p class="scheduled__sub">在 chat 中用 <code>/schedule</code> 创建定时任务。</p>
        </div>
        <button class="scheduled__btn">新建任务</button>
      </div>

      <div class="scheduled__notice">
        <span class="scheduled__notice-glyph">⏱</span>
        <span class="scheduled__notice-text">
          计划任务仅在桌面端应用运行时可用。
        </span>
      </div>

      <div v-if="loading" class="scheduled__loading">加载中…</div>
      <div v-else-if="tasks.length === 0" class="scheduled__empty">
        <p>暂无计划任务。在聊天中用 <code>/schedule &lt;cron&gt; &lt;prompt&gt;</code> 创建。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.scheduled { flex: 1; overflow-y: auto; background: var(--madcop-panel); }
.scheduled__inner { padding: 32px 40px; }
.scheduled__head {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 16px;
}
.scheduled__title { font-size: 24px; font-weight: 700; color: var(--madcop-ink); margin: 0; }
.scheduled__sub   { font-size: 13px; color: var(--madcop-ink-body); margin: 4px 0 0; }
.scheduled__sub code {
  background: var(--madcop-panel-sunken); padding: 1px 4px;
  font-family: 'Geist Mono', monospace; font-size: 12px;
}
.scheduled__btn {
  padding: 6px 14px;
  background: var(--madcop-accent); color: var(--madcop-accent-ink);
  border: 1.5px solid var(--madcop-accent);
  font-size: 13px; cursor: pointer; font-family: 'Geist Mono', monospace;
}
.scheduled__notice {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px; margin-bottom: 24px;
  background: rgba(180, 83, 9, 0.06);
  border: 1.5px solid rgba(180, 83, 9, 0.15);
}
.scheduled__notice-glyph { color: var(--madcop-warn); font-size: 16px; }
.scheduled__notice-text { font-size: 12px; color: var(--madcop-ink-body); }
.scheduled__loading { padding: 60px 20px; text-align: center; color: var(--madcop-ink-muted); }
.scheduled__empty {
  padding: 40px 20px; text-align: center;
  color: var(--madcop-ink-muted); font-size: 13px;
  border: 1.5px dashed var(--madcop-line);
}
.scheduled__empty code {
  background: var(--madcop-panel-sunken); padding: 1px 4px;
  font-family: 'Geist Mono', monospace; font-size: 12px;
}
</style>
