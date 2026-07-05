<script setup lang="ts">
// v3.0 — StatusPill (Vue 3)
// Direct translation of StatusPill component from PluginDetail.tsx
import { computed } from 'vue'
import { useTranslation } from '../../../i18n'

const props = defineProps<{
  enabled: boolean
  hasErrors: boolean
}>()

const t = useTranslation()

const classes = computed(() =>
  props.hasErrors
    ? 'bg-[var(--color-error)]/12 text-[var(--color-error)]'
    : props.enabled
      ? 'bg-[var(--color-success-container)] text-[var(--color-success)]'
      : 'bg-[var(--color-surface-container-high)] text-[var(--color-text-tertiary)]'
)

const label = computed(() =>
  props.hasErrors
    ? t('settings.plugins.status.attention')
    : props.enabled
      ? t('settings.plugins.status.enabled')
      : t('settings.plugins.status.disabled')
)
</script>

<template>
  <span class="rounded-full px-2 py-0.5 text-[10px] font-medium" :class="classes">
    {{ label }}
  </span>
</template>