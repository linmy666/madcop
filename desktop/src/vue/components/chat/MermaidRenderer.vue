<!--
  v3.0 — MermaidRenderer (Vue 3 SFC)
  Full translation of src/components/chat/MermaidRenderer.tsx (810 lines).
  Renders mermaid flowcharts/diagrams in chat messages with inline preview,
  fullscreen modal with zoom/pan, copy, and PNG export.
-->
<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import DOMPurify from 'dompurify'
import mermaid from 'mermaid'
import { useUIStore } from '../stores'

// ── Props ────────────────────────────────────────────────────────────────────
const props = defineProps<{
  code: string
}>()

// ── Constants ────────────────────────────────────────────────────────────────
const MIN_PREVIEW_ZOOM = 0.05
const MAX_PREVIEW_ZOOM = 3
const PREVIEW_ZOOM_STEP = 0.25
const PREVIEW_FIT_PADDING = 48

// ── Regex constants ──────────────────────────────────────────────────────────
const FLOWCHART_START = /^\s*(?:graph|flowchart)\b/i
const FLOWCHART_NODE_START = /^([A-Za-z][\w-]*)\[/
const UNQUOTED_FLOWCHART_LABEL_UNSAFE = /<br\s*\/?>|[{}[\]*]/i

// ── Helpers ──────────────────────────────────────────────────────────────────
function isFlowchartDiagram(code: string): boolean {
  const firstMeaningfulLine = code
    .split('\n')
    .map((line) => line.trim())
    .find(Boolean)
  return firstMeaningfulLine ? FLOWCHART_START.test(firstMeaningfulLine) : false
}

function isQuotedFlowchartLabel(label: string): boolean {
  const trimmed = label.trim()
  return (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'")) ||
    (trimmed.startsWith('`') && trimmed.endsWith('`'))
  )
}

function shouldQuoteFlowchartLabel(label: string): boolean {
  return !isQuotedFlowchartLabel(label) && UNQUOTED_FLOWCHART_LABEL_UNSAFE.test(label)
}

function escapeFlowchartLabel(label: string): string {
  return label.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

function isLikelyFlowchartLabelClose(line: string, closeIndex: number): boolean {
  const after = line.slice(closeIndex + 1).trimStart()
  return (
    after.length === 0 ||
    after.startsWith('--') ||
    after.startsWith('-.') ||
    after.startsWith('==') ||
    after.startsWith('~~~') ||
    after.startsWith(':::') ||
    after.startsWith('&') ||
    after.startsWith('@') ||
    /^[;,)]/.test(after)
  )
}

function findFlowchartLabelClose(line: string, openIndex: number): number {
  for (let index = openIndex + 1; index < line.length; index += 1) {
    if (line[index] === ']' && isLikelyFlowchartLabelClose(line, index)) {
      return index
    }
  }
  return -1
}

function normalizeFlowchartLine(line: string): string {
  let output = ''
  let index = 0

  while (index < line.length) {
    const match = FLOWCHART_NODE_START.exec(line.slice(index))
    if (!match) {
      output += line[index]
      index += 1
      continue
    }

    const nodeId = match[1] ?? ''
    const openIndex = index + nodeId.length
    const closeIndex = findFlowchartLabelClose(line, openIndex)
    if (closeIndex < 0) {
      output += line[index]
      index += 1
      continue
    }

    const label = line.slice(openIndex + 1, closeIndex)
    if (!shouldQuoteFlowchartLabel(label)) {
      output += line.slice(index, closeIndex + 1)
    } else {
      output += `${nodeId}["${escapeFlowchartLabel(label)}"]`
    }
    index = closeIndex + 1
  }

  return output
}

function normalizeGeneratedFlowchartSyntax(code: string): string {
  if (!isFlowchartDiagram(code)) return code
  return code.split('\n').map(normalizeFlowchartLine).join('\n')
}

function rgbToHex(color: string, fallback: string): string {
  const trimmed = color.trim()
  if (/^#[0-9a-f]{6}$/i.test(trimmed)) return trimmed
  const shortHex = /^#([0-9a-f])([0-9a-f])([0-9a-f])$/i.exec(trimmed)
  if (shortHex) {
    return `#${shortHex[1]}${shortHex[1]}${shortHex[2]}${shortHex[2]}${shortHex[3]}${shortHex[3]}`
  }

  const rgb = /^rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)/i.exec(trimmed)
  if (!rgb) return fallback

  return [rgb[1], rgb[2], rgb[3]]
    .map((value) => {
      const channel = Math.max(0, Math.min(255, Math.round(Number.parseFloat(value ?? '0'))))
      return channel.toString(16).padStart(2, '0')
    })
    .join('')
    .replace(/^/, '#')
}

function resolveThemeColor(token: string, fallback: string): string {
  if (typeof document === 'undefined') return fallback

  const probe = document.createElement('span')
  probe.style.color = `var(${token})`
  probe.style.position = 'absolute'
  probe.style.pointerEvents = 'none'
  probe.style.opacity = '0'
  document.body.appendChild(probe)
  const resolved = getComputedStyle(probe).color
  probe.remove()

  return rgbToHex(resolved, fallback)
}

function getMermaidThemeColors(theme: 'light' | 'dark'): {
  textColor: string
  mutedTextColor: string
  surfaceColor: string
  nodeColor: string
  accentColor: string
  lineColor: string
  isDark: boolean
} {
  const isDark = theme === 'dark'
  return {
    textColor: resolveThemeColor('--color-text-primary', isDark ? '#E5E2E1' : '#1B1C1A'),
    mutedTextColor: resolveThemeColor('--color-text-secondary', isDark ? '#B7AAA5' : '#61514B'),
    surfaceColor: resolveThemeColor('--color-surface-container-lowest', isDark ? '#0E0E0E' : '#FFFFFF'),
    nodeColor: resolveThemeColor('--color-surface-container-low', isDark ? '#1C1B1B' : '#F4EFEA'),
    accentColor: resolveThemeColor('--color-primary', isDark ? '#FFB59F' : '#8F482F'),
    lineColor: resolveThemeColor('--color-outline', isDark ? '#BFAEAA' : '#667485'),
    isDark,
  }
}

function initMermaid(theme: 'light' | 'dark'): { lineColor: string } {
  const {
    textColor,
    mutedTextColor,
    surfaceColor,
    nodeColor,
    accentColor,
    lineColor,
    isDark,
  } = getMermaidThemeColors(theme)

  mermaid.initialize({
    startOnLoad: false,
    theme: 'base',
    htmlLabels: false,
    flowchart: {
      htmlLabels: false,
      arrowMarkerAbsolute: true,
    },
    themeVariables: {
      darkMode: isDark,
      background: surfaceColor,
      mainBkg: nodeColor,
      primaryColor: nodeColor,
      primaryTextColor: textColor,
      primaryBorderColor: lineColor,
      secondaryColor: surfaceColor,
      tertiaryColor: surfaceColor,
      textColor,
      lineColor,
      edgeLabelBackground: surfaceColor,
      clusterBkg: surfaceColor,
      clusterBorder: lineColor,
      titleColor: textColor,
      labelTextColor: textColor,
      nodeTextColor: textColor,
      noteTextColor: textColor,
      noteBkgColor: surfaceColor,
      noteBorderColor: lineColor,
      actorTextColor: textColor,
      actorLineColor: lineColor,
      signalTextColor: textColor,
      signalColor: mutedTextColor,
      activationBkgColor: nodeColor,
      activationBorderColor: accentColor,
    },
    securityLevel: 'strict',
    suppressErrorRendering: true,
    fontFamily: 'var(--font-sans)',
  })

  return { lineColor }
}

let mermaidIdCounter = 0

function sanitizeMermaidSvg(svg: string): string {
  return DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true, html: true },
    ADD_TAGS: ['foreignObject'],
  })
}

function formatSvgDimension(value: number): string {
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(3)))
}

function getSvgStyleProperty(element: Element, property: string): string {
  const style = element.getAttribute('style') ?? ''
  const escapedProperty = property.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = new RegExp(`(?:^|;)\\s*${escapedProperty}\\s*:\\s*([^;]+)`, 'i').exec(style)
  return match?.[1]?.trim() ?? ''
}

function setSvgStyle(element: Element, property: string, value: string, overwrite = true): void {
  if (!overwrite && getSvgStyleProperty(element, property)) return

  const style = element.getAttribute('style') ?? ''
  const escapedProperty = property.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const declaration = `${property}: ${value}`
  const pattern = new RegExp(`(^|;)\\s*${escapedProperty}\\s*:[^;]*`, 'i')
  const nextStyle = pattern.test(style)
    ? style.replace(pattern, (_: string, prefix: string) => `${prefix}${declaration}`)
    : `${style.trim().replace(/;$/, '')}${style.trim() ? '; ' : ''}${declaration}`

  element.setAttribute('style', nextStyle)
}

function setSvgFallbackStyle(element: Element, property: string, value: string): void {
  if (element.hasAttribute(property)) return
  setSvgStyle(element, property, value, false)
}

function normalizeMermaidSvg(svg: string, lineColor: string): string {
  if (typeof DOMParser === 'undefined' || typeof XMLSerializer === 'undefined') {
    return svg
  }

  const parsed = new DOMParser().parseFromString(svg, 'image/svg+xml')
  if (parsed.querySelector('parsererror')) return svg

  const root = parsed.querySelector('svg')
  if (!root) return svg

  const metrics = parseSvgMetrics(svg)
  if (metrics) {
    root.setAttribute('width', formatSvgDimension(metrics.width))
    root.setAttribute('height', formatSvgDimension(metrics.height))
  }

  root.setAttribute('preserveAspectRatio', 'xMidYMid meet')
  setSvgStyle(root, 'display', 'block')
  setSvgStyle(root, 'max-width', 'none')
  setSvgStyle(root, 'height', metrics ? `${formatSvgDimension(metrics.height)}px` : 'auto')
  setSvgStyle(root, 'background', 'transparent')
  setSvgStyle(root, 'overflow', 'visible')

  root
    .querySelectorAll('[data-edge="true"], .flowchart-link, .edgePath .path')
    .forEach((edge) => {
      setSvgFallbackStyle(edge, 'stroke', lineColor)
      setSvgFallbackStyle(edge, 'stroke-width', '1.6px')
      setSvgFallbackStyle(edge, 'fill', 'none')
      setSvgStyle(edge, 'vector-effect', 'non-scaling-stroke')
    })

  root
    .querySelectorAll('.marker, .arrowMarkerPath, marker path')
    .forEach((marker) => {
      setSvgFallbackStyle(marker, 'fill', lineColor)
      setSvgFallbackStyle(marker, 'stroke', lineColor)
    })

  return new XMLSerializer().serializeToString(root)
}

function clampZoom(value: number): number {
  return Math.min(MAX_PREVIEW_ZOOM, Math.max(MIN_PREVIEW_ZOOM, value))
}

function calculateFitZoom(metrics: { width: number; height: number }, viewport: HTMLElement | null): number {
  if (!viewport) return 1

  const viewportWidth = viewport.clientWidth
  const viewportHeight = viewport.clientHeight
  if (viewportWidth <= 0 || viewportHeight <= 0) return 1

  const availableWidth = Math.max(1, viewportWidth - PREVIEW_FIT_PADDING)
  const availableHeight = Math.max(1, viewportHeight - PREVIEW_FIT_PADDING)
  return clampZoom(Math.min(1, availableWidth / metrics.width, availableHeight / metrics.height))
}

function getPointerPosition(event: { clientX?: number; clientY?: number; pageX?: number; pageY?: number }) {
  const x = Number.isFinite(event.clientX!) ? event.clientX! : event.pageX!
  const y = Number.isFinite(event.clientY!) ? event.clientY! : event.pageY!

  return {
    x: Number.isFinite(x) ? x : 0,
    y: Number.isFinite(y) ? y : 0,
  }
}

function parseSvgMetrics(svg: string): { width: number; height: number } | null {
  const viewBoxMatch = svg.match(/viewBox="([^"]+)"/i)
  if (viewBoxMatch) {
    const viewBox = viewBoxMatch[1]
    if (!viewBox) return null

    const values = viewBox
      .split(/[\s,]+/)
      .map((part) => Number.parseFloat(part))
    if (values.length === 4 && values.every((value) => Number.isFinite(value))) {
      const [, , width, height] = values
      if (width !== undefined && height !== undefined) {
        return { width, height }
      }
    }
  }

  const widthMatch = svg.match(/\bwidth="([0-9.]+)(?:px)?"/i)
  const heightMatch = svg.match(/\bheight="([0-9.]+)(?:px)?"/i)
  if (widthMatch && heightMatch) {
    const widthValue = widthMatch[1]
    const heightValue = heightMatch[1]
    if (!widthValue || !heightValue) return null

    const width = Number.parseFloat(widthValue)
    const height = Number.parseFloat(heightValue)
    if (Number.isFinite(width) && Number.isFinite(height)) {
      return { width, height }
    }
  }

  return null
}

// ── State ────────────────────────────────────────────────────────────────────
const uiStore = useUIStore()
const theme = computed(() => uiStore.theme)

const containerRef = ref<HTMLDivElement | null>(null)
const previewViewportRef = ref<HTMLDivElement | null>(null)
const previewContentRef = ref<HTMLDivElement | null>(null)

const svg = ref<string | null>(null)
const error = ref<string | null>(null)
const previewOpen = ref(false)
const previewZoom = ref(1)
const previewFitMode = ref(true)
const isDraggingPreview = ref(false)
const inlineViewportWidth = ref(0)

// Drag state held in a plain object (not ref) to avoid triggering re-renders during drag
let dragState: {
  pointerId: number
  startX: number
  startY: number
  scrollLeft: number
  scrollTop: number
} | null = null

// ── Computed ─────────────────────────────────────────────────────────────────
const svgMetrics = computed(() => (svg.value ? parseSvgMetrics(svg.value) : null))
const sanitizedSvg = computed(() => (svg.value ? sanitizeMermaidSvg(svg.value) : null))

const inlineZoom = computed(() => {
  if (!svgMetrics.value || inlineViewportWidth.value <= 0) return 1
  return clampZoom(Math.min(1, Math.max(1, inlineViewportWidth.value - 32) / svgMetrics.value.width))
})

const inlineFrameStyle = computed(() => {
  if (!svgMetrics.value) return undefined
  return {
    position: 'relative' as const,
    width: `${svgMetrics.value.width * inlineZoom.value}px`,
    height: `${svgMetrics.value.height * inlineZoom.value}px`,
  }
})

const inlineCanvasStyle = computed(() => {
  if (!svgMetrics.value) return undefined
  return {
    position: 'absolute' as const,
    left: 0,
    top: 0,
    width: `${svgMetrics.value.width}px`,
    height: `${svgMetrics.value.height}px`,
    transform: `scale(${inlineZoom.value})`,
    transformOrigin: 'top left',
  }
})

const previewFrameStyle = computed(() => {
  if (!svgMetrics.value) return undefined
  return {
    position: 'relative' as const,
    width: `${svgMetrics.value.width * previewZoom.value}px`,
    height: `${svgMetrics.value.height * previewZoom.value}px`,
  }
})

const previewCanvasStyle = computed(() => {
  if (!svgMetrics.value) return undefined
  return {
    position: 'absolute' as const,
    left: 0,
    top: 0,
    width: `${svgMetrics.value.width}px`,
    height: `${svgMetrics.value.height}px`,
    transform: `scale(${previewZoom.value})`,
    transformOrigin: 'top left',
    willChange: 'transform',
  }
})

// ── Clipboard helper (from src/components/chat/clipboard.ts) ─────────────────
async function copyTextToClipboard(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
      return true
    }
  } catch {
    // Fall through to legacy copy path.
  }

  try {
    const textarea = document.createElement('textarea')
    textarea.value = text
    textarea.setAttribute('readonly', 'true')
    textarea.style.position = 'fixed'
    textarea.style.opacity = '0'
    document.body.appendChild(textarea)
    textarea.select()
    const copied = document.execCommand('copy')
    document.body.removeChild(textarea)
    return copied
  } catch {
    return false
  }
}

// ── Copy button state ────────────────────────────────────────────────────────
const copied = ref(false)

function handleCopy(): void {
  (async () => {
    try {
      const ok = await copyTextToClipboard(props.code)
      if (!ok) {
        copied.value = false
        return
      }
      copied.value = true
      setTimeout(() => { copied.value = false }, 1500)
    } catch {
      copied.value = false
    }
  })()
}

// ── Mermaid rendering ────────────────────────────────────────────────────────
let renderCancelled = false
let resizeObserver: ResizeObserver | null = null
let previewResizeObserver: ResizeObserver | null = null
let fitAnimationFrame = 0

async function renderMermaid(): Promise<void> {
  renderCancelled = false
  const { lineColor } = initMermaid(theme.value)

  const id = `mermaid-${++mermaidIdCounter}`
  const renderCode = normalizeGeneratedFlowchartSyntax(props.code)

  try {
    const result = await mermaid.render(id, renderCode)
    if (!renderCancelled) {
      svg.value = normalizeMermaidSvg((result as { svg: string }).svg, lineColor)
      error.value = null
    }
  } catch (err: unknown) {
    if (!renderCancelled) {
      error.value = String((err as Error)?.message || err)
      svg.value = null
    }
  }
}

onMounted(() => {
  renderMermaid()
})

// ── Inline viewport resize observer ──────────────────────────────────────────
onMounted(() => {
  nextTick(() => {
    if (!containerRef.value) return
    const updateInlineWidth = () => { inlineViewportWidth.value = containerRef.value!.clientWidth }
    updateInlineWidth()

    if (typeof ResizeObserver !== 'undefined') {
      resizeObserver = new ResizeObserver(updateInlineWidth)
      resizeObserver.observe(containerRef.value!)
    }
  })
})

// ── Preview controls ─────────────────────────────────────────────────────────
function handlePreview(): void {
  previewOpen.value = true
}

function handlePreviewClose(): void {
  previewOpen.value = false
}

function applyPreviewFit(): void {
  if (!svgMetrics.value) return
  previewZoom.value = calculateFitZoom(svgMetrics.value, previewViewportRef.value)
}

function setPreviewZoomAroundCenter(nextZoom: number): void {
  const viewport = previewViewportRef.value
  const previousZoom = previewZoom.value
  const clampedZoom = clampZoom(nextZoom)

  if (!viewport || previousZoom <= 0) {
    previewZoom.value = clampedZoom
    return
  }

  const sourceCenterX = (viewport.scrollLeft + viewport.clientWidth / 2) / previousZoom
  const sourceCenterY = (viewport.scrollTop + viewport.clientHeight / 2) / previousZoom
  previewZoom.value = clampedZoom

  requestAnimationFrame(() => {
    viewport.scrollLeft = Math.max(0, sourceCenterX * clampedZoom - viewport.clientWidth / 2)
    viewport.scrollTop = Math.max(0, sourceCenterY * clampedZoom - viewport.clientHeight / 2)
  })
}

function fitPreview(): void {
  previewFitMode.value = true
  applyPreviewFit()
  const viewport = previewViewportRef.value
  if (viewport) {
    viewport.scrollLeft = 0
    viewport.scrollTop = 0
  }
}

function zoomIn(): void {
  previewFitMode.value = false
  setPreviewZoomAroundCenter(previewZoom.value + PREVIEW_ZOOM_STEP)
}

function zoomOut(): void {
  previewFitMode.value = false
  setPreviewZoomAroundCenter(previewZoom.value - PREVIEW_ZOOM_STEP)
}

function resetZoom(): void {
  previewFitMode.value = false
  setPreviewZoomAroundCenter(1)
}

// Reset preview state when modal closes/opens (handled via Vue watchers)

function stopDraggingPreview(): void {
  const viewport = previewViewportRef.value
  if (viewport && dragState) {
    try {
      viewport.releasePointerCapture(dragState.pointerId)
    } catch {
      // Ignore capture release failures from synthetic test events.
    }
  }
  dragState = null
  isDraggingPreview.value = false
}

// ── Preview pointer handlers ─────────────────────────────────────────────────
function handlePreviewWheel(event: WheelEvent): void {
  if (!event.ctrlKey && !event.metaKey) return

  event.preventDefault()
  const direction = event.deltaY < 0 ? PREVIEW_ZOOM_STEP : -PREVIEW_ZOOM_STEP
  previewFitMode.value = false
  setPreviewZoomAroundCenter(previewZoom.value + direction)
}

function handlePreviewPointerDown(event: PointerEvent): void {
  if (event.pointerType === 'mouse' && event.button !== 0) return

  const viewport = previewViewportRef.value
  if (!viewport) return
  const { x, y } = getPointerPosition(event as any)

  dragState = {
    pointerId: (event as PointerEvent).pointerId,
    startX: x,
    startY: y,
    scrollLeft: viewport.scrollLeft,
    scrollTop: viewport.scrollTop,
  }
  isDraggingPreview.value = true
  viewport.setPointerCapture((event as PointerEvent).pointerId)
}

function handlePreviewPointerMove(event: PointerEvent): void {
  const viewport = previewViewportRef.value
  if (!viewport || !dragState || dragState.pointerId !== (event as PointerEvent).pointerId) return

  event.preventDefault()
  const { x, y } = getPointerPosition(event as any)
  viewport.scrollLeft = dragState.scrollLeft - (x - dragState.startX)
  viewport.scrollTop = dragState.scrollTop - (y - dragState.startY)
}

function handlePreviewPointerUp(event: PointerEvent): void {
  if (!dragState || dragState.pointerId !== (event as PointerEvent).pointerId) return
  stopDraggingPreview()
}

// ── Preview fit mode resize observer ─────────────────────────────────────────
function setupPreviewFitObserver(): void {
  if (!svgMetrics.value || !previewFitMode.value || !previewViewportRef.value) return

  cancelAnimationFrame(fitAnimationFrame)

  const viewport = previewViewportRef.value

  if (previewResizeObserver) {
    previewResizeObserver.disconnect()
  }

  if (typeof ResizeObserver !== 'undefined') {
    previewResizeObserver = new ResizeObserver(() => {
      if (!previewFitMode.value) return
      cancelAnimationFrame(fitAnimationFrame)
      fitAnimationFrame = requestAnimationFrame(applyPreviewFit)
    })
    previewResizeObserver.observe(viewport)
  }

  fitAnimationFrame = requestAnimationFrame(applyPreviewFit)
}

function cleanupPreviewFitObserver(): void {
  cancelAnimationFrame(fitAnimationFrame)
  if (previewResizeObserver) {
    previewResizeObserver.disconnect()
    previewResizeObserver = null
  }
}

// ── Lifecycle ────────────────────────────────────────────────────────────────
// Cleanup moved to second <script> block (Vue 3 dual-script pattern)
function exportToPng(): void {
  (async () => {
    try {
      const svgEl = containerRef.value?.querySelector('svg')
      if (!svgEl) return
      const svgData = new XMLSerializer().serializeToString(svgEl)
      const canvas = document.createElement('canvas')
      const ctx = canvas.getContext('2d')
      if (!ctx) return
      const img = new Image()
      const svgBlob = new Blob([svgData], { type: 'image/svg+xml;charset=utf-8' })
      const url = URL.createObjectURL(svgBlob)
      img.onload = () => {
        canvas.width = img.width * 2
        canvas.height = img.height * 2
        ctx.scale(2, 2)
        ctx.fillStyle = '#fff'
        ctx.fillRect(0, 0, canvas.width, canvas.height)
        ctx.drawImage(img, 0, 0)
        URL.revokeObjectURL(url)
        canvas.toBlob((blob) => {
          if (!blob) return
          const a = document.createElement('a')
          a.href = URL.createObjectURL(blob)
          a.download = `madcop-chart-${Date.now()}.png`
          a.click()
          URL.revokeObjectURL(a.href)
        }, 'image/png')
      }
      img.src = url
    } catch {
      // noop
    }
  })()
}

// ── Expose for parent ────────────────────────────────────────────────────────
defineExpose({
  svg,
  error,
})
</script>

<script lang="ts">
// ── Proper Vue watches (code/theme re-render + preview sync) ─────────────────
import { watch as vueWatch } from 'vue'

let lastCodeWatch = ''
let lastThemeWatch = ''

vueWatch(
  () => [props.code, theme.value],
  ([newCode, newTheme]) => {
    if (newCode !== lastCodeWatch || newTheme !== lastThemeWatch) {
      lastCodeWatch = newCode
      lastThemeWatch = newTheme
      renderCancelled = true
      renderMermaid()
    }
  },
)

vueWatch(
  () => previewOpen.value,
  (open, prevOpen) => {
    if (open && !prevOpen) {
      // Opening modal — reset zoom to fit
      previewZoom.value = 1
      previewFitMode.value = true
      isDraggingPreview.value = false
      dragState = null
    } else if (!open && prevOpen) {
      // Closing modal — cleanup
      cleanupPreviewFitObserver()
    }
  },
)

vueWatch(
  () => [svgMetrics.value, previewOpen.value, previewFitMode.value],
  () => {
    if (previewOpen.value && previewFitMode.value && svgMetrics.value) {
      nextTick(() => {
        setupPreviewFitObserver()
      })
    } else if (!previewFitMode.value || !previewOpen.value) {
      cleanupPreviewFitObserver()
    }
  },
)

// ── Lifecycle ────────────────────────────────────────────────────────────────
onBeforeUnmount(() => {
  renderCancelled = true
  if (resizeObserver) {
    resizeObserver.disconnect()
    resizeObserver = null
  }
  cleanupPreviewFitObserver()
})

<template>
  <!-- Error state -->
  <div
    v-if="error"
    class="my-4 overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-error)]/30"
  >
    <div
      class="flex items-center gap-2 border-b border-[var(--color-error)]/20 bg-[var(--color-error-container)] px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-error)]"
    >
      <span class="material-symbols-outlined text-[14px]" style="fontVariationSettings: 'FILL' 1">error</span>
      Mermaid Error
    </div>
    <div
      class="bg-[var(--color-error-container)]/30 px-3 py-2 font-[var(--font-mono)] text-[11px] text-[var(--color-error)]"
    >
      {{ error }}
    </div>
  </div>

  <!-- Loading state -->
  <div
    v-else-if="!svg"
    class="my-4 flex items-center justify-center rounded-[var(--radius-lg)] border border-[var(--color-border)]/50 bg-[var(--color-surface-container-low)] py-8"
  >
    <div class="flex items-center gap-2 text-[11px] text-[var(--color-text-tertiary)]">
      <span class="material-symbols-outlined animate-spin text-[16px]" style="fontVariationSettings: 'FILL' 1">progress_activity</span>
      Rendering diagram...
    </div>
  </div>

  <!-- Success: diagram rendered -->
  <template v-else>
    <div
      class="my-4 overflow-hidden rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)]/50 bg-[var(--color-surface-container-low)]"
    >
      <!-- Header -->
      <div
        class="flex items-center justify-between border-b border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container)] px-3 py-1.5 text-[11px] text-[var(--color-text-tertiary)]"
      >
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-[14px]" style="fontVariationSettings: 'FILL' 1">account_tree</span>
          <span class="font-semibold uppercase tracking-[0.14em]">Mermaid</span>
        </div>
        <div class="flex items-center gap-1.5">
          <button
            @click="handlePreview"
            class="flex items-center gap-1 rounded-md border border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container-lowest)] px-2 py-1 text-[11px] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-text-primary)]"
          >
            <span class="material-symbols-outlined text-[12px]" style="fontVariationSettings: 'FILL' 1">fullscreen</span>
            Preview
          </button>

          <!-- CopyButton -->
          <button
            type="button"
            @click="handleCopy"
            :class="[
              'rounded-md border border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container-lowest)] px-2 py-1 text-[11px] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-text-primary)]',
            ]"
            :aria-label="copied ? 'Copied' : 'Copy'"
            :title="copied ? 'Copied' : 'Copy'"
          >
            {{ copied ? 'Copied' : 'Copy' }}
          </button>

          <button
            @click="exportToPng"
            class="rounded-md border border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container-lowest)] px-2 py-1 text-[11px] text-[var(--color-text-tertiary)] transition-colors hover:bg-[var(--color-surface-container-high)] hover:text-[var(--color-text-primary)]"
          >
            💾 保存
          </button>
        </div>
      </div>

      <!-- Diagram -->
      <div
        ref="containerRef"
        data-testid="mermaid-diagram-surface"
        class="overflow-auto bg-[var(--color-surface-container-lowest)] p-4 cursor-pointer"
        style="max-height: 400px"
        @click="handlePreview"
      >
        <div class="mx-auto shrink-0 select-none" :style="inlineFrameStyle">
          <div
            :style="inlineCanvasStyle"
            aria-label="Mermaid inline canvas"
            v-html="sanitizedSvg ?? ''"
          />
        </div>
      </div>
    </div>

    <!-- Fullscreen preview modal -->
    <teleport v-if="previewOpen" to="body">
      <div class="fixed inset-0 z-50 flex items-center justify-center">
        <!-- Backdrop -->
        <div
          class="absolute inset-0 bg-[var(--color-overlay-scrim)] transition-opacity duration-200"
          @click="handlePreviewClose"
        />

        <!-- Modal content -->
        <div
          class="glass-panel relative rounded-[var(--radius-xl)] max-h-[85vh] flex flex-col"
          style="width: 1100px; max-width: calc(100vw - 48px)"
          role="dialog"
          aria-modal="true"
          aria-label="Mermaid Diagram"
        >
          <div class="px-6 py-4 overflow-y-auto flex-1 space-y-3">
            <!-- Modal header -->
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2 text-sm font-semibold text-[var(--color-text-primary)]">
                <span class="material-symbols-outlined text-[18px]" style="fontVariationSettings: 'FILL' 1">account_tree</span>
                Mermaid Diagram
              </div>
              <div class="flex items-center gap-2">
                <div class="flex items-center gap-1 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-1 py-1">
                  <button
                    type="button"
                    @click="zoomOut"
                    aria-label="Zoom out"
                    class="flex h-8 w-8 items-center justify-center rounded-md text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                  >
                    <span class="material-symbols-outlined text-[16px]" style="fontVariationSettings: 'FILL' 1">remove</span>
                  </button>
                  <button
                    type="button"
                    @click="resetZoom"
                    class="min-w-[68px] rounded-md px-2 py-1 text-[11px] font-semibold text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                  >
                    {{ Math.round(previewZoom * 100) }}%
                  </button>
                  <button
                    type="button"
                    @click="fitPreview"
                    aria-label="Fit diagram"
                    class="rounded-md px-2 py-1 text-[11px] font-semibold text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                  >
                    Fit
                  </button>
                  <button
                    type="button"
                    @click="zoomIn"
                    aria-label="Zoom in"
                    class="flex h-8 w-8 items-center justify-center rounded-md text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
                  >
                    <span class="material-symbols-outlined text-[16px]" style="fontVariationSettings: 'FILL' 1">add</span>
                  </button>
                </div>
                <!-- CopyButton in modal -->
                <button
                  type="button"
                  @click="handleCopy"
                  class="rounded-md border border-[var(--color-border)] px-2.5 py-1 text-[11px] text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)]"
                  :aria-label="copied ? 'Copied' : 'Copy'"
                >
                  {{ copied ? 'Copied' : 'Copy' }}
                </button>
              </div>
            </div>

            <!-- Preview viewport -->
            <div
              ref="previewViewportRef"
              data-testid="mermaid-preview-viewport"
              class="overflow-auto rounded-xl bg-[var(--color-surface-container-lowest)]"
              :style="{
                maxHeight: '75vh',
                cursor: isDraggingPreview ? 'grabbing' : 'grab',
              }"
              @wheel="handlePreviewWheel"
              @pointerdown="handlePreviewPointerDown"
              @pointermove="handlePreviewPointerMove"
              @pointerup="handlePreviewPointerUp"
              @pointercancel="handlePreviewPointerUp"
              @pointerleave="handlePreviewPointerUp"
            >
              <div class="min-h-full min-w-full p-6">
                <div class="mx-auto shrink-0 select-none" :style="previewFrameStyle">
                  <div
                    ref="previewContentRef"
                    :style="previewCanvasStyle"
                    :data-dragging="isDraggingPreview ? 'true' : 'false'"
                    aria-label="Mermaid preview canvas"
                    v-html="sanitizedSvg ?? ''"
                  />
                </div>
              </div>
            </div>

            <!-- Help text -->
            <div class="text-[11px] text-[var(--color-text-tertiary)]">
              Use the zoom controls to enlarge the diagram. Drag inside the preview to pan, or use the trackpad, mouse wheel, and scrollbars. Hold Ctrl/Command while scrolling to zoom.
            </div>
          </div>

          <!-- Close button -->
          <button
            type="button"
            @click="handlePreviewClose"
            aria-label="Close dialog"
            class="absolute top-4 right-4 flex h-9 w-9 items-center justify-center rounded-full text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]"
          >
            <span class="material-symbols-outlined text-[18px]" style="fontVariationSettings: 'FILL' 1">close</span>
          </button>
        </div>
      </div>
    </teleport>
  </template>
</template>

<style scoped>
/* No scoped styles — all styling via Tailwind and CSS custom properties */
</style>
