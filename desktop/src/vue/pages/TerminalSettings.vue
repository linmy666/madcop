<script setup lang="ts">
import { ref } from 'vue'

const shellPath = ref('/bin/bash')
const fontSize = ref(13)
const lineSpacing = ref(1.5)
const showScrollbar = ref(true)
const enableSuggestion = ref(true)

const sections = [
  { key: 'general', label: 'General' },
  { key: 'appearance', label: 'Appearance' },
  { key: 'suggestions', label: 'Suggestions' },
]
const activeSection = ref('general')
</script>

<template>
  <div class="h-full flex flex-col bg-[var(--color-surface)]">
    <div class="flex border-b border-[var(--color-border)]">
      <button v-for="s in sections" :key="s.key"
        @click="activeSection = s.key"
        :class="['flex-1 px-4 py-2.5 text-xs font-semibold border-b-2 transition-colors',
          activeSection === s.key ? 'border-[var(--color-brand)] text-[var(--color-brand)]' :
          'border-transparent text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]']">
        {{ s.label }}
      </button>
    </div>
    <div class="flex-1 overflow-y-auto p-6 space-y-6">
      <!-- General -->
      <div v-if="activeSection === 'general'">
        <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">terminal</span>
          General Settings
        </h2>
        <div class="space-y-4">
          <div class="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <p class="text-sm font-semibold text-[var(--color-text-primary)] mb-1">Shell Path</p>
            <p class="text-xs text-[var(--color-text-tertiary)] mb-3">Default shell for terminal sessions</p>
            <input v-model="shellPath" type="text"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm font-mono focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30" />
          </div>
        </div>
      </div>
      <!-- Appearance -->
      <div v-else-if="activeSection === 'appearance'">
        <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">format_size</span>
          Appearance
        </h2>
        <div class="space-y-4">
          <div class="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <p class="text-sm font-semibold text-[var(--color-text-primary)] mb-1">Font Size</p>
            <input type="range" v-model="fontSize" min="8" max="24"
              class="w-full accent-[var(--color-brand)]" />
            <p class="text-xs text-[var(--color-text-tertiary)] mt-1">{{ fontSize }}px</p>
          </div>
          <div class="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <p class="text-sm font-semibold text-[var(--color-text-primary)] mb-1">Line Spacing</p>
            <input type="range" v-model="lineSpacing" min="1" max="3" step="0.1"
              class="w-full accent-[var(--color-brand)]" />
            <p class="text-xs text-[var(--color-text-tertiary)] mt-1">{{ lineSpacing }}x</p>
          </div>
          <div class="flex items-center justify-between p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <p class="text-sm font-semibold text-[var(--color-text-primary)]">Show Scrollbar</p>
            <button @click="showScrollbar = !showScrollbar"
              :class="['w-11 h-6 rounded-full transition-colors relative', showScrollbar ? 'bg-[var(--color-brand)]' : 'bg-[var(--color-border)]']">
              <span :class="['absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform', showScrollbar ? 'left-5.5' : 'left-0.5']" />
            </button>
          </div>
        </div>
      </div>
      <!-- Suggestions -->
      <div v-else-if="activeSection === 'suggestions'">
        <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">lightbulb</span>
          Suggestions
        </h2>
        <div class="flex items-center justify-between p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
          <div>
            <p class="text-sm font-semibold text-[var(--color-text-primary)]">Enable Suggestions</p>
            <p class="text-xs text-[var(--color-text-tertiary)]">Show AI-powered command suggestions</p>
          </div>
          <button @click="enableSuggestion = !enableSuggestion"
            :class="['w-11 h-6 rounded-full transition-colors relative', enableSuggestion ? 'bg-[var(--color-brand)]' : 'bg-[var(--color-border)]']">
            <span :class="['absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform', enableSuggestion ? 'left-5.5' : 'left-0.5']" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
