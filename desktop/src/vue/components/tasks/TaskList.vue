<script setup lang="ts">
// v3.0 — TaskList (Vue 3)
// Direct translation — same Tailwind classes, same stat cards.
import { ref, computed } from 'vue'

interface CronTask {
  id: string
  name: string
  cron: string
  prompt: string
  enabled: boolean
  modelId?: string
}

const props = defineProps<{ tasks: CronTask[] }>()
const expandedLogsId = ref<string | null>(null)

const enabledCount = computed(() => props.tasks.filter((t) => t.enabled).length)
const disabledCount = computed(() => props.tasks.length - enabledCount.value)
</script>

<template>
  <div>
    <div class="grid grid-cols-3 gap-4 mb-6">
      <div class="px-4 py-3 rounded-[var(--radius-lg)] bg-[var(--color-surface-info)]">
        <div class="text-2xl font-bold text-[var(--color-text-primary)]">{{ tasks.length }}</div>
        <div class="text-xs text-[var(--color-text-secondary)]">总任务数</div>
      </div>
      <div class="px-4 py-3 rounded-[var(--radius-lg)] bg-[var(--color-surface-info)]">
        <div class="text-2xl font-bold text-[var(--color-success)]">{{ enabledCount }}</div>
        <div class="text-xs text-[var(--color-text-secondary)]">已启用</div>
      </div>
      <div class="px-4 py-3 rounded-[var(--radius-lg)] bg-[var(--color-surface-info)]">
        <div class="text-2xl font-bold text-[var(--color-text-tertiary)]">{{ disabledCount }}</div>
        <div class="text-xs text-[var(--color-text-secondary)]">已禁用</div>
      </div>
    </div>
    <div class="flex flex-col">
      <slot :tasks="tasks" :expanded-id="expandedLogsId" :toggle="(id: string) => expandedLogsId = expandedLogsId === id ? null : id" />
    </div>
  </div>
</template>
