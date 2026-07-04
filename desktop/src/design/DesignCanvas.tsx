// v2.8.0 — MadCop Design Canvas (native, zero-dependency)
// Inspired by Puck's Data format (MIT, github.com/puckeditor/puck)
// but reimplemented with native HTML5 drag & drop + inline styles.
// No external CSS, no dnd-kit, no global style pollution.

import { useState, useCallback, useRef } from 'react'

// ── Types (compatible with Puck Data format) ────────────────────────── //

export interface DesignData {
  root: { props: Record<string, any> }
  content: DesignItem[]
  zones?: Record<string, DesignItem[]>
}

export interface DesignItem {
  type: string
  props: Record<string, any>
}

export interface FieldConfig {
  type: 'text' | 'textarea' | 'number' | 'select' | 'radio' | 'color'
  label: string
  options?: { label: string; value: string }[]
}

export interface ComponentConfig {
  render: (props: Record<string, any>) => React.ReactNode
  fields: Record<string, FieldConfig>
  defaultProps: Record<string, any>
}

export interface DesignConfig {
  root?: {
    fields: Record<string, FieldConfig>
    defaultProps: Record<string, any>
  }
  components: Record<string, ComponentConfig>
}

// ── Component registry ──────────────────────────────────────────────── //

const componentRegistry: Record<string, ComponentConfig> = {
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
      level: { type: 'select', label: '级别', options: [
        { label: 'H1', value: '1' },
        { label: 'H2', value: '2' },
        { label: 'H3', value: '3' },
      ] },
      color: { type: 'color', label: '颜色' },
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
      color: { type: 'color', label: '颜色' },
      fontSize: { type: 'number', label: '字号' },
    },
    defaultProps: { text: '这是一段文字', fontSize: 14 },
  },
  Button: {
    render: ({ text, variant, width, color }) => (
      <button
        style={{
          padding: '10px 24px',
          borderRadius: 6,
          border: 'none',
          cursor: 'pointer',
          fontWeight: 600,
          fontSize: 14,
          width: width ? `${width}px` : 'auto',
          background: variant === 'primary' ? (color || '#7C3AED') : '#E2E8F0',
          color: variant === 'primary' ? '#fff' : '#1A1A1A',
        }}
      >
        {text || '按钮'}
      </button>
    ),
    fields: {
      text: { type: 'text', label: '文字' },
      variant: { type: 'radio', label: '样式', options: [
        { label: '主要', value: 'primary' },
        { label: '次要', value: 'secondary' },
      ] },
      color: { type: 'color', label: '主色' },
      width: { type: 'number', label: '宽度' },
    },
    defaultProps: { text: '提交', variant: 'primary', color: '#7C3AED' },
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
        readOnly
        style={{
          padding: '10px 14px',
          border: '1px solid #D1D5DB',
          borderRadius: 6,
          fontSize: 14,
          width: width ? `${width}px` : '100%',
          outline: 'none',
          background: '#F9FAFB',
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
    render: ({ padding, bgColor, borderWidth, borderColor, radius }) => (
      <div style={{
        padding: padding || 20,
        borderRadius: radius || 12,
        background: bgColor || '#F9FAFB',
        border: `${borderWidth || 1}px solid ${borderColor || '#E5E7EB'}`,
      }}>
        <span style={{ fontSize: 12, color: '#9CA3AF' }}>卡片容器</span>
      </div>
    ),
    fields: {
      padding: { type: 'number', label: '内边距' },
      bgColor: { type: 'color', label: '背景色' },
      radius: { type: 'number', label: '圆角' },
      borderWidth: { type: 'number', label: '边框粗细' },
      borderColor: { type: 'color', label: '边框色' },
    },
    defaultProps: { padding: 20, bgColor: '#F9FAFB', radius: 12, borderWidth: 1, borderColor: '#E5E7EB' },
  },
}

// ── Field renderer ──────────────────────────────────────────────────── //

function FieldEditor({
  field,
  value,
  onChange,
}: {
  field: FieldConfig
  value: any
  onChange: (v: any) => void
}) {
  const inputStyle: React.CSSProperties = {
    width: '100%',
    padding: '6px 10px',
    border: '1px solid #D1D5DB',
    borderRadius: 4,
    fontSize: 13,
    background: '#fff',
    boxSizing: 'border-box',
  }

  switch (field.type) {
    case 'textarea':
      return (
        <textarea
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value)}
          rows={3}
          style={{ ...inputStyle, resize: 'vertical', fontFamily: 'inherit' }}
        />
      )
    case 'number':
      return (
        <input
          type="number"
          value={value ?? 0}
          onChange={(e) => onChange(Number(e.target.value) || 0)}
          style={inputStyle}
        />
      )
    case 'select':
      return (
        <select
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value)}
          style={inputStyle}
        >
          {(field.options || []).map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      )
    case 'radio':
      return (
        <div style={{ display: 'flex', gap: 12 }}>
          {(field.options || []).map((opt) => (
            <label key={opt.value} style={{
              display: 'flex',
              alignItems: 'center',
              gap: 4,
              fontSize: 13,
              cursor: 'pointer',
            }}>
              <input
                type="radio"
                checked={value === opt.value}
                onChange={() => onChange(opt.value)}
              />
              {opt.label}
            </label>
          ))}
        </div>
      )
    case 'color':
      return (
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <input
            type="color"
            value={value || '#000000'}
            onChange={(e) => onChange(e.target.value)}
            style={{
              width: 32, height: 32,
              border: '1px solid #D1D5DB',
              borderRadius: 4,
              cursor: 'pointer',
              padding: 0,
            }}
          />
          <input
            type="text"
            value={value || ''}
            onChange={(e) => onChange(e.target.value)}
            style={{ ...inputStyle, width: 100 }}
          />
        </div>
      )
    default:
      return (
        <input
          type="text"
          value={value ?? ''}
          onChange={(e) => onChange(e.target.value)}
          style={inputStyle}
        />
      )
  }
}

// ── Main Canvas Component ───────────────────────────────────────────── //

interface DesignCanvasProps {
  initialData?: DesignData
  onSave?: (data: DesignData) => void
}

export function DesignCanvas({ initialData, onSave }: DesignCanvasProps) {
  const [data, setData] = useState<DesignData>(initialData || {
    root: { props: { bgColor: '#FFFFFF', padding: 40 } },
    content: [],
  })
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null)
  const [dragIdx, setDragIdx] = useState<number | null>(null)
  const [dragOverIdx, setDragOverIdx] = useState<number | null>(null)
  const canvasRef = useRef<HTMLDivElement>(null)

  // Sync external data
  const lastInitial = useRef<DesignData | null>(null)
  if (initialData && initialData !== lastInitial.current) {
    lastInitial.current = initialData
    setData(initialData)
    setSelectedIdx(null)
  }

  // ── Mutations ── //
  const updateItem = useCallback((idx: number, props: Record<string, any>) => {
    setData((prev) => {
      const content = [...prev.content]
      content[idx] = { ...content[idx], props: { ...content[idx].props, ...props } }
      return { ...prev, content }
    })
  }, [])

  const deleteItem = useCallback((idx: number) => {
    setData((prev) => ({
      ...prev,
      content: prev.content.filter((_, i) => i !== idx),
    }))
    setSelectedIdx(null)
  }, [])

  const addComponent = useCallback((type: string) => {
    const cfg = componentRegistry[type]
    if (!cfg) return
    const newItem: DesignItem = { type, props: { ...cfg.defaultProps } }
    setData((prev) => ({
      ...prev,
      content: [...prev.content, newItem],
    }))
    setSelectedIdx(data.content.length) // select the new item
  }, [data.content.length])

  const reorder = useCallback((from: number, to: number) => {
    if (from === to) return
    setData((prev) => {
      const content = [...prev.content]
      const [moved] = content.splice(from, 1)
      content.splice(to, 0, moved)
      return { ...prev, content }
    })
    setSelectedIdx(to)
  }, [])

  // ── Drag handlers ── //
  const onDragStart = (idx: number) => setDragIdx(idx)
  const onDragOver = (e: React.DragEvent, idx: number) => {
    e.preventDefault()
    setDragOverIdx(idx)
  }
  const onDrop = (e: React.DragEvent, idx: number) => {
    e.preventDefault()
    if (dragIdx !== null) reorder(dragIdx, idx)
    setDragIdx(null)
    setDragOverIdx(null)
  }

  const bgColor = data.root?.props?.bgColor || '#FFFFFF'
  const padding = data.root?.props?.padding || 40
  const selectedItem = selectedIdx !== null ? data.content[selectedIdx] : null
  const selectedCfg = selectedItem ? componentRegistry[selectedItem.type] : null

  return (
    <div style={{ display: 'flex', height: '100%', background: '#F3F4F6' }}>
      {/* ── Left: Component palette ── */}
      <div style={{
        width: 180,
        flexShrink: 0,
        borderRight: '1px solid #E5E7EB',
        background: '#fff',
        padding: '12px 8px',
        overflowY: 'auto',
      }}>
        <div style={{
          fontSize: 11, fontWeight: 700, color: '#9CA3AF',
          textTransform: 'uppercase', letterSpacing: 0.5,
          marginBottom: 10, padding: '0 4px',
        }}>
          组件
        </div>
        {Object.keys(componentRegistry).map((type) => (
          <button
            key={type}
            onClick={() => addComponent(type)}
            style={{
              display: 'block',
              width: '100%',
              textAlign: 'left',
              padding: '8px 12px',
              marginBottom: 4,
              background: '#F9FAFB',
              border: '1px solid #E5E7EB',
              borderRadius: 6,
              cursor: 'pointer',
              fontSize: 13,
              color: '#374151',
              transition: 'background 0.15s',
            }}
            onMouseEnter={(e) => e.currentTarget.style.background = '#EEF2FF'}
            onMouseLeave={(e) => e.currentTarget.style.background = '#F9FAFB'}
          >
            {type}
          </button>
        ))}
      </div>

      {/* ── Center: Canvas ── */}
      <div
        ref={canvasRef}
        style={{
          flex: 1,
          overflowY: 'auto',
          padding: 24,
          display: 'flex',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            width: '100%',
            maxWidth: 720,
            minHeight: '100%',
            background: bgColor,
            borderRadius: 8,
            padding,
            boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
          }}
          onClick={() => setSelectedIdx(null)}
        >
          {data.content.length === 0 && (
            <div style={{
              textAlign: 'center',
              padding: '60px 20px',
              color: '#9CA3AF',
              fontSize: 14,
            }}>
              从左侧添加组件，或用 AI 生成设计
            </div>
          )}
          {data.content.map((item, idx) => {
            const cfg = componentRegistry[item.type]
            if (!cfg) return null
            const isSelected = selectedIdx === idx
            const isDragOver = dragOverIdx === idx
            return (
              <div
                key={idx}
                draggable
                onDragStart={() => onDragStart(idx)}
                onDragOver={(e) => onDragOver(e, idx)}
                onDrop={(e) => onDrop(e, idx)}
                onClick={(e) => {
                  e.stopPropagation()
                  setSelectedIdx(idx)
                }}
                style={{
                  marginBottom: 8,
                  padding: 4,
                  borderRadius: 4,
                  cursor: 'pointer',
                  border: isSelected
                    ? '2px solid #7C3AED'
                    : isDragOver
                    ? '2px dashed #A78BFA'
                    : '2px solid transparent',
                  transition: 'border-color 0.15s',
                }}
              >
                {/* Drag handle */}
                <div style={{
                  display: isSelected ? 'flex' : 'none',
                  justifyContent: 'flex-end',
                  fontSize: 10,
                  color: '#9CA3AF',
                  marginBottom: 2,
                }}>
                  ⠿ 拖拽排序
                </div>
                {cfg.render(item.props)}
                {/* Delete button */}
                {isSelected && (
                  <div style={{ textAlign: 'right', marginTop: 4 }}>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        deleteItem(idx)
                      }}
                      style={{
                        padding: '2px 8px',
                        fontSize: 11,
                        background: '#FEE2E2',
                        color: '#DC2626',
                        border: 'none',
                        borderRadius: 3,
                        cursor: 'pointer',
                      }}
                    >
                      删除
                    </button>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* ── Right: Properties panel ── */}
      <div style={{
        width: 260,
        flexShrink: 0,
        borderLeft: '1px solid #E5E7EB',
        background: '#fff',
        padding: '12px 12px',
        overflowY: 'auto',
      }}>
        {selectedItem && selectedCfg ? (
          <>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 14,
            }}>
              <span style={{
                fontSize: 13, fontWeight: 700, color: '#1F2937',
              }}>
                {selectedItem.type} 属性
              </span>
              <span style={{
                fontSize: 11, color: '#9CA3AF',
              }}>
                #{(selectedIdx ?? 0) + 1}
              </span>
            </div>
            {Object.entries(selectedCfg.fields).map(([key, field]) => (
              <div key={key} style={{ marginBottom: 12 }}>
                <label style={{
                  display: 'block',
                  fontSize: 12,
                  color: '#6B7280',
                  marginBottom: 4,
                  fontWeight: 500,
                }}>
                  {field.label}
                </label>
                <FieldEditor
                  field={field}
                  value={selectedItem.props[key]}
                  onChange={(v) => {
                    if (selectedIdx !== null) {
                      updateItem(selectedIdx, { [key]: v })
                    }
                  }}
                />
              </div>
            ))}
          </>
        ) : (
          <>
            <div style={{
              fontSize: 11, fontWeight: 700, color: '#9CA3AF',
              textTransform: 'uppercase', letterSpacing: 0.5,
              marginBottom: 10,
            }}>
              画布设置
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{
                display: 'block', fontSize: 12, color: '#6B7280', marginBottom: 4,
              }}>
                背景色
              </label>
              <FieldEditor
                field={{ type: 'color', label: '背景色' }}
                value={data.root?.props?.bgColor}
                onChange={(v) => {
                  setData((prev) => ({
                    ...prev,
                    root: { props: { ...prev.root.props, bgColor: v } },
                  }))
                }}
              />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{
                display: 'block', fontSize: 12, color: '#6B7280', marginBottom: 4,
              }}>
                内边距
              </label>
              <FieldEditor
                field={{ type: 'number', label: '内边距' }}
                value={data.root?.props?.padding}
                onChange={(v) => {
                  setData((prev) => ({
                    ...prev,
                    root: { props: { ...prev.root.props, padding: v } },
                  }))
                }}
              />
            </div>
            <div style={{
              marginTop: 20, padding: 10,
              background: '#F3F4F6', borderRadius: 6,
              fontSize: 12, color: '#9CA3AF', lineHeight: 1.5,
            }}>
              点击组件编辑属性
            </div>
          </>
        )}
      </div>

      {/* ── Bottom toolbar ── */}
      <div style={{
        position: 'absolute',
        bottom: 0,
        right: 0,
        display: 'flex',
        gap: 8,
        padding: '8px 16px',
      }}>
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
            background: 'rgba(255,255,255,0.9)',
            border: '1px solid #E5E7EB',
            borderRadius: 4,
            cursor: 'pointer',
            fontSize: 12,
            color: '#374151',
            backdropFilter: 'blur(4px)',
          }}
        >
          导出 .madcop
        </button>
        <button
          onClick={() => onSave?.(data)}
          style={{
            padding: '6px 12px',
            background: 'rgba(124,58,237,0.9)',
            color: '#fff',
            border: 'none',
            borderRadius: 4,
            cursor: 'pointer',
            fontSize: 12,
            fontWeight: 600,
            backdropFilter: 'blur(4px)',
          }}
        >
          保存
        </button>
      </div>
    </div>
  )
}

export type { Config as DesignConfig }
