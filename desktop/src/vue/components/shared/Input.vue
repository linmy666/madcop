<script setup lang="ts">
// v3.0 — Input (Vue 3)
import { computed, useAttrs } from 'vue'

const props = withDefaults(defineProps<{
  label?: string
  error?: string
  required?: boolean
  modelValue?: string | number
  type?: string
  id?: string
  placeholder?: string
  disabled?: boolean
}>(), {
  type: 'text',
})

defineEmits<{ (e: 'update:modelValue', v: string | number): void }>()

const inputId = computed(() => props.id || (props.label ? props.label.toLowerCase().replace(/\s+/g, '-') : undefined))
</script>

<template>
  <div class="madcop-input">
    <label v-if="label" :for="inputId" class="madcop-input__label">
      {{ label }}
      <span v-if="required" class="madcop-input__req">*</span>
    </label>
    <input
      :id="inputId"
      :value="modelValue"
      :type="type"
      :placeholder="placeholder"
      :disabled="disabled"
      :class="['madcop-input__field', { 'madcop-input__field--err': error }]"
      @input="(e) => $emit('update:modelValue', (e.target as HTMLInputElement).value)"
    />
    <p v-if="error" class="madcop-input__error">{{ error }}</p>
  </div>
</template>

<style scoped>
.madcop-input { display: flex; flex-direction: column; gap: 4px; }
.madcop-input__label { font-size: 13px; font-weight: 500; color: var(--madcop-ink); }
.madcop-input__req { color: var(--madcop-danger); margin-left: 2px; }
.madcop-input__field {
  height: 36px; padding: 0 12px;
  font-size: 13px; outline: none;
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-raised);
  color: var(--madcop-ink);
  font-family: 'Geist Mono', monospace;
  transition: border-color 140ms;
}
.madcop-input__field:focus { border-color: var(--madcop-accent); }
.madcop-input__field--err { border-color: var(--madcop-danger); }
.madcop-input__error { font-size: 11px; color: var(--madcop-danger); }
</style>
