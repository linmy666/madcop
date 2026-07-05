<script setup lang="ts">
// v3.0 — SkillPreviewCard (Vue 3)
// Direct translation of SkillPreviewCard component from PluginDetail.tsx
import { computed } from 'vue'
import { useTranslation } from '../../i18n'

const props = withDefaults(
  defineProps<{
    name: string
    rawName?: string
    description: string
    version?: string
    disabled?: boolean
  }>(),
  {
    rawName: undefined,
    version: undefined,
    disabled: false,
  }
)

defineEmits<{
  (e: 'click'): void
}>()

const t = useTranslation()
const slashName = computed(() => props.rawName || props.name)
</script>

<template>
  <button
    type="button"
    @click="$emit('click')"
    :disabled="disabled"
    class="group rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-left transition-colors hover:border-[var(--color-border-focus)] hover:bg-[var(--color-surface-hover)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-brand)] disabled:cursor-default disabled:opacity-70 disabled:hover:border-[var(--color-border)] disabled:hover:bg-[var(--color-surface)]"
  >
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-2 flex-wrap min-w-0">
        <span class="text-sm font-semibold text-[var(--color-text-primary)] break-all">{{ name }}</span>
        <span v-if="version" class="rounded-full bg-[var(--color-surface-container-high)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-text-tertiary)]">
          v{{ version }}
        </span>
        <span class="rounded-full border border-[var(--color-border)] px-2 py-0.5 text-[10px] font-medium text-[var(--color-text-tertiary)]">
          {{ t('settings.skills.slashCommand') }}
        </span>
      </div>
      <span class="material-symbols-outlined text-[18px] text-[var(--color-text-tertiary)] transition-transform group-hover:translate-x-0.5">
        chevron_right
      </span>
    </div>
    <div class="mt-1 text-[11px] text-[var(--color-text-tertiary)] break-all">/{{ slashName }}</div>
    <div class="mt-2 text-xs leading-5 text-[var(--color-text-secondary)] break-words">{{ description }}</div>
  </button>
</template>