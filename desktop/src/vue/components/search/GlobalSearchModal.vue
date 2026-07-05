<script setup lang="ts">
/**
 * GlobalSearchModal — Vue 3 port of components/search/GlobalSearchModal.tsx
 * Full-translation search modal with debounced query, keyboard navigation,
 * and result highlighting. Teleport replaces createPortal.
 */
import { ref, computed, watch, nextTick, h } from 'vue'
import { useTranslation } from '../../i18n'
import { useSessionStore } from '../../stores/sessionStore'
import { useTabStore } from '../../stores/tabStore'
import { searchApi, type SessionMatch, type SessionMatchRole } from '../../api/search'

const DEBOUNCE_MS = 250
const RECENT_LIMIT = 8
const SEARCH_LIMIT = 50
const MATCH_PREVIEW_PER_SESSION = 3

interface Props {
  open: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{ (e: 'close'): void }>()

// ─── Reactive state ────────────────────────────────────────────────
const query = ref('')
const debouncedQuery = ref('')
const results = ref<any[]>([])
const loading = ref(false)
const error = ref(false)
const truncated = ref(false)
const activeIndex = ref(0)

const inputRef = ref<HTMLInputElement | null>(null)
const listRef = ref<HTMLDivElement | null>(null)
const requestIdRef = ref(0)

// ─── i18n ──────────────────────────────────────────────────────────
const t = useTranslation()

// ─── Store access ──────────────────────────────────────────────────
const sessions = computed(() => useSessionStore().sessions)

// ─── Debounced query ───────────────────────────────────────────────
let debounceTimer: ReturnType<typeof setTimeout> | null = null
watch(query, (newQuery) => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    debouncedQuery.value = newQuery
  }, DEBOUNCE_MS)
})

// ─── Run search on debounced query change ──────────────────────────
watch(debouncedQuery, () => {
  activeIndex.value = 0
  const q = debouncedQuery.value.trim()
  if (!q) {
    results.value = []
    loading.value = false
    error.value = false
    truncated.value = false
    return
  }

  const reqId = ++requestIdRef.value
  loading.value = true
  error.value = false
  searchApi
    .searchSessions(q, { limit: SEARCH_LIMIT })
    .then((resp) => {
      if (reqId !== requestIdRef.value) return
      results.value = resp.results
      truncated.value = resp.truncated
      loading.value = false
    })
    .catch(() => {
      if (reqId !== requestIdRef.value) return
      results.value = []
      error.value = true
      loading.value = false
    })
})

// ─── Recent sessions (sorted) ──────────────────────────────────────
const recentSessions = computed(() =>
  [...sessions.value]
    .sort((a, b) =>
      a.modifiedAt < b.modifiedAt ? 1 : a.modifiedAt > b.modifiedAt ? -1 : 0
    )
    .slice(0, RECENT_LIMIT),
)

// ─── Derived state ─────────────────────────────────────────────────
interface Row {
  sessionId: string
  title: string
  projectPath: string
  workDir: string | null
  modifiedAt: string
  matchCount: number
  matches: SessionMatch[]
}

const isSearching = computed(() => debouncedQuery.value.trim().length > 0)

const rows = computed<Row[]>(() => {
  if (!isSearching.value) {
    return recentSessions.value.map((s) => ({
      sessionId: s.id,
      title: s.title,
      projectPath: s.projectPath,
      workDir: s.workDir,
      modifiedAt: s.modifiedAt,
      matchCount: 0,
      matches: [],
    }))
  }
  return results.value.map((r) => ({
    sessionId: r.sessionId,
    title: r.title,
    projectPath: r.projectPath,
    workDir: r.workDir,
    modifiedAt: r.modifiedAt,
    matchCount: r.matchCount,
    matches: r.matches,
  }))
})

// ─── Keep active row in view ───────────────────────────────────────
watch(activeIndex, () => {
  nextTick(() => {
    const el = listRef.value?.querySelector(`[data-index="${activeIndex.value}"]`)
    el?.scrollIntoView({ block: 'nearest' })
  })
})

// ─── Row interaction ───────────────────────────────────────────────
function openRow(row: Row) {
  useTabStore().openTab(row.sessionId, row.title)
  emit('close')
}

// ─── Keyboard handler ──────────────────────────────────────────────
function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIndex.value = Math.min(activeIndex.value + 1, rows.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIndex.value = Math.max(activeIndex.value - 1, 0)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const row = rows.value[activeIndex.value]
    if (row) openRow(row)
  } else if (e.key === 'Escape') {
    e.preventDefault()
    emit('close')
  }
}

// ─── Reset + focus when modal opens ────────────────────────────────
watch(
  () => props.open,
  (open) => {
    if (!open) return
    query.value = ''
    debouncedQuery.value = ''
    results.value = []
    error.value = false
    truncated.value = false
    activeIndex.value = 0
    requestIdRef.value += 1
    nextTick(() => {
      inputRef.value?.focus()
    })
  },
)

// ─── Helper functions ──────────────────────────────────────────────
function projectLabel(row: Row): string {
  const candidate = row.workDir || row.projectPath
  if (!candidate) return ''
  const segments = candidate.split('/').filter(Boolean)
  return segments[segments.length - 1] ?? candidate
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr)
  const timestamp = date.getTime()
  if (!Number.isFinite(timestamp)) return ''

  const diff = Date.now() - timestamp
  const min = Math.floor(diff / 60000)
  if (min < 1) return t('session.timeJustNow')
  if (min < 60) return t('session.timeMinutes', { n: min })
  const hr = Math.floor(min / 60)
  if (hr < 24) return t('session.timeHours', { n: hr })
  const day = Math.floor(hr / 24)
  if (day < 30) return t('session.timeDays', { n: day })
  return new Intl.DateTimeFormat(undefined, { month: 'numeric', day: 'numeric' }).format(date)
}

// ─── Sub-components (rendered inline in template) ──────────────────

// RoleBadge: a small badge showing 'You' or 'Assistant'
const RoleBadge = {
  props: {
    role: { type: String as () => SessionMatchRole, required: true },
  },
  setup(props: { role: SessionMatchRole }) {
    return () => {
      const isUser = props.role === 'user'
      return h(
        'span',
        {
          class: [
            'mt-px shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium leading-none',
            isUser
              ? 'bg-[var(--color-brand)]/15 text-[var(--color-brand)]'
              : 'bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)]',
          ],
        },
        isUser ? t('search.global.roleUser') : t('search.global.roleAssistant'),
      )
    }
  },
}

// ResultRow: rendered inline in template via the parent's own logic
// (We use template blocks directly for ResultRow to keep it clean.)
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="fixed inset-0 z-50 flex items-start justify-center pt-[12vh]">
      <div
        class="absolute inset-0 bg-[var(--color-overlay-scrim)] transition-opacity duration-200"
        @click="emit('close')"
      />

      <div
        class="glass-panel relative z-10 flex max-h-[70vh] w-[640px] max-w-[calc(100vw-48px)] flex-col overflow-hidden rounded-[var(--radius-xl)]"
        role="dialog"
        aria-modal="true"
        :aria-label="t('search.global.placeholder')"
      >
        <!-- Search input -->
        <div class="flex items-center gap-2.5 border-b border-[var(--color-border)] px-4 py-3">
          <span class="material-symbols-outlined h-4 w-4 shrink-0 text-[var(--color-text-tertiary)]">search</span>
          <input
            ref="inputRef"
            type="text"
            :value="query"
            @input="(e) => (query = (e.target as HTMLInputElement).value)"
            @keydown="handleKeyDown"
            :placeholder="t('search.global.placeholder')"
            :aria-label="t('search.global.placeholder')"
            class="min-w-0 flex-1 bg-transparent text-sm text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)]"
          />
          <span
            v-if="loading"
            class="material-symbols-outlined animate-spin text-[16px] text-[var(--color-text-tertiary)]"
          >
            progress_activity
          </span>
          <button
            type="button"
            @click="emit('close')"
            :aria-label="t('search.global.close')"
            :title="t('search.global.close')"
            class="flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
          >
            <span class="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>

        <!-- Results -->
        <div ref="listRef" class="min-h-0 flex-1 overflow-y-auto py-1.5" role="listbox">
          <!-- Recent sessions -->
          <template v-if="!isSearching">
            <div v-if="rows.length > 0" class="px-4 pb-1 pt-1.5 text-[11px] font-medium uppercase tracking-wide text-[var(--color-text-tertiary)]">
              {{ t('search.global.recentTitle') }}
            </div>
            <button
              v-for="(row, i) in rows"
              :key="row.sessionId"
              type="button"
              :data-index="i"
              role="option"
              :aria-selected="i === activeIndex"
              @mouseenter="activeIndex = i"
              @click="openRow(row)"
              :class="[
                'flex w-full flex-col gap-0.5 px-4 py-2 text-left transition-colors focus-visible:outline-none',
                { 'bg-[var(--color-surface-hover)]': i === activeIndex },
              ]"
            >
              <div class="flex items-center gap-2">
                <span class="min-w-0 flex-1 truncate text-sm font-medium text-[var(--color-text-primary)]">
                  {{ row.title }}
                </span>
                <span class="shrink-0 text-[10px] tabular-nums text-[var(--color-text-tertiary)]">
                  {{ formatRelativeTime(row.modifiedAt) }}
                </span>
              </div>
              <div class="flex items-center gap-1.5 text-[11px] text-[var(--color-text-tertiary)]">
                <span class="min-w-0 truncate">{{ projectLabel(row) }}</span>
                <template v-if="row.matchCount > 0">
                  <span aria-hidden="true">·</span>
                  <span class="shrink-0">{{ t('search.global.matchCount', { count: row.matchCount }) }}</span>
                </template>
              </div>
            </button>
          </template>

          <!-- Loading -->
          <div v-else-if="loading && results.length === 0" class="px-4 py-8 text-center text-xs text-[var(--color-text-tertiary)]">
            {{ t('search.global.loading') }}
          </div>

          <!-- Error -->
          <div v-else-if="error" class="px-4 py-8 text-center text-xs text-[var(--color-error)]">
            {{ t('search.global.error') }}
          </div>

          <!-- No results -->
          <div v-else-if="rows.length === 0" class="px-4 py-8 text-center text-xs text-[var(--color-text-tertiary)]">
            {{ t('search.global.noResults') }}
          </div>

          <!-- Search results -->
          <template v-else>
            <button
              v-for="(row, i) in rows"
              :key="row.sessionId"
              type="button"
              :data-index="i"
              role="option"
              :aria-selected="i === activeIndex"
              @mouseenter="activeIndex = i"
              @click="openRow(row)"
              :class="[
                'flex w-full flex-col gap-0.5 px-4 py-2 text-left transition-colors focus-visible:outline-none',
                { 'bg-[var(--color-surface-hover)]': i === activeIndex },
              ]"
            >
              <div class="flex items-center gap-2">
                <span class="min-w-0 flex-1 truncate text-sm font-medium text-[var(--color-text-primary)]">
                  {{ row.title }}
                </span>
                <span class="shrink-0 text-[10px] tabular-nums text-[var(--color-text-tertiary)]">
                  {{ formatRelativeTime(row.modifiedAt) }}
                </span>
              </div>
              <div class="flex items-center gap-1.5 text-[11px] text-[var(--color-text-tertiary)]">
                <span class="min-w-0 truncate">{{ projectLabel(row) }}</span>
                <template v-if="row.matchCount > 0">
                  <span aria-hidden="true">·</span>
                  <span class="shrink-0">{{ t('search.global.matchCount', { count: row.matchCount }) }}</span>
                </template>
              </div>
              <!-- Match previews -->
              <div
                v-for="(m, j) in row.matches.slice(0, MATCH_PREVIEW_PER_SESSION)"
                :key="`${m.lineNumber}-${j}`"
                class="mt-0.5 flex items-start gap-2"
              >
                <RoleBadge :role="m.role" />
                <span class="min-w-0 flex-1 truncate text-[12px] text-[var(--color-text-secondary)]">
                  <!-- Highlighted snippet: render parts inline -->
                  <template
                    v-for="(part, pi) in renderHighlightedParts(m.snippet, m.highlights)"
                    :key="pi"
                  >
                    <mark
                      v-if="part.highlighted"
                      class="rounded-[3px] bg-[var(--color-brand)]/25 px-0.5 text-[var(--color-text-primary)]"
                    >
                      {{ part.text }}
                    </mark>
                    <span v-else>{{ part.text }}</span>
                  </template>
                </span>
              </div>
            </button>
            <div v-if="truncated" class="px-4 py-2 text-center text-[11px] text-[var(--color-text-tertiary)]">
              {{ t('search.global.truncated', { count: SEARCH_LIMIT }) }}
            </div>
          </template>
        </div>

        <!-- Footer hints -->
        <div class="flex items-center gap-1.5 border-t border-[var(--color-border)] px-4 py-1.5 text-[10px] text-[var(--color-text-tertiary)]">
          <kbd class="rounded border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-1 py-0.5 font-mono">↑↓</kbd>
          <span>{{ t('fileSearch.navigate') }}</span>
          <kbd class="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-1 py-0.5 font-mono">Enter</kbd>
          <span>{{ t('fileSearch.select') }}</span>
          <kbd class="ml-2 rounded border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-1 py-0.5 font-mono">Esc</kbd>
          <span>{{ t('fileSearch.close') }}</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>
