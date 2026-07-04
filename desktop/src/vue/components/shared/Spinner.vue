<script setup lang="ts">
// v3.0 — Spinner (Vue 3)
// Direct translation of Spinner.tsx — same SVG, same className.
withDefaults(defineProps<{ size?: number; class?: string }>(), {
  size: 20,
})
</script>

<template>
  <svg
    :class="['animate-spin', $props.class]"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
  >
    <circle
      class="opacity-25"
      cx="12"
      cy="12"
      r="10"
      stroke="currentColor"
      stroke-width="4"
    />
    <path
      class="opacity-75"
      fill="currentColor"
      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
    />
  </svg>
</template>
