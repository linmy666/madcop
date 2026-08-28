<script setup lang="ts">
/**
 * One session row in the sidebar project group.
 */
import { computed } from 'vue'
import type { SessionListItem } from '../../../types/session'

const props = defineProps<{
  session: SessionListItem
  active: boolean
  batchMode: boolean
  selected: boolean
  isRunning?: boolean
  isWorktree?: boolean
  renaming: boolean
  renameValue: string
  missingDirLabel?: string
  relativeTime?: string
}>()

const emit = defineEmits<{
  (e: 'click', ev: MouseEvent): void
  (e: 'contextmenu', ev: MouseEvent): void
  (e: 'finish-rename'): void
  (e: 'cancel-rename'): void
  (e: 'update:renameValue', v: string): void
}>()

const rowClass = computed(() => {
  if (props.selected) {
    return 'sidebar-session-row--selected bg-[var(--color-sidebar-item-active)] text-[var(--color-text-primary)]'
  }
  if (props.active) {
    return 'sidebar-session-row--active bg-[var(--color-sidebar-item-active)] text-[var(--color-text-primary)]'
  }
  return 'sidebar-session-row--idle text-[var(--color-text-secondary)] hover:bg-[var(--color-sidebar-item-hover)] hover:text-[var(--color-text-primary)]'
})
</script>

<template>
  <div class="sidebar-session-row relative mb-0.5 last:mb-0">
    <input
      v-if="renaming"
      :value="renameValue"
      class="w-full rounded-[var(--radius-md)] border border-[var(--color-border-focus)] bg-[var(--color-surface)] px-3 py-2 text-sm text-[var(--color-text-primary)] outline-none"
      autofocus
      @input="emit('update:renameValue', ($event.target as HTMLInputElement).value)"
      @blur="emit('finish-rename')"
      @keydown.enter="emit('finish-rename')"
      @keydown.escape="emit('cancel-rename')"
    />
    <button
      v-else
      type="button"
      :class="`group/session w-full rounded-lg px-2.5 py-1.5 text-left text-[13px] transition-[background-color,color,box-shadow] duration-150 ease-out active:scale-[0.985] motion-reduce:transition-none ${rowClass}`"
      :aria-pressed="batchMode ? selected : undefined"
      @click="emit('click', $event)"
      @contextmenu="emit('contextmenu', $event)"
    >
      <span class="flex min-w-0 items-center gap-2">
        <span
          v-if="batchMode"
          :class="`flex h-4 w-4 flex-shrink-0 items-center justify-center rounded-[5px] border transition-colors ${
            selected
              ? 'border-[var(--color-brand)] bg-[var(--color-brand)] text-white'
              : 'border-[var(--color-border)] bg-[var(--color-surface)]'
          }`"
          aria-hidden="true"
        >
          <span v-if="selected" class="material-symbols-outlined text-[12px]">check</span>
        </span>
        <span
          :class="`min-w-0 flex-1 truncate font-medium tracking-normal ${
            session.title ? '' : 'italic text-[var(--color-text-tertiary)]'
          }`"
        >
          {{ session.title || '新对话' }}
        </span>
        <span
          v-if="!session.workDirExists"
          class="flex-shrink-0 text-[10px] text-[var(--color-warning)]"
          :title="session.workDir ?? ''"
        >
          {{ missingDirLabel || '!' }}
        </span>
        <span
          v-if="isRunning"
          class="h-1.5 w-1.5 shrink-0 rounded-full bg-[var(--color-brand)]"
          title="running"
        />
        <span
          v-if="isWorktree"
          class="material-symbols-outlined shrink-0 text-[12px] text-[var(--color-text-tertiary)]"
        >account_tree</span>
        <span
          v-if="relativeTime"
          class="shrink-0 text-[10px] tabular-nums text-[var(--color-text-tertiary)]"
        >{{ relativeTime }}</span>
      </span>
    </button>
  </div>
</template>

<style scoped>
.sidebar-session-row {
  content-visibility: auto;
  contain-intrinsic-size: auto 36px;
}
/* Selected/active = the same quiet treatment as the 新对话 nav item:
   soft neutral fill only. The old 3px brand bar + brand ring combo
   read as heavy next to it (user: "prefer the first style"). */
.sidebar-session-row--active,
.sidebar-session-row--selected {
  box-shadow: none;
}
</style>
