<script setup lang="ts">
// v3.0 — TitleBar (Vue 3)
// Direct translation — same Tailwind classes, same SVG icons.
import { ref } from 'vue'

const activeView = ref<'code' | 'terminal' | 'history'>('code')

function setActiveView(view: 'code' | 'terminal' | 'history') {
  activeView.value = view
}
</script>

<template>
  <div
    class="h-[var(--titlebar-height)] flex items-center border-b border-[var(--color-border)] bg-[var(--color-surface)] select-none"
    data-desktop-drag-region
  >
    <div class="w-[78px] flex-shrink-0" data-desktop-drag-region />

    <div class="flex items-center gap-2 mr-4" data-desktop-drag-region>
      <span class="text-xs font-bold tracking-wider text-[var(--color-brand)] uppercase">MadCop Agent Companion</span>
    </div>

    <div class="flex items-center gap-1 mr-4">
      <button class="p-1 rounded-[var(--radius-md)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] transition-colors">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M15 18l-6-6 6-6" />
        </svg>
      </button>
      <button class="p-1 rounded-[var(--radius-md)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] transition-colors">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M9 18l6-6-6-6" />
        </svg>
      </button>
    </div>

    <div class="flex-1 flex items-center justify-center gap-1" data-desktop-drag-region>
      <button
        v-for="tab in [
          { id: 'code', icon: 'code', label: '代码' },
          { id: 'terminal', icon: 'terminal', label: '终端' },
          { id: 'history', icon: 'history', label: '历史' },
        ]" :key="tab.id"
        @click="setActiveView(tab.id as any)"
        :class="[
          'flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-[var(--radius-md)] transition-colors duration-200',
          activeView === tab.id
            ? 'bg-[var(--color-surface-selected)] text-[var(--color-text-primary)]'
            : 'text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]',
        ]"
      >
        <span class="material-symbols-outlined text-[16px]">{{ tab.icon }}</span>
        {{ tab.label }}
      </button>
    </div>

    <div class="flex items-center gap-2 mr-4">
      <button class="p-1.5 rounded-[var(--radius-md)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] transition-colors">
        <span class="material-symbols-outlined text-[18px]">settings</span>
      </button>
    </div>
  </div>
</template>
