<script setup lang="ts">
import { ref } from 'vue'

const enabled = ref(true)
const screenshotQuality = ref(80)
const autoScreenshot = ref(true)

const sections = [
  { key: 'general', label: 'General' },
  { key: 'permissions', label: 'Permissions' },
  { key: 'screenshots', label: 'Screenshots' },
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
      <div v-if="activeSection === 'general'">
        <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">computer</span>
          Computer Use
        </h2>
        <div class="flex items-center justify-between p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
          <div>
            <p class="text-sm font-semibold text-[var(--color-text-primary)]">Enable Computer Use</p>
            <p class="text-xs text-[var(--color-text-tertiary)]">Allow the agent to control your computer</p>
          </div>
          <button @click="enabled = !enabled"
            :class="['w-11 h-6 rounded-full transition-colors relative', enabled ? 'bg-[var(--color-brand)]' : 'bg-[var(--color-border)]']">
            <span :class="['absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform', enabled ? 'left-5.5' : 'left-0.5']" />
          </button>
        </div>
      </div>
      <div v-else-if="activeSection === 'permissions'">
        <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">lock</span>
          Permissions
        </h2>
        <div class="space-y-3">
          <div class="flex items-center justify-between p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <p class="text-xs font-medium text-[var(--color-text-primary)]">Mouse Control</p>
            <span class="text-[10px] text-[var(--color-success)] font-bold">Allowed</span>
          </div>
          <div class="flex items-center justify-between p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <p class="text-xs font-medium text-[var(--color-text-primary)]">Keyboard Input</p>
            <span class="text-[10px] text-[var(--color-success)] font-bold">Allowed</span>
          </div>
          <div class="flex items-center justify-between p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <p class="text-xs font-medium text-[var(--color-text-primary)]">Window Management</p>
            <span class="text-[10px] text-[var(--color-warning)] font-bold">Prompt</span>
          </div>
          <div class="flex items-center justify-between p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <p class="text-xs font-medium text-[var(--color-text-primary)]">File Operations</p>
            <span class="text-[10px] text-[var(--color-warning)] font-bold">Prompt</span>
          </div>
        </div>
      </div>
      <div v-else-if="activeSection === 'screenshots'">
        <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">screenshot_monitor</span>
          Screenshots
        </h2>
        <div class="space-y-4">
          <div class="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <p class="text-sm font-semibold text-[var(--color-text-primary)] mb-1">Screenshot Quality</p>
            <input type="range" v-model="screenshotQuality" min="10" max="100"
              class="w-full accent-[var(--color-brand)]" />
            <p class="text-xs text-[var(--color-text-tertiary)] mt-1">{{ screenshotQuality }}%</p>
          </div>
          <div class="flex items-center justify-between p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <p class="text-sm font-semibold text-[var(--color-text-primary)]">Auto-screenshot</p>
            <button @click="autoScreenshot = !autoScreenshot"
              :class="['w-11 h-6 rounded-full transition-colors relative', autoScreenshot ? 'bg-[var(--color-brand)]' : 'bg>[var(--color-border)]']">
              <span :class="['absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform', autoScreenshot ? 'left-5.5' : 'left-0.5']" />
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
