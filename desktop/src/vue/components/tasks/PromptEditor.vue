<script setup lang="ts">
// v3.0 — PromptEditor (Vue 3)
// Full translation of PromptEditor.tsx — same Tailwind classes, same layout.
import { useTranslation } from '../../i18n'
import ModelSelector from '../controls/ModelSelector.vue'
import DirectoryPicker from '../shared/DirectoryPicker.vue'

const props = defineProps<{
  value: string
  placeholder?: string

  modelId: string
  providerId?: string | null

  folderPath: string
  useWorktree: boolean
}>()

const emit = defineEmits<{
  (e: 'change', value: string): void
  (e: 'modelChange', modelId: string): void
  (e: 'providerIdChange', providerId: string | null): void
  (e: 'folderPathChange', path: string): void
  (e: 'useWorktreeChange', checked: boolean): void
}>()

const t = useTranslation()

function onModelSelectionChange(selection: { modelId: string; providerId: string | null }) {
  emit('modelChange', selection.modelId)
  emit('providerIdChange', selection.providerId)
}
</script>

<template>
  <div
    class="rounded-[var(--radius-lg)] border border-[var(--color-border)] focus-within:border-[var(--color-border-focus)] transition-colors overflow-visible"
  >
    <!-- Prompt textarea -->
    <textarea
      :value="value"
      @input="(e) => emit('change', (e.target as HTMLTextAreaElement).value)"
      :placeholder="placeholder"
      rows="4"
      class="w-full resize-y bg-transparent px-3 py-2.5 text-sm leading-relaxed text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)]"
      style="min-height: 120px;"
    />

    <!-- Bottom toolbar -->
    <div
      class="border-t border-[var(--color-border)]/40 px-3 py-2 flex flex-col gap-2 bg-[var(--color-surface-container-low)] rounded-b-[var(--radius-lg)]"
    >
      <!-- Row 1: Permission + Model selectors -->
      <div class="flex items-center justify-between">
        <div
          class="inline-flex items-center gap-1.5 rounded-full bg-[var(--color-error)]/8 px-2.5 py-1.5 text-xs font-medium text-[var(--color-error)]"
        >
          <span class="material-symbols-outlined text-[14px]">gavel</span>
          {{ t('newTask.fullPermissions') }}
        </div>
        <ModelSelector
          :runtime-selection="modelId ? { providerId: providerId ?? null, modelId } : undefined"
          @runtime-selection-change="onModelSelectionChange"
        />
      </div>

      <!-- Row 2: Folder picker -->
      <div class="flex items-center justify-between">
        <DirectoryPicker
          :value="folderPath"
          @change="(path: string) => emit('folderPathChange', path)"
        />
      </div>

      <div
        class="flex items-center gap-1.5 px-2 py-1.5 rounded-md bg-[var(--color-error)]/8 text-[10px] text-[var(--color-error)]"
      >
        <span class="material-symbols-outlined text-[12px]">warning</span>
        {{ t('promptEditor.bypassWarning') }}
        {{
          folderPath
            ? ` ${t('promptEditor.within')} ${folderPath}`
            : ` ${t('promptEditor.selectFolder')}`
        }}.
      </div>
    </div>
  </div>
</template>
