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
  <!-- ============================================ -->
  <!-- Project list (no active project)             -->
  <!-- ============================================ -->
  <div v-if="!activeProject" class="dp-page">
    <div class="dp-page__inner">
      <!-- Header -->
      <header class="dp-page__head">
        <div>
          <h1 class="dp-page__title">设计工具</h1>
          <p class="dp-page__sub">用 AI 批量生成 UI 原型，拖拽组件、配置属性、导出分享</p>
        </div>
      </header>

      <!-- Hero: quick AI generation -->
      <section class="dp-hero">
        <div class="dp-hero__inner">
          <div class="dp-hero__icon">
            <span class="material-symbols-outlined">auto_awesome</span>
          </div>
          <div class="dp-hero__body">
            <h2 class="dp-hero__title">从一个提示词开始</h2>
            <p class="dp-hero__sub">输入项目名，下方选一个模板，AI 自动生成完整页面</p>
          </div>
        </div>
        <div class="dp-hero__form">
          <input
            ref="newProjectNameInput"
            v-model="newProjectName"
            type="text"
            placeholder="项目名…"
            class="dp-input"
            @keydown.enter="createProject(newProjectName)"
          />
          <button
            @click="createProject(newProjectName)"
            :disabled="!newProjectName.trim()"
            class="dp-btn dp-btn--primary"
          >创建项目</button>
        </div>
      </section>

      <!-- Page presets (quick start) -->
      <section class="dp-presets">
        <header class="dp-section__head">
          <h3 class="dp-section__title">页面模板</h3>
          <p class="dp-section__sub">创建项目后选择模板，AI 生成完整 UI</p>
        </header>
        <div class="dp-presets-grid">
          <button
            v-for="(p, i) in PAGE_PRESETS"
            :key="i"
            class="dp-preset"
            @click="newProjectName.trim() && createProjectAndApply(p.prompt)"
          >
            <span class="dp-preset__label">{{ p.label }}</span>
            <span class="dp-preset__arrow material-symbols-outlined">arrow_forward</span>
          </button>
        </div>
      </section>

      <!-- App full templates -->
      <section class="dp-presets" v-if="FULL_APP_PROMPTS.length">
        <header class="dp-section__head">
          <h3 class="dp-section__title">多页面 App 模板</h3>
          <p class="dp-section__sub">一次生成整个 App 的多个页面</p>
        </header>
        <div class="dp-app-templates">
          <button
            v-for="(t, i) in FULL_APP_PROMPTS"
            :key="i"
            class="dp-app-template"
            @click="newProjectName.trim() && createProjectAndApply(t)"
          >
            <div class="dp-app-template__name">{{ t.name }}</div>
            <div class="dp-app-template__pages">{{ t.pages.length }} 个页面 · {{ t.pages.join(' · ') }}</div>
          </button>
        </div>
      </section>

      <!-- Recent projects -->
      <section class="dp-recent">
        <header class="dp-section__head dp-section__head--row">
          <h3 class="dp-section__title">最近的项目</h3>
          <span class="dp-meta">{{ projects.length }} 个</span>
        </header>

        <div v-if="projects.length === 0" class="dp-empty">
          <div class="dp-empty__icon">
            <span class="material-symbols-outlined">draw</span>
          </div>
          <h4 class="dp-empty__title">还没有项目</h4>
          <p class="dp-empty__sub">在上方输入项目名创建第一个</p>
        </div>

        <div v-else class="dp-projects">
          <article
            v-for="proj in projects"
            :key="proj.id"
            class="dp-project"
            @click="activeProject = proj"
          >
            <div class="dp-project__thumb">
              <div
                v-for="(p, i) in proj.pages.slice(0, 3)"
                :key="p.id"
                class="dp-project__page"
                :style="{ width: (40 + i * 12) + '%', opacity: 0.6 + i * 0.13 }"
              />
              <div v-if="proj.pages.length === 0" class="dp-project__empty">—</div>
            </div>
            <div class="dp-project__body">
              <h4 class="dp-project__name">{{ proj.name }}</h4>
              <div class="dp-project__meta">
                <span class="dp-meta">{{ proj.pages.length }} 个页面</span>
                <span class="dp-meta">·</span>
                <span class="dp-meta">{{ formatRelative(proj.createdAt) }}</span>
              </div>
            </div>
            <button
              @click.stop="deleteProject(proj.id)"
              class="dp-project__del"
              aria-label="删除"
            >
              <span class="material-symbols-outlined" style="font-size:16px">delete</span>
            </button>
          </article>
        </div>
      </section>
    </div>
  </div>

  <!-- ============================================ -->
  <!-- Active project: editor                       -->
  <!-- ============================================ -->
  <div v-else class="dp-editor">
    <header class="dp-editor__topbar">
      <button @click="activeProject = null" class="dp-editor__back">
        <span class="material-symbols-outlined" style="font-size:18px">arrow_back</span>
        返回
      </button>
      <div class="dp-editor__title">{{ activeProject.name }}</div>
      <div class="dp-editor__spacer" />
      <button @click="saveProject" class="dp-btn">保存</button>
      <button @click="deleteCurrentProject" class="dp-btn dp-btn--danger">删除项目</button>
    </header>

    <div class="dp-editor__body">
      <div class="dp-editor__pages">
        <div class="dp-section__head">
          <h3 class="dp-section__title">页面</h3>
          <button @click="addPage" class="dp-btn dp-btn--sm">+ 新页面</button>
        </div>
        <div class="dp-page-list">
          <button
            v-for="p in activeProject.pages"
            :key="p.id"
            :class="['dp-page-tab', { 'dp-page-tab--active': p.id === activePageId }]"
            @click="activePageId = p.id"
          >
            {{ p.name || '未命名' }}
          </button>
        </div>
      </div>

      <div class="dp-editor__canvas">
        <DesignCanvas
          v-if="activePage"
          :data="activePage.data"
          @update="onCanvasUpdate"
        />
      </div>

      <div class="dp-editor__props">
        <div class="dp-section__head">
          <h3 class="dp-section__title">属性</h3>
        </div>
        <div v-if="selectedNode" class="dp-props-form">
          <label class="dp-field">
            <span class="dp-field__label">类型</span>
            <input :value="selectedNode.type" disabled class="dp-input" />
          </label>
          <label class="dp-field">
            <span class="dp-field__label">文本</span>
            <input v-model="selectedNode.props.text" class="dp-input" />
          </label>
        </div>
        <div v-else class="dp-props-empty">
          <p>选中画布上的组件以编辑属性</p>
        </div>
      </div>
    </div>

    <PreviewPanel v-if="activePage" :data="activePage.data" />
  </div>
</template>

<style scoped>
/* ── Page layout ─────────────────────────────────────────────── */
.dp-page { width: 100%; height: 100%; overflow-y: auto; background: var(--color-surface); }
.dp-page__inner { max-width: 960px; margin: 0 auto; padding: 48px 32px 64px; }

.dp-page__head { margin-bottom: 32px; }
.dp-page__title { font-size: 28px; font-weight: 600; margin: 0 0 4px; letter-spacing: -0.01em; }
.dp-page__sub { margin: 0; font-size: 14px; color: var(--color-text-secondary); }

/* ── Section heading (shared) ────────────────────────────────── */
.dp-section__head { margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.dp-section__head--row { justify-content: space-between; }
.dp-section__title { font-size: 14px; font-weight: 600; margin: 0; color: var(--color-text-primary); }
.dp-section__sub { margin: 0; font-size: 12px; color: var(--color-text-secondary); }

/* ── Hero (new project) ───────────────────────────────────── */
.dp-hero {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 32px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.dp-hero__inner { display: flex; gap: 12px; align-items: center; }
.dp-hero__icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface-container-low);
  border-radius: 6px;
  color: var(--color-text-primary);
  flex-shrink: 0;
}
.dp-hero__icon .material-symbols-outlined { font-size: 22px; }
.dp-hero__body { flex: 1; min-width: 0; }
.dp-hero__title { font-size: 16px; font-weight: 600; margin: 0 0 2px; }
.dp-hero__sub { margin: 0; font-size: 12px; color: var(--color-text-secondary); }
.dp-hero__form { display: flex; gap: 8px; }

/* ── Page preset chips ───────────────────────────────────── */
.dp-presets { margin-bottom: 32px; }
.dp-presets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}
.dp-preset {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 12px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  cursor: pointer;
  font-family: inherit;
  text-align: left;
  transition: border-color 140ms, background 140ms;
}
.dp-preset:hover { border-color: var(--color-text-tertiary); background: var(--color-surface-container-lowest); }
.dp-preset__label { flex: 1; }
.dp-preset__arrow { font-size: 16px !important; color: var(--color-text-tertiary); }

/* ── App full templates ─────────────────────────────────── */
.dp-app-templates {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 12px;
}
.dp-app-template {
  text-align: left;
  padding: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  cursor: pointer;
  font-family: inherit;
  color: var(--color-text-primary);
  transition: border-color 140ms;
}
.dp-app-template:hover { border-color: var(--color-text-tertiary); }
.dp-app-template__name { font-size: 14px; font-weight: 600; margin-bottom: 4px; }
.dp-app-template__pages { font-size: 11px; color: var(--color-text-tertiary); line-height: 1.5; }

/* ── Recent projects ────────────────────────────────────── */
.dp-recent { margin-top: 8px; }
.dp-meta { font-size: 11px; color: var(--color-text-tertiary); }
.dp-projects {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 12px;
}
.dp-project {
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px 12px;
  padding: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 140ms, transform 140ms;
  position: relative;
}
.dp-project:hover { border-color: var(--color-text-tertiary); transform: translateY(-1px); }
.dp-project__thumb {
  grid-column: 1 / -1;
  height: 56px;
  background: var(--color-surface-container-lowest);
  border-radius: 4px;
  padding: 8px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 4px;
}
.dp-project__page {
  height: 6px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 2px;
}
.dp-project__empty { color: var(--color-text-tertiary); font-size: 11px; text-align: center; }
.dp-project__name { font-size: 14px; font-weight: 600; margin: 0; }
.dp-project__meta { display: flex; gap: 4px; align-items: center; }
.dp-project__del {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  color: var(--color-text-tertiary);
}
.dp-project__del:hover { background: #fee2e2; color: #b91c1c; }

/* ── Empty state ──────────────────────────────────────── */
.dp-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 60px 20px;
  background: var(--color-surface-container-lowest);
  border: 1px dashed var(--color-border);
  border-radius: 8px;
}
.dp-empty__icon {
  width: 48px;
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--color-surface);
  border-radius: 50%;
  margin-bottom: 12px;
}
.dp-empty__icon .material-symbols-outlined { font-size: 24px; color: var(--color-text-tertiary); }
.dp-empty__title { font-size: 15px; font-weight: 600; margin: 0 0 4px; }
.dp-empty__sub { margin: 0; font-size: 12px; color: var(--color-text-secondary); }

/* ── Buttons (shared) ────────────────────────────────── */
.dp-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-primary);
  cursor: pointer;
  font-family: inherit;
  transition: background 120ms, border-color 120ms;
}
.dp-btn:hover:not(:disabled) { background: var(--color-surface-container-low); }
.dp-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.dp-btn--sm { padding: 5px 10px; font-size: 12px; }
.dp-btn--primary {
  background: var(--color-brand, #0a0a0a);
  color: #fff;
  border-color: var(--color-brand, #0a0a0a);
}
.dp-btn--primary:hover:not(:disabled) { background: #1f2937; border-color: #1f2937; }
.dp-btn--danger { color: #b91c1c; }
.dp-btn--danger:hover:not(:disabled) { background: #fee2e2; }

.dp-input {
  flex: 1;
  padding: 8px 12px;
  border: 1px solid var(--color-border);
  border-radius: 4px;
  background: var(--color-surface);
  font-size: 13px;
  color: var(--color-text-primary);
  font-family: inherit;
  outline: none;
  transition: border-color 120ms;
}
.dp-input:focus { border-color: var(--color-text-tertiary); }
.dp-input:disabled { background: var(--color-surface-container); color: var(--color-text-tertiary); cursor: not-allowed; }

/* ── Editor mode ──────────────────────────────────────── */
.dp-editor {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--color-surface);
}
.dp-editor__topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  height: 48px;
  padding: 0 16px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.dp-editor__back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: transparent;
  border: none;
  padding: 4px 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-family: inherit;
  border-radius: 4px;
}
.dp-editor__back:hover { background: var(--color-surface-container-low); color: var(--color-text-primary); }
.dp-editor__title { font-size: 14px; font-weight: 600; }
.dp-editor__spacer { flex: 1; }
.dp-editor__body {
  flex: 1;
  display: grid;
  grid-template-columns: 180px 1fr 280px;
  min-height: 0;
}
.dp-editor__pages {
  border-right: 1px solid var(--color-border);
  padding: 16px;
  overflow-y: auto;
}
.dp-page-list { display: flex; flex-direction: column; gap: 4px; }
.dp-page-tab {
  text-align: left;
  padding: 8px 10px;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 4px;
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-family: inherit;
}
.dp-page-tab:hover { background: var(--color-surface-container-low); color: var(--color-text-primary); }
.dp-page-tab--active {
  background: var(--color-text-primary);
  color: var(--color-surface);
  border-color: var(--color-text-primary);
}
.dp-editor__canvas { background: var(--color-surface-container-lowest); overflow: auto; min-height: 0; }
.dp-editor__props {
  border-left: 1px solid var(--color-border);
  padding: 16px;
  overflow-y: auto;
}
.dp-props-form { display: flex; flex-direction: column; gap: 12px; }
.dp-props-empty { font-size: 13px; color: var(--color-text-secondary); text-align: center; padding: 24px 0; }
.dp-field { display: flex; flex-direction: column; gap: 6px; }
.dp-field__label { font-size: 11px; font-weight: 500; color: var(--color-text-secondary); text-transform: uppercase; letter-spacing: 0.04em; }
</style>

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
