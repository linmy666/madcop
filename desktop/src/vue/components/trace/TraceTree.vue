<script setup lang="ts">
// v3.0 — TraceTree (Vue 3)
// Direct translation of components/trace/TraceTree.tsx — same tree UI, same Tailwind classes.
import { computed, ref, watch, type Component } from 'vue'
import { useTranslation } from '../../i18n'
import type { TraceSpan, TraceViewModel } from '../../lib/traceViewModel'
import { previewTraceValue } from '../../lib/traceViewModel'
import { formatDurationMs } from '../../lib/trace/formatters'
import { iconForSpanKind, statusBadge } from '../trace/TraceBadges.vue'

export type TraceTreeFilter = 'all' | 'llm' | 'tool' | 'error'

type TreeRow = {
  span: TraceSpan
  depth: number
}

type TreeGroup = {
  turnId: string
  turnSpan: TraceSpan
  rows: TreeRow[]
  errorCount: number
}

const props = defineProps<{
  viewModel: TraceViewModel
  selectedId: string | null
}>()

const emit = defineEmits<{
  select: [spanId: string]
}>()

const t = useTranslation()

const query = ref('')
const filter = ref<TraceTreeFilter>('all')
const collapsedTurns = ref<Set<string>>(new Set())
const scrollRef = ref<HTMLDivElement | null>(null)

// ── helpers (module-level, same as React) ──────────────────────────────────

function spanDisplayTitle(span: TraceSpan, t: ReturnType<typeof useTranslation>): string {
  if (span.kind === 'llm') return span.title || t('trace.kind.llm')
  if (span.kind === 'tool') return span.title || t('trace.kind.tool')
  if (span.kind === 'tool_result') return span.title || t('trace.kind.toolResult')
  if (span.kind === 'turn') return span.title || t('trace.kind.turn')
  if (span.kind === 'session') return span.title || t('trace.kind.session')
  if (span.kind === 'event') return span.title || t('trace.kind.event')
  if (span.kind === 'message') return span.title || t('trace.kind.message')
  return span.title || ''
}

function turnDisplayTitle(_title: string, turnNumber: number, t: ReturnType<typeof useTranslation>): string {
  return t('trace.turnLabel', { index: turnNumber })
}

function filterLabel(f: TraceTreeFilter, t: ReturnType<typeof useTranslation>): string {
  switch (f) {
    case 'llm': return t('trace.filter.llm')
    case 'tool': return t('trace.filter.tools')
    case 'error': return t('trace.filter.errors')
    default: return t('trace.filter.all')
  }
}

function rowPreview(span: TraceSpan): string | null {
  if (span.kind === 'message' || span.kind === 'event') {
    const preview = span.subtitle
    return preview && preview !== 'empty' ? preview : null
  }
  return null
}

function turnPreview(turnSpan: TraceSpan, t: ReturnType<typeof useTranslation>): string {
  return turnDisplayTitle(turnSpan.title, (turnSpan.turnIndex ?? 0) + 1, t)
}

function spanSearchText(span: TraceSpan): string {
  return [
    span.title,
    span.subtitle,
    span.kind,
    span.status,
    span.toolName,
    span.toolUseId,
    span.call?.model,
    span.call?.provider?.name,
    span.call?.request.url,
    span.event?.phase,
    span.event?.message,
    span.event?.provider?.name,
    previewTraceValue(span.raw, 500),
  ].filter(Boolean).join(' ').toLowerCase()
}

function includeWithAncestors(vm: TraceViewModel, spanId: string, target: Set<string>) {
  let current = vm.spansById.get(spanId)
  while (current) {
    target.add(current.id)
    current = current.parentId ? vm.spansById.get(current.parentId) : undefined
  }
}

function filterSpanIds(vm: TraceViewModel, f: TraceTreeFilter, q: string): Set<string> {
  const normalizedQuery = q.trim().toLowerCase()
  const matched = new Set<string>()
  for (const span of vm.spans) {
    const filterMatch =
      f === 'all' ||
      (f === 'llm' && span.kind === 'llm') ||
      (f === 'tool' && (span.kind === 'tool' || span.kind === 'tool_result')) ||
      (f === 'error' && span.status === 'error')
    const queryMatch = !normalizedQuery || spanSearchText(span).includes(normalizedQuery)
    if (filterMatch && queryMatch) {
      includeWithAncestors(vm, span.id, matched)
    }
  }
  return matched
}

function computeDepths(vm: TraceViewModel): Map<string, number> {
  const depths = new Map<string, number>()
  const visit = (id: string, depth: number) => {
    depths.set(id, depth)
    const span = vm.spansById.get(id)
    if (!span) return
    for (const childId of span.childIds) visit(childId, depth + 1)
  }
  visit(vm.rootId, 0)
  return depths
}

function buildTreeGroups(vm: TraceViewModel, f: TraceTreeFilter, q: string): TreeGroup[] {
  const visibleIds = filterSpanIds(vm, f, q)
  const depthById = computeDepths(vm)
  const groupsByTurn = new Map<string, TreeGroup>()
  const groups: TreeGroup[] = []

  for (const id of vm.orderedSpanIds) {
    const span = vm.spansById.get(id)
    if (!span) continue
    if (span.kind === 'session') continue
    if (span.kind === 'turn') {
      const group: TreeGroup = { turnId: span.id, turnSpan: span, rows: [], errorCount: 0 }
      groupsByTurn.set(span.id, group)
      groups.push(group)
      continue
    }
    if (span.kind === 'tool_result') continue
    if (span.isLifecycleNoise === true) continue
    if (!visibleIds.has(span.id)) continue
    const turnId = `turn:${span.turnIndex ?? 0}`
    const group = groupsByTurn.get(turnId)
    if (!group) continue
    const depth = Math.max(0, (depthById.get(span.id) ?? 2) - 2)
    group.rows.push({ span, depth })
    if (span.status === 'error') group.errorCount += 1
  }

  return groups.filter((group) => group.rows.length > 0 || (!q.trim() && f === 'all'))
}

// ── reactive state ─────────────────────────────────────────────────────────

const groups = computed(() => buildTreeGroups(props.viewModel, filter.value, query.value))

const navigableIds = computed(() => {
  const ids: string[] = []
  for (const group of groups.value) {
    ids.push(group.turnId)
    if (collapsedTurns.value.has(group.turnId)) continue
    for (const row of group.rows) ids.push(row.span.id)
  }
  return ids
})

// scroll selected span into view
function scrollToSelected(spanId: string) {
  const container = scrollRef.value
  if (!container) return
  const tryScroll = () => {
    const row = container.querySelector<HTMLElement>(`[data-span-id="${CSS.escape(spanId)}"]`)
    if (!row) {
      requestAnimationFrame(tryScroll)
      return
    }
    row.scrollIntoView({ block: 'nearest' })
  }
  tryScroll()
}

watch(
  () => props.selectedId,
  (id) => {
    if (id) scrollToSelected(id)
  },
)

// ── interactions ───────────────────────────────────────────────────────────

function onKeyDown(event: KeyboardEvent) {
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
  const ids = navigableIds.value
  if (ids.length === 0) return
  event.preventDefault()
  const currentIndex = props.selectedId ? ids.indexOf(props.selectedId) : -1
  const nextIndex = event.key === 'ArrowDown'
    ? Math.min(ids.length - 1, currentIndex + 1)
    : Math.max(0, currentIndex <= 0 ? 0 : currentIndex - 1)
  const nextId = ids[nextIndex]
  if (nextId && nextId !== props.selectedId) emit('select', nextId)
}

function toggleTurn(turnId: string) {
  const next = new Set(collapsedTurns.value)
  if (next.has(turnId)) next.delete(turnId)
  else next.add(turnId)
  collapsedTurns.value = next
}

function handleSelect(spanId: string) {
  emit('select', spanId)
}

// ── exported sub-components (so child template tags resolve) ────────────────

const TurnGroup: Component = {
  name: 'TurnGroup',
  props: {
    group: Object as () => TreeGroup,
    collapsed: Boolean,
    selectedId: String as () => string | null,
  },
  emits: ['toggle', 'select'],
  setup(props, { emit }) {
    const t = useTranslation()
    const turnSpan = props.group.turnSpan
    const selected = props.selectedId === props.group.turnId
    const turnNumber = (turnSpan.turnIndex ?? 0) + 1
    const turnLabel = t('trace.turnLabel', { index: turnNumber })
    const preview = turnPreview(turnSpan, t)
    return { t, turnSpan, selected, turnNumber, turnLabel, preview, props }
  },
  template: `
    <section>
      <div
        class="sticky top-0 z-10 flex items-center gap-1 border-b border-[var(--color-border)]/60 bg-[var(--color-surface-container-lowest)] py-1.5 pl-1.5 pr-3"
        :class="{ 'shadow-[inset_2px_0_0_var(--color-brand)]': selected }"
      >
        <button
          type="button"
          @click="$emit('toggle')"
          :aria-label="t('trace.tree.toggleTurn')"
          :aria-expanded="!collapsed"
          class="inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-[var(--radius-sm)] text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)]"
        >
          <span class="material-symbols-outlined" style="fontVariationSettings: 'FILL' 0" :style="{ fontSize: '13px', lineHeight: '13px' }">
            {{ collapsed ? 'chevron_right' : 'chevron_down' }}
          </span>
        </button>
        <button
          type="button"
          @click="$emit('select', group.turnId)"
          :data-span-id="group.turnId"
          class="flex min-w-0 flex-1 items-baseline gap-1.5 text-left"
        >
          <span
            class="shrink-0 text-[10px] font-semibold uppercase tracking-[0.08em]"
            :class="selected ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)]'"
          >
            {{ turnLabel }}
          </span>
          <span
            v-if="preview && preview !== turnLabel"
            class="truncate text-[11px] text-[var(--color-text-tertiary)]"
          >
            {{ preview }}
          </span>
        </button>
        <span
          v-if="group.errorCount > 0"
          class="shrink-0 font-mono text-[10px] font-semibold text-[var(--color-error)]"
        >
          {{ group.errorCount }}
        </span>
      </div>
      <template v-if="!collapsed">
        <TreeRowButton
          v-for="row in group.rows"
          :key="row.span.id"
          :row="row"
          :selected="selectedId === row.span.id"
          @select="$emit('select', row.span.id)"
        />
      </template>
    </section>
  `,
}

const TreeRowButton: Component = {
  name: 'TreeRowButton',
  props: {
    row: Object as () => TreeRow,
    selected: Boolean,
  },
  emits: ['select'],
  setup(props) {
    const t = useTranslation()
    const span = props.row.span
    const preview = rowPreview(span)
    const duration = span.durationMs !== undefined ? formatDurationMs(span.durationMs) : null
    const { icon, color: iconColor } = iconForSpanKind(span.kind, span.status)
    const statusInfo = statusBadge(span.status)
    return { t, span, preview, duration, icon, iconColor, statusInfo, props }
  },
  template: `
    <button
      type="button"
      role="treeitem"
      :aria-selected="selected"
      :aria-level="row.depth + 1"
      :data-span-id="span.id"
      @click="$emit('select')"
      class="trace-row-cv relative flex h-[34px] w-full items-center gap-2 pr-3 text-left transition-colors"
      :class="selected ? 'bg-[var(--color-surface-container-high)]' : 'hover:bg-[var(--color-surface-container-low)]'"
      :style="{ paddingLeft: (12 + row.depth * 14) + 'px' }"
    >
      <span v-if="selected" class="absolute inset-y-0 left-0 w-[2px] bg-[var(--color-brand)]" aria-hidden="true"></span>
      <span class="material-symbols-outlined shrink-0" :style="{ fontSize: '16px', color: iconColor, fontVariationSettings: 'FILL 1' }">
        {{ icon }}
      </span>
      <span class="flex min-w-0 flex-1 items-baseline gap-1.5">
        <span
          class="shrink-0 truncate text-xs font-semibold"
          :class="selected ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-secondary)]'"
        >
          {{ spanDisplayTitle(span, t) }}
        </span>
        <span v-if="preview" class="truncate text-[11px] text-[var(--color-text-tertiary)]">{{ preview }}</span>
        <span
          v-if="span.isSidechain"
          class="shrink-0 rounded-[var(--radius-sm)] border border-[var(--color-border)] px-1 text-[9px] text-[var(--color-text-tertiary)]"
        >
          {{ t('trace.sidechain') }}
        </span>
      </span>
      <span v-if="duration" class="shrink-0 font-mono text-[10px] text-[var(--color-text-tertiary)]">{{ duration }}</span>
      <span
        v-if="statusInfo"
        class="material-symbols-outlined shrink-0"
        :style="{ fontSize: '14px', color: statusInfo.color, fontVariationSettings: 'FILL 1' }"
      >
        {{ statusInfo.icon }}
      </span>
    </button>
  `,
}
</script>

<template>
  <div class="flex min-h-0 flex-1 flex-col bg-[var(--color-surface-container-lowest)]" data-testid="trace-tree">
    <!-- Search bar + filter pills -->
    <div class="shrink-0 border-b border-[var(--color-border)] px-3 py-2.5">
      <label class="flex h-7 items-center gap-2 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface)] px-2 text-xs text-[var(--color-text-tertiary)]">
        <span class="material-symbols-outlined" style="fontVariationSettings: 'FILL' 0; font-size: 13px; line-height: 13px;">search</span>
        <input
          v-model="query"
          :placeholder="t('trace.searchSpans')"
          class="min-w-0 flex-1 bg-transparent text-xs text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)]"
        />
      </label>
      <div class="mt-2 flex flex-wrap gap-1">
        <button
          v-for="value in ['all', 'llm', 'tool', 'error']"
          :key="value"
          type="button"
          @click="filter = value as TraceTreeFilter"
          :class="[
            'rounded-[var(--radius-sm)] px-2 py-0.5 text-[10px] font-semibold transition-colors',
            filter === value
              ? 'bg-[var(--color-primary-container)] text-[var(--color-on-primary-container)]'
              : 'border border-[var(--color-border)] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)]'
          ]"
        >
          {{ filterLabel(value as TraceTreeFilter, t) }}
        </button>
      </div>
    </div>

    <!-- Tree -->
    <div
      ref="scrollRef"
      role="tree"
      :aria-label="t('trace.tree.aria')"
      tabindex="0"
      @keydown="onKeyDown"
      class="min-h-0 flex-1 overflow-y-auto pb-2 outline-none focus-visible:ring-1 focus-visible:ring-inset focus-visible:ring-[var(--color-border-focus)]"
    >
      <template v-if="groups.length > 0">
        <TurnGroup
          v-for="group in groups"
          :key="group.turnId"
          :group="group"
          :collapsed="collapsedTurns.has(group.turnId)"
          :selected-id="selectedId"
          @toggle="toggleTurn(group.turnId)"
          @select="handleSelect"
        />
      </template>
      <div v-else class="px-4 py-8 text-center text-xs text-[var(--color-text-tertiary)]">
        {{ t('trace.noMatchingSpans') }}
      </div>
    </div>
  </div>
</template>
