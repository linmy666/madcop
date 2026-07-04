<script setup lang="ts">
// v3.0 — WorkbenchTab (Vue 3)
// Direct translation — same Tailwind classes. WorkbenchPanel deferred.
const props = defineProps<{ tabId: string; sessionId: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()
</script>

<template>
  <div data-testid="workbench-tab" class="flex min-h-0 flex-1 flex-col bg-[var(--color-surface)]">
    <slot :session-id="sessionId" :on-close="() => emit('close')" />
  </div>
</template>
