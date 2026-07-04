<script setup lang="ts">
// v3.0 — TeamStatusBar (Vue 3)
// Direct translation — same Tailwind classes, same member status icons.
import { ref, computed } from 'vue'

interface TeamMember {
  agentId: string
  agentName: string
  status: 'running' | 'idle' | 'completed' | 'error'
  sessionId?: string
}

const props = defineProps<{
  members?: TeamMember[]
  leadAgentId?: string
}>()

const emit = defineEmits<{ (e: 'openMember', agentId: string): void }>()
const expanded = ref(true)

const filteredMembers = computed(() =>
  (props.members || []).filter((m) => !props.leadAgentId || m.agentId !== props.leadAgentId)
)
const runningCount = computed(() => filteredMembers.value.filter((m) => m.status === 'running').length)
const completedCount = computed(() => filteredMembers.value.filter((m) => m.status === 'completed').length)
const totalCount = computed(() => filteredMembers.value.length)
const progressPercent = computed(() => totalCount.value > 0 ? Math.round((completedCount.value / totalCount.value) * 100) : 0)

const statusConfig: Record<string, { icon: string; color: string; pulse: boolean }> = {
  running:   { icon: 'pending',                color: 'var(--color-warning)',     pulse: true },
  idle:      { icon: 'radio_button_unchecked', color: 'var(--color-text-tertiary)', pulse: false },
  completed: { icon: 'check_circle',           color: 'var(--color-success)',     pulse: false },
  error:     { icon: 'error',                  color: 'var(--color-error)',       pulse: false },
}
</script>

<template>
  <div v-if="filteredMembers.length > 0" class="shrink-0 px-8">
    <div class="mx-auto max-w-[860px] rounded-[var(--radius-lg)] border border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container-lowest)] overflow-hidden mb-2">
      <button
        @click="expanded = !expanded"
        class="flex w-full items-center gap-3 px-4 py-2.5 text-left"
      >
        <span class="material-symbols-outlined text-[16px] text-[var(--color-text-tertiary)] transition-transform" :style="{ transform: expanded ? 'rotate(90deg)' : '' }">chevron_right</span>
        <span class="text-sm font-semibold text-[var(--color-text-primary)]">团队状态</span>
        <span class="text-xs text-[var(--color-text-tertiary)]">{{ completedCount }}/{{ totalCount }} 完成 · {{ runningCount }} 运行中</span>
        <div class="flex-1" />
        <div class="h-1.5 w-24 rounded-full bg-[var(--color-surface-container-high)] overflow-hidden">
          <div class="h-full rounded-full bg-[var(--color-success)] transition-all duration-300" :style="{ width: progressPercent + '%' }" />
        </div>
      </button>

      <Transition name="team-expand">
        <div v-if="expanded" class="border-t border-[var(--color-border-separator)]">
          <div
            v-for="member in filteredMembers" :key="member.agentId"
            @click="emit('openMember', member.agentId)"
            class="flex items-center gap-3 px-4 py-2 cursor-pointer hover:bg-[var(--color-surface-hover)] transition-colors"
          >
            <span
              class="material-symbols-outlined text-[16px]"
              :style="{ color: statusConfig[member.status]?.color }"
              :class="{ 'animate-pulse': statusConfig[member.status]?.pulse }"
            >{{ statusConfig[member.status]?.icon }}</span>
            <span class="flex-1 min-w-0 truncate text-sm text-[var(--color-text-primary)]">{{ member.agentName }}</span>
            <span class="text-xs text-[var(--color-text-tertiary)] capitalize">{{ member.status }}</span>
          </div>
        </div>
      </Transition>
    </div>
  </div>
</template>

<style>
.team-expand-enter-active, .team-expand-leave-active { transition: all 200ms; overflow: hidden; }
.team-expand-enter-from, .team-expand-leave-to { opacity: 0; max-height: 0; }
</style>
