<script setup lang="ts">
// v3.0 — TargetIcon (Vue 3)
// Direct translation — same img/fallback logic, same Tailwind classes.
import { ref, watch } from 'vue'

const props = withDefaults(defineProps<{
  iconUrl?: string
  kind: 'ide' | 'file_manager'
  size?: number
}>(), {
  size: 18,
})

const failed = ref(false)
watch(() => props.iconUrl, () => { failed.value = false })
</script>

<template>
  <img
    v-if="iconUrl && !failed"
    :src="iconUrl"
    alt=""
    aria-hidden="true"
    draggable="false"
    @error="failed = true"
    class="block shrink-0 object-contain"
    :style="{ width: size + 'px', height: size + 'px' }"
  />
  <span
    v-else
    class="material-symbols-outlined"
    :style="{ fontSize: Math.max(16, size - 1) + 'px' }"
  >
    {{ kind === 'file_manager' ? 'folder_open' : 'code' }}
  </span>
</template>
