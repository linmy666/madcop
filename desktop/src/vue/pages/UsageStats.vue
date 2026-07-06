<script setup lang="ts">
// v3.0 — UsageStats: track token usage and agent activity over time.
// MadCop-exclusive dashboard (React has no equivalent).

import { ref, computed, onMounted } from 'vue'

interface UsagePoint {
  ts: number
  date: string
  promptTokens: number
  completionTokens: number
  totalTokens: number
  agent: string
  model: string
}

const points = ref<UsagePoint[]>([
  // 7 days of sample data
  { ts: 1, date: '周一', promptTokens: 12400, completionTokens: 3200, totalTokens: 15600, agent: '通用助手', model: 'GLM-5.2' },
  { ts: 2, date: '周二', promptTokens: 24300, completionTokens: 8800, totalTokens: 33100, agent: '编码专家', model: 'DeepSeek-V4' },
  { ts: 3, date: '周三', promptTokens: 18700, completionTokens: 5100, totalTokens: 23800, agent: '设计助手', model: 'GLM-5.2' },
  { ts: 4, date: '周四', promptTokens: 31200, completionTokens: 12100, totalTokens: 43300, agent: '通用助手', model: 'GLM-5.2' },
  { ts: 5, date: '周五', promptTokens: 42500, completionTokens: 18900, totalTokens: 61400, agent: '编码专家', model: 'DeepSeek-V4' },
  { ts: 6, date: '周六', promptTokens: 22100, completionTokens: 7300, totalTokens: 29400, agent: '研究员', model: 'Qwen3' },
  { ts: 7, date: '周日', promptTokens: 8700, completionTokens: 2200, totalTokens: 10900, agent: '通用助手', model: 'GLM-5.2' },
])

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
    map.set(p.agent, (map.get(p.agent) || 0) + p.totalTokens)
  }
  return Array.from(map.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 3)
    .map(([name, tokens]) => ({ name, tokens, percent: (tokens / totals.value.tokens * 100).toFixed(0) }))
})

const usage = ref({})
onMounted(async () => {
  try {
    const r = await fetch('/api/activity-stats')
    if (r.ok) usage.value = await r.json()
  } catch {}
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
          <div class="usage-stat__value">{(totals.tokens / 1000).toFixed(1)}K</div>
          <div class="usage-stat__label">总 Token</div>
        </div>
        <div class="usage-stat">
          <div class="usage-stat__value">{(totals.prompt / 1000).toFixed(1)}K</div>
          <div class="usage-stat__label">提示 Token</div>
        </div>
        <div class="usage-stat">
          <div class="usage-stat__value">{(totals.completion / 1000).toFixed(1)}K</div>
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