<script setup lang="ts">
/**
 * MadCop Design Canvas — product-grade UI editor shell.
 * Drag-drop component tree, artboard sizes, layers, property inspector.
 */

import { ref, computed, onMounted, watch } from 'vue'

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
  icon: string
  group: 'basic' | 'layout' | 'media'
  hint?: string
  render: (props: Record<string, any>, children?: string) => string
}

// ── Component Registry ────────────────────────────────────────────────

const componentRegistry: Record<string, ComponentConfig> = {
  Header: {
    label: '标题',
    icon: 'title',
    group: 'basic',
    hint: '页面主次标题',
    fields: {
      text: { type: 'text', label: '文字' },
      level: {
        type: 'select',
        label: '级别',
        options: [
          { label: 'H1 大标题', value: '1' },
          { label: 'H2 小节', value: '2' },
          { label: 'H3 小标题', value: '3' },
        ],
      },
      color: { type: 'color', label: '颜色' },
      fontSize: { type: 'number', label: '字号' },
    },
    defaultProps: { text: '新标题', level: '2', fontSize: 24, color: '#111827' },
    render: ({ text, level, color, fontSize }) => {
      const tag = `h${level || 2}`
      return `<${tag} style="margin:0 0 8px;color:${color || '#111827'};font-size:${fontSize || 24}px;font-weight:700;line-height:1.25;letter-spacing:-0.02em">${text || '标题'}</${tag}>`
    },
  },
  Paragraph: {
    label: '段落',
    icon: 'notes',
    group: 'basic',
    hint: '说明文案',
    fields: {
      text: { type: 'textarea', label: '文字' },
      color: { type: 'color', label: '颜色' },
      fontSize: { type: 'number', label: '字号' },
      textAlign: {
        type: 'select',
        label: '对齐',
        options: [
          { label: '左', value: 'left' },
          { label: '中', value: 'center' },
          { label: '右', value: 'right' },
        ],
      },
    },
    defaultProps: { text: '这是一段说明文字，可以改成产品卖点或操作提示。', fontSize: 14, textAlign: 'left', color: '#4B5563' },
    render: ({ text, color, fontSize, textAlign }) =>
      `<p style="margin:0 0 12px;font-size:${fontSize || 14}px;line-height:1.65;color:${color || '#4B5563'};text-align:${textAlign || 'left'}">${text || '段落文字'}</p>`,
  },
  Button: {
    label: '按钮',
    icon: 'smart_button',
    group: 'basic',
    hint: '主/次操作',
    fields: {
      text: { type: 'text', label: '文字' },
      variant: {
        type: 'select',
        label: '样式',
        options: [
          { label: '主按钮', value: 'primary' },
          { label: '次按钮', value: 'secondary' },
          { label: '幽灵', value: 'ghost' },
        ],
      },
      color: { type: 'color', label: '主色' },
      width: { type: 'number', label: '宽度' },
      radius: { type: 'number', label: '圆角' },
    },
    defaultProps: { text: '立即开始', variant: 'primary', color: '#7C3AED', radius: 10 },
    render: ({ text, variant, color, width, radius }) => {
      const v = variant || 'primary'
      const brand = color || '#7C3AED'
      let bg = brand
      let fg = '#FFFFFF'
      let border = 'none'
      if (v === 'secondary') {
        bg = '#F3F4F6'
        fg = '#374151'
      } else if (v === 'ghost') {
        bg = 'transparent'
        fg = brand
        border = `1px solid ${brand}`
      }
      const w = width ? `width:${width}px;` : ''
      return `<button style="${w}padding:11px 22px;border-radius:${radius ?? 10}px;border:${border};cursor:pointer;font-weight:600;font-size:14px;background:${bg};color:${fg};box-shadow:${v === 'primary' ? '0 1px 2px rgba(0,0,0,.06)' : 'none'}">${text || '按钮'}</button>`
    },
  },
  Image: {
    label: '图片',
    icon: 'image',
    group: 'media',
    hint: '占位或远程图',
    fields: {
      src: { type: 'text', label: '图片地址' },
      alt: { type: 'text', label: '替代文字' },
      width: { type: 'number', label: '宽度' },
      height: { type: 'number', label: '高度' },
      borderRadius: { type: 'number', label: '圆角' },
    },
    defaultProps: { src: '', alt: '', width: 320, height: 180, borderRadius: 12 },
    render: ({ src, alt, width, height, borderRadius }) => {
      const w = width || 320
      const h = height || 180
      const br = borderRadius ?? 12
      const realSrc =
        src && String(src).trim()
          ? src
          : `data:image/svg+xml;utf8,${encodeURIComponent(`<svg xmlns='http://www.w3.org/2000/svg' width='${w}' height='${h}'><defs><linearGradient id='g' x1='0' y1='0' x2='1' y2='1'><stop stop-color='#F3F4F6'/><stop offset='1' stop-color='#E5E7EB'/></linearGradient></defs><rect width='${w}' height='${h}' fill='url(#g)' rx='${br}'/><text x='50%' y='50%' font-family='system-ui,sans-serif' font-size='13' fill='#9CA3AF' text-anchor='middle' dominant-baseline='middle'>${w}×${h}</text></svg>`)}`
      return `<img src="${realSrc}" alt="${alt || ''}" style="max-width:100%;width:${w}px;height:${h}px;object-fit:cover;border-radius:${br}px;display:block" />`
    },
  },
  Input: {
    label: '输入框',
    icon: 'edit_square',
    group: 'basic',
    hint: '表单字段',
    fields: {
      placeholder: { type: 'text', label: '占位文字' },
      width: { type: 'number', label: '宽度' },
      type: {
        type: 'select',
        label: '类型',
        options: [
          { label: '文本', value: 'text' },
          { label: '密码', value: 'password' },
          { label: '邮箱', value: 'email' },
        ],
      },
    },
    defaultProps: { placeholder: '请输入…', width: 320, type: 'text' },
    render: ({ placeholder, width, type }) =>
      `<input type="${type || 'text'}" placeholder="${placeholder || ''}" style="box-sizing:border-box;padding:11px 14px;border:1px solid #E5E7EB;border-radius:10px;font-size:14px;width:${width || 320}px;outline:none;background:#fff;color:#111827" />`,
  },
  Card: {
    label: '卡片',
    icon: 'crop_landscape',
    group: 'layout',
    hint: '内容容器',
    fields: {
      padding: { type: 'number', label: '内边距' },
      bgColor: { type: 'color', label: '背景色' },
      radius: { type: 'number', label: '圆角' },
      shadow: {
        type: 'select',
        label: '阴影',
        options: [
          { label: '无', value: 'none' },
          { label: '轻', value: 'sm' },
          { label: '中', value: 'md' },
          { label: '重', value: 'lg' },
        ],
      },
    },
    defaultProps: { padding: 24, bgColor: '#FFFFFF', radius: 16, shadow: 'md' },
    isContainer: true,
    render: ({ padding, bgColor, radius, shadow }, children = '') => {
      const shadows: Record<string, string> = {
        none: 'none',
        sm: '0 1px 2px rgba(0,0,0,0.05)',
        md: '0 4px 16px -4px rgba(0,0,0,0.08)',
        lg: '0 12px 32px -8px rgba(0,0,0,0.12)',
      }
      return `<div style="background:${bgColor || '#FFFFFF'};border:1px solid #E5E7EB;border-radius:${radius ?? 16}px;padding:${padding ?? 24}px;box-shadow:${shadows[shadow || 'md'] || shadows.md}">${children || '<span style="color:#9CA3AF;font-size:12px">卡片内容…</span>'}</div>`
    },
  },
  Flex: {
    label: '弹性布局',
    icon: 'view_week',
    group: 'layout',
    hint: '横/纵向排列',
    fields: {
      direction: {
        type: 'select',
        label: '方向',
        options: [
          { label: '横向', value: 'row' },
          { label: '纵向', value: 'column' },
        ],
      },
      gap: { type: 'number', label: '间距' },
      justify: {
        type: 'select',
        label: '主轴',
        options: [
          { label: '起始', value: 'start' },
          { label: '居中', value: 'center' },
          { label: '末尾', value: 'end' },
          { label: '两端', value: 'between' },
          { label: '环绕', value: 'around' },
        ],
      },
      align: {
        type: 'select',
        label: '交叉轴',
        options: [
          { label: '起始', value: 'start' },
          { label: '居中', value: 'center' },
          { label: '末尾', value: 'end' },
          { label: '拉伸', value: 'stretch' },
        ],
      },
    },
    defaultProps: { direction: 'column', gap: 16, justify: 'start', align: 'stretch' },
    isContainer: true,
    render: ({ direction, gap, justify, align }, children = '') => {
      const jc: Record<string, string> = {
        start: 'flex-start',
        center: 'center',
        end: 'flex-end',
        between: 'space-between',
        around: 'space-around',
      }
      const ac: Record<string, string> = {
        start: 'flex-start',
        center: 'center',
        end: 'flex-end',
        stretch: 'stretch',
      }
      return `<div style="display:flex;flex-direction:${direction || 'column'};gap:${gap ?? 16}px;justify-content:${jc[justify || 'start']};align-items:${ac[align || 'stretch']}">${children}</div>`
    },
  },
  Grid: {
    label: '网格',
    icon: 'grid_view',
    group: 'layout',
    hint: '多列卡片',
    fields: {
      columns: { type: 'number', label: '列数' },
      gap: { type: 'number', label: '间距' },
    },
    defaultProps: { columns: 2, gap: 16 },
    isContainer: true,
    render: ({ columns, gap }, children = '') =>
      `<div style="display:grid;grid-template-columns:repeat(${columns || 2},1fr);gap:${gap ?? 16}px">${children}</div>`,
  },
  Section: {
    label: '区块',
    icon: 'view_agenda',
    group: 'layout',
    hint: '整页分区',
    fields: {
      bgColor: { type: 'color', label: '背景色' },
      padding: { type: 'number', label: '内边距' },
      maxWidth: { type: 'number', label: '最大宽度' },
    },
    defaultProps: { bgColor: '#F9FAFB', padding: 40, maxWidth: 960 },
    isContainer: true,
    render: ({ bgColor, padding, maxWidth }, children = '') => {
      const mw = maxWidth ? `max-width:${maxWidth}px;margin:0 auto;` : ''
      return `<section style="${mw}padding:${padding ?? 40}px;background:${bgColor || '#F9FAFB'};border-radius:0">${children}</section>`
    },
  },
  Divider: {
    label: '分割线',
    icon: 'horizontal_rule',
    group: 'basic',
    fields: {
      color: { type: 'color', label: '颜色' },
      thickness: { type: 'number', label: '粗细' },
      margin: { type: 'number', label: '上下间距' },
    },
    defaultProps: { color: '#E5E7EB', thickness: 1, margin: 16 },
    render: ({ color, thickness, margin }) =>
      `<hr style="margin:${margin ?? 16}px 0;border:none;border-top:${thickness || 1}px solid ${color || '#E5E7EB'}" />`,
  },
  Space: {
    label: '间距',
    icon: 'expand',
    group: 'layout',
    hint: '垂直空白',
    fields: {
      height: { type: 'number', label: '高度' },
    },
    defaultProps: { height: 24 },
    render: ({ height }) =>
      `<div style="height:${height ?? 24}px;border-left:2px dashed transparent" title="间距"></div>`,
  },
}

const GROUP_META: { id: ComponentConfig['group']; label: string }[] = [
  { id: 'basic', label: '基础' },
  { id: 'layout', label: '布局' },
  { id: 'media', label: '媒体' },
]

const DEVICE_PRESETS = [
  { id: 'mobile', label: '手机', width: 390, icon: 'smartphone' },
  { id: 'tablet', label: '平板', width: 768, icon: 'tablet' },
  { id: 'desktop', label: '桌面', width: 960, icon: 'desktop_windows' },
] as const

function emptyData(): DesignData {
  return {
    root: { props: { bgColor: '#FFFFFF', padding: 40 } },
    content: [],
  }
}

const props = defineProps<{
  initialData: DesignData
}>()

const emit = defineEmits<{
  save: [data: DesignData]
}>()

const data = ref<DesignData>(JSON.parse(JSON.stringify(props.initialData)) || emptyData())
const selectedIndex = ref<number | null>(null)
const draggingIndex = ref<number | null>(null)
const draggingType = ref<string | null>(null)
const fileInputRef = ref<HTMLInputElement | null>(null)
const deviceId = ref<(typeof DEVICE_PRESETS)[number]['id']>('desktop')
const zoom = ref(100)
const leftTab = ref<'components' | 'layers'>('components')

const history = ref<DesignData[]>([])
const historyIndex = ref(-1)

watch(
  () => data.value,
  (val) => {
    history.value.push(JSON.parse(JSON.stringify(val)))
    historyIndex.value = history.value.length - 1
  },
  { deep: true },
)

onMounted(() => {
  if (props.initialData) {
    data.value = JSON.parse(JSON.stringify(props.initialData))
  }
  history.value = [JSON.parse(JSON.stringify(data.value))]
  historyIndex.value = 0
})

const selectedItem = computed<DesignItem | null>(() => {
  if (selectedIndex.value === null) return null
  return data.value.content[selectedIndex.value] || null
})

const artboardWidth = computed(() => {
  const p = DEVICE_PRESETS.find((d) => d.id === deviceId.value)
  return p?.width ?? 960
})

const paletteByGroup = computed(() =>
  GROUP_META.map((g) => ({
    ...g,
    items: Object.entries(componentRegistry)
      .filter(([, cfg]) => cfg.group === g.id)
      .map(([type, cfg]) => ({ type, ...cfg })),
  })),
)

function selectIndex(idx: number | null) {
  selectedIndex.value = idx
}

function addItem(type: string, atIndex?: number) {
  const cfg = componentRegistry[type]
  if (!cfg) return
  const newItem: DesignItem = { type, props: { ...cfg.defaultProps } }
  const items = data.value.content
  if (atIndex === undefined || atIndex >= items.length) {
    items.push(newItem)
    selectIndex(items.length - 1)
  } else {
    items.splice(atIndex, 0, newItem)
    selectIndex(atIndex)
  }
}

function updateItem(idx: number | null, updates: Partial<DesignItem['props']>) {
  if (idx === null) return
  const item = data.value.content[idx]
  if (!item) return
  item.props = { ...item.props, ...updates }
}

function updateRoot(key: string, value: any) {
  if (!data.value.root.props) data.value.root.props = {}
  data.value.root.props[key] = value
}

function deleteItem(idx: number | null) {
  if (idx === null) return
  data.value.content.splice(idx, 1)
  if (selectedIndex.value === idx) selectIndex(null)
  else if (selectedIndex.value !== null && selectedIndex.value > idx) {
    selectedIndex.value--
  }
}

function duplicateItem(idx: number | null) {
  if (idx === null) return
  const item = data.value.content[idx]
  if (!item) return
  const copy = JSON.parse(JSON.stringify(item))
  data.value.content.splice(idx + 1, 0, copy)
  selectIndex(idx + 1)
}

function moveItem(idx: number, dir: -1 | 1) {
  const to = idx + dir
  if (to < 0 || to >= data.value.content.length) return
  const arr = data.value.content
  const [item] = arr.splice(idx, 1)
  arr.splice(to, 0, item)
  selectIndex(to)
}

function onDragStart(e: DragEvent, type: string) {
  draggingType.value = type
  draggingIndex.value = null
  e.dataTransfer?.setData('text/plain', type)
  e.dataTransfer!.effectAllowed = 'copy'
}

function onItemDragStart(e: DragEvent, idx: number) {
  draggingIndex.value = idx
  draggingType.value = null
  e.dataTransfer?.setData('text/plain', String(idx))
  e.dataTransfer!.effectAllowed = 'move'
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
    const fromIdx = draggingIndex.value
    let toIdx = atIndex
    if (toIdx === undefined) {
      data.value.content.push(data.value.content.splice(fromIdx, 1)[0])
      selectIndex(data.value.content.length - 1)
    } else if (fromIdx !== toIdx) {
      const item = data.value.content.splice(fromIdx, 1)[0]
      data.value.content.splice(toIdx, 0, item)
      selectIndex(toIdx)
    }
  }
  draggingType.value = null
  draggingIndex.value = null
}

function undo() {
  if (historyIndex.value > 0) {
    historyIndex.value--
    data.value = JSON.parse(JSON.stringify(history.value[historyIndex.value]))
    selectedIndex.value = null
  }
}

function redo() {
  if (historyIndex.value < history.value.length - 1) {
    historyIndex.value++
    data.value = JSON.parse(JSON.stringify(history.value[historyIndex.value]))
    selectedIndex.value = null
  }
}

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
  reader.onload = () => {
    try {
      const parsed = JSON.parse(String(reader.result || ''))
      if (parsed && Array.isArray(parsed.content)) {
        data.value = parsed
        selectedIndex.value = null
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

function renderItem(item: DesignItem): string {
  const cfg = componentRegistry[item.type]
  if (!cfg) return ''
  const childHtml = item.children ? item.children.map(renderItem).join('') : ''
  return cfg.render(item.props, childHtml)
}

function itemLabel(item: DesignItem, idx: number): string {
  const cfg = componentRegistry[item.type]
  const t = item.props?.text || item.props?.placeholder || ''
  const short = t ? String(t).slice(0, 12) : ''
  return short ? `${cfg?.label || item.type} · ${short}` : `${cfg?.label || item.type} #${idx + 1}`
}

function zoomIn() {
  zoom.value = Math.min(150, zoom.value + 10)
}
function zoomOut() {
  zoom.value = Math.max(50, zoom.value - 10)
}
function zoomReset() {
  zoom.value = 100
}
</script>

<template>
  <div class="dc">
    <!-- Left rail -->
    <aside class="dc-rail">
      <div class="dc-rail__tabs">
        <button
          type="button"
          :class="['dc-rail__tab', { 'dc-rail__tab--on': leftTab === 'components' }]"
          @click="leftTab = 'components'"
        >
          组件
        </button>
        <button
          type="button"
          :class="['dc-rail__tab', { 'dc-rail__tab--on': leftTab === 'layers' }]"
          @click="leftTab = 'layers'"
        >
          图层
        </button>
      </div>

      <div v-if="leftTab === 'components'" class="dc-rail__scroll">
        <p class="dc-rail__hint">拖到画板，或点击添加</p>
        <section v-for="g in paletteByGroup" :key="g.id" class="dc-group">
          <h4 class="dc-group__title">{{ g.label }}</h4>
          <div class="dc-palette">
            <button
              v-for="item in g.items"
              :key="item.type"
              type="button"
              class="dc-chip"
              draggable="true"
              :title="item.hint || item.label"
              @dragstart="onDragStart($event, item.type)"
              @click="addItem(item.type)"
            >
              <span class="material-symbols-outlined dc-chip__icon">{{ item.icon }}</span>
              <span class="dc-chip__label">{{ item.label }}</span>
            </button>
          </div>
        </section>
      </div>

      <div v-else class="dc-rail__scroll">
        <p class="dc-rail__hint">点击选中 · 拖拽排序</p>
        <div v-if="data.content.length === 0" class="dc-layers-empty">暂无图层</div>
        <div class="dc-layers">
          <button
            v-for="(item, idx) in data.content"
            :key="idx"
            type="button"
            :class="['dc-layer', { 'dc-layer--on': selectedIndex === idx }]"
            draggable="true"
            @click="selectIndex(idx)"
            @dragstart="onItemDragStart($event, idx)"
            @dragover="onDragOver"
            @drop.stop="onDrop($event, idx)"
          >
            <span class="material-symbols-outlined dc-layer__icon">
              {{ componentRegistry[item.type]?.icon || 'widgets' }}
            </span>
            <span class="dc-layer__name">{{ itemLabel(item, idx) }}</span>
          </button>
        </div>
      </div>

      <div class="dc-rail__foot">
        <button type="button" class="dc-tool" title="撤销" :disabled="historyIndex <= 0" @click="undo">
          <span class="material-symbols-outlined">undo</span>
        </button>
        <button
          type="button"
          class="dc-tool"
          title="重做"
          :disabled="historyIndex >= history.length - 1"
          @click="redo"
        >
          <span class="material-symbols-outlined">redo</span>
        </button>
        <button type="button" class="dc-tool" title="导入" @click="triggerImport">
          <span class="material-symbols-outlined">upload</span>
        </button>
        <button type="button" class="dc-tool" title="导出 .madcop" @click="exportMadcop">
          <span class="material-symbols-outlined">download</span>
        </button>
        <button type="button" class="dc-tool dc-tool--primary" title="保存到项目" @click="saveData">
          <span class="material-symbols-outlined">save</span>
        </button>
        <input
          ref="fileInputRef"
          type="file"
          accept=".madcop,.json"
          class="dc-hidden"
          @change="importMadcop"
        />
      </div>
    </aside>

    <!-- Center stage -->
    <section class="dc-stage">
      <div class="dc-stage__bar">
        <div class="dc-devices">
          <button
            v-for="d in DEVICE_PRESETS"
            :key="d.id"
            type="button"
            :class="['dc-device', { 'dc-device--on': deviceId === d.id }]"
            :title="d.label"
            @click="deviceId = d.id"
          >
            <span class="material-symbols-outlined">{{ d.icon }}</span>
            <span class="dc-device__label">{{ d.label }}</span>
          </button>
        </div>
        <div class="dc-stage__meta">
          <span class="dc-meta-pill">{{ artboardWidth }}px</span>
          <span class="dc-meta-pill">{{ data.content.length }} 组件</span>
        </div>
        <div class="dc-zoom">
          <button type="button" class="dc-tool" @click="zoomOut">−</button>
          <button type="button" class="dc-zoom__val" @click="zoomReset">{{ zoom }}%</button>
          <button type="button" class="dc-tool" @click="zoomIn">+</button>
        </div>
      </div>

      <div
        class="dc-stage__board"
        @click="selectIndex(null)"
        @dragover="onDragOver"
        @drop="onDrop($event)"
      >
        <div
          class="dc-artboard-wrap"
          :style="{ transform: `scale(${zoom / 100})`, width: artboardWidth + 'px' }"
        >
          <div class="dc-artboard-label">
            {{ DEVICE_PRESETS.find((d) => d.id === deviceId)?.label }} · {{ artboardWidth }}
          </div>
          <div
            class="dc-artboard"
            :style="{
              background: data.root.props.bgColor || '#FFFFFF',
              padding: (data.root.props.padding ?? 40) + 'px',
              width: artboardWidth + 'px',
            }"
            @click.stop
          >
            <div v-if="data.content.length === 0" class="dc-empty">
              <div class="dc-empty__icon">
                <span class="material-symbols-outlined">design_services</span>
              </div>
              <h3 class="dc-empty__title">从左侧添加组件</h3>
              <p class="dc-empty__sub">或用上方 AI 生成一页完整 UI，再在这里微调</p>
              <div class="dc-empty__actions">
                <button type="button" class="dc-empty__btn" @click="addItem('Header')">+ 标题</button>
                <button type="button" class="dc-empty__btn" @click="addItem('Button')">+ 按钮</button>
                <button type="button" class="dc-empty__btn" @click="addItem('Card')">+ 卡片</button>
              </div>
            </div>
            <div
              v-for="(item, idx) in data.content"
              :key="idx"
              :draggable="true"
              class="dc-node"
              :class="{ 'dc-node--selected': selectedIndex === idx }"
              @dragstart.stop="onItemDragStart($event, idx)"
              @dragover="onDragOver"
              @drop.stop="onDrop($event, idx)"
              @click.stop="selectIndex(idx)"
              v-html="renderItem(item)"
            />
          </div>
        </div>
      </div>
    </section>

    <!-- Right inspector -->
    <aside class="dc-inspector">
      <template v-if="selectedItem && selectedIndex !== null">
        <header class="dc-inspector__head">
          <div>
            <div class="dc-inspector__eyebrow">组件</div>
            <div class="dc-inspector__title">
              <span class="material-symbols-outlined">{{
                componentRegistry[selectedItem.type]?.icon || 'widgets'
              }}</span>
              {{ componentRegistry[selectedItem.type]?.label || selectedItem.type }}
            </div>
          </div>
          <div class="dc-inspector__ops">
            <button type="button" class="dc-tool" title="上移" @click="moveItem(selectedIndex, -1)">
              <span class="material-symbols-outlined">arrow_upward</span>
            </button>
            <button type="button" class="dc-tool" title="下移" @click="moveItem(selectedIndex, 1)">
              <span class="material-symbols-outlined">arrow_downward</span>
            </button>
          </div>
        </header>

        <div class="dc-fields">
          <div
            v-for="(field, key) in componentRegistry[selectedItem.type]?.fields || {}"
            :key="key"
            class="dc-field"
          >
            <label class="dc-field__label">{{ field.label }}</label>
            <input
              v-if="field.type === 'text'"
              class="dc-field__ctrl"
              type="text"
              :value="selectedItem.props[key]"
              @input="updateItem(selectedIndex, { [key]: ($event.target as HTMLInputElement).value })"
            />
            <textarea
              v-else-if="field.type === 'textarea'"
              class="dc-field__ctrl dc-field__ctrl--area"
              rows="3"
              :value="selectedItem.props[key]"
              @input="updateItem(selectedIndex, { [key]: ($event.target as HTMLTextAreaElement).value })"
            />
            <input
              v-else-if="field.type === 'number'"
              class="dc-field__ctrl"
              type="number"
              :value="selectedItem.props[key]"
              @input="updateItem(selectedIndex, { [key]: Number(($event.target as HTMLInputElement).value) })"
            />
            <div v-else-if="field.type === 'color'" class="dc-color">
              <input
                type="color"
                class="dc-color__swatch"
                :value="selectedItem.props[key] || '#000000'"
                @input="updateItem(selectedIndex, { [key]: ($event.target as HTMLInputElement).value })"
              />
              <input
                class="dc-field__ctrl"
                type="text"
                :value="selectedItem.props[key] || ''"
                @input="updateItem(selectedIndex, { [key]: ($event.target as HTMLInputElement).value })"
              />
            </div>
            <select
              v-else-if="field.type === 'select'"
              class="dc-field__ctrl"
              :value="selectedItem.props[key]"
              @change="updateItem(selectedIndex, { [key]: ($event.target as HTMLSelectElement).value })"
            >
              <option v-for="opt in field.options" :key="opt.value" :value="opt.value">
                {{ opt.label }}
              </option>
            </select>
          </div>
        </div>

        <div class="dc-inspector__actions">
          <button type="button" class="dc-btn" @click="duplicateItem(selectedIndex)">复制</button>
          <button type="button" class="dc-btn dc-btn--danger" @click="deleteItem(selectedIndex)">
            删除
          </button>
        </div>
      </template>

      <template v-else>
        <header class="dc-inspector__head">
          <div>
            <div class="dc-inspector__eyebrow">画板</div>
            <div class="dc-inspector__title">
              <span class="material-symbols-outlined">web_asset</span>
              页面属性
            </div>
          </div>
        </header>
        <div class="dc-fields">
          <div class="dc-field">
            <label class="dc-field__label">背景色</label>
            <div class="dc-color">
              <input
                type="color"
                class="dc-color__swatch"
                :value="data.root.props.bgColor || '#FFFFFF'"
                @input="updateRoot('bgColor', ($event.target as HTMLInputElement).value)"
              />
              <input
                class="dc-field__ctrl"
                type="text"
                :value="data.root.props.bgColor || '#FFFFFF'"
                @input="updateRoot('bgColor', ($event.target as HTMLInputElement).value)"
              />
            </div>
          </div>
          <div class="dc-field">
            <label class="dc-field__label">内边距</label>
            <input
              class="dc-field__ctrl"
              type="number"
              :value="data.root.props.padding ?? 40"
              @input="updateRoot('padding', Number(($event.target as HTMLInputElement).value))"
            />
          </div>
        </div>
        <p class="dc-inspector__tip">
          选中画板上的组件可编辑属性。未选中时调整整页背景与边距。
        </p>
      </template>
    </aside>
  </div>
</template>

<style scoped>
.dc {
  display: flex;
  height: 100%;
  width: 100%;
  min-height: 0;
  background: var(--color-surface-container-low, #f3f4f6);
  color: var(--color-text-primary);
}

/* ── Left rail ── */
.dc-rail {
  width: 220px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--color-border);
  background: var(--color-surface-container-lowest, #fff);
}
.dc-rail__tabs {
  display: flex;
  gap: 4px;
  padding: 10px 10px 0;
  flex-shrink: 0;
}
.dc-rail__tab {
  flex: 1;
  border: none;
  background: transparent;
  padding: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  border-radius: 8px;
  cursor: pointer;
}
.dc-rail__tab--on {
  background: color-mix(in srgb, var(--color-brand, #7c3aed) 12%, transparent);
  color: var(--color-brand, #7c3aed);
}
.dc-rail__scroll {
  flex: 1;
  overflow-y: auto;
  padding: 8px 10px 12px;
  min-height: 0;
}
.dc-rail__hint {
  margin: 4px 0 12px;
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.dc-group + .dc-group {
  margin-top: 14px;
}
.dc-group__title {
  margin: 0 0 8px;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
}
.dc-palette {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.dc-chip {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  padding: 10px 8px;
  border: 1px solid var(--color-border);
  border-radius: 10px;
  background: var(--color-surface, #fff);
  cursor: grab;
  text-align: left;
  transition: border-color 0.12s, box-shadow 0.12s, transform 0.12s;
}
.dc-chip:hover {
  border-color: color-mix(in srgb, var(--color-brand, #7c3aed) 45%, var(--color-border));
  box-shadow: 0 2px 8px rgba(124, 58, 237, 0.08);
  transform: translateY(-1px);
}
.dc-chip:active {
  cursor: grabbing;
}
.dc-chip__icon {
  font-size: 18px;
  color: var(--color-brand, #7c3aed);
}
.dc-chip__label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.dc-layers {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.dc-layers-empty {
  font-size: 12px;
  color: var(--color-text-tertiary);
  padding: 24px 8px;
  text-align: center;
}
.dc-layer {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.dc-layer:hover {
  background: var(--color-surface-hover, #f9fafb);
}
.dc-layer--on {
  background: color-mix(in srgb, var(--color-brand, #7c3aed) 10%, transparent);
  border-color: color-mix(in srgb, var(--color-brand, #7c3aed) 22%, transparent);
  color: var(--color-text-primary);
  font-weight: 600;
}
.dc-layer__icon {
  font-size: 16px;
  color: var(--color-text-tertiary);
}
.dc-layer--on .dc-layer__icon {
  color: var(--color-brand, #7c3aed);
}
.dc-layer__name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.dc-rail__foot {
  display: flex;
  gap: 4px;
  padding: 10px;
  border-top: 1px solid var(--color-border);
  flex-shrink: 0;
}

/* ── Stage ── */
.dc-stage {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.dc-stage__bar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-container-lowest, #fff);
  flex-shrink: 0;
}
.dc-devices {
  display: flex;
  gap: 4px;
  padding: 3px;
  background: var(--color-surface-container-low, #f3f4f6);
  border-radius: 10px;
}
.dc-device {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: none;
  background: transparent;
  padding: 6px 10px;
  border-radius: 8px;
  cursor: pointer;
  color: var(--color-text-secondary);
  font-size: 12px;
}
.dc-device .material-symbols-outlined {
  font-size: 16px;
}
.dc-device--on {
  background: var(--color-surface, #fff);
  color: var(--color-text-primary);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}
.dc-device__label {
  display: none;
}
@media (min-width: 1100px) {
  .dc-device__label {
    display: inline;
  }
}
.dc-stage__meta {
  display: flex;
  gap: 6px;
  flex: 1;
}
.dc-meta-pill {
  font-size: 11px;
  color: var(--color-text-tertiary);
  padding: 4px 8px;
  border-radius: 999px;
  background: var(--color-surface-container-low, #f3f4f6);
}
.dc-zoom {
  display: flex;
  align-items: center;
  gap: 2px;
}
.dc-zoom__val {
  border: none;
  background: transparent;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  min-width: 44px;
  cursor: pointer;
  color: var(--color-text-secondary);
}
.dc-stage__board {
  flex: 1;
  overflow: auto;
  padding: 36px 28px 48px;
  background:
    radial-gradient(circle at 1px 1px, color-mix(in srgb, var(--color-border) 70%, transparent) 1px, transparent 0)
      0 0 / 16px 16px,
    var(--color-surface-container-low, #eef0f3);
  min-height: 0;
}
.dc-artboard-wrap {
  margin: 0 auto;
  transform-origin: top center;
  transition: transform 0.15s ease;
}
.dc-artboard-label {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-bottom: 8px;
  font-weight: 500;
}
.dc-artboard {
  min-height: 520px;
  border-radius: 12px;
  box-shadow:
    0 0 0 1px rgba(0, 0, 0, 0.06),
    0 16px 40px -12px rgba(15, 23, 42, 0.18);
  overflow: hidden;
}
.dc-empty {
  text-align: center;
  padding: 72px 24px;
}
.dc-empty__icon {
  width: 56px;
  height: 56px;
  margin: 0 auto 12px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: color-mix(in srgb, var(--color-brand, #7c3aed) 12%, transparent);
  color: var(--color-brand, #7c3aed);
}
.dc-empty__icon .material-symbols-outlined {
  font-size: 28px;
}
.dc-empty__title {
  margin: 0 0 6px;
  font-size: 15px;
  font-weight: 600;
}
.dc-empty__sub {
  margin: 0 0 16px;
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.dc-empty__actions {
  display: flex;
  gap: 8px;
  justify-content: center;
  flex-wrap: wrap;
}
.dc-empty__btn {
  border: 1px solid var(--color-border);
  background: var(--color-surface, #fff);
  border-radius: 999px;
  padding: 6px 12px;
  font-size: 12px;
  cursor: pointer;
  color: var(--color-text-secondary);
}
.dc-empty__btn:hover {
  border-color: var(--color-brand, #7c3aed);
  color: var(--color-brand, #7c3aed);
}
.dc-node {
  position: relative;
  margin: 2px 0;
  padding: 6px;
  border-radius: 8px;
  cursor: pointer;
  outline: 1px solid transparent;
  transition: outline-color 0.1s, background 0.1s;
}
.dc-node:hover {
  outline-color: color-mix(in srgb, var(--color-brand, #7c3aed) 35%, transparent);
  background: color-mix(in srgb, var(--color-brand, #7c3aed) 4%, transparent);
}
.dc-node--selected {
  outline: 2px solid var(--color-brand, #7c3aed);
  outline-offset: 0;
  background: color-mix(in srgb, var(--color-brand, #7c3aed) 6%, transparent);
}

/* ── Inspector ── */
.dc-inspector {
  width: 280px;
  flex-shrink: 0;
  border-left: 1px solid var(--color-border);
  background: var(--color-surface-container-lowest, #fff);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
  min-height: 0;
}
.dc-inspector__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 14px 10px;
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}
.dc-inspector__eyebrow {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
  margin-bottom: 4px;
}
.dc-inspector__title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
}
.dc-inspector__title .material-symbols-outlined {
  font-size: 18px;
  color: var(--color-brand, #7c3aed);
}
.dc-inspector__ops {
  display: flex;
  gap: 2px;
}
.dc-fields {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.dc-field__label {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 6px;
}
.dc-field__ctrl {
  width: 100%;
  box-sizing: border-box;
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  font-size: 12px;
  background: var(--color-surface, #fff);
  color: var(--color-text-primary);
  outline: none;
}
.dc-field__ctrl:focus {
  border-color: var(--color-brand, #7c3aed);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--color-brand, #7c3aed) 15%, transparent);
}
.dc-field__ctrl--area {
  resize: vertical;
  font-family: inherit;
  line-height: 1.45;
}
.dc-color {
  display: flex;
  gap: 8px;
  align-items: center;
}
.dc-color__swatch {
  width: 36px;
  height: 34px;
  padding: 2px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface);
  cursor: pointer;
  flex-shrink: 0;
}
.dc-inspector__actions {
  display: flex;
  gap: 8px;
  padding: 0 14px 16px;
  margin-top: auto;
}
.dc-inspector__tip {
  margin: 0 14px 16px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-tertiary);
}

.dc-tool {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-surface, #fff);
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0;
}
.dc-tool .material-symbols-outlined {
  font-size: 16px;
}
.dc-tool:hover:not(:disabled) {
  border-color: var(--color-brand, #7c3aed);
  color: var(--color-brand, #7c3aed);
}
.dc-tool:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.dc-tool--primary {
  background: var(--color-brand, #7c3aed);
  border-color: transparent;
  color: #fff;
}
.dc-tool--primary:hover:not(:disabled) {
  color: #fff;
  opacity: 0.92;
}
.dc-btn {
  flex: 1;
  padding: 8px 10px;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  color: var(--color-text-primary);
}
.dc-btn--danger {
  color: var(--color-error, #ef4444);
  border-color: color-mix(in srgb, var(--color-error, #ef4444) 30%, transparent);
}
.dc-hidden {
  display: none;
}
</style>
