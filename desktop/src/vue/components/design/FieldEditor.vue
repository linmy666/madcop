<!--
  FieldEditor — sub-component of DesignCanvas.
  Renders configurable field editors (text, textarea, number, select, radio, color).
-->
<script setup lang="ts">
import { computed, type PropType } from 'vue'

export interface FieldConfig {
  type: 'text' | 'textarea' | 'number' | 'select' | 'radio' | 'color'
  label: string
  options?: { label: string; value: string }[]
}

const props = defineProps<{
  field: FieldConfig
  value: any
}>()

const emit = defineEmits<{
  (e: 'change', v: any): void
}>()

const inputStyle = computed<Record<string, any>>(() => ({
  width: '100%',
  padding: '6px 10px',
  border: '1px solid #D1D5DB',
  borderRadius: 4,
  fontSize: 13,
  background: '#fff',
  boxSizing: 'border-box',
}))

const displayValue = computed(() => props.value ?? '')
const numValue = computed(() => props.value ?? 0)

function handleChange(v: any) {
  emit('change', v)
}
</script>

<template>
  <component
    :is="field.type === 'textarea' ? 'textarea' : field.type === 'color' ? 'div' : 'input'"
    v-if="field.type !== 'radio' && field.type !== 'color'"
    :type="field.type === 'number' ? 'number' : field.type === 'select' ? undefined : field.type"
    :value="field.type === 'number' ? numValue : displayValue"
    :rows="field.type === 'textarea' ? 3 : undefined"
    :placeholder="field.type === 'text' && !displayValue ? '输入...' : undefined"
    @input="handleChange(($event.target as HTMLInputElement).value)"
    :style="field.type === 'textarea' ? { ...inputStyle, resize: 'vertical' } : inputStyle"
  />

  <select
    v-else-if="field.type === 'select'"
    :value="displayValue"
    @input="handleChange(($event.target as HTMLSelectElement).value)"
    :style="inputStyle"
  >
    <option
      v-for="o in field.options || []"
      :key="o.value"
      :value="o.value"
    >
      {{ o.label }}
    </option>
  </select>

  <div
    v-else-if="field.type === 'radio'"
    :style="{ display: 'flex', gap: 12 }"
  >
    <label
      v-for="o in field.options || []"
      :key="o.value"
      :style="{
        display: 'flex',
        alignItems: 'center',
        gap: 4,
        fontSize: 13,
        cursor: 'pointer',
      }"
    >
      <input
        type="radio"
        :checked="value === o.value"
        @change="handleChange(o.value)"
      />
      {{ o.label }}
    </label>
  </div>

  <div
    v-else-if="field.type === 'color'"
    :style="{ display: 'flex', gap: 6 }"
  >
    <input
      type="color"
      :value="displayValue || '#000000'"
      @input="handleChange(($event.target as HTMLInputElement).value)"
      :style="{
        width: 32,
        height: 32,
        border: '1px solid #D1D5DB',
        borderRadius: 4,
        padding: 0,
        cursor: 'pointer',
      }"
    />
    <input
      type="text"
      :value="displayValue || ''"
      @input="handleChange(($event.target as HTMLInputElement).value)"
      :style="{ ...inputStyle, width: 100 }"
    />
  </div>
</template>