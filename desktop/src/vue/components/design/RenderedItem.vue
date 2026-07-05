<!--
  RenderedItem — recursive item renderer for DesignCanvas.
  Renders each DesignItem component with selection, drag, and context-menu support.
-->
<script setup lang="ts">
import { computed, type PropType } from 'vue'

// ── Types ─────────────────────────────────────────────────────────────

export interface DesignItem {
  type: string
  props: Record<string, any>
  children?: DesignItem[]
}

export interface ComponentConfig {
  fields: Record<string, any>
  defaultProps: Record<string, any>
  isContainer?: boolean
  label: string
}

export type Path = number[]

const props = defineProps<{
  item: DesignItem
  path: Path
  selectedPath: Path | null
  dragPath: Path | null
  dragOverPath: Path | null
  componentRegistry: Record<string, ComponentConfig>
  shadowMap: Record<string, string>
}>()

const emit = defineEmits<{
  (e: 'select', path: Path): void
  (e: 'startDrag', path: Path): void
  (e: 'dragOver', path: Path): void
  (e: 'drop', targetPath: Path): void
  (e: 'contextMenu', event: MouseEvent, path: Path): void
}>()

// ── Computed ──────────────────────────────────────────────────────────

const isSelected = computed(() =>
  props.selectedPath && props.path.length === props.selectedPath.length &&
  props.path.every((v, i) => v === props.selectedPath[i])
)

const isDragOver = computed(() =>
  props.dragOverPath && props.path.length === props.dragOverPath.length &&
  props.path.every((v, i) => v === props.dragOverPath[i])
)

const cfg = computed(() => props.componentRegistry[props.item.type] || null)

const containerStyle = computed<Record<string, any>>(() => ({
  marginBottom: 4,
  padding: 2,
  borderRadius: 4,
  cursor: 'pointer',
  border: isSelected.value
    ? '2px solid #7C3AED'
    : isDragOver.value
      ? '2px dashed #A78BFA'
      : '2px solid transparent',
  transition: 'border-color 0.1s',
}))

const hasChildren = computed(() => props.item.children && props.item.children.length > 0)

// ── Event handlers ─────────────────────────────────────────────────────

function handleSelect() {
  emit('select', props.path)
}

function handleDragStart() {
  emit('startDrag', props.path)
}

function handleDragOver(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  emit('dragOver', props.path)
}

function handleDrop(e: DragEvent) {
  e.preventDefault()
  e.stopPropagation()
  emit('drop', props.path)
}

function handleContextMenu(e: MouseEvent) {
  e.preventDefault()
  e.stopPropagation()
  emit('contextMenu', e, props.path)
}

// ── Dynamic tag for Header ─────────────────────────────────────────────

const headerTag = computed(() => `h${props.item.props?.level || '2'}`)
</script>

<template>
  <div
    :draggable="true"
    @dragstart="handleDragStart"
    @dragover="handleDragOver"
    @drop="handleDrop"
    @click="handleSelect"
    @contextmenu="handleContextMenu"
    :style="containerStyle"
  >
    <!-- ── Header ── -->
    <component
      :is="headerTag"
      v-if="item.type === 'Header'"
      :style="{
        margin: '0 0 8px 0',
        color: item.props?.color || '#1A1A1A',
        fontSize: item.props?.fontSize || 24,
        fontWeight: 700,
      }"
    >
      {{ item.props?.text || '标题' }}
    </component>

    <!-- ── Paragraph ── -->
    <p
      v-else-if="item.type === 'Paragraph'"
      :style="{
        margin: '0 0 12px 0',
        fontSize: item.props?.fontSize || 14,
        lineHeight: 1.6,
        color: item.props?.color || '#4B5563',
        textAlign: item.props?.textAlign || 'left',
      }"
    >
      {{ item.props?.text || '段落文字' }}
    </p>

    <!-- ── Button ── -->
    <button
      v-else-if="item.type === 'Button'"
      :style="{
        padding: '10px 24px',
        borderRadius: 6,
        border: 'none',
        cursor: 'pointer',
        fontWeight: 600,
        fontSize: 14,
        width: item.props?.width ? `${item.props.width}px` : 'auto',
        background: item.props?.variant === 'primary' ? (item.props?.color || '#7C3AED') : '#E2E8F0',
        color: item.props?.variant === 'primary' ? '#fff' : '#1A1A1A',
      }"
    >
      {{ item.props?.text || '按钮' }}
    </button>

    <!-- ── Image ── -->
    <img
      v-else-if="item.type === 'Image'"
      :src="item.props?.src || 'https://via.placeholder.com/400x200'"
      :alt="item.props?.alt || ''"
      :style="{
        maxWidth: '100%',
        borderRadius: item.props?.borderRadius || 8,
        width: item.props?.width ? `${item.props.width}px` : 'auto',
        height: item.props?.height ? `${item.props.height}px` : 'auto',
      }"
    />

    <!-- ── Input ── -->
    <input
      v-else-if="item.type === 'Input'"
      :type="item.props?.type || 'text'"
      :placeholder="item.props?.placeholder || '输入...'"
      readonly
      :style="{
        padding: '10px 14px',
        border: '1px solid #D1D5DB',
        borderRadius: 6,
        fontSize: 14,
        width: item.props?.width ? `${item.props.width}px` : '100%',
        outline: 'none',
        background: '#F9FAFB',
      }"
    />

    <!-- ── Divider ── -->
    <hr
      v-else-if="item.type === 'Divider'"
      :style="{
        border: 'none',
        borderTop: `${item.props?.thickness || 1}px solid ${item.props?.color || '#E5E7EB'}`,
        margin: `${item.props?.margin || 16}px 0`,
      }"
    />

    <!-- ── Space ── -->
    <div
      v-else-if="item.type === 'Space'"
      :style="{ height: item.props?.height || 20 }"
    />

    <!-- ── Card (container) ── -->
    <div
      v-else-if="item.type === 'Card'"
      :style="{
        padding: item.props?.padding || 20,
        borderRadius: item.props?.radius || 12,
        background: item.props?.bgColor || '#F9FAFB',
        border: '1px solid #E5E7EB',
        boxShadow: shadowMap[item.props?.shadow || 'sm'],
      }"
    >
      <RenderedItem
        v-for="(child, i) in (item.children || [])"
        :key="path.join('-') + '-' + i"
        :item="child"
        :path="[...path, i]"
        :selected-path="selectedPath"
        :drag-path="dragPath"
        :drag-over-path="dragOverPath"
        :component-registry="componentRegistry"
        :shadow-map="shadowMap"
        @select="(p) => emit('select', p)"
        @start-drag="(p) => emit('startDrag', p)"
        @drag-over="(p) => emit('dragOver', p)"
        @drop="(p) => emit('drop', p)"
        @context-menu="(e, p) => emit('contextMenu', e, p)"
      />
      <span
        v-if="!hasChildren"
        style="font-size: 12px; color: #9CA3AF"
      >
        拖入组件到此处
      </span>
    </div>

    <!-- ── Flex (container) ── -->
    <div
      v-else-if="item.type === 'Flex'"
      :style="{
        display: 'flex',
        flexDirection: item.props?.direction || 'column',
        gap: item.props?.gap || 8,
        justifyContent: item.props?.justify === 'center' ? 'center' : item.props?.justify === 'between' ? 'space-between' : item.props?.justify === 'around' ? 'space-around' : 'flex-start',
        alignItems: item.props?.align === 'center' ? 'center' : item.props?.align === 'stretch' ? 'stretch' : 'flex-start',
      }"
    >
      <RenderedItem
        v-for="(child, i) in (item.children || [])"
        :key="path.join('-') + '-' + i"
        :item="child"
        :path="[...path, i]"
        :selected-path="selectedPath"
        :drag-path="dragPath"
        :drag-over-path="dragOverPath"
        :component-registry="componentRegistry"
        :shadow-map="shadowMap"
        @select="(p) => emit('select', p)"
        @start-drag="(p) => emit('startDrag', p)"
        @drag-over="(p) => emit('dragOver', p)"
        @drop="(p) => emit('drop', p)"
        @context-menu="(e, p) => emit('contextMenu', e, p)"
      />
      <span
        v-if="!hasChildren"
        style="font-size: 12px; color: #9CA3AF"
      >
        拖入组件
      </span>
    </div>

    <!-- ── Grid (container) ── -->
    <div
      v-else-if="item.type === 'Grid'"
      :style="{
        display: 'grid',
        gridTemplateColumns: `repeat(${item.props?.columns || 2}, 1fr)`,
        gap: item.props?.gap || 12,
      }"
    >
      <RenderedItem
        v-for="(child, i) in (item.children || [])"
        :key="path.join('-') + '-' + i"
        :item="child"
        :path="[...path, i]"
        :selected-path="selectedPath"
        :drag-path="dragPath"
        :drag-over-path="dragOverPath"
        :component-registry="componentRegistry"
        :shadow-map="shadowMap"
        @select="(p) => emit('select', p)"
        @start-drag="(p) => emit('startDrag', p)"
        @drag-over="(p) => emit('dragOver', p)"
        @drop="(p) => emit('drop', p)"
        @context-menu="(e, p) => emit('contextMenu', e, p)"
      />
      <span
        v-if="!hasChildren"
        style="font-size: 12px; color: #9CA3AF"
      >
        拖入组件
      </span>
    </div>

    <!-- ── Section (container) ── -->
    <div
      v-else-if="item.type === 'Section'"
      :style="{
        background: item.props?.bgColor || 'transparent',
        padding: item.props?.padding || 24,
        maxWidth: item.props?.maxWidth || 720,
        borderRadius: 8,
      }"
    >
      <RenderedItem
        v-for="(child, i) in (item.children || [])"
        :key="path.join('-') + '-' + i"
        :item="child"
        :path="[...path, i]"
        :selected-path="selectedPath"
        :drag-path="dragPath"
        :drag-over-path="dragOverPath"
        :component-registry="componentRegistry"
        :shadow-map="shadowMap"
        @select="(p) => emit('select', p)"
        @start-drag="(p) => emit('startDrag', p)"
        @drag-over="(p) => emit('dragOver', p)"
        @drop="(p) => emit('drop', p)"
        @context-menu="(e, p) => emit('contextMenu', e, p)"
      />
      <span
        v-if="!hasChildren"
        style="font-size: 12px; color: #9CA3AF"
      >
        拖入组件到区块
      </span>
    </div>
  </div>
</template>