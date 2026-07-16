<script setup lang="ts">
/**
 * CommandPalette — ⌘K global command palette for MadCop
 *
 * Design philosophy:
 *   - Pure typography, zero icons. Semantics conveyed by position + weight.
 *   - Monospace for keyboard hints and numeric counters (engineer's aesthetic).
 *   - Results grouped into: 命令 / 节点 / 最近.
 *   - Keyboard-first navigation (↑↓ to move, Enter to run, Esc to close).
 *   - Graph-theory vocabulary: everything is a "node" you can activate.
 */

import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { useTabStore, SETTINGS_TAB_ID } from '../../stores/tabs'
import { useSessionStore } from '../../stores/sessionStore'

const tabStore = useTabStore()
const sessionStore = useSessionStore()

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()

// ─── State ─────────────────────────────────────────────────────────────

const query = ref('')
const selectedIndex = ref(0)
const inputRef = ref<HTMLInputElement>()

// ─── Item model ────────────────────────────────────────────────────────

interface PaletteItem {
  id: string
  group: '命令' | '节点' | '最近'
  label: string
  detail?: string
  shortcut?: string
  action: () => void
}

// ─── Source items ──────────────────────────────────────────────────────

const baseItems = computed<PaletteItem[]>(() => {
  const items: PaletteItem[] = []

  // — 命令 —
  items.push(
    {
      id: 'cmd-new-session',
      group: '命令',
      label: '新对话',
      shortcut: '⌘N',
      action: () => {
        tabStore.openTab(`session-${Date.now()}`, '新对话', 'session')
      },
    },
    {
      id: 'cmd-settings',
      group: '命令',
      label: '设置',
      shortcut: '⌘,',
      action: () => {
        tabStore.openTab(SETTINGS_TAB_ID, '设置', 'settings')
      },
    },
    {
      id: 'cmd-agent',
      group: '命令',
      label: '打开 Agent',
      detail: '多智能体编排画布',
      action: () => {
        tabStore.openTab('__agents__', 'Agent', 'agents' as any)
      },
    },
    {
      id: 'cmd-knowledge',
      group: '命令',
      label: '打开知识库',
      action: () => {
        tabStore.openTab('__knowledge__', '知识库', 'knowledge' as any)
      },
    },
    {
      id: 'cmd-arena',
      group: '命令',
      label: '打开 Arena 竞技场',
      detail: '多 LLM 并行对比',
      action: () => {
        tabStore.openTab('__arena__', 'Arena', 'arena' as any)
      },
    },
    {
      id: 'cmd-workflows',
      group: '命令',
      label: '打开工作流',
      action: () => {
        tabStore.openWorkflowsTab()
      },
    },
    {
      id: 'cmd-design',
      group: '命令',
      label: '打开设计工具',
      action: () => {
        tabStore.openDesignTab()
      },
    },
    {
      id: 'cmd-usage',
      group: '命令',
      label: '查看用量统计',
      action: () => {
        tabStore.openUsageStatsTab()
      },
    },
  )

  // — 节点 (graph nodes = agents) —
  const agentNodes = [
    { name: '代码专家', model: 'GLM-5.2', id: 'agent-code' },
    { name: '写作专家', model: 'Qwen3-80B', id: 'agent-write' },
    { name: '数据分析', model: 'DeepSeek-V3', id: 'agent-data' },
    { name: '测试专家', model: 'GLM-5.2', id: 'agent-test' },
    { name: '架构师', model: 'Qwen3-80B', id: 'agent-arch' },
  ]
  for (const a of agentNodes) {
    items.push({
      id: a.id,
      group: '节点',
      label: a.name,
      detail: a.model,
      action: () => {
        // Activate this agent node — for now, just open a new session
        tabStore.openTab(`session-${Date.now()}`, `对话 · ${a.name}`, 'session')
      },
    })
  }

  // — 最近 —
  const recentSessions = (sessionStore.sessions ?? []).slice(0, 5)
  for (const s of recentSessions) {
    items.push({
      id: `recent-${s.id}`,
      group: '最近',
      label: s.title || '未命名对话',
      detail: s.id.slice(0, 8),
      action: () => {
        tabStore.openTab(s.id, s.title || '对话', 'session')
      },
    })
  }

  return items
})

// ─── Filtering ─────────────────────────────────────────────────────────

const filteredItems = computed<PaletteItem[]>(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return baseItems.value
  return baseItems.value.filter(
    (item) =>
      item.label.toLowerCase().includes(q) ||
      (item.detail?.toLowerCase().includes(q) ?? false),
  )
})

const groupedItems = computed(() => {
  const groups: { label: string; items: PaletteItem[] }[] = []
  const order = ['命令', '最近', '节点'] as const
  for (const g of order) {
    const items = filteredItems.value.filter((i) => i.group === g)
    if (items.length > 0) groups.push({ label: g, items })
  }
  return groups
})

// ─── Keyboard navigation ───────────────────────────────────────────────

function moveSelection(delta: number) {
  const total = filteredItems.value.length
  if (total === 0) return
  selectedIndex.value = (selectedIndex.value + delta + total) % total
}

function executeSelected() {
  const item = filteredItems.value[selectedIndex.value]
  if (item) {
    item.action()
    emit('close')
  }
}

function onKeydown(e: KeyboardEvent) {
  // ⌘K toggles
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
    e.preventDefault()
    if (props.open) emit('close')
    else {
      // Notify parent to open — we use a custom event for this
      window.dispatchEvent(new CustomEvent('madcop:command-palette-toggle'))
    }
    return
  }
  if (!props.open) return
  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      moveSelection(1)
      break
    case 'ArrowUp':
      e.preventDefault()
      moveSelection(-1)
      break
    case 'Enter':
      e.preventDefault()
      executeSelected()
      break
    case 'Escape':
      e.preventDefault()
      emit('close')
      break
  }
}

// ─── Lifecycle ─────────────────────────────────────────────────────────

watch(
  () => props.open,
  (open) => {
    if (open) {
      query.value = ''
      selectedIndex.value = 0
      nextTick(() => inputRef.value?.focus())
    }
  },
)

// Reset selection when query changes
watch(query, () => {
  selectedIndex.value = 0
})

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))
</script>

<template>
  <Transition name="palette-fade">
    <div
      v-if="open"
      class="fixed inset-0 z-[9999] flex items-start justify-center pt-[15vh] bg-black/20 backdrop-blur-[2px]"
      @click.self="emit('close')"
    >
      <div
        class="w-[560px] max-w-[90vw] overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-2xl"
      >
        <!-- Search input — minimal, no search icon, just a blinking caret -->
        <div class="flex items-center px-4 py-3 border-b border-[var(--color-border-separator)]">
          <input
            ref="inputRef"
            v-model="query"
            type="text"
            class="flex-1 bg-transparent text-[15px] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:outline-none"
            placeholder="输入命令、节点名称…"
            spellcheck="false"
            autocomplete="off"
          />
          <kbd
            class="ml-3 shrink-0 rounded border border-[var(--color-border)] px-1.5 py-0.5 text-[10px] tabular-nums text-[var(--color-text-tertiary)]"
            style="font-family: ui-monospace, 'SF Mono', monospace"
          >
            Esc
          </kbd>
        </div>

        <!-- Results — grouped, flat, typography-driven -->
        <div class="max-h-[360px] overflow-y-auto py-2">
          <template v-if="groupedItems.length > 0">
            <div v-for="group in groupedItems" :key="group.label" class="mb-1">
              <!-- Group header: monospace uppercase, like a section in a spec doc -->
              <div
                class="px-4 py-1 text-[10px] uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]"
                style="font-family: ui-monospace, 'SF Mono', monospace"
              >
                {{ group.label }}
              </div>
              <!-- Items -->
              <button
                v-for="(item, idx) in group.items"
                :key="item.id"
                type="button"
                :class="[
                  'flex w-full items-center px-4 py-2 text-left transition-colors',
                  selectedIndex ===
                    filteredItems.findIndex((i) => i.id === item.id)
                    ? 'bg-[var(--color-sidebar-item-active)]'
                    : 'hover:bg-[var(--color-sidebar-item-hover)]',
                ]"
                @click="executeSelected()"
                @mousemove="selectedIndex = filteredItems.findIndex((i) => i.id === item.id)"
              >
                <!-- Label -->
                <span class="flex-1 truncate text-[13px] text-[var(--color-text-primary)]">
                  {{ item.label }}
                </span>
                <!-- Detail (model name, session ID) -->
                <span
                  v-if="item.detail"
                  class="mr-3 text-[11px] text-[var(--color-text-tertiary)]"
                  style="font-family: ui-monospace, 'SF Mono', monospace"
                >
                  {{ item.detail }}
                </span>
                <!-- Shortcut -->
                <kbd
                  v-if="item.shortcut"
                  class="shrink-0 text-[10px] tabular-nums text-[var(--color-text-tertiary)]"
                  style="font-family: ui-monospace, 'SF Mono', monospace"
                >
                  {{ item.shortcut }}
                </kbd>
              </button>
            </div>
          </template>

          <!-- Empty state -->
          <div v-else class="px-4 py-8 text-center">
            <div class="text-[13px] text-[var(--color-text-tertiary)]">无匹配结果</div>
            <div
              class="mt-1 text-[10px] uppercase tracking-[0.14em] text-[var(--color-text-tertiary)] opacity-60"
              style="font-family: ui-monospace, 'SF Mono', monospace"
            >
              ∅ empty set
            </div>
          </div>
        </div>

        <!-- Footer — keyboard hints -->
        <div
          class="flex items-center justify-between border-t border-[var(--color-border-separator)] px-4 py-2 text-[10px] text-[var(--color-text-tertiary)]"
          style="font-family: ui-monospace, 'SF Mono', monospace"
        >
          <div class="flex items-center gap-3">
            <span><kbd class="font-sans">↑↓</kbd> 导航</span>
            <span><kbd class="font-sans">↵</kbd> 执行</span>
            <span><kbd class="font-sans">Esc</kbd> 关闭</span>
          </div>
          <div class="tabular-nums">
            {{ filteredItems.length }} items
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.palette-fade-enter-active,
.palette-fade-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}
.palette-fade-enter-from,
.palette-fade-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}

/* Remove default kbd styling inside footer */
kbd {
  font-family: inherit;
}
</style>
