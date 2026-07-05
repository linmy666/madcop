<script setup lang="ts">
// v3.0 — Agent Hub: the entry point for MadCop's Agent Network.
// Shows available agents (local + hub), status, and quick actions.
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'

interface Agent {
  id: string
  name: string
  description: string
  icon: string          // material-symbols name
  model: string
  status: 'online' | 'offline' | 'busy'
  capabilities: string[]
  source: 'builtin' | 'installed' | 'hub'
  rating?: number
  installs?: number
}

// ── Built-in agents ────────────────────────────────────────────────
const builtins: Agent[] = [
  { id: 'assistant', name: '通用助手', description: '全能型对话 agent，适合日常问题、代码编写和一般任务。', icon: 'smart_toy', model: 'GLM-5.2', status: 'online', capabilities: ['对话', '代码', '工具调用', '文件读写'], source: 'builtin' },
  { id: 'coder', name: '编码专家', description: '专注于代码生成、审查和调试。多文件编辑能力强。', icon: 'code', model: 'DeepSeek-V4', status: 'online', capabilities: ['代码生成', '代码审查', '调试', '重构'], source: 'builtin' },
  { id: 'designer', name: '设计助手', description: '生成 UI 原型和设计稿。集成 DesignCanvas。', icon: 'palette', model: 'GLM-5.2', status: 'online', capabilities: ['UI 设计', '原型生成', 'CSS 编写'], source: 'builtin' },
  { id: 'researcher', name: '研究员', description: '联网搜索、资料整理、报告生成。', icon: 'travel_explore', model: 'Qwen3-80B', status: 'online', capabilities: ['网页搜索', '信息提取', '报告生成'], source: 'builtin' },
  { id: 'planner', name: '规划师', description: '将复杂任务分解为多步骤计划，协调其他 agent。', icon: 'account_tree', model: 'GLM-5.2', status: 'online', capabilities: ['任务分解', '协调', '调度'], source: 'builtin' },
  { id: 'reviewer', name: '审查员', description: '代码审查、安全审计、质量检查。', icon: 'rate_review', model: 'DeepSeek-V4', status: 'offline', capabilities: ['代码审查', '安全审计', '性能分析'], source: 'builtin' },
]

// ── Hub agents (discoverable) ──────────────────────────────────────
const hubAgents: Agent[] = [
  { id: 'data-analyst', name: '数据分析师', description: 'SQL 查询、Excel 处理、数据可视化图表。', icon: 'bar_chart', model: 'GPT-5.4', status: 'offline', capabilities: ['SQL', '数据分析', '图表'], source: 'hub', rating: 4.8, installs: 1240 },
  { id: 'translator', name: '翻译官', description: '中英日韩等多语言翻译，保留格式。', icon: 'translate', model: 'GLM-5.2', status: 'offline', capabilities: ['翻译', '本地化', '校对'], source: 'hub', rating: 4.6, installs: 892 },
  { id: 'devops', name: '运维助手', description: 'Docker/K8s/CI-CD 管道管理。', icon: 'terminal', model: 'DeepSeek-V4', status: 'offline', capabilities: ['Docker', 'K8s', 'CI/CD'], source: 'hub', rating: 4.7, installs: 567 },
  { id: 'writer', name: '写作助手', description: '营销文案、技术文档、创意写作。', icon: 'edit_note', model: 'GLM-5.2', status: 'offline', capabilities: ['写作', '润色', '摘要'], source: 'hub', rating: 4.5, installs: 2103 },
]

const search = ref('')
const activeTab = ref<'local' | 'hub'>('local')
const installing = ref<Set<string>>(new Set())

const filtered = computed(() => {
  const pool = activeTab.value === 'local' ? builtins : hubAgents
  const q = search.value.trim().toLowerCase()
  if (!q) return pool
  return pool.filter(a => a.name.toLowerCase().includes(q) || a.description.toLowerCase().includes(q) || a.capabilities.some(c => c.includes(q)))
})

function installAgent(id: string) {
  installing.value.add(id)
  setTimeout(() => {
    installing.value.delete(id)
    // In real app: POST /api/agents/install
  }, 1500)
}

function openChat(id: string) {
  // In real app: navigate to a new session with this agent
}

function openConfig(id: string) {
  // In real app: open Agent Detail page
}
</script>

<template>
  <div class="agent-hub">
    <div class="agent-hub__inner">
      <!-- Header -->
      <div class="agent-hub__head">
        <div>
          <h1 class="agent-hub__title">Agent Network</h1>
          <p class="agent-hub__sub">发现、配置和编排你的 AI agent 团队。内置 6 个专业 agent，hub 上有更多。</p>
        </div>
      </div>

      <!-- Search -->
      <div class="agent-hub__search">
        <span class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)]">search</span>
        <input v-model="search" type="text" placeholder="搜索 agent 名称、描述或能力..." class="agent-hub__search-input" />
      </div>

      <!-- Tabs -->
      <div class="agent-hub__tabs">
        <button :class="['agent-hub__tab', { 'agent-hub__tab--active': activeTab === 'local' }]" @click="activeTab = 'local'">
          我的 Agents ({{ builtins.length }})
        </button>
        <button :class="['agent-hub__tab', { 'agent-hub__tab--active': activeTab === 'hub' }]" @click="activeTab = 'hub'">
          Agent Hub ({{ hubAgents.length }})
        </button>
      </div>

      <!-- Agent Grid -->
      <div class="agent-hub__grid">
        <div v-for="agent in filtered" :key="agent.id" class="agent-card" @click="openChat(agent.id)">
          <div class="agent-card__head">
            <div class="agent-card__icon" :class="`agent-card__icon--${agent.status}`">
              <span class="material-symbols-outlined text-[22px]">{{ agent.icon }}</span>
            </div>
            <div class="agent-card__info">
              <div class="agent-card__name">{{ agent.name }}</div>
              <div class="agent-card__model">{{ agent.model }}</div>
            </div>
            <div class="agent-card__status" :class="`agent-card__status--${agent.status}`">
              <span class="agent-card__dot" />
              {{ agent.status === 'online' ? '在线' : agent.status === 'busy' ? '忙碌' : '离线' }}
            </div>
          </div>

          <p class="agent-card__desc">{{ agent.description }}</p>

          <!-- Capabilities -->
          <div class="agent-card__caps">
            <span v-for="cap in agent.capabilities" :key="cap" class="agent-card__cap">{{ cap }}</span>
          </div>

          <!-- Hub-specific: rating + installs -->
          <div v-if="agent.source === 'hub'" class="agent-card__meta">
            <span class="agent-card__rating">★ {{ agent.rating }}</span>
            <span class="agent-card__installs">{{ agent.installs }} 次安装</span>
          </div>

          <!-- Actions -->
          <div class="agent-card__actions">
            <button
              v-if="agent.source === 'hub'"
              :class="['agent-card__btn', { 'agent-card__btn--loading': installing.has(agent.id) }]"
              @click.stop="installAgent(agent.id)"
            >
              {{ installing.has(agent.id) ? '安装中…' : '安装' }}
            </button>
            <button class="agent-card__btn agent-card__btn--outline" @click.stop="openConfig(agent.id)">
              配置
            </button>
            <button class="agent-card__btn agent-card__btn--ghost" @click.stop="openChat(agent.id)">
              对话
            </button>
          </div>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="filtered.length === 0" class="agent-hub__empty">
        <span class="material-symbols-outlined text-[48px] text-[var(--color-text-tertiary)]">search_off</span>
        <p>没有找到匹配的 agent。试试其他关键词。</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.agent-hub {
  width: 100%; height: 100%;
  overflow-y: auto;
  background: var(--color-surface);
}
.agent-hub__inner {
  max-width: 1080px; margin: 0 auto;
  padding: 32px 24px;
}
.agent-hub__head { margin-bottom: 24px; }
.agent-hub__title { font-size: 26px; font-weight: 700; color: var(--color-text-primary); letter-spacing: -0.025em; margin: 0; }
.agent-hub__sub   { font-size: 14px; color: var(--color-text-secondary); margin-top: 6px; line-height: 1.5; }

.agent-hub__search {
  display: flex; align-items: center; gap: 10px;
  padding: 10px 14px;
  border: 1.5px solid var(--color-border);
  background: var(--color-surface-container-lowest);
  margin-bottom: 20px;
}
.agent-hub__search-input {
  flex: 1; border: none; outline: none; background: transparent;
  font-size: 14px; color: var(--color-text-primary);
}

.agent-hub__tabs {
  display: flex; gap: 0; margin-bottom: 20px;
  border-bottom: 1.5px solid var(--color-border);
}
.agent-hub__tab {
  padding: 10px 20px; font-size: 13px; font-weight: 500;
  cursor: pointer; background: transparent; border: none;
  border-bottom: 2px solid transparent;
  color: var(--color-text-secondary);
  transition: all 140ms;
}
.agent-hub__tab--active {
  color: var(--color-primary);
  border-bottom-color: var(--color-primary);
}

.agent-hub__grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 16px; }

.agent-card {
  background: var(--color-surface-container-lowest);
  border: 1.5px solid var(--color-border);
  padding: 20px;
  cursor: pointer;
  transition: box-shadow 140ms, border-color 140ms;
}
.agent-card:hover { border-color: var(--color-primary); box-shadow: 0 0 0 2px rgba(124, 58, 237, 0.08); }
.agent-card__head { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.agent-card__icon {
  width: 44px; height: 44px; display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}
.agent-card__icon--online  { background: var(--color-primary-fixed); color: var(--color-primary); }
.agent-card__icon--busy   { background: var(--color-warning-container); color: var(--color-warning); }
.agent-card__icon--offline { background: var(--color-surface-container-high); color: var(--color-text-tertiary); }
.agent-card__info { flex: 1; min-width: 0; }
.agent-card__name  { font-size: 15px; font-weight: 600; color: var(--color-text-primary); }
.agent-card__model { font-size: 11px; color: var(--color-text-tertiary); font-family: var(--font-mono); }
.agent-card__status { display: flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 500; white-space: nowrap; }
.agent-card__dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.agent-card__status--online  .agent-card__dot { background: var(--color-success); }
.agent-card__status--busy   .agent-card__dot { background: var(--color-warning); }
.agent-card__status--offline .agent-card__dot { background: var(--color-text-tertiary); }
.agent-card__status--online  { color: var(--color-success); }
.agent-card__status--busy   { color: var(--color-warning); }
.agent-card__status--offline { color: var(--color-text-tertiary); }

.agent-card__desc { font-size: 13px; color: var(--color-text-secondary); line-height: 1.5; margin-bottom: 12px; }
.agent-card__caps { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.agent-card__cap {
  padding: 3px 8px; font-size: 11px; font-weight: 500;
  background: var(--color-primary-fixed); color: var(--color-primary);
  border-radius: 4px;
}
.agent-card__meta { display: flex; gap: 16px; margin-bottom: 12px; font-size: 12px; color: var(--color-text-tertiary); }
.agent-card__rating { color: #CA8A04; }
.agent-card__actions { display: flex; gap: 8px; margin-top: 4px; }
.agent-card__btn {
  padding: 6px 14px; font-size: 12px; font-weight: 500; cursor: pointer;
  border: 1.5px solid var(--color-primary);
  background: var(--color-primary); color: var(--color-on-primary);
  transition: opacity 140ms;
}
.agent-card__btn--outline { background: transparent; color: var(--color-text-primary); border-color: var(--color-border); }
.agent-card__btn--ghost   { background: transparent; color: var(--color-text-secondary); border-color: transparent; }
.agent-card__btn--loading { opacity: 0.6; cursor: wait; }

.agent-hub__empty {
  text-align: center; padding: 60px 20px;
  color: var(--color-text-secondary); font-size: 14px;
}
</style>