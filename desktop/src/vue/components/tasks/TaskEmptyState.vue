<script setup lang="ts">
// v3.0 — TaskEmptyState (Vue 3)
// Direct translation — same Tailwind classes, same SVG clock icon.
import Button from '../shared/Button.vue'

const emit = defineEmits<{ (e: 'create'): void }>()
</script>

<template>
  <div class="flex flex-col items-center justify-center py-20">
    <div class="w-16 h-16 rounded-full bg-[var(--color-surface-info)] flex items-center justify-center mb-4">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="var(--color-text-tertiary)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 16 14" />
      </svg>
    </div>
    <h3 class="text-sm font-medium text-[var(--color-text-primary)] mb-1">
      <slot name="title">暂无计划任务</slot>
    </h3>
    <p class="text-sm text-[var(--color-text-tertiary)] mb-4 text-center max-w-sm">
      <slot name="desc">在聊天中输入 /schedule 创建定时任务</slot>
    </p>
    <Button @click="emit('create')">
      <slot>新建任务</slot>
    </Button>
  </div>
</template>
