<script setup lang="ts">
import { ref, computed, defineComponent, h, Fragment } from 'vue'
import { useSkillStore } from '../stores/skillStore'
import { useUIStore } from '../stores/uiStore'
import { useTranslation } from '../i18n'
import MarkdownRenderer from '../components/markdown/MarkdownRenderer.vue'
import CodeViewer from '../components/chat/CodeViewer.vue'

type SkillSource = 'user' | 'project' | 'plugin' | 'mcp' | 'bundled'

interface SkillMeta {
  name: string
  displayName?: string
  description: string
  source: SkillSource
  userInvocable: boolean
  version?: string
  contentLength: number
  hasDirectory: boolean
  pluginName?: string
}

interface FileTreeNode {
  name: string
  path: string
  type: 'file' | 'directory'
  children?: FileTreeNode[]
}

interface SkillFrontmatter {
  [key: string]: unknown
}

interface SkillFile {
  path: string
  content: string
  language: string
  frontmatter?: SkillFrontmatter
  body?: string
  isEntry?: boolean
}

interface SkillDetail {
  meta: SkillMeta
  tree: FileTreeNode[]
  files: SkillFile[]
  skillRoot: string
}

const META_PRIORITY: readonly string[] = [
  'description',
  'when_to_use',
  'argument-hint',
  'model',
  'effort',
  'allowed-tools',
  'paths',
  'agent',
  'context',
  'version',
  'user-invocable',
] as const

const skillStore = useSkillStore()
const t = useTranslation()

const selectedFile = ref<string>('SKILL.md')

// Cast selectedSkill to SkillDetail — React uses this shape directly
const selectedSkill = computed(() => skillStore.selectedSkill as unknown as SkillDetail | null)

// Normalized selection: fallback to first file if current choice is gone
const normalizedSelection = computed(() => {
  if (!selectedSkill.value) return 'SKILL.md'
  return selectedSkill.value.files.some((file) => file.path === selectedFile.value)
    ? selectedFile.value
    : selectedSkill.value.files[0]?.path || 'SKILL.md'
})

const handleBack = () => {
  const returnTab = (skillStore as any).selectedSkillReturnTab
  (skillStore as any).clearSelection?.()
  if (returnTab === 'plugins') {
    useUIStore().setPendingSettingsTab('plugins')
  }
}

function fileIcon(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase()
  switch (ext) {
    case 'md':
      return 'description'
    case 'ts':
    case 'tsx':
    case 'js':
    case 'jsx':
    case 'py':
    case 'rs':
    case 'go':
      return 'code'
    case 'json':
    case 'yaml':
    case 'yml':
    case 'toml':
      return 'data_object'
    case 'sh':
    case 'bash':
      return 'terminal'
    default:
      return 'draft'
  }
}

function formatMetaKey(key: string): string {
  return key.replace(/[-_]/g, ' ')
}

function formatMetaValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map((item) => String(item)).join(', ')
  }
  if (typeof value === 'boolean') {
    return value ? 'true' : 'false'
  }
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value)
  }
  return String(value)
}

function getMetaEntries(frontmatter?: SkillFrontmatter): Array<[string, unknown]> {
  if (!frontmatter) return []

  const entries = Object.entries(frontmatter).filter(([, value]) => {
    if (value == null) return false
    if (typeof value === 'string') return value.trim().length > 0
    if (Array.isArray(value)) return value.length > 0
    return true
  })

  entries.sort((a, b) => {
    const aIndex = META_PRIORITY.indexOf(a[0] as (typeof META_PRIORITY)[number])
    const bIndex = META_PRIORITY.indexOf(b[0] as (typeof META_PRIORITY)[number])
    const normalizedA = aIndex === -1 ? Number.MAX_SAFE_INTEGER : aIndex
    const normalizedB = bIndex === -1 ? Number.MAX_SAFE_INTEGER : bIndex
    return normalizedA - normalizedB || a[0].localeCompare(b[0])
  })

  return entries
}

const currentFileSafe = computed(() => {
  if (!selectedSkill.value) return null
  return selectedSkill.value.files.find((f) => f.path === normalizedSelection.value)
    || selectedSkill.value.files[0]
    || null
})

const metaEntries = computed(() => {
  return getMetaEntries(currentFileSafe.value?.frontmatter)
})

// ============================================================
// TreeItem — defined as a render-function component (no template)
// ============================================================
const TreeItem = defineComponent({
  props: {
    node: { type: Object as () => FileTreeNode, required: true },
    selectedPath: { type: String, required: true },
    depth: { type: Number, required: true },
  },
  emits: ['select'],
  setup(props, { emit }) {
    const expanded = ref(true)
    const isSelected = computed(() => props.node.path === props.selectedPath)
    const isDir = computed(() => props.node.type === 'directory')
    const icon = computed(() => {
      if (isDir.value) return expanded.value ? 'folder_open' : 'folder'
      return fileIcon(props.node.name)
    })

    function handleClick() {
      if (isDir.value) {
        expanded.value = !expanded.value
      } else {
        emit('select', props.node.path)
      }
    }

    return () => {
      const btnClasses = [
        'flex w-full items-center gap-1.5 rounded-lg px-2 py-1.5 text-left text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]',
        isSelected.value
          ? 'bg-[var(--color-surface-selected)] text-[var(--color-text-primary)] font-medium'
          : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]',
      ]

      const chevronOrIndent = isDir.value
        ? h('span', { class: 'material-symbols-outlined text-[12px] text-[var(--color-text-tertiary)]' }, expanded.value ? 'expand_more' : 'chevron_right')
        : h('span', { style: { width: 12 } })

      return h('div', null, [
        h(
          'button',
          {
            onClick: handleClick,
            class: btnClasses,
            style: { marginLeft: `${props.depth * 12}px`, width: `calc(100% - ${props.depth * 12}px)` },
          },
          [
            chevronOrIndent,
            h('span', { class: 'material-symbols-outlined text-[14px] text-[var(--color-text-tertiary)]' }, icon.value),
            h('span', { class: 'truncate' }, props.node.name),
          ]
        ),
        isDir.value && expanded.value && props.node.children
          ? h(
              Fragment,
              null,
              props.node.children.map((child) =>
                h(TreeItem, {
                  key: child.path,
                  node: child,
                  selectedPath: props.selectedPath,
                  depth: props.depth + 1,
                  onSelect: (path: string) => emit('select', path),
                })
              )
            )
          : null,
      ])
    }
  },
})
</script>

<template>
  <!-- Loading spinner -->
  <div
    v-if="(skillStore as any).isDetailLoading"
    class="flex justify-center py-12"
  >
    <div class="animate-spin w-5 h-5 border-2 border-[var(--color-brand)] border-t-transparent rounded-full" />
  </div>

  <template v-else-if="selectedSkill">
    <div class="flex h-full min-h-0 flex-col gap-4 min-w-0">
      <!-- Back button -->
      <div>
        <button
          @click="handleBack"
          class="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]"
        >
          <span class="material-symbols-outlined text-[16px]">arrow_back</span>
          {{ t('settings.skills.back') }}
        </button>
      </div>

      <!-- Header section -->
      <section class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] overflow-hidden">
        <div class="grid gap-4 px-5 py-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(280px,0.9fr)] lg:items-start">
          <div class="min-w-0">
            <div class="text-[11px] font-semibold uppercase tracking-[0.2em] text-[var(--color-text-tertiary)] mb-2">
              {{ t('settings.skills.entryEyebrow') }}
            </div>
            <div class="flex flex-wrap items-center gap-2 mb-2">
              <h3 class="text-[22px] font-semibold leading-tight text-[var(--color-text-primary)] break-all">
                {{ selectedSkill.meta.displayName || selectedSkill.meta.name }}
              </h3>
              <span class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]">
                {{ t(`settings.skills.source.${selectedSkill.meta.source}`) }}
              </span>
              <span
                v-if="selectedSkill.meta.version"
                class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]"
              >
                v{{ selectedSkill.meta.version }}
              </span>
              <span
                v-if="selectedSkill.meta.userInvocable"
                class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]"
              >
                {{ t('settings.skills.slashCommand') }}
              </span>
            </div>
            <p class="max-w-4xl text-sm leading-6 text-[var(--color-text-secondary)]">
              {{ selectedSkill.meta.description }}
            </p>
            <div class="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-[var(--color-text-tertiary)]">
              <span>{{ t('settings.skills.tokenEstimate', { count: String(Math.ceil(selectedSkill.meta.contentLength / 4)) }) }}</span>
              <span>
                {{ selectedSkill.files.length }} {{ t('settings.skills.files') }}
              </span>
              <span>{{ currentFileSafe?.isEntry ? t('settings.skills.entryFile') : (currentFileSafe?.path ?? '') }}</span>
            </div>
          </div>

          <!-- Detail stats -->
          <div class="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-2">
            <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3">
              <div class="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">
                <span class="material-symbols-outlined text-[14px]">folder_open</span>
                <span>{{ t('settings.skills.summary.totalFiles') }}</span>
              </div>
              <div class="mt-2 text-base font-semibold text-[var(--color-text-primary)] break-all">
                {{ selectedSkill.files.length }}
              </div>
            </div>
            <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3">
              <div class="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">
                <span class="material-symbols-outlined text-[14px]">notes</span>
                <span>{{ t('settings.skills.summary.tokens') }}</span>
              </div>
              <div class="mt-2 text-base font-semibold text-[var(--color-text-primary)] break-all">
                {{ t('settings.skills.tokenEstimateShort', { count: String(Math.ceil(selectedSkill.meta.contentLength / 4)) }) }}
              </div>
            </div>
            <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3">
              <div class="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text>[var(--color-text-tertiary)]">
                <span class="material-symbols-outlined text-[14px]">layers</span>
                <span>{{ t('settings.skills.summary.source') }}</span>
              </div>
              <div class="mt-2 text-base font-semibold text-[var(--color-text-primary)] break-all">
                {{ t(`settings.skills.source.${selectedSkill.meta.source}`) }}
              </div>
            </div>
            <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-3">
              <div class="flex items-center gap-2 text-[11px] uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">
                <span class="material-symbols-outlined text-[14px]">article</span>
                <span>{{ t('settings.skills.summary.entry') }}</span>
              </div>
              <div class="mt-2 text-base font-semibold text>[var(--color-text-primary)] break-all">
                {{ selectedSkill.files.some((f: { isEntry?: boolean }) => f.isEntry) ? 'SKILL.md' : '—' }}
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- Meta entries section -->
      <section
        v-if="metaEntries.length > 0"
        class="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] px-5 py-4"
      >
        <div class="flex items-center gap-2 mb-3">
          <span class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)]">tune</span>
          <h4 class="text-sm font-semibold text-[var(--color-text-primary)]">
            {{ t('settings.skills.metaTitle') }}
          </h4>
        </div>
        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
          <div
            v-for="[key, value] in metaEntries"
            :key="key"
            class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-3 py-3 min-w-0"
          >
            <div class="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-text-tertiary)]">
              {{ formatMetaKey(key) }}
            </div>
            <div class="mt-2 text-sm leading-6 text-[var(--color-text-primary)] break-words">
              {{ formatMetaValue(value) }}
            </div>
          </div>
        </div>
      </section>

      <!-- File viewer section -->
      <section class="flex flex-1 min-h-0 min-w-0 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]">
        <!-- Tree view sidebar (desktop) -->
        <aside class="hidden w-[250px] flex-shrink-0 border-r border-[var(--color-border)] bg-[var(--color-surface-container-low)] lg:flex lg:flex-col">
          <div class="border-b border-[var(--color-border)] px-4 py-3">
            <div class="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-text-tertiary)]">
              {{ t('settings.skills.filesPanel') }}
            </div>
            <p class="mt-1 text-xs leading-5 text-[var(--color-text-tertiary)]">
              {{ t('settings.skills.filesPanelHint') }}
            </p>
          </div>
          <div class="min-h-0 flex-1 overflow-y-auto p-2">
            <TreeItem
              v-for="node in selectedSkill.tree"
              :key="node.path"
              :node="node"
              :selected-path="normalizedSelection"
              @select="(path: string) => { selectedFile = path }"
              :depth="0"
            />
          </div>
        </aside>

        <!-- Main content area -->
        <div class="flex min-w-0 flex-1 flex-col overflow-hidden">
          <!-- Header -->
          <div class="flex flex-wrap items-center justify-between gap-2 border-b border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-4 py-3">
            <div class="min-w-0">
              <div class="flex items-center gap-2 flex-wrap">
                <span class="text-xs font-mono text-[var(--color-text-secondary)] break-all">
                  {{ currentFileSafe?.path }}
                </span>
                <span
                  v-if="currentFileSafe?.isEntry"
                  class="rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[var(--color-text-tertiary)]"
                >
                  {{ t('settings.skills.entryFile') }}
                </span>
              </div>
              <div class="mt-1 text-[11px] text-[var(--color-text-tertiary)]">
                {{ t('settings.skills.readingMode', {
                  mode:
                    currentFileSafe?.language === 'markdown'
                      ? t('settings.skills.docMode')
                      : t('settings.skills.codeMode'),
                }) }}
              </div>
            </div>
            <div class="flex items-center gap-2">
              <span class="rounded-full bg-[var(--color-surface)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking>[0.12em] text-[var(--color-text-tertiary)] border border-[var(--color-border)]">
                {{ currentFileSafe?.language }}
              </span>
            </div>
          </div>

          <!-- File tabs (mobile) -->
          <div class="lg:hidden border-b border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 overflow-x-auto">
            <div class="flex gap-2 min-w-max">
              <button
                v-for="file in selectedSkill.files"
                :key="file.path"
                @click="selectedFile = file.path"
                :class="[
                  'rounded-full border px-3 py-1.5 text-xs transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)]',
                  file.path === normalizedSelection
                    ? 'border-[var(--color-brand)] bg-[var(--color-primary-fixed)] text-[var(--color-text-primary)]'
                    : 'border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]'
                ]"
              >
                {{ file.path }}
              </button>
            </div>
          </div>

          <!-- Content area -->
          <div class="min-h-0 flex-1 overflow-y-auto bg-[var(--color-surface-container-lowest)]">
            <div
              v-if="currentFileSafe"
              :class="currentFileSafe.language === 'markdown' ? 'px-6 py-5 lg:px-8' : 'p-4'"
            >
              <MarkdownRenderer
                v-if="currentFileSafe.language === 'markdown'"
                :content="currentFileSafe.body ?? currentFileSafe.content"
                variant="document"
                class="mx-auto max-w-[72ch]"
              />
              <CodeViewer
                v-else
                :code="currentFileSafe.content"
                :language="currentFileSafe.language"
                :max-lines="9999"
                show-line-numbers
              />
            </div>
          </div>
        </div>
      </section>
    </div>
  </template>
</template>