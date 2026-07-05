<script setup lang="ts">
// v3.0 — MadCopLoader (Vue 3)
// Mascot image with breathing/thinking/working CSS animations.
// Keyframes are in a GLOBAL <style> tag (not scoped) so the animation
// names are not mangled by Vue's scoping mechanism.

import { ref, onMounted, computed } from 'vue'

export type MadCopState = 'ready' | 'thinking' | 'working'

const props = withDefaults(defineProps<{
  state: MadCopState
  size?: number
  label?: string
}>(), {
  size: 140,
})

const STAGE_LABELS: Record<MadCopState, string> = {
  ready: '在线 · 随时待命',
  thinking: '正在分析...',
  working: '正在执行...',
}

const mascotSrc = ref('./mascot.png?v=2633')
const animClass = computed(() =>
  props.state === 'thinking' ? 'madcop-anim-think'
  : props.state === 'working' ? 'madcop-anim-work'
  : 'madcop-anim-breathe'
)
const displayLabel = computed(() => props.label ?? STAGE_LABELS[props.state])
</script>

<template>
  <div class="madcop-loader" role="img" :aria-label="displayLabel">
    <div :class="['madcop-loader__anim', animClass]" :style="{ width: size + 'px', height: size + 'px' }">
      <img :src="mascotSrc" alt="MadCop mascot" class="madcop-loader__img" draggable="false" />
    </div>
    <div class="madcop-loader__label">{{ displayLabel }}</div>
  </div>
</template>

<style scoped>
.madcop-loader {
  display: flex; flex-direction: column; align-items: center; gap: 12px;
  background: transparent;
}
.madcop-loader__anim {
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
  background: transparent;
}
.madcop-loader__img {
  width: 100%; height: 100%; display: block;
  object-fit: contain; background: transparent;
}
.madcop-loader__label {
  font-size: 16px; color: var(--color-text-secondary);
  font-weight: 500; text-align: center;
}
</style>

<style>
/* Global keyframes — NOT scoped, so the animation names match */
@keyframes madcop-anim-breathe {
  0%, 100% { transform: scale(1) translateY(0); }
  50% { transform: scale(1.04) translateY(-3px); }
}
@keyframes madcop-anim-think {
  0%, 100% { transform: rotate(-3deg); }
  25% { transform: rotate(-5deg); }
  50% { transform: rotate(0deg); }
  75% { transform: rotate(5deg); }
}
@keyframes madcop-anim-work {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-8px); }
}
.madcop-anim-breathe {
  animation: madcop-anim-breathe 3s ease-in-out infinite;
  transform-origin: center;
}
.madcop-anim-think {
  animation: madcop-anim-think 1.6s ease-in-out infinite;
  transform-origin: center bottom;
}
.madcop-anim-work {
  animation: madcop-anim-work 0.8s ease-in-out infinite;
  transform-origin: center;
}
</style>