<script setup lang="ts">
// v3.0 — DirectoryPicker (Vue 3, ref-tdz-fixed)
// CRITICAL: no variable named 'ref' — shadows Vue's import
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'

interface RecentProject {
  name: string
  path: string
}

const props = withDefaults(defineProps<{
  value?: string
  isGitProject?: boolean
}>(), {
  value: '',
  isGitProject: false,
})

const emit = defineEmits<{
  (e: 'update:value', v: string): void
  (e: 'change', v: string): void
}>()

const isOpen = ref(false)
const mode = ref<'recent' | 'browse'>('recent')
const projects = ref<RecentProject[]>([])
const browseEntries = ref<any[]>([])
const browsePath = ref('')
const browseParent = ref('')
const loading = ref(false)
const dropdownPos = ref<{ top: number; left: number; width: number; direction: 'up' | 'down' } | null>(null)
const dialogRef = ref<HTMLDivElement | null>(null)
const triggerRef = ref<HTMLButtonElement | null>(null)
const dropdownRef = ref<HTMLDivElement | null>(null)
const isMobileBrowser = ref(false)

function onDocClick(e: MouseEvent) {
  if (dialogRef.value?.contains(e.target as Node)) return
  if (triggerRef.value?.contains(e.target as Node)) return
  isOpen.value = false
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') isOpen.value = false
}

function updateDropdownPos() {
  if (!isOpen.value || !triggerRef.value) {
    dropdownPos.value = null
    return
  }
  const r = triggerRef.value.getBoundingClientRect()
  const vw = window.innerWidth
  const vh = window.innerHeight
  const margin = 8
  // Dropdown is min-w-[280px] but can grow to 360; pick width based on
  // what's available, but never narrower than the trigger.
  const desiredW = Math.min(360, Math.max(280, r.width))
  // The actual rendered height is what `dialogRef` reports. We use it
  // instead of a hard-coded max so the popover sits flush against the
  // trigger (and only flips above when truly out of room below).
  const measuredH = dialogRef.value?.getBoundingClientRect().height ?? 0
  const popoverH = Math.max(40, Math.min(measuredH, vh * 0.6))
  // Default: place below the trigger.
  let top = r.bottom + 6
  let direction: 'up' | 'down' = 'down'
  if (top + popoverH > vh - margin) {
    // Not enough space below — flip above.
    top = Math.max(margin, r.top - 6 - popoverH)
    direction = 'up'
  }
  // Horizontal: keep aligned to the trigger's left edge but clamp
  // within the viewport so the dropdown never overflows left/right.
  let left = Math.max(margin, r.left)
  if (left + desiredW > vw - margin) {
    left = vw - desiredW - margin
  }
  dropdownPos.value = { top, left, width: desiredW, direction }
}

// Wrap the original isOpen.toggle so we recompute position before
// the dropdown renders.
function toggleOpen() {
  isOpen.value = !isOpen.value
  if (isOpen.value) {
    // Open the popover first (so the DOM exists), then position it
    // using the measured size. Using `nextTick` would also work but
    // awaiting a microtask via `requestAnimationFrame` lets the
    // browser lay out the popover before we read its size.
    requestAnimationFrame(() => {
      updateDropdownPos()
      // Lazily populate recent projects from the backend.
      void loadRecent()
      // Re-position once content is in (the list may have grown).
      requestAnimationFrame(() => updateDropdownPos())
    })
  } else {
    mode.value = 'recent'
  }
}

async function loadRecent() {
  if (loading.value) return
  loading.value = true
  try {
    // Use /api/sessions/recent-projects — the same endpoint the
    // sidebar uses to discover recent workspaces.
    const res = await fetch('/api/sessions/recent-projects')
    if (res.ok) {
      const data = await res.json()
      const list = Array.isArray(data?.projects) ? data.projects : Array.isArray(data) ? data : []
      projects.value = list
        .map((p: any) => ({
          name: p.name || p.path?.split('/').pop() || p.path || '未知',
          path: p.path || '',
        }))
        .filter((p: RecentProject) => !!p.path)
        .slice(0, 10)
    }
  } catch {
    // ignore — leave the list empty
  } finally {
    loading.value = false
  }
}

async function switchToBrowse() {
  mode.value = 'browse'
  loading.value = true
  try {
    const startDir = props.value || (await getCurrentWorkspaceDir()) || '/'
    await loadBrowse(startDir)
  } finally {
    loading.value = false
  }
}

async function getCurrentWorkspaceDir(): Promise<string> {
  try {
    const res = await fetch('/api/workspace/dir')
    if (res.ok) {
      const data = await res.json()
      return data?.dir || ''
    }
  } catch {}
  return ''
}

async function loadBrowse(dir: string) {
  loading.value = true
  try {
    const res = await fetch(`/api/workspace/ls?dir=${encodeURIComponent(dir)}`)
    if (res.ok) {
      const data = await res.json()
      browsePath.value = data.dir || dir
      browseEntries.value = (data.entries || []).map((e: any) => ({
        name: e.name,
        is_dir: e.is_dir,
        size: e.size || 0,
        path: `${data.dir}/${e.name}`,
      }))
      const parent = data.dir?.replace(/\/+$/, '').split('/').slice(0, -1).join('/') || '/'
      browseParent.value = parent
    }
  } catch {
  } finally {
    loading.value = false
  }
}

function pickRecent(p: RecentProject) {
  emit('update:value', p.path)
  emit('change', p.path)
  isOpen.value = false
}

function pickBrowse(entry: { name: string; is_dir: boolean; path: string }) {
  if (entry.is_dir) {
    void loadBrowse(entry.path)
  } else {
    emit('update:value', entry.path)
    emit('change', entry.path)
    isOpen.value = false
  }
}

// Also recompute on window resize / scroll while open
function onResize() {
  if (isOpen.value) updateDropdownPos()
}

onMounted(() => {
  document.addEventListener('mousedown', onDocClick)
  document.addEventListener('keydown', onKey)
  window.addEventListener('resize', onResize)
  window.addEventListener('scroll', onResize, true)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onDocClick)
  document.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('scroll', onResize, true)
})
</script>

<template>
  <div class="relative">
    <button
      ref="triggerRef"
      type="button"
      @click="toggleOpen"
      class="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-[var(--radius-md)] border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
    >
      <span class="material-symbols-outlined text-[14px]">folder</span>
      <span class="truncate max-w-[120px]">{{ value || '选择目录…' }}</span>
    </button>

    <Teleport to="body">
      <div
        v-if="isOpen"
        ref="dialogRef"
        class="fixed z-50 min-w-[280px] max-w-[360px] max-h-[60vh] overflow-y-auto rounded-[12px] border border-[var(--color-border)] bg-[var(--color-surface)] py-1 shadow-[var(--shadow-dropdown)]"
        :style="dropdownPos ? {
          top: dropdownPos.top + 'px',
          left: dropdownPos.left + 'px',
          width: dropdownPos.width + 'px',
        } : {}"
      >
        <!-- Recent projects view -->
        <template v-if="mode === 'recent'">
          <div class="flex items-center justify-between px-3 py-2 text-[11px] text-[var(--color-text-tertiary)] font-medium uppercase tracking-wide">
            <span>选择目录</span>
            <button
              type="button"
              class="text-[10px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] transition-colors"
              @click="switchToBrowse"
            >浏览…</button>
          </div>
          <div v-if="loading" class="px-3 py-3 text-[11px] text-[var(--color-text-tertiary)]">
            加载中…
          </div>
          <div v-else-if="projects.length === 0" class="px-3 py-3 text-[11px] text-[var(--color-text-tertiary)]">
            暂无最近目录
          </div>
          <div v-else class="border-t border-[var(--color-border-separator)]">
            <button
              v-for="p in projects" :key="p.path"
              @click="pickRecent(p)"
              class="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-[var(--color-surface-hover)]"
            >
              <span class="material-symbols-outlined text-[14px] text-[var(--color-text-secondary)] shrink-0">folder</span>
              <span class="min-w-0 flex-1 truncate text-[12px]">{{ p.name }}</span>
            </button>
          </div>
        </template>

        <!-- Browse filesystem view -->
        <template v-else>
          <div class="flex items-center gap-1 px-2 py-2 border-b border-[var(--color-border-separator)]">
            <button
              type="button"
              class="text-[11px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)] px-1"
              @click="browseParent ? loadBrowse(browseParent) : null"
              :title="browseParent"
            >←</button>
            <div class="flex-1 min-w-0 text-[10px] font-mono text-[var(--color-text-tertiary)] truncate" :title="browsePath">
              {{ browsePath }}
            </div>
            <button
              type="button"
              class="text-[10px] text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]"
              @click="mode = 'recent'"
            >返回</button>
          </div>
          <div v-if="loading" class="px-3 py-3 text-[11px] text-[var(--color-text-tertiary)]">
            加载中…
          </div>
          <div v-else-if="browseEntries.length === 0" class="px-3 py-3 text-[11px] text-[var(--color-text-tertiary)]">
            空目录
          </div>
          <div v-else>
            <button
              v-for="entry in browseEntries" :key="entry.path"
              @click="pickBrowse(entry)"
              class="w-full flex items-center gap-2.5 px-3 py-1.5 text-left hover:bg-[var(--color-surface-hover)]"
            >
              <span class="text-[10px] text-[var(--color-text-tertiary)] shrink-0 w-3 text-center">
                {{ entry.is_dir ? '▸' : '·' }}
              </span>
              <span class="min-w-0 flex-1 truncate text-[12px]">{{ entry.name }}</span>
            </button>
          </div>
        </template>
      </div>
    </Teleport>
  </div>
</template>