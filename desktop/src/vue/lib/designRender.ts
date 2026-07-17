/**
 * Pure HTML export for design trees (iframe preview / share).
 * Mirrors DesignCanvas component visual defaults without Vue.
 */
import type { DesignData, DesignItem } from './designJson'

function esc(s: any): string {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function renderItem(item: DesignItem): string {
  const p = item.props || {}
  const kids = (item.children || []).map(renderItem).join('')
  switch (item.type) {
    case 'Header': {
      const tag = `h${p.level || 2}`
      return `<${tag} style="margin:0 0 8px;color:${p.color || '#111827'};font-size:${p.fontSize || 24}px;font-weight:700;line-height:1.25">${esc(p.text || '标题')}</${tag}>`
    }
    case 'Paragraph':
      return `<p style="margin:0 0 12px;font-size:${p.fontSize || 14}px;line-height:1.6;color:${p.color || '#4B5563'};text-align:${p.textAlign || 'left'}">${esc(p.text || '段落文字')}</p>`
    case 'Button': {
      const bg = p.variant === 'primary' ? (p.color || '#7C3AED') : '#F3F4F6'
      const fg = p.variant === 'primary' ? '#FFFFFF' : '#374151'
      const w = p.width ? `width:${p.width}px;` : ''
      return `<button style="${w}padding:10px 24px;border-radius:8px;border:none;cursor:pointer;font-weight:600;font-size:14px;background:${bg};color:${fg}">${esc(p.text || '按钮')}</button>`
    }
    case 'Image': {
      const w = p.width || 300
      const h = p.height || 200
      const br = p.borderRadius ?? 8
      const src =
        p.src && String(p.src).trim()
          ? p.src
          : `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' width='${w}' height='${h}'><rect width='${w}' height='${h}' fill='#F3F4F6'/><text x='50%' y='50%' font-family='sans-serif' font-size='14' fill='#9CA3AF' text-anchor='middle' dominant-baseline='middle'>${w}×${h}</text></svg>`)}`
      return `<img src="${esc(src)}" alt="${esc(p.alt || '')}" style="max-width:100%;width:${w}px;height:${h}px;object-fit:cover;border-radius:${br}px;display:block" />`
    }
    case 'Input':
      return `<input type="${esc(p.type || 'text')}" placeholder="${esc(p.placeholder || '')}" style="box-sizing:border-box;padding:10px 14px;border:1px solid #E5E7EB;border-radius:8px;font-size:14px;width:${p.width || 300}px;outline:none" />`
    case 'Card': {
      const shadows: Record<string, string> = {
        sm: '0 1px 2px rgba(0,0,0,0.05)',
        md: '0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -2px rgba(0,0,0,0.05)',
        lg: '0 10px 24px -4px rgba(0,0,0,0.12), 0 4px 8px -4px rgba(0,0,0,0.08)',
      }
      return `<div style="background:${p.bgColor || '#FFFFFF'};border:1px solid #E5E7EB;border-radius:${p.radius || 12}px;padding:${p.padding || 24}px;box-shadow:${shadows[p.shadow || 'md'] || shadows.md}">${kids}</div>`
    }
    case 'Flex': {
      const jmap: Record<string, string> = {
        start: 'flex-start',
        center: 'center',
        end: 'flex-end',
        between: 'space-between',
        around: 'space-around',
      }
      const amap: Record<string, string> = {
        start: 'flex-start',
        center: 'center',
        end: 'flex-end',
        stretch: 'stretch',
      }
      return `<div style="display:flex;flex-direction:${p.direction || 'column'};gap:${p.gap || 16}px;justify-content:${jmap[p.justify || 'start'] || 'flex-start'};align-items:${amap[p.align || 'stretch'] || 'stretch'}">${kids}</div>`
    }
    case 'Grid':
      return `<div style="display:grid;grid-template-columns:repeat(${p.columns || 2},1fr);gap:${p.gap || 16}px">${kids}</div>`
    case 'Section':
      return `<section style="${p.maxWidth ? `max-width:${p.maxWidth}px;margin:0 auto;` : ''}padding:${p.padding || 40}px;background:${p.bgColor || '#F9FAFB'}">${kids}</section>`
    case 'Divider':
      return `<hr style="margin:${p.margin || 16}px 0;border:none;border-top:${p.thickness || 1}px solid ${p.color || '#E5E7EB'}" />`
    case 'Space':
      return `<div style="height:${p.height || 16}px"></div>`
    default:
      return kids || ''
  }
}

/** Build a full HTML document for iframe srcdoc / export. */
export function designDataToHtml(design: DesignData | null | undefined): string {
  const d = design || { root: { props: { bgColor: '#FFFFFF', padding: 40 } }, content: [] }
  const bg = d.root?.props?.bgColor || '#FFFFFF'
  const pad = d.root?.props?.padding ?? 40
  const body = (d.content || []).map(renderItem).join('')
  return `<!DOCTYPE html><html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/><style>
  *{box-sizing:border-box} body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:${bg};}
  .frame{padding:${pad}px;max-width:960px;margin:0 auto;min-height:100vh}
  </style></head><body><div class="frame">${body || '<p style="color:#9CA3AF;text-align:center;padding:80px 20px">空画布</p>'}</div></body></html>`
}
