<script setup lang="ts">
withDefaults(defineProps<{ open?: boolean }>(), { open: false })
defineEmits<{ (e: 'close'): void; (e: 'approve'): void }>()
</script>
<template><div v-if="open" class="p-4 text-sm">Computer Use 权限请求</div></template>
