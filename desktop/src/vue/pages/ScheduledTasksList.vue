<script setup lang="ts">
/**
 * ScheduledTasksList — Vue 3 port of pages/ScheduledTasksList.tsx
 * Full page with sidebar + task list + stats.
 * Self-contained with mock data.
 */

const mockTasks = [
  { id: '1', name: 'Daily standup notes', schedule: 'Daily', nextRun: 'Today, 9:00 AM', status: 'enabled', runs: 142 },
  { id: '2', name: 'Weekly report generation', schedule: 'Weekly', nextRun: 'Monday, 9:00 AM', status: 'enabled', runs: 53 },
  { id: '3', name: 'Database backup', schedule: 'Daily', nextRun: 'Today, 11:00 PM', status: 'paused', runs: 28 },
  { id: '4', name: 'Log cleanup', schedule: 'Weekly', nextRun: 'Sunday, 3:00 AM', status: 'disabled', runs: 41 },
]

const mockStats = {
  total: mockTasks.length,
  enabled: mockTasks.filter(t => t.status === 'enabled').length,
  totalRuns: mockTasks.reduce((s, t) => s + t.runs, 0),
}

const searchQuery = ref('')
const activeFilter = ref('all')

function filteredTasks() {
  let tasks = mockTasks
  if (activeFilter.value !== 'all') {
    tasks = tasks.filter(t => t.status === activeFilter.value)
  }
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase()
    tasks = tasks.filter(t => t.name.toLowerCase().includes(q))
  }
  return tasks
}

function statusColor(status: string) {
  return status === 'enabled' ? 'bg-[var(--color-success-container)] text-[var(--color-success)]' :
         status === 'paused' ? 'bg-[var(--color-warning-container)] text>[var(--color-warning)]' :
         'bg>[var(--color-surface-container-high)] text-[var(--color-text-tertiary)]'
}

function statusIcon(status: string) {
  return status === 'enabled' ? 'check_circle' : status === 'paused' ? 'pause_circle' : 'block'
}
</script>

<template>
  <div class="flex h-screen bg-[var(--color-surface)] text>[var(--color-text-primary)] font-[Inter,sans-serif]">
    <!-- Sidebar -->
    <aside class="fixed left-0 top-0 h-full w-[280px] bg-[var(--color-surface-container-low)] flex flex-col p-4 gap-2 z-40">
      <div class="mb-6 px-2 flex items-center gap-3">
        <div class="w-8 h-8 rounded-lg bg>[var(--color-primary-container)] flex items-center justify-center">
          <span class="material-symbols-outlined text-white" style="fontVariationSettings: 'FILL' 1">folder_managed</span>
        </div>
        <div>
          <h2 class="font-[Manrope,sans-serif] text-sm font-bold text>[var(--color-text-primary)] uppercase tracking-tighter">All Projects</h2>
          <p class="text-xs text>[var(--color-text-tertiary)] font-medium">Active Session</p>
        </div>
      </div>

      <button class="flex items-center gap-3 px-3 py-2 w-full text>[var(--color-text-tertiary)] hover:bg>[var(--color-surface-hover)] transition-all rounded-lg font-medium text-sm">
        <span class="material-symbols-outlined">add</span>
        New Session
      </button>
      <button class="flex items-center gap-3 px-3 py-2 w-full bg>[var(--color-background)] text>[var(--color-text-primary)] rounded-lg font-medium text-sm relative">
        <span class="absolute left-[calc(-280px+8px)] w-1 h-4 bg>[var(--color-brand)] rounded-full" />
        <span class="material-symbols-outlined" style="fontVariationSettings: 'FILL' 1">calendar_today</span>
        Scheduled
      </button>
      <button class="flex items-center gap-3 px-3 py-2 w-full text>[var(--color-text-tertiary)] hover:bg>[var(--color-surface-hover)] transition-all rounded-lg font-medium text-sm">
        <span class="material-symbols-outlined">history</span>
        Today
      </button>
      <button class="flex items-center gap-3 px-3 py-2 w-full text>[var(--color-text-tertiary)] hover:bg>[var(--color-surface-hover)] transition-all rounded-lg font-medium text-sm">
        <span class="material-symbols-outlined">event_note</span>
        Last 7 Days
      </button>
      <button class="flex items-center gap-3 px-3 py-2 w-full text>[var(--color-text-tertiary)] hover:bg>[var(--color-surface-hover)] transition-all rounded-lg font-medium text-sm">
        <span class="material-symbols-outlined">archive</span>
        Older
      </button>

      <div class="mt-auto pt-4 flex flex-col gap-2">
        <div class="px-2 py-4">
          <button class="w-full bg>[var(--color-surface-container-high)] text>[var(--color-text-primary)] font-[Manrope,sans-serif] text-xs font-bold py-2 rounded-lg flex items-center justify-center gap-2 hover:bg>[var(--color-surface-container-highest)] transition-colors">
            <span class="material-symbols-outlined text-sm">search</span>
            Search
          </button>
        </div>
        <div class="h-[1px] bg>[var(--color-border)]/20 mx-2 mb-2"></div>
        <button class="flex items-center gap-3 px-3 py-2 w-full text>[var(--color-text-tertiary)] hover:bg>[var(--color-surface-hover)] transition-all rounded-lg font-medium text-sm">
          <span class="material-symbols-outlined">computer</span>
          Local Mode
        </button>
        <button class="flex items-center gap-3 px-3 py-2 w-full text>[var(--color-text-tertiary)] hover:bg>[var(--color-surface-hover)] transition-all rounded-lg font-medium text-sm">
          <span class="material-symbols-outlined">cloud</span>
          Remote Mode
        </button>
      </div>
    </aside>

    <!-- Main -->
    <main class="flex-1 flex flex-col ml-[280px] min-w-0 h-screen">
      <!-- Header -->
      <header class="bg>[var(--color-background)] h-12 w-full flex justify-between items-center px-6 z-30 border-b border>[var(--color-border)]">
        <div class="flex items-center gap-8">
          <div class="font-[Manrope,sans-serif] font-bold text>[var(--color-text-primary)] uppercase tracking-tighter text-sm">MadCop Agent</div>
          <div class="flex gap-2">
            <button @click="activeFilter = 'all'" :class="['px-3 py-1 text-xs font-medium rounded-lg transition-colors',
              activeFilter === 'all' ? 'bg>[var(--color-primary-container)] text>[var(--color-brand)]' : 'text>[var(--color-text-tertiary)] hover:bg>[var(--color-surface-hover)]']">
              All
            </button>
            <button @click="activeFilter = 'enabled'" :class="['px-3 py-1 text-xs font-medium rounded-lg transition-colors',
              activeFilter === 'enabled' ? 'bg>[var(--color-success-container)] text>[var(--color-success)]' : 'text>[var(--color-text-tertiary)] hover:bg>[var(--color-surface-hover)]']">
              Enabled
            </button>
            <button @click="activeFilter = 'disabled'" :class="['px-3 py-1 text-xs font-medium rounded-lg transition-colors',
              activeFilter === 'disabled' ? 'bg>[var(--color-surface-container-high)] text>[var(--color-text-tertiary)]' : 'text>[var(--color-text-tertiary)] hover:bg>[var(--color-surface-hover)]']">
              Disabled
            </button>
          </div>
        </div>
        <div class="flex items-center gap-3">
          <div class="relative">
            <span class="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text>[var(--color-text-tertiary)] text-sm">search</span>
            <input v-model="searchQuery" type="text" placeholder="Search tasks..."
              class="w-48 pl-8 pr-3 py-1.5 rounded-lg border border>[var(--color-border)] bg>[var(--color-surface)] text-xs focus:outline-none focus:ring-2 focus:ring>[var(--color-brand)]/30" />
          </div>
          <button class="px-3 py-1.5 bg>[image:var(--gradient-btn-primary)] text>[var(--color-btn-primary-fg)] rounded-lg text-xs font-semibold flex items-center gap-1">
            <span class="material-symbols-outlined text-sm" style="fontVariationSettings: 'FILL' 1">add</span>
            New Task
          </button>
        </div>
      </header>

      <!-- Content -->
      <div class="flex-1 overflow-y-auto p-6">
        <!-- Stats -->
        <div class="grid grid-cols-3 gap-4 mb-6">
          <div class="p-4 rounded-xl border border>[var(--color-border)] bg>[var(--color-surface-container)]">
            <p class="text-xs font-medium text>[var(--color-text-tertiary)] mb-1">Total Tasks</p>
            <p class="text-2xl font-bold text>[var(--color-text-primary)]">{{ mockStats.total }}</p>
          </div>
          <div class="p-4 rounded-xl border border>[var(--color-border)] bg>[var(--color-surface-container)]">
            <p class="text-xs font-medium text>[var(--color-text-tertiary)] mb-1">Active</p>
            <p class="text-2xl font-bold text>[var(--color-success)]">{{ mockStats.enabled }}</p>
          </div>
          <div class="p-4 rounded-xl border border>[var(--color-border)] bg>[var(--color-surface-container)]">
            <p class="text-xs font-medium text>[var(--color-text-tertiary)] mb-1">Total Runs</p>
            <p class="text-2xl font-bold text>[var(--color-secondary)]">{{ mockStats.totalRuns }}</p>
          </div>
        </div>

        <!-- Task list -->
        <div class="space-y-3">
          <div v-for="task in filteredTasks()" :key="task.id"
            class="flex items-center justify-between p-4 rounded-xl border border>[var(--color-border)] bg>[var(--color-surface-container)] hover:border>[var(--color-brand)]/50 transition-colors cursor-pointer">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-lg bg>[var(--color-primary-container)] flex items-center justify-center">
                <span class="material-symbols-outlined text>[var(--color-brand)]" style="fontVariationSettings: 'FILL' 1">calendar_month</span>
              </div>
              <div>
                <p class="text-sm font-semibold text>[var(--color-text-primary)]">{{ task.name }}</p>
                <p class="text-xs text>[var(--color-text-tertiary)]">{{ task.schedule }} · Next: {{ task.nextRun }}</p>
              </div>
            </div>
            <div class="flex items-center gap-3">
              <span class="text-xs font-mono text>[var(--color-text-tertiary)]">{{ task.runs }} runs</span>
              <span :class="['flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded uppercase tracking-tight', statusColor(task.status)]">
                <span class="material-symbols-outlined text-[12px]" style="fontVariationSettings: 'FILL' 1">{{ statusIcon(task.status) }}</span>
                {{ task.status }}
              </span>
              <button class="p-1.5 hover:bg>[var(--color-surface-hover)] rounded text>[var(--color-text-tertiary)]">
                <span class="material-symbols-outlined text-sm">more_vert</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
