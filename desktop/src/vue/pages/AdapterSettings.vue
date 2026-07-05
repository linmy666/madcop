<script setup lang="ts">
import { ref } from 'vue'

const apiKey = ref('')
const baseUrl = ref('')
const model = ref('')

const adapters = ref([
  { id: '1', name: 'OpenAI', provider: 'openai', model: 'gpt-4o', enabled: true },
  { id: '2', name: 'Anthropic', provider: 'anthropic', model: 'claude-3.5-sonnet', enabled: true },
  { id: '3', name: 'DeepSeek', provider: 'deepseek', model: 'deepseek-chat', enabled: false },
  { id: '4', name: 'GLM', provider: 'zhipu', model: 'glm-4-plus', enabled: true },
])

const sections = [
  { key: 'list', label: 'Adapters' },
  { key: 'add', label: 'Add' },
]
const activeSection = ref('list')

function toggleAdapter(id: string) {
  const a = adapters.value.find(a => a.id === id)
  if (a) a.enabled = !a.enabled
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
      <!-- Adapter list -->
      <div v-if="activeSection === 'list'" class="space-y-4">
        <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">api</span>
          Model Adapters
        </h2>
        <div v-for="a in adapters" :key="a.id"
          class="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)] flex items-center justify-between">
          <div class="flex items-center gap-3">
            <div :class="['w-10 h-10 rounded-lg flex items-center justify-center',
              a.enabled ? 'bg-[var(--color-primary-container)] text-[var(--color-brand)]' : 'bg-[var(--color-surface-container-high)] text-[var(--color-text-tertiary)]']">
              <span class="material-symbols-outlined text-lg">{{ a.provider === 'openai' ? 'chat' : a.provider === 'anthropic' ? 'psychology' : 'code' }}</span>
            </div>
            <div>
              <p class="text-sm font-semibold text-[var(--color-text-primary)]">{{ a.name }}</p>
              <p class="text-xs text-[var(--color-text-tertiary)]">{{ a.provider }} · {{ a.model }}</p>
            </div>
          </div>
          <button @click="toggleAdapter(a.id)"
            :class="['w-11 h-6 rounded-full transition-colors relative', a.enabled ? 'bg-[var(--color-brand)]' : 'bg-[var(--color-border)]']">
            <span :class="['absolute top-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform', a.enabled ? 'left-5.5' : 'left-0.5']" />
          </button>
        </div>
      </div>
      <!-- Add adapter -->
      <div v-else class="space-y-4">
        <h2 class="text-base font-bold text-[var(--color-text-primary)] mb-4 flex items-center gap-2">
          <span class="material-symbols-outlined text-[var(--color-brand)]">add_circle</span>
          Add Adapter
        </h2>
        <div class="space-y-4">
          <div>
            <label class="text-xs font-semibold text-[var(--color-text-tertiary)] mb-1 block">API Key</label>
            <input v-model="apiKey" type="password"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30" />
          </div>
          <div>
            <label class="text-xs font-semibold text-[var(--color-text-tertiary)] mb-1 block">Base URL</label>
            <input v-model="baseUrl" type="text" placeholder="https://api.openai.com/v1"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30" />
          </div>
          <div>
            <label class="text-xs font-semibold text-[var(--color-text-tertiary)] mb-1 block">Default Model</label>
            <input v-model="model" type="text" placeholder="gpt-4o"
              class="w-full px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30" />
          </div>
          <button class="w-full px-4 py-2 bg-[image:var(--gradient-btn-primary)] text-[var(--color-btn-primary-fg)] rounded-lg text-sm font-semibold">
            Save Adapter
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
