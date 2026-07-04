<script setup lang="ts">
// v3.0 — Spinner (Vue 3)
withDefaults(defineProps<{ size?: number; class?: string }>(), {
  size: 20,
})
</script>

<template>
  <svg
    :class="['madcop-spinner', $props.class]"
    :width="size" :height="size"
    viewBox="0 0 24 24" fill="none"
  >
    <circle
      class="madcop-spinner__track"
      cx="12" cy="12" r="10"
      stroke="currentColor" stroke-width="4"
    />
    <path
      class="madcop-spinner__arc"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
    />
  </svg>
</template>

<style scoped>
.madcop-spinner { animation: madcop-spin 0.8s linear infinite; }
.madcop-spinner__track { opacity: 0.25; }
.madcop-spinner__arc  { opacity: 0.75; }
@keyframes madcop-spin { to { transform: rotate(360deg); } }
</style>
