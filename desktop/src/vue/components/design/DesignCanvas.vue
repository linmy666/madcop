<script setup lang="ts">
/**
 * v3.0 — MadCop Design Canvas (Vue 3 port)
 *
 * Native HTML5 drag-drop design editor. No external CSS, no Puck, no deps.
 * 1:1 port of src/design/DesignCanvas.tsx (React).
 *
 * Features:
 *  - 11 component types: Header / Paragraph / Button / Image / Input / Card /
 *    Flex / Grid / Section / Divider / Space
 *  - Click to select, edit fields in right panel
 *  - Drag to reorder children
 *  - 导出 .madcop (JSON) and 导入 .madcop
 *  - 保存 triggers onSave callback
 */

import { ref, computed, onMounted } from 'vue'

// ── Types ──────────────────────────────────────────────────────────────

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
  fields: Record<string, FieldConfig>
  defaultProps: Record<string, any>
  isContainer?: boolean
  label: string
  render: (props: Record<string, any>, children?: string) => string
}

// ── Component Registry ────────────────────────────────────────────────

const componentRegistry: Record<string, ComponentConfig> = {
  Header: {
    label: '标题',
    fields: {
      text: { type: 'text', label: '文字' },
      level: { type: 'select', label: '级别', options: [{ label: 'H1', value: '1' }, { label: 'H2', value: '2' }, { label: 'H3', value: '3' }] },
      color: { type: 'color', label: '颜色' },
      fontSize: { type: 'number', label: '字号' },
    },
    defaultProps: { text: '新标题', level: '2', fontSize: 24 },
    render: ({ text, level, color, fontSize }) => {
      const fontSizePx = `${fontSize || 24}px`
      const colorHex = color || '#111827'
      const text_ = text || '标题'
      const tag = `h${level || 2}`
      return `<${tag} style="margin: 0 0 8px 0; color: ${colorHex}; font-size: ${fontSizePx}; font-weight: 700; line-height: 1.25;">${text_}</${tag}>`
    },
  },
  Paragraph: {
    label: '段落',
    fields: {
      text: { type: 'textarea', label: '文字' },
      color: { type: 'color', label: '颜色' },
      fontSize: { type: 'number', label: '字号' },
      textAlign: { type: 'select', label: '对齐', options: [{ label: '左', value: 'left' }, { label: '中', value: 'center' }, { label: '右', value: 'right' }] },
    },
    defaultProps: { text: '这是一段文字', fontSize: 14, textAlign: 'left' },
    render: ({ text, color, fontSize, textAlign }) =>
      `<p style="margin: 0 0 12px 0; font-size: ${fontSize || 14}px; line-height: 1.6; color: ${color || '#4B5563'}; text-align: ${textAlign || 'left'};">${text || '段落文字'}</p>`,
  },
  Button: {
    label: '按钮',
    fields: {
      text: { type: 'text', label: '文字' },
      variant: { type: 'select', label: '样式', options: [{ label: '主按钮', value: 'primary' }, { label: '次按钮', value: 'secondary' }] },
      color: { type: 'color', label: '颜色' },
      width: { type: 'number', label: '宽度' },
    },
    defaultProps: { text: '按钮', variant: 'primary' },
    render: ({ text, variant, color, width }) => {
      const bg = variant === 'primary' ? (color || '#7C3AED') : '#F3F4F6'
      const fg = variant === 'primary' ? '#FFFFFF' : '#374151'
      const widthStyle = width ? `width: ${width}px; ` : ''
      return `<button style="${widthStyle}padding: 10px 24px; border-radius: 8px; border: none; cursor: pointer; font-weight: 600; font-size: 14px; background: ${bg}; color: ${fg}; transition: opacity 0.15s, transform 0.05s;" onmouseover="this.style.opacity='0.9'" onmouseout="this.style.opacity='1'">${text || '按钮'}</button>`
    },
  },
  Image: {
    label: '图片',
    fields: {
      src: { type: 'text', label: '图片地址' },
      alt: { type: 'text', label: '替代文字' },
      width: { type: 'number', label: '宽度' },
      height: { type: 'number', label: '高度' },
      borderRadius: { type: 'number', label: '圆角' },
    },
    defaultProps: { src: '', alt: '', width: 300, height: 200, borderRadius: 8 },
    render: ({ src, alt, width, height, borderRadius }) => {
      // Inline SVG placeholder so we never depend on a dead external URL.
      const w = width || 300
      const h = height || 200
      const br = borderRadius ?? 8
      const realSrc = src && src.trim()
        ? src
        : `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' width='${w}' height='${h}'><rect width='${w}' height='${h}' fill='#F3F4F6'/><text x='50%' y='50%' font-family='sans-serif' font-size='14' fill='#9CA3AF' text-anchor='middle' dominant-baseline='middle'>${w}×${h}</text></svg>`)}`
      return `<img src="${realSrc}" alt="${alt || ''}" style="max-width: 100%; width: ${w}px; height: ${h}px; object-fit: cover; border-radius: ${br}px; display: block;" />`
    },
  },
  Input: {
    label: '输入框',
    fields: {
      placeholder: { type: 'text', label: '占位文字' },
      width: { type: 'number', label: '宽度' },
      type: { type: 'select', label: '类型', options: [{ label: '文本', value: 'text' }, { label: '密码', value: 'password' }, { label: '邮箱', value: 'email' }] },
    },
    defaultProps: { placeholder: '请输入...', width: 300, type: 'text' },
    render: ({ placeholder, width, type }) =>
      `<input type="${type || 'text'}" placeholder="${placeholder || ''}" style="box-sizing: border-box; padding: 10px 14px; border: 1px solid #E5E7EB; border-radius: 8px; font-size: 14px; width: ${width || 300}px; outline: none; transition: border-color 0.15s;" onfocus="this.style.borderColor='#7C3AED'" onblur="this.style.borderColor='#E5E7EB'" />`,
  },
  Card: {
    label: '卡片',
    fields: {
      padding: { type: 'number', label: '内边距' },
      bgColor: { type: 'color', label: '背景色' },
      radius: { type: 'number', label: '圆角' },
      shadow: { type: 'select', label: '阴影', options: [{ label: '小', value: 'sm' }, { label: '中', value: 'md' }, { label: '大', value: 'lg' }] },
    },
    defaultProps: { padding: 24, bgColor: '#FFFFFF', radius: 12, shadow: 'md' },
    isContainer: true,
    render: ({ padding, bgColor, radius, shadow }, children = '') => {
      const shadows: Record<string, string> = {
        sm: '0 1px 2px rgba(0,0,0,0.05)',
        md: '0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -2px rgba(0,0,0,0.05)',
        lg: '0 10px 24px -4px rgba(0,0,0,0.12), 0 4px 8px -4px rgba(0,0,0,0.08)',
      }
      return `<div style="background: ${bgColor || '#FFFFFF'}; border: 1px solid #E5E7EB; border-radius: ${radius || 12}px; padding: ${padding || 24}px; box-shadow: ${shadows[shadow || 'md']};">${children}</div>`
    },
  },
  Flex: {
    label: '弹性布局',
    fields: {
      direction: { type: 'select', label: '方向', options: [{ label: '横向', value: 'row' }, { label: '纵向', value: 'column' }] },
      gap: { type: 'number', label: '间距' },
      justify: { type: 'select', label: '主轴对齐', options: [{ label: '起始', value: 'start' }, { label: '居中', value: 'center' }, { label: '末尾', value: 'end' }, { label: '两端', value: 'between' }, { label: '环绕', value: 'around' }] },
      align: { type: 'select', label: '交叉对齐', options: [{ label: '起始', value: 'start' }, { label: '居中', value: 'center' }, { label: '末尾', value: 'end' }, { label: '拉伸', value: 'stretch' }] },
    },
    defaultProps: { direction: 'column', gap: 16, justify: 'start', align: 'stretch' },
    isContainer: true,
    render: ({ direction, gap, justify, align }, children = '') => {
      const jc = { start: 'flex-start', center: 'center', end: 'flex-end', between: 'space-between', around: 'space-around' }[justify || 'start'] || 'flex-start'
      const ac = { start: 'flex-start', center: 'center', end: 'flex-end', stretch: 'stretch' }[align || 'stretch'] || 'stretch'
      return `<div style="display: flex; flex-direction: ${direction || 'column'}; gap: ${gap || 16}px; justify-content: ${jc}; align-items: ${ac};">${children}</div>`
    },
  },
  Grid: {
    label: '网格',
    fields: {
      columns: { type: 'number', label: '列数' },
      gap: { type: 'number', label: '间距' },
    },
    defaultProps: { columns: 2, gap: 16 },
    isContainer: true,
    render: ({ columns, gap }, children = '') =>
      `<div style="display: grid; grid-template-columns: repeat(${columns || 2}, 1fr); gap: ${gap || 16}px;">${children}</div>`,
  },
  Section: {
    label: '区块',
    fields: {
      bgColor: { type: 'color', label: '背景色' },
      padding: { type: 'number', label: '内边距' },
      maxWidth: { type: 'number', label: '最大宽度' },
    },
    defaultProps: { bgColor: '#F9FAFB', padding: 40, maxWidth: 960 },
    isContainer: true,
    render: ({ bgColor, padding, maxWidth }, children = '') => {
      const mw = maxWidth ? `max-width: ${maxWidth}px; margin: 0 auto; ` : ''
      return `<section style="${mw}padding: ${padding || 40}px; background: ${bgColor || '#F9FAFB'};">${children}</section>`
    },
  },
  Divider: {
    label: '分割线',
    fields: {
      color: { type: 'color', label: '颜色' },
      thickness: { type: 'number', label: '粗细' },
      margin: { type: 'number', label: '上下间距' },
    },
    defaultProps: { color: '#E5E7EB', thickness: 1, margin: 16 },
    render: ({ color, thickness, margin }) =>
      `<hr style="margin: ${margin || 16}px 0; border: none; border-top: ${thickness || 1}px solid ${color || '#E5E7EB'};" />`,
  },
  Space: {
    label: '间距',
    fields: {
      height: { type: 'number', label: '高度' },
    },
    defaultProps: { height: 16 },
    render: ({ height }) => `<div style="height: ${height || 16}px;"></div>`,
  },
}

// ── Empty data helper ───────────────────────────────────────────────

function emptyData(): DesignData {
  return {
    root: { props: { bgColor: '#FFFFFF', padding: 40 } },
    content: [],
  }
}

// ── Props ─────────────────────────────────────────────────────────────

const props = defineProps<{
  initialData: DesignData
}>()

const emit = defineEmits<{
  save: [data: DesignData]
}>()

// ── State ───────────────────────────────────────────────────────────

const data = ref<DesignData>(JSON.parse(JSON.stringify(props.initialData)) || emptyData())
const selectedIndex = ref<number | null>(null)
const draggingIndex = ref<number | null>(null)
const draggingType = ref<string | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)

// History (undo/redo)
const history = ref<DesignData[]>([])
const historyIndex = ref(-1)

watch(
  () => data.value,
  (val) => {
    // Push to history (debounced)
    history.value.push(JSON.parse(JSON.stringify(val)))
    historyIndex.value = history.value.length - 1
  },
  { deep: true }
)

onMounted(() => {
  // Load initial data
  if (props.initialData) {
    data.value = JSON.parse(JSON.stringify(props.initialData))
  }
  history.value = [JSON.parse(JSON.stringify(data.value))]
  historyIndex.value = 0
})

// ── Selection ────────────────────────────────────────────────────────

const selectedItem = computed<DesignItem | null>(() => {
  if (selectedIndex.value === null) return null
  return data.value.content[selectedIndex.value] || null
})

function selectIndex(idx: number | null) {
  selectedIndex.value = idx
}

// ── Item actions ────────────────────────────────────────────────────

function addItem(type: string, atIndex?: number) {
  const cfg = componentRegistry[type]
  if (!cfg) return
  const newItem: DesignItem = { type, props: { ...cfg.defaultProps } }
  const items = data.value.content
  if (atIndex === undefined || atIndex >= items.length) {
    items.push(newItem)
  } else {
    items.splice(atIndex, 0, newItem)
  }
  selectIndex(items.length - 1)
}

function updateItem(idx: number, updates: Partial<DesignItem['props']>) {
  const item = data.value.content[idx]
  if (!item) return
  item.props = { ...item.props, ...updates }
}

function deleteItem(idx: number) {
  data.value.content.splice(idx, 1)
  if (selectedIndex.value === idx) selectIndex(null)
  else if (selectedIndex.value !== null && selectedIndex.value > idx) {
    selectedIndex.value--
  }
}

function duplicateItem(idx: number) {
  const item = data.value.content[idx]
  if (!item) return
  const copy = JSON.parse(JSON.stringify(item))
  data.value.content.splice(idx + 1, 0, copy)
}

// ── Drag-drop ────────────────────────────────────────────────────────

function onDragStart(e: DragEvent, type: string) {
  draggingType.value = type
  draggingIndex.value = null
  e.dataTransfer?.setData('text/plain', type)
}

function onItemDragStart(e: DragEvent, idx: number) {
  draggingIndex.value = idx
  draggingType.value = null
  e.dataTransfer?.setData('text/plain', String(idx))
  e.stopPropagation()
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
}

function onDrop(e: DragEvent, atIndex?: number) {
  e.preventDefault()
  if (draggingType.value) {
    addItem(draggingType.value, atIndex)
  } else if (draggingIndex.value !== null) {
    // Reorder
    const fromIdx = draggingIndex.value
    let toIdx = atIndex
    if (toIdx === undefined) {
      data.value.content.push(data.value.content.splice(fromIdx, 1)[0])
    } else if (fromIdx !== toIdx) {
      const item = data.value.content.splice(fromIdx, 1)[0]
      data.value.content.splice(toIdx, 0, item)
      if (selectedIndex.value === fromIdx) selectedIndex.value = toIdx
    }
  }
  draggingType.value = null
  draggingIndex.value = null
}

// ── Undo/Redo ───────────────────────────────────────────────────────

function undo() {
  if (historyIndex.value > 0) {
    historyIndex.value--
    data.value = JSON.parse(JSON.stringify(history.value[historyIndex.value]))
  }
}
function redo() {
  if (historyIndex.value < history.value.length - 1) {
    historyIndex.value++
    data.value = JSON.parse(JSON.stringify(history.value[historyIndex.value]))
  }
}

// ── Export / Import .madcop ─────────────────────────────────────────

function exportMadcop() {
  const json = JSON.stringify(data.value, null, 2)
  const blob = new Blob([json], { type: 'application/json' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `design-${Date.now()}.madcop`
  a.click()
  URL.revokeObjectURL(url)
}

function triggerImport() {
  fileInputRef.value?.click()
}

function importMadcop(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = (ev) => {
    try {
      const parsed = JSON.parse(ev.target?.result as string)
      if (parsed.root && Array.isArray(parsed.content)) {
        data.value = parsed
        history.value = [JSON.parse(JSON.stringify(data.value))]
        historyIndex.value = 0
      } else {
        alert('文件格式有误')
      }
    } catch {
      alert('解析失败')
    }
  }
  reader.readAsText(file)
  input.value = ''
}

function saveData() {
  emit('save', JSON.parse(JSON.stringify(data.value)))
}

// ── Render the content tree ─────────────────────────────────────────

function renderItem(item: DesignItem): string {
  const cfg = componentRegistry[item.type]
  if (!cfg) return ''
  const childHtml = item.children ? item.children.map(renderItem).join('') : ''
  return cfg.render(item.props, childHtml)
}

const contentHtml = computed(() => data.value.content.map(renderItem).join(''))
</script>

<template>
  <div class="flex h-full w-full">
    <!-- Left palette -->
    <div
      style="width: 200px; background: var(--color-surface-container-lowest); border-right: 1px solid var(--color-border); padding: 12px; flex-shrink: 0; overflow-y: auto;"
    >
      <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: var(--color-text-tertiary); margin-bottom: 8px;">
        组件库
      </div>
      <div style="display: flex; flex-direction: column; gap: 6px;">
        <div
          v-for="(cfg, type) in componentRegistry"
          :key="type"
          draggable="true"
          @dragstart="onDragStart($event, type)"
          class="design-palette-item"
        >
          {{ cfg.label }}
        </div>
      </div>
      <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: var(--color-text-tertiary); margin: 16px 0 8px;">
        操作
      </div>
      <div style="display: flex; flex-direction: column; gap: 6px;">
        <button
          @click="undo"
          style="padding: 6px 10px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 4px; cursor: pointer; font-size: 12px; color: var(--color-text-primary);"
        >↶ 撤销</button>
        <button
          @click="redo"
          style="padding: 6px 10px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 4px; cursor: pointer; font-size: 12px; color: var(--color-text-primary);"
        >↷ 重做</button>
        <button
          @click="triggerImport"
          style="padding: 6px 10px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 4px; cursor: pointer; font-size: 12px; color: var(--color-text-primary);"
        >导入 .madcop</button>
        <button
          @click="exportMadcop"
          style="padding: 6px 10px; background: #7C3AED; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; color: #fff; font-weight: 500;"
        >导出 .madcop</button>
        <button
          @click="saveData"
          style="padding: 6px 10px; background: var(--color-success, #10b981); border: none; border-radius: 4px; cursor: pointer; font-size: 12px; color: #fff; font-weight: 500;"
        >保存</button>
      </div>
      <input
        ref="fileInputRef"
        type="file"
        accept=".madcop,.json"
        style="display: none;"
        @change="importMadcop"
      />
    </div>

    <!-- Center canvas -->
    <div
      style="flex: 1; overflow: auto; padding: 32px; background: #E5E7EB;"
      @click="selectIndex(null)"
    >
      <div
        :style="{
          background: data.root.props.bgColor || '#FFFFFF',
          padding: (data.root.props.padding || 40) + 'px',
          minHeight: '100%',
          maxWidth: '800px',
          width: '100%',
          margin: '0 auto',
          boxShadow: '0 4px 12px rgba(0,0,0,0.1)',
        }"
        @click.stop
      >
        <div
          v-if="data.content.length === 0"
          style="text-align: center; padding: 80px 20px; color: var(--color-text-tertiary); font-size: 14px;"
        >
          从左侧拖入组件开始设计
        </div>
        <div
          v-for="(item, idx) in data.content"
          :key="idx"
          :draggable="true"
          @dragstart.stop="onItemDragStart($event, idx)"
          @dragover="onDragOver"
          @drop.stop="onDrop($event, idx)"
          @click.stop="selectIndex(idx)"
          :class="['design-canvas-item', selectedIndex === idx ? 'design-canvas-item--selected' : '']"
          v-html="renderItem(item)"
        ></div>
      </div>
    </div>

    <!-- Right: property panel -->
    <div
      v-if="selectedItem"
      style="width: 280px; background: var(--color-surface-container-lowest); border-left: 1px solid var(--color-border); padding: 12px; flex-shrink: 0; overflow-y: auto;"
    >
      <div style="font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; color: var(--color-text-tertiary); margin-bottom: 8px;">
        属性: {{ componentRegistry[selectedItem.type]?.label || selectedItem.type }}
      </div>
      <div
        v-for="(field, key) in componentRegistry[selectedItem.type]?.fields || {}"
        :key="key"
        style="margin-bottom: 10px;"
      >
        <label
          style="display: block; font-size: 11px; color: var(--color-text-secondary); margin-bottom: 4px;"
        >{{ field.label }}</label>
        <input
          v-if="field.type === 'text'"
          type="text"
          :value="selectedItem.props[key]"
          @input="(e) => updateItem(selectedIndex, { [key]: (e.target as HTMLInputElement).value })"
          style="width: 100%; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; font-size: 12px; background: var(--color-surface); color: var(--color-text-primary);"
        />
        <textarea
          v-else-if="field.type === 'textarea'"
          :value="selectedItem.props[key]"
          @input="(e) => updateItem(selectedIndex, { [key]: (e.target as HTMLTextAreaElement).value })"
          rows="3"
          style="width: 100%; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; font-size: 12px; resize: vertical; font-family: inherit; background: var(--color-surface); color: var(--color-text-primary);"
        ></textarea>
        <input
          v-else-if="field.type === 'number'"
          type="number"
          :value="selectedItem.props[key]"
          @input="(e) => updateItem(selectedIndex, { [key]: Number((e.target as HTMLInputElement).value) })"
          style="width: 100%; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; font-size: 12px; background: var(--color-surface); color: var(--color-text-primary);"
        />
        <input
          v-else-if="field.type === 'color'"
          type="color"
          :value="selectedItem.props[key] || '#000000'"
          @input="(e) => updateItem(selectedIndex, { [key]: (e.target as HTMLInputElement).value })"
          style="width: 100%; height: 32px; padding: 2px; border: 1px solid var(--color-border); border-radius: 4px; background: var(--color-surface);"
        />
        <select
          v-else-if="field.type === 'select'"
          :value="selectedItem.props[key]"
          @change="(e) => updateItem(selectedIndex, { [key]: (e.target as HTMLSelectElement).value })"
          style="width: 100%; padding: 6px 8px; border: 1px solid var(--color-border); border-radius: 4px; font-size: 12px; background: var(--color-surface); color: var(--color-text-primary);"
        >
          <option v-for="opt in field.options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
        </select>
        <div v-else-if="field.type === 'radio'" style="display: flex; gap: 8px; flex-wrap: wrap;">
          <label
            v-for="opt in field.options"
            :key="opt.value"
            style="display: flex; align-items: center; gap: 4px; font-size: 12px;"
          >
            <input
              type="radio"
              :value="opt.value"
              :checked="selectedItem.props[key] === opt.value"
              @change="updateItem(selectedIndex, { [key]: opt.value })"
            />
            {{ opt.label }}
          </label>
        </div>
      </div>
      <div style="display: flex; gap: 6px; margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--color-border);">
        <button
          @click="duplicateItem(selectedIndex)"
          style="flex: 1; padding: 6px 10px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 4px; cursor: pointer; font-size: 12px; color: var(--color-text-primary);"
        >复制</button>
        <button
          @click="deleteItem(selectedIndex)"
          style="flex: 1; padding: 6px 10px; background: var(--color-surface); border: 1px solid color-mix(in srgb, var(--color-error) 30%, transparent); border-radius: 4px; cursor: pointer; font-size: 12px; color: var(--color-error);"
        >删除</button>
      </div>
    </div>
    <div
      v-else
      style="width: 280px; background: var(--color-surface-container-lowest); border-left: 1px solid var(--color-border); padding: 12px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; color: var(--color-text-tertiary); font-size: 12px;"
    >
      选中组件后编辑属性
    </div>
  </div>
</template>

<style scoped>
.design-palette-item {
  padding: 8px 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 12px;
  color: var(--color-text-primary);
  cursor: grab;
  user-select: none;
  transition: all 0.15s;
}
.design-palette-item:hover {
  background: var(--color-surface-container);
  border-color: #7C3AED;
  transform: translateX(2px);
}
.design-palette-item:active {
  cursor: grabbing;
}

.design-canvas-item {
  position: relative;
  padding: 4px;
  border-radius: 2px;
  cursor: pointer;
  transition: background 0.1s;
}
.design-canvas-item:hover {
  background: rgba(124, 58, 237, 0.05);
}
.design-canvas-item--selected {
  background: rgba(124, 58, 237, 0.08);
  outline: 2px solid #7C3AED;
  outline-offset: 2px;
}
</style>
