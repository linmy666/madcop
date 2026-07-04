<script setup lang="ts">
// v3.0 — MadCop Sidebar (Vue 3)
// Flat nav list. 3px accent rail on active. 52px collapsed.

import { ref, computed } from 'vue'

export type MadcopSection =
  | 'chat' | 'threads' | 'skills' | 'memory' | 'agents'
  | 'workflow' | 'design' | 'trace' | 'teams'
  | 'doctor' | 'diagnostics' | 'activity' | 'schedule'
  | 'browser' | 'terminal'
  | 'settings'

const props = defineProps<{ active: MadcopSection; collapsed?: boolean }>()
const emit = defineEmits<{ (e: 'select', id: MadcopSection): void }>()

interface NavLink {
  id: MadcopSection
  label: string
  glyph: string
  group: 'work' | 'tools' | 'system'
}

const NAV: NavLink[] = [
  { id: 'chat',        label: '会话',   glyph: '◇', group: 'work' },
  { id: 'threads',     label: '主题',   glyph: '◫', group: 'work' },
  { id: 'skills',      label: '技能',   glyph: '◐', group: 'work' },
  { id: 'memory',      label: '记忆',   glyph: '◉', group: 'work' },
  { id: 'agents',      label: '代理',   glyph: '◈', group: 'work' },
  { id: 'workflow',    label: '工作流', glyph: '⬡', group: 'tools' },
  { id: 'design',      label: '设计',   glyph: '◰', group: 'tools' },
  { id: 'trace',       label: '追踪',   glyph: '∿', group: 'tools' },
  { id: 'teams',       label: '团队',   glyph: '⏣', group: 'tools' },
  { id: 'browser',     label: '浏览器', glyph: '◯', group: 'system' },
  { id: 'terminal',    label: '终端',   glyph: '▣', group: 'system' },
  { id: 'doctor',      label: '诊断',   glyph: '✚', group: 'system' },
  { id: 'diagnostics', label: '日志',   glyph: '◔', group: 'system' },
  { id: 'activity',    label: '活动',   glyph: '◭', group: 'system' },
  { id: 'schedule',    label: '计划',   glyph: '◷', group: 'system' },
  { id: 'settings',    label: '设置',   glyph: '⚙', group: 'system' },
]

const GROUP_LABELS: Record<NavLink['group'], string> = {
  work: '工作区', tools: '工具', system: '系统',
}

const query = ref('')
const groups: Array<NavLink['group']> = ['work', 'tools', 'system']

const filtered = computed(() => {
  const q = query.value.trim().toLowerCase()
  return q ? NAV.filter((n) => n.label.toLowerCase().includes(q)) : NAV
})

function selectLink(id: MadcopSection) { emit('select', id) }
</script>

<template>
  <div class="madcop-sidebar">
    <div class="madcop-sidebar__brand">
      <div class="madcop-sidebar__brand-mark">M</div>
      <div v-if="!collapsed" class="madcop-sidebar__brand-meta">
        <div class="madcop-sidebar__brand-name">MadCop</div>
        <div class="madcop-sidebar__brand-sub">v3.0 · engineering</div>
      </div>
    </div>

    <div v-if="!collapsed" class="madcop-sidebar__search">
      <div class="madcop-sidebar__search-inner">
        <span class="madcop-sidebar__search-icon">⌕</span>
        <input
          v-model="query"
          type="text"
          placeholder="搜索面板..."
          class="madcop-sidebar__search-input"
        />
      </div>
    </div>

    <nav class="madcop-sidebar__nav">
      <div v-for="g in groups" :key="g" class="madcop-sidebar__group">
        <div v-if="!collapsed" class="madcop-eyebrow madcop-sidebar__group-label">
          {{ GROUP_LABELS[g] }}
        </div>
        <button
          v-for="link in filtered.filter((n) => n.group === g)"
          :key="link.id"
          :class="[
            'madcop-sidebar__link',
            { 'madcop-sidebar__link--active': active === link.id },
          ]"
          :title="collapsed ? link.label : undefined"
          @click="selectLink(link.id)"
        >
          <span v-if="active === link.id" class="madcop-sidebar__rail" />
          <span class="madcop-sidebar__glyph">{{ link.glyph }}</span>
          <span v-if="!collapsed" class="madcop-sidebar__label">{{ link.label }}</span>
        </button>
      </div>
    </nav>
  </div>
</template>

<style scoped>
.madcop-sidebar {
  width: 100%; height: 100%;
  display: flex; flex-direction: column;
  background: var(--madcop-panel-raised);
  font-size: 13px;
}
.madcop-sidebar__brand {
  padding: 12px 16px;
  border-bottom: 1.5px solid var(--madcop-line);
  display: flex; align-items: center; gap: 8px;
  min-height: 32px;
}
.madcop-sidebar__brand-mark {
  width: 20px; height: 20px;
  background: var(--madcop-accent);
  display: flex; align-items: center; justify-content: center;
  color: var(--madcop-accent-ink);
  font-weight: 700; font-size: 11px;
}
.madcop-sidebar__brand-name { font-weight: 600; font-size: 14px; color: var(--madcop-ink); line-height: 1.1; }
.madcop-sidebar__brand-sub  { font-size: 10px; color: var(--madcop-ink-muted); font-family: 'Geist Mono', monospace; line-height: 1.1; }

.madcop-sidebar__search { padding: 12px; }
.madcop-sidebar__search-inner {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 10px;
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-sunken);
}
.madcop-sidebar__search-icon { color: var(--madcop-ink-muted); font-size: 13px; }
.madcop-sidebar__search-input {
  border: none; outline: none; background: transparent;
  flex: 1; font-size: 13px; color: var(--madcop-ink);
}

.madcop-sidebar__nav { flex: 1; overflow-y: auto; padding: 8px 0; }
.madcop-sidebar__group { margin-bottom: 12px; }
.madcop-sidebar__group-label { padding: 0 16px; margin-bottom: 6px; }

.madcop-sidebar__link {
  position: relative;
  display: flex; align-items: center; gap: 12px;
  width: 100%;
  padding: 6px 16px;
  border: none; background: transparent; cursor: pointer; text-align: left;
  color: var(--madcop-ink-body);
  font-size: 13px;
}
.madcop-sidebar__link:hover { background: var(--madcop-panel-sunken); }
.madcop-sidebar__link--active {
  color: var(--madcop-accent);
  font-weight: 600;
  background: transparent;
}
.madcop-sidebar__link--active:hover { background: var(--madcop-panel-sunken); }
.madcop-sidebar__rail {
  position: absolute; left: 0; top: 0; bottom: 0;
  width: 3px; background: var(--madcop-accent);
}
.madcop-sidebar__glyph {
  width: 16px; font-size: 14px; text-align: center;
  font-family: 'Geist Mono', monospace;
  opacity: 0.7;
}
.madcop-sidebar__link--active .madcop-sidebar__glyph { opacity: 1; }
.madcop-sidebar__label { flex: 1; }
</style>
