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
      <h2 class="text-base font-semibold text-[var(--color-text-primary)] mb-1">
        {{ t('settings.plugins.title') }}
      </h2>
      <p class="text-sm text-[var(--color-text-tertiary)] mb-4">
        {{ t('settings.plugins.description') }}
      </p>
      <PluginList />
    </template>
  </div>
</template>