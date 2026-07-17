<script setup lang="ts">
import { usePluginStore } from '../stores/pluginStore'
import { useTranslation } from '../i18n'
import PluginList from './PluginList.vue'
import PluginDetail from './PluginDetail.vue'

const pluginStore = usePluginStore()
const t = useTranslation()
</script>

<template>
  <div class="w-full min-w-0">
    <template v-if="pluginStore.selectedPlugin">
      <PluginDetail />
    </template>
    <template v-else>
      <section class="mb-5 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)]">
        <div class="px-5 py-5">
          <div class="mb-2 text-[11px] font-semibold tracking-wide text-[var(--color-text-tertiary)]">
            {{ t('settings.nav.system') || '系统' }}
          </div>
          <div class="mb-2 flex items-center gap-2">
            <span class="material-symbols-outlined text-[20px] text-[var(--color-brand)]" style="fontVariationSettings: 'FILL' 1">extension</span>
            <h2 class="text-lg font-semibold text-[var(--color-text-primary)]">
              {{ t('settings.plugins.title') }}
            </h2>
          </div>
          <p class="max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">
            {{ t('settings.plugins.description') }}
          </p>
        </div>
      </section>
      <PluginList />
    </template>
  </div>
</template>
