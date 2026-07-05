<script setup lang="ts">
/**
 * WorkspaceFileOpenWith — Vue 3 port of components/workspace/WorkspaceFileOpenWith.tsx
 * Context menu for opening workspace files (app browser, system, targets).
 * Prop-driven: parent passes absolutePath, sessionId, workspacePath.
 * No React store imports — uses @/emit for actions.
 */

export interface WorkspaceFileOpenWithProps {
  absolutePath: string
  sessionId?: string
  workspacePath?: string
}

const props = withDefaults(defineProps<WorkspaceFileOpenWithProps>(), {
  workspacePath: undefined,
})

const emit = defineEmits<{
  openInAppBrowser: [url: string]
  openWorkspacePreview: [relPath: string]
  openSystem: [path: string]
  openTarget: [id: string, path: string]
  afterSelect: []
}>()

const target: { label: string; icon: string; target?: string } = {
  label: 'Open in App Browser',
  icon: 'open_in_new',
}

const items = computed(() => [
  { id: 'browser', label: 'Open in App Browser', icon: 'open_in_new' },
  { id: 'workspace', label: 'Preview in Workspace', icon: 'description' },
  { id: 'system', label: 'Open in System', icon: 'launch', target: 'system' },
])

function onSelect(id: string) {
  emit('afterSelect')
  switch (id) {
    case 'browser': emit('openInAppBrowser', props.absolutePath); break
    case 'workspace': emit('openWorkspacePreview', props.absolutePath); break
    case 'system': emit('openSystem', props.absolutePath); break
    default: emit('openTarget', id, props.absolutePath)
  }
}
</script>

<template>
  <template v-if="items.length > 0">
    <div class="my-1 border-t border-[var(--color-border)]" role="separator" />
    <button v-for="item in items" :key="item.id"
      type="button" role="menuitem" @click="onSelect(item.id)"
      class="flex w-full items-center gap-2 px-3 py-1.5 text-left text-[var(--color-text-primary)] hover:bg-[var(--color-surface-hover)]">
      <span aria-hidden="true" class="flex h-[14px] w-[14px] items-center justify-center text-[var(--color-text-tertiary)]">
        <span class="material-symbols-outlined text-[14px]">{{ item.icon }}</span>
      </span>
      <span class="truncate">{{ item.label }}</span>
    </button>
  </template>
</template>
