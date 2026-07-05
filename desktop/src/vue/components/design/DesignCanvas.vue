<!--
  v3.0 — DesignCanvas (Vue 3 SFC)
  Full translation of src/design/DesignCanvas.tsx (640 lines).
  Native HTML5 canvas-based design tool, zero external deps.
-->
<script setup lang="ts">
import {
  ref,
  computed,
  onMounted,
  onBeforeUnmount,
  watch,
  type Ref,
} from 'vue'
import FieldEditor from './FieldEditor.vue'
import RenderedItem from './RenderedItem.vue'

// ── Types ─────────────────────────────────────────────────────────────

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
}

// ── Component Registry ────────────────────────────────────────────────

const shadowMap: Record<string, string> = {
  sm: '0 1px 2px rgba(0,0,0,0.05)',
  md: '0 4px 6px rgba(0,0,0,0.1)',
  lg: '0 10px 15px rgba(0,0,0,0.15)',
}

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
  },
  Button: {
    label: '按钮',
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
    fields: {
      columns: { type: 'number', label: '列数' },
      gap: { type: 'number', label: '间距' },
    },
    defaultProps: { columns: 2, gap: 12 },
  },
  Section: {
    label: '区块',
    isContainer: true,
    fields: {
      bgColor: { type: 'color', label: '背景色' },
      padding: { type: 'number', label: '内边距' },
      maxWidth: { type: 'number', label: '最大宽度' },
    },
    defaultProps: { padding: 24, maxWidth: 720 },
  },
  Divider: {
    label: '分割线',
    fields: {
      color: { type: 'color', label: '颜色' },
      thickness: { type: 'number', label: '粗细' },
      margin: { type: 'number', label: '外边距' },
    },
    defaultProps: { color: '#E5E7EB', thickness: 1, margin: 16 },
  },
  Space: {
    label: '间距',
    fields: { height: { type: 'number', label: '高度' } },
    defaultProps: { height: 20 },
  },
}

// ── Path utilities (address items in the tree) ────────────────────────

type Path = (number)[] // e.g. [0, 2] = content[0].children[2]

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
  if (to.length === 1) {
    result.splice(to[0], 0, item)
  } else {
    result = addItemToTree(result, to.length === 0 ? null : to.slice(0, -1), item)
  }
  return result
}

// ── Layer Tree ────────────────────────────────────────────────────────

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

// ── Props / Emits ──────────────────────────────────────────────────────

const props = defineProps<{
  initialData?: DesignData
}>()

const emit = defineEmits<{
  (e: 'save', data: DesignData): void
}>()

// ── State ──────────────────────────────────────────────────────────────

const VIEWPORTS = [
  { label: '桌面', width: 0, icon: '🖥' },
  { label: '平板', width: 600, icon: '📱' },
  { label: '手机', width: 375, icon: '📱' },
]

const data = ref<DesignData>(props.initialData || { root: { props: { bgColor: '#FFFFFF', padding: 40 } }, content: [] })
const selectedPath = ref<Path | null>(null)
const viewport = ref(0)
const clipboard = ref<DesignItem | null>(null)
const showLayers = ref(true)
const contextMenu = ref<{ x: number; y: number; path: Path } | null>(null)

// Drag state
const dragPath = ref<Path | null>(null)
const dragOverPath = ref<Path | null>(null)

// ── History ────────────────────────────────────────────────────────────

const history = ref<DesignData[]>([])
const historyIdx = ref(-1)
const skipHistory = ref(false)

function commitHistory(newData: DesignData) {
  if (skipHistory.value) { skipHistory.value = false; data.value = newData; return }
  history.value = history.value.slice(0, historyIdx.value + 1)
  history.value.push(deepClone(newData))
  historyIdx.value = history.value.length - 1
  if (history.value.length > 50) { history.value.shift(); historyIdx.value-- }
  data.value = newData
}

function undo() {
  if (historyIdx.value > 0) {
    historyIdx.value--
    skipHistory.value = true
    data.value = deepClone(history.value[historyIdx.value])
  }
}

function redo() {
  if (historyIdx.value < history.value.length - 1) {
    historyIdx.value++
    skipHistory.value = true
    data.value = deepClone(history.value[historyIdx.value])
  }
}

// ── Sync external data ─────────────────────────────────────────────────

const lastExternal = ref('')

function syncInitialData() {
  if (props.initialData) {
    const sig = JSON.stringify(props.initialData)
    if (sig !== lastExternal.value) {
      lastExternal.value = sig
      data.value = props.initialData
      selectedPath.value = null
      history.value = [deepClone(props.initialData)]
      historyIdx.value = 0
    }
  }
}

watch(() => props.initialData, syncInitialData, { deep: true })

// ── Keyboard shortcuts ─────────────────────────────────────────────────

let keydownBound = false

function handleKeydown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement)?.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

  if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) { e.preventDefault(); undo() }
  if ((e.metaKey || e.ctrlKey) && (e.key === 'y' || (e.shiftKey && e.key === 'z'))) { e.preventDefault(); redo() }
  if ((e.metaKey || e.ctrlKey) && e.key === 'c' && selectedPath.value) {
    e.preventDefault()
    const item = getItem(data.value.content, selectedPath.value)
    if (item) clipboard.value = deepClone(item)
  }
  if ((e.metaKey || e.ctrlKey) && e.key === 'v' && clipboard.value) {
    e.preventDefault()
    const newContent = addItemToTree(data.value.content, null, deepClone(clipboard.value))
    commitHistory({ ...data.value, content: newContent })
  }
  if ((e.key === 'Delete' || e.key === 'Backspace') && selectedPath.value) {
    e.preventDefault()
    const newContent = deleteItem(data.value.content, selectedPath.value)
    commitHistory({ ...data.value, content: newContent })
    selectedPath.value = null
  }
  if (e.key === 'Escape') { selectedPath.value = null; contextMenu.value = null }
}

onMounted(() => {
  window.addEventListener('keydown', handleKeydown)
  history.value = [deepClone(data.value)]
  historyIdx.value = 0
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeydown)
})

// ── Mutations ──────────────────────────────────────────────────────────

function updateProps(path: Path, propsUpdate: Record<string, any>) {
  commitHistory({ ...data.value, content: updateItem(data.value.content, path, (item) => ({ ...item, props: { ...item.props, ...propsUpdate } })) })
}

function addComponent(type: string) {
  const cfg = componentRegistry[type]
  if (!cfg) return
  const newItem: DesignItem = { type, props: { ...cfg.defaultProps } }
  const targetPath = selectedPath.value && getItem(data.value.content, selectedPath.value)?.children !== undefined ? selectedPath.value : null
  commitHistory({ ...data.value, content: addItemToTree(data.value.content, targetPath, newItem) })
}

function deleteComponent(path: Path) {
  commitHistory({ ...data.value, content: deleteItem(data.value.content, path) })
  selectedPath.value = null
}

function duplicateComponent(path: Path) {
  const item = getItem(data.value.content, path)
  if (!item) return
  const newContent = addItemToTree(data.value.content, null, deepClone(item))
  commitHistory({ ...data.value, content: newContent })
}

// ── Context menu ───────────────────────────────────────────────────────

function onContextMenu(e: MouseEvent, path: Path) {
  e.preventDefault()
  e.stopPropagation()
  selectedPath.value = path
  contextMenu.value = { x: e.clientX, y: e.clientY, path }
}

// ── Computed ───────────────────────────────────────────────────────────

const selectedItem = computed(() => selectedPath.value ? getItem(data.value.content, selectedPath.value) : null)
const selectedCfg = computed(() => selectedItem.value ? componentRegistry[selectedItem.value.type] : null)
const flatLayers = computed(() => flattenTree(data.value.content))

const vp = computed(() => VIEWPORTS[viewport.value])
const canvasMaxWidth = computed(() => vp.value.width || '100%')

// ── Expose for parent ──────────────────────────────────────────────────

defineExpose({
  getData: () => deepClone(data.value),
  setData: (d: DesignData) => {
    data.value = d
    history.value = [deepClone(d)]
    historyIdx.value = 0
  },
})

function exportJson() {
  const blob = new Blob([JSON.stringify(data.value, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = `design-${Date.now()}.madcop`
  a.click()
  URL.revokeObjectURL(a.href)
}

</script>
<template>
  <div
    class="flex h-full bg-[#F3F4F6] relative"
    @click="selectedPath = null; contextMenu = null"
  >
    <!-- ── Left: Components + Layers ── -->
    <div class="w-[200px] flex-shrink-0 border-r border-[#E5E7EB] bg-white flex flex-col">
      <!-- Component palette -->
      <div class="p-[10px_8px] border-b border-[#E5E7EB] max-h-[260px] overflow-y-auto">
        <div class="text-xs font-bold text-[#9CA3AF] uppercase tracking-[0.5] mb-2">
          组件
        </div>
        <div class="flex flex-wrap gap-1">
          <button
            v-for="([type, cfg]) in Object.entries(componentRegistry)"
            :key="type"
            @click.stop="addComponent(type)"
            class="px-2.5 py-1 bg-[#F3F4F6] border border-[#E5E7EB] rounded text-xs text-[#374151] cursor-pointer hover:bg-[#EEF2FF] transition-colors"
          >
            {{ cfg.label }}
          </button>
        </div>
      </div>

      <!-- Layer tree -->
      <div class="flex-1 overflow-y-auto p-2">
        <div class="text-xs font-bold text-[#9CA3AF] uppercase tracking-[0.5] mb-2 flex justify-between items-center">
          图层
          <button
            @click.stop="showLayers = !showLayers"
            class="bg-none border-none cursor-pointer text-[10px] text-[#9CA3AF]"
          >
            {{ showLayers ? '收起' : '展开' }}
          </button>
        </div>
        <div
          v-if="showLayers"
          v-for="{ item, path, depth } in flatLayers"
          :key="path.join('-')"
          @click.stop="selectedPath = path"
          :style="{
            padding: '4px 8px',
            marginLeft: `${depth * 12}px`,
            fontSize: 12,
            cursor: 'pointer',
            borderRadius: 3,
            background: selectedPath && path.join('-') === selectedPath.join('-') ? '#EEF2FF' : 'transparent',
            color: selectedPath && path.join('-') === selectedPath.join('-') ? '#4F46E5' : '#374151',
            whiteSpace: 'nowrap',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          }"
        >
          <span v-if="componentRegistry[item.type]?.isContainer">▸ </span>
          {{ componentRegistry[item.type]?.label || item.type }}
        </div>
        <div
          v-if="flatLayers.length === 0"
          class="text-xs text-[#D1D5DB]"
        >
          暂无组件
        </div>
      </div>
    </div>

    <!-- ── Center: Canvas ── -->
    <div class="flex-1 flex flex-col overflow-hidden">
      <!-- Toolbar -->
      <div class="flex items-center justify-between px-3 py-1.5 border-b border-[#E5E7EB] bg-white flex-shrink-0">
        <div class="flex gap-1">
          <button
            v-for="(v, i) in VIEWPORTS"
            :key="i"
            @click.stop="viewport = i"
            :style="{
              padding: '4px 10px',
              border: 'none',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 12,
              background: viewport === i ? '#7C3AED' : 'transparent',
              color: viewport === i ? '#fff' : '#6B7280',
            }"
          >
            {{ v.label }}
          </button>
        </div>
        <div class="flex gap-1.5">
          <button
            @click.stop="undo()"
            :disabled="historyIdx <= 0"
            :style="{
              padding: '4px 10px',
              border: '1px solid #E5E7EB',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 12,
              background: '#fff',
              color: historyIdx <= 0 ? '#D1D5DB' : '#374151',
            }"
          >
            撤销
          </button>
          <button
            @click.stop="redo()"
            :disabled="historyIdx >= history.length - 1"
            :style="{
              padding: '4px 10px',
              border: '1px solid #E5E7EB',
              borderRadius: 4,
              cursor: 'pointer',
              fontSize: 12,
              background: '#fff',
              color: historyIdx >= history.length - 1 ? '#D1D5DB' : '#374151',
            }"
          >
            重做
          </button>
        </div>
      </div>

      <!-- Canvas area -->
      <div
        class="flex-1 overflow-y-auto p-6 flex justify-center items-start"
        @dragover.stop.prevent
        @drop.stop.prevent
      >
        <!-- Canvas container -->
        <div
          :style="{
            width: '100%',
            maxWidth: canvasMaxWidth,
            minHeight: '100%',
            background: data.root?.props?.bgColor || '#FFFFFF',
            borderRadius: 8,
            padding: `${data.root?.props?.padding || 40}px`,
            boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
          }"
          @click="selectedPath = null"
          @dragover.stop.prevent
          @drop.stop="(e) => {
            e.preventDefault()
            if (dragPath) {
              const moved = getItem(data.content, dragPath)
              if (moved) {
                let newContent = deleteItem(data.content, dragPath)
                newContent = [...newContent, deepClone(moved)]
                commitHistory({ ...data, content: newContent })
              }
            }
            dragPath = null
            dragOverPath = null
          }"
        >
          <div
            v-if="data.content.length === 0"
            class="text-center py-[60px] px-5 text-[#9CA3AF] text-sm"
          >
            从左侧添加组件，或用 AI 生成设计
          </div>

          <!-- Render items recursively -->
          <RenderedItem
            v-for="(item, idx) in data.content"
            :key="idx"
            :item="item"
            :path="[idx]"
            :selected-path="selectedPath"
            :drag-path="dragPath"
            :drag-over-path="dragOverPath"
            :component-registry="componentRegistry"
            :shadow-map="shadowMap"
            @select="(p: Path) => selectedPath = p"
            @start-drag="(p: Path) => dragPath = p"
            @drag-over="(p: Path) => dragOverPath = p"
            @drop="(targetPath: Path) => {
              if (dragPath && componentRegistry[data.content[idx]?.type]?.isContainer && dragPath.join('-') !== targetPath.join('-')) {
                const moved = getItem(data.content, dragPath)
                if (moved) {
                  let newContent = deleteItem(data.content, dragPath)
                  newContent = addItemToTree(newContent, targetPath, deepClone(moved))
                  commitHistory({ ...data, content: newContent })
                }
              }
              dragPath = null
              dragOverPath = null
            }"
            @context-menu="(e: MouseEvent, p: Path) => onContextMenu(e, p)"
          />
        </div>
      </div>
    </div>

    <!-- ── Right: Properties ── -->
    <div
      class="w-[260px] flex-shrink-0 border-l border-[#E5E7EB] bg-white overflow-y-auto p-3"
      @click.stop
    >
      <template v-if="selectedItem && selectedCfg">
        <div class="flex justify-between items-center mb-3.5">
          <span class="text-sm font-bold">{{ selectedCfg.label }} 属性</span>
          <div class="flex gap-1">
            <button
              @click="duplicateComponent(selectedPath!)"
              class="px-1.5 py-0.5 text-xs border border-[#D1D5DB] rounded cursor-pointer bg-white"
            >
              复制
            </button>
            <button
              @click="deleteComponent(selectedPath!)"
              class="px-1.5 py-0.5 text-xs border-none rounded cursor-pointer bg-[#FEE2E2] text-[#DC2626]"
            >
              删除
            </button>
          </div>
        </div>
        <div
          v-for="([key, field]) in Object.entries(selectedCfg.fields)"
          :key="key"
          class="mb-3"
        >
          <label class="block text-xs text-[#6B7280] mb-1">{{ field.label }}</label>
          <FieldEditor
            :field="field"
            :value="selectedItem.props[key]"
            @change="(v: any) => updateProps(selectedPath!, { [key]: v })"
          />
        </div>
      </template>
      <template v-else>
        <div class="text-xs font-bold text-[#9CA3AF] uppercase tracking-[0.5] mb-2.5">
          画布设置
        </div>
        <div class="mb-3">
          <label class="block text-xs text-[#6B7280] mb-1">背景色</label>
          <FieldEditor
            :field="{ type: 'color', label: '背景色' }"
            :value="data.root?.props?.bgColor"
            @change="(v: any) => commitHistory({ ...data, root: { props: { ...data.root.props, bgColor: v } } })"
          />
        </div>
        <div class="mb-3">
          <label class="block text-xs text-[#6B7280] mb-1">内边距</label>
          <FieldEditor
            :field="{ type: 'number', label: '内边距' }"
            :value="data.root?.props?.padding"
            @change="(v: any) => commitHistory({ ...data, root: { props: { ...data.root.props, padding: v } } })"
          />
        </div>
        <div class="mt-5 p-2.5 bg-[#F3F4F6] rounded-md text-xs text-[#9CA3AF] leading-relaxed">
          快捷键: Ctrl+Z 撤销 | Ctrl+C/V 复制粘贴 | Del 删除 | Esc 取消选中
        </div>
      </template>
    </div>

    <!-- ── Context Menu (teleport to body) ── -->
    <teleport v-if="contextMenu" to="body">
      <div
        class="fixed inset-0 z-[200]"
        @click.stop="contextMenu = null"
        @contextmenu.stop.prevent="contextMenu = null"
      />
      <div
        :style="{
          position: 'fixed',
          left: contextMenu.x,
          top: contextMenu.y,
          zIndex: 201,
          background: '#fff',
          border: '1px solid #E5E7EB',
          borderRadius: 6,
          boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
          padding: 4,
          minWidth: 120,
        }"
      >
        <button
          v-for="(menuItem, i) in [
            { label: '复制', action: () => { const item = getItem(data.content, contextMenu!.path); if (item) clipboard = deepClone(item) } },
            { label: '粘贴到末尾', action: () => { if (clipboard) commitHistory({ ...data, content: addItemToTree(data.content, null, deepClone(clipboard)) }) } },
            { label: '创建副本', action: () => duplicateComponent(contextMenu!.path) },
            { label: '删除', action: () => deleteComponent(contextMenu!.path), danger: true },
          ]"
          :key="i"
          @click.stop="menuItem.action(); contextMenu = null"
          :style="{
            display: 'block',
            width: '100%',
            textAlign: 'left',
            padding: '6px 12px',
            border: 'none',
            background: 'transparent',
            cursor: 'pointer',
            fontSize: 13,
            color: menuItem.danger ? '#DC2626' : '#374151',
            borderRadius: 3,
          }"
          @mouseenter="($event.target as HTMLElement).style.background = menuItem.danger ? '#FEF2F2' : '#F3F4F6'"
          @mouseleave="($event.target as HTMLElement).style.background = 'transparent'"
        >
          {{ menuItem.label }}
        </button>
      </div>
    </teleport>

    <!-- ── Export/Save floating buttons ── -->
    <div class="absolute bottom-3 right-3 flex gap-2">
      <button @click.stop="exportJson" class="rounded-lg p-2.5 text-white transition-colors hover:bg-opacity-90" :style="{ background: 'var(--color-brand)' }">
        <span class="material-symbols-outlined text-lg">save</span>
      </button>
      <button
        @click.stop="emit('save', data)"
        class="px-3 py-1.5 bg-purple-600/90 text-white border-none rounded cursor-pointer text-xs font-semibold backdrop-blur-sm"
      >
        保存
      </button>
    </div>
  </div>
</template>