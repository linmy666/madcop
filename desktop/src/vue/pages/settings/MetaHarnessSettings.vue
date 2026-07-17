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
const showActiveJson = ref(false)

const iterations = ref(2)
const suite = ref('smoke')
const proposer = ref('code_edit')

const activeSummary = computed(() => {
  if (!active.value) return []
  const a = active.value
  return [
    { label: '记忆预算', value: `${a.profile_budget}/${a.relevant_budget}/${a.preferences_budget}` },
    { label: '技能', value: a.inject_skills ? `最多 ${a.max_skills}` : '关闭' },
    { label: '工具', value: a.enable_tools ? `最多 ${a.max_tools}` : '关闭' },
    { label: '模式', value: `deep=${a.enable_deep_mode} · plan=${a.enable_plan_mode}` },
    { label: '压缩', value: a.enable_context_compact ? `@${a.compact_threshold_messages} 条` : '关闭' },
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
  <div class="mh mx-auto max-w-3xl space-y-5">
    <header class="mh__head">
      <div class="min-w-0">
        <div class="mh__eyebrow">AI</div>
        <h2 class="mh__title">任务外壳 (Meta-Harness)</h2>
        <p class="mh__sub">
          优化任务外壳（记忆 / 技能 / 工具 / deep·plan 开关），不是供应商 API 适配。
          档案目录 <code>~/.madcop/meta_harness/</code>
        </p>
      </div>
      <button type="button" class="mh-btn" :disabled="loading" @click="loadStatus">
        <span class="material-symbols-outlined text-[16px]" :class="{ 'animate-spin': loading }">refresh</span>
        {{ loading ? '刷新中…' : '刷新' }}
      </button>
    </header>

    <p v-if="error" class="mh-err">{{ error }}</p>

    <!-- Active -->
    <section class="mh-card">
      <div class="mh-card__head">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined mh-card__icon">bolt</span>
          <h3>当前生效</h3>
        </div>
        <button
          v-if="active"
          type="button"
          class="mh-btn mh-btn--ghost"
          @click="showActiveJson = !showActiveJson"
        >
          {{ showActiveJson ? '隐藏 JSON' : '查看 JSON' }}
        </button>
      </div>
      <div v-if="activeSummary.length" class="mh-pills">
        <div v-for="(s, i) in activeSummary" :key="i" class="mh-pill">
          <span class="mh-pill__label">{{ s.label }}</span>
          <span class="mh-pill__value">{{ s.value }}</span>
        </div>
      </div>
      <p v-else class="mh-muted px-4 py-3">尚未加载 active harness</p>
      <pre v-if="showActiveJson && active" class="mh-json">{{ JSON.stringify(active, null, 2) }}</pre>
    </section>

    <!-- Offline search -->
    <section class="mh-card">
      <div class="mh-card__head">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined mh-card__icon">science</span>
          <h3>离线搜索</h3>
        </div>
      </div>
      <div class="mh-form">
        <label class="mh-field">
          <span>迭代次数</span>
          <input v-model.number="iterations" type="number" min="1" max="10" />
        </label>
        <label class="mh-field">
          <span>评测套件</span>
          <select v-model="suite">
            <option value="smoke">smoke（快速）</option>
            <option value="full">full（完整）</option>
          </select>
        </label>
        <label class="mh-field">
          <span>提议器</span>
          <select v-model="proposer">
            <option value="local">local</option>
            <option value="code_edit">code_edit</option>
            <option value="mock">mock</option>
          </select>
        </label>
        <button type="button" class="mh-btn mh-btn--primary" :disabled="running" @click="runSearch">
          <span v-if="running" class="material-symbols-outlined animate-spin text-[16px]">progress_activity</span>
          <span v-else class="material-symbols-outlined text-[16px]">play_arrow</span>
          {{ running ? '搜索中…' : '运行搜索' }}
        </button>
      </div>
      <pre v-if="lastRun" class="mh-json">{{ JSON.stringify(lastRun, null, 2) }}</pre>
    </section>

    <!-- Archive -->
    <section class="mh-card">
      <div class="mh-card__head">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined mh-card__icon">inventory_2</span>
          <h3>档案候选</h3>
          <span class="mh-count">{{ archiveCount }}</span>
        </div>
        <button type="button" class="mh-btn mh-btn--primary" @click="promote()">Promote 最优</button>
      </div>
      <p v-if="best" class="mh-best">
        最优：<code>{{ best.id }}</code>
        <span class="mh-muted"> · pass_rate={{ best.pass_rate }}</span>
      </p>
      <ul class="mh-list">
        <li v-for="c in candidates" :key="c.id" class="mh-list__item">
          <div class="min-w-0">
            <div class="mh-list__id">{{ c.id }}</div>
            <div class="mh-muted">
              pass={{ c.pass_rate }} · parent={{ c.parent_id || '—' }}
            </div>
          </div>
          <button type="button" class="mh-btn mh-btn--sm" @click="promote(c.id)">Promote</button>
        </li>
      </ul>
      <p v-if="!candidates.length" class="mh-empty">暂无候选。先跑一次搜索。</p>
    </section>
  </div>
</template>

<style scoped>
.mh__head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; }
.mh__eyebrow {
  font-size: 11px; font-weight: 600; letter-spacing: 0.04em;
  color: var(--color-text-tertiary); margin-bottom: 6px;
}
.mh__title { margin: 0; font-size: 18px; font-weight: 700; color: var(--color-text-primary); }
.mh__sub { margin: 6px 0 0; font-size: 13px; color: var(--color-text-secondary); line-height: 1.5; max-width: 40rem; }
.mh__sub code {
  font-size: 11px; padding: 1px 5px; border-radius: 4px;
  background: var(--color-surface-container-low); font-family: var(--font-mono);
}
.mh-err {
  padding: 10px 12px; border-radius: 10px; font-size: 13px;
  color: var(--color-error);
  background: color-mix(in srgb, var(--color-error) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-error) 20%, transparent);
}

.mh-card {
  border: 1px solid var(--color-border);
  border-radius: 16px;
  background: var(--color-surface);
  overflow: hidden;
}
.mh-card__head {
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-container-low);
}
.mh-card__head h3 { margin: 0; font-size: 13px; font-weight: 600; color: var(--color-text-primary); }
.mh-card__icon { font-size: 18px; color: var(--color-brand); }
.mh-count {
  font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 999px;
  background: var(--color-surface-container-high); color: var(--color-text-tertiary);
}

.mh-pills {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px; padding: 14px 16px;
}
.mh-pill {
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 10px 12px;
  background: var(--color-surface-container-low);
}
.mh-pill__label { display: block; font-size: 10px; font-weight: 600; color: var(--color-text-tertiary); margin-bottom: 4px; }
.mh-pill__value { font-size: 12px; font-weight: 600; color: var(--color-text-primary); font-family: var(--font-mono); word-break: break-all; }

.mh-form {
  display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end;
  padding: 14px 16px;
}
.mh-field { display: flex; flex-direction: column; gap: 4px; font-size: 11px; color: var(--color-text-tertiary); }
.mh-field input, .mh-field select {
  border: 1px solid var(--color-border); border-radius: 10px; padding: 7px 10px;
  background: var(--color-surface-container-lowest, var(--color-surface));
  color: var(--color-text-primary); font-size: 13px; min-width: 120px; outline: none;
}
.mh-field input:focus, .mh-field select:focus { border-color: var(--color-brand); }

.mh-btn {
  display: inline-flex; align-items: center; gap: 6px;
  border: 1px solid var(--color-border); background: var(--color-surface);
  border-radius: 10px; padding: 7px 12px; font-size: 12px; font-weight: 500;
  cursor: pointer; color: var(--color-text-primary); flex-shrink: 0;
}
.mh-btn:hover { background: var(--color-surface-hover); }
.mh-btn--primary { background: var(--color-brand); color: #fff; border-color: transparent; }
.mh-btn--primary:hover { opacity: 0.92; background: var(--color-brand); }
.mh-btn--ghost { background: transparent; }
.mh-btn--sm { padding: 4px 10px; font-size: 11px; border-radius: 8px; }
.mh-btn:disabled { opacity: 0.55; cursor: wait; }

.mh-json {
  margin: 0; padding: 12px 16px; border-top: 1px solid var(--color-border);
  font-size: 11px; line-height: 1.5; font-family: var(--font-mono);
  background: var(--color-surface-container-lowest);
  overflow: auto; max-height: 240px; color: var(--color-text-primary);
}
.mh-best {
  margin: 0; padding: 10px 16px; font-size: 12px; color: var(--color-text-secondary);
  border-bottom: 1px solid var(--color-border);
}
.mh-best code { font-family: var(--font-mono); font-size: 11px; }
.mh-list { list-style: none; margin: 0; padding: 0; }
.mh-list__item {
  display: flex; justify-content: space-between; align-items: center; gap: 10px;
  padding: 12px 16px; border-top: 1px solid var(--color-border);
}
.mh-list__item:first-child { border-top: none; }
.mh-list__id { font-size: 12px; font-weight: 600; color: var(--color-text-primary); font-family: var(--font-mono); word-break: break-all; }
.mh-muted { color: var(--color-text-tertiary); font-size: 12px; }
.mh-empty { margin: 0; padding: 20px 16px; text-align: center; font-size: 12px; color: var(--color-text-tertiary); }
</style>
