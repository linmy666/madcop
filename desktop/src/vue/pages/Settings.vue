<script setup lang="ts">
// v3.0 — Settings (Vue 3) — MadCop redesigned
// Completely new layout: left sidebar nav + right content panel.
// No cc-haha TabButton horizontal strip — uses a proper settings sidebar.
// Includes new Agent Network + Knowledge Base settings sections.

import { ref, computed, onMounted } from 'vue'

type SettingsTab =
  | 'providers'    // 模型供应商
  | 'general'      // 通用
  | 'agents'       // Agent 网络（新）
  | 'learning'     // 持续学习（LoRA 微调）
  | 'knowledge'    // 知识库（新）
  | 'workflow'     // 工作流引擎（新）
  | 'memory'       // 记忆
  | 'plugins'      // 插件
  | 'mcp'          // MCP 工具
  | 'terminal'     // 终端
  | 'activity'     // 活动统计
  | 'diagnostics'  // 诊断
  | 'about'        // 关于（新）

const activeTab = ref<SettingsTab>('providers')

// ── Settings nav items — grouped ────────────────────────────────────
interface NavItem {
  id: SettingsTab
  label: string
  icon: string  // material-symbols name
  group: 'core' | 'ai' | 'system'
  badge?: string
}

const navItems: NavItem[] = [
  // Core
  { id: 'providers',   label: '模型供应商', icon: 'dns',     group: 'core' },
  { id: 'general',     label: '通用设置',   icon: 'tune',    group: 'core' },
  // AI Features (new!)
  { id: 'agents',      label: 'Agent 网络', icon: 'hub',     group: 'ai', badge: 'NEW' },
  { id: 'learning',    label: '持续学习',  icon: 'school',   group: 'ai', badge: 'NEW' },
  { id: 'knowledge',   label: '知识库',     icon: 'menu_book', group: 'ai', badge: 'NEW' },
  { id: 'workflow',    label: '工作流引擎', icon: 'account_tree', group: 'ai' },
  { id: 'memory',      label: '记忆系统',   icon: 'psychology', group: 'ai' },
  { id: 'plugins',     label: '插件',       icon: 'extension', group: 'ai' },
  { id: 'mcp',         label: 'MCP 工具',   icon: 'build',   group: 'ai' },
  // System
  { id: 'terminal',    label: '终端',       icon: 'terminal', group: 'system' },
  { id: 'activity',    label: '活动统计',   icon: 'monitoring', group: 'system' },
  { id: 'diagnostics', label: '环境诊断',   icon: 'monitor_heart', group: 'system' },
  { id: 'about',       label: '关于',       icon: 'info',    group: 'system' },
]

const groupLabels: Record<string, string> = {
  core: '核心配置',
  ai: 'AI 能力',
  system: '系统',
}

const groupedNav = computed(() => {
  const groups: ('core' | 'ai' | 'system')[] = ['core', 'ai', 'system']
  return groups.map(g => ({
    label: groupLabels[g],
    items: navItems.filter(n => n.group === g),
  }))
})

// ── Provider state ───────────────────────────────────────────────────
const providers = ref<any[]>([])
const activeProvider = ref('')
const activeModel = ref('')

onMounted(async () => {
  try {
    const r = await fetch('/api/settings')
    const s = await r.json()
    providers.value = Object.values(s.providers || {})
    activeProvider.value = s.active_provider || ''
  } catch {}
})

// ── Agent network stats ──────────────────────────────────────────────
const agentStats = ref({ builtin: 0, installed: 0 })
const kbCount = ref(0)

onMounted(async () => {
  try {
    const r = await fetch('/api/agents')
    const d = await r.json()
    agentStats.value = {
      builtin: d.builtin?.length || 0,
      installed: d.installed?.length || 0,
    }
  } catch {}
  try {
    const r2 = await fetch('/api/agents/knowledge')
    const d2 = await r2.json()
    kbCount.value = Array.isArray(d2) ? d2.length : 0
  } catch {}
})

// ─── Continuous Learning state ───────────────────────────────────────
const learningMode = ref<'none' | 'local'>('none')
const learningStats = ref({ total: 0, used: 0 })
const learningHistory = ref<any[]>([])
const learningTraining = ref(false)
const learningTrainingStatus = ref<'idle' | 'running' | 'completed' | 'failed'>('idle')
const learningTrainingMessage = ref('')

async function loadLearning() {
  try {
    const r1 = await fetch('/api/training/mode')
    if (r1.ok) {
      const d = await r1.json()
      learningMode.value = d.mode || 'none'
    }
    const r2 = await fetch('/api/training/stats')
    if (r2.ok) {
      const d = await r2.json()
      learningStats.value = d.stats ?? { total: 0, used: 0 }
      learningHistory.value = d.history ?? []
    }
  } catch {}
}

async function setLearningMode(mode: 'none' | 'local') {
  learningMode.value = mode
  await fetch('/api/training/mode', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  })
}

async function triggerTraining() {
  if (learningTraining.value) return
  if (learningStats.value.total - learningStats.value.used < 10) {
    alert('至少需要 10 条未训练反馈才能触发微调')
    return
  }
  learningTraining.value = true
  learningTrainingStatus.value = 'running'
  learningTrainingMessage.value = '正在准备 LoRA 微调...'
  try {
    const res = await fetch('/api/training/trigger', { method: 'POST' })
    if (res.ok) {
      const d = await res.json()
      learningTrainingMessage.value = `微调已启动，使用 ${d.samples} 条样本`
      pollTrainingStatus()
    } else {
      const err = await res.json().catch(() => ({}))
      learningTrainingStatus.value = 'failed'
      learningTrainingMessage.value = err.message || '启动失败'
      learningTraining.value = false
    }
  } catch (e) {
    learningTrainingStatus.value = 'failed'
    learningTrainingMessage.value = '网络错误'
    learningTraining.value = false
  }
}

async function pollTrainingStatus() {
  for (let i = 0; i < 60; i++) {
    await new Promise((r) => setTimeout(r, 30000))
    try {
      const res = await fetch('/api/training/status')
      if (res.ok) {
        const d = await res.json()
        if (d.status === 'completed') {
          learningTrainingStatus.value = 'completed'
          learningTrainingMessage.value = '微调完成'
          learningTraining.value = false
          await loadLearning()
          return
        } else if (d.status === 'failed') {
          learningTrainingStatus.value = 'failed'
          learningTrainingMessage.value = d.message || '微调失败'
          learningTraining.value = false
          return
        }
      }
    } catch {}
  }
  learningTrainingStatus.value = 'failed'
  learningTrainingMessage.value = '轮询超时'
  learningTraining.value = false
}

async function exportDataset() {
  try {
    const res = await fetch('/api/training/export')
    if (!res.ok) return
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `madcop-feedback-${Date.now()}.jsonl`
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  } catch {}
}

async function clearLearningData() {
  if (!confirm('确定清除所有反馈数据？此操作不可恢复。')) return
  await fetch('/api/training/clear', { method: 'POST' })
  await loadLearning()
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '—'
  const d = new Date(dateStr)
  const diff = Date.now() - d.getTime()
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`
  return d.toLocaleDateString('zh-CN')
}

onMounted(loadLearning)
</script>

<template>
  <div class="settings-page">
    <div class="settings-layout">
      <!-- Left: Settings Nav -->
      <nav class="settings-nav">
        <div v-for="group in groupedNav" :key="group.label" class="settings-nav__group">
          <div class="settings-nav__label">{{ group.label }}</div>
          <button
            v-for="item in group.items" :key="item.id"
            :class="['settings-nav__item', { 'settings-nav__item--active': activeTab === item.id }]"
            @click="activeTab = item.id"
          >
            <span class="material-symbols-outlined text-[18px]">{{ item.icon }}</span>
            <span class="settings-nav__text">{{ item.label }}</span>
            <span v-if="item.badge" class="settings-nav__badge">{{ item.badge }}</span>
          </button>
        </div>
      </nav>

      <!-- Right: Content -->
      <main class="settings-content">
        <!-- ═══ Providers ═══ -->
        <div v-if="activeTab === 'providers'" class="settings-section">
          <h2 class="settings-section__title">模型供应商</h2>
          <p class="settings-section__desc">配置你的 LLM API key 和默认模型。</p>

          <div v-for="p in providers" :key="p.id" class="provider-card">
            <div class="provider-card__head">
              <span class="material-symbols-outlined text-[20px] text-[var(--color-text-secondary)]">cloud</span>
              <span class="provider-card__name">{{ p.name }}</span>
              <span v-if="p.id === activeProvider" class="provider-card__active">当前</span>
            </div>
            <div class="provider-card__model">{{ p.model }}</div>
            <div class="provider-card__status" :class="p.api_key ? 'provider-card__status--ok' : 'provider-card__status--warn'">
              {{ p.api_key ? 'API Key 已配置' : '未配置 API Key' }}
            </div>
          </div>
        </div>

        <!-- ═══ General ═══ -->
        <div v-else-if="activeTab === 'general'" class="settings-section">
          <h2 class="settings-section__title">通用设置</h2>
          <div class="settings-row">
            <span class="settings-row__label">语言</span>
            <select class="settings-select"><option>中文</option><option>English</option></select>
          </div>
          <div class="settings-row">
            <span class="settings-row__label">回复语言</span>
            <select class="settings-select"><option>跟随用户</option><option>始终中文</option><option>始终英文</option></select>
          </div>
          <div class="settings-row">
            <span class="settings-row__label">发送快捷键</span>
            <select class="settings-select"><option>Enter 发送 / Shift+Enter 换行</option><option>Ctrl+Enter 发送</option></select>
          </div>
        </div>

        <!-- ═══ Agent Network ═══ -->
        <div v-else-if="activeTab === 'agents'" class="settings-section">
          <h2 class="settings-section__title">Agent 网络</h2>
          <p class="settings-section__desc">管理你的 AI Agent 团队。每个 Agent 可以有独立的模型、工具和能力。</p>

          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-card__value">{{ agentStats.builtin }}</div>
              <div class="stat-card__label">内置 Agent</div>
            </div>
            <div class="stat-card">
              <div class="stat-card__value">{{ agentStats.installed }}</div>
              <div class="stat-card__label">自定义 Agent</div>
            </div>
            <div class="stat-card">
              <div class="stat-card__value">{{ agentStats.builtin + agentStats.installed }}</div>
              <div class="stat-card__label">总计</div>
            </div>
          </div>

          <div class="settings-row">
            <span class="settings-row__label">默认 Agent 模型</span>
            <select class="settings-select"><option>GLM-5.2</option><option>DeepSeek-V4 Flash</option><option>Qwen3-80B</option></select>
          </div>
          <div class="settings-row">
            <span class="settings-row__label">Agent 超时（秒）</span>
            <input type="number" value="120" class="settings-input" />
          </div>
          <div class="settings-row">
            <span class="settings-row__label">最大并发 Agent</span>
            <input type="number" value="3" class="settings-input" />
          </div>
        </div>

        <!-- ═══ Knowledge Base ═══ -->
        <div v-else-if="activeTab === 'knowledge'" class="settings-section">
          <h2 class="settings-section__title">知识库</h2>
          <p class="settings-section__desc">管理 Agent 对话中可引用的文档、笔记和代码片段。</p>

          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-card__value">{{ kbCount }}</div>
              <div class="stat-card__label">知识条目</div>
            </div>
            <div class="stat-card">
              <div class="stat-card__value">4</div>
              <div class="stat-card__label">支持类型</div>
            </div>
            <div class="stat-card">
              <div class="stat-card__value">∞</div>
              <div class="stat-card__label">容量上限</div>
            </div>
          </div>

          <div class="settings-row">
            <span class="settings-row__label">自动提取知识</span>
            <Toggle default-on />
          </div>
          <div class="settings-row">
            <span class="settings-row__label">对话中自动引用</span>
            <Toggle default-on />
          </div>
        </div>

        <!-- ═══ Continuous Learning ═══ -->
        <div v-else-if="activeTab === 'learning'" class="settings-section">
          <h2 class="settings-section__title">持续学习</h2>
          <p class="settings-section__desc">基于你的反馈数据，本地 LoRA 微调专属小模型。所有数据保留在 Mac 上。</p>

          <!-- Mode selector -->
          <div class="settings-row settings-row--stack">
            <span class="settings-row__label">学习模式</span>
            <div class="learning-modes">
              <button
                type="button"
                :class="['learning-mode', { 'learning-mode--active': learningMode === 'none' }]"
                @click="setLearningMode('none')"
              >
                <span class="learning-mode__title">不学习</span>
                <span class="learning-mode__desc">仅使用在线推理，不收集反馈</span>
              </button>
              <button
                type="button"
                :class="['learning-mode', { 'learning-mode--active': learningMode === 'local' }]"
                @click="setLearningMode('local')"
              >
                <span class="learning-mode__title">本地 LoRA 微调</span>
                <span class="learning-mode__desc">数据保留在本地，用反馈训练小模型</span>
              </button>
            </div>
          </div>

          <!-- Stats -->
          <div class="stats-grid">
            <div class="stat-card">
              <div class="stat-card__value">{{ learningStats.total }}</div>
              <div class="stat-card__label">已收集反馈</div>
            </div>
            <div class="stat-card">
              <div class="stat-card__value">{{ learningStats.used }}</div>
              <div class="stat-card__label">已用于训练</div>
            </div>
            <div class="stat-card">
              <div class="stat-card__value">{{ learningHistory.length }}</div>
              <div class="stat-card__label">微调次数</div>
            </div>
          </div>

          <!-- Training trigger -->
          <div class="settings-row">
            <span class="settings-row__label">手动触发</span>
            <div class="flex flex-col gap-2">
              <button
                type="button"
                :disabled="learningTraining"
                :class="[
                  'training-trigger-btn',
                  learningTraining ? 'training-trigger-btn--disabled' : '',
                ]"
                @click="triggerTraining"
              >
                {{ learningTraining ? '微调中…' : '开始 LoRA 微调' }}
              </button>
              <span
                v-if="learningTrainingMessage"
                :class="[
                  'text-[11px]',
                  learningTrainingStatus === 'failed' ? 'training-msg--error' : 'training-msg--ok',
                ]"
                style="font-family: ui-monospace, monospace"
              >{{ learningTrainingMessage }}</span>
            </div>
          </div>

          <!-- Data management -->
          <div class="settings-row">
            <span class="settings-row__label">数据管理</span>
            <div class="flex flex-wrap gap-2">
              <button class="settings-btn" @click="exportDataset">导出训练集 (JSONL)</button>
              <button
                class="settings-btn settings-btn--danger"
                :disabled="learningStats.total === 0"
                @click="clearLearningData"
              >清除所有数据</button>
            </div>
          </div>

          <!-- History -->
          <div v-if="learningHistory.length > 0" class="settings-row settings-row--stack">
            <span class="settings-row__label">微调历史</span>
            <div class="learning-history">
              <div v-for="r in learningHistory" :key="r.id" class="learning-history__row">
                <span class="learning-history__dot" :class="r.status === 'completed' ? 'learning-history__dot--ok' : 'learning-history__dot--err'"></span>
                <span class="learning-history__date">{{ formatDate(r.date) }}</span>
                <span class="learning-history__meta">{{ r.samples }} samples · {{ r.duration }} · loss {{ r.loss.toFixed(3) }}</span>
              </div>
            </div>
          </div>

          <div class="privacy-banner">
            <span style="font-family: ui-monospace, monospace">local only</span>
            <span>数据存储于 <code>~/Library/MadCop/training_data/</code></span>
          </div>
        </div>

        <!-- ═══ Workflow ═══ -->
        <div v-else-if="activeTab === 'workflow'" class="settings-section">
          <h2 class="settings-section__title">工作流引擎</h2>
          <p class="settings-section__desc">配置可视化工作流编排的行为。</p>
          <div class="settings-row">
            <span class="settings-row__label">最大迭代次数</span>
            <input type="number" value="30" class="settings-input" />
          </div>
          <div class="settings-row">
            <span class="settings-row__label">节点超时（秒）</span>
            <input type="number" value="60" class="settings-input" />
          </div>
          <div class="settings-row">
            <span class="settings-row__label">自动保存工作流</span>
            <Toggle default-on />
          </div>
        </div>

        <!-- ═══ Memory ═══ -->
        <div v-else-if="activeTab === 'memory'" class="settings-section">
          <h2 class="settings-section__title">记忆系统</h2>
          <p class="settings-section__desc">MadCop 会自动记忆你的偏好和上下文。</p>
          <div class="settings-row">
            <span class="settings-row__label">启用长期记忆</span>
            <Toggle default-on />
          </div>
          <div class="settings-row">
            <span class="settings-row__label">自动提取事实</span>
            <Toggle default-on />
          </div>
          <div class="settings-row">
            <span class="settings-row__label">记忆保留（天）</span>
            <input type="number" value="90" class="settings-input" />
          </div>
        </div>

        <!-- ═══ About ═══ -->
        <div v-else-if="activeTab === 'about'" class="settings-section">
          <h2 class="settings-section__title">关于 MadCop</h2>
          <div class="about-card">
            <div class="about-card__logo">
              <span class="material-symbols-outlined text-[48px] text-[var(--color-primary)]">smart_toy</span>
            </div>
            <div class="about-card__info">
              <div class="about-card__name">MadCop</div>
              <div class="about-card__version">v3.0.0 · Agent Network Edition</div>
              <div class="about-card__desc">周思万虑，巡行无疆 — 本地 AI Agent 桌面工作站</div>
              <a href="https://github.com/linmy666/madcop" target="_blank" class="about-card__link">
                <span class="material-symbols-outlined text-[14px]">open_in_new</span>
                GitHub
              </a>
            </div>
          </div>
          <div class="about-tech">
            <div class="about-tech__title">技术栈</div>
            <div class="about-tech__list">
              <span class="about-tech__item">Vue 3 + Pinia</span>
              <span class="about-tech__item">FastAPI + Uvicorn</span>
              <span class="about-tech__item">Electron 42</span>
              <span class="about-tech__item">Tailwind v4</span>
              <span class="about-tech__item">SQLite + JSON</span>
            </div>
          </div>
        </div>

        <!-- ═══ Placeholder for other tabs ═══ -->
        <div v-else class="settings-section">
          <h2 class="settings-section__title">{{ navItems.find(n => n.id === activeTab)?.label }}</h2>
          <p class="settings-section__desc">此模块正在开发中。</p>
          <div class="settings-placeholder">
            <span class="material-symbols-outlined text-[48px] text-[var(--color-text-tertiary)] opacity-30">construction</span>
            <p>即将上线</p>
          </div>
        </div>
      </main>
    </div>
  </div>
</template>

<script lang="ts">
import { defineComponent, h } from 'vue'

// Toggle switch component (inline)
const Toggle = defineComponent({
  props: { defaultOn: { type: Boolean, default: false } },
  setup(props) {
    return () => h('div', {
      class: 'madcop-toggle',
      onClick: (e: MouseEvent) => {
        const el = e.currentTarget as HTMLElement
        el.classList.toggle('madcop-toggle--on')
      },
    })
  },
})

export default { components: { Toggle } }
</script>

<style scoped>
.settings-page { width: 100%; height: 100%; overflow: hidden; background: var(--color-surface); }
.settings-layout { display: flex; height: 100%; }

/* Left nav */
.settings-nav {
  width: 220px; flex-shrink: 0;
  border-right: 1.5px solid var(--color-border);
  background: var(--color-surface-container-low);
  overflow-y: auto; padding: 16px 0;
}
.settings-nav__group { margin-bottom: 16px; }
.settings-nav__label {
  font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--color-text-tertiary); padding: 0 16px; margin-bottom: 6px;
}
.settings-nav__item {
  display: flex; align-items: center; gap: 10px;
  width: 100%; padding: 8px 16px;
  background: transparent; border: none; cursor: pointer;
  color: var(--color-text-secondary); font-size: 13px;
  transition: background 140ms;
}
.settings-nav__item:hover { background: var(--color-surface-hover); }
.settings-nav__item--active {
  background: var(--color-primary-fixed); color: var(--color-primary); font-weight: 600;
}
.settings-nav__text { flex: 1; text-align: left; }
.settings-nav__badge {
  font-size: 9px; font-weight: 700; padding: 1px 6px;
  background: var(--color-primary); color: var(--color-on-primary);
}

/* Right content */
.settings-content { flex: 1; overflow-y: auto; padding: 32px 40px; }
.settings-section__title { font-size: 20px; font-weight: 700; color: var(--color-text-primary); margin: 0 0 4px; }
.settings-section__desc { font-size: 13px; color: var(--color-text-secondary); margin-bottom: 24px; line-height: 1.5; }

.settings-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 0; border-bottom: 1px solid var(--color-border);
}
.settings-row__label { font-size: 14px; font-weight: 500; color: var(--color-text-primary); }
.settings-select, .settings-input {
  padding: 6px 12px; border: 1.5px solid var(--color-border);
  background: var(--color-surface); color: var(--color-text-primary); font-size: 13px; outline: none;
}
.settings-select { min-width: 200px; cursor: pointer; }
.settings-input { width: 100px; }

/* Stats grid */
.stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 24px; }
.stat-card { padding: 16px; background: var(--color-surface-container-lowest); border: 1.5px solid var(--color-border); }
.stat-card__value { font-size: 28px; font-weight: 700; color: var(--color-primary); }
.stat-card__label { font-size: 12px; color: var(--color-text-tertiary); margin-top: 4px; }

/* Provider card */
.provider-card { padding: 16px; background: var(--color-surface-container-lowest); border: 1.5px solid var(--color-border); margin-bottom: 12px; }
.provider-card__head { display: flex; align-items: center; gap: 8px; }
.provider-card__name { font-size: 14px; font-weight: 600; color: var(--color-text-primary); }
.provider-card__active { font-size: 10px; padding: 2px 8px; background: var(--color-primary); color: var(--color-on-primary); }
.provider-card__model { font-size: 12px; color: var(--color-text-tertiary); font-family: var(--font-mono); margin-top: 4px; }
.provider-card__status { font-size: 11px; margin-top: 8px; }
.provider-card__status--ok { color: var(--color-success); }
.provider-card__status--warn { color: var(--color-warning); }

/* About */
.about-card { display: flex; gap: 20px; padding: 24px; background: var(--color-surface-container-lowest); border: 1.5px solid var(--color-border); margin-bottom: 16px; }
.about-card__logo { width: 64px; height: 64px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.about-card__name { font-size: 20px; font-weight: 700; color: var(--color-text-primary); }
.about-card__version { font-size: 12px; color: var(--color-text-tertiary); font-family: var(--font-mono); margin-top: 4px; }
.about-card__desc { font-size: 13px; color: var(--color-text-secondary); margin-top: 8px; }
.about-card__link { display: inline-flex; align-items: center; gap: 4px; margin-top: 12px; font-size: 12px; color: var(--color-primary); }
.about-tech__title { font-size: 12px; font-weight: 600; color: var(--color-text-tertiary); margin-bottom: 8px; text-transform: uppercase; letter-spacing: 0.05em; }
.about-tech__list { display: flex; flex-wrap: wrap; gap: 8px; }
.about-tech__item { padding: 4px 10px; font-size: 11px; font-weight: 500; background: var(--color-primary-fixed); color: var(--color-primary); }

/* Placeholder */
.settings-placeholder { text-align: center; padding: 60px 20px; color: var(--color-text-tertiary); }
.settings-placeholder p { margin-top: 12px; font-size: 14px; }

/* Toggle */
:deep(.madcop-toggle) {
  width: 40px; height: 22px; padding: 2px; cursor: pointer;
  background: var(--color-border); transition: background 140ms;
}
:deep(.madcop-toggle--on) { background: var(--color-primary); }
:deep(.madcop-toggle)::after {
  content: ''; display: block; width: 18px; height: 18px;
  background: #fff; transition: transform 140ms;
}
:deep(.madcop-toggle--on)::after { transform: translateX(18px); }
</style>

/* Continuous Learning styles */
.learning-modes {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}
.learning-mode {
  text-align: left;
  padding: 10px 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  transition: all 0.15s;
}
.learning-mode:hover { border-color: var(--color-border-focus); }
.learning-mode--active {
  border-color: var(--color-brand);
  background: color-mix(in srgb, var(--color-brand) 5%, transparent);
}
.learning-mode__title {
  display: block;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
}
.learning-mode__desc {
  display: block;
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
}
.training-trigger-btn {
  padding: 8px 16px;
  border-radius: 6px;
  background: var(--color-brand);
  color: white;
  font-size: 12px;
  font-weight: 500;
  border: none;
  cursor: pointer;
  transition: opacity 0.15s;
}
.training-trigger-btn:hover { opacity: 0.9; }
.training-trigger-btn--disabled {
  background: var(--color-surface-container);
  color: var(--color-text-tertiary);
  cursor: not-allowed;
}
.training-msg--ok { color: var(--color-text-secondary); }
.training-msg--error { color: var(--color-error); }
.learning-history {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.learning-history__row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 6px;
  background: var(--color-surface);
  font-size: 12px;
}
.learning-history__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-text-tertiary);
}
.learning-history__dot--ok { background: var(--color-success); }
.learning-history__dot--err { background: var(--color-error); }
.learning-history__date { color: var(--color-text-primary); }
.learning-history__meta {
  color: var(--color-text-tertiary);
  font-family: ui-monospace, monospace;
  font-size: 10px;
  margin-left: auto;
}
.privacy-banner {
  margin-top: 16px;
  padding: 8px 12px;
  border-radius: 6px;
  background: color-mix(in srgb, var(--color-success) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-success) 20%, transparent);
  color: var(--color-text-secondary);
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.privacy-banner code {
  font-family: ui-monospace, monospace;
  font-size: 10px;
  padding: 1px 4px;
  background: var(--color-surface);
  border-radius: 3px;
}
.settings-row--stack {
  flex-direction: column;
  align-items: flex-start !important;
  gap: 8px;
}
.settings-btn {
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
}
.settings-btn:hover { background: var(--color-surface-container); }
.settings-btn--danger {
  border-color: color-mix(in srgb, var(--color-error) 30%, transparent);
  color: var(--color-error);
}
.settings-btn--danger:hover {
  background: color-mix(in srgb, var(--color-error) 5%, transparent);
}
