<script setup lang="ts">
// v3.0 — DayOfWeekPicker (Vue 3)
// Direct translation — same Tailwind classes, same toggle logic.
const props = defineProps<{
  selected: number[]
}>()

const emit = defineEmits<{ (e: 'change', days: number[]): void }>()

const DAY_ORDER = [1, 2, 3, 4, 5, 6, 0]
const DAY_LABELS = ['日', '一', '二', '三', '四', '五', '六']

function toggle(day: number) {
  if (props.selected.includes(day)) {
    if (props.selected.length <= 1) return
    emit('change', props.selected.filter((d) => d !== day))
  } else {
    emit('change', [...props.selected, day])
  }
}
</script>

<template>
  <div class="flex gap-1.5">
    <button
      v-for="day in DAY_ORDER" :key="day"
      type="button"
      @click="toggle(day)"
      :class="[
        'w-8 h-8 rounded-full text-xs font-medium transition-colors',
        selected.includes(day)
          ? 'bg-[var(--color-surface-selected)] text-[var(--color-text-primary)] border border-[var(--color-border-focus)]'
          : 'bg-[var(--color-surface)] text-[var(--color-text-tertiary)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]',
      ]"
    >
      {{ DAY_LABELS[day] }}
    </button>
  </div>
</template>
