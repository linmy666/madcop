<script setup lang="ts">
// v3.0 — Settings (Vue 3) — MadCop redesigned
// Completely new layout: left sidebar nav + right content panel.
// No cc-haha TabButton horizontal strip — uses a proper settings sidebar.
// Includes new Agent Network + Knowledge Base settings sections.

import { ref, computed, onMounted, defineAsyncComponent, watch } from 'vue'
import { useTabStore } from '../stores/tabStore'
import { useSessionStore } from '../stores/sessionStore'
import { useUIStore } from '../stores/uiStore'
import { useTranslation } from '../i18n'
import { getApiUrl } from '../api/client'

const MemoryPage = defineAsyncComponent(() => import('./MemoryPage.vue'))
const KnowledgeBase = defineAsyncComponent(() => import('./KnowledgeBase.vue'))
const ProviderSettings = defineAsyncComponent(() => import('./settings/ProviderSettings.vue'))
const GeneralSettings = defineAsyncComponent(() => import('./settings/GeneralSettings.vue'))
const H5AccessSettings = defineAsyncComponent(() => import('./H5AccessSettings.vue'))
const AdapterSettings = defineAsyncComponent(() => import('./AdapterSettings.vue'))
const TerminalSettings = defineAsyncComponent(() => import('./TerminalSettings.vue'))
const McpSettings = defineAsyncComponent(() => import('./McpSettings.vue'))
const AgentsSettingsPage = defineAsyncComponent(() => import('./AgentsSettings.vue'))
const SkillSettingsPage = defineAsyncComponent(() => import('./SkillSettings.vue'))
const PluginSettingsPage = defineAsyncComponent(() => import('./PluginSettings.vue'))
const ComputerUseSettingsPage = defineAsyncComponent(() => import('./ComputerUseSettings.vue'))
const ActivitySettingsPage = defineAsyncComponent(() => import('./ActivitySettings.vue'))
const DiagnosticsSettingsPage = defineAsyncComponent(() => import('./DiagnosticsSettings.vue'))
const AboutSettingsPage = defineAsyncComponent(() => import('./AboutSettings.vue'))
const MetaHarnessSettings = defineAsyncComponent(() => import('./settings/MetaHarnessSettings.vue'))

const t = useTranslation()
const uiStore = useUIStore()

type SettingsTab =
  | 'providers'
  | 'general'
  | 'agents'
  | 'memory'
  | 'plugins'
  | 'mcp'
  | 'metaHarness'
  | 'knowledge'
  | 'terminal'
  | 'activity'
  | 'diagnostics'
  | 'about'
  | string

const tabStore = useTabStore()
const sessionStore = useSessionStore()
const activeTab = ref<SettingsTab>('providers')

// ── Settings nav items — grouped ────────────────────────────────────
interface NavItem {
  id: SettingsTab
  labelKey: string
  icon: string
  group: 'core' | 'ai' | 'system'
  badge?: string
}

const navItems: NavItem[] = [
  { id: 'providers',   labelKey: 'settings.nav.providers',   icon: 'dns',            group: 'core' },
  { id: 'general',     labelKey: 'settings.nav.general',     icon: 'tune',           group: 'core' },
  { id: 'agents',      labelKey: 'settings.nav.agents',      icon: 'smart_toy',      group: 'ai' },
  { id: 'memory',      labelKey: 'settings.nav.memory',      icon: 'psychology',     group: 'ai' },
  { id: 'knowledge',   labelKey: 'sidebar.knowledge',        icon: 'menu_book',      group: 'ai' },
  { id: 'mcp',         labelKey: 'settings.nav.mcp',         icon: 'build',          group: 'ai' },
  { id: 'skills',      labelKey: 'settings.nav.skills',      icon: 'auto_awesome',   group: 'ai' },
  { id: 'metaHarness', labelKey: 'settings.nav.metaHarness', icon: 'science',        group: 'ai' },
  { id: 'adapters',    labelKey: 'settings.nav.adapters',    icon: 'chat',           group: 'ai' },
  { id: 'h5Access',    labelKey: 'settings.nav.h5Access',    icon: 'qr_code_2',      group: 'ai' },
  { id: 'plugins',     labelKey: 'settings.nav.plugins',     icon: 'extension',      group: 'system' },
  { id: 'terminal',    labelKey: 'settings.nav.terminal',    icon: 'terminal',       group: 'system' },
  { id: 'computerUse', labelKey: 'settings.nav.computerUse', icon: 'mouse',          group: 'system' },
  { id: 'activity',    labelKey: 'settings.nav.activity',    icon: 'monitoring',     group: 'system' },
  { id: 'diagnostics', labelKey: 'settings.nav.diagnostics', icon: 'monitor_heart',  group: 'system' },
  { id: 'about',       labelKey: 'settings.nav.about',       icon: 'info',           group: 'system' },
]

const groupLabelKeys: Record<string, string> = {
  core: 'settings.nav.core',
  ai: 'settings.nav.ai',
  system: 'settings.nav.system',
}

const groupedNav = computed(() => {
  const groups: ('core' | 'ai' | 'system')[] = ['core', 'ai', 'system']
  return groups.map(g => ({
    label: t(groupLabelKeys[g]),
    items: navItems.filter(n => n.group === g),
  }))
})

// Honor pending settings tab from slash / deep links
watch(
  () => uiStore.pendingSettingsTab,
  (tab) => {
    if (tab && navItems.some((n) => n.id === tab)) {
      activeTab.value = tab
      uiStore.setPendingSettingsTab(null)
    }
  },
  { immediate: true },
)

// ── Provider state ───────────────────────────────────────────────────
const providers = ref<any[]>([])
const activeProvider = ref('')

onMounted(async () => {
  try {
    const r = await fetch(getApiUrl('/api/settings'))
    const s = await r.json()
    providers.value = Object.values(s.providers || {})
    activeProvider.value = s.active_provider || ''
  } catch { /* ignore */ }
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
    const r1 = await fetch(getApiUrl('/api/training/mode'))
    if (r1.ok) {
      const d = await r1.json()
      learningMode.value = d.mode || 'none'
    }
    const r2 = await fetch(getApiUrl('/api/training/stats'))
    if (r2.ok) {
      const d = await r2.json()
      learningStats.value = d.stats ?? { total: 0, used: 0 }
      learningHistory.value = d.history ?? []
    }
  } catch {}
}

async function setLearningMode(mode: 'none' | 'local') {
  learningMode.value = mode
  await fetch(getApiUrl('/api/training/mode'), {
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

function goBackToSession() {
  // Create a new session if none active
  if (!tabStore.activeTabId) {
    sessionStore.createSession().then((id: string) => {
      tabStore.openTab(id, '新对话')
    })
  } else {
    // Just set active to the current session tab
    const firstSession = (tabStore.tabs as any[]).find((t: any) => t.type === 'session')
    if (firstSession) {
      tabStore.setActiveTab(firstSession.sessionId)
    }
  }
}

onMounted(loadLearning)
</script>

<template>
  <div class="settings-page">
    <!-- Back to session button -->
    <div class="settings-topbar" @click="goBackToSession">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M15 18l-6-6 6-6"/></svg>
      <span class="settings-topbar__title">{{ t('settings.title') }}</span>
      <span class="settings-topbar__hint">{{ t('settings.back') }}</span>
    </div>
    <div class="settings-layout">
      <!-- Left: Settings Nav -->
      <nav class="settings-nav">
        <div v-for="group in groupedNav" :key="group.label" class="settings-nav__group">
          <div class="settings-nav__label">{{ group.label }}</div>
          <button
            v-for="item in group.items" :key="item.id"
            type="button"
            :class="['settings-nav__item', { 'settings-nav__item--active': activeTab === item.id }]"
            @click="activeTab = item.id"
          >
            <span class="material-symbols-outlined text-[18px]">{{ item.icon }}</span>
            <span class="settings-nav__text">{{ t(item.labelKey) }}</span>
            <span v-if="item.badge" class="settings-nav__badge">{{ item.badge }}</span>
          </button>
        </div>
      </nav>

      <!-- Right: Content -->
      <main class="settings-content">
        <!-- ═══ Providers ═══ -->
        <div v-if="activeTab === 'providers'" class="settings-section settings-section--fullbleed">
          <ProviderSettings />
        </div>

        <!-- ═══ General ═══ -->
        <div v-else-if="activeTab === 'general'" class="settings-section settings-section--fullbleed">
          <GeneralSettings />
        </div>

        <!-- ═══ Knowledge Base ═══ -->
        <div v-else-if="activeTab === 'knowledge'" class="settings-section settings-section--fullbleed">
          <KnowledgeBase />
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
                style="font-family: var(--font-mono)"
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
            <span style="font-family: var(--font-mono)">local only</span>
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
        <div v-else-if="activeTab === 'memory'" class="settings-section settings-section--fullbleed">
          <MemoryPage />
        </div>

<!-- ═══ About (now handled by routing above) ═══ -->

        <!-- ═══ Placeholder for other tabs ═══ -->
        <!-- ═══ H5 Access ═══ -->
        <div v-else-if="activeTab === 'h5Access'" class="settings-section settings-section--fullbleed">
          <H5AccessSettings />
        </div>
        <!-- ═══ Adapters ═══ -->
        <div v-else-if="activeTab === 'adapters'" class="settings-section settings-section--fullbleed">
          <AdapterSettings />
        </div>
        <!-- ═══ Terminal ═══ -->
        <div v-else-if="activeTab === 'terminal'" class="settings-section settings-section--fullbleed">
          <TerminalSettings />
        </div>
        <!-- ═══ MCP ═══ -->
        <div v-else-if="activeTab === 'mcp'" class="settings-section settings-section--fullbleed">
          <McpSettings />
        </div>
        <!-- ═══ Agents ═══ -->
        <div v-else-if="activeTab === 'agents'" class="settings-section settings-section--fullbleed">
          <AgentsSettingsPage />
        </div>
        <!-- ═══ Skills ═══ -->
        <div v-else-if="activeTab === 'metaHarness'" class="settings-section settings-section--fullbleed">
          <MetaHarnessSettings />
        </div>

        <div v-else-if="activeTab === 'skills'" class="settings-section settings-section--fullbleed">
          <SkillSettingsPage />
        </div>
                <!-- ═══ ComputerUse ═══ -->
        <div v-else-if="activeTab === 'computerUse'" class="settings-section settings-section--fullbleed">
          <ComputerUseSettingsPage />
        </div>
        <!-- ═══ Activity ═══ -->
        <div v-else-if="activeTab === 'activity'" class="settings-section settings-section--fullbleed">
          <ActivitySettingsPage />
        </div>
        <!-- ═══ Diagnostics ═══ -->
        <div v-else-if="activeTab === 'diagnostics'" class="settings-section settings-section--fullbleed">
          <DiagnosticsSettingsPage />
        </div>
        <!-- ═══ About ═══ -->
        <div v-else-if="activeTab === 'about'" class="settings-section settings-section--fullbleed">
          <AboutSettingsPage />
        </div>
        <!-- ═══ Placeholder for unhandled tabs ═══ -->
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
.settings-page {
  width: 100%; height: 100%; overflow: hidden; background: var(--color-surface);
  display: flex; flex-direction: column;
}
.settings-topbar {
  display: flex; align-items: center; gap: 10px;
  flex-shrink: 0; padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  cursor: pointer;
  transition: background 120ms;
}
.settings-topbar:hover { background: var(--color-surface-hover); }
.settings-topbar__title {
  font-size: 14px; font-weight: 600; color: var(--color-text-primary);
}
.settings-topbar__hint {
  margin-left: auto; font-size: 12px; color: var(--color-text-tertiary);
}
.settings-layout { display: flex; flex: 1; min-height: 0; }

/* Left nav */
.settings-nav {
  width: 232px; flex-shrink: 0;
  border-right: 1px solid var(--color-border);
  background: var(--color-surface-container-low);
  overflow-y: auto; padding: 12px 0 24px;
}
.settings-nav__group { margin-bottom: 14px; }
.settings-nav__label {
  font-size: 11px; font-weight: 600; letter-spacing: 0.02em;
  color: var(--color-text-tertiary); padding: 4px 16px 8px; margin-bottom: 2px;
}
.settings-nav__item {
  display: flex; align-items: center; gap: 10px;
  width: calc(100% - 12px); margin: 0 6px; padding: 9px 12px;
  background: transparent; border: none; cursor: pointer;
  color: var(--color-text-secondary); font-size: 13px;
  border-radius: 10px;
  transition: background 140ms, color 140ms;
}
.settings-nav__item:hover { background: var(--color-surface-hover); color: var(--color-text-primary); }
.settings-nav__item--active {
  background: var(--color-primary-fixed, color-mix(in srgb, var(--color-brand) 12%, transparent));
  color: var(--color-brand, var(--color-primary)); font-weight: 600;
}
.settings-nav__text { flex: 1; text-align: left; }
.settings-nav__badge {
  font-size: 9px; font-weight: 700; padding: 1px 6px; border-radius: 999px;
  background: var(--color-primary); color: var(--color-on-primary);
}

/* Right content */
.settings-content { flex: 1; overflow-y: auto; padding: 24px 28px 48px; min-width: 0; }
.settings-section--fullbleed { margin: 0; }
.settings-section__title { font-size: 18px; font-weight: 700; color: var(--color-text-primary); margin: 0 0 4px; }
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
  background: var(--color-switch-thumb); transition: transform 140ms;
}
:deep(.madcop-toggle--on)::after { transform: translateX(18px); }

/* Continuous Learning styles (scoped) */
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
  border-radius: 12px;
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
  border-radius: 10px;
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
  padding: 8px 12px;
  border-radius: 10px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
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
  font-family: var(--font-mono);
  font-size: 10px;
  margin-left: auto;
}
.privacy-banner {
  margin-top: 16px;
  padding: 10px 14px;
  border-radius: 12px;
  background: color-mix(in srgb, var(--color-success) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-success) 20%, transparent);
  color: var(--color-text-secondary);
  font-size: 11px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.privacy-banner code {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 1px 4px;
  background: var(--color-surface);
  border-radius: 4px;
}
.settings-row--stack {
  flex-direction: column;
  align-items: flex-start !important;
  gap: 8px;
}
.settings-btn {
  padding: 7px 12px;
  border-radius: 10px;
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
</style>

