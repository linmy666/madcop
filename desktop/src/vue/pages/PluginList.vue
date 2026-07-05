<script setup lang="ts">
import { usePluginStore } from '../stores/pluginStore'
import { onMounted } from 'vue'

const pluginStore = usePluginStore()

onMounted(() => {
  void pluginStore.fetchPlugins()
})
</script>

<template>
  <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
    <div v-if="pluginStore.isLoading" class="flex justify-center py-12">
      <div class="animate-spin w-5 h-5 border-2 border-[var(--color-brand)] border-t-transparent rounded-full" />
    </div>
    <div v-else-if="pluginStore.plugins.length === 0" class="text-center py-12 text-[var(--color-text-tertiary)]">
      No plugins available
    </div>
    <div v-else class="space-y-2">
      <div
        v-for="plugin in pluginStore.plugins"
        :key="plugin.id"
        class="flex items-center justify-between p-3 rounded-lg hover:bg-[var(--color-surface-container-low)] cursor-pointer transition-colors"
        @click="pluginStore.selectPlugin(plugin)"
      >
        <div class="min-w-0">
          <div class="text-sm font-medium text-[var(--color-text-primary)] truncate">{{ plugin.name }}</div>
          <div class="text-xs text-[var(--color-text-tertiary)] truncate">{{ plugin.description }}</div>
        </div>
        <span class="text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)]">{{ plugin.source }}</span>
      </div>
    </div>
  </div>
</template>