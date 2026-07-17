<script setup lang="ts">
/**
 * Meta-Harness settings — view active harness, archive candidates, promote, run offline search.
 */
import { ref, onMounted, computed } from 'vue'
import { getApiUrl } from '../../api/client'
import { useUIStore } from '../../stores/uiStore'

const ui = useUIStore()
const loading = ref(false)
const running = ref(false)
const error = ref<string | null>(null)
const active = ref<Record<string, any> | null>(null)
const best = ref<Record<string, any> | null>(null)
const candidates = ref<Array<Record<string, any>>>([])
const archiveCount = ref(0)
const lastRun = ref<Record<string, any> | null>(null)

const iterations = ref(2)
const suite = ref('smoke')
const proposer = ref('code_edit')

const activeSummary = computed(() => {
  if (!active.value) return []
  const a = active.value
  return [
    `memory: ${a.profile_budget}/${a.relevant_budget}/${a.preferences_budget}`,
    `skills: ${a.inject_skills ? a.max_skills : 'off'}`,
    `tools: ${a.enable_tools ? `max ${a.max_tools}` : 'off'}`,
    `deep=${a.enable_deep_mode} plan=${a.enable_plan_mode} compact=${a.enable_context_compact}@${a.compact_threshold_messages}`,
  ]
})

async function loadStatus() {
  loading.value = true
  error.value = null
  try {
    const [st, cand] = await Promise.all([
      fetch(getApiUrl('/api/meta-harness/status')).then((r) => r.json()),
      fetch(getApiUrl('/api/meta-harness/candidates')).then((r) => r.json()),
    ])
    active.value = st.active || null
    best.value = st.archive_best || null
    archiveCount.value = st.archive_count ?? 0
    candidates.value = Array.isArray(cand.candidates) ? cand.candidates.slice().reverse() : []
  } catch (e: any) {
    error.value = e?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

async function promote(id?: string) {
  try {
    const res = await fetch(getApiUrl('/api/meta-harness/promote'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(id ? { id } : {}),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
    active.value = data.active
    ui.addToast({ type: 'success', message: '已 promote 为当前任务 harness' })
    await loadStatus()
  } catch (e: any) {
    ui.addToast({ type: 'error', message: e?.message || 'promote 失败' })
  }
}

async function runSearch() {
  running.value = true
  try {
    const res = await fetch(getApiUrl('/api/meta-harness/run'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        iterations: iterations.value,
        suite: suite.value,
        proposer: proposer.value,
        promote: false,
      }),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
    lastRun.value = data
    ui.addToast({
      type: 'success',
      message: `搜索完成 pass_rate=${(data.best_pass_rate ?? 0).toFixed(2)}`,
    })
    await loadStatus()
  } catch (e: any) {
    ui.addToast({ type: 'error', message: e?.message || '搜索失败' })
  } finally {
    running.value = false
  }
}

onMounted(loadStatus)
</script>

<template>
  <div class="mh">
    <div class="mh__head">
      <div>
        <h2 class="text-[18px] font-semibold tracking-tight">任务外壳 (Meta-Harness)</h2>
        <p class="sub">
          优化任务外壳（记忆/技能/工具/deep·plan 开关），不是供应商 API 适配。
          档案目录 <code>~/.madcop/meta_harness/</code>
        </p>
      </div>
      <button type="button" class="btn" :disabled="loading" @click="loadStatus">
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
    </div>

    <p v-if="error" class="err">{{ error }}</p>

    <section class="card">
      <h3>当前生效 (active)</h3>
      <ul class="summary">
        <li v-for="(s, i) in activeSummary" :key="i">{{ s }}</li>
      </ul>
      <pre v-if="active" class="json">{{ JSON.stringify(active, null, 2) }}</pre>
    </section>

    <section class="card">
      <h3>离线搜索</h3>
      <div class="row">
        <label>
          iterations
          <input v-model.number="iterations" type="number" min="1" max="10" />
        </label>
        <label>
          suite
          <select v-model="suite">
            <option value="smoke">smoke</option>
            <option value="full">full</option>
          </select>
        </label>
        <label>
          proposer
          <select v-model="proposer">
            <option value="local">local</option>
            <option value="code_edit">code_edit</option>
            <option value="mock">mock</option>
          </select>
        </label>
        <button type="button" class="btn primary" :disabled="running" @click="runSearch">
          {{ running ? '搜索中…' : '运行搜索' }}
        </button>
      </div>
      <pre v-if="lastRun" class="json">{{ JSON.stringify(lastRun, null, 2) }}</pre>
    </section>

    <section class="card">
      <div class="card__title">
        <h3>档案候选 ({{ archiveCount }})</h3>
        <button type="button" class="btn" @click="promote()">Promote 最优</button>
      </div>
      <p v-if="best" class="muted">
        best: {{ best.id }} · pass_rate={{ best.pass_rate }}
      </p>
      <ul class="list">
        <li v-for="c in candidates" :key="c.id" class="list__item">
          <div>
            <strong>{{ c.id }}</strong>
            <span class="muted"> pass={{ c.pass_rate }} parent={{ c.parent_id || '—' }}</span>
          </div>
          <button type="button" class="btn sm" @click="promote(c.id)">Promote</button>
        </li>
      </ul>
      <p v-if="!candidates.length" class="muted">暂无候选。先跑一次搜索。</p>
    </section>
  </div>
</template>

<style scoped>
.mh { max-width: 820px; }
.mh__head { display: flex; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
.mh__head h2 { margin: 0; font-size: 18px; font-weight: 700; color: var(--color-text-primary); }
.sub { margin: 4px 0 0; font-size: 13px; color: var(--color-text-secondary); line-height: 1.45; }
.sub code { font-size: 12px; }
.err { color: var(--color-error); font-size: 13px; }
.card {
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 14px 16px;
  margin-bottom: 14px;
  background: var(--color-surface);
}
.card h3 { margin: 0 0 10px; font-size: 14px; color: var(--color-text-primary); }
.card__title { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.card__title h3 { margin: 0; }
.summary { margin: 0 0 8px; padding-left: 18px; font-size: 12px; color: var(--color-text-secondary); }
.json {
  margin: 0; padding: 10px; border-radius: 8px; font-size: 11px;
  background: var(--color-surface-container-low); overflow: auto; max-height: 240px;
  color: var(--color-text-primary);
}
.row { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; margin-bottom: 10px; }
.row label { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--color-text-tertiary); }
.row input, .row select {
  border: 1px solid var(--color-border); border-radius: 8px; padding: 6px 8px;
  background: var(--color-surface); color: var(--color-text-primary); font-size: 13px;
}
.btn {
  border: 1px solid var(--color-border); background: var(--color-surface);
  border-radius: 8px; padding: 6px 12px; font-size: 12px; cursor: pointer;
  color: var(--color-text-primary);
}
.btn.primary { background: var(--color-brand); color: #fff; border-color: transparent; }
.btn.sm { padding: 4px 8px; font-size: 11px; }
.btn:disabled { opacity: 0.6; cursor: wait; }
.list { list-style: none; margin: 0; padding: 0; }
.list__item {
  display: flex; justify-content: space-between; align-items: center; gap: 8px;
  padding: 8px 0; border-top: 1px solid var(--color-border); font-size: 12px;
}
.muted { color: var(--color-text-tertiary); font-size: 12px; }
</style>
