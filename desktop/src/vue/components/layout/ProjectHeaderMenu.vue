<!--
  v4 — Extracted from Sidebar.vue.

  Used to be a nested defineComponent({setup() {return () => ...}}) which
  had two problems:
    1. `props.x` / `props.y` were captured at setup time. Vue never
       re-evaluated them inside the render fn, so the inline `style`
       ended up with undefined left/top → menu drifted to (0,0).
    2. Building per-type item lists (main/organize/sort/create)
       required reading props inside the closure, which is brittle.

  This file uses <script setup lang="ts"> + <template> so props
  reactivity is automatic via `defineProps`, items render through
  v-for, and emit() gives a typed event surface.

  File-level boundaries kept narrow: only this file and the
  importing site (Sidebar.vue) need to change. The menu is
  teleported visibly but emitted from Sidebar.vue's existing
  watchers — no prop drilling needed beyond x/y/type.
-->
<script setup lang="ts">
import { computed, h } from 'vue'

// ─── Types ────────────────────────────────────────────────────────────

type MenuType = 'main' | 'organize' | 'sort' | 'create'
type Organization = 'project' | 'recentProject' | 'time'
type SortBy = 'createdAt' | 'updatedAt'

// ─── Props & Emits ────────────────────────────────────────────────────

const props = defineProps<{
  type?: MenuType
  x?: number | null
  y?: number | null
  organization?: Organization
  sortBy?: SortBy
  /** Unused for now — kept so the parent template doesn't break. */
  hiddenProjectCount?: number
}>()

const emit = defineEmits<{
  (e: 'open-submenu', ev: MouseEvent, submenu: 'organize' | 'sort'): void
  (e: 'set-organization', value: Organization): void
  (e: 'set-sort-by', value: SortBy): void
  (e: 'create-blank'): void
  (e: 'use-existing-folder'): void
  (e: 'restore-hidden-projects'): void
}>()

// ─── Static item lists (per-type) ─────────────────────────────────────
//
// Hardcoded labels for now. The locale tables
// (desktop/src/i18n/locales/{zh,en}.ts) don't yet have entries for
// the org/sort/create strings, so calling t() would surface the
// raw key instead of the translated value. Re-introduce a t()
// call once those entries exist (a separate i18n PR is fine).

// ─── Static item lists (per-type) ─────────────────────────────────────

const orgs: ReadonlyArray<{ value: Organization; label: string }> = [
  { value: 'project', label: 'By project' },
  { value: 'recentProject', label: 'By recent project' },
  { value: 'time', label: 'By time' },
]

const sorts: ReadonlyArray<{ value: SortBy; label: string }> = [
  { value: 'updatedAt', label: 'Updated at' },
  { value: 'createdAt', label: 'Created at' },
]

// ─── Inline SVG icons (kept here so the .vue file is self-contained
//     and Sidebar.vue's <script setup> doesn't need to expose icons).

const PlusIcon = () =>
  h('svg', {
    width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none',
    stroke: 'currentColor', 'stroke-width': '2',
    'stroke-linecap': 'round', 'stroke-linejoin': 'round',
  }, [
    h('line', { x1: '12', y1: '5', x2: '12', y2: '19' }),
    h('line', { x1: '5', y1: '12', x2: '19', y2: '12' }),
  ])

const GitHubIcon = () =>
  h('svg', {
    width: 18, height: 18, viewBox: '0 0 24 24', fill: 'currentColor',
  }, [
    h('path', {
      d: 'M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0 0 24 12c0-6.63-5.37-12-12-12z',
    }),
  ])

const SortIcon = () =>
  h('svg', {
    width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none',
    stroke: 'currentColor', 'stroke-width': '2',
    'stroke-linecap': 'round', 'stroke-linejoin': 'round',
  }, [
    h('path', { d: 'M3 6h18M6 12h12M10 18h4' }),
  ])

const OrganizationIcon = () =>
  h('svg', {
    width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none',
    stroke: 'currentColor', 'stroke-width': '2',
    'stroke-linecap': 'round', 'stroke-linejoin': 'round',
  }, [
    h('rect', { x: '3', y: '3', width: '7', height: '7', rx: '1' }),
    h('rect', { x: '14', y: '3', width: '7', height: '7', rx: '1' }),
    h('rect', { x: '3', y: '14', width: '7', height: '7', rx: '1' }),
    h('rect', { x: '14', y: '14', width: '7', height: '7', rx: '1' }),
  ])

const ChevronRightIcon = () =>
  h('span', {
    class: 'material-symbols-outlined text-[17px] text-[var(--color-text-tertiary)]',
    style: { transform: 'rotate(-90deg)' },
    'aria-hidden': 'true',
  }, 'expand_more')

// ─── Style — reactive via computed so props.x/y are re-evaluated
//     on every render. This is the actual fix to the (0,0) bug.

const menuStyle = computed(() => ({
  position: 'fixed' as const,
  left: typeof props.x === 'number' ? `${props.x}px` : '8px',
  top: typeof props.y === 'number' ? `${props.y}px` : '8px',
  boxShadow: 'var(--shadow-dropdown)',
}))

// Inline arrow handlers — stable references, no factory-function
// template binding quirks. Each handler reads the right submenu /
// org / sort target and the click event is passed in.
const openSortSubmenu = (ev: MouseEvent) => emit('open-submenu', ev, 'sort')
const openOrganizeSubmenu = (ev: MouseEvent) => emit('open-submenu', ev, 'organize')
const setOrganization = (org: Organization) => () => emit('set-organization', org)
const setSortBy = (sort: SortBy) => () => emit('set-sort-by', sort)
const triggerCreateBlank = () => emit('create-blank')
const triggerUseExistingFolder = () => emit('use-existing-folder')
const triggerRestoreHidden = () => emit('restore-hidden-projects')
</script>

<template>
  <div
    role="menu"
    class="project-header-menu fixed z-50 min-w-[230px] overflow-hidden rounded-[18px] border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] py-2"
    :style="menuStyle"
    @click.stop
  >
    <!-- Main menu: shortcuts to organize / sort submenus + create entry -->
    <template v-if="type === 'main'">
      <button
        type="button"
        class="project-header-menu__item"
        :data-submenu="sort"
        @click="openSortSubmenu"
        @mouseenter="openSortSubmenu"
      >
        <SortIcon />
        <span class="flex-1 text-left">Sort by</span>
        <ChevronRightIcon />
      </button>
      <button
        type="button"
        class="project-header-menu__item"
        :data-submenu="organize"
        @click="openOrganizeSubmenu"
        @mouseenter="openOrganizeSubmenu"
      >
        <OrganizationIcon />
        <span class="flex-1 text-left">Organize by</span>
        <ChevronRightIcon />
      </button>
      <div class="my-1 h-px bg-[var(--color-border-separator)]" role="separator" />
      <button
        type="button"
        class="project-header-menu__item"
        @click="triggerCreateBlank"
      >
        <PlusIcon />
        <span class="flex-1 text-left">Create blank session</span>
      </button>
    </template>

    <!-- Organize submenu: pick the active ordering -->
    <template v-else-if="type === 'organize'">
      <button
        v-for="o in orgs"
        :key="o.value"
        type="button"
        class="project-header-menu__item"
        :class="{ 'is-checked': organization === o.value }"
        @click="setOrganization(o.value)"
      >
        <OrganizationIcon />
        <span class="flex-1 text-left">{{ o.label }}</span>
        <span
          v-if="organization === o.value"
          class="material-symbols-outlined text-[17px] text-[var(--color-text-secondary)]"
          aria-hidden="true"
        >check</span>
      </button>
    </template>

    <!-- Sort submenu: pick the active sort key -->
    <template v-else-if="type === 'sort'">
      <button
        v-for="s in sorts"
        :key="s.value"
        type="button"
        class="project-header-menu__item"
        :class="{ 'is-checked': sortBy === s.value }"
        @click="setSortBy(s.value)"
      >
        <SortIcon />
        <span class="flex-1 text-left">{{ s.label }}</span>
        <span
          v-if="sortBy === s.value"
          class="material-symbols-outlined text-[17px] text-[var(--color-text-secondary)]"
          aria-hidden="true"
        >check</span>
      </button>
    </template>

    <!-- Create submenu: blank vs. existing folder -->
    <template v-else-if="type === 'create'">
      <button
        type="button"
        class="project-header-menu__item"
        @click="triggerCreateBlank"
      >
        <PlusIcon />
        <span class="flex-1 text-left">Create blank session</span>
      </button>
      <button
        type="button"
        class="project-header-menu__item"
        @click="triggerUseExistingFolder"
      >
        <GitHubIcon />
        <span class="flex-1 text-left">Use existing folder</span>
      </button>
    </template>
  </div>
</template>

<style scoped>
.project-header-menu__item {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 12px;
  padding: 9px 14px;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary, #1f1f1f);
  background: transparent;
  border: 0;
  cursor: pointer;
  /* Specify exact properties (Emil review-animations standard #1).
     `transition: all` is bounded so layout-triggering animations
     can't leak through. */
  transition: background-color 150ms ease-out, color 150ms ease-out;
}

.project-header-menu__item:hover {
  background: var(--color-surface-hover, #f0f0f2);
  color: var(--color-text-primary, #111);
}

.project-header-menu__item.is-checked {
  background: var(--color-surface-hover, #f0f0f2);
}

.project-header-menu__item:active {
  transform: scale(0.98);
}

@media (prefers-reduced-motion: reduce) {
  .project-header-menu__item { transition: none; }
  .project-header-menu__item:active { transform: none; }
}
</style>
