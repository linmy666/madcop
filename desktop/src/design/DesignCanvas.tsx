// v2.8.0 — MadCop Design Canvas
// Wraps Puck (MIT license) as MadCop's built-in design tool.
// License: MIT — see LICENSE file in this directory.
//
// Original: github.com/puckeditor/puck (MIT)

import { useState, useCallback, useEffect } from 'react'
import {
  Puck,
  type Config,
  type Data,
} from '@measured/puck'
import '@measured/puck/dist/index.css'

interface DesignCanvasProps {
  initialData?: Data
  onSave?: (data: Data) => void
  height?: string | number
}

// Default components available in the canvas
const defaultComponents: Config['components'] = {
  Header: {
    render: ({ text, level, color, fontSize }) => {
      const lvl = level || 2
      const Tag = `h${lvl}` as any
      return (
        <Tag style={{
          margin: '0 0 8px 0',
          color: color || '#1A1A1A',
          fontSize: fontSize || 24,
          fontWeight: 700,
        }}>
          {text || '标题'}
        </Tag>
      )
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
    render: ({ text, color, fontSize }) => (
      <p style={{
        margin: '0 0 12px 0',
        fontSize: fontSize || 14,
        lineHeight: 1.6,
        color: color || '#4B5563',
      }}>
        {text || '段落文字'}
      </p>
    ),
    fields: {
      text: { type: 'textarea', label: '文字' },
      color: { type: 'text', label: '颜色' },
      fontSize: { type: 'number', label: '字号' },
    },
    defaultProps: { text: '这是一段文字', fontSize: 14 },
  },
  Button: {
    render: ({ text, variant, width }) => (
      <button
        style={{
          padding: '10px 24px',
          borderRadius: 6,
          border: 'none',
          cursor: 'pointer',
          fontWeight: 600,
          fontSize: 14,
          width: width ? `${width}px` : 'auto',
          background: variant === 'primary' ? '#7C3AED' : '#E2E8F0',
          color: variant === 'primary' ? '#fff' : '#1A1A1A',
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
    render: ({ src, alt, width, height }) => (
      <img
        src={src || 'https://via.placeholder.com/400x200'}
        alt={alt || ''}
        style={{
          maxWidth: '100%',
          borderRadius: 8,
          width: width ? `${width}px` : 'auto',
          height: height ? `${height}px` : 'auto',
        }}
      />
    ),
    fields: {
      src: { type: 'text', label: '图片地址' },
      alt: { type: 'text', label: '替代文字' },
      width: { type: 'number', label: '宽度' },
      height: { type: 'number', label: '高度' },
    },
    defaultProps: { src: '', alt: '' },
  },
  Input: {
    render: ({ placeholder, width }) => (
      <input
        placeholder={placeholder || '输入...'}
        style={{
          padding: '10px 14px',
          border: '1px solid #D1D5DB',
          borderRadius: 6,
          fontSize: 14,
          width: width ? `${width}px` : '100%',
          outline: 'none',
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
    render: ({ children, padding, bgColor }) => (
      <div
        style={{
          padding: padding || 20,
          borderRadius: 12,
          background: bgColor || '#fff',
          boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
        }}
      >
        {children as any}
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
      bgColor: '#FFFFFF',
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
    root: { props: { bgColor: '#FFFFFF', padding: 40 } },
    content: [],
  })

  // Update data when initialData changes (e.g. after LLM generates new design)
  useEffect(() => {
    if (initialData) {
      setData(initialData)
    }
  }, [initialData])

  const handlePublish = useCallback((newData: Data) => {
    setData(newData)
    onSave?.(newData)
  }, [onSave])

  return (
    <div style={{ height, display: 'flex', flexDirection: 'column' }}>
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <Puck
          config={config}
          data={data}
          onPublish={handlePublish}
          overrides={{
            header: ({ children }) => (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '8px 16px',
                  borderBottom: '1px solid #E2E8F0',
                  background: '#fff',
                  zIndex: 100,
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
                    onClick={() => handlePublish(data)}
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
                {children}
              </div>
            ),
          }}
        />
      </div>
    </div>
  )
}

export type { Config, Data as DesignData }
