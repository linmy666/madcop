<script setup lang="ts">
// UsageStats: token usage and activity dashboard.
// Wired to GET /api/activity-stats (madcop_compat.py).

import { ref, computed, onMounted } from 'vue'
import { getApiUrl } from '../api/client'

interface UsagePoint {
  ts: number
  date: string
  promptTokens: number
  completionTokens: number
  totalTokens: number
  agent: string
  model: string
}

const points = ref<UsagePoint[]>([])
const loading = ref(true)
const loadError = ref(false)

onMounted(async () => {
  loading.value = true
  try {
    const r = await fetch(getApiUrl('/api/activity-stats?range=7d'))
    if (!r.ok) throw new Error(String(r.status))
    const data = await r.json()
    const stats = data.stats || data              // endpoint wraps in {stats, range}
    const daily: any[] = stats.dailyActivity || []
    const modelUsage: Record<string, any> = stats.modelUsage || {}
    // Build per-day points from dailyActivity + estimated tokens (~4 chars/tok
    // is the backend heuristic, so messageCount is the real signal here).
    points.value = daily.map((d: any, i: number) => {
      const msgs = d.messageCount || 0
      const estTokens = msgs * 800                  // rough per-message estimate
      return {
        ts: i,
        date: d.date ? String(d.date).slice(5) : `D${i + 1}`,
        promptTokens: Math.round(estTokens * 0.7),
        completionTokens: Math.round(estTokens * 0.3),
        totalTokens: estTokens,
        agent: '—',
        model: '—',
      }
    })
    // If we have modelUsage, overlay real token totals from it.
    const muEntries = Object.entries(modelUsage)
    if (muEntries.length) {
      const sum = (m: any) => (m.inputTokens || 0) + (m.outputTokens || 0)
      const totalFromModels = muEntries.reduce((s, [, m]) => s + sum(m as any), 0)
      if (totalFromModels > 0 && points.value.length) {
        // Distribute real token total proportionally across days.
        const perPoint = totalFromModels / points.value.length
        points.value.forEach((p, idx) => {
          p.totalTokens = Math.round(perPoint)
          p.promptTokens = Math.round(perPoint * 0.7)
          p.completionTokens = Math.round(perPoint * 0.3)
          p.model = idx < muEntries.length ? muEntries[idx][0] : '—'
        })
      }
    }
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
})

const totals = computed(() => ({
  tokens: points.value.reduce((s, p) => s + p.totalTokens, 0),
  prompt: points.value.reduce((s, p) => s + p.promptTokens, 0),
  completion: points.value.reduce((s, p) => s + p.completionTokens, 0),
  sessions: points.value.length,
  agents: new Set(points.value.map(p => p.agent)).size,
}))

const maxTokens = computed(() => Math.max(...points.value.map(p => p.totalTokens), 1))

const topAgents = computed(() => {
  const map = new Map<string, number>()
  for (const p of points.value) {
    map.set(p.model !== '—' ? p.model : p.agent, (map.get(p.model !== '—' ? p.model : p.agent) || 0) + p.totalTokens)
  }
  return Array.from(map.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([name, tokens]) => ({ name, tokens, percent: totals.value.tokens ? (tokens / totals.value.tokens * 100).toFixed(0) : '0' }))
})
</script>

<template>
  <div class="usage-page">
    <div class="usage-page__inner">
      <div class="usage-page__head">
        <h1 class="usage-page__title">用量统计</h1>
        <p class="usage-page__sub">过去 7 天的 token 使用和 agent 活动</p>
      </div>

      <!-- Top stats -->
      <div class="usage-stats">
        <div class="usage-stat">
          <div class="usage-stat__value">{{ (totals.tokens / 1000).toFixed(1) }}K</div>
          <div class="usage-stat__label">总 Token</div>
        </div>
        <div class="usage-stat">
          <div class="usage-stat__value">{{ (totals.prompt / 1000).toFixed(1) }}K</div>
          <div class="usage-stat__label">提示 Token</div>
        </div>
        <div class="usage-stat">
          <div class="usage-stat__value">{{ (totals.completion / 1000).toFixed(1) }}K</div>
          <div class="usage-stat__label">生成 Token</div>
        </div>
        <div class="usage-stat">
          <div class="usage-stat__value">{{ totals.sessions }}</div>
          <div class="usage-stat__label">会话</div>
        </div>
        <div class="usage-stat">
          <div class="usage-stat__value">{{ totals.agents }}</div>
          <div class="usage-stat__label">Agent 数</div>
        </div>
      </div>

      <!-- Bar chart -->
      <div class="usage-section">
        <div class="usage-section__title">每日 Token 使用</div>
        <div class="usage-chart">
          <div v-for="p in points" :key="p.ts" class="usage-bar">
            <div class="usage-bar__label">{{ p.date }}</div>
            <div class="usage-bar__track">
              <div class="usage-bar__fill" :style="{ width: (p.totalTokens / maxTokens * 100) + '%' }" />
              <div class="usage-bar__value">{{ (p.totalTokens / 1000).toFixed(1) }}K</div>
            </div>
          </div>
        </div>
      </div>

      <!-- Top agents -->
      <div class="usage-section">
        <div class="usage-section__title">Top Agent</div>
        <div class="usage-agents">
          <div v-for="a in topAgents" :key="a.name" class="usage-agent-row">
            <div class="usage-agent-row__name">{{ a.name }}</div>
            <div class="usage-agent-row__bar">
              <div class="usage-agent-row__fill" :style="{ width: a.percent + '%' }" />
            </div>
            <div class="usage-agent-row__percent">{{ a.percent }}%</div>
            <div class="usage-agent-row__tokens">{{ (a.tokens / 1000).toFixed(1) }}K</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.usage-page { width: 100%; height: 100%; overflow-y: auto; background: var(--color-surface); }
.usage-page__inner { max-width: 900px; margin: 0 auto; padding: 24px 20px; }
.usage-page__head { margin-bottom: 20px; }
.usage-page__title { font-size: 22px; font-weight: 700; color: var(--color-text-primary); margin: 0; }
.usage-page__sub { font-size: 12px; color: var(--color-text-secondary); margin-top: 4px; }

.usage-stats { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 24px; }
.usage-stat { padding: 16px; background: var(--color-surface-container-lowest); border: 1.5px solid var(--color-border); }
.usage-stat__value { font-size: 22px; font-weight: 700; color: var(--color-primary); }
.usage-stat__label { font-size: 11px; color: var(--color-text-tertiary); margin-top: 4px; }

.usage-section { padding: 20px; background: var(--color-surface-container-lowest); border: 1.5px solid var(--color-border); margin-bottom: 16px; }
.usage-section__title { font-size: 13px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 16px; }

.usage-chart { display: flex; flex-direction: column; gap: 10px; }
.usage-bar { display: flex; align-items: center; gap: 12px; }
.usage-bar__label { width: 36px; font-size: 12px; color: var(--color-text-secondary); }
.usage-bar__track { flex: 1; height: 24px; background: var(--color-surface); border: 1px solid var(--color-border); position: relative; }
.usage-bar__fill { height: 100%; background: var(--color-primary); opacity: 0.7; transition: width 300ms; }
.usage-bar__value { position: absolute; right: 8px; top: 50%; transform: translateY(-50%); font-size: 11px; color: var(--color-text-primary); font-weight: 600; }

.usage-agents { display: flex; flex-direction: column; gap: 8px; }
.usage-agent-row { display: flex; align-items: center; gap: 12px; }
.usage-agent-row__name { width: 100px; font-size: 13px; color: var(--color-text-primary); }
.usage-agent-row__bar { flex: 1; height: 16px; background: var(--color-surface); border: 1px solid var(--color-border); }
.usage-agent-row__fill { height: 100%; background: var(--color-primary); }
.usage-agent-row__percent { width: 40px; font-size: 12px; color: var(--color-text-secondary); text-align: right; }
.usage-agent-row__tokens { width: 60px; font-size: 12px; color: var(--color-text-tertiary); font-family: var(--font-mono); text-align: right; }
</style>