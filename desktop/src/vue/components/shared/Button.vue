<script setup lang="ts">
// v3.0 — Button (Vue 3)
import { computed } from 'vue'

withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
}>(), {
  variant: 'primary',
  size: 'md',
  loading: false,
  disabled: false,
  type: 'button',
})

defineEmits<{ (e: 'click', ev: MouseEvent): void }>()
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :class="['madcop-btn', `madcop-btn--${variant}`, `madcop-btn--${size}`, { 'madcop-btn--loading': loading }]"
    @click="(e) => $emit('click', e)"
  >
    <span v-if="loading" class="madcop-btn__spinner" />
    <slot v-else name="icon" />
    <slot />
  </button>
</template>

<style scoped>
.madcop-btn {
  display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  font-weight: 500; cursor: pointer;
  border: 1.5px solid transparent;
  transition: filter 140ms;
  font-family: 'Geist Mono', monospace;
  font-size: 12px;
}
.madcop-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.madcop-btn--sm { padding: 4px 8px; font-size: 11px; }
.madcop-btn--md { padding: 6px 14px; font-size: 12px; }
.madcop-btn--lg { padding: 8px 20px; font-size: 13px; }

.madcop-btn--primary {
  background: var(--madcop-accent);
  color: var(--madcop-accent-ink);
  border-color: var(--madcop-accent);
}
.madcop-btn--primary:hover:not(:disabled) { background: var(--madcop-accent-hover); }

.madcop-btn--secondary {
  background: var(--madcop-panel-raised);
  color: var(--madcop-ink);
  border-color: var(--madcop-line);
}
.madcop-btn--secondary:hover:not(:disabled) { background: var(--madcop-panel-sunken); }

.madcop-btn--danger {
  background: var(--madcop-danger);
  color: #fff;
  border-color: var(--madcop-danger);
}

.madcop-btn--ghost {
  background: transparent;
  color: var(--madcop-ink-body);
  border-color: transparent;
}
.madcop-btn--ghost:hover:not(:disabled) { background: var(--madcop-panel-sunken); color: var(--madcop-ink); }

.madcop-btn__spinner {
  width: 12px; height: 12px;
  border: 1.5px solid currentColor; border-top-color: transparent;
  border-radius: 50%;
  animation: madcop-btn-spin 0.6s linear infinite;
}
@keyframes madcop-btn-spin { to { transform: rotate(360deg); } }
</style>
