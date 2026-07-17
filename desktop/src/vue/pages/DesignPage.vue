<script setup lang="ts">
/**
 * Design tool — project list + AI page gen + DesignCanvas.
 * Script and template are aligned (rewired after v3.1 desync).
 */
import { ref, computed, watch, onMounted } from 'vue'
import DesignCanvas from '../components/design/DesignCanvas.vue'
import DesignPreview from '../components/design/DesignPreview.vue'
import { getApiUrl } from '../api/client'
import {
  type DesignData,
  autoRepairDesignData,
  emptyDesignData,
  parseAndRepairDesignResponse,
} from '../lib/designJson'

interface DesignPageData {
  id: string
  name: string
  data: DesignData
}
interface DesignProject {
  id: string
  name: string
  pages: DesignPageData[]
  activePageId: string | null
  createdAt: number
}

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
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return []
}
function saveProjects(list: DesignProject[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
  } catch { /* ignore */ }
}
function genId() {
  return `p${Date.now()}${Math.floor(Math.random() * 1000)}`
}

function emptyData(): DesignData {
  return emptyDesignData()
}

const projects = ref<DesignProject[]>(loadProjects())
const activeProject = ref<DesignProject | null>(null)
const prompt = ref('')
const loading = ref(false)
const error = ref<string | null>(null)
const statusMsg = ref<string | null>(null)
const newProjectName = ref('')
const newProjectNameInput = ref<HTMLInputElement | null>(null)

watch(projects, (val) => saveProjects(val), { deep: true })

onMounted(() => {
  newProjectNameInput.value?.focus()
})

function upsertProject(updated: DesignProject) {
  activeProject.value = updated
  projects.value = projects.value.map((p) => (p.id === updated.id ? updated : p))
  if (!projects.value.find((p) => p.id === updated.id)) {
    projects.value = [updated, ...projects.value]
  }
}

function createProject(name: string) {
  if (!name.trim()) return
  const project: DesignProject = {
    id: genId(),
    name: name.trim(),
    pages: [],
    activePageId: null,
    createdAt: Date.now(),
  }
  projects.value = [project, ...projects.value]
  activeProject.value = project
  newProjectName.value = ''
  error.value = null
  statusMsg.value = null
}

function deleteProject(id: string) {
  if (!confirm('删除此项目？')) return
  projects.value = projects.value.filter((p) => p.id !== id)
  if (activeProject.value?.id === id) activeProject.value = null
}

function deleteCurrentProject() {
  if (!activeProject.value) return
  deleteProject(activeProject.value.id)
}

function saveProject() {
  if (!activeProject.value) return
  // deep watch already persists; give feedback
  saveProjects(projects.value)
  statusMsg.value = '已保存到本机'
  setTimeout(() => {
    if (statusMsg.value === '已保存到本机') statusMsg.value = null
  }, 2000)
}

function addPage(name?: string) {
  if (!activeProject.value) return
  const n = (name && name.trim()) || `页面 ${activeProject.value.pages.length + 1}`
  const page: DesignPageData = { id: genId(), name: n, data: emptyData() }
  const updated: DesignProject = {
    ...activeProject.value,
    pages: [...activeProject.value.pages, page],
    activePageId: page.id,
  }
  upsertProject(updated)
}

function deletePage(pageId: string) {
  if (!activeProject.value) return
  if (!confirm('删除此页面？')) return
  const pages = activeProject.value.pages.filter((p) => p.id !== pageId)
  const updated: DesignProject = {
    ...activeProject.value,
    pages,
    activePageId:
      activeProject.value.activePageId === pageId
        ? (pages[0]?.id ?? null)
        : activeProject.value.activePageId,
  }
  upsertProject(updated)
}

function selectPage(pageId: string) {
  if (!activeProject.value) return
  upsertProject({ ...activeProject.value, activePageId: pageId })
}

function updatePageData(pageId: string, data: DesignData) {
  if (!activeProject.value) return
  const updated: DesignProject = {
    ...activeProject.value,
    pages: activeProject.value.pages.map((p) =>
      p.id === pageId
        ? { ...p, data: autoRepairDesignData(JSON.parse(JSON.stringify(data))) }
        : p,
    ),
  }
  upsertProject(updated)
}

/** Call design generate API; does not own loading (callers do). */
async function generatePage(genPrompt: string): Promise<DesignData | null> {
  try {
    const r = await fetch(getApiUrl('/api/design/generate'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: genPrompt }),
    })
    if (!r.ok) {
      const errText = await r.text().catch(() => '')
      throw new Error(errText || `HTTP ${r.status}`)
    }
    const resp = await r.json()
    const text: string = resp.content || ''
    const data = parseAndRepairDesignResponse(text)
    if (data) return data
    error.value = `AI 返回格式有误：${text.slice(0, 180).replace(/\s+/g, ' ')}…`
    return null
  } catch (e: any) {
    error.value = `生成失败: ${e?.message || e}`
    return null
  }
}

async function handleGenerate() {
  if (!prompt.value.trim() || !activeProject.value || loading.value) return
  loading.value = true
  error.value = null
  statusMsg.value = '正在调用 AI 生成…'
  try {
    const data = await generatePage(prompt.value)
    if (data && activeProject.value) {
      const pageName = prompt.value.trim().slice(0, 16) || '生成页'
      const page: DesignPageData = { id: genId(), name: pageName, data }
      upsertProject({
        ...activeProject.value,
        pages: [...activeProject.value.pages, page],
        activePageId: page.id,
      })
      prompt.value = ''
      statusMsg.value = '已生成页面'
    } else {
      statusMsg.value = null
    }
  } finally {
    loading.value = false
  }
}

async function handleGenerateApp(preset: (typeof FULL_APP_PROMPTS)[0]) {
  if (!activeProject.value || loading.value) return
  loading.value = true
  error.value = null
  const newPages: DesignPageData[] = []
  try {
    for (const pageName of preset.pages) {
      statusMsg.value = `正在生成：${pageName}…`
      const data = await generatePage(`${preset.name}的${pageName}，风格统一、简洁现代`)
      if (data) newPages.push({ id: genId(), name: pageName, data })
    }
    if (newPages.length > 0 && activeProject.value) {
      upsertProject({
        ...activeProject.value,
        pages: [...activeProject.value.pages, ...newPages],
        activePageId: newPages[0].id,
      })
    }
    statusMsg.value = newPages.length ? `已生成 ${newPages.length} 个页面` : null
  } finally {
    loading.value = false
  }
}

/** Home: create project then AI one page */
async function createProjectAndApply(pagePrompt: string) {
  if (loading.value) return
  const name =
    newProjectName.value.trim() ||
    PAGE_PRESETS.find((p) => p.prompt === pagePrompt)?.label ||
    '未命名项目'
  createProject(name)
  if (!activeProject.value) return
  loading.value = true
  error.value = null
  statusMsg.value = '正在调用 AI 生成…'
  try {
    const data = await generatePage(pagePrompt)
    if (data && activeProject.value) {
      const page: DesignPageData = {
        id: genId(),
        name: PAGE_PRESETS.find((p) => p.prompt === pagePrompt)?.label || '生成页',
        data,
      }
      upsertProject({
        ...activeProject.value,
        pages: [page],
        activePageId: page.id,
      })
      statusMsg.value = '已生成页面'
    } else {
      statusMsg.value = null
    }
  } finally {
    loading.value = false
  }
}

/** Home: create project then multi-page app */
async function createProjectAndApplyApp(preset: (typeof FULL_APP_PROMPTS)[0]) {
  if (loading.value) return
  const name = newProjectName.value.trim() || preset.name
  createProject(name)
  await handleGenerateApp(preset)
}

const activePage = computed<DesignPageData | null>(() => {
  if (!activeProject.value) return null
  return (
    activeProject.value.pages.find((p) => p.id === activeProject.value!.activePageId) || null
  )
})

function formatRelative(ts: number): string {
  const days = Math.floor((Date.now() - ts) / 86400000)
  if (days === 0) return '今天'
  if (days === 1) return '昨天'
  if (days < 7) return `${days} 天前`
  if (days < 30) return `${Math.floor(days / 7)} 周前`
  return new Date(ts).toLocaleDateString('zh-CN')
}

function onCanvasSave(data: DesignData) {
  if (!activePage.value) return
  updatePageData(activePage.value.id, data)
  statusMsg.value = '画布已保存'
  setTimeout(() => {
    if (statusMsg.value === '画布已保存') statusMsg.value = null
  }, 1500)
}
</script>

<template>
  <!-- Project list -->
  <div v-if="!activeProject" class="dp-page">
    <div class="dp-page__inner">
      <header class="dp-page__head">
        <div>
          <h1 class="dp-page__title">设计工具</h1>
          <p class="dp-page__sub">用 AI 生成 UI 原型，拖拽组件、编辑属性、导出 .madcop</p>
        </div>
      </header>

      <section class="dp-hero">
        <div class="dp-hero__inner">
          <div class="dp-hero__icon">
            <span class="material-symbols-outlined">auto_awesome</span>
          </div>
          <div class="dp-hero__body">
            <h2 class="dp-hero__title">从一个提示词开始</h2>
            <p class="dp-hero__sub">输入项目名，再选模板；AI 会生成可编辑的组件树</p>
          </div>
        </div>
        <div class="dp-hero__form">
          <input
            ref="newProjectNameInput"
            v-model="newProjectName"
            type="text"
            placeholder="项目名…"
            class="dp-input"
            :disabled="loading"
            @keydown.enter="createProject(newProjectName)"
          />
          <button
            type="button"
            class="dp-btn dp-btn--primary"
            :disabled="!newProjectName.trim() || loading"
            @click="createProject(newProjectName)"
          >
            创建项目
          </button>
        </div>
        <p v-if="error" class="dp-error">{{ error }}</p>
        <p v-if="statusMsg" class="dp-status">{{ statusMsg }}</p>
        <p v-if="loading" class="dp-status">生成中，请稍候…</p>
      </section>

      <section class="dp-presets">
        <header class="dp-section__head">
          <div>
            <h3 class="dp-section__title">页面模板</h3>
            <p class="dp-section__sub">可先填项目名，再点模板（未填则用模板名）</p>
          </div>
        </header>
        <div class="dp-presets-grid">
          <button
            v-for="(p, i) in PAGE_PRESETS"
            :key="i"
            type="button"
            class="dp-preset"
            :disabled="loading"
            @click="createProjectAndApply(p.prompt)"
          >
            <span class="dp-preset__label">{{ p.label }}</span>
            <span class="dp-preset__arrow material-symbols-outlined">arrow_forward</span>
          </button>
        </div>
      </section>

      <section class="dp-presets">
        <header class="dp-section__head">
          <div>
            <h3 class="dp-section__title">多页面 App 模板</h3>
            <p class="dp-section__sub">依次生成多个页面（较慢）</p>
          </div>
        </header>
        <div class="dp-app-templates">
          <button
            v-for="(t, i) in FULL_APP_PROMPTS"
            :key="i"
            type="button"
            class="dp-app-template"
            :disabled="loading"
            @click="createProjectAndApplyApp(t)"
          >
            <div class="dp-app-template__name">{{ t.name }}</div>
            <div class="dp-app-template__pages">
              {{ t.pages.length }} 个页面 · {{ t.pages.join(' · ') }}
            </div>
          </button>
        </div>
      </section>

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
          <p class="dp-empty__sub">在上方输入项目名或点模板开始</p>
        </div>

        <div v-else class="dp-projects">
          <article
            v-for="proj in projects"
            :key="proj.id"
            class="dp-project"
            @click="activeProject = proj; error = null"
          >
            <div class="dp-project__thumb">
              <div
                v-for="(p, i) in proj.pages.slice(0, 3)"
                :key="p.id"
                class="dp-project__page"
                :style="{ width: 40 + i * 12 + '%', opacity: 0.6 + i * 0.13 }"
              />
              <div v-if="proj.pages.length === 0" class="dp-project__empty">空</div>
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
              type="button"
              class="dp-project__del"
              aria-label="删除"
              @click.stop="deleteProject(proj.id)"
            >
              <span class="material-symbols-outlined" style="font-size: 16px">delete</span>
            </button>
          </article>
        </div>
      </section>
    </div>
  </div>

  <!-- Editor -->
  <div v-else class="dp-editor">
    <header class="dp-editor__topbar">
      <button type="button" class="dp-editor__back" @click="activeProject = null">
        <span class="material-symbols-outlined" style="font-size: 18px">arrow_back</span>
        返回
      </button>
      <div class="dp-editor__title">{{ activeProject.name }}</div>
      <div class="dp-editor__spacer" />
      <span v-if="loading" class="dp-status">生成中…</span>
      <span v-else-if="statusMsg" class="dp-status">{{ statusMsg }}</span>
      <button type="button" class="dp-btn" @click="saveProject">保存</button>
      <button type="button" class="dp-btn dp-btn--danger" @click="deleteCurrentProject">删除项目</button>
    </header>

    <!-- AI generate bar -->
    <div class="dp-ai-bar">
      <input
        v-model="prompt"
        type="text"
        class="dp-input dp-ai-bar__input"
        placeholder="描述要生成的页面，例如：带搜索栏的商品列表…"
        :disabled="loading"
        @keydown.enter="handleGenerate"
      />
      <button
        type="button"
        class="dp-btn dp-btn--primary"
        :disabled="loading || !prompt.trim()"
        @click="handleGenerate"
      >
        {{ loading ? '生成中…' : 'AI 生成页面' }}
      </button>
      <button
        type="button"
        class="dp-btn"
        :disabled="loading"
        @click="addPage()"
      >
        + 空白页
      </button>
    </div>
    <p v-if="error" class="dp-error dp-error--bar">{{ error }}</p>

    <div class="dp-editor__body">
      <div class="dp-editor__pages">
        <div class="dp-section__head">
          <h3 class="dp-section__title">页面</h3>
          <button type="button" class="dp-btn dp-btn--sm" @click="addPage()">+ 新页面</button>
        </div>
        <div v-if="activeProject.pages.length === 0" class="dp-props-empty">
          <p>还没有页面。用上方 AI 生成，或点「空白页」。</p>
        </div>
        <div class="dp-page-list">
          <div
            v-for="p in activeProject.pages"
            :key="p.id"
            class="dp-page-row"
          >
            <button
              type="button"
              :class="[
                'dp-page-tab',
                { 'dp-page-tab--active': p.id === activeProject.activePageId },
              ]"
              @click="selectPage(p.id)"
            >
              {{ p.name || '未命名' }}
            </button>
            <button
              type="button"
              class="dp-page-del"
              title="删除页面"
              @click="deletePage(p.id)"
            >
              ×
            </button>
          </div>
        </div>
      </div>

      <div class="dp-editor__canvas">
        <DesignCanvas
          v-if="activePage"
          :key="activePage.id"
          :initial-data="activePage.data"
          @save="onCanvasSave"
        />
        <div v-else class="dp-canvas-empty">
          <p>选择或生成一个页面以开始编辑</p>
          <p class="dp-meta">画布左侧可拖入组件；点「保存」写回项目</p>
        </div>
      </div>
    </div>

    <DesignPreview v-if="activePage" :data="activePage.data" />
  </div>
</template>

<style scoped>
.dp-page { width: 100%; height: 100%; overflow-y: auto; background: var(--color-surface); }
.dp-page__inner { max-width: 960px; margin: 0 auto; padding: 48px 32px 64px; }
.dp-page__head { margin-bottom: 32px; }
.dp-page__title { font-size: 28px; font-weight: 600; margin: 0 0 4px; letter-spacing: -0.01em; color: var(--color-text-primary); }
.dp-page__sub { margin: 0; font-size: 14px; color: var(--color-text-secondary); }

.dp-section__head { margin-bottom: 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.dp-section__head--row { justify-content: space-between; }
.dp-section__title { font-size: 14px; font-weight: 600; margin: 0; color: var(--color-text-primary); }
.dp-section__sub { margin: 4px 0 0; font-size: 12px; color: var(--color-text-secondary); }

.dp-hero {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 20px;
  margin-bottom: 32px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.dp-hero__inner { display: flex; gap: 12px; align-items: center; }
.dp-hero__icon {
  width: 40px; height: 40px; display: flex; align-items: center; justify-content: center;
  border-radius: 10px; background: color-mix(in srgb, var(--color-brand) 12%, transparent);
  color: var(--color-brand);
}
.dp-hero__title { margin: 0; font-size: 16px; font-weight: 600; color: var(--color-text-primary); }
.dp-hero__sub { margin: 4px 0 0; font-size: 13px; color: var(--color-text-secondary); }
.dp-hero__form { display: flex; gap: 10px; }

.dp-input {
  flex: 1; padding: 10px 14px; border: 1px solid var(--color-border); border-radius: 10px;
  background: var(--color-surface-container-lowest, var(--color-surface));
  color: var(--color-text-primary); font-size: 13px; outline: none;
}
.dp-input:focus { border-color: var(--color-brand); }

.dp-btn {
  padding: 8px 14px; border-radius: 10px; border: 1px solid var(--color-border);
  background: var(--color-surface); color: var(--color-text-primary); font-size: 13px;
  cursor: pointer; font-weight: 500;
}
.dp-btn:hover { background: var(--color-surface-hover, var(--color-surface-container)); }
.dp-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.dp-btn--primary {
  background: var(--color-brand); color: #fff; border-color: transparent;
}
.dp-btn--primary:hover { opacity: 0.92; }
.dp-btn--danger { color: var(--color-error); border-color: color-mix(in srgb, var(--color-error) 30%, transparent); }
.dp-btn--sm { padding: 4px 10px; font-size: 12px; }

.dp-error { margin: 0; font-size: 12px; color: var(--color-error); }
.dp-error--bar { padding: 0 16px 8px; }
.dp-status { margin: 0; font-size: 12px; color: var(--color-text-tertiary); }
.dp-meta { font-size: 12px; color: var(--color-text-tertiary); }

.dp-presets { margin-bottom: 32px; }
.dp-presets-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 10px; }
.dp-preset {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px; border: 1px solid var(--color-border); border-radius: 12px;
  background: var(--color-surface); cursor: pointer; text-align: left;
}
.dp-preset:hover { border-color: var(--color-brand); }
.dp-preset:disabled { opacity: 0.5; cursor: not-allowed; }
.dp-preset__label { font-size: 13px; font-weight: 600; color: var(--color-text-primary); }
.dp-preset__arrow { font-size: 16px; color: var(--color-text-tertiary); }

.dp-app-templates { display: flex; flex-direction: column; gap: 10px; }
.dp-app-template {
  text-align: left; padding: 14px 16px; border: 1px solid var(--color-border);
  border-radius: 12px; background: var(--color-surface); cursor: pointer;
}
.dp-app-template:hover { border-color: var(--color-brand); }
.dp-app-template:disabled { opacity: 0.5; cursor: not-allowed; }
.dp-app-template__name { font-size: 14px; font-weight: 600; color: var(--color-text-primary); }
.dp-app-template__pages { margin-top: 4px; font-size: 12px; color: var(--color-text-tertiary); }

.dp-empty { text-align: center; padding: 40px 20px; border: 1px dashed var(--color-border); border-radius: 12px; }
.dp-empty__icon { font-size: 36px; color: var(--color-text-tertiary); opacity: 0.5; }
.dp-empty__title { margin: 8px 0 4px; font-size: 14px; color: var(--color-text-primary); }
.dp-empty__sub { margin: 0; font-size: 12px; color: var(--color-text-tertiary); }

.dp-projects { display: flex; flex-direction: column; gap: 10px; }
.dp-project {
  display: flex; align-items: center; gap: 14px; padding: 12px 14px;
  border: 1px solid var(--color-border); border-radius: 12px; cursor: pointer;
  background: var(--color-surface);
}
.dp-project:hover { border-color: var(--color-border-focus, var(--color-brand)); }
.dp-project__thumb {
  width: 72px; height: 48px; border-radius: 8px; background: var(--color-surface-container-low);
  position: relative; overflow: hidden; flex-shrink: 0;
}
.dp-project__page {
  position: absolute; bottom: 6px; left: 8px; height: 28px;
  background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 4px;
}
.dp-project__empty {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  font-size: 11px; color: var(--color-text-tertiary);
}
.dp-project__body { flex: 1; min-width: 0; }
.dp-project__name { margin: 0; font-size: 14px; font-weight: 600; color: var(--color-text-primary); }
.dp-project__meta { display: flex; gap: 6px; margin-top: 4px; }
.dp-project__del {
  border: none; background: transparent; cursor: pointer; color: var(--color-text-tertiary);
  opacity: 0; padding: 6px; border-radius: 8px;
}
.dp-project:hover .dp-project__del { opacity: 1; }
.dp-project__del:hover { color: var(--color-error); }

/* Editor */
.dp-editor {
  display: flex; flex-direction: column; height: 100%; width: 100%;
  background: var(--color-surface); overflow: hidden;
}
.dp-editor__topbar {
  display: flex; align-items: center; gap: 10px; padding: 10px 14px;
  border-bottom: 1px solid var(--color-border); flex-shrink: 0;
}
.dp-editor__back {
  display: inline-flex; align-items: center; gap: 4px; border: none; background: transparent;
  cursor: pointer; color: var(--color-text-secondary); font-size: 13px; padding: 6px 8px;
  border-radius: 8px;
}
.dp-editor__back:hover { background: var(--color-surface-hover); color: var(--color-text-primary); }
.dp-editor__title { font-size: 14px; font-weight: 600; color: var(--color-text-primary); }
.dp-editor__spacer { flex: 1; }

.dp-ai-bar {
  display: flex; gap: 8px; padding: 10px 14px; border-bottom: 1px solid var(--color-border);
  flex-shrink: 0; align-items: center;
}
.dp-ai-bar__input { flex: 1; }

.dp-editor__body {
  flex: 1; min-height: 0; display: flex; overflow: hidden;
}
.dp-editor__pages {
  width: 200px; flex-shrink: 0; border-right: 1px solid var(--color-border);
  padding: 12px; overflow-y: auto;
}
.dp-page-list { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.dp-page-row { display: flex; align-items: center; gap: 4px; }
.dp-page-tab {
  flex: 1; text-align: left; padding: 8px 10px; border-radius: 8px; border: 1px solid transparent;
  background: transparent; cursor: pointer; font-size: 12px; color: var(--color-text-secondary);
}
.dp-page-tab:hover { background: var(--color-surface-hover); }
.dp-page-tab--active {
  background: color-mix(in srgb, var(--color-brand) 10%, transparent);
  color: var(--color-brand); font-weight: 600; border-color: color-mix(in srgb, var(--color-brand) 20%, transparent);
}
.dp-page-del {
  border: none; background: transparent; cursor: pointer; color: var(--color-text-tertiary);
  width: 24px; height: 24px; border-radius: 6px; font-size: 14px;
}
.dp-page-del:hover { color: var(--color-error); background: var(--color-surface-hover); }

.dp-editor__canvas { flex: 1; min-width: 0; min-height: 0; overflow: hidden; }
.dp-canvas-empty {
  height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: var(--color-text-tertiary); font-size: 13px; gap: 6px;
}
.dp-props-empty { font-size: 12px; color: var(--color-text-tertiary); line-height: 1.45; padding: 8px 0; }
</style>
