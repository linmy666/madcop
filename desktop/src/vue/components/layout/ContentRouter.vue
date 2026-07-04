<script setup lang="ts">
// v3.0 — ContentRouter (Vue 3)
// Direct translation — routes active tab type to the correct page.
// Uses defineAsyncComponent for lazy-loaded pages.
import { computed, defineAsyncComponent } from 'vue'

const EmptySession = defineAsyncComponent(() => import('../../pages/EmptySession.vue'))
const Settings = defineAsyncComponent(() => import('../../pages/Settings.vue'))
const ScheduledTasks = defineAsyncComponent(() => import('../../pages/ScheduledTasks.vue'))
const DesignPage = defineAsyncComponent(() => import('../../pages/DesignPage.vue'))
const ChatPage = defineAsyncComponent(() => import('../../pages/ChatPage.vue'))

const props = defineProps<{
  activeTabType?: string | null
  activeTabId?: string | null
}>()

const page = computed(() => {
  if (!props.activeTabId || !props.activeTabType) return 'empty'
  if (props.activeTabType === 'settings') return 'settings'
  if (props.activeTabType === 'scheduled') return 'scheduled'
  if (props.activeTabType === 'design') return 'design'
  if (props.activeTabType === 'session') return 'chat'
  return 'empty'
})
</script>

<template>
  <div class="relative min-h-0 flex-1 overflow-hidden">
    <div class="absolute inset-0 z-10 flex min-h-0 flex-col overflow-hidden">
      <EmptySession v-if="page === 'empty'" />
      <Settings v-else-if="page === 'settings'" />
      <ScheduledTasks v-else-if="page === 'scheduled'" />
      <DesignPage v-else-if="page === 'design'" />
      <ChatPage v-else-if="page === 'chat'" />
    </div>
  </div>
</template>
