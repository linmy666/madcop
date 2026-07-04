<script setup lang="ts">
// v3.0 — Textarea (Vue 3)
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  label?: string
  error?: string
  required?: boolean
  modelValue?: string
  rows?: number
  id?: string
  placeholder?: string
}>(), {
  rows: 5,
})

defineEmits<{ (e: 'update:modelValue', v: string): void }>()

const inputId = computed(() => props.id || (props.label ? props.label.toLowerCase().replace(/\s+/g, '-') : undefined))
</script>

<template>
  <div class="madcop-textarea">
    <label v-if="label" :for="inputId" class="madcop-textarea__label">
      {{ label }}<span v-if="required" class="madcop-textarea__req">*</span>
    </label>
    <textarea
      :id="inputId"
      :value="modelValue"
      :rows="rows"
      :placeholder="placeholder"
      :class="['madcop-textarea__field', { 'madcop-textarea__field--err': error }]"
      @input="(e) => $emit('update:modelValue', (e.target as HTMLTextAreaElement).value)"
    />
    <p v-if="error" class="madcop-textarea__error">{{ error }}</p>
  </div>
</template>

<style scoped>
.madcop-textarea { display: flex; flex-direction: column; gap: 4px; }
.madcop-textarea__label { font-size: 13px; font-weight: 500; color: var(--madcop-ink); }
.madcop-textarea__req  { color: var(--madcop-danger); margin-left: 2px; }
.madcop-textarea__field {
  min-height: 100px; padding: 8px 12px;
  font-size: 13px; outline: none; resize: vertical;
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-raised);
  color: var(--madcop-ink);
  font-family: 'Geist Mono', monospace;
}
.madcop-textarea__field:focus { border-color: var(--madcop-accent); }
.madcop-textarea__field--err { border-color: var(--madcop-danger); }
.madcop-textarea__error { font-size: 11px; color: var(--madcop-danger); }
</style>
