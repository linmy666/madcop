// v2.8.0 — MadCop Design Canvas
// Wraps Puck (MIT license) as MadCop's built-in design tool.
// License: MIT — see LICENSE file in this directory.
//
// The DesignCanvas lets users:
// 1. Describe a UI with natural language
// 2. LLM generates a component tree
// 3. Render in a drag-and-drop canvas
// 4. Edit properties directly
// 5. Export as .madcop / HTML / Markdown
//
// Original: github.com/puckeditor/puck (MIT)

import { useState, useCallback } from 'react'
import {
  Puck,
  type Config,
  type Data,
} from './core/bundle/core'
import { DesignComponent } from './types'

interface DesignCanvasProps {
  /** Initial component tree data */
  initialData?: Data
  /** Called when the user saves/exports */
  onSave?: (data: Data) => void
  /** Height of the canvas */
  height?: string | number
}

// Default components available in the canvas
const defaultComponents = {
  Header: {
    render: ({ text, level, ...props }) => {
      const Tag = `h${level || 2}` as keyof JSX.IntrinsicElements
      return <Tag style={{ ...props }}>{text || '标题'}</Tag>
    },
    fields: {
      text: { type: 'text', label: '文字' },
      level: {
        type: 'select', label: '级别',
        options: [
          { label: 'H1', value: '1' },
          { label: 'H2', value: '2' },
          { label: 'H3', value: '3' },
        ],
      },
      color: { type: 'text', label: '颜色' },
      fontSize: { type: 'number', label: '字号' },
    },
    defaultProps: { text: '新标题', level: '2', fontSize: 24 },
  },
  Paragraph: {
    render: ({ text, ...props }) => (
      <p style={{ fontSize: 14, lineHeight: 1.6, ...props }}>{text || '段落文字'}</p>
    ),
    fields: {
      text: { type: 'textarea', label: '文字' },
      color: { type: 'text', label: '颜色' },
      fontSize: { type: 'number', label: '字号' },
    },
    defaultProps: { text: '这是一段文字', fontSize: 14 },
  },
  Button: {
    render: ({ text, variant, ...props }) => (
      <button
        style={{
          padding: '8px 20px',
          borderRadius: 6,
          border: 'none',
          cursor: 'pointer',
          fontWeight: 600,
          background: variant === 'primary' ? '#7C3AED' : '#E2E8F0',
          color: variant === 'primary' ? '#fff' : '#1A1A1A',
          ...props,
        }}
      >
        {text || '按钮'}
      </button>
    ),
    fields: {
      text: { type: 'text', label: '文字' },
      variant: {
        type: 'radio', label: '样式',
        options: [
          { label: '主要', value: 'primary' },
          { label: '次要', value: 'secondary' },
        ],
      },
      width: { type: 'number', label: '宽度' },
    },
    defaultProps: { text: '提交', variant: 'primary' },
  },
  Image: {
    render: ({ src, alt, ...props }) => (
      <img
        src={src || 'https://via.placeholder.com/400x200'}
        alt={alt || ''}
        style={{ maxWidth: '100%', borderRadius: 8, ...props }}
      />
    ),
    fields: {
      src: { type: 'text', label: '图片地址' },
      alt: { type: 'text', label: '替代文字' },
      width: { type: 'number', label: '宽度' },
      height: { type: 'number', label: '高度' },
    },
    defaultProps: { src: 'https://via.placeholder.com/400x200', alt: '' },
  },
  Input: {
    render: ({ placeholder, ...props }) => (
      <input
        placeholder={placeholder || '输入...'}
        style={{
          padding: '8px 12px',
          border: '1px solid #E2E8F0',
          borderRadius: 6,
          fontSize: 14,
          width: '100%',
          ...props,
        }}
      />
    ),
    fields: {
      placeholder: { type: 'text', label: '占位文字' },
      width: { type: 'number', label: '宽度' },
    },
    defaultProps: { placeholder: '请输入...', width: 300 },
  },
  Card: {
    render: ({ children, ...props }) => (
      <div
        style={{
          padding: 20,
          borderRadius: 12,
          background: '#fff',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
          ...props,
        }}
      >
        {children}
      </div>
    ),
    fields: {
      padding: { type: 'number', label: '内边距' },
      bgColor: { type: 'text', label: '背景色' },
    },
    defaultProps: { padding: 20 },
  },
}

const config: Config = {
  root: {
    fields: {
      bgColor: { type: 'text', label: '背景色' },
      padding: { type: 'number', label: '内边距' },
    },
    defaultProps: {
      bgColor: '#FAFAFA',
      padding: 40,
    },
  },
  components: defaultComponents,
}

export function DesignCanvas({
  initialData,
  onSave,
  height = '100%',
}: DesignCanvasProps) {
  const [data, setData] = useState<Data>(initialData || {
    root: { props: { bgColor: '#FAFAFA', padding: 40 } },
    content: [],
    zones: {},
  })

  const handleSave = useCallback((newData: Data) => {
    setData(newData)
    onSave?.(newData)
  }, [onSave])

  return (
    <div style={{ height, display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <Puck
          config={config}
          data={data}
          onPublish={handleSave}
          overrides={{
            header: ({ publish }) => (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 16px',
                  borderBottom: '1px solid #E2E8F0',
                  background: '#fff',
                }}
              >
                <span style={{ fontWeight: 600, fontSize: 14 }}>
                  MadCop 设计工具
                </span>
                <div style={{ display: 'flex', gap: 8 }}>
                  <button
                    onClick={() => {
                      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
                      const a = document.createElement('a')
                      a.href = URL.createObjectURL(blob)
                      a.download = `design-${Date.now()}.madcop`
                      a.click()
                    }}
                    style={{
                      padding: '6px 12px',
                      background: 'transparent',
                      border: '1px solid #E2E8F0',
                      borderRadius: 4,
                      cursor: 'pointer',
                      fontSize: 12,
                    }}
                  >
                    导出 .madcop
                  </button>
                  <button
                    onClick={() => publish()}
                    style={{
                      padding: '6px 12px',
                      background: '#7C3AED',
                      color: '#fff',
                      border: 'none',
                      borderRadius: 4,
                      cursor: 'pointer',
                      fontSize: 12,
                      fontWeight: 600,
                    }}
                  >
                    保存
                  </button>
                </div>
              </div>
            ),
          }}
        />
      </div>
    </div>
  )
}

export type { Config, Data as DesignData }
export { defaultComponents }