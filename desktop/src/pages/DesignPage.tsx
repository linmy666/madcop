// v2.8.0 — Design tool page: wrapper around DesignCanvas with LLM prompt integration.
import { useState, useCallback } from 'react'
import { getApiUrl } from '../api/client'
import { DesignCanvas, type DesignData } from '../design/DesignCanvas'

// Preset examples the user can click to test
const PRESETS = [
  { label: '登录页面', prompt: '一个简洁的登录页面，包含邮箱输入框、密码输入框、一个主要登录按钮，白色背景，居中布局' },
  { label: '仪表盘', prompt: '一个数据仪表盘卡片布局，包含4张卡片：今日订单、收入、活跃用户、转化率，每张卡片有数字和标题' },
  { label: '个人中心', prompt: '用户个人中心页，顶部是头像和昵称，下面是设置项列表：个人信息、通知设置、隐私、关于' },
]

// System prompt that teaches the LLM exactly how to format Puck Data
const DESIGN_SYSTEM_PROMPT = `你是 MadCop 设计工具的前端组件生成器。
你根据用户的需求生成符合 Puck 编辑器格式的 JSON 数据。

Puck Data 的 JSON 格式：
{
  "root": {
    "props": {
      "bgColor": "字符串，十六进制色值，如 #FAFAFA",
      "padding": "数字，单位px，如 40"
    }
  },
  "content": [
    {
      "type": "组件名",
      "props": { "组件属性" }
    }
  ]
}

可用的组件列表（每个组件都有可编辑的属性）：
1. Header — 标题组件
   props: text（文字，字符串）, level（级别，"1"|"2"|"3"）, color（颜色，字符串）, fontSize（字号，数字）
2. Paragraph — 段落文字
   props: text（文字，字符串）, color（颜色，字符串）, fontSize（字号，数字）
3. Button — 按钮
   props: text（文字，字符串）, variant（样式，"primary"|"secondary"）, width（宽度，数字）
4. Image — 图片
   props: src（图片地址，字符串）, alt（替代文字，字符串）, width（宽度，数字）, height（高度，数字）
5. Input — 输入框
   props: placeholder（占位文字，字符串）, width（宽度，数字）
6. Card — 卡片容器
   props: padding（内边距，数字）, bgColor（背景色，字符串）
   注意：Card 的 content 放在 "slots" 字段中

【重要规则】
1. 必须按用户的 UI 需求合理组合这些组件
2. 内容要真实，不要用"标题"、"段落"这类占位词
3. 颜色搭配要合理美观
4. 只返回 JSON，不要任何解释文字
5. 如果一个 UI 需要多个分组，可以用相同组件多次
6. Login 页面推荐组件顺序：Header(大标题) → Paragraph(副标题) → Input(邮箱) → Input(密码) → Button(登录按钮)
7. 仪表盘推荐：Header(标题) → Card(每项指标一个Card，内部用Header+Paragraph展示数字)`

// Fallback data when LLM fails
const FALLBACK_LOGIN_DATA: DesignData = {
  root: { props: { bgColor: '#FFFFFF', padding: 40 } },
  content: [
    { type: 'Header', props: { text: '欢迎回来', level: '2', fontSize: 28 } },
    { type: 'Paragraph', props: { text: '请登录你的账号继续', fontSize: 14, color: '#6B7280' } },
    { type: 'Input', props: { placeholder: '邮箱地址', width: 320 } },
    { type: 'Input', props: { placeholder: '密码', width: 320 } },
    { type: 'Button', props: { text: '登录', variant: 'primary', width: 320 } },
  ],
}

export function DesignPage() {
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showCanvas, setShowCanvas] = useState(false)
  const [designData, setDesignData] = useState<DesignData | null>(null)
  const [lastPrompt, setLastPrompt] = useState('')

  const handleGenerate = async () => {
    if (!prompt.trim()) return
    setLoading(true)
    setError(null)
    setLastPrompt(prompt)

    try {
      const r = await fetch(getApiUrl('/api/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [
            { role: 'system', content: DESIGN_SYSTEM_PROMPT },
            { role: 'user', content: `根据以下需求生成 UI 设计 JSON（只返回 JSON，不要解释）：\n\n${prompt}` },
          ],
          model: 'glm-5.2',
          stream: false,
          max_tokens: 4096,
        }),
      })
      const data = await r.json()
      const text = data.choices?.[0]?.message?.content || ''

      // Try to extract JSON from the response
      const jsonMatch = text.match(/\{[\s\S]*\}/)
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0])
        // Validate has required fields
        if (parsed.content && Array.isArray(parsed.content)) {
          setDesignData(parsed)
          setShowCanvas(true)
          return
        }
      }
      // If we get here, parsing failed — use fallback
      console.warn('LLM did not return valid design data, using fallback', text.slice(0, 200))
      setDesignData(FALLBACK_LOGIN_DATA)
      setShowCanvas(true)
    } catch (e) {
      console.error('Design generation failed:', e)
      setError('生成失败，已使用默认模板')
      setDesignData(FALLBACK_LOGIN_DATA)
      setShowCanvas(true)
    } finally {
      setLoading(false)
    }
  }

  const handleBack = useCallback(() => {
    setShowCanvas(false)
    setDesignData(null)
  }, [])

  const handleSave = useCallback((data: DesignData) => {
    setDesignData(data)
  }, [])

  const handleRegenerate = useCallback(() => {
    setShowCanvas(false)
    setDesignData(null)
  }, [])

  if (showCanvas && designData) {
    return (
      <div style={{ width: '100%', height: '100vh', display: 'flex', flexDirection: 'column' }}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            padding: '8px 16px',
            borderBottom: '1px solid #E2E8F0',
            background: '#fff',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <button
              onClick={handleBack}
              style={{
                padding: '4px 12px',
                background: 'transparent',
                border: '1px solid #E2E8F0',
                borderRadius: 4,
                cursor: 'pointer',
                fontSize: 12,
                color: '#374151',
              }}
            >
              ← 返回
            </button>
            <span style={{ fontSize: 13, color: '#9CA3AF' }}>
              需求: {lastPrompt.slice(0, 40)}...
            </span>
          </div>
          <button
            onClick={handleRegenerate}
            style={{
              padding: '4px 12px',
              background: 'transparent',
              border: '1px solid #7C3AED',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 12,
              color: '#7C3AED',
            }}
          >
            重新生成
          </button>
        </div>
        {error && (
          <div style={{
            padding: '6px 16px',
            background: '#FEF3C7',
            color: '#92400E',
            fontSize: 12,
            textAlign: 'center',
          }}>
            {error}
          </div>
        )}
        <div style={{ flex: 1, overflow: 'hidden' }}>
          <DesignCanvas
            initialData={designData}
            onSave={handleSave}
          />
        </div>
      </div>
    )
  }

  return (
    <div
      style={{
        maxWidth: 640,
        margin: '0 auto',
        padding: '60px 20px',
      }}
    >
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8, textAlign: 'center' }}>设计工具</h1>
      <p style={{ fontSize: 14, color: '#6B7280', marginBottom: 24, textAlign: 'center' }}>
        描述你想设计的界面，AI 自动生成可拖拽编辑的原型
      </p>

      {/* Preset buttons */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', justifyContent: 'center' }}>
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => setPrompt(p.prompt)}
            style={{
              padding: '6px 14px',
              background: prompt === p.prompt ? '#7C3AED' : '#F3F4F6',
              color: prompt === p.prompt ? '#fff' : '#374151',
              border: 'none',
              borderRadius: 20,
              cursor: 'pointer',
              fontSize: 13,
              fontWeight: prompt === p.prompt ? 600 : 400,
            }}
          >
            {p.label}
          </button>
        ))}
      </div>

      <textarea
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        placeholder="例如：帮我设计一个登录页面，包含邮箱输入框、密码输入框和登录按钮，背景要渐变色"
        rows={5}
        style={{
          width: '100%',
          padding: 12,
          border: '1px solid #E2E8F0',
          borderRadius: 8,
          fontSize: 14,
          resize: 'vertical',
          marginBottom: 16,
          fontFamily: 'inherit',
          boxSizing: 'border-box',
        }}
      />
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          onClick={handleGenerate}
          disabled={loading || !prompt.trim()}
          style={{
            flex: 1,
            padding: '10px 24px',
            background: loading ? '#9CA3AF' : '#7C3AED',
            color: '#fff',
            border: 'none',
            borderRadius: 6,
            cursor: loading ? 'default' : 'pointer',
            fontSize: 14,
            fontWeight: 600,
          }}
        >
          {loading ? 'AI 生成中...' : '生成设计'}
        </button>
        <button
          onClick={() => {
            setDesignData(FALLBACK_LOGIN_DATA)
            setShowCanvas(true)
            setLastPrompt('默认登录模板')
          }}
          style={{
            padding: '10px 16px',
            background: '#F3F4F6',
            color: '#374151',
            border: '1px solid #E2E8F0',
            borderRadius: 6,
            cursor: 'pointer',
            fontSize: 13,
          }}
        >
          使用模板
        </button>
      </div>

      <div
        style={{
          marginTop: 40,
          padding: 20,
          background: '#F9FAFB',
          borderRadius: 8,
          fontSize: 13,
          color: '#6B7280',
          lineHeight: 1.6,
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: 8, color: '#374151' }}>使用提示</div>
        • 描述要包含：页面类型 + 需要的组件 + 颜色风格 + 布局要求
        <br />
        • 如果 AI 生成不满意，点「重新生成」试试
        <br />
        • 进入画布后可以拖拽组件、编辑属性
        <br />
        • 支持导出 .madcop 文件（工具栏按钮）
      </div>
    </div>
  )
}