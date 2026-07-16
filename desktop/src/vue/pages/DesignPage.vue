<script setup lang="ts">
/**
 * v3.1 — Design tool page (redesigned for beauty)
 *
 * Visual language:
 *  - Quiet top bar (project name + minimal controls)
 *  - Hero "AI generation" card with a clear type-first prompt
 *  - Recent projects: clean card grid with thumbnails
 *  - Inside project: tabbed pages + full canvas + property panel
 *  - All stroke-outline icons (no Material Symbols fill)
 *  - Monospace for IDs, file names
 *  - Subtle gradients, no garish colors
 */

import { ref, computed, watch, onMounted } from 'vue'
import DesignCanvas, { type DesignData } from '../components/design/DesignCanvas.vue'
import PreviewPanel from '../components/design/PreviewPanel.vue'
import { getApiUrl } from '../api/client'

interface DesignPageData { id: string; name: string; data: DesignData }
interface DesignProject { id: string; name: string; pages: DesignPageData[]; activePageId: string | null; createdAt: number }

const PAGE_PRESETS = [
  { label: '登录页', prompt: '一个简洁的登录页面，包含邮箱输入框、密码输入框、一个主要登录按钮，白色背景，居中布局' },
  { label: '仪表盘', prompt: '一个数据仪表盘卡片布局，包含4张卡片：今日订单、收入、活跃用户、转化率，每张卡片有数字和标题，网格布局' },
  { label: '个人中心', prompt: '用户个人中心页，顶部是头像和昵称，下面是设置项列表：个人信息、通知设置、隐私、关于' },
  { label: '落地页', prompt: '产品落地页，包含大标题、副标题、行动号召按钮、功能特性列表（3列网格）' },
]
const FULL_APP_PROMPTS = [
  { name: '电商 App', pages: ['首页轮播推荐', '商品列表页', '商品详情页', '购物车', '个人中心'] },
  { name: 'SaaS 后台', pages: ['登录页', '仪表盘概览', '用户管理', '设置页'] },
  { name: '社交 App', pages: ['登录页', '消息列表', '个人主页', '设置'] },
]

const STORAGE_KEY = 'madcop_design_projects'
function loadProjects(): DesignProject[] {
  try { const raw = localStorage.getItem(STORAGE_KEY); if (raw) return JSON.parse(raw) } catch {}
  return []
}
function saveProjects(projects: DesignProject[]) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(projects)) } catch {}
}
function genId() { return `p${Date.now()}${Math.floor(Math.random() * 1000)}` }

const componentNames: Record<string, boolean> = {
  Header: true, Paragraph: true, Button: true, Image: true,
  Input: true, Card: true, Flex: true, Grid: true,
  Section: true, Divider: true, Space: true,
}
const defaultsFor: Record<string, Record<string, any>> = {
  Header: { text: '标题', level: '2', fontSize: 24 },
  Paragraph: { text: '文字', fontSize: 14 },
  Button: { text: '按钮', variant: 'primary' },
  Card: { padding: 24, bgColor: '#FFFFFF', radius: 12, shadow: 'md' },
  Flex: { direction: 'column', gap: 16, justify: 'start', align: 'stretch' },
  Grid: { columns: 2, gap: 16 },
  Section: { bgColor: '#F9FAFB', padding: 40, maxWidth: 960 },
  Divider: { color: '#E5E7EB', thickness: 1, margin: 16 },
  Space: { height: 16 },
  Image: { width: 300, height: 200, borderRadius: 8 },
  Input: { placeholder: '请输入...', width: 300, type: 'text' },
}
function autoRepair(data: any): DesignData {
  if (!data.root) data.root = { props: { bgColor: '#FFFFFF', padding: 40 } }
  if (!data.root.props) data.root.props = {}
  if (!data.root.props.bgColor) data.root.props.bgColor = '#FFFFFF'
  if (!data.root.props.padding) data.root.props.padding = 40
  if (!Array.isArray(data.content)) data.content = []
  function repairItem(item: any): any {
    if (!item || !item.type) return null
    // Unknown component types are NOT silently dropped — surface them as a
    // visible Paragraph so the user can see what the LLM emitted instead of
    // wondering why content disappeared.
    if (!componentNames[item.type]) {
      return { type: 'Paragraph', props: { text: `[未知组件: ${item.type}]`, color: '#EF4444', fontSize: 12 } }
    }
    if (!item.props) item.props = {}
    if (defaultsFor[item.type]) {
      for (const [k, v] of Object.entries(defaultsFor[item.type])) {
        if (item.props[k] === undefined) item.props[k] = v
      }
    }
    if (item.children && Array.isArray(item.children)) {
      item.children = item.children.map(repairItem).filter(Boolean)
    }
    return item
  }
  data.content = data.content.map(repairItem).filter(Boolean)
  return data as DesignData
}
function emptyData(): DesignData {
  return { root: { props: { bgColor: '#FFFFFF', padding: 40 } }, content: [] }
}

const projects = ref<DesignProject[]>(loadProjects())
const activeProject = ref<DesignProject | null>(null)
const prompt = ref('')
const loading = ref(false)
const error = ref<string | null>(null)
const showGenAll = ref(false)
const newProjectName = ref('')
const newProjectNameInput = ref<HTMLInputElement | null>(null)
const viewMode = ref<'editor' | 'preview'>('editor')
const previewRefreshKey = ref(0)

watch(projects, (val) => saveProjects(val), { deep: true })

onMounted(() => {
  if (newProjectNameInput.value) newProjectNameInput.value.focus()
})

function createProject(name: string) {
  if (!name.trim()) return
  const project: DesignProject = {
    id: genId(), name: name.trim(),
    pages: [], activePageId: null, createdAt: Date.now(),
  }
  projects.value = [project, ...projects.value]
  activeProject.value = project
  newProjectName.value = ''
}
function deleteProject(id: string) {
  if (!confirm('删除此项目？')) return
  projects.value = projects.value.filter((p) => p.id !== id)
}
function addPage(name: string) {
  if (!activeProject.value) return
  const page: DesignPageData = { id: genId(), name, data: emptyData() }
  const updated: DesignProject = {
    ...activeProject.value,
    pages: [...activeProject.value.pages, page], activePageId: page.id,
  }
  activeProject.value = updated
  projects.value = projects.value.map((p) => p.id === updated.id ? updated : p)
}
function deletePage(pageId: string) {
  if (!activeProject.value) return
  if (!confirm('删除此页面？')) return
  const updated: DesignProject = {
    ...activeProject.value,
    pages: activeProject.value.pages.filter((p) => p.id !== pageId),
    activePageId: activeProject.value.activePageId === pageId ? null : activeProject.value.activePageId,
  }
  activeProject.value = updated
  projects.value = projects.value.map((p) => p.id === updated.id ? updated : p)
}
function selectPage(pageId: string) {
  if (!activeProject.value) return
  const updated: DesignProject = { ...activeProject.value, activePageId: pageId }
  activeProject.value = updated
  projects.value = projects.value.map((p) => p.id === updated.id ? updated : p)
}
function updatePageData(pageId: string, data: DesignData) {
  if (!activeProject.value) return
  const updated: DesignProject = {
    ...activeProject.value,
    pages: activeProject.value.pages.map((p) => p.id === pageId ? { ...p, data } : p),
  }
  activeProject.value = updated
  projects.value = projects.value.map((p) => p.id === updated.id ? updated : p)
}

async function generatePage(genPrompt: string): Promise<DesignData | null> {
  loading.value = true
  error.value = null
  try {
    const r = await fetch(getApiUrl('/api/design/generate'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: genPrompt }),
    })
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const resp = await r.json()
    const text: string = resp.content || ''
    const jsonMatch = text.match(/\{[\s\S]*\}/)
    if (jsonMatch) {
      const parsed = JSON.parse(jsonMatch[0])
      if (parsed.content && Array.isArray(parsed.content)) {
        return autoRepair(parsed)
      }
    }
    error.value = 'AI 返回格式有误'
    return null
  } catch (e: any) {
    error.value = `生成失败: ${e?.message || e}`
    return null
  } finally {
    loading.value = false
  }
}
async function handleGenerate() {
  if (!prompt.value.trim() || !activeProject.value) return
  const data = await generatePage(prompt.value)
  if (data) {
    const pageName = prompt.value.slice(0, 12) + '…'
    const page: DesignPageData = { id: genId(), name: pageName, data }
    const updated: DesignProject = {
      ...activeProject.value,
      pages: [...activeProject.value.pages, page], activePageId: page.id,
    }
    activeProject.value = updated
    projects.value = projects.value.map((p) => p.id === updated.id ? updated : p)
    prompt.value = ''
  }
}
async function handleGenerateApp(preset: typeof FULL_APP_PROMPTS[0]) {
  if (!activeProject.value) return
  showGenAll.value = false
  loading.value = true
  const newPages: DesignPageData[] = []
  for (const pageName of preset.pages) {
    const data = await generatePage(`${preset.name}的${pageName}，风格统一`)
    if (data) newPages.push({ id: genId(), name: pageName, data })
  }
  if (newPages.length > 0) {
    const updated: DesignProject = {
      ...activeProject.value,
      pages: [...activeProject.value.pages, ...newPages],
      activePageId: newPages[0].id,
    }
    activeProject.value = updated
    projects.value = projects.value.map((p) => p.id === updated.id ? updated : p)
  }
  loading.value = false
}
const activePage = computed<DesignPageData | null>(() => {
  if (!activeProject.value) return null
  return activeProject.value.pages.find((p) => p.id === activeProject.value!.activePageId) || null
})

// Format date as "3 天前"
function formatRelative(ts: number): string {
  const days = Math.floor((Date.now() - ts) / 86400000)
  if (days === 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 7) return `${days} 天前`
  if (days < 30) return `${Math.floor(days / 7)} 周前`
  return new Date(ts).toLocaleDateString('zh-CN')
}
</script>

<template>
  <!-- ============================== -->
  <!-- Project list (no active project) -->
  <!-- ============================== -->
  <div v-if="!activeProject" class="design-page bg-[var(--color-surface)] flex h-full w-full overflow-y-auto">
    <div class="mx-auto w-full max-w-[960px] px-12 py-20">
      <!-- Title -->
      <div class="mb-16">
        <h1 class="text-[28px] font-semibold tracking-tight text-[var(--color-text-primary)] mb-2">设计工具</h1>
        <p class="text-[14px] text-[var(--color-text-secondary)] leading-relaxed max-w-xl">
          用 AI 批量生成原型设计。拖拽组件、属性面板、导出 .madcop 分享。
        </p>
      </div>

      <!-- New project card (top, prominent) -->
      <div class="mb-12">
        <div class="design-new-card">
          <div class="design-new-card__title">新建项目</div>
          <div class="flex gap-2">
            <input
              ref="newProjectNameInput"
              v-model="newProjectName"
              type="text"
              placeholder="项目名…"
              @keydown.enter="createProject(newProjectName)"
              class="design-input flex-1"
            />
            <button
              @click="createProject(newProjectName)"
              :disabled="!newProjectName.trim()"
              class="design-btn-primary"
              :class="{ 'design-btn-primary--disabled': !newProjectName.trim() }"
            >创建</button>
          </div>
        </div>
      </div>

      <!-- Recent projects -->
      <div>
        <div class="design-section-label flex items-center justify-between mb-4">
          <span>最近的项目</span>
          <span class="design-meta">{{ projects.length }} 个</span>
        </div>

        <div v-if="projects.length === 0" class="design-empty">
          <div class="design-empty__icon">○</div>
          <div class="design-empty__text">还没有项目</div>
          <div class="design-empty__hint">在上方创建一个开始</div>
        </div>

        <div v-else class="grid grid-cols-3 gap-4">
          <div
            v-for="proj in projects"
            :key="proj.id"
            @click="activeProject = proj"
            class="design-project-tile"
          >
            <!-- Mini "thumbnail" — stacked page rectangles -->
            <div class="design-project-tile__thumb">
              <div
                v-for="(p, i) in proj.pages.slice(0, 3)"
                :key="p.id"
                :style="{
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-border)',
                  borderRadius: '3px',
                  height: '6px',
                  width: (40 + i * 12) + '%',
                  marginBottom: '4px',
                  opacity: 0.6 + i * 0.13,
                }"
              ></div>
              <div v-if="proj.pages.length === 0" class="design-project-tile__empty">—</div>
            </div>
            <div class="design-project-tile__name">{{ proj.name }}</div>
            <div class="design-project-tile__meta">
              <span class="design-meta">{{ proj.pages.length }} 个页面</span>
              <span class="design-meta">{{ formatRelative(proj.createdAt) }}</span>
            </div>
            <button
              @click.stop="deleteProject(proj.id)"
              class="design-project-tile__delete"
              aria-label="删除"
            >
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/></svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- ============================== -->
  <!-- Active project: editor -->
  <!-- ============================== -->
  <div v-else class="design-page flex h-full w-full flex-col overflow-hidden bg-[var(--color-surface)]">
    <!-- Quiet top bar -->
    <header
      class="flex items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-5 h-12 flex-shrink-0"
    >
      <div class="flex items-center gap-4">
        <button
          @click="activeProject = null"
          class="design-btn-ghost flex items-center gap-1.5"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><path d="M15 18l-6-6 6-6"/></svg>
          <span>项目</span>
        </button>
        <div class="h-4 w-px bg-[var(--color-border)]"></div>
        <span class="text-[14px] font-medium text-[var(--color-text-primary)]">{{ activeProject.name }}</span>
        <span class="design-meta">{{ activeProject.pages.length }} 页</span>
      </div>
      <div class="flex items-center gap-2">
        <button
          @click="showGenAll = !showGenAll"
          class="design-btn-ghost flex items-center gap-1.5"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
          <span>批量生成</span>
        </button>
      </div>
    </header>

    <!-- Batch generation strip -->
    <div
      v-if="showGenAll"
      class="border-b border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] px-5 py-3 flex items-center gap-3 flex-shrink-0"
    >
      <span class="design-meta shrink-0">一套生成</span>
      <button
        v-for="preset in FULL_APP_PROMPTS"
        :key="preset.name"
        @click="handleGenerateApp(preset)"
        :disabled="loading"
        class="design-chip"
      >{{ preset.name }} <span class="opacity-60">· {{ preset.pages.length }}页</span></button>
    </div>

    <!-- Page tabs strip -->
    <div
      class="flex items-center gap-1 border-b border-[var(--color-border)] bg-[var(--color-surface)] px-5 h-10 overflow-x-auto flex-shrink-0"
    >
      <button
        v-for="page in activeProject.pages"
        :key="page.id"
        @click="selectPage(page.id)"
        :class="['design-page-tab', activeProject.activePageId === page.id ? 'design-page-tab--active' : '']"
      >
        <span>{{ page.name }}</span>
        <span
          @click.stop="deletePage(page.id)"
          class="design-page-tab__close"
          aria-label="删除页面"
        >×</span>
      </button>
      <button
        @click="addPage(`页面 ${activeProject.pages.length + 1}`)"
        class="design-page-tab-add"
      >+ 新页面</button>
    </div>

    <!-- Content: prompt bar OR canvas -->
    <div v-if="!activePage && !loading" class="flex-1 overflow-y-auto bg-[var(--color-surface-container-lowest)]">
      <div class="mx-auto max-w-[640px] px-8 py-16">
        <!-- Presets (as quiet chips) -->
        <div class="mb-6">
          <div class="design-section-label mb-3">快速开始</div>
          <div class="flex flex-wrap gap-2">
            <button
              v-for="p in PAGE_PRESETS"
              :key="p.label"
              @click="prompt = p.prompt"
              :class="['design-preset', prompt === p.prompt ? 'design-preset--active' : '']"
            >{{ p.label }}</button>
          </div>
        </div>

        <!-- Prompt area — like Notion / Figma -->
        <div class="design-prompt-area">
          <textarea
            v-model="prompt"
            placeholder="描述你想生成的页面…&#10;&#10;例: 一个深色主题的登录页,左侧有产品图,右侧是邮箱密码登录框,登录按钮用品牌色"
            rows="6"
            class="design-prompt-textarea"
          ></textarea>
          <div class="flex items-center justify-between mt-3">
            <span class="design-meta">GLM-5.2 · 约 30s</span>
            <button
              @click="handleGenerate"
              :disabled="!prompt.trim()"
              :class="['design-btn-primary', !prompt.trim() ? 'design-btn-primary--disabled' : '']"
            >生成</button>
          </div>
        </div>
      </div>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="flex-1 flex items-center justify-center bg-[var(--color-surface)]">
      <div class="text-center">
        <div class="design-loading-dot"></div>
        <div class="text-[13px] text-[var(--color-text-tertiary)] mt-4">AI 正在生成</div>
      </div>
    </div>

    <!-- Camera / Preview tabs -->
    <div v-if="activePage && !loading" class="flex-1 flex flex-col overflow-hidden">
      <!-- Tab bar -->
      <div class="px-5 pt-2 pb-0 border-b border-[var(--color-border)] bg-[var(--color-surface)] flex items-center gap-0 flex-shrink-0">
        <button
          @click="viewMode = 'editor'"
          :class="['preview-tab', viewMode === 'editor' ? 'preview-tab--active' : '']"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" style="margin-right:4px;">
            <path d="M12 20h9M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"/>
          </svg>
          编辑
        </button>
        <button
          @click="viewMode = 'preview'"
          :class="['preview-tab', viewMode === 'preview' ? 'preview-tab--active' : '']"
        >
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" style="margin-right:4px;">
            <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
            <circle cx="12" cy="12" r="3"/>
          </svg>
          预览
        </button>
      </div>
      <!-- Editor -->
      <div v-show="viewMode === 'editor'" class="flex-1 overflow-hidden">
        <DesignCanvas
          :initial-data="activePage.data"
          @save="(data) => updatePageData(activePage.id, data)"
        />
      </div>
      <!-- Preview -->
      <div v-show="viewMode === 'preview'" class="flex-1 overflow-hidden">
        <PreviewPanel :refresh-key="previewRefreshKey" />
      </div>
    </div>

    <!-- Error toast -->
    <Transition name="design-fade">
      <div v-if="error" class="design-toast">{{ error }}</div>
    </Transition>
  </div>
</template>

<style scoped>
/* ── Type system ────────────────────────────────────── */
.design-page {
  font-family: var(--font-body);
  -webkit-font-smoothing: antialiased;
}
.design-section-label {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1.2px;
  color: var(--color-text-tertiary);
}
.design-meta {
  font-size: 11px;
  color: var(--color-text-tertiary);
  font-family: var(--font-mono);
}

/* ── Buttons ───────────────────────────────────────── */
.design-btn-primary {
  padding: 8px 18px;
  background: var(--color-brand);
  color: #fff;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: opacity 0.15s, transform 0.05s;
}
.design-btn-primary:hover { opacity: 0.92; }
.design-btn-primary:active { transform: scale(0.98); }
.design-btn-primary--disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.design-btn-ghost {
  padding: 5px 10px;
  background: transparent;
  color: var(--color-text-secondary);
  border: none;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.1s;
}
.design-btn-ghost:hover { background: var(--color-surface-container); color: var(--color-text-primary); }

.design-chip {
  padding: 5px 14px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.1s;
}
.design-chip:hover {
  border-color: var(--color-brand);
  color: var(--color-text-primary);
}
.design-chip:disabled { opacity: 0.4; cursor: not-allowed; }

/* ── Inputs ────────────────────────────────────────── */
.design-input {
  width: 100%;
  padding: 8px 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 13px;
  color: var(--color-text-primary);
  font-family: inherit;
  outline: none;
  transition: border-color 0.1s;
}
.design-input:focus { border-color: var(--color-brand); }

/* ── New project card ────────────────────────────── */
.design-new-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 16px 20px;
}
.design-new-card__title {
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 10px;
}

/* ── Project tiles ────────────────────────────────── */
.design-project-tile {
  position: relative;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.15s;
  min-height: 132px;
  display: flex;
  flex-direction: column;
}
.design-project-tile:hover {
  border-color: var(--color-border-focus);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.06);
  transform: translateY(-1px);
}
.design-project-tile__thumb {
  background: var(--color-surface-container-low);
  border-radius: 4px;
  height: 64px;
  margin-bottom: 12px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}
.design-project-tile__empty {
  color: var(--color-text-tertiary);
  font-size: 14px;
  text-align: center;
  opacity: 0.5;
}
.design-project-tile__name {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.design-project-tile__meta {
  display: flex;
  gap: 8px;
  margin-top: auto;
}
.design-project-tile__delete {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 24px;
  height: 24px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-tertiary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.1s, color 0.1s;
}
.design-project-tile:hover .design-project-tile__delete { opacity: 1; }
.design-project-tile__delete:hover { color: var(--color-error); border-color: var(--color-error); }

/* ── Empty state ──────────────────────────────────── */
.design-empty {
  text-align: center;
  padding: 80px 20px;
  border: 1px dashed var(--color-border);
  border-radius: 10px;
  color: var(--color-text-tertiary);
}
.design-empty__icon {
  font-size: 32px;
  opacity: 0.4;
  margin-bottom: 12px;
}
.design-empty__text {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}
.design-empty__hint {
  font-size: 12px;
}

/* ── Prompt area ─────────────────────────────────── */
.design-prompt-area {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  padding: 16px 20px;
  transition: border-color 0.15s;
}
.design-prompt-area:focus-within { border-color: var(--color-brand); }
.design-prompt-textarea {
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  font-size: 14px;
  font-family: inherit;
  line-height: 1.6;
  color: var(--color-text-primary);
  background: transparent;
}
.design-prompt-textarea::placeholder {
  color: var(--color-text-tertiary);
  white-space: pre-line;
}

.design-preset {
  padding: 5px 12px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
  border-radius: 16px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.1s;
}
.design-preset:hover { border-color: var(--color-border-focus); }
.design-preset--active {
  background: var(--color-brand);
  color: #fff;
  border-color: var(--color-brand);
}

/* ── Page tabs ────────────────────────────────────── */
.design-page-tab {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: background 0.1s;
}
.design-page-tab:hover { background: var(--color-surface-container-low); }
.design-page-tab--active {
  background: var(--color-surface-container-lowest);
  border: 1px solid var(--color-border);
  color: var(--color-text-primary);
  font-weight: 500;
}
.design-page-tab__close {
  margin-left: 2px;
  font-size: 14px;
  color: var(--color-text-tertiary);
  line-height: 1;
  padding: 0 2px;
  border-radius: 3px;
}
.design-page-tab__close:hover { background: var(--color-error); color: #fff; }

.design-page-tab-add {
  padding: 4px 10px;
  background: transparent;
  color: var(--color-text-tertiary);
  border: 1px dashed var(--color-border);
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.design-page-tab-add:hover { color: var(--color-text-primary); border-color: var(--color-border-focus); }

/* ── Loading ──────────────────────────────────────── */
.design-loading-dot {
  width: 24px;
  height: 24px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-brand);
  border-radius: 50%;
  margin: 0 auto;
  animation: design-spin 0.8s linear infinite;
}
@keyframes design-spin {
  to { transform: rotate(360deg); }
}

/* ── Toast ───────────────────────────────────────── */
.design-toast {
  position: fixed;
  bottom: 24px;
  left: 50%;
  transform: translateX(-50%);
  padding: 10px 20px;
  background: var(--color-surface);
  color: var(--color-error);
  border: 1px solid color-mix(in srgb, var(--color-error) 30%, transparent);
  border-radius: 8px;
  font-size: 13px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  z-index: 1000;
}

.design-fade-enter-active, .design-fade-leave-active {
  transition: opacity 0.2s, transform 0.2s;
}
.design-fade-enter-from, .design-fade-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(8px);
}

/* ── Preview tabs ─────────────────────────────────── */
.preview-tab {
  display: inline-flex;
  align-items: center;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 500;
  color: var(--color-text-tertiary, #999);
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: color 0.1s, border-color 0.1s;
  margin-bottom: -1px;
}
.preview-tab:hover { color: var(--color-text-primary, #222); }
.preview-tab--active {
  color: var(--color-brand, #333);
  border-bottom-color: var(--color-brand, #333);
}
</style>
