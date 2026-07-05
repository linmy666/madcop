<script setup lang="ts">
import { usePluginStore } from '../stores/pluginStore'
import { useTranslation } from '../../../i18n'
import Button from '../controls/Button.vue'

const pluginStore = usePluginStore()
const t = useTranslation()

const handleBack = () => {
  pluginStore.selectPlugin(null)
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex items-center gap-3">
      <Button variant="ghost" size="sm" @click="handleBack">
        <span class="material-symbols-outlined text-[18px]">arrow_back</span>
        <span class="ml-1">{{ t('common.back') }}</span>
      </Button>
      <h2 class="text-lg font-semibold text-[var(--color-text-primary)]">
        {{ pluginStore.selectedPlugin?.name }}
      </h2>
    </div>
    <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <p class="text-sm text-[var(--color-text-tertiary)]">{{ pluginStore.selectedPlugin?.description }}</p>
      <div class="mt-4 flex items-center gap-2">
        <span class="text-xs text-[var(--color-text-tertiary)]">Source:</span>
        <span class="text-xs text-[var(--color-text-primary)]">{{ pluginStore.selectedPlugin?.source }}</span>
      </div>
    </div>
  </div>
</template>