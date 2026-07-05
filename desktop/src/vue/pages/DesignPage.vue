<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount } from 'vue'
import DesignCanvas from '@/vue/components/design/DesignCanvas.vue'
import { useDesignStore } from '../stores/design'
import { useGDDStore } from '../stores/gdd'
import { Button } from '@/components/ui/button'

const designStore = useDesignStore()
const gddStore = useGDDStore()

const showSystemPanel = ref(true)
const showEntityPanel = ref(true)
const showRegistryPanel = ref(true)
const showImportModal = ref(false)
const showExportModal = ref(false)
const activeSystemId = ref<string | null>(null)
const activeEntityId = ref<string | null>(null)
const newSystemName = ref('')
const newEntityName = ref('')
const searchQuery = ref('')
const activeTab = ref<'systems' | 'entities' | 'registry'>('systems')
const contextMenu = ref<{ x: number; y: number; target?: string; type?: string } | null>(null)
const zoomLevel = ref(100)
const gridSize = ref(20)
const showGrid = ref(true)
const snapToGrid = ref(false)
const theme = ref<'light' | 'dark'>('dark')
const layoutMode = ref<'canvas' | 'split' | 'panel'>('canvas')
const collapsedPanels = ref<string[]>([])

const systems = ref(designStore.systems)
const entities = ref(designStore.entities)
const gddRefs = ref(designStore.gddRefs)

// Color palette
const palette = {
  bg: '#0a0a0a',
  surface: '#171717',
  surface2: '#1f1f1f',
  border: '#262626',
  border2: '#404040',
  text: '#ececec',
  textMuted: '#a3a3a3',
  textDim: '#737373',
  accent: '#3b82f6',
  accent2: '#8b5cf6',
  accent3: '#06b6d4',
  success: '#22c55e',
  warning: '#f59e0b',
  error: '#ef4444',
}

// Compute filtered systems/entities based on search
const filteredSystems = ref(systems.value.filter(s =>
  s.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
  s.description.toLowerCase().includes(searchQuery.value.toLowerCase())
))

const filteredEntities = ref(entities.value.filter(e =>
  e.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
  (e.category && e.category.toLowerCase().includes(searchQuery.value.toLowerCase()))
))

// Handlers
function togglePanel(panel: string) {
  collapsedPanels.value = collapsedPanels.value.includes(panel)
    ? collapsedPanels.value.filter(p => p !== panel)
    : [...collapsedPanels.value, panel]
}

function handleAddSystem() {
  if (!newSystemName.value.trim()) return
  designStore.addSystem({
    id: `sys_${Date.now()}`,
    name: newSystemName.value.trim(),
    description: '',
    entities: [],
    gddRefs: [],
    status: 'draft',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  })
  newSystemName.value = ''
  filteredSystems.value = systems.value.filter(s =>
    s.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
    s.description.toLowerCase().includes(searchQuery.value.toLowerCase())
  )
}

function handleAddEntity(systemId: string) {
  if (!newEntityName.value.trim()) return
  designStore.addEntity(systemId, {
    id: `ent_${Date.now()}`,
    name: newEntityName.value.trim(),
    category: 'general',
    properties: [],
    relationships: [],
    gddRefs: [],
    status: 'draft',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  })
  newEntityName.value = ''
  filteredEntities.value = entities.value.filter(e =>
    e.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
    (e.category && e.category.toLowerCase().includes(searchQuery.value.toLowerCase()))
  )
}

function handleDeleteSystem(systemId: string) {
  designStore.deleteSystem(systemId)
  filteredSystems.value = systems.value.filter(s =>
    s.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
    s.description.toLowerCase().includes(searchQuery.value.toLowerCase())
  )
}

function handleDeleteEntity(systemId: string, entityId: string) {
  designStore.deleteEntity(systemId, entityId)
  filteredEntities.value = entities.value.filter(e =>
    e.name.toLowerCase().includes(searchQuery.value.toLowerCase()) ||
    (e.category && e.category.toLowerCase().includes(searchQuery.value.toLowerCase()))
  )
}

function handleOpenSystem(systemId: string) {
  activeSystemId.value = activeSystemId.value === systemId ? null : systemId
}

function handleOpenEntity(entityId: string) {
  activeEntityId.value = activeEntityId.value === entityId ? null : entityId
}

function handleContextMenu(e: MouseEvent, target: string, type: string) {
  contextMenu.value = { x: e.clientX, y: e.clientY, target, type }
}

function handleCanvasClick() {
  contextMenu.value = null
}

function handleZoom(delta: number) {
  zoomLevel.value = Math.max(25, Math.min(200, zoomLevel.value + delta))
}

function handleToggleGrid() {
  showGrid.value = !showGrid.value
}

function handleToggleSnap() {
  snapToGrid.value = !snapToGrid.value
}

function handleExport() {
  showExportModal.value = true
}

function handleImport() {
  showImportModal.value = true
}

function handleToggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
}

function handleToggleLayout() {
  const layouts: ('canvas' | 'split' | 'panel')[] = ['canvas', 'split', 'panel']
  const idx = layouts.indexOf(layoutMode.value)
  layoutMode.value = layouts[(idx + 1) % layouts.length]
}

function handleGDDLink(systemId: string, gddRef: string) {
  designStore.addGDDRef(systemId, gddRef)
}

function handleUpdateSystem(systemId: string, updates: any) {
  designStore.updateSystem(systemId, updates)
}

function handleUpdateEntity(systemId: string, entityId: string, updates: any) {
  designStore.updateEntity(systemId, entityId, updates)
}

function handleMoveEntity(systemId: string, entityId: string, newSystemId: string) {
  designStore.moveEntity(systemId, entityId, newSystemId)
}

// Keyboard shortcuts
function handleKeyDown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    contextMenu.value = null
    showImportModal.value = false
    showExportModal.value = false
  }
  if (e.key === 'Delete' && activeEntityId.value) {
    const system = systems.value.find(s => s.entities.some(e => e.id === activeEntityId.value))
    if (system) {
      handleDeleteEntity(system.id, activeEntityId.value!)
    }
  }
  if ((e.metaKey || e.ctrlKey) && e.key === 's') {
    e.preventDefault()
    designStore.save()
  }
  if ((e.metaKey || e.ctrlKey) && e.key === 'n') {
    e.preventDefault()
    handleAddSystem()
  }
  if (e.key === ' ' && activeSystemId.value) {
    e.preventDefault()
    handleAddEntity(activeSystemId.value)
  }
}

// Lifecycle
onMounted(() => {
  window.addEventListener('keydown', handleKeyDown)
  window.addEventListener('click', handleCanvasClick)
  designStore.load()
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', handleKeyDown)
  window.removeEventListener('click', handleCanvasClick)
})

// Expose for template
defineExpose({
  systems,
  entities,
  gddRefs,
  filteredSystems: () => filteredSystems.value,
  filteredEntities: () => filteredEntities.value,
  showSystemPanel,
  showEntityPanel,
  showRegistryPanel,
  activeSystemId,
  activeEntityId,
  searchQuery,
  activeTab,
  zoomLevel,
  gridSize,
  showGrid,
  snapToGrid,
  theme,
  layoutMode,
  collapsedPanels,
  palette,
})
</script>

<template>
  <div
    class="design-page flex h-screen w-screen overflow-hidden"
    :class="[theme === 'dark' ? 'bg-[#0a0a0a]' : 'bg-white', theme]"
    :style="{ '--color-bg': palette.bg, '--color-surface': palette.surface, '--color-surface2': palette.surface2, '--color-border': palette.border, '--color-border2': palette.border2, '--color-text': palette.text, '--color-text-muted': palette.textMuted, '--color-text-dim': palette.textDim, '--color-accent': palette.accent, '--color-accent2': palette.accent2, '--color-accent3': palette.accent3, '--color-success': palette.success, '--color-warning': palette.warning, '--color-error': palette.error }"
    @click="handleCanvasClick"
  >
    <!-- Top Bar -->
    <header class="topbar flex h-12 w-full items-center justify-between border-b border-[var(--color-border)] bg-[var(--color-surface)] px-4 z-50">
      <div class="flex items-center gap-3">
        <span class="material-symbols-outlined text-[var(--color-accent)] text-lg">design_services</span>
        <h1 class="text-sm font-semibold text-[var(--color-text)]">Game Design Studio</h1>
        <span class="text-xs text-[var(--color-text-dim)] ml-2">
          {{ systems.length }} systems · {{ entities.length }} entities
        </span>
      </div>
      <div class="flex items-center gap-2">
        <!-- Search -->
        <div class="relative">
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search systems, entities..."
            class="h-7 w-48 rounded border border-[var(--color-border)] bg-[var(--color-surface2)] px-2 py-1 text-xs text-[var(--color-text)] placeholder:text-[var(--color-text-dim)] outline-none focus:border-[var(--color-accent)] transition-colors"
          />
          <span class="material-symbols-outlined absolute right-2 top-1/2 -translate-y-1/2 text-[var(--color-text-dim)] text-sm">search</span>
        </div>
        <!-- Zoom controls -->
        <div class="flex items-center gap-1 rounded border border-[var(--color-border)] bg-[var(--color-surface2)] p-1">
          <button @click="handleZoom(-10)" class="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">
            <span class="material-symbols-outlined text-sm">remove</span>
          </button>
          <span class="px-1 text-xs text-[var(--color-text-muted)] min-w-[3rem] text-center">{{ zoomLevel }}%</span>
          <button @click="handleZoom(10)" class="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">
            <span class="material-symbols-outlined text-sm">add</span>
          </button>
          <button @click="zoomLevel = 100" class="flex h-5 items-center px-1 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-border)] rounded transition-colors">
            Reset
          </button>
        </div>
        <!-- Grid toggle -->
        <button @click="handleToggleGrid" class="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors" :title="showGrid ? 'Hide grid' : 'Show grid'">
          <span class="material-symbols-outlined text-sm">{{ showGrid ? 'grid_on' : 'grid_off' }}</span>
        </button>
        <!-- Snap toggle -->
        <button @click="handleToggleSnap" class="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors" :title="snapToGrid ? 'Snap off' : 'Snap on'">
          <span class="material-symbols-outlined text-sm">{{ snapToGrid ? 'layers' : 'layers_clear' }}</span>
        </button>
        <!-- Theme toggle -->
        <button @click="handleToggleTheme" class="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors" :title="theme === 'dark' ? 'Switch to light' : 'Switch to dark'">
          <span class="material-symbols-outlined text-sm">{{ theme === 'dark' ? 'light_mode' : 'dark_mode' }}</span>
        </button>
        <!-- Layout toggle -->
        <button @click="handleToggleLayout" class="flex h-7 w-7 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors" :title="`Layout: ${layoutMode}`">
          <span class="material-symbols-outlined text-sm">{{ layoutMode === 'canvas' ? 'web' : layoutMode === 'split' ? 'panorama' : 'view_column' }}</span>
        </button>
        <!-- Import -->
        <button @click="handleImport" class="flex h-7 items-center gap-1 rounded px-2 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">
          <span class="material-symbols-outlined text-sm">upload_file</span>
          Import
        </button>
        <!-- Export -->
        <button @click="handleExport" class="flex h-7 items-center gap-1 rounded px-2 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">
          <span class="material-symbols-outlined text-sm">download</span>
          Export
        </button>
        <!-- Save -->
        <button @click="designStore.save()" class="flex h-7 items-center gap-1 rounded bg-[var(--color-accent)] px-3 text-xs font-medium text-white hover:bg-[var(--color-accent)]/90 transition-colors">
          <span class="material-symbols-outlined text-sm">save</span>
          Save
        </button>
      </div>
    </header>

    <!-- Main Content -->
    <main class="main flex flex-1 overflow-hidden">
      <!-- Left Panel: Systems -->
      <aside
        v-if="showSystemPanel && layoutMode !== 'panel'"
        class="left-panel flex flex-col border-r border-[var(--color-border)] bg-[var(--color-surface)]"
        :class="[layoutMode === 'split' ? 'w-96' : 'w-64']"
      >
        <!-- Panel Header -->
        <div class="panel-header flex h-10 items-center justify-between border-b border-[var(--color-border)] px-3">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-[var(--color-accent)] text-sm">system_security</span>
            <h2 class="text-xs font-semibold uppercase tracking-wider text-[var(--color-text)]">Systems</h2>
            <span class="rounded bg-[var(--color-surface2)] px-1.5 py-0.5 text-[10px] text-[var(--color-text-dim)]">{{ systems.length }}</span>
          </div>
          <div class="flex items-center gap-1">
            <button @click="handleAddSystem" class="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors" title="New system">
              <span class="material-symbols-outlined text-sm">add</span>
            </button>
            <button @click="togglePanel('systems')" class="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors" title="Collapse">
              <span class="material-symbols-outlined text-sm">chevron_left</span>
            </button>
          </div>
        </div>

        <!-- New System Form -->
        <div v-if="newSystemName" class="new-system-form border-b border-[var(--color-border)] bg-[var(--color-surface2)] p-3">
          <input
            v-model="newSystemName"
            type="text"
            placeholder="System name..."
            class="w-full rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1.5 text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-dim)] outline-none focus:border-[var(--color-accent)] transition-colors"
            @keyup.enter="handleAddSystem"
          />
          <div class="mt-2 flex gap-2">
            <button @click="handleAddSystem" class="flex-1 rounded bg-[var(--color-accent)] px-2 py-1 text-xs font-medium text-white hover:bg-[var(--color-accent)]/90 transition-colors">Create</button>
            <button @click="newSystemName = ''" class="rounded border border-[var(--color-border)] px-2 py-1 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">Cancel</button>
          </div>
        </div>

        <!-- Systems List -->
        <div class="systems-list flex-1 overflow-y-auto p-2">
          <div v-if="filteredSystems.length === 0" class="flex flex-col items-center justify-center py-8 text-center">
            <span class="material-symbols-outlined text-3xl text-[var(--color-text-dim)]">inventory_2</span>
            <p class="mt-2 text-xs text-[var(--color-text-dim)]">No systems yet</p>
            <button @click="handleAddSystem" class="mt-3 rounded bg-[var(--color-accent)] px-3 py-1 text-xs font-medium text-white hover:bg-[var(--color-accent)]/90 transition-colors">Create first system</button>
          </div>
          <div
            v-for="system in filteredSystems"
            :key="system.id"
            class="system-card group mb-2 rounded border border-[var(--color-border)] bg-[var(--color-surface2)] p-3 transition-all hover:border-[var(--color-border2)] cursor-pointer"
            :class="[activeSystemId === system.id ? 'border-[var(--color-accent)] ring-1 ring-[var(--color-accent)]' : '']"
            @click="handleOpenSystem(system.id)"
            @contextmenu.prevent="handleContextMenu($event, system.id, 'system')"
          >
            <div class="flex items-start justify-between">
              <div class="flex-1 min-w-0">
                <div class="flex items-center gap-1.5">
                  <span class="material-symbols-outlined text-sm" :class="[system.status === 'complete' ? 'text-[var(--color-success)]' : system.status === 'in-progress' ? 'text-[var(--color-warning)]' : 'text-[var(--color-text-dim)]']">
                    {{ system.status === 'complete' ? 'check_circle' : system.status === 'in-progress' ? 'edit' : 'outline' }}
                  </span>
                  <h3 class="truncate text-sm font-medium text-[var(--color-text)]">{{ system.name }}</h3>
                </div>
                <p v-if="system.description" class="mt-1 truncate text-[10px] text-[var(--color-text-dim)]">{{ system.description }}</p>
                <div class="mt-1.5 flex items-center gap-2">
                  <span class="text-[10px] text-[var(--color-text-dim)]">{{ system.entities.length }} entities</span>
                  <span v-if="system.gddRefs.length" class="text-[10px] text-[var(--color-accent)]">{{ system.gddRefs.length }} GDD refs</span>
                </div>
              </div>
              <div class="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <button @click.stop="handleOpenEntity(activeEntityId ? activeEntityId : undefined)" class="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-[var(--color-border)] transition-colors">
                  <span class="material-symbols-outlined text-sm">edit</span>
                </button>
                <button @click.stop="handleDeleteSystem(system.id)" class="flex h-5 w-5 items-center justify-center rounded text-[var(--color-text-dim)] hover:bg-[var(--color-border)] hover:text-[var(--color-error)] transition-colors">
                  <span class="material-symbols-outlined text-sm">delete</span>
                </button>
              </div>
            </div>
            <!-- System entities preview -->
            <div v-if="activeSystemId === system.id" class="mt-2 border-t border-[var(--color-border)] pt-2">
              <div v-if="system.entities.length === 0" class="text-center py-3">
                <span class="material-symbols-outlined text-xl text-[var(--color-text-dim)]">person_add</span>
                <p class="mt-1 text-[10px] text-[var(--color-text-dim)]">No entities</p>
                <input
                  v-if="newEntityName && activeSystemId === system.id"
                  v-model="newEntityName"
                  type="text"
                  placeholder="Entity name..."
                  class="mt-1 w-full rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-2 py-1 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-accent)] transition-colors"
                  @keyup.enter="handleAddEntity(system.id)"
                />
                <button v-else @click="newEntityName = ''; activeSystemId = system.id" class="mt-1 text-[10px] text-[var(--color-accent)] hover:underline">+ Add entity</button>
              </div>
              <div v-for="entity in system.entities" :key="entity.id" class="entity-row flex items-center gap-1.5 rounded px-1.5 py-0.5 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-border)] cursor-pointer transition-colors" :class="[activeEntityId === entity.id ? 'bg-[var(--color-accent)]/10 text-[var(--color-accent)]' : '']" @click="handleOpenEntity(entity.id)" @contextmenu.prevent="handleContextMenu($event, entity.id, 'entity')">
                <span class="material-symbols-outlined text-sm">{{ entity.category === 'character' ? 'person' : entity.category === 'item' ? 'inventory_2' : entity.category === 'location' ? 'pin_drop' : entity.category === 'quest' ? 'flag' : entity.category === 'skill' ? 'favorite' : entity.category === 'ability' ? 'auto_fix' : 'extension' }}</span>
                <span class="truncate flex-1">{{ entity.name }}</span>
                <span class="text-[10px] text-[var(--color-text-dim)]">
                  {{ entity.status === 'complete' ? '✓' : entity.status === 'in-progress' ? '◐' : '○' }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </aside>

      <!-- Right Panel: Registry -->
      <aside
        v-if="showRegistryPanel && layoutMode !== 'canvas'"
        class="right-panel flex flex-col border-l border-[var(--color-border)] bg-[var(--color-surface)]"
        :class="[layoutMode === 'split' ? 'w-96' : 'w-64']"
      >
        <!-- Panel Header -->
        <div class="panel-header flex h-10 items-center justify-between border-b border-[var(--color-border)] px-3">
          <div class="flex items-center gap-2">
            <span class="material-symbols-outlined text-[var(--color-accent2)] text-sm">database</span>
            <h2 class="text-xs font-semibold uppercase tracking-wider text-[var(--color-text)]">Registry</h2>
          </div>
          <button @click="togglePanel('registry')" class="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">
            <span class="material-symbols-outlined text-sm">chevron_right</span>
          </button>
        </div>

        <!-- Registry Content -->
        <div class="registry-content flex-1 overflow-y-auto p-3">
          <div v-if="activeEntityId" class="entity-detail">
            <div class="flex items-center gap-2 border-b border-[var(--color-border)] pb-2">
              <span class="material-symbols-outlined text-[var(--color-accent2)] text-lg">extension</span>
              <h3 class="text-sm font-medium text-[var(--color-text)]">Entity Detail</h3>
            </div>
            <div class="mt-3 space-y-3">
              <div>
                <label class="text-[10px] uppercase tracking-wider text-[var(--color-text-dim)]">Status</label>
                <select class="mt-1 w-full rounded border border-[var(--color-border)] bg-[var(--color-surface2)] px-2 py-1.5 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-accent)] transition-colors">
                  <option value="draft">Draft</option>
                  <option value="in-progress">In Progress</option>
                  <option value="complete">Complete</option>
                </select>
              </div>
              <div>
                <label class="text-[10px] uppercase tracking-wider text-[var(--color-text-dim)]">Category</label>
                <select class="mt-1 w-full rounded border border-[var(--color-border)] bg-[var(--color-surface2)] px-2 py-1.5 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-accent)] transition-colors">
                  <option value="character">Character</option>
                  <option value="item">Item</option>
                  <option value="location">Location</option>
                  <option value="quest">Quest</option>
                  <option value="skill">Skill</option>
                  <option value="ability">Ability</option>
                  <option value="general">General</option>
                </select>
              </div>
              <div>
                <label class="text-[10px] uppercase tracking-wider text-[var(--color-text-dim)]">Description</label>
                <textarea class="mt-1 min-h-[80px] w-full rounded border border-[var(--color-border)] bg-[var(--color-surface2)] px-2 py-1.5 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-accent)] transition-colors resize-y"></textarea>
              </div>
              <div>
                <label class="text-[10px] uppercase tracking-wider text-[var(--color-text-dim)]">Properties</label>
                <div class="mt-1 space-y-1">
                  <div v-for="(prop, i) in []" :key="i" class="flex items-center gap-1 rounded border border-[var(--color-border)] bg-[var(--color-surface2)] px-2 py-1">
                    <input type="text" placeholder="key" class="flex-1 bg-transparent text-xs text-[var(--color-text)] outline-none" />
                    <span class="text-[var(--color-text-dim)]">:</span>
                    <input type="text" placeholder="value" class="flex-1 bg-transparent text-xs text-[var(--color-text)] outline-none" />
                    <button class="flex h-4 w-4 items-center justify-center text-[var(--color-text-dim)] hover:text-[var(--color-error)]">
                      <span class="material-symbols-outlined text-sm">close</span>
                    </button>
                  </div>
                  <button class="mt-1 flex items-center gap-1 text-[10px] text-[var(--color-accent)] hover:underline">
                    <span class="material-symbols-outlined text-sm">add</span>
                    Add property
                  </button>
                </div>
              </div>
              <div>
                <label class="text-[10px] uppercase tracking-wider text-[var(--color-text-dim)]">Relationships</label>
                <div class="mt-1 space-y-1">
                  <div v-for="(rel, i) in []" :key="i" class="flex items-center gap-1 rounded border border-[var(--color-border)] bg-[var(--color-surface2)] px-2 py-1">
                    <input type="text" placeholder="target" class="flex-1 bg-transparent text-xs text-[var(--color-text)] outline-none" />
                    <select class="rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-1 text-xs text-[var(--color-text-muted)] outline-none">
                      <option value="uses">uses</option>
                      <option value="has">has</option>
                      <option value="requires">requires</option>
                      <option value="unlocks">unlocks</option>
                      <option value="opposes">opposes</option>
                    </select>
                  </div>
                  <button class="mt-1 flex items-center gap-1 text-[10px] text-[var(--color-accent)] hover:underline">
                    <span class="material-symbols-outlined text-sm">add</span>
                    Add relationship
                  </button>
                </div>
              </div>
              <div>
                <label class="text-[10px] uppercase tracking-wider text-[var(--color-text-dim)]">GDD References</label>
                <div class="mt-1 space-y-1">
                  <div v-for="(gdd, i) in []" :key="i" class="flex items-center gap-1 rounded border border-[var(--color-border)] bg-[var(--color-surface2)] px-2 py-1">
                    <input type="text" placeholder="gdd-ref" class="flex-1 bg-transparent text-xs text-[var(--color-text)] outline-none" />
                    <button class="flex h-4 w-4 items-center justify-center text-[var(--color-text-dim)] hover:text-[var(--color-error)]">
                      <span class="material-symbols-outlined text-sm">close</span>
                    </button>
                  </div>
                  <button class="mt-1 flex items-center gap-1 text-[10px] text-[var(--color-accent)] hover:underline">
                    <span class="material-symbols-outlined text-sm">add</span>
                    Link GDD
                  </button>
                </div>
              </div>
            </div>
          </div>
          <div v-else class="flex flex-col items-center justify-center py-12 text-center">
            <span class="material-symbols-outlined text-4xl text-[var(--color-text-dim)]">info</span>
            <p class="mt-3 text-xs text-[var(--color-text-dim)]">Select an entity to view details</p>
          </div>
        </div>
      </aside>

      <!-- Canvas Area -->
      <section class="canvas-area flex-1 overflow-hidden relative">
        <DesignCanvas
          :zoom="zoomLevel"
          :grid-size="gridSize"
          :show-grid="showGrid"
          :snap-to-grid="snapToGrid"
          :systems="systems"
          :entities="entities"
          :gdd-refs="gddRefs"
          :active-system-id="activeSystemId"
          :active-entity-id="activeEntityId"
          :palette="palette"
          @update:zoom="handleZoom"
          @toggle-grid="handleToggleGrid"
          @toggle-snap="handleToggleSnap"
          @open-system="handleOpenSystem"
          @open-entity="handleOpenEntity"
        />
        <!-- Canvas overlay controls -->
        <div class="canvas-controls absolute bottom-4 left-4 flex items-center gap-2">
          <div class="rounded border border-[var(--color-border)] bg-[var(--color-surface)]/80 backdrop-blur-sm p-1 flex items-center gap-1">
            <button @click="handleZoom(-25)" class="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">
              <span class="material-symbols-outlined text-sm">remove</span>
            </button>
            <span class="px-2 text-xs text-[var(--color-text-muted)]">{{ zoomLevel }}%</span>
            <button @click="handleZoom(25)" class="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">
              <span class="material-symbols-outlined text-sm">add</span>
            </button>
            <button @click="zoomLevel = 100" class="flex h-6 items-center justify-center px-2 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-border)] rounded transition-colors">
              <span class="material-symbols-outlined text-sm">center_focus_strong</span>
            </button>
          </div>
        </div>
        <div class="canvas-status absolute bottom-4 right-4 flex items-center gap-2 rounded border border-[var(--color-border)] bg-[var(--color-surface)]/80 backdrop-blur-sm px-2 py-1">
          <span class="material-symbols-outlined text-sm" :class="[gddRefs.length > 0 ? 'text-[var(--color-success)]' : 'text-[var(--color-warning)]']">{{ gddRefs.length > 0 ? 'check_circle' : 'warning' }}</span>
          <span class="text-[10px] text-[var(--color-text-muted)]">{{ gddRefs.length }} GDD refs</span>
        </div>
      </section>
    </main>

    <!-- Context Menu -->
    <teleport to="body">
      <div
        v-if="contextMenu"
        class="context-menu fixed z-50 min-w-[160px] rounded border border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg py-1 animate-in fade-in zoom-in-95 duration-100"
        :style="{ left: contextMenu.x + 'px', top: contextMenu.y + 'px' }"
        @click="contextMenu = null"
      >
        <button v-if="contextMenu.type === 'system'" class="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text)] hover:bg-[var(--color-border)] transition-colors">
          <span class="material-symbols-outlined text-sm">edit</span>
          Edit system
        </button>
        <button v-if="contextMenu.type === 'system'" class="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text)] hover:bg-[var(--color-border)] transition-colors">
          <span class="material-symbols-outlined text-sm">add_circle</span>
          Add entity
        </button>
        <button v-if="contextMenu.type === 'system'" class="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text)] hover:bg-[var(--color-border)] transition-colors">
          <span class="material-symbols-outlined text-sm">content_copy</span>
          Duplicate
        </button>
        <div v-if="contextMenu.type === 'system'" class="my-1 h-px bg-[var(--color-border)]"></div>
        <button v-if="contextMenu.type === 'system'" @click="handleDeleteSystem(contextMenu.target!)" class="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-error)] hover:bg-[var(--color-border)] transition-colors">
          <span class="material-symbols-outlined text-sm">delete</span>
          Delete
        </button>
        <button v-if="contextMenu.type === 'entity'" class="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text)] hover:bg-[var(--color-border)] transition-colors">
          <span class="material-symbols-outlined text-sm">edit</span>
          Edit entity
        </button>
        <button v-if="contextMenu.type === 'entity'" class="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text)] hover:bg-[var(--color-border)] transition-colors">
          <span class="material-symbols-outlined text-sm">content_copy</span>
          Duplicate
        </button>
        <button v-if="contextMenu.type === 'entity'" class="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-text)] hover:bg-[var(--color-border)] transition-colors">
          <span class="material-symbols-outlined text-sm">move_to_inbox</span>
          Move to...
        </button>
        <div v-if="contextMenu.type === 'entity'" class="my-1 h-px bg-[var(--color-border)]"></div>
        <button v-if="contextMenu.type === 'entity'" @click="handleDeleteEntity(activeSystemId!, contextMenu.target!)" class="flex w-full items-center gap-2 px-3 py-1.5 text-xs text-[var(--color-error)] hover:bg-[var(--color-border)] transition-colors">
          <span class="material-symbols-outlined text-sm">delete</span>
          Delete
        </button>
      </div>
    </teleport>

    <!-- Export Modal -->
    <teleport to="body">
      <div v-if="showExportModal" class="modal-overlay fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" @click="showExportModal = false">
        <div class="modal-content w-full max-w-md rounded border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl" @click.stop>
          <div class="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
            <h2 class="text-sm font-medium text-[var(--color-text)]">Export Design</h2>
            <button @click="showExportModal = false" class="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">
              <span class="material-symbols-outlined text-sm">close</span>
            </button>
          </div>
          <div class="p-4 space-y-3">
            <p class="text-xs text-[var(--color-text-muted)]">Export your game design in various formats</p>
            <div class="space-y-2">
              <button class="flex w-full items-center gap-3 rounded border border-[var(--color-border)] bg-[var(--color-surface2)] px-3 py-2 text-left hover:border-[var(--color-border2)] transition-colors">
                <span class="material-symbols-outlined text-[var(--color-accent)]">code</span>
                <div>
                  <p class="text-sm text-[var(--color-text)]">JSON</p>
                  <p class="text-[10px] text-[var(--color-text-dim)]">Raw design data</p>
                </div>
              </button>
              <button class="flex w-full items-center gap-3 rounded border border-[var(--color-border)] bg-[var(--color-surface2)] px-3 py-2 text-left hover:border-[var(--color-border2)] transition-colors">
                <span class="material-symbols-outlined text-[var(--color-accent2)]">article</span>
                <div>
                  <p class="text-sm text-[var(--color-text)]">Markdown</p>
                  <p class="text-[10px] text-[var(--color-text-dim)]">Human-readable format</p>
                </div>
              </button>
              <button class="flex w-full items-center gap-3 rounded border border-[var(--color-border)] bg-[var(--color-surface2)] px-3 py-2 text-left hover:border-[var(--color-border2)] transition-colors">
                <span class="material-symbols-outlined text-[var(--color-accent3)]">table_chart</span>
                <div>
                  <p class="text-sm text-[var(--color-text)]">CSV</p>
                  <p class="text-[10px] text-[var(--color-text-dim)]">Spreadsheet export</p>
                </div>
              </button>
              <button class="flex w-full items-center gap-3 rounded border border-[var(--color-border)] bg-[var(--color-surface2)] px-3 py-2 text-left hover:border-[var(--color-border2)] transition-colors">
                <span class="material-symbols-outlined text-[var(--color-success)]">diagram</span>
                <div>
                  <p class="text-sm text-[var(--color-text)]">Graphviz</p>
                  <p class="text-[10px] text-[var(--color-text-dim)]">Relationship diagram</p>
                </div>
              </button>
            </div>
          </div>
          <div class="flex justify-end gap-2 border-t border-[var(--color-border)] px-4 py-3">
            <button @click="showExportModal = false" class="rounded border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">Close</button>
          </div>
        </div>
      </div>
    </teleport>

    <!-- Import Modal -->
    <teleport to="body">
      <div v-if="showImportModal" class="modal-overlay fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" @click="showImportModal = false">
        <div class="modal-content w-full max-w-md rounded border border-[var(--color-border)] bg-[var(--color-surface)] shadow-xl" @click.stop>
          <div class="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
            <h2 class="text-sm font-medium text-[var(--color-text)]">Import Design</h2>
            <button @click="showImportModal = false" class="flex h-6 w-6 items-center justify-center rounded text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">
              <span class="material-symbols-outlined text-sm">close</span>
            </button>
          </div>
          <div class="p-4 space-y-4">
            <p class="text-xs text-[var(--color-text-muted)]">Import a design from a JSON file or paste JSON directly</p>
            <div class="flex flex-col items-center justify-center rounded border-2 border-dashed border-[var(--color-border)] bg-[var(--color-surface2)] py-8 text-center">
              <span class="material-symbols-outlined text-3xl text-[var(--color-text-dim)]">upload_file</span>
              <p class="mt-2 text-xs text-[var(--color-text-muted)]">Drop JSON file here or click to browse</p>
              <button class="mt-3 rounded bg-[var(--color-accent)] px-3 py-1 text-xs font-medium text-white hover:bg-[var(--color-accent)]/90 transition-colors">Browse</button>
            </div>
            <div class="space-y-2">
              <label class="text-[10px] uppercase tracking-wider text-[var(--color-text-dim)]">Or paste JSON</label>
              <textarea class="min-h-[100px] w-full rounded border border-[var(--color-border)] bg-[var(--color-surface2)] px-2 py-1.5 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-accent)] transition-colors resize-y" placeholder='{"systems": [...], "entities": [...]}'></textarea>
            </div>
          </div>
          <div class="flex justify-end gap-2 border-t border-[var(--color-border)] px-4 py-3">
            <button @click="showImportModal = false" class="rounded border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-text-muted)] hover:bg-[var(--color-border)] transition-colors">Cancel</button>
            <button class="rounded bg-[var(--color-accent)] px-3 py-1.5 text-xs font-medium text-white hover:bg-[var(--color-accent)]/90 transition-colors">Import</button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<style scoped>
.design-page {
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
}
.system-card {
  animation: slide-in 0.2s ease-out;
}
@keyframes slide-in {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.entity-row {
  animation: fade-in 0.15s ease-out;
}
@keyframes fade-in {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}
.context-menu {
  z-index: 9999;
}
</style>