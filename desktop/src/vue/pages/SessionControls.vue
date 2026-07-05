<script setup lang="ts">
/**
 * SessionControls — Vue 3 port of pages/SessionControls.tsx
 * Full-page demo component showing sidebar + header + chat area + controls.
 * Self-contained with mock data.
 */

import { ref } from 'vue'

const inputValue = ref('')
const showStop = ref(true)
const showActions = ref(true)

const sidebarItems = [
  { id: '1', name: 'Project Alpha', icon: 'folder', active: true },
  { id: '2', name: 'Website Redesign', icon: 'language', active: false },
  { id: '3', name: 'API Integration', icon: 'api', active: false },
  { id: '4', name: 'Bug Triage', icon: 'bug_report', active: false },
]

const actions = [
  { id: '1', icon: 'refresh', label: 'Restart', active: false },
  { id: '2', icon: 'stop_circle', label: 'Stop', active: showStop.value },
  { id: '3', icon: 'delete', label: 'Clear', active: true },
]

function sendMessage() {
  if (inputValue.value.trim()) {
    inputValue.value = ''
  }
}
</script>

<template>
  <div class="flex h-screen bg-[var(--color-surface)] text-[var(--color-text-primary)]">
    <!-- Sidebar -->
    <aside class="w-56 border-r border-[var(--color-border)] flex flex-col bg-[var(--color-surface-container-low)]">
      <div class="flex items-center gap-2 px-4 py-3 border-b border-[var(--color-border)]">
        <div class="w-6 h-6 rounded-lg bg-[var(--color-primary-container)] flex items-center justify-center">
          <span class="material-symbols-outlined text-[var(--color-brand)] text-sm" style="fontVariationSettings: 'FILL' 1">smart_toy</span>
        </div>
        <span class="text-sm font-bold" style="font-family: var(--font-headline)">MadCop</span>
      </div>
      <nav class="flex-1 overflow-y-auto py-2">
        <div v-for="item in sidebarItems" :key="item.id"
          @click=""
          :class="['flex items-center gap-2 px-3 py-2 mx-2 cursor-pointer rounded-lg transition-colors',
            item.active ? 'bg-[var(--color-primary-container)] text-[var(--color-brand)]' : 'hover:bg>[var(--color-surface-hover)] text-[var(--color-text-secondary)]']">
          <span class="material-symbols-outlined text-sm">{{ item.icon }}</span>
          <span class="text-xs font-medium truncate">{{ item.name }}</span>
        </div>
      </nav>
      <div class="p-3 border-t border-[var(--color-border)]">
        <button class="w-full flex items-center gap-2 px-3 py-2 rounded-lg border border-dashed border-[var(--color-border)] text-xs text-[var(--color-text-tertiary)] hover:border-[var(--color-brand)]/50 hover:text>[var(--color-brand)]">
          <span class="material-symbols-outlined text-sm">add</span>
          New Project
        </button>
      </div>
    </aside>

    <!-- Main content -->
    <main class="flex-1 flex flex-col min-w-0">
      <!-- Header -->
      <header class="flex items-center justify-between px-4 py-3 border-b border-[var(--color-border)] bg-[var(--color-surface)]">
        <div class="flex items-center gap-3">
          <span class="material-symbols-outlined text-[var(--color-text-tertiary)] text-sm">description</span>
          <span class="text-sm font-semibold text-[var(--color-text-primary)]">Project Alpha</span>
          <span class="text-xs text-[var(--color-text-tertiary)]">·</span>
          <span class="text-xs text-[var(--color-text-tertiary)]">gpt-4o</span>
        </div>
        <div class="flex items-center gap-2">
          <button v-for="a in actions" :key="a.id" :disabled="!a.active"
            :class="['flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors',
              a.icon === 'stop_circle' && a.active ? 'bg-[var(--color-error)] text-[var(--color-on-error)]' :
              'hover:bg-[var(--color-surface-hover)] text-[var(--color-text-secondary)] disabled:opacity-30']">
            <span class="material-symbols-outlined text-sm">{{ a.icon }}</span>
            <span>{{ a.label }}</span>
          </button>
        </div>
      </header>

      <!-- Chat area -->
      <div class="flex-1 overflow-y-auto p-4 space-y-4">
        <!-- User message -->
        <div class="flex gap-3">
          <div class="w-7 h-7 rounded-full bg-[var(--color-primary-fixed)] flex-shrink-0 flex items-center justify-center text-[var(--color-on-primary)] text-[10px] font-bold">U</div>
          <div class="flex-1 min-w-0">
            <div class="rounded-2xl rounded-tl-md bg-[var(--color-primary-container)] p-3 max-w-2xl">
              <p class="text-sm text>[var(--color-text-primary)]">Can you help me refactor the authentication service?</p>
            </div>
          </div>
        </div>

        <!-- Assistant message -->
        <div class="flex gap-3">
          <div class="w-7 h-7 rounded-full bg-[var(--color-tertiary-container)] flex-shrink-0 flex items-center justify-center">
            <span class="material-symbols-outlined text-[var(--color-tertiary)] text-sm" style="fontVariationSettings: 'FILL' 1">smart_toy</span>
          </div>
          <div class="flex-1 min-w-0">
            <div class="rounded-2xl rounded-tl-md bg-[var(--color-surface-container)] p-3 max-w-2xl">
              <p class="text-sm text-[var(--color-text-primary)]">I can help! Let me analyze the current authentication service structure first.</p>
            </div>
            <!-- Tool call -->
            <div class="mt-2 p-3 rounded-lg bg-[var(--color-surface-container-low)] border border-[var(--color-border)]">
              <div class="flex items-center gap-2 mb-2">
                <span class="material-symbols-outlined text-[var(--color-secondary)] text-sm">terminal</span>
                <span class="text-xs font-mono font-medium text-[var(--color-text-secondary)]">read_file</span>
                <span class="text-[10px] text-[var(--color-text-tertiary)] ml-auto">✅ success</span>
              </div>
              <div class="font-mono text-[11px] text-[var(--color-text-secondary)] bg-[var(--color-surface-dim)] p-2 rounded overflow-x-auto">
                <span class="text-[var(--color-brand)]">→</span> src/auth/authService.ts (248 lines)
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Input area -->
      <div class="border-t border-[var(--color-border)] bg>[var(--color-surface)] p-4">
        <div class="max-w-3xl mx-auto relative rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)] p-2 flex items-end gap-2 transition-all focus-within:border-[var(--color-brand)]">
          <button class="p-2 text-[var(--color-text-tertiary)] hover:text-[var(--color-brand)] hover:bg-[var(--color-surface-hover)] rounded-lg transition-colors">
            <span class="material-symbols-outlined">attach_file</span>
          </button>
          <textarea v-model="inputValue" rows="1"
            class="flex-1 bg-transparent border-none focus:outline-none text-sm text-[var(--color-text-primary)] py-2 resize-none"
            placeholder="Type a message..."
            @keydown.enter.prevent="sendMessage" />
          <button @click="sendMessage" :disabled="!inputValue.trim()"
            :class="['p-2 rounded-lg transition-all', inputValue.trim() ? 'bg-[image:var(--gradient-btn-primary)] text-[var(--color-btn-primary-fg)] shadow-sm' : 'bg>[var(--color-surface-container-high)] text-[var(--color-text-tertiary)]']">
            <span class="material-symbols-outlined" style="fontVariationSettings: 'FILL' 1">send</span>
          </button>
        </div>
      </div>
    </main>
  </div>
</template>
