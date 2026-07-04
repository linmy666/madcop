<script setup lang="ts">
// v3.0 — Textarea (Vue 3)
// Direct translation of Textarea.tsx — same Tailwind classes.
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  label?: string
  error?: string
  required?: boolean
  modelValue?: string
  rows?: number
  id?: string
  placeholder?: string
  class?: string
}>(), {
  rows: 5,
})

defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const inputId = computed(() => props.id || (props.label ? props.label.toLowerCase().replace(/\s+/g, '-') : undefined))
</script>

<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" :for="inputId" class="text-sm font-medium text-[var(--color-text-primary)]">
      {{ label }}<span v-if="required" class="text-[var(--color-error)] ml-0.5">*</span>
    </label>
    <textarea
      :id="inputId"
      :value="modelValue"
      :rows="rows"
      :placeholder="placeholder"
      :class="[
        'min-h-[120px] px-3 py-2 rounded-[var(--radius-lg)] border text-sm resize-y bg-[var(--color-surface)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] transition-colors duration-150 outline-none',
        error
          ? 'border-[var(--color-error)]'
          : 'border-[var(--color-border)] focus:border-[var(--color-border-focus)] focus:shadow-[var(--shadow-focus-ring)]',
        $props.class
      ]"
      @input="(e) => $emit('update:modelValue', (e.target as HTMLTextAreaElement).value)"
    />
    <p v-if="error" class="text-xs text-[var(--color-error)]">{{ error }}</p>
  </div>
</template>
