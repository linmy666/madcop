<script setup lang="ts">
/**
 * Sprint 6 — Knowledge Canvas (知识画布).
 * Renders the brain graph with cytoscape + fcose force-directed layout.
 *
 * Interactions:
 *  - Drag nodes; positions persist to localStorage.
 *  - Click a node → open NodeDetail drawer.
 *  - Right-click a node → "链接到…" picker to create an edge.
 *  - Double-click empty canvas → open NodeEditor to create a new node.
 *  - Wheel to zoom; built-in pan.
 */
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import cytoscape from 'cytoscape'
// fcose registers itself as a layout; the import has the side-effect of
// attaching the ext to the cytoscape core via `cytoscape.use()`.
// The package ships no type declarations, so we declare a minimal shape.
import fcose from 'cytoscape-fcose'
import type { Core, EventObject, NodeSingular } from 'cytoscape'
import { brainApi, type BrainNode, type BrainEdge } from '../../api/brain'
import NodeDetail from './NodeDetail.vue'
import NodeEditor from './NodeEditor.vue'

// Minimal ambient declaration for the untyped cytoscape-fcose extension.
// The package exports the extension as a callable (UMD) — passed to
// `cytoscape.use(fcose)` to register the 'fcose' layout.
declare module 'cytoscape-fcose' {
  const ext: ((cy: typeof cytoscape) => void) & { register?: (cy: typeof cytoscape) => void }
  export default ext
}

// Register fcose — wrapped in try/catch: throws if already registered
// (HMR reload / duplicate import), which caused "出现异常" on Canvas open.
try {
  cytoscape.use(fcose)
} catch (_e: any) { /* already registered */ }

const props = defineProps<{
  workspace?: string
}>()

const containerRef = ref<HTMLDivElement | null>(null)
const loading = ref(true)
const errorMsg = ref('')
const empty = ref(false)
const nodeCount = ref(0)

const selectedNode = ref<BrainNode | null>(null)
const editorOpen = ref(false)
const editorExisting = ref<BrainNode | null>(null)

// Right-click context menu state for "link to…"
const ctxMenu = ref<{ x: number; y: number; fromSlug: string } | null>(null)
const linkPickerOpen = ref(false)
const linkFromSlug = ref('')
const allNodeSlugs = ref<{ slug: string; title: string }[]>([])

let cy: Core | null = null
const POS_KEY = 'madcop_brain_positions_v1'

// Muted palette aligned with the neutral design language: ink/zinc for
// the common types, semantic green/amber/red reserved for project/person/
// event. (skill nodes previously dominated the canvas in violet.)
const TYPE_COLORS: Record<string, string> = {
  concept: '#3F3F46',
  skill: '#71717A',
  project: '#16A34A',
  person: '#CA8A04',
  event: '#BA1A1A',
}

function loadPositions(): Record<string, { x: number; y: number }> {
  try {
    return JSON.parse(localStorage.getItem(POS_KEY) || '{}')
  } catch {
    return {}
  }
}
function savePositions(positions: Record<string, { x: number; y: number }>) {
  try {
    localStorage.setItem(POS_KEY, JSON.stringify(positions))
  } catch {
    /* quota / disabled — ignore */
  }
}

async function loadGraph() {
  loading.value = true
  errorMsg.value = ''
  try {
    const graph = await brainApi.graph(props.workspace)
    nodeCount.value = graph.nodes.length
    empty.value = graph.nodes.length === 0
    // The container div lives in the v-else branch of `loading` — drop the
    // spinner and let the DOM render BEFORE creating cytoscape, or
    // containerRef is null and the graph mounts into nothing (blank
    // canvas with no error).
    loading.value = false
    await nextTick()
    renderGraph(graph)
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  } finally {
    loading.value = false
  }
}

function renderGraph(graph: { nodes: BrainNode[]; edges: BrainEdge[] }) {
  if (!cy) initCytoscape()
  if (!cy) return
  const positions = loadPositions()

  cy.elements().remove()
  const els: cytoscape.ElementDefinition[] = graph.nodes.map((n) => ({
    group: 'nodes',
    data: {
      id: n.slug,
      label: n.title || n.slug,
      type: n.type,
      // stash the full node so the detail drawer can read it.
      raw: n,
    },
    position: positions[n.slug],
  }))
  els.push(
    ...graph.edges.map((e) => ({
      group: 'edges',
      data: {
        id: e.id,
        source: e.source,
        target: e.target,
        label: e.label,
      },
    })),
  )
  cy.add(els)

  // Preserve saved positions for nodes that had them; fcose the rest.
  const positioned = Object.keys(positions)
  if (positioned.length === 0 || positioned.length < graph.nodes.length) {
    runLayout()
  } else {
    cy.fit(undefined, 60)
  }
  allNodeSlugs.value = graph.nodes.map((n) => ({ slug: n.slug, title: n.title || n.slug }))
}

function runLayout() {
  if (!cy) return
  // fcose is an untyped extension whose registration can silently fail
  // (async chunk load, version drift) — a dead layout left 21 nodes
  // positioned at (0,0) inside a blank canvas. Fall back to the built-in
  // 'grid' if fcose isn't registered, so the graph ALWAYS becomes visible.
  // grid FIRST: it always succeeds, guaranteeing a readable spread even
  // when the fcose extension silently no-ops (unregistered layout does
  // not throw — the old fcose-then-break order left the grid fallback
  // unreachable and nodes stacked in their stale positions).
  const layouts: object[] = [
    { name: 'grid', animate: true, animationDuration: 400, fit: true, padding: 60,
      sort: (a: any, b: any) => String(a.id()).localeCompare(String(b.id())) },
    {
      name: 'fcose',
      animate: true,
      animationDuration: 600,
      nodeRepulsion: () => 8000,
      idealEdgeLength: () => 120,
      nodeSeparation: 90,
      randomize: true,
    },
  ]
  for (const opts of layouts) {
    try {
      const layout = cy.layout(opts as object)
      layout.run()
      break
    } catch (e) {
      console.warn('[knowledge-canvas] layout failed, trying fallback', e)
    }
  }
  // Safety net: even if every layout dies, force nodes into view.
  if (cy.nodes().nonempty()) {
    const box = cy.nodes().boundingBox()
    if (!box || (box.w === 0 && box.h === 0)) {
      cy.nodes().positions((n: any, i: number) => ({
        x: 160 + (i % 6) * 180,
        y: 120 + Math.floor(i / 6) * 140,
      }))
    }
    cy.fit(undefined, 60)
  }
  void nextTick(() => persistPositions())
}

function persistPositions() {
  if (!cy) return
  const positions: Record<string, { x: number; y: number }> = {}
  cy.nodes().forEach((n: NodeSingular) => {
    const p = n.position()
    positions[n.id()] = { x: p.x, y: p.y }
  })
  savePositions(positions)
}

function initCytoscape() {
  if (!containerRef.value) return
  // Cytoscape paints to <canvas>, so CSS var() does NOT resolve there —
  // the tokens must be read from the computed theme and passed as real
  // values (var() left every label the fallback huge black smear).
  const cs = getComputedStyle(document.documentElement)
  const tok = (name: string, fb: string) => cs.getPropertyValue(name).trim() || fb
  const INK = tok('--color-text-primary', '#0D0D0D')
  const MUTED = tok('--color-text-tertiary', '#8F8F8F')
  const SURFACE = tok('--color-surface', '#FFFFFF')
  const BORDER = tok('--color-border', '#E5E5E5')
  cy = cytoscape({
    container: containerRef.value,
    wheelSensitivity: 0.25,
    style: [
      {
        selector: 'node',
        style: {
          'background-color': (ele: any) => TYPE_COLORS[ele.data('type')] ?? '#8F8F8F',
          label: 'data(label)',
          color: INK,
          'text-valign': 'bottom',
          'text-halign': 'center',
          'text-margin-y': 6,
          'font-size': 11,
          'text-wrap': 'wrap',
          'text-max-width': 150,
          'text-outline-color': SURFACE,
          'text-outline-width': 2,
          width: 36,
          height: 36,
          'border-width': 2,
          'border-color': SURFACE,
        },
      },
      {
        selector: 'node:selected',
        style: {
          'border-width': 3,
          'border-color': '#52525B',
          width: 42,
          height: 42,
        },
      },
      {
        selector: 'edge',
        style: {
          width: 1.5,
          'line-color': BORDER,
          'target-arrow-color': BORDER,
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
          label: 'data(label)',
          'font-size': 9,
          color: MUTED,
          'text-background-color': SURFACE,
          'text-background-opacity': 0.9,
          'text-background-padding': 1,
          'text-rotation': 'autorotate',
        },
      },
    ] as unknown as cytoscape.Stylesheet[],
    elements: [],
  })

  cy.on('tap', 'node', (evt: EventObject) => {
    openDetail(evt.target.id())
  })
  cy.on('cxttap', 'node', (evt: EventObject) => {
    const renderedPos = evt.renderedPosition
    const containerRect = containerRef.value?.getBoundingClientRect()
    ctxMenu.value = {
      x: (containerRect?.left ?? 0) + (renderedPos?.x ?? 0),
      y: (containerRect?.top ?? 0) + (renderedPos?.y ?? 0),
      fromSlug: evt.target.id(),
    }
  })
  // Double-click on empty canvas → create node.
  let lastTap = 0
  cy.on('tap', (evt: EventObject) => {
    if (evt.target === cy) {
      const now = Date.now()
      if (now - lastTap < 350) {
        startCreate()
      }
      lastTap = now
    }
  })
  cy.on('dragfree', 'node', () => persistPositions())
}

async function openDetail(slug: string) {
  try {
    const { node } = await brainApi.node(slug)
    selectedNode.value = node
  } catch {
    /* ignore */
  }
}

function startCreate() {
  editorExisting.value = null
  editorOpen.value = true
}
function startEdit(node: BrainNode) {
  editorExisting.value = node
  editorOpen.value = true
  selectedNode.value = null
}

async function onSave(payload: { slug: string; title: string; body: string; type: string; tags: string[]; staleAfterDays?: number | null }) {
  editorOpen.value = false
  try {
    await brainApi.saveNode(payload, props.workspace)
    await loadGraph()
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  }
}

async function onDelete(slug: string) {
  if (!confirm(`确定删除节点 ${slug}？相关链接也会一并删除。`)) return
  selectedNode.value = null
  try {
    await brainApi.deleteNode(slug)
    await loadGraph()
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  }
}

/** Sprint 6 / P1-2 — delete a single directed edge, then refresh. */
async function onDeleteLink(fromSlug: string, toSlug: string) {
  try {
    await brainApi.deleteLink(fromSlug, toSlug)
    await loadGraph()
    // Re-open the detail so the links list updates.
    await openDetail(fromSlug)
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  }
}

async function navigateTo(slug: string) {
  await openDetail(slug)
  if (cy) {
    cy.getElementById(slug).select()
  }
}

function startLinkFromCtx() {
  if (!ctxMenu.value) return
  linkFromSlug.value = ctxMenu.value.fromSlug
  ctxMenu.value = null
  linkPickerOpen.value = true
}

async function confirmLink(toSlug: string) {
  linkPickerOpen.value = false
  if (!linkFromSlug.value || toSlug === linkFromSlug.value) return
  try {
    const res = await brainApi.link(linkFromSlug.value, toSlug)
    if (!res.ok) {
      errorMsg.value = res.error || '链接失败（节点可能不存在）'
      return
    }
    await loadGraph()
  } catch (e) {
    errorMsg.value = e instanceof Error ? e.message : String(e)
  }
}

onMounted(async () => {
  await loadGraph()
})

onBeforeUnmount(() => {
  cy?.destroy()
  cy = null
})

// Re-render when workspace changes.
watch(() => props.workspace, () => loadGraph())

// Close context menu on outside click.
function onOverlayClick() {
  ctxMenu.value = null
}
</script>

<template>
  <div class="kc-root" @click="onOverlayClick">
    <!-- Toolbar -->
    <header class="kc-toolbar">
      <div class="kc-titlegroup">
        <h1 class="kc-title">知识画布</h1>
        <span class="kc-count">{{ nodeCount }} 个节点</span>
      </div>
      <div class="kc-actions">
        <button class="kc-btn" title="重新布局" @click="runLayout">
          <span class="material-symbols-outlined">hub</span>
          重新布局
        </button>
        <button class="kc-btn" title="刷新" @click="loadGraph">
          <span class="material-symbols-outlined">refresh</span>
          刷新
        </button>
        <button class="kc-btn kc-btn--primary" @click="startCreate">
          <span class="material-symbols-outlined">add</span>
          新建节点
        </button>
      </div>
    </header>

    <!-- Canvas area -->
    <div class="kc-canvas-wrap">
      <div v-if="loading" class="kc-status">
        <div class="kc-spinner"></div>
        <p>加载知识图谱…</p>
      </div>

      <div v-else-if="errorMsg" class="kc-status kc-status--error">
        <span class="material-symbols-outlined">error</span>
        <p>{{ errorMsg }}</p>
        <button class="kc-btn" @click="loadGraph">重试</button>
      </div>

      <template v-else>
        <div ref="containerRef" class="kc-cytoscape"></div>
        <div v-if="empty" class="kc-empty-overlay">
          <div class="kc-empty-icon">
            <span class="material-symbols-outlined">account_tree</span>
          </div>
          <h3>还没有知识节点</h3>
          <p>和 Agent 聊天让它记住知识，或双击空白处新建节点。</p>
          <button class="kc-btn kc-btn--primary" @click="startCreate">
            <span class="material-symbols-outlined">add</span>
            新建第一个节点
          </button>
        </div>
      </template>
    </div>

    <!-- Right-click context menu -->
    <div
      v-if="ctxMenu"
      class="kc-ctxmenu"
      :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
      @click.stop
    >
      <button class="kc-ctx-item" @click="openDetail(ctxMenu.fromSlug)">
        <span class="material-symbols-outlined">description</span>
        查看详情
      </button>
      <button class="kc-ctx-item" @click="startLinkFromCtx">
        <span class="material-symbols-outlined">link</span>
        链接到…
      </button>
    </div>

    <!-- Link picker -->
    <Teleport to="body">
      <div v-if="linkPickerOpen" class="kc-picker-overlay" @click.self="linkPickerOpen = false">
        <div class="kc-picker">
          <h3 class="kc-picker-title">链接 {{ linkFromSlug }} → ?</h3>
          <p class="kc-picker-sub">选择目标节点</p>
          <ul class="kc-picker-list">
            <li v-for="n in allNodeSlugs.filter((x) => x.slug !== linkFromSlug)" :key="n.slug">
              <button class="kc-picker-item" @click="confirmLink(n.slug)">
                <span class="material-symbols-outlined">arrow_forward</span>
                {{ n.title }}
                <code>{{ n.slug }}</code>
              </button>
            </li>
          </ul>
          <button class="kc-btn kc-picker-cancel" @click="linkPickerOpen = false">取消</button>
        </div>
      </div>
    </Teleport>

    <!-- Detail drawer -->
    <NodeDetail
      :node="selectedNode"
      @close="selectedNode = null"
      @edit="startEdit"
      @delete="onDelete"
      @navigate="navigateTo"
      @delete-link="onDeleteLink"
    />

    <!-- Editor modal -->
    <NodeEditor
      v-if="editorOpen"
      :existing="editorExisting"
      @close="editorOpen = false"
      @save="onSave"
    />
  </div>
</template>

<style scoped>
.kc-root {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  overflow: hidden;
}
.kc-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 18px;
  border-bottom: 1px solid var(--color-border);
  flex: none;
}
.kc-titlegroup {
  display: flex;
  align-items: baseline;
  gap: 10px;
}
.kc-title {
  font-size: 17px;
  font-weight: 600;
  margin: 0;
  color: var(--color-text-primary);
}
.kc-count {
  font-size: 12px;
  color: var(--color-text-tertiary);
}
.kc-actions {
  display: flex;
  gap: 6px;
}
.kc-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--color-text-primary);
  cursor: pointer;
  font-family: inherit;
  transition: background 120ms;
}
.kc-btn:hover {
  background: var(--color-surface-container-low);
}
.kc-btn .material-symbols-outlined {
  font-size: 15px;
}
.kc-btn--primary {
  background: var(--color-brand, #0a0a0a);
  color: #fff;
  border-color: var(--color-brand, #0a0a0a);
}
.kc-btn--primary:hover {
  background: #1f2937;
}

.kc-canvas-wrap {
  position: relative;
  flex: 1;
  min-height: 0;
}
.kc-cytoscape {
  position: absolute;
  inset: 0;
  background: var(--color-surface-container-lowest);
}

.kc-status {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--color-text-tertiary);
  background: var(--color-surface);
}
.kc-status p {
  margin: 0;
  font-size: 13px;
}
.kc-status--error .material-symbols-outlined {
  font-size: 32px;
  color: #b91c1c;
}
.kc-spinner {
  width: 28px;
  height: 28px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-brand, #0a0a0a);
  border-radius: 50%;
  animation: kc-spin 0.8s linear infinite;
}
@keyframes kc-spin {
  to {
    transform: rotate(360deg);
  }
}

.kc-empty-overlay {
  position: absolute;
  inset: 0;
  z-index: 4;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
  pointer-events: none;
}
.kc-empty-overlay > * {
  pointer-events: auto;
}
.kc-empty-overlay .kc-empty-icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: var(--color-surface-container);
  color: var(--color-text-tertiary);
  margin-bottom: 4px;
}
.kc-empty-overlay .material-symbols-outlined {
  font-size: 28px;
}
.kc-empty-overlay h3 {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.kc-empty-overlay p {
  margin: 0 0 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.kc-ctxmenu {
  position: fixed;
  z-index: 50;
  min-width: 160px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.16);
  padding: 4px;
  overflow: hidden;
}
.kc-ctx-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 13px;
  color: var(--color-text-primary);
  font-family: inherit;
  border-radius: 5px;
  text-align: left;
}
.kc-ctx-item:hover {
  background: var(--color-surface-container);
}
.kc-ctx-item .material-symbols-outlined {
  font-size: 16px;
  color: var(--color-text-tertiary);
}

.kc-picker-overlay {
  position: fixed;
  inset: 0;
  z-index: 90;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.4);
}
.kc-picker {
  width: min(420px, 92vw);
  max-height: 70vh;
  display: flex;
  flex-direction: column;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 18px;
}
.kc-picker-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 2px;
  color: var(--color-text-primary);
}
.kc-picker-sub {
  font-size: 12px;
  color: var(--color-text-tertiary);
  margin: 0 0 12px;
}
.kc-picker-list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.kc-picker-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  background: transparent;
  border: none;
  cursor: pointer;
  font-size: 13px;
  color: var(--color-text-primary);
  font-family: inherit;
  border-radius: 6px;
  text-align: left;
}
.kc-picker-item:hover {
  background: var(--color-surface-container);
}
.kc-picker-item .material-symbols-outlined {
  font-size: 15px;
  color: var(--color-text-tertiary);
}
.kc-picker-item code {
  margin-left: auto;
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.kc-picker-cancel {
  align-self: flex-end;
  margin-top: 12px;
}
</style>
