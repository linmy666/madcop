<script setup lang="ts">
import { ref } from 'vue'

const memories = ref([
  { id: '1', content: 'Prefers concise responses', tag: 'user', lastUpdated: '2026-07-01' },
  { id: '2', content: 'Use TypeScript strict mode', tag: 'project', lastUpdated: '2026-07-02' },
  { id: '3', content: 'Python package uses pytest with xdist', tag: 'project', lastUpdated: '2026-07-03' },
  { id: '4', content: 'Build with vite --config vite.vue.config.ts', tag: 'build', lastUpdated: '2026-07-04' },
  { id: '5', content: 'Avoid using React stores in Vue components', tag: 'rule', lastUpdated: '2026-07-04' },
])

const newContent = ref('')
const newTag = ref('user')
const filter = ref('all')

function addMemory() {
  if (!newContent.value.trim()) return
  memories.value.push({
    id: String(Date.now()),
    content: newContent.value.trim(),
    tag: newTag.value,
    lastUpdated: new Date().toISOString().split('T')[0],
  })
  newContent.value = ''
}

function deleteMemory(id: string) {
  memories.value = memories.value.filter(m => m.id !== id)
}

function filtered() {
  if (filter.value === 'all') return memories.value
  return memories.value.filter(m => m.tag === filter.value)
}

function tagColor(tag: string) {
  return tag === 'user' ? 'bg-[var(--color-primary-container)] text-[var(--color-brand)]' :
         tag === 'project' ? 'bg-[var(--color-secondary-container)] text-[var(--color-secondary)]' :
         tag === 'build' ? 'bg-[var(--color-tertiary-container)] text-[var(--color-tertiary)]' :
         'bg-[var(--color-surface-container-high)] text-[var(--color-text-tertiary)]'
}
</script>

<template>
  <div class="h-full flex flex-col bg-[var(--color-surface)]">
    <div class="flex items-center gap-3 px-6 py-4 border-b border-[var(--color-border)]">
      <span class="material-symbols-outlined text-[var(--color-brand)]">memory</span>
      <h1 class="text-lg font-bold text-[var(--color-text-primary)]" style="font-family: var(--font-headline)">Memory</h1>
    </div>
    <div class="flex-1 overflow-y-auto p-6 space-y-4">
      <!-- Add new -->
      <div class="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container)]">
        <div class="flex gap-2 mb-2">
          <input v-model="newContent" type="text" placeholder="Add a new memory entry..."
            class="flex-1 px-3 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--color-brand)]/30"
            @keyup.enter="addMemory" />
          <select v-model="newTag"
            class="px-2 py-2 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] text-xs focus:outline-none">
            <option value="user">User</option>
            <option value="project">Project</option>
            <option value="build">Build</option>
            <option value="rule">Rule</option>
          </select>
          <button @click="addMemory"
            class="px-4 py-2 bg-[image:var(--gradient-btn-primary)] text-[var(--color-btn-primary-fg)] rounded-lg text-xs font-semibold">
            Add
          </button>
        </div>
      </div>
      <!-- Filter tabs -->
      <div class="flex gap-2">
        <button v-for="tag in ['all', 'user', 'project', 'build', 'rule']" :key="tag"
          @click="filter = tag"
          :class="['px-3 py-1 text-xs font-semibold rounded-lg border transition-colors',
            filter === tag ? 'border-[var(--color-brand)] bg-[var(--color-primary-container)] text-[var(--color-brand)]' :
            'border-[var(--color-border)] text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]']">
          {{ tag }}
        </button>
      </div>
      <!-- Memory list -->
      <div class="space-y-2">
        <div v-for="m in filtered()" :key="m.id"
          class="flex items-start justify-between gap-3 p-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container)]">
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 mb-1">
              <span :class="['text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-tight', tagColor(m.tag)]">{{ m.tag }}</span>
              <span class="text-[10px] text-[var(--color-text-tertiary)]">{{ m.lastUpdated }}</span>
            </div>
            <p class="text-xs text-[var(--color-text-primary)]">{{ m.content }}</p>
          </div>
          <button @click="deleteMemory(m.id)"
            class="p-1 hover:bg-[var(--color-surface-hover)] rounded text-[var(--color-text-tertiary)] hover:text-[var(--color-error)]">
            <span class="material-symbols-outlined text-sm">delete</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
