<script setup lang="ts">
defineProps<{ question?: string; options?: string[]; allowFreeText?: boolean }>()
defineEmits<{ (e: 'choose', choice: string): void }>()
</script>
<template><div v-if="question" class="p-4 text-sm text-[var(--color-text-secondary)]">{{ question }}</div></template>
