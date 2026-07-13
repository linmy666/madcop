<script setup lang="ts">
// v3.0 — AnimationPlayer (Vue 3)
// Direct translation — same video sources, same CSS animation fallbacks.
import { ref, computed, onMounted } from 'vue'

const props = withDefaults(defineProps<{
  name: 'clover' | 'ripple' | 'spinner'
  class?: string
  ariaLabel?: string
  loop?: boolean
}>(), {
  loop: true,
})

const failed = ref(false)

// NOTE: there is no spinner.mp4 asset — spinner intentionally has no video
// source and renders the CSS dot-bounce animation below. Pointing it at a
// missing file caused a recurring net::ERR_FILE_NOT_FOUND under file://.
const VIDEO_SRC: Record<string, string> = {
  clover: './animations/clover.mp4',
  ripple: './animations/ripple.mp4',
}

const ARIA_LABEL: Record<string, string> = {
  clover: 'MadCop is ready',
  ripple: 'MadCop is thinking',
  spinner: 'MadCop is working',
}

const label = computed(() => props.ariaLabel ?? ARIA_LABEL[props.name] ?? '')
</script>

<template>
  <video
    v-if="!failed && VIDEO_SRC[name]"
    :class="$props.class"
    :src="VIDEO_SRC[name]"
    autoplay
    :loop="loop"
    muted
    playsinline
    :aria-label="label"
    @error="failed = true"
  />
  <!-- Fallback: CSS-only animation -->
  <div v-else-if="name === 'clover'" :class="$props.class" role="img" :aria-label="label"
    style="width: 100%; height: 100%; background: radial-gradient(circle at 50% 50%, #5EEAD4 0%, #14B8A6 35%, #0F766E 60%, transparent 75%); animation: madcop-clover-pulse 2.5s ease-in-out infinite;" />
  <div v-else-if="name === 'ripple'" :class="$props.class" role="img" :aria-label="label"
    style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; position: relative;">
    <div style="width: 40%; height: 40%; border: 2px solid #14B8A6; border-radius: 50%; animation: madcop-ripple-out 1.6s ease-out infinite; position: absolute;" />
    <div style="width: 40%; height: 40%; border: 2px solid #5EEAD4; border-radius: 50%; animation: madcop-ripple-out 1.6s ease-out 0.4s infinite; position: absolute;" />
  </div>
  <div v-else :class="$props.class" role="img" :aria-label="label"
    style="width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; gap: 6px;">
    <div v-for="i in 3" :key="i"
      :style="{ width: '8px', height: '8px', background: '#14B8A6', borderRadius: '50%', animation: `madcop-dot-bounce 1.2s ${(i - 1) * 0.15}s ease-in-out infinite` }"
    />
  </div>
</template>

<style>
@keyframes madcop-clover-pulse {
  0%, 100% { transform: scale(1); opacity: 0.85; }
  50%      { transform: scale(1.08); opacity: 1; }
}
@keyframes madcop-ripple-out {
  0%   { transform: scale(0.4); opacity: 1; }
  100% { transform: scale(1.4); opacity: 0; }
}
@keyframes madcop-dot-bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.6; }
  40%           { transform: translateY(-6px); opacity: 1; }
}
</style>
