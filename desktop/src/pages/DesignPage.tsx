// v2.8.0 — Design tool page: wrapper around DesignCanvas with LLM prompt integration.
import { useState } from 'react'
import { getApiUrl } from '../api/client'
import { DesignCanvas } from '../design/DesignCanvas'

export function DesignPage() {
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [showCanvas, setShowCanvas] = useState(false)
  const [designData, setDesignData] = useState<any>(null)

  const handleGenerate = async () => {
    if (!prompt.trim()) return
    setLoading(true)
    try {
      const r = await fetch(getApiUrl('/api/chat'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          messages: [
            {
              role: 'user',
              content: `生成一个 UI 设计 JSON，格式为 Puck 的 Data 结构，包含 root 和 content 数组。\n\n需求：${prompt}\n\n只返回 JSON，不要其他文字。JSON 格式：{"root":{"props":{"bgColor":"#FAFAFA","padding":40}},"content":[{"type":"Header","props":{"text":"标题","level":"2"}},{"type":"Paragraph","props":{"text":"描述文字"}}]}`,
            },
          ],
          model: 'glm-5.2',
          stream: false,
        }),
      })
      const data = await r.json()
      const text = data.choices?.[0]?.message?.content || ''
      // Try to extract JSON from the response
      const jsonMatch = text.match(/\{[\s\S]*\}/)
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0])
        setDesignData(parsed)
        setShowCanvas(true)
      }
    } catch (e) {
      console.error('Design generation failed:', e)
    } finally {
      setLoading(false)
    }
  }

  if (showCanvas) {
    return (
      <div style={{ width: '100%', height: '100vh' }}>
        <DesignCanvas
          initialData={designData}
          onSave={(data) => {
            setDesignData(data)
          }}
        />
      </div>
    )
  }

  return (
    <div
      style={{
        maxWidth: 640,
        margin: '0 auto',
        padding: '60px 20px',
        textAlign: 'center',
      }}
    >
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 8 }}>设计工具</h1>
      <p style={{ fontSize: 14, color: '#6B7280', marginBottom: 24 }}>
        描述你想设计的界面，AI 自动生成可拖拽编辑的原型
      </p>
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
        }}
      />
      <button
        onClick={handleGenerate}
        disabled={loading || !prompt.trim()}
        style={{
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
        {loading ? '生成中...' : '生成设计'}
      </button>
      <div
        style={{
          marginTop: 40,
          padding: 20,
          background: '#F9FAFB',
          borderRadius: 8,
          textAlign: 'left',
          fontSize: 13,
          color: '#6B7280',
          lineHeight: 1.6,
        }}
      >
        <strong>提示：</strong>
        <br />
        尽量描述清楚你的需求，包括：
        <br />
        • 页面类型（登录页、仪表盘、个人中心等）
        <br />
        • 需要哪些组件（按钮、输入框、卡片、表格等）
        <br />
        • 颜色风格（简洁、科技感、卡通等）
        <br />
        • 布局要求（两栏、居中、顶部导航等）
      </div>
    </div>
  )
}