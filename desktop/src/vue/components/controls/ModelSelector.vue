<script setup lang="ts">
// v3.0 — ModelSelector (Vue 3)
// Direct translation of controls/ModelSelector.tsx (607 lines).
import {
  ref,
  computed,
  watch,
  onMounted,
  onUnmounted,
  nextTick,
  defineSlots,
} from 'vue'
import {
  OFFICIAL_DEFAULT_MODEL_ID,
  OFFICIAL_MODELS,
} from '../../constants/modelCatalog'
import {
  MADCOP_BUILT_IN_PROVIDER_B_DEFAULT_MODEL,
  MADCOP_BUILT_IN_PROVIDER_B_MODELS,
  MADCOP_BUILT_IN_PROVIDER_B,
} from '../../constants/builtInProviderIds'
import { useTranslation } from '../../i18n'
import { useChatStore } from '../../stores/chatStore'
import { useProviderStore } from '../../stores/providerStore'
import { DRAFT_RUNTIME_SELECTION_KEY, useSessionRuntimeStore } from '../../stores/sessionRuntimeStore'
import { useSettingsStore } from '../../stores/settingsStore'
import type { SavedProvider } from '../../types/provider'
import type { RuntimeSelection } from '../../types/runtime'
import type { EffortLevel, ModelInfo } from '../../types/settings'
import MobileBottomSheet from '../shared/MobileBottomSheet.vue'

// ─── Helpers ported from the React source ────────────────────────────
type ProviderChoice = {
  providerId: string | null
  providerName: string
  isDefault: boolean
  models: ModelInfo[]
}

function officialChoices(
  providerId: string | null,
  models: ModelInfo[],
  isDefault: boolean,
  officialName: string,
): ProviderChoice {
  return { providerId, providerName: officialName, isDefault, models }
}

function buildProviderModels(
  provider: SavedProvider,
  labels: Record<'main' | 'haiku' | 'sonnet' | 'opus', string>,
  liveModels: ModelInfo[] = [],
): ModelInfo[] {
  if (liveModels.length > 0) {
    const own = liveModels.filter(
      (m) => (m as any).providerId === provider.id || (m as any).providerName === provider.name,
    )
    if (own.length > 0) return own
  }
  const providerAny = provider as any
  const explicit = providerAny.models
  if (explicit && typeof explicit === 'object') {
    const entries: Array<{ id: string; label: string }> = [
      { id: String(explicit.main ?? '').trim(), label: labels.main },
      { id: String(explicit.haiku ?? '').trim(), label: labels.haiku },
      { id: String(explicit.sonnet ?? '').trim(), label: labels.sonnet },
      { id: String(explicit.opus ?? '').trim(), label: labels.opus },
    ]
    return entries
      .filter((e) => e.id)
      .map<ModelInfo>((e) => ({
        id: e.id,
        name: e.label,
        description: '',
        context: 'auto',
      }))
  }
  const modelId = String(providerAny.model ?? '').trim()
  if (!modelId) return []
  return [{ id: modelId, name: labels.main, description: '', context: 'auto' }]
}

function buildProviderChoices(
  providers: SavedProvider[],
  activeId: string | null,
  availableModels: ModelInfo[],
  officialName: string,
  openAIOfficialName: string,
  labels: Record<'main' | 'haiku' | 'sonnet' | 'opus', string>,
  claudeOfficialLoggedIn: boolean,
  openAIOfficialLoggedIn: boolean,
): ProviderChoice[] {
  const claudeOfficialModels =
    activeId === null && availableModels.length > 0 ? availableModels : OFFICIAL_MODELS
  const openAIOfficialModels =
    activeId === MADCOP_BUILT_IN_PROVIDER_B && availableModels.length > 0
      ? availableModels
      : MADCOP_BUILT_IN_PROVIDER_B_MODELS
  const choices: ProviderChoice[] = []
  if (claudeOfficialLoggedIn) {
    choices.push(officialChoices(null, claudeOfficialModels, activeId === null, officialName))
  }
  if (openAIOfficialLoggedIn) {
    choices.push(officialChoices(
      MADCOP_BUILT_IN_PROVIDER_B,
      openAIOfficialModels,
      activeId === MADCOP_BUILT_IN_PROVIDER_B,
      openAIOfficialName,
    ))
  }
  for (const provider of providers) {
    choices.push({
      providerId: provider.id,
      providerName: provider.name,
      isDefault: activeId === provider.id,
      models: buildProviderModels(provider, labels, availableModels),
    })
  }
  return choices
}

function resolveDefaultRuntimeSelection(
  activeId: string | null,
  activeProviderName: string | null,
  providers: SavedProvider[],
  currentModelId: string | undefined,
): RuntimeSelection {
  const activeProvider = activeId
    ? providers.find((p) => p.id === activeId)
    : activeProviderName
      ? providers.find((p) => p.name === activeProviderName)
      : undefined
  const inferredProviderId = activeId ?? activeProvider?.id ?? null
  const providerMainModelId =
    (activeProvider as any)?.models?.main?.trim?.() ??
    (activeProvider as any)?.model?.trim?.() ??
    ''
  return {
    providerId: inferredProviderId,
    modelId:
      providerMainModelId ||
      currentModelId ||
      (inferredProviderId === MADCOP_BUILT_IN_PROVIDER_B
        ? MADCOP_BUILT_IN_PROVIDER_B_DEFAULT_MODEL
        : OFFICIAL_DEFAULT_MODEL_ID),
  }
}

// ─── Props / Emits ───────────────────────────────────────────────────
interface Props {
  value?: string
  runtimeSelection?: RuntimeSelection
  runtimeKey?: string
  disabled?: boolean
  compact?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  compact: false,
})

const emit = defineEmits<{
  change: [modelId: string]
  'update:runtimeSelection': [selection: RuntimeSelection]
}>()

// ─── Stores ──────────────────────────────────────────────────────────
const t = useTranslation()
const settingsStore = useSettingsStore()
const providerStore = useProviderStore()
const runtimeStore = useSessionRuntimeStore()
const chatStore = useChatStore()

// Mobile detection
const isMobileBrowser = ref(false)

// ─── Local state ─────────────────────────────────────────────────────
const open = ref(false)
const dropdownPosition = ref<{
  top: number | undefined
  bottom: number | undefined
  left: number
  width: number
  maxHeight: number
} | null>(null)
const rootRef = ref<HTMLDivElement | null>(null)
const dropdownRef = ref<HTMLDivElement | null>(null)
const requestedProvidersRef = ref(false)
const requestedOAuthStatusRef = ref(false)

// ─── Computed ────────────────────────────────────────────────────────
const isControlled = computed(() => props.value !== undefined)
const isRuntimeScoped = computed(
  () => !isControlled.value && (props.runtimeKey !== undefined),
)
const canEditRuntimeEffort = computed(() => props.runtimeKey !== undefined)

const currentModel = computed(() => settingsStore.currentModel)
const availableModels = computed(() => settingsStore.availableModels)
const effortLevel = computed(() => settingsStore.effortLevel)
const activeProviderName = computed(() => settingsStore.activeProviderName)
const activeId = computed(() => providerStore.activeId)
const providersLoading = computed(() => providerStore.isLoading)
const providers = computed(() => providerStore.providers)

const roleLabels = computed(() => ({
  main: t('settings.providers.mainModel'),
  haiku: t('settings.providers.haikuModel'),
  sonnet: t('settings.providers.sonnetModel'),
  opus: t('settings.providers.opusModel'),
}))

const providerChoices = computed((): ProviderChoice[] =>
  buildProviderChoices(
    providers.value,
    activeId.value,
    availableModels.value,
    t('settings.providers.officialName'),
    t('settings.providers.openaiOfficialName'),
    roleLabels.value,
    false, // claudeOAuthLoggedIn (no hahaOAuth in Vue yet)
    false, // openAIOAuthLoggedIn (no hahaOpenAI in Vue yet)
  ),
)

const selectedModel = computed(() =>
  isControlled.value
    ? availableModels.value.find((m) => m.id === props.value) || null
    : currentModel.value,
)

const runtimeSelection = computed(() =>
  props.runtimeKey ? runtimeStore.selections[props.runtimeKey!] : undefined,
)

const activeRuntimeSelection = computed((): RuntimeSelection | null => {
  if (!isRuntimeScoped.value) return null
  return (
    props.runtimeSelection ??
    runtimeSelection.value ??
    resolveDefaultRuntimeSelection(activeId.value, activeProviderName.value, providers.value, currentModel.value?.id)
  )
})

const selectedProviderChoice = computed(() =>
  activeRuntimeSelection.value
    ? providerChoices.value.find((c) => c.providerId === activeRuntimeSelection.value?.providerId) ?? null
    : null,
)

const selectedRuntimeModel = computed((): ModelInfo | null => {
  if (!activeRuntimeSelection.value) return null
  return (
    selectedProviderChoice.value?.models.find((m) => m.id === activeRuntimeSelection.value.modelId) ??
    { id: activeRuntimeSelection.value.modelId, name: activeRuntimeSelection.value.modelId, description: '', context: '' }
  )
})

const buttonModelLabel = computed(() =>
  isRuntimeScoped.value
    ? selectedRuntimeModel.value?.name ?? currentModel.value?.name ?? t('model.selectModel')
    : selectedModel.value?.name ?? t('model.selectModel'),
)

const buttonProviderLabel = computed(() =>
  isRuntimeScoped.value
    ? selectedProviderChoice.value?.providerName ?? activeProviderName.value ?? t('settings.providers.officialName')
    : null,
)

const selectedRuntimeEffort = computed(() =>
  activeRuntimeSelection.value?.effortLevel ?? effortLevel.value,
)

const EFFORT_OPTIONS = computed(() => [
  { value: 'low' as EffortLevel, label: t('settings.general.effort.low') },
  { value: 'medium' as EffortLevel, label: t('settings.general.effort.medium') },
  { value: 'high' as EffortLevel, label: t('settings.general.effort.high') },
  { value: 'max' as EffortLevel, label: t('settings.general.effort.max') },
])

// ─── Effects ─────────────────────────────────────────────────────────
const MOBILE_VIEWPORT_QUERY = '(max-width: 767px)'
function updateMobileViewport() {
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    isMobileBrowser.value = window.matchMedia(MOBILE_VIEWPORT_QUERY).matches
  }
}

function onDocClick(e: MouseEvent) {
  if (!open.value) return
  const target = e.target as Node
  if (
    rootRef.value && !rootRef.value.contains(target) &&
    dropdownRef.value && !dropdownRef.value.contains(target)
  ) {
    open.value = false
  }
}
function onDocKey(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = false
}

function onResize() {
  if (open.value) updateDropdownPosition()
}

onMounted(() => {
  if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
    const mq = window.matchMedia(MOBILE_VIEWPORT_QUERY)
    isMobileBrowser.value = mq.matches
    mq.addEventListener?.('change', updateMobileViewport)
    mq.addListener?.(updateMobileViewport)
  }
  document.addEventListener('mousedown', onDocClick)
  document.addEventListener('keydown', onDocKey)
  window.addEventListener('resize', onResize)
  window.addEventListener('scroll', onResize, true)
})
onUnmounted(() => {
  document.removeEventListener('mousedown', onDocClick)
  document.removeEventListener('keydown', onDocKey)
  window.removeEventListener('resize', onResize)
  window.removeEventListener('scroll', onResize, true)
})

watch(
  [isRuntimeScoped, providersLoading],
  ([scoped, loading]) => {
    if (!scoped || loading || requestedProvidersRef.value) return
    requestedProvidersRef.value = true
    providerStore.fetchProviders()
  },
)

watch(
  [isRuntimeScoped, open],
  ([scoped, isOpen]) => {
    if (!scoped || !isOpen || requestedOAuthStatusRef.value) return
    requestedOAuthStatusRef.value = true
    // stub: no hahaOAuthStores yet
  },
)

// ─── Dropdown positioning ────────────────────────────────────────────
const DROPDOWN_WIDTH = 360
const DROPDOWN_GAP = 8
const VIEWPORT_MARGIN = 16
const DROPDOWN_MAX_HEIGHT = 420
const DROPDOWN_MIN_HEIGHT = 180

function updateDropdownPosition() {
  const anchor = rootRef.value
  if (!anchor) return
  const rect = anchor.getBoundingClientRect()
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight
  const width = Math.min(DROPDOWN_WIDTH, Math.max(0, viewportWidth - VIEWPORT_MARGIN * 2))
  const left = Math.min(
    Math.max(VIEWPORT_MARGIN, rect.right - width),
    Math.max(VIEWPORT_MARGIN, viewportWidth - width - VIEWPORT_MARGIN),
  )
  const spaceBelow = viewportHeight - rect.bottom - DROPDOWN_GAP - VIEWPORT_MARGIN
  const spaceAbove = rect.top - DROPDOWN_GAP - VIEWPORT_MARGIN
  const placeBelow = spaceBelow >= DROPDOWN_MIN_HEIGHT || spaceBelow >= spaceAbove
  const availableHeight = Math.max(
    DROPDOWN_MIN_HEIGHT,
    placeBelow ? spaceBelow : spaceAbove,
  )
  const maxHeight = Math.min(DROPDOWN_MAX_HEIGHT, availableHeight)
  dropdownPosition.value = {
    top: placeBelow ? rect.bottom + DROPDOWN_GAP : undefined,
    bottom: placeBelow ? undefined : viewportHeight - rect.top + DROPDOWN_GAP,
    left,
    width,
    maxHeight,
  }
}

watch(
  open,
  (isOpen) => {
    if (!isOpen) {
      dropdownPosition.value = null
      return
    }
    nextTick(updateDropdownPosition)
  },
)

// ─── Handlers ────────────────────────────────────────────────────────
function handleRuntimeSelect(selection: RuntimeSelection) {
  emit('update:runtimeSelection', selection)
  if (props.runtimeKey) {
    runtimeStore.setSelection(props.runtimeKey, selection)
    if (props.runtimeKey !== DRAFT_RUNTIME_SELECTION_KEY) {
      chatStore.setSessionRuntime(props.runtimeKey, selection)
    }
  }
  open.value = false
}

function handleRuntimeEffortSelect(level: EffortLevel) {
  if (!activeRuntimeSelection.value) return
  handleRuntimeSelect({ ...activeRuntimeSelection.value, effortLevel: level })
}

function handleModelSelect(model: ModelInfo) {
  if (isControlled.value) {
    emit('change', model.id)
  } else {
    settingsStore.setCurrentModel(model)
  }
  open.value = false
}

const dropdownVisible = computed(() => open.value && !!dropdownPosition.value)

// Expose for scoped-slot usage
defineExpose({ open, handleToggle: () => { if (!props.disabled) open.value = !open.value } })
</script>

<template>
  <div ref="rootRef" class="relative min-w-0 shrink-0">
    <!-- Trigger button -->
    <button
      @click="handleToggle"
      :disabled="disabled"
      :class="[
        'flex items-center gap-2 rounded-full bg-[var(--color-surface-container-low)] text-xs font-medium text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] disabled:cursor-not-allowed disabled:opacity-50',
        compact ? 'max-w-[112px] px-2.5 py-1.5' : 'max-w-[280px] px-3 py-1.5',
      ]"
    >
      <div class="flex min-w-0 flex-1 items-center gap-2">
        <span
          :class="[
            compact ? 'text-xs' : 'text-sm',
            'min-w-0 flex-1 truncate font-semibold text-[var(--color-text-primary)]',
          ]"
        >
          {{ buttonModelLabel }}
        </span>
        <span
          v-if="!compact && buttonProviderLabel"
          class="max-w-[108px] flex-shrink-0 truncate text-[11px] text-[var(--color-text-tertiary)]"
        >
          {{ buttonProviderLabel }}
        </span>
      </div>
      <span class="material-symbols-outlined flex-shrink-0 text-[12px]">expand_more</span>
    </button>

    <!-- Shared dropdown content -->
    <template #dropdown-content>
      <div
        :class="['overflow-y-auto', isMobileBrowser ? 'p-1' : 'p-3']"
        :style="{ maxHeight: isMobileBrowser ? undefined : dropdownPosition?.maxHeight + 'px' }"
      >
        <div
          v-if="!isMobileBrowser"
          class="mb-2 px-1 text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)]"
        >
          {{ t('model.configuration') }}
        </div>

        <!-- Runtime-scoped: grouped by provider -->
        <div v-if="isRuntimeScoped" class="space-y-3">
          <div v-for="choice in providerChoices" :key="choice.providerId ?? 'official'" class="space-y-1.5">
            <div class="flex items-center justify-between px-2 pt-1">
              <span class="truncate text-[11px] font-semibold tracking-[0.01em] text-[var(--color-text-secondary)]">
                {{ choice.providerName }}
              </span>
              <span
                v-if="choice.isDefault"
                class="flex-shrink-0 text-[10px] font-medium text-[var(--color-text-tertiary)]"
              >
                {{ t('settings.providers.default') }}
              </span>
            </div>
            <div class="space-y-1">
              <button
                v-for="model in choice.models"
                :key="(choice.providerId ?? 'official') + ':' + model.id"
                @click="handleRuntimeSelect({ providerId: choice.providerId, modelId: model.id, effortLevel: selectedRuntimeEffort })"
                :class="[
                  'w-full rounded-lg border px-3 text-left transition-colors',
                  isMobileBrowser ? 'min-h-[56px] py-3' : 'py-2.5',
                  choice.providerId === activeRuntimeSelection?.providerId && activeRuntimeSelection?.modelId === model.id
                    ? 'border-[var(--color-model-option-selected-border)] bg-[var(--color-model-option-selected-bg)]'
                    : 'border-transparent hover:bg-[var(--color-surface-hover)]',
                ]"
              >
                <div class="flex items-start gap-3">
                  <div
                    :class="[
                      'mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full border-2',
                      choice.providerId === activeRuntimeSelection?.providerId && activeRuntimeSelection?.modelId === model.id
                        ? 'border-[var(--color-brand)]'
                        : 'border-[var(--color-outline)]',
                    ]"
                  >
                    <div
                      v-if="choice.providerId === activeRuntimeSelection?.providerId && activeRuntimeSelection?.modelId === model.id"
                      class="h-2 w-2 rounded-full bg-[var(--color-brand)]"
                    />
                  </div>
                  <div class="min-w-0 flex-1">
                    <div class="truncate text-sm font-semibold text-[var(--color-text-primary)]">
                      {{ model.name }}
                    </div>
                    <div
                      v-if="model.description"
                      class="mt-0.5 truncate pr-[6px] text-[10px] text-[var(--color-text-tertiary)]"
                    >
                      {{ model.description }}
                    </div>
                  </div>
                </div>
              </button>
            </div>
          </div>
        </div>

        <!-- Normal: flat model list -->
        <div v-else class="space-y-1">
          <button
            v-for="model in availableModels"
            :key="model.id"
            @click="handleModelSelect(model)"
            :class="[
              'w-full rounded-lg px-3 text-left transition-colors',
              isMobileBrowser ? 'min-h-[56px] py-3' : 'py-2.5',
              model.id === selectedModel?.id
                ? 'border border-[var(--color-model-option-selected-border)] bg-[var(--color-model-option-selected-bg)]'
                : 'hover:bg-[var(--color-surface-hover)]',
            ]"
          >
            <div class="flex items-center gap-3">
              <div
                :class="[
                  'flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full border-2',
                  model.id === selectedModel?.id ? 'border-[var(--color-brand)]' : 'border-[var(--color-outline)]',
                ]"
              >
                <div
                  v-if="model.id === selectedModel?.id"
                  class="h-2 w-2 rounded-full bg-[var(--color-brand)]"
                />
              </div>
              <div class="min-w-0 flex-1">
                <div class="text-sm font-semibold text-[var(--color-text-primary)]">
                  {{ model.name }}
                </div>
                <div
                  v-if="model.description"
                  class="mt-0.5 truncate text-[10px] text-[var(--color-text-tertiary)]"
                >
                  {{ model.description }}
                </div>
              </div>
            </div>
          </button>
        </div>

        <!-- Effort level section -->
        <div v-if="canEditRuntimeEffort" class="border-t border-[var(--color-border)] p-3">
          <div class="mb-2 px-1 text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)]">
            {{ t('model.effort') }}
          </div>
          <div class="grid grid-cols-4 gap-1.5">
            <button
              v-for="opt in EFFORT_OPTIONS"
              :key="opt.value"
              @click="handleRuntimeEffortSelect(opt.value)"
              :class="[
                'rounded-lg py-2 text-center text-xs font-semibold transition-colors',
                opt.value === selectedRuntimeEffort
                  ? 'bg-[var(--color-brand)] text-white'
                  : 'bg-[var(--color-surface-container-high)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]',
              ]"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
      </div>
    </template>

    <!-- Mobile bottom sheet -->
    <Teleport to="body">
      <MobileBottomSheet
        v-if="dropdownVisible && isMobileBrowser"
        :open="open"
        @close="open = false"
        :title="t('model.configuration')"
        :close-label="t('tabs.close')"
        :test-id="'model-selector-dropdown'"
      >
        <div class="overflow-y-auto p-1">
          <div v-if="isRuntimeScoped" class="space-y-3">
            <div v-for="choice in providerChoices" :key="choice.providerId ?? 'official'" class="space-y-1.5">
              <div class="flex items-center justify-between px-2 pt-1">
                <span class="truncate text-[11px] font-semibold tracking-[0.01em] text-[var(--color-text-secondary)]">
                  {{ choice.providerName }}
                </span>
                <span
                  v-if="choice.isDefault"
                  class="flex-shrink-0 text-[10px] font-medium text-[var(--color-text-tertiary)]"
                >
                  {{ t('settings.providers.default') }}
                </span>
              </div>
              <div class="space-y-1">
                <button
                  v-for="model in choice.models"
                  :key="(choice.providerId ?? 'official') + ':' + model.id"
                  @click="handleRuntimeSelect({ providerId: choice.providerId, modelId: model.id, effortLevel: selectedRuntimeEffort })"
                  :class="[
                    'w-full rounded-lg border px-3 text-left transition-colors min-h-[56px] py-3',
                    choice.providerId === activeRuntimeSelection?.providerId && activeRuntimeSelection?.modelId === model.id
                      ? 'border-[var(--color-model-option-selected-border)] bg-[var(--color-model-option-selected-bg)]'
                      : 'border-transparent hover:bg-[var(--color-surface-hover)]',
                  ]"
                >
                  <div class="flex items-start gap-3">
                    <div
                      :class="[
                        'mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full border-2',
                        choice.providerId === activeRuntimeSelection?.providerId && activeRuntimeSelection?.modelId === model.id
                          ? 'border-[var(--color-brand)]'
                          : 'border-[var(--color-outline)]',
                      ]"
                    >
                      <div
                        v-if="choice.providerId === activeRuntimeSelection?.providerId && activeRuntimeSelection?.modelId === model.id"
                        class="h-2 w-2 rounded-full bg-[var(--color-brand)]"
                      />
                    </div>
                    <div class="min-w-0 flex-1">
                      <div class="truncate text-sm font-semibold text-[var(--color-text-primary)]">
                        {{ model.name }}
                      </div>
                      <div
                        v-if="model.description"
                        class="mt-0.5 truncate pr-[6px] text-[10px] text-[var(--color-text-tertiary)]"
                      >
                        {{ model.description }}
                      </div>
                    </div>
                  </div>
                </button>
              </div>
            </div>
          </div>

          <div v-else class="space-y-1">
            <button
              v-for="model in availableModels"
              :key="model.id"
              @click="handleModelSelect(model)"
              :class="[
                'w-full rounded-lg px-3 text-left transition-colors min-h-[56px] py-3',
                model.id === selectedModel?.id
                  ? 'border border-[var(--color-model-option-selected-border)] bg-[var(--color-model-option-selected-bg)]'
                  : 'hover:bg-[var(--color-surface-hover)]',
              ]"
            >
              <div class="flex items-center gap-3">
                <div
                  :class="[
                    'flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full border-2',
                    model.id === selectedModel?.id ? 'border-[var(--color-brand)]' : 'border-[var(--color-outline)]',
                  ]"
                >
                  <div
                    v-if="model.id === selectedModel?.id"
                    class="h-2 w-2 rounded-full bg-[var(--color-brand)]"
                  />
                </div>
                <div class="min-w-0 flex-1">
                  <div class="text-sm font-semibold text-[var(--color-text-primary)]">
                    {{ model.name }}
                  </div>
                  <div
                    v-if="model.description"
                    class="mt-0.5 truncate text-[10px] text-[var(--color-text-tertiary)]"
                  >
                    {{ model.description }}
                  </div>
                </div>
              </div>
            </button>
          </div>

          <div v-if="canEditRuntimeEffort" class="border-t border-[var(--color-border)] p-3">
            <div class="mb-2 px-1 text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)]">
              {{ t('model.effort') }}
            </div>
            <div class="grid grid-cols-4 gap-1.5">
              <button
                v-for="opt in EFFORT_OPTIONS"
                :key="opt.value"
                @click="handleRuntimeEffortSelect(opt.value)"
                :class="[
                  'rounded-lg py-2 text-center text-xs font-semibold transition-colors',
                  opt.value === selectedRuntimeEffort
                    ? 'bg-[var(--color-brand)] text-white'
                    : 'bg-[var(--color-surface-container-high)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]',
                ]"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
        </div>
      </MobileBottomSheet>
    </Teleport>

    <!-- Desktop portal dropdown -->
    <Teleport to="body">
      <div
        v-if="dropdownVisible && !isMobileBrowser"
        ref="dropdownRef"
        data-testid="model-selector-dropdown"
        class="fixed z-[80] rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-[var(--shadow-dropdown)]"
        :style="{
          top: dropdownPosition?.top != null ? dropdownPosition.top + 'px' : undefined,
          bottom: dropdownPosition?.bottom != null ? dropdownPosition.bottom + 'px' : undefined,
          left: dropdownPosition?.left + 'px',
          width: dropdownPosition?.width + 'px',
        }"
      >
        <div class="overflow-y-auto p-3" :style="{ maxHeight: dropdownPosition?.maxHeight + 'px' }">
          <div class="mb-2 px-1 text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)]">
            {{ t('model.configuration') }}
          </div>

          <div v-if="isRuntimeScoped" class="space-y-3">
            <div v-for="choice in providerChoices" :key="choice.providerId ?? 'official'" class="space-y-1.5">
              <div class="flex items-center justify-between px-2 pt-1">
                <span class="truncate text-[11px] font-semibold tracking-[0.01em] text-[var(--color-text-secondary)]">
                  {{ choice.providerName }}
                </span>
                <span
                  v-if="choice.isDefault"
                  class="flex-shrink-0 text-[10px] font-medium text-[var(--color-text-tertiary)]"
                >
                  {{ t('settings.providers.default') }}
                </span>
              </div>
              <div class="space-y-1">
                <button
                  v-for="model in choice.models"
                  :key="(choice.providerId ?? 'official') + ':' + model.id"
                  @click="handleRuntimeSelect({ providerId: choice.providerId, modelId: model.id, effortLevel: selectedRuntimeEffort })"
                  :class="[
                    'w-full rounded-lg border px-3 text-left transition-colors py-2.5',
                    choice.providerId === activeRuntimeSelection?.providerId && activeRuntimeSelection?.modelId === model.id
                      ? 'border-[var(--color-model-option-selected-border)] bg-[var(--color-model-option-selected-bg)]'
                      : 'border-transparent hover:bg-[var(--color-surface-hover)]',
                  ]"
                >
                  <div class="flex items-start gap-3">
                    <div
                      :class="[
                        'mt-0.5 flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full border-2',
                        choice.providerId === activeRuntimeSelection?.providerId && activeRuntimeSelection?.modelId === model.id
                          ? 'border-[var(--color-brand)]'
                          : 'border-[var(--color-outline)]',
                      ]"
                    >
                      <div
                        v-if="choice.providerId === activeRuntimeSelection?.providerId && activeRuntimeSelection?.modelId === model.id"
                        class="h-2 w-2 rounded-full bg-[var(--color-brand)]"
                      />
                    </div>
                    <div class="min-w-0 flex-1">
                      <div class="truncate text-sm font-semibold text-[var(--color-text-primary)]">
                        {{ model.name }}
                      </div>
                      <div
                        v-if="model.description"
                        class="mt-0.5 truncate pr-[6px] text-[10px] text-[var(--color-text-tertiary)]"
                      >
                        {{ model.description }}
                      </div>
                    </div>
                  </div>
                </button>
              </div>
            </div>
          </div>

          <div v-else class="space-y-1">
            <button
              v-for="model in availableModels"
              :key="model.id"
              @click="handleModelSelect(model)"
              :class="[
                'w-full rounded-lg px-3 text-left transition-colors py-2.5',
                model.id === selectedModel?.id
                  ? 'border border-[var(--color-model-option-selected-border)] bg-[var(--color-model-option-selected-bg)]'
                  : 'hover:bg-[var(--color-surface-hover)]',
              ]"
            >
              <div class="flex items-center gap-3">
                <div
                  :class="[
                    'flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-full border-2',
                    model.id === selectedModel?.id ? 'border-[var(--color-brand)]' : 'border-[var(--color-outline)]',
                  ]"
                >
                  <div
                    v-if="model.id === selectedModel?.id"
                    class="h-2 w-2 rounded-full bg-[var(--color-brand)]"
                  />
                </div>
                <div class="min-w-0 flex-1">
                  <div class="text-sm font-semibold text-[var(--color-text-primary)]">
                    {{ model.name }}
                  </div>
                  <div
                    v-if="model.description"
                    class="mt-0.5 truncate text-[10px] text-[var(--color-text-tertiary)]"
                  >
                    {{ model.description }}
                  </div>
                </div>
              </div>
            </button>
          </div>

          <div v-if="canEditRuntimeEffort" class="border-t border-[var(--color-border)] p-3">
            <div class="mb-2 px-1 text-[10px] font-bold uppercase tracking-widest text-[var(--color-outline)]">
              {{ t('model.effort') }}
            </div>
            <div class="grid grid-cols-4 gap-1.5">
              <button
                v-for="opt in EFFORT_OPTIONS"
                :key="opt.value"
                @click="handleRuntimeEffortSelect(opt.value)"
                :class="[
                  'rounded-lg py-2 text-center text-xs font-semibold transition-colors',
                  opt.value === selectedRuntimeEffort
                    ? 'bg-[var(--color-brand)] text white'
                    : 'bg-[var(--color-surface-container-high)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]',
                ]"
              >
                {{ opt.label }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>