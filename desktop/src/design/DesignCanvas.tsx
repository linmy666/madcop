// v3.0 — MadCop Design Canvas (native, zero-dependency, full-featured)
// Inspired by Puck/GrapesJS architecture, reimplemented with native HTML5.
// No external CSS, no dnd-kit, no global style pollution.

import {
  useState, useCallback, useEffect, useRef, useMemo,
} from 'react'
import React from 'react'

// ── Types ───────────────────────────────────────────────────────────── //

export interface DesignItem {
  type: string
  props: Record<string, any>
  children?: DesignItem[]
}

export interface DesignData {
  root: { props: Record<string, any> }
  content: DesignItem[]
}

export interface FieldConfig {
  type: 'text' | 'textarea' | 'number' | 'select' | 'radio' | 'color'
  label: string
  options?: { label: string; value: string }[]
}

export interface ComponentConfig {
  render: (props: Record<string, any>, children?: React.ReactNode) => React.ReactNode
  fields: Record<string, FieldConfig>
  defaultProps: Record<string, any>
  isContainer?: boolean
  label: string
}

// ── Component Registry ──────────────────────────────────────────────── //

const shadowMap: Record<string, string> = {
  sm: '0 1px 2px rgba(0,0,0,0.05)',
  md: '0 4px 6px rgba(0,0,0,0.1)',
  lg: '0 10px 15px rgba(0,0,0,0.15)',
}

const componentRegistry: Record<string, ComponentConfig> = {
  Header: {
    label: '标题',
    render: ({ text, level, color, fontSize }) => {
      const Tag = (`h${level || 2}`) as any
      return <Tag style={{ margin: '0 0 8px 0', color: color || '#1A1A1A', fontSize: fontSize || 24, fontWeight: 700 }}>{text || '标题'}</Tag>
    },
    fields: {
      text: { type: 'text', label: '文字' },
      level: { type: 'select', label: '级别', options: [{ label: 'H1', value: '1' }, { label: 'H2', value: '2' }, { label: 'H3', value: '3' }] },
      color: { type: 'color', label: '颜色' },
      fontSize: { type: 'number', label: '字号' },
    },
    defaultProps: { text: '新标题', level: '2', fontSize: 24 },
  },
  Paragraph: {
    label: '段落',
    render: ({ text, color, fontSize, textAlign }) => (
      <p style={{ margin: '0 0 12px 0', fontSize: fontSize || 14, lineHeight: 1.6, color: color || '#4B5563', textAlign: textAlign || 'left' }}>{text || '段落文字'}</p>
    ),
    fields: {
      text: { type: 'textarea', label: '文字' },
      color: { type: 'color', label: '颜色' },
      fontSize: { type: 'number', label: '字号' },
      textAlign: { type: 'select', label: '对齐', options: [{ label: '左', value: 'left' }, { label: '中', value: 'center' }, { label: '右', value: 'right' }] },
    },
    defaultProps: { text: '这是一段文字', fontSize: 14, textAlign: 'left' },
  },
  Button: {
    label: '按钮',
    render: ({ text, variant, width, color }) => (
      <button style={{
        padding: '10px 24px', borderRadius: 6, border: 'none', cursor: 'pointer',
        fontWeight: 600, fontSize: 14, width: width ? `${width}px` : 'auto',
        background: variant === 'primary' ? (color || '#7C3AED') : '#E2E8F0',
        color: variant === 'primary' ? '#fff' : '#1A1A1A',
      }}>{text || '按钮'}</button>
    ),
    fields: {
      text: { type: 'text', label: '文字' },
      variant: { type: 'radio', label: '样式', options: [{ label: '主要', value: 'primary' }, { label: '次要', value: 'secondary' }] },
      color: { type: 'color', label: '主色' },
      width: { type: 'number', label: '宽度' },
    },
    defaultProps: { text: '提交', variant: 'primary', color: '#7C3AED' },
  },
  Image: {
    label: '图片',
    render: ({ src, alt, width, height, borderRadius }) => (
      <img src={src || 'https://via.placeholder.com/400x200'} alt={alt || ''} style={{ maxWidth: '100%', borderRadius: borderRadius || 8, width: width ? `${width}px` : 'auto', height: height ? `${height}px` : 'auto' }} />
    ),
    fields: {
      src: { type: 'text', label: '图片地址' },
      alt: { type: 'text', label: '替代文字' },
      width: { type: 'number', label: '宽度' },
      height: { type: 'number', label: '高度' },
      borderRadius: { type: 'number', label: '圆角' },
    },
    defaultProps: { src: '', alt: '', borderRadius: 8 },
  },
  Input: {
    label: '输入框',
    render: ({ placeholder, width, type }) => (
      <input type={type || 'text'} placeholder={placeholder || '输入...'} readOnly style={{ padding: '10px 14px', border: '1px solid #D1D5DB', borderRadius: 6, fontSize: 14, width: width ? `${width}px` : '100%', outline: 'none', background: '#F9FAFB' }} />
    ),
    fields: {
      placeholder: { type: 'text', label: '占位文字' },
      width: { type: 'number', label: '宽度' },
      type: { type: 'select', label: '类型', options: [{ label: '文本', value: 'text' }, { label: '密码', value: 'password' }, { label: '邮箱', value: 'email' }] },
    },
    defaultProps: { placeholder: '请输入...', width: 300, type: 'text' },
  },
  Card: {
    label: '卡片',
    isContainer: true,
    render: ({ padding, bgColor, radius, shadow }, children) => (
      <div style={{ padding: padding || 20, borderRadius: radius || 12, background: bgColor || '#F9FAFB', border: '1px solid #E5E7EB', boxShadow: shadowMap[shadow || 'sm'] }}>
        {children || <span style={{ fontSize: 12, color: '#9CA3AF' }}>拖入组件到此处</span>}
      </div>
    ),
    fields: {
      padding: { type: 'number', label: '内边距' },
      bgColor: { type: 'color', label: '背景色' },
      radius: { type: 'number', label: '圆角' },
      shadow: { type: 'select', label: '阴影', options: [{ label: '小', value: 'sm' }, { label: '中', value: 'md' }, { label: '大', value: 'lg' }] },
    },
    defaultProps: { padding: 20, bgColor: '#F9FAFB', radius: 12, shadow: 'sm' },
  },
  Flex: {
    label: '弹性布局',
    isContainer: true,
    render: ({ direction, gap, justify, align }, children) => (
      <div style={{ display: 'flex', flexDirection: direction || 'column', gap: gap || 8, justifyContent: justify === 'center' ? 'center' : justify === 'between' ? 'space-between' : justify === 'around' ? 'space-around' : 'flex-start', alignItems: align === 'center' ? 'center' : align === 'stretch' ? 'stretch' : 'flex-start' }}>
        {children || <span style={{ fontSize: 12, color: '#9CA3AF' }}>拖入组件</span>}
      </div>
    ),
    fields: {
      direction: { type: 'select', label: '方向', options: [{ label: '水平', value: 'row' }, { label: '垂直', value: 'column' }] },
      gap: { type: 'number', label: '间距' },
      justify: { type: 'select', label: '主轴', options: [{ label: '起始', value: 'start' }, { label: '居中', value: 'center' }, { label: '两端', value: 'between' }, { label: '环绕', value: 'around' }] },
      align: { type: 'select', label: '交叉轴', options: [{ label: '起始', value: 'start' }, { label: '居中', value: 'center' }, { label: '拉伸', value: 'stretch' }] },
    },
    defaultProps: { direction: 'column', gap: 8, justify: 'start', align: 'start' },
  },
  Grid: {
    label: '网格',
    isContainer: true,
    render: ({ columns, gap }, children) => (
      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${columns || 2}, 1fr)`, gap: gap || 12 }}>
        {children || <span style={{ fontSize: 12, color: '#9CA3AF' }}>拖入组件</span>}
      </div>
    ),
    fields: {
      columns: { type: 'number', label: '列数' },
      gap: { type: 'number', label: '间距' },
    },
    defaultProps: { columns: 2, gap: 12 },
  },
  Section: {
    label: '区块',
    isContainer: true,
    render: ({ bgColor, padding, maxWidth }, children) => (
      <div style={{ background: bgColor || 'transparent', padding: padding || 24, maxWidth: maxWidth || 720, borderRadius: 8 }}>
        {children || <span style={{ fontSize: 12, color: '#9CA3AF' }}>拖入组件到区块</span>}
      </div>
    ),
    fields: {
      bgColor: { type: 'color', label: '背景色' },
      padding: { type: 'number', label: '内边距' },
      maxWidth: { type: 'number', label: '最大宽度' },
    },
    defaultProps: { padding: 24, maxWidth: 720 },
  },
  Divider: {
    label: '分割线',
    render: ({ color, thickness, margin }) => (
      <hr style={{ border: 'none', borderTop: `${thickness || 1}px solid ${color || '#E5E7EB'}`, margin: `${margin || 16}px 0` }} />
    ),
    fields: {
      color: { type: 'color', label: '颜色' },
      thickness: { type: 'number', label: '粗细' },
      margin: { type: 'number', label: '外边距' },
    },
    defaultProps: { color: '#E5E7EB', thickness: 1, margin: 16 },
  },
  Space: {
    label: '间距',
    render: ({ height }) => <div style={{ height: height || 20 }} />,
    fields: { height: { type: 'number', label: '高度' } },
    defaultProps: { height: 20 },
  },
}

// ── Path utilities (address items in the tree) ──────────────────────── //

type Path = (number)[]  // e.g. [0, 2] = content[0].children[2]

function deepClone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj))
}

function getItem(content: DesignItem[], path: Path): DesignItem | null {
  if (path.length === 0) return null
  let item = content[path[0]]
  for (let i = 1; i < path.length; i++) {
    if (!item?.children) return null
    item = item.children[path[i]]
  }
  return item
}

function updateItem(content: DesignItem[], path: Path, updater: (item: DesignItem) => DesignItem): DesignItem[] {
  const result = deepClone(content)
  let arr = result
  for (let i = 0; i < path.length - 1; i++) {
    arr = arr[path[i]].children!
  }
  arr[path[path.length - 1]] = updater(arr[path[path.length - 1]])
  return result
}

function deleteItem(content: DesignItem[], path: Path): DesignItem[] {
  const result = deepClone(content)
  let arr = result
  for (let i = 0; i < path.length - 1; i++) {
    arr = arr[path[i]].children!
  }
  arr.splice(path[path.length - 1], 1)
  return result
}

function addItemToTree(content: DesignItem[], path: Path | null, item: DesignItem): DesignItem[] {
  const result = deepClone(content)
  if (!path || path.length === 0) {
    result.push(item)
    return result
  }
  // path points to a container — append to its children
  let target = result
  for (let i = 0; i < path.length - 1; i++) {
    target = target[path[i]].children!
  }
  const container = target[path[path.length - 1]]
  if (!container.children) container.children = []
  container.children.push(item)
  return result
}

function reorderInTree(content: DesignItem[], from: Path, to: Path): DesignItem[] {
  const item = getItem(content, from)
  if (!item) return content
  let result = deleteItem(content, from)
  // Adjust to path if from was before to in the same array
  if (from.length === to.length && from.slice(0, -1).join() === to.slice(0, -1).join() && from[from.length - 1] < to[to.length - 1]) {
    to = [...to.slice(0, -1), to[to.length - 1] - 1]
  }
  // Insert at to
  let arr = result
  for (let i = 0; i < to.length - 1; i++) {
    arr = arr[to[i]].children!
  }
  if (to.length === 1) {
    result.splice(to[0], 0, item)
  } else {
    const parent = arr
    if (!parent[to[to.length - 2]]?.children) parent[to[to.length - 2]].children = []
    // This path is for nested — simpler approach below
  }
  // Simpler: if to has length 1, we already did it above
  // For nested, rebuild children
  if (to.length > 1) {
    result = addItemToTree(result, to.slice(0, -1).length === 0 ? null : to.slice(0, -1), item)
  }
  return result
}

// ── Layer Tree ──────────────────────────────────────────────────────── //

function flattenTree(items: DesignItem[], parentPath: Path = []): { item: DesignItem; path: Path; depth: number }[] {
  const result: { item: DesignItem; path: Path; depth: number }[] = []
  items.forEach((item, idx) => {
    const path = [...parentPath, idx]
    result.push({ item, path, depth: parentPath.length })
    if (item.children) {
      result.push(...flattenTree(item.children, path))
    }
  })
  return result
}

// ── Field Renderer ──────────────────────────────────────────────────── //

function FieldEditor({ field, value, onChange }: { field: FieldConfig; value: any; onChange: (v: any) => void }) {
  const s: React.CSSProperties = { width: '100%', padding: '6px 10px', border: '1px solid #D1D5DB', borderRadius: 4, fontSize: 13, background: '#fff', boxSizing: 'border-box' }
  switch (field.type) {
    case 'textarea': return <textarea value={value ?? ''} onChange={(e) => onChange(e.target.value)} rows={3} style={{ ...s, resize: 'vertical' }} />
    case 'number': return <input type="number" value={value ?? 0} onChange={(e) => onChange(Number(e.target.value) || 0)} style={s} />
    case 'select': return <select value={value ?? ''} onChange={(e) => onChange(e.target.value)} style={s}>{(field.options || []).map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}</select>
    case 'radio': return <div style={{ display: 'flex', gap: 12 }}>{(field.options || []).map((o) => <label key={o.value} style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 13, cursor: 'pointer' }}><input type="radio" checked={value === o.value} onChange={() => onChange(o.value)} />{o.label}</label>)}</div>
    case 'color': return <div style={{ display: 'flex', gap: 6 }}><input type="color" value={value || '#000000'} onChange={(e) => onChange(e.target.value)} style={{ width: 32, height: 32, border: '1px solid #D1D5DB', borderRadius: 4, padding: 0, cursor: 'pointer' }} /><input type="text" value={value || ''} onChange={(e) => onChange(e.target.value)} style={{ ...s, width: 100 }} /></div>
    default: return <input type="text" value={value ?? ''} onChange={(e) => onChange(e.target.value)} style={s} />
  }
}

// ── Main Canvas ──────────────────────────────────────────────────────── //

interface DesignCanvasProps {
  initialData?: DesignData
  onSave?: (data: DesignData) => void
}

const VIEWPORTS = [
  { label: '桌面', width: 0, icon: '🖥' },
  { label: '平板', width: 600, icon: '📱' },
  { label: '手机', width: 375, icon: '📱' },
]

export function DesignCanvas({ initialData, onSave }: DesignCanvasProps) {
  // ── State ── //
  const [data, setData] = useState<DesignData>(initialData || { root: { props: { bgColor: '#FFFFFF', padding: 40 } }, content: [] })
  const [selectedPath, setSelectedPath] = useState<Path | null>(null)
  const [viewport, setViewport] = useState(0)
  const [clipboard, setClipboard] = useState<DesignItem | null>(null)
  const [showLayers, setShowLayers] = useState(true)
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; path: Path } | null>(null)

  // ── History ── //
  const history = useRef<DesignData[]>([])
  const historyIdx = useRef(-1)
  const skipHistory = useRef(false)

  const commitHistory = useCallback((newData: DesignData) => {
    if (skipHistory.current) { skipHistory.current = false; setData(newData); return }
    history.current = history.current.slice(0, historyIdx.current + 1)
    history.current.push(deepClone(newData))
    historyIdx.current = history.current.length - 1
    if (history.current.length > 50) { history.current.shift(); historyIdx.current-- }
    setData(newData)
  }, [])

  const undo = useCallback(() => {
    if (historyIdx.current > 0) {
      historyIdx.current--
      skipHistory.current = true
      setData(deepClone(history.current[historyIdx.current]))
    }
  }, [])

  const redo = useCallback(() => {
    if (historyIdx.current < history.current.length - 1) {
      historyIdx.current++
      skipHistory.current = true
      setData(deepClone(history.current[historyIdx.current]))
    }
  }, [])

  // ── Sync external data ── //
  const lastExternal = useRef<string>('')
  useEffect(() => {
    if (initialData) {
      const sig = JSON.stringify(initialData)
      if (sig !== lastExternal.current) {
        lastExternal.current = sig
        setData(initialData)
        setSelectedPath(null)
        history.current = [deepClone(initialData)]
        historyIdx.current = 0
      }
    }
  }, [initialData])

  // ── Keyboard shortcuts ── //
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Don't trigger when typing in inputs
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) { e.preventDefault(); undo() }
      if ((e.metaKey || e.ctrlKey) && (e.key === 'y' || (e.shiftKey && e.key === 'z'))) { e.preventDefault(); redo() }
      if ((e.metaKey || e.ctrlKey) && e.key === 'c' && selectedPath) { e.preventDefault(); const item = getItem(data.content, selectedPath); if (item) setClipboard(deepClone(item)) }
      if ((e.metaKey || e.ctrlKey) && e.key === 'v' && clipboard) { e.preventDefault(); const newContent = addItemToTree(data.content, null, deepClone(clipboard)); commitHistory({ ...data, content: newContent }) }
      if ((e.key === 'Delete' || e.key === 'Backspace') && selectedPath) { e.preventDefault(); const newContent = deleteItem(data.content, selectedPath); commitHistory({ ...data, content: newContent }); setSelectedPath(null) }
      if (e.key === 'Escape') { setSelectedPath(null); setContextMenu(null) }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [selectedPath, clipboard, data, undo, redo, commitHistory])

  // ── Mutations ── //
  const updateProps = useCallback((path: Path, props: Record<string, any>) => {
    commitHistory({ ...data, content: updateItem(data.content, path, (item) => ({ ...item, props: { ...item.props, ...props } })) })
  }, [data, commitHistory])

  const addComponent = useCallback((type: string) => {
    const cfg = componentRegistry[type]
    if (!cfg) return
    const newItem: DesignItem = { type, props: { ...cfg.defaultProps } }
    // If a container is selected, add inside it
    const targetPath = selectedPath && getItem(data.content, selectedPath)?.children !== undefined ? selectedPath : null
    commitHistory({ ...data, content: addItemToTree(data.content, targetPath, newItem) })
  }, [data, selectedPath, commitHistory])

  const deleteComponent = useCallback((path: Path) => {
    commitHistory({ ...data, content: deleteItem(data.content, path) })
    setSelectedPath(null)
  }, [data, commitHistory])

  const duplicateComponent = useCallback((path: Path) => {
    const item = getItem(data.content, path)
    if (!item) return
    const newContent = addItemToTree(data.content, null, deepClone(item))
    commitHistory({ ...data, content: newContent })
  }, [data, commitHistory])

  // ── Drag & Drop ── //
  const [dragPath, setDragPath] = useState<Path | null>(null)
  const [dragOverPath, setDragOverPath] = useState<Path | null>(null)

  // ── Context menu ── //
  const onContextMenu = (e: React.MouseEvent, path: Path) => {
    e.preventDefault(); e.stopPropagation()
    setSelectedPath(path)
    setContextMenu({ x: e.clientX, y: e.clientY, path })
  }

  // ── Render item recursively ── //
  const renderItem = (item: DesignItem, path: Path): React.ReactNode => {
    const cfg = componentRegistry[item.type]
    if (!cfg) return null
    const isSelected = selectedPath && path.length === selectedPath.length && path.every((v, i) => v === selectedPath[i])
    const isDragOver = dragOverPath && path.length === dragOverPath.length && path.every((v, i) => v === dragOverPath[i])

    const children = item.children?.map((child, i) => renderItem(child, [...path, i]))

    return (
      <div
        key={path.join('-')}
        draggable
        onDragStart={() => setDragPath(path)}
        onDragOver={(e) => { e.preventDefault(); setDragOverPath(path) }}
        onDrop={(e) => {
          e.preventDefault(); e.stopPropagation()
          if (dragPath && cfg.isContainer && dragPath.join('-') !== path.join('-')) {
            // Move dragPath into this container
            const moved = getItem(data.content, dragPath)
            if (moved) {
              let newContent = deleteItem(data.content, dragPath)
              newContent = addItemToTree(newContent, path, deepClone(moved))
              commitHistory({ ...data, content: newContent })
            }
          }
          setDragPath(null); setDragOverPath(null)
        }}
        onClick={(e) => { e.stopPropagation(); setSelectedPath(path) }}
        onContextMenu={(e) => onContextMenu(e, path)}
        style={{
          marginBottom: 4, padding: 2, borderRadius: 4, cursor: 'pointer',
          border: isSelected ? '2px solid #7C3AED' : isDragOver ? '2px dashed #A78BFA' : '2px solid transparent',
          transition: 'border-color 0.1s',
        }}
      >
        {cfg.render(item.props, children)}
      </div>
    )
  }

  // ── Selected item detail ── //
  const selectedItem = selectedPath ? getItem(data.content, selectedPath) : null
  const selectedCfg = selectedItem ? componentRegistry[selectedItem.type] : null

  // ── Flat layer list ── //
  const flatLayers = useMemo(() => flattenTree(data.content), [data.content])

  // ── Viewport ── //
  const vp = VIEWPORTS[viewport]
  const canvasMaxWidth = vp.width || '100%'

  return (
    <div style={{ display: 'flex', height: '100%', background: '#F3F4F6', position: 'relative' }} onClick={() => { setSelectedPath(null); setContextMenu(null) }}>
      {/* ── Left: Components + Layers ── */}
      <div style={{ width: 200, flexShrink: 0, borderRight: '1px solid #E5E7EB', background: '#fff', display: 'flex', flexDirection: 'column' }}>
        {/* Component palette */}
        <div style={{ padding: '10px 8px', borderBottom: '1px solid #E5E7EB', maxHeight: 260, overflowY: 'auto' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8 }}>组件</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {Object.entries(componentRegistry).map(([type, cfg]) => (
              <button key={type} onClick={(e) => { e.stopPropagation(); addComponent(type) }} style={{ padding: '5px 10px', background: '#F3F4F6', border: '1px solid #E5E7EB', borderRadius: 4, cursor: 'pointer', fontSize: 12, color: '#374151' }}
                onMouseEnter={(e) => e.currentTarget.style.background = '#EEF2FF'}
                onMouseLeave={(e) => e.currentTarget.style.background = '#F3F4F6'}>
                {cfg.label}
              </button>
            ))}
          </div>
        </div>
        {/* Layer tree */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 8px' }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            图层
            <button onClick={(e) => { e.stopPropagation(); setShowLayers(!showLayers) }} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 10, color: '#9CA3AF' }}>{showLayers ? '收起' : '展开'}</button>
          </div>
          {showLayers && flatLayers.map(({ item, path, depth }) => (
            <div key={path.join('-')} onClick={(e) => { e.stopPropagation(); setSelectedPath(path) }}
              style={{
                padding: `4px 8px`, marginLeft: depth * 12, fontSize: 12, cursor: 'pointer', borderRadius: 3,
                background: selectedPath && path.join('-') === selectedPath.join('-') ? '#EEF2FF' : 'transparent',
                color: selectedPath && path.join('-') === selectedPath.join('-') ? '#4F46E5' : '#374151',
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
              {componentRegistry[item.type]?.isContainer ? '▸ ' : ''}{componentRegistry[item.type]?.label || item.type}
            </div>
          ))}
          {flatLayers.length === 0 && <div style={{ fontSize: 12, color: '#D1D5DB' }}>暂无组件</div>}
        </div>
      </div>

      {/* ── Center: Canvas ── */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Toolbar */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '6px 12px', borderBottom: '1px solid #E5E7EB', background: '#fff', flexShrink: 0 }}>
          <div style={{ display: 'flex', gap: 4 }}>
            {VIEWPORTS.map((v, i) => (
              <button key={i} onClick={(e) => { e.stopPropagation(); setViewport(i) }}
                style={{ padding: '4px 10px', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12,
                  background: viewport === i ? '#7C3AED' : 'transparent', color: viewport === i ? '#fff' : '#6B7280' }}>
                {v.label}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={(e) => { e.stopPropagation(); undo() }} disabled={historyIdx.current <= 0} style={{ padding: '4px 10px', border: '1px solid #E5E7EB', borderRadius: 4, cursor: 'pointer', fontSize: 12, background: '#fff', color: historyIdx.current <= 0 ? '#D1D5DB' : '#374151' }}>撤销</button>
            <button onClick={(e) => { e.stopPropagation(); redo() }} disabled={historyIdx.current >= history.current.length - 1} style={{ padding: '4px 10px', border: '1px solid #E5E7EB', borderRadius: 4, cursor: 'pointer', fontSize: 12, background: '#fff', color: historyIdx.current >= history.current.length - 1 ? '#D1D5DB' : '#374151' }}>重做</button>
          </div>
        </div>
        {/* Canvas area */}
        <div style={{ flex: 1, overflowY: 'auto', padding: 24, display: 'flex', justifyContent: 'center', alignItems: 'flex-start' }}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault()
            if (dragPath) {
              // Reorder to end
              const moved = getItem(data.content, dragPath)
              if (moved) {
                let newContent = deleteItem(data.content, dragPath)
                newContent = [...newContent, deepClone(moved)]
                commitHistory({ ...data, content: newContent })
              }
            }
            setDragPath(null); setDragOverPath(null)
          }}>
          <div style={{ width: '100%', maxWidth: canvasMaxWidth as any, minHeight: '100%', background: data.root?.props?.bgColor || '#FFFFFF', borderRadius: 8, padding: data.root?.props?.padding || 40, boxShadow: '0 1px 3px rgba(0,0,0,0.08)' }}
            onClick={() => setSelectedPath(null)}>
            {data.content.length === 0 && (
              <div style={{ textAlign: 'center', padding: '60px 20px', color: '#9CA3AF', fontSize: 14 }}>
                从左侧添加组件，或用 AI 生成设计
              </div>
            )}
            {data.content.map((item, idx) => renderItem(item, [idx]))}
          </div>
        </div>
      </div>

      {/* ── Right: Properties ── */}
      <div style={{ width: 260, flexShrink: 0, borderLeft: '1px solid #E5E7EB', background: '#fff', overflowY: 'auto', padding: '12px' }} onClick={(e) => e.stopPropagation()}>
        {selectedItem && selectedCfg ? (
          <>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <span style={{ fontSize: 13, fontWeight: 700 }}>{selectedCfg.label} 属性</span>
              <div style={{ display: 'flex', gap: 4 }}>
                <button onClick={() => duplicateComponent(selectedPath!)} style={{ padding: '2px 6px', fontSize: 11, border: '1px solid #D1D5DB', borderRadius: 3, cursor: 'pointer', background: '#fff' }}>复制</button>
                <button onClick={() => deleteComponent(selectedPath!)} style={{ padding: '2px 6px', fontSize: 11, border: 'none', borderRadius: 3, cursor: 'pointer', background: '#FEE2E2', color: '#DC2626' }}>删除</button>
              </div>
            </div>
            {Object.entries(selectedCfg.fields).map(([key, field]) => (
              <div key={key} style={{ marginBottom: 12 }}>
                <label style={{ display: 'block', fontSize: 12, color: '#6B7280', marginBottom: 4 }}>{field.label}</label>
                <FieldEditor field={field} value={selectedItem.props[key]} onChange={(v) => updateProps(selectedPath!, { [key]: v })} />
              </div>
            ))}
          </>
        ) : (
          <>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#9CA3AF', textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 10 }}>画布设置</div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', fontSize: 12, color: '#6B7280', marginBottom: 4 }}>背景色</label>
              <FieldEditor field={{ type: 'color', label: '背景色' }} value={data.root?.props?.bgColor} onChange={(v) => commitHistory({ ...data, root: { props: { ...data.root.props, bgColor: v } } })} />
            </div>
            <div style={{ marginBottom: 12 }}>
              <label style={{ display: 'block', fontSize: 12, color: '#6B7280', marginBottom: 4 }}>内边距</label>
              <FieldEditor field={{ type: 'number', label: '内边距' }} value={data.root?.props?.padding} onChange={(v) => commitHistory({ ...data, root: { props: { ...data.root.props, padding: v } } })} />
            </div>
            <div style={{ marginTop: 20, padding: 10, background: '#F3F4F6', borderRadius: 6, fontSize: 11, color: '#9CA3AF', lineHeight: 1.5 }}>
              快捷键: Ctrl+Z 撤销 | Ctrl+C/V 复制粘贴 | Del 删除 | Esc 取消选中
            </div>
          </>
        )}
      </div>

      {/* ── Context Menu ── */}
      {contextMenu && (
        <>
          <div style={{ position: 'fixed', inset: 0, zIndex: 200 }} onClick={(e) => { e.stopPropagation(); setContextMenu(null) }} onContextMenu={(e) => { e.preventDefault(); setContextMenu(null) }} />
          <div style={{ position: 'fixed', left: contextMenu.x, top: contextMenu.y, zIndex: 201, background: '#fff', border: '1px solid #E5E7EB', borderRadius: 6, boxShadow: '0 4px 12px rgba(0,0,0,0.15)', padding: 4, minWidth: 120 }}>
            {[
              { label: '复制', action: () => { const item = getItem(data.content, contextMenu.path); if (item) setClipboard(deepClone(item)) } },
              { label: '粘贴到末尾', action: () => { if (clipboard) commitHistory({ ...data, content: addItemToTree(data.content, null, deepClone(clipboard)) }) } },
              { label: '创建副本', action: () => duplicateComponent(contextMenu.path) },
              { label: '删除', action: () => deleteComponent(contextMenu.path), danger: true },
            ].map((item, i) => (
              <button key={i} onClick={(e) => { e.stopPropagation(); item.action(); setContextMenu(null) }}
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 12px', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: 13, color: item.danger ? '#DC2626' : '#374151', borderRadius: 3 }}
                onMouseEnter={(e) => e.currentTarget.style.background = item.danger ? '#FEF2F2' : '#F3F4F6'}
                onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}>
                {item.label}
              </button>
            ))}
          </div>
        </>
      )}

      {/* ── Export/Save floating buttons ── */}
      <div style={{ position: 'absolute', bottom: 12, right: 12, display: 'flex', gap: 8 }}>
        <button onClick={(e) => { e.stopPropagation(); const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `design-${Date.now()}.madcop`; a.click() }}
          style={{ padding: '6px 12px', background: 'rgba(255,255,255,0.9)', border: '1px solid #E5E7EB', borderRadius: 4, cursor: 'pointer', fontSize: 12, color: '#374151', backdropFilter: 'blur(4px)' }}>
          导出 .madcop
        </button>
        <button onClick={(e) => { e.stopPropagation(); onSave?.(data) }}
          style={{ padding: '6px 12px', background: 'rgba(124,58,237,0.9)', color: '#fff', border: 'none', borderRadius: 4, cursor: 'pointer', fontSize: 12, fontWeight: 600, backdropFilter: 'blur(4px)' }}>
          保存
        </button>
      </div>
    </div>
  )
}

export type { ComponentConfig, FieldConfig }
