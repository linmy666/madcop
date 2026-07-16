<template>
  <div class="workspace-section">
    <!-- Trigger: compact button that shows current state -->
    <button
      class="workspace-trigger"
      :class="{ 'is-empty': !currentDir, 'is-open': showPopover }"
      @click="togglePopover"
    >
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" class="shrink-0">
        <path d="M3 7v11a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-7l-2-2H5a2 2 0 0 0-2 2z" />
      </svg>
      <span class="min-w-0 flex-1 truncate text-left">
        {{ currentDir ? shortPath : '工作区' }}
      </span>
      <svg v-if="!showPopover" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <path d="M6 9l6 6 6-6" />
      </svg>
      <svg v-else width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round">
        <path d="M6 15l6-6 6 6" />
      </svg>
    </button>

    <!-- Popover (teleported to body) -->
    <Teleport to="body">
      <div
        v-if="showPopover"
        class="workspace-popover"
        :style="popoverStyle"
        @click.stop
      >
        <!-- Path input row -->
        <div class="p-2 border-b border-[var(--color-border)]">
          <div class="flex gap-1.5">
            <input
              ref="dirInputRef"
              v-model="dirDraft"
              type="text"
              class="flex-1 min-w-0 bg-transparent border border-[var(--color-border)] rounded px-2 py-1 text-[11px] font-mono outline-none focus:border-[var(--color-text-secondary)]"
              placeholder="/Users/.../project"
              @keydown.enter="confirmDir"
              @keydown.esc="showPopover = false"
            />
            <button
              @click="browseDir"
              title="浏览文件夹"
              class="text-[10px] px-2 py-1 border border-[var(--color-border)] hover:bg-[var(--color-text-primary)] hover:text-[var(--color-surface)] transition-colors rounded flex items-center gap-1"
            >
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 7v11a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-7l-2-2H5a2 2 0 0 0-2 2z" />
                <path d="M9 13h6" />
              </svg>
              浏览
            </button>
            <button
              @click="confirmDir"
              class="text-[10px] px-2 py-1 border border-[var(--color-border)] hover:bg-[var(--color-text-primary)] hover:text-[var(--color-surface)] transition-colors rounded"
            >打开</button>
          </div>
          <p v-if="errorMsg" class="text-[10px] mt-1 opacity-60">{{ errorMsg }}</p>
        </div>

        <!-- File list -->
        <div class="flex-1 overflow-y-auto min-h-0">
          <div
            v-if="parentDir && parentDir !== currentDir"
            class="file-row flex items-center gap-2 px-2 py-1 cursor-pointer"
            @click="loadDir(parentDir)"
          >
            <span class="text-[10px] opacity-40 shrink-0">↑</span>
            <span class="text-[10px] opacity-60 truncate">..</span>
          </div>
          <div
            v-for="entry in entries"
            :key="entry.name"
            class="file-row flex items-center gap-2 px-2 py-1 cursor-pointer"
            @click="clickEntry(entry)"
          >
            <span class="text-[10px] opacity-40 shrink-0 w-3 text-center">
              {{ entry.is_dir ? '▸' : '·' }}
            </span>
            <span class="min-w-0 flex-1 truncate text-[11px]">{{ entry.name }}</span>
            <span v-if="!entry.is_dir" class="text-[9px] opacity-40 font-mono shrink-0">
              {{ formatSize(entry.size) }}
            </span>
          </div>
          <div v-if="entries.length === 0 && currentDir" class="px-2 py-6 text-center text-[10px] opacity-40">
            空目录
          </div>
          <div v-if="!currentDir" class="px-2 py-6 text-center text-[10px] opacity-40">
            <p>选择或输入目录</p>
            <p class="opacity-60 mt-1">↑↓ 导航 · Enter 打开</p>
          </div>
        </div>

        <!-- Footer hint -->
        <div v-if="currentDir" class="px-2 py-1 border-t border-[var(--color-border)] text-[9px] opacity-40 flex items-center justify-between">
          <span>{{ entries.length }} 项</span>
          <span>↑↓ 移动 · Enter 打开 · Esc 关闭</span>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed, nextTick, watch } from 'vue'
import { getApiUrl } from '../../api/client'

interface FileEntry {
  name: string
  is_dir: boolean
  size: number
  modified: number
}

const loading = ref(true)
const currentDir = ref('')
const entries = ref<FileEntry[]>([])
const showPopover = ref(false)
const dirDraft = ref('')
const errorMsg = ref('')
const dirInputRef = ref<HTMLInputElement | null>(null)
const triggerRect = ref<DOMRect | null>(null)
let triggerEl: HTMLElement | null = null

const parentDir = computed(() => {
  if (!currentDir.value || currentDir.value === '/') return ''
  const parts = currentDir.value.replace(/\/$/, '').split('/')
  parts.pop()
  return parts.join('/') || '/'
})

const shortPath = computed(() => {
  if (!currentDir.value) return ''
  const home = '/Users/linruihan'
  if (currentDir.value.startsWith(home))
    return '~' + currentDir.value.slice(home.length)
  // Truncate if too long
  if (currentDir.value.length > 28) return '…' + currentDir.value.slice(-26)
  return currentDir.value
})

const popoverStyle = computed(() => {
  if (!triggerRect.value) return { display: 'none' }
  const w = 320
  const r = triggerRect.value
  const vh = window.innerHeight
  const popoverH = 360
  const margin = 8

  // Default: place below button
  let top = r.bottom + margin
  // If not enough space below, place above the button
  if (top + popoverH > vh - 20) {
    top = Math.max(20, r.top - popoverH - margin)
  }

  // Horizontal: try to align to the right of the sidebar
  let left = r.right + margin
  // If overflows right, align right edges
  if (left + w > window.innerWidth - 12) {
    left = window.innerWidth - w - 12
  }
  if (left < 12) left = 12

  return {
    position: 'fixed' as const,
    top: `${top}px`,
    left: `${left}px`,
    width: `${w}px`,
    height: `${popoverH}px`,
    zIndex: 9999,
  }
})

async function loadDir(dir?: string) {
  loading.value = true
  try {
    const params = new URLSearchParams()
    if (dir) params.set('dir', dir)
    const res = await fetch(getApiUrl(`/api/workspace/ls?${params}`))
    if (res.ok) {
      const data = await res.json()
      if (data.entries !== undefined) entries.value = data.entries
      if (data.dir) currentDir.value = data.dir
    }
  } catch {} finally {
    loading.value = false
  }
}

async function confirmDir() {
  const d = dirDraft.value.trim()
  if (!d) return
  errorMsg.value = ''
  try {
    await fetch(getApiUrl('/api/workspace/dir'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ dir: d }),
    })
    // Persist to localStorage so the sessionStore can attribute
    // loaded sessions to this workspace on next page load.
    try { localStorage.setItem('madcop_workspace_dir', d) } catch {}
    await loadDir(d)
  } catch (e: any) {
    errorMsg.value = `Error: ${e.message || e}`
  }
}

async function browseDir() {
  errorMsg.value = ''
  try {
    // Use Electron's native file dialog if available
    const host: any = (window as any).desktopHost
    let chosen: string | null = null
    if (host?.dialogs?.open) {
      chosen = await host.dialogs.open({
        directory: true,
        title: '选择工作区目录',
        defaultPath: currentDir.value || undefined,
      })
    } else {
      // Fallback for browser dev: use a hidden file input
      chosen = await pickDirViaInput()
    }
    if (!chosen) return // user cancelled
    dirDraft.value = chosen
    await confirmDir()
  } catch (e: any) {
    errorMsg.value = `Error: ${e.message || e}`
  }
}

function pickDirViaInput(): Promise<string | null> {
  return new Promise((resolve) => {
    const input = document.createElement('input')
    input.type = 'file'
    // @ts-ignore — webkitdirectory is non-standard but works in Chromium
    input.webkitdirectory = true
    input.style.display = 'none'
    input.onchange = () => {
      const files = input.files
      if (!files || files.length === 0) return resolve(null)
      // The first file's path.webkitRelativePath gives e.g. "myproject/sub"
      // Full path can be reconstructed from the first file
      const f = files[0] as any
      const rel = f.webkitRelativePath || f.name
      const parts = rel.split('/')
      parts.pop()
      // We can't get the absolute path in browser, so resolve to
      // whatever the input gave us
      resolve(parts.join('/') || rel)
    }
    document.body.appendChild(input)
    input.click()
    setTimeout(() => document.body.removeChild(input), 1000)
  })
}

function clickEntry(entry: FileEntry) {
  if (entry.is_dir) {
    loadDir(`${currentDir.value}/${entry.name}`)
  }
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)}MB`
}

function togglePopover() {
  showPopover.value = !showPopover.value
  if (showPopover.value) {
    nextTick(() => {
      if (dirInputRef.value) {
        dirInputRef.value.focus()
        dirInputRef.value.select()
      }
      // Refresh trigger position
      if (triggerEl) triggerRect.value = triggerEl.getBoundingClientRect()
    })
  }
}

function updateTriggerRect() {
  if (triggerEl) triggerRect.value = triggerEl.getBoundingClientRect()
}

function onWindowClick(e: MouseEvent) {
  if (!showPopover.value) return
  const target = e.target as HTMLElement
  if (target.closest('.workspace-popover')) return
  if (target.closest('.workspace-trigger')) return
  showPopover.value = false
}

function onWindowResize() {
  updateTriggerRect()
}

onMounted(async () => {
  // Load current dir
  try {
    const res = await fetch(getApiUrl('/api/workspace/dir'))
    if (res.ok) {
      const data = await res.json()
      if (data.dir) {
        currentDir.value = data.dir
        // Mirror to localStorage so the sessionStore can attribute
        // loaded sessions to this workspace on next page load.
        try { localStorage.setItem('madcop_workspace_dir', data.dir) } catch {}
      }
    }
  } catch {}
  await loadDir()

  await nextTick()
  triggerEl = document.querySelector('.workspace-trigger') as HTMLElement
  if (triggerEl) {
    triggerRect.value = triggerEl.getBoundingClientRect()
    new ResizeObserver(updateTriggerRect).observe(document.body)
    window.addEventListener('resize', onWindowResize)
    window.addEventListener('scroll', onWindowResize, true)
  }

  setTimeout(() => document.addEventListener('mousedown', onWindowClick), 100)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onWindowClick)
  window.removeEventListener('resize', onWindowResize)
  window.removeEventListener('scroll', onWindowResize, true)
})
</script>

<style scoped>
.workspace-section {
  width: 100%;
}

.workspace-trigger {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  height: 28px;
  padding: 0 8px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: transparent;
  color: var(--color-text-primary);
  font-size: 11px;
  font-family: var(--font-mono);
  transition: background 0.08s, border-color 0.08s;
  cursor: pointer;
  outline: none;
}
.workspace-trigger:hover {
  background: var(--color-surface-hover);
}
.workspace-trigger.is-open {
  background: var(--color-surface-hover);
  border-color: var(--color-text-secondary);
}
.workspace-trigger.is-empty {
  color: var(--color-text-tertiary);
  border-style: dashed;
}

.workspace-popover {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12), 0 2px 6px rgba(0, 0, 0, 0.06);
  color: var(--color-text-primary);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  font-size: 11px;
}

.file-row {
  transition: background 0.06s;
  user-select: none;
}
.file-row:hover {
  background: var(--color-surface-hover);
}
</style>