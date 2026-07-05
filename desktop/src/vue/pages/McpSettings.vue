<script setup lang="ts">
import { ref } from 'vue'

const mcpServers = ref([
  { id: '1', name: 'Filesystem', command: 'npx', args: ['@modelcontextprotocol/server-filesystem', '/Users'], enabled: true },
  { id: '2', name: 'GitHub', command: 'npx', args: ['@modelcontextprotocol/server-github'], enabled: true },
  { id: '3', name: 'PostgreSQL', command: 'npx', args: ['@modelcontextprotocol/server-postgres', 'postgresql://localhost/db'], enabled: false },
])

const sections = [
  { key: 'list', label: 'Servers' },
  { key: 'add', label: 'Add' },
]
const activeSection = ref('list')

function toggleMcp(id: string) {
  const m = mcpServers.value.find(m => m.id === id)
  if (m) m.enabled = !m.enabled
}
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
    <div class="flex-1 overflow-y-auto p-6">
      <div v-if="activeSection === 'list'" class="space-y-4">
        <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">dns</span>
          MCP Servers
        </h2>
        <div v-for="m in mcpServers" :key="m.id"
          class="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
          <div class="flex items-center justify-between mb-2">
            <div class="flex items-center gap-2">
              <span class="material-symbols-outlined text-[var(--color-secondary)] text-sm">dns</span>
              <p class="text-sm font-semibold text-[var(--color-text-primary)]">{{ m.name }}</p>
              <span :class="['text-[9px] font-bold px-1.5 py-0.5 rounded uppercase',
                m.enabled ? 'bg-[var(--color-success-container)] text-[var(--color-success)]' : 'bg-[var(--color-surface-container-high)] text-[var(--color-text-tertiary)]']">
                {{ m.enabled ? 'ON' : 'OFF' }}
              </span>
            </div>
            <button @click="toggleMcp(m.id)"
              :class="['w-11 h-6 rounded-full transition-colors relative', m.enabled ? 'bg-[var(--color-brand)]' : 'bg-[var(--color-border)]']">
              <span :class="['absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform', m.enabled ? 'left-5.5' : 'left-0.5']" />
            </button>
          </div>
          <div class="flex gap-1 text-xs font-mono text-[var(--color-text-tertiary)]">
            <span>{{ m.command }}</span>
            <span v-for="arg in m.args" :key="arg">{{ arg }}</span>
          </div>
        </div>
      </div>
      <div v-else class="space-y-4">
        <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">add_circle</span>
          Add MCP Server
        </h2>
        <div class="space-y-4">
          <div>
            <label class="text-xs font-semibold text-[var(--color-text-tertiary)] mb-1 block">Name</label>
            <input type="text" placeholder="My Server"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30" />
          </div>
          <div>
            <label class="text-xs font-semibold text-[var(--color-text-tertiary)] mb-1 block">Command</label>
            <input type="text" placeholder="npx"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30" />
          </div>
          <div>
            <label class="text-xs font-semibold text-[var(--color-text-tertiary)] mb-1 block">Arguments</label>
            <input type="text" placeholder="server-name arg1 arg2"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30" />
          </div>
          <button class="w-full px-4 py-2 bg-[image:var(--gradient-btn-primary)] text-[var(--color-btn-primary-fg)] rounded-lg text-sm font-semibold">
            Save Server
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
