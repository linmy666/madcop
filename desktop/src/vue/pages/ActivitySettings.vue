<script setup lang="ts">
import { ref } from 'vue'

const enabled = ref(true)
const maxRetentionDays = ref(30)
const autoStart = ref(false)

const sections = [
  { key: 'activity', label: 'Activity' },
  { key: 'notifications', label: 'Notifications' },
  { key: 'retention', label: 'Retention' },
]
const activeSection = ref('activity')
</script>

<template>
  <div class="h-full flex flex-col bg-[var(--color-surface)]">
    <!-- Sidebar nav -->
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
      <!-- Activity section -->
      <div v-if="activeSection === 'activity'">
        <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">activity</span>
          Activity Settings
        </h2>
        <div class="space-y-4">
          <div class="flex items-center justify-between p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <div>
              <p class="text-sm font-semibold text-[var(--color-text-primary)]">Enable Activity Tracking</p>
              <p class="text-xs text-[var(--color-text-tertiary)]">Record agent activity for trace analysis</p>
            </div>
            <button @click="enabled = !enabled"
              :class="['w-11 h-6 rounded-full transition-colors relative', enabled ? 'bg-[var(--color-brand)]' : 'bg-[var(--color-border)]']">
              <span :class="['absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform', enabled ? 'left-5.5' : 'left-0.5']" />
            </button>
          </div>
          <div class="flex items-center justify-between p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <div>
              <p class="text-sm font-semibold text-[var(--color-text-primary)]">Auto-start on Launch</p>
              <p class="text-xs text-[var(--color-text-tertiary)]">Begin tracking immediately when app opens</p>
            </div>
            <button @click="autoStart = !autoStart"
              :class="['w-11 h-6 rounded-full transition-colors relative', autoStart ? 'bg-[var(--color-brand)]' : 'bg-[var(--color-border)]']">
              <span :class="['absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform', autoStart ? 'left-5.5' : 'left-0.5']" />
            </button>
          </div>
        </div>
      </div>
      <!-- Notifications section -->
      <div v-else-if="activeSection === 'notifications'">
        <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">notifications</span>
          Notifications
        </h2>
        <div class="space-y-4">
          <div class="flex items-center justify-between p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
            <div>
              <p class="text-sm font-semibold text-[var(--color-text-primary)]">Task Completion Alerts</p>
              <p class="text-xs text-[var(--color-text-tertiary)]">Show a toast when a task finishes</p>
            </div>
            <button @click="enabled = !enabled"
              :class="['w-11 h-6 rounded-full transition-colors relative', enabled ? 'bg-[var(--color-brand)]' : 'bg-[var(--color-border)]']">
              <span :class="['absolute top-0.5 w-5 h-5 rounded-full bg white shadow transition-transform', enabled ? 'left-5.5' : 'left-0.5']" />
            </button>
          </div>
        </div>
      </div>
      <!-- Retention section -->
      <div v-else-if="activeSection === 'retention'">
        <h2 class="text-base font bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">archive</span>
          Data Retention
        </h2>
        <div class="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
          <p class="text-sm font-semibold text-[var(--color-text-primary)]">Retention Period</p>
          <p class="text-xs text-[var(--color-text-tertiary)] mb-3">Keep activity data for this many days</p>
          <input type="range" v-model="maxRetentionDays" min="1" max="365"
            class="w-full accent-[var(--color-brand)]" />
          <p class="text-xs text-[var(--color-text-tertiary)] mt-1">{{ maxRetentionDays }} days</p>
        </div>
      </div>
    </div>
  </div>
</template>
