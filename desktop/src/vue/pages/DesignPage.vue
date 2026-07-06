<script setup lang="ts">
/**
 * v3.0 — Design tool page: multi-page project management + AI generation.
 *
 * 1:1 Vue 3 port of src/pages/DesignPage.tsx (React).
 * Features:
 *  - Multi-project management (localStorage)
 *  - Per-project: multi-page design
 *  - AI generation via /api/design/generate (single page or full app)
 *  - Page preset templates (登录页/仪表盘/个人中心/落地页)
 *  - Full-app templates (电商 App/SaaS 后台/社交 App)
 *  - Auto-repair for malformed LLM output
 */

import { ref, computed, watch, onMounted } from 'vue'
import DesignCanvas, { type DesignData } from '../components/design/DesignCanvas.vue'

function emptyData(): DesignData {
  return { root: { props: { bgColor: '#FFFFFF', padding: 40 } }, content: [] }
}
import { getApiUrl } from '../api/client'

// ── Types ──────────────────────────────────────────────────────────────

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

// ── Presets ───────────────────────────────────────────────────────────

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

// ── Project storage ──────────────────────────────────────────────────

const STORAGE_KEY = 'madcop_design_projects'

function loadProjects(): DesignProject[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {}
  return []
}

function saveProjects(projects: DesignProject[]) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(projects))
  } catch {}
}

function genId() {
  return `p${Date.now()}${Math.floor(Math.random() * 1000)}`
}

// ── Auto-repair for LLM output ──────────────────────────────────────

const componentNames: Record<string, boolean> = {
  Header: true, Paragraph: true, Button: true, Image: true,
  Input: true, Card: true, Flex: true, Grid: true,
  Section: true, Divider: true, Space: true,
}

const defaultsFor: Record<string, Record<string, any>> = {
  Header: { text: '标题', level: '2', fontSize: 24 },
  Paragraph: { text: '文字', fontSize: 14 },
  Button: { text: '按钮', variant: 'primary' },
  Card: { padding: 20, radius: 12 },
  Flex: { direction: 'column', gap: 8 },
  Grid: { columns: 2, gap: 12 },
  Space: { height: 20 },
}

function autoRepair(data: any): DesignData {
  if (!data.root) data.root = { props: { bgColor: '#FFFFFF', padding: 40 } }
  if (!data.root.props) data.root.props = {}
  if (!data.root.props.bgColor) data.root.props.bgColor = '#FFFFFF'
  if (!data.root.props.padding) data.root.props.padding = 40
  if (!Array.isArray(data.content)) data.content = []
  function repairItem(item: any): any {
    if (!item.type) return null
    if (!componentNames[item.type]) return null
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

// ── Main state ───────────────────────────────────────────────────────

const projects = ref<DesignProject[]>(loadProjects())
const activeProject = ref<DesignProject | null>(null)
const prompt = ref('')
const loading = ref(false)
const error = ref<string | null>(null)
const showGenAll = ref(false)
const newProjectName = ref('')

watch(projects, (val) => saveProjects(val), { deep: true })

onMounted(() => {
  if (projects.value.length > 0) {
    // Don't auto-open — show project list first
  }
})

// ── Project actions ──────────────────────────────────────────────────

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

// ── Page actions ─────────────────────────────────────────────────────

function addPage(name: string) {
  if (!activeProject.value) return
  const page: DesignPageData = { id: genId(), name, data: emptyData() }
  const updated: DesignProject = {
    ...activeProject.value,
    pages: [...activeProject.value.pages, page],
    activePageId: page.id,
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
    activePageId: activeProject.value.activePageId === pageId
      ? null
      : activeProject.value.activePageId,
  }
  activeProject.value = updated
  projects.value = projects.value.map((p) => p.id === updated.id ? updated : p)
}

function selectPage(pageId: string) {
  if (!activeProject.value) return
  const updated: DesignProject = {
    ...activeProject.value,
    activePageId: pageId,
  }
  activeProject.value = updated
  projects.value = projects.value.map((p) => p.id === updated.id ? updated : p)
}

function updatePageData(pageId: string, data: DesignData) {
  if (!activeProject.value) return
  const updated: DesignProject = {
    ...activeProject.value,
    pages: activeProject.value.pages.map((p) =>
      p.id === pageId ? { ...p, data } : p
    ),
  }
  activeProject.value = updated
  projects.value = projects.value.map((p) => p.id === updated.id ? updated : p)
}

// ── AI generation ────────────────────────────────────────────────────

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
      pages: [...activeProject.value.pages, page],
      activePageId: page.id,
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
    if (data) {
      newPages.push({ id: genId(), name: pageName, data })
    }
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

// ── Computed ─────────────────────────────────────────────────────────

const activePage = computed<DesignPageData | null>(() => {
  if (!activeProject.value) return null
  return activeProject.value.pages.find((p) => p.id === activeProject.value!.activePageId) || null
})

// ── Render: project list ─────────────────────────────────────────────
</script>

<template>
  <!-- No active project: project list -->
  <div v-if="!activeProject" :class="['design-page', 'flex', 'h-screen', 'w-screen', 'overflow-hidden', 'bg-[var(--color-surface-container-lowest)]', 'text-[var(--color-text-primary)]']">
    <div style="max-width: 720px; margin: 0 auto; padding: 40px 20px; width: 100%;">
      <h1 style="font-size: 24px; font-weight: 700; margin-bottom: 6px; text-align: center; color: var(--color-text-primary);">
        设计工具
      </h1>
      <p style="font-size: 14px; color: var(--color-text-tertiary); margin-bottom: 32px; text-align: center;">
        创建项目，用 AI 批量生成原型设计
      </p>

      <!-- Create new project -->
      <div style="display: flex; gap: 8px; margin-bottom: 32px;">
        <input
          v-model="newProjectName"
          type="text"
          placeholder="输入项目名称…"
          @keydown.enter="createProject(newProjectName)"
          style="flex: 1; padding: 10px 14px; border: 1px solid var(--color-border); border-radius: 6px; font-size: 14px; outline: none; background: var(--color-surface); color: var(--color-text-primary);"
        />
        <button
          @click="createProject(newProjectName)"
          :disabled="!newProjectName.trim()"
          style="padding: 10px 20px; background: #7C3AED; color: #fff; border: none; border-radius: 6px; cursor: pointer; font-size: 14px; font-weight: 600; opacity: newProjectName.trim() ? 1 : 0.5;"
        >新建项目</button>
      </div>

      <!-- Existing projects -->
      <div
        v-if="projects.length === 0"
        style="text-align: center; padding: 60px 20px; color: var(--color-text-tertiary); font-size: 14px;"
      >
        还没有项目，创建一个开始吧
      </div>
      <div
        v-else
        style="display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 16px;"
      >
        <div
          v-for="proj in projects"
          :key="proj.id"
          @click="activeProject = proj"
          class="design-project-card"
        >
          <div style="font-size: 15px; font-weight: 600; margin-bottom: 4px; color: var(--color-text-primary);">
            {{ proj.name }}
          </div>
          <div style="font-size: 12px; color: var(--color-text-tertiary);">
            {{ proj.pages.length }} 个页面
          </div>
          <div style="font-size: 11px; color: var(--color-text-tertiary); margin-top: 8px; opacity: 0.7;">
            {{ new Date(proj.createdAt).toLocaleDateString('zh-CN') }}
          </div>
          <button
            @click.stop="deleteProject(proj.id)"
            style="margin-top: 12px; padding: 4px 10px; font-size: 11px; border: 1px solid color-mix(in srgb, var(--color-error) 30%, transparent); border-radius: 3px; background: var(--color-surface); color: var(--color-error); cursor: pointer;"
          >删除</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Active project: editor + AI generation -->
  <div v-else class="design-page flex h-screen w-screen flex-col overflow-hidden bg-[var(--color-surface)]">
    <!-- Top bar -->
    <div
      style="display: flex; align-items: center; justify-content: space-between; padding: 8px 16px; border-bottom: 1px solid var(--color-border); background: var(--color-surface); flex-shrink: 0;"
    >
      <div style="display: flex; align-items: center; gap: 12px;">
        <button
          @click="activeProject = null"
          style="padding: 4px 12px; border: 1px solid var(--color-border); border-radius: 4px; cursor: pointer; font-size: 12px; color: var(--color-text-secondary); background: var(--color-surface);"
        >← 项目列表</button>
        <span style="font-size: 14px; font-weight: 600; color: var(--color-text-primary);">{{ activeProject.name }}</span>
      </div>
      <div style="display: flex; gap: 8px;">
        <button
          @click="showGenAll = !showGenAll"
          style="padding: 4px 12px; border: 1px solid #7C3AED; border-radius: 4px; cursor: pointer; font-size: 12px; color: #7C3AED; background: var(--color-surface);"
        >批量生成</button>
      </div>
    </div>

    <!-- Batch generation dropdown -->
    <div
      v-if="showGenAll"
      style="padding: 12px; background: var(--color-surface-container-lowest); border-bottom: 1px solid var(--color-border); display: flex; gap: 8px; flex-wrap: wrap; align-items: center;"
    >
      <span style="font-size: 12px; color: var(--color-text-tertiary);">一键生成:</span>
      <button
        v-for="preset in FULL_APP_PROMPTS"
        :key="preset.name"
        @click="handleGenerateApp(preset)"
        :disabled="loading"
        style="padding: 4px 14px; border: 1px solid var(--color-border); border-radius: 20px; cursor: pointer; font-size: 12px; background: var(--color-surface); color: var(--color-text-secondary);"
      >{{ preset.name }} ({{ preset.pages.length }}页)</button>
    </div>

    <!-- Page tabs -->
    <div
      style="display: flex; align-items: center; gap: 2px; padding: 6px 16px; border-bottom: 1px solid var(--color-border); background: var(--color-surface-container-lowest); overflow-x: auto; flex-shrink: 0;"
    >
      <div
        v-for="page in activeProject.pages"
        :key="page.id"
        @click="selectPage(page.id)"
        :class="['design-page-tab', activeProject.activePageId === page.id ? 'design-page-tab--active' : '']"
      >
        <span>{{ page.name }}</span>
        <button
          @click.stop="deletePage(page.id)"
          style="background: none; border: none; cursor: pointer; font-size: 14px; color: var(--color-text-tertiary); padding: 0; line-height: 1; margin-left: 4px;"
        >×</button>
      </div>
      <button
        @click="addPage(`页面 ${activeProject.pages.length + 1}`)"
        style="padding: 5px 10px; border: 1px dashed var(--color-border); border-radius: 4px; cursor: pointer; font-size: 12px; color: var(--color-text-tertiary); background: transparent;"
      >+ 新页面</button>
    </div>

    <!-- AI prompt bar (when no page active) -->
    <div
      v-if="!activePage && !loading"
      style="padding: 40px 20px; max-width: 640px; margin: 0 auto; width: 100%; flex: 1; overflow-y: auto;"
    >
      <!-- Presets -->
      <div
        style="display: flex; gap: 8px; margin-bottom: 16px; flex-wrap: wrap; justify-content: center;"
      >
        <button
          v-for="p in PAGE_PRESETS"
          :key="p.label"
          @click="prompt = p.prompt"
          :class="['design-preset', prompt === p.prompt ? 'design-preset--active' : '']"
        >{{ p.label }}</button>
      </div>
      <textarea
        v-model="prompt"
        placeholder="描述你想生成的页面…"
        rows="4"
        style="width: 100%; padding: 12px; border: 1px solid var(--color-border); border-radius: 8px; font-size: 14px; resize: vertical; margin-bottom: 16px; font-family: inherit; box-sizing: border-box; background: var(--color-surface); color: var(--color-text-primary);"
      ></textarea>
      <button
        @click="handleGenerate"
        :disabled="!prompt.trim()"
        :style="{
          width: '100%', padding: '12px',
          background: prompt.trim() ? '#7C3AED' : '#D1D5DB',
          color: '#fff', border: 'none', borderRadius: '6px',
          cursor: prompt.trim() ? 'pointer' : 'default',
          fontSize: '14px', fontWeight: '600',
        }"
      >AI 生成页面</button>
    </div>

    <!-- Loading -->
    <div
      v-if="loading"
      style="flex: 1; display: flex; align-items: center; justify-content: center; color: #7C3AED; font-size: 14px;"
    >
      <div style="text-align: center;">
        <div style="font-size: 32px; margin-bottom: 12px;">⟳</div>
        <div style="font-size: 12px; color: var(--color-text-tertiary);">AI 正在生成…</div>
      </div>
    </div>

    <!-- Active page canvas -->
    <div
      v-if="activePage && !loading"
      style="flex: 1; overflow: hidden;"
    >
      <DesignCanvas
        :initial-data="activePage.data"
        @save="(data) => updatePageData(activePage.id, data)"
      />
    </div>

    <!-- Error toast -->
    <div
      v-if="error"
      style="position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); padding: 8px 20px; background: color-mix(in srgb, var(--color-error) 8%, var(--color-surface)); color: var(--color-error); border-radius: 6px; font-size: 13px; box-shadow: 0 4px 12px rgba(0,0,0,0.1); z-index: 1000;"
    >{{ error }}</div>
  </div>
</template>

<style scoped>
.design-project-card {
  padding: 20px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 10px;
  cursor: pointer;
  transition: box-shadow 0.15s;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
}
.design-project-card:hover {
  box-shadow: 0 4px 12px rgba(124, 58, 237, 0.15);
}

.design-page-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
  white-space: nowrap;
  background: transparent;
  border: 1px solid transparent;
  color: var(--color-text-secondary);
  font-weight: 400;
}
.design-page-tab:hover {
  background: var(--color-surface);
}
.design-page-tab--active {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  color: #7C3AED;
  font-weight: 600;
}

.design-preset {
  padding: 6px 14px;
  border: none;
  border-radius: 20px;
  cursor: pointer;
  font-size: 13px;
  background: var(--color-surface-container);
  color: var(--color-text-secondary);
  font-weight: 400;
}
.design-preset:hover {
  background: var(--color-surface);
}
.design-preset--active {
  background: #7C3AED;
  color: #fff;
  font-weight: 600;
}
</style>
