<script setup lang="ts">
/**
 * LocalSlashCommandPanel — Vue 3 port of chat/LocalSlashCommandPanel.tsx
 * Simplified: slash command selector panel with common commands.
 * Shows when user types "/" in the composer.
 */

interface SlashCommand {
  name: string
  description: string
  argumentHint?: string
  icon?: string
  category?: string
}

interface Props {
  /** Filter text (after /) */
  filter: string
  /** Current slash command name (mcp | skills | help | status | cost | context) */
  currentCommand?: string
  /** Called when a command is selected */
  onSelect: (command: string, args?: string) => void
  /** Called when the panel is dismissed */
  onDismiss: () => void
}

const props = defineProps<Props>()

const selectedIndex = ref(0)

const ALL_COMMANDS: SlashCommand[] = [
  { name: '/new', description: 'Start a new chat session', icon: 'add_comment', category: 'session' },
  { name: '/stop', description: 'Stop the current generation', icon: 'stop_circle', category: 'session' },
  { name: '/settings', description: 'Open settings', icon: 'settings', category: 'app' },
  { name: '/compact', description: 'Compact the session history', icon: 'compress', category: 'session' },
  { name: '/help', description: 'Show available commands', icon: 'help', category: 'info' },
  { name: '/status', description: 'Show session status', icon: 'info', category: 'info' },
  { name: '/mcp', description: 'Manage MCP servers', icon: 'dns', category: 'tools' },
  { name: '/skills', description: 'List available skills', icon: 'extension', category: 'tools' },
  { name: '/context', description: 'Show context usage', icon: 'memory', category: 'info' },
]

const filtered = computed(() => {
  if (!props.filter) return ALL_COMMANDS
  const q = props.filter.toLowerCase()
  return ALL_COMMANDS.filter(c =>
    c.name.toLowerCase().includes(q) ||
    c.description.toLowerCase().includes(q)
  )
})

function selectCommand(cmd: SlashCommand) {
  props.onSelect(cmd.name)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    selectedIndex.value = Math.min(selectedIndex.value + 1, filtered.value.length - 1)
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    selectedIndex.value = Math.max(selectedIndex.value - 1, 0)
  } else if (e.key === 'Enter' && filtered.value[selectedIndex.value]) {
    selectCommand(filtered.value[selectedIndex.value])
  } else if (e.key === 'Escape') {
    props.onDismiss()
  }
}
</script>

<template>
  <div
    class="absolute left-0 right-0 bottom-full mb-2 bg>[var(--color-surface-container-lowest)] border border>[var(--color-border)] rounded-xl shadow-[var(--shadow-dropdown)] max-h-[300px] overflow-y-auto z-50"
    @keydown="onKeydown"
  >
    <div v-if="currentCommand" class="px-3 py-2 border-b border>[var(--color-border)] text-[10px] font-bold uppercase tracking-wider text>[var(--color-outline)]">
      {{ currentCommand }}
    </div>
    <div class="py-1">
      <div v-if="filtered.length === 0" class="px-4 py-3 text-xs text>[var(--color-text-tertiary)]">No commands found</div>
      <button v-for="(cmd, idx) in filtered" :key="cmd.name"
        @click="selectCommand(cmd)"
        :class="['flex w-full items-center gap-3 px-3 py-2 text-left transition-colors',
          idx === selectedIndex ? 'bg>[var(--color-surface-hover)]' : 'hover:bg>[var(--color-surface-hover)]']">
        <span class="material-symbols-outlined text-[16px] text>[var(--color-text-tertiary)]">{{ cmd.icon || 'terminal' }}</span>
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2">
            <span class="text-sm font-mono font-semibold text>[var(--color-text-primary)]">{{ cmd.name }}</span>
            <span v-if="cmd.category" class="text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-tight bg>[var(--color-surface-container-high)] text>[var(--color-text-tertiary)]">{{ cmd.category }}</span>
          </div>
          <span class="text-xs text>[var(--color-text-tertiary)]">{{ cmd.description }}</span>
        </div>
      </button>
    </div>
  </div>
</template>
