/**
 * Pure design-JSON helpers used by the Design tool page.
 * No Vue deps — unit-testable without mounting components.
 */

export interface DesignItem {
  type: string
  props: Record<string, any>
  children?: DesignItem[]
}

export interface DesignData {
  root: { props: Record<string, any> }
  content: DesignItem[]
}

export const DESIGN_COMPONENT_NAMES: Record<string, boolean> = {
  Header: true,
  Paragraph: true,
  Button: true,
  Image: true,
  Input: true,
  Card: true,
  Flex: true,
  Grid: true,
  Section: true,
  Divider: true,
  Space: true,
}

export const DESIGN_DEFAULTS: Record<string, Record<string, any>> = {
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

export function emptyDesignData(): DesignData {
  return { root: { props: { bgColor: '#FFFFFF', padding: 40 } }, content: [] }
}

/**
 * Pull a design JSON object (with a `content` array) out of an LLM string.
 * Handles fenced markdown, leading prose, and trailing junk.
 */
export function extractDesignJson(text: string): any | null {
  if (!text) return null
  let s = text.trim()
  const fence = s.match(/```(?:json)?\s*([\s\S]*?)```/i)
  if (fence) s = fence[1].trim()
  try {
    const p = JSON.parse(s)
    if (p && Array.isArray(p.content)) return p
  } catch {
    /* continue */
  }
  const idx = s.indexOf('{')
  if (idx < 0) return null
  for (let end = s.length; end > idx + 10; end--) {
    if (s[end - 1] !== '}') continue
    try {
      const p = JSON.parse(s.slice(idx, end))
      if (p && Array.isArray(p.content)) return p
    } catch {
      /* try shorter */
    }
  }
  return null
}

/**
 * Normalize LLM / partial design trees so the canvas can open them:
 * root props, defaults, unknown types → visible Paragraph fallback.
 */
export function autoRepairDesignData(data: any): DesignData {
  if (!data || typeof data !== 'object') return emptyDesignData()
  const out = data
  if (!out.root) out.root = { props: { bgColor: '#FFFFFF', padding: 40 } }
  if (!out.root.props) out.root.props = {}
  if (!out.root.props.bgColor) out.root.props.bgColor = '#FFFFFF'
  if (out.root.props.padding === undefined) out.root.props.padding = 40
  if (!Array.isArray(out.content)) out.content = []

  function repairItem(item: any): DesignItem | null {
    if (!item || !item.type) return null
    if (!DESIGN_COMPONENT_NAMES[item.type]) {
      return {
        type: 'Paragraph',
        props: { text: `[未知组件: ${item.type}]`, color: '#EF4444', fontSize: 12 },
      }
    }
    if (!item.props) item.props = {}
    const defs = DESIGN_DEFAULTS[item.type]
    if (defs) {
      for (const [k, v] of Object.entries(defs)) {
        if (item.props[k] === undefined) item.props[k] = v
      }
    }
    if (item.children && Array.isArray(item.children)) {
      item.children = item.children.map(repairItem).filter(Boolean)
    }
    return item as DesignItem
  }

  out.content = out.content.map(repairItem).filter(Boolean)
  return out as DesignData
}

/** Parse + repair in one step; null if no design object found. */
export function parseAndRepairDesignResponse(text: string): DesignData | null {
  const parsed = extractDesignJson(text)
  if (!parsed) return null
  return autoRepairDesignData(parsed)
}
