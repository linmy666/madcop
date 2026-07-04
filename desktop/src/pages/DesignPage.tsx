// v3.0 — Design tool page: multi-page project management + AI generation.
import { useState, useCallback, useEffect } from 'react'
import { getApiUrl } from '../api/client'
import { DesignCanvas, type DesignData } from '../design/DesignCanvas'

// ── Types ── //

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

// ── Presets ── //

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

// ── Project storage ── //

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

function emptyData(): DesignData {
  return { root: { props: { bgColor: '#FFFFFF', padding: 40 } }, content: [] }
}

// ── Main Component ── //

export function DesignPage() {
  const [projects, setProjects] = useState<DesignProject[]>(loadProjects)
  const [activeProject, setActiveProject] = useState<DesignProject | null>(null)
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showGenAll, setShowGenAll] = useState(false)

  useEffect(() => { saveProjects(projects) }, [projects])

  // ── Project actions ── //
  const createProject = useCallback((name: string) => {
    const project: DesignProject = {
      id: genId(), name, pages: [], activePageId: null, createdAt: Date.now(),
    }
    setProjects((prev) => [project, ...prev])
    setActiveProject(project)
  }, [])

  const deleteProject = useCallback((id: string) => {
    setProjects((prev) => prev.filter((p) => p.id !== id))
  }, [])

  // ── Page actions ── //
  const addPage = useCallback((name: string) => {
    if (!activeProject) return
    const page: DesignPageData = { id: genId(), name, data: emptyData() }
    const updated = { ...activeProject, pages: [...activeProject.pages, page], activePageId: page.id }
    setActiveProject(updated)
    setProjects((prev) => prev.map((p) => p.id === updated.id ? updated : p))
  }, [activeProject])

  const deletePage = useCallback((pageId: string) => {
    if (!activeProject) return
    const updated = {
      ...activeProject,
      pages: activeProject.pages.filter((p) => p.id !== pageId),
      activePageId: activeProject.activePageId === pageId ? null : activeProject.activePageId,
    }
    setActiveProject(updated)
    setProjects((prev) => prev.map((p) => p.id === updated.id ? updated : p))
  }, [activeProject])

  const updatePageData = useCallback((pageId: string, data: DesignData) => {
    if (!activeProject) return
    const updated = {
      ...activeProject,
      pages: activeProject.pages.map((p) => p.id === pageId ? { ...p, data } : p),
    }
    setActiveProject(updated)
    setProjects((prev) => prev.map((p) => p.id === updated.id ? updated : p))
  }, [activeProject])

  // ── AI Generation ── //
  const generatePage = useCallback(async (genPrompt: string): Promise<DesignData | null> => {
    setLoading(true)
    setError(null)
    try {
      const r = await fetch(getApiUrl('/api/design/generate'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: genPrompt }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const resp = await r.json()
      const text = resp.content || ''
      const jsonMatch = text.match(/\{[\s\S]*\}/)
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0])
        if (parsed.content && Array.isArray(parsed.content)) {
          return autoRepair(parsed)
        }
      }
      setError('AI 返回格式有误')
      return null
    } catch (e: any) {
      setError(`生成失败: ${e?.message || e}`)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  // Auto-repair LLM output
  function autoRepair(data: any): DesignData {
    // Ensure root exists
    if (!data.root) data.root = { props: { bgColor: '#FFFFFF', padding: 40 } }
    if (!data.root.props) data.root.props = {}
    if (!data.root.props.bgColor) data.root.props.bgColor = '#FFFFFF'
    if (!data.root.props.padding) data.root.props.padding = 40
    // Ensure content is array
    if (!Array.isArray(data.content)) data.content = []
    // Repair each item
    function repairItem(item: any): any {
      if (!item.type) return null
      const cfg = componentNames[item.type]
      if (!cfg) return null
      if (!item.props) item.props = {}
      // Fill defaults
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
    return data
  }

  // ── AI generate single page ── //
  const handleGenerate = async () => {
    if (!prompt.trim() || !activeProject) return
    const data = await generatePage(prompt)
    if (data) {
      const pageName = prompt.slice(0, 12) + '...'
      const page: DesignPageData = { id: genId(), name: pageName, data }
      const updated = { ...activeProject, pages: [...activeProject.pages, page], activePageId: page.id }
      setActiveProject(updated)
      setProjects((prev) => prev.map((p) => p.id === updated.id ? updated : p))
      setPrompt('')
    }
  }

  // ── AI generate entire app ── //
  const handleGenerateApp = async (preset: typeof FULL_APP_PROMPTS[0]) => {
    if (!activeProject) return
    setShowGenAll(false)
    setLoading(true)
    const newPages: DesignPageData[] = []
    for (const pageName of preset.pages) {
      const data = await generatePage(`${preset.name}的${pageName}，风格统一`)
      if (data) {
        newPages.push({ id: genId(), name: pageName, data })
      }
    }
    if (newPages.length > 0) {
      const updated = { ...activeProject, pages: [...activeProject.pages, ...newPages], activePageId: newPages[0].id }
      setActiveProject(updated)
      setProjects((prev) => prev.map((p) => p.id === updated.id ? updated : p))
    }
    setLoading(false)
  }

  // ── Render ── //

  // No active project → show project list
  if (!activeProject) {
    return (
      <div style={{ maxWidth: 720, margin: '0 auto', padding: '40px 20px' }}>
        <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6, textAlign: 'center' }}>设计工具</h1>
        <p style={{ fontSize: 14, color: '#6B7280', marginBottom: 32, textAlign: 'center' }}>创建项目，用 AI 批量生成原型设计</p>

        {/* Create new project */}
        <div style={{ display: 'flex', gap: 8, marginBottom: 32 }}>
          <input
            type="text"
            placeholder="输入项目名称..."
            onKeyDown={(e) => { if (e.key === 'Enter') { const v = (e.target as HTMLInputElement).value.trim(); if (v) { createProject(v); (e.target as HTMLInputElement).value = '' } } }}
            style={{ flex: 1, padding: '10px 14px', border: '1px solid #D1D5DB', borderRadius: 6, fontSize: 14, outline: 'none' }}
          />
          <button
            onClick={() => { const input = document.querySelector('input[placeholder="输入项目名称..."]') as HTMLInputElement; const v = input?.value?.trim(); if (v) { createProject(v); if (input) input.value = '' } }}
            style={{ padding: '10px 20px', background: '#7C3AED', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 14, fontWeight: 600 }}
          >新建项目</button>
        </div>

        {/* Existing projects */}
        {projects.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '60px 20px', color: '#9CA3AF', fontSize: 14 }}>
            还没有项目，创建一个开始吧
          </div>
        ) : (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 16 }}>
            {projects.map((proj) => (
              <div key={proj.id}
                onClick={() => setActiveProject(proj)}
                style={{ padding: 20, background: '#fff', border: '1px solid #E5E7EB', borderRadius: 10, cursor: 'pointer', transition: 'box-shadow 0.15s', boxShadow: '0 1px 3px rgba(0,0,0,0.05)' }}
                onMouseEnter={(e) => e.currentTarget.style.boxShadow = '0 4px 12px rgba(124,58,237,0.15)'}
                onMouseLeave={(e) => e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.05)'}>
                <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>{proj.name}</div>
                <div style={{ fontSize: 12, color: '#9CA3AF' }}>{proj.pages.length} 个页面</div>
                <div style={{ fontSize: 11, color: '#D1D5DB', marginTop: 8 }}>{new Date(proj.createdAt).toLocaleDateString('zh-CN')}</div>
                <button
                  onClick={(e) => { e.stopPropagation(); if (confirm(`删除项目 "${proj.name}"？`)) deleteProject(proj.id) }}
                  style={{ marginTop: 12, padding: '4px 10px', fontSize: 11, border: '1px solid #FECACA', borderRadius: 3, background: '#fff', color: '#DC2626', cursor: 'pointer' }}>
                  删除
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // Active project → show canvas
  const activePage = activeProject.pages.find((p) => p.id === activeProject.activePageId) || null

  return (
    <div style={{ width: '100%', height: '100vh', display: 'flex', flexDirection: 'column' }}>
      {/* ── Top bar ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '8px 16px', borderBottom: '1px solid #E5E7EB', background: '#fff', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button onClick={() => setActiveProject(null)} style={{ padding: '4px 12px', border: '1px solid #E5E8F0', borderRadius: 4, cursor: 'pointer', fontSize: 12, color: '#374151', background: '#fff' }}>← 项目列表</button>
          <span style={{ fontSize: 14, fontWeight: 600 }}>{activeProject.name}</span>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => setShowGenAll(!showGenAll)} style={{ padding: '4px 12px', border: '1px solid #7C3AED', borderRadius: 4, cursor: 'pointer', fontSize: 12, color: '#7C3AED', background: '#fff' }}>批量生成</button>
        </div>
      </div>

      {/* ── Batch generation dropdown ── */}
      {showGenAll && (
        <div style={{ padding: 12, background: '#F9FAFB', borderBottom: '1px solid #E5E7EB', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 12, color: '#6B7280', lineHeight: '28px' }}>一键生成:</span>
          {FULL_APP_PROMPTS.map((preset) => (
            <button key={preset.name} onClick={() => handleGenerateApp(preset)} style={{ padding: '4px 14px', border: '1px solid #D1D5DB', borderRadius: 20, cursor: 'pointer', fontSize: 12, background: '#fff', color: '#374151' }}>
              {preset.name} ({preset.pages.length}页)
            </button>
          ))}
        </div>
      )}

      {/* ── Page tabs ── */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 2, padding: '6px 16px', borderBottom: '1px solid #E5E7EB', background: '#FAFAFA', overflowX: 'auto', flexShrink: 0 }}>
        {activeProject.pages.map((page) => (
          <div key={page.id}
            onClick={() => { const updated = { ...activeProject, activePageId: page.id }; setActiveProject(updated); setProjects((prev) => prev.map((p) => p.id === updated.id ? updated : p)) }}
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '5px 12px', borderRadius: 4, cursor: 'pointer', fontSize: 12, whiteSpace: 'nowrap',
              background: activeProject.activePageId === page.id ? '#fff' : 'transparent',
              border: activeProject.activePageId === page.id ? '1px solid #E5E7EB' : '1px solid transparent',
              color: activeProject.activePageId === page.id ? '#7C3AED' : '#6B7280', fontWeight: activeProject.activePageId === page.id ? 600 : 400,
            }}>
            <span>{page.name}</span>
            <button onClick={(e) => { e.stopPropagation(); deletePage(page.id) }} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, color: '#D1D5DB', padding: 0, lineHeight: 1 }}>×</button>
          </div>
        ))}
        <button onClick={() => addPage(`页面 ${activeProject.pages.length + 1}`)} style={{ padding: '5px 10px', border: '1px dashed #D1D5DB', borderRadius: 4, cursor: 'pointer', fontSize: 12, color: '#9CA3AF', background: 'transparent' }}>+ 新页面</button>
      </div>

      {/* ── AI prompt bar (shown when no page active or user wants to generate) ── */}
      {!activePage && !loading && (
        <div style={{ padding: '40px 20px', maxWidth: 640, margin: '0 auto', width: '100%' }}>
          {/* Presets */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', justifyContent: 'center' }}>
            {PAGE_PRESETS.map((p) => (
              <button key={p.label} onClick={() => setPrompt(p.prompt)} style={{ padding: '6px 14px', background: prompt === p.prompt ? '#7C3AED' : '#F3F4F6', color: prompt === p.prompt ? '#fff' : '#374151', border: 'none', borderRadius: 20, cursor: 'pointer', fontSize: 13, fontWeight: prompt === p.prompt ? 600 : 400 }}>{p.label}</button>
            ))}
          </div>
          <textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="描述你想生成的页面..." rows={4} style={{ width: '100%', padding: 12, border: '1px solid #E2E8F0', borderRadius: 8, fontSize: 14, resize: 'vertical', marginBottom: 16, fontFamily: 'inherit', boxSizing: 'border-box' }} />
          <button onClick={handleGenerate} disabled={!prompt.trim()} style={{ width: '100%', padding: '12px', background: prompt.trim() ? '#7C3AED' : '#D1D5DB', color: '#fff', border: 'none', borderRadius: 6, cursor: prompt.trim() ? 'pointer' : 'default', fontSize: 14, fontWeight: 600 }}>
            AI 生成页面
          </button>
        </div>
      )}

      {/* ── Loading ── */}
      {loading && (
        <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#7C3AED', fontSize: 14 }}>
          <div style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 32, marginBottom: 12 }}>AI 正在生成...</div>
            <div style={{ fontSize: 12, color: '#9CA3AF' }}>GLM-5.2 正在思考</div>
          </div>
        </div>
      )}

      {/* ── Active page canvas ── */}
      {activePage && !loading && (
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <DesignCanvas
            initialData={activePage.data}
            onSave={(data) => updatePageData(activePage.id, data)}
          />
        </div>
      )}

      {/* ── Error toast ── */}
      {error && (
        <div style={{ position: 'absolute', bottom: 20, left: '50%', transform: 'translateX(-50%)', padding: '8px 20px', background: '#FEF2F2', color: '#DC2626', borderRadius: 6, fontSize: 13, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
          {error}
        </div>
      )}
    </div>
  )
}

// ── Component names for auto-repair ── //
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
