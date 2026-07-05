<script setup lang="ts">
// v3.0 — Input (Vue 3)
// Direct translation of Input.tsx — same Tailwind classes.
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  label?: string
  error?: string
  required?: boolean
  modelValue?: string | number
  type?: string
  id?: string
  placeholder?: string
  disabled?: boolean
  readOnly?: boolean
  inputMode?: string
  class?: string
}>(), {
  type: 'text',
})

defineEmits<{ (e: 'update:modelValue', v: string | number): void }>()

const inputId = computed(() => props.id || (props.label ? props.label.toLowerCase().replace(/\s+/g, '-') : undefined))
</script>

<template>
  <div class="flex flex-col gap-1">
    <label v-if="label" :for="inputId" class="text-sm font-medium text-[var(--color-text-primary)]">
      {{ label }}
      <span v-if="required" class="text-[var(--color-error)] ml-0.5">*</span>
    </label>
    <input
      :id="inputId"
      :value="modelValue"
      :type="type"
      :placeholder="placeholder"
      :disabled="disabled"
      :readonly="readOnly"
      :inputmode="inputMode"
      :class="[
        'h-10 px-3 rounded-[var(--radius-md)] border text-sm bg-[var(--color-surface)] text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] transition-colors duration-150 outline-none',
        error
          ? 'border-[var(--color-error)] focus:shadow-[var(--shadow-error-ring)]'
          : 'border-[var(--color-border)] focus:border-[var(--color-border-focus)] focus:shadow-[var(--shadow-focus-ring)]',
        $props.class
      ]"
      @input="(e) => $emit('update:modelValue', (e.target as HTMLInputElement).value)"
    />
    <p v-if="error" class="text-xs text-[var(--color-error)]">{{ error }}</p>
  </div>
</template>
