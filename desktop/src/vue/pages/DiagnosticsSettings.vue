<script setup lang="ts">
import { ref } from 'vue'

const diagnostics = ref([
  { key: 'os', label: 'OS', value: 'macOS 26.5.1', status: 'ok' },
  { key: 'node', label: 'Node.js', value: 'v20.18.0', status: 'ok' },
  { key: 'cpu', label: 'CPU', value: 'Apple M4', status: 'ok' },
  { key: 'memory', label: 'Memory', value: '16 GB', status: 'ok' },
  { key: 'gpu', label: 'GPU', value: 'Apple M4 GPU', status: 'ok' },
  { key: 'storage', label: 'Storage', value: '512 GB SSD', status: 'ok' },
  { key: 'network', label: 'Network', value: 'Connected', status: 'ok' },
  { key: 'api', label: 'API', value: 'Online', status: 'ok' },
])

function statusIcon(status: string) {
  return status === 'ok' ? 'check_circle' : status === 'warn' ? 'warning' : 'error'
}
function statusColor(status: string) {
  return status === 'ok' ? 'text-[var(--color-success)]' : status === 'warn' ? 'text-[var(--color-warning)]' : 'text-[var(--color-error)]'
}
</script>

<template>
  <div class="h-full flex flex-col bg-[var(--color-surface)]">
    <div class="flex items-center gap-3 px-6 py-4 border-b border-[var(--color-border)]">
      <span class="material-symbols-outlined text-[var(--color-brand)]">biotech</span>
      <h1 class="text-lg font-bold text-[var(--color-text-primary)]" style="font-family: var(--font-headline)">Diagnostics</h1>
    </div>
    <div class="flex-1 overflow-y-auto p-6">
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div v-for="d in diagnostics" :key="d.key"
          class="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)] flex items-center justify-between">
          <div class="flex items-center gap-2">
            <span :class="['material-symbols-outlined text-sm', statusColor(d.status)]" style="fontVariationSettings: 'FILL' 1">{{ statusIcon(d.status) }}</span>
            <span class="text-xs font-semibold text-[var(--color-text-tertiary)]">{{ d.label }}</span>
          </div>
          <span class="text-xs font-medium text-[var(--color-text-primary)]">{{ d.value }}</span>
        </div>
      </div>
      <div class="mt-6 p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] font-mono text-[11px] text-[var(--color-text-secondary)] overflow-x-auto">
        <p>Session: 2026-07-05T14:00:00Z</p>
        <p>Version: madcop v2.8.0-rc1</p>
        <p>Build: vue3-migration</p>
        <p>Status: All systems operational</p>
      </div>
    </div>
  </div>
</template>
