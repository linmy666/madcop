<script setup lang="ts">
import { ref, onMounted, onUnmounted, computed } from 'vue'

/**
 * MadCopLoader — Vue 3 port of components/common/MadCopLoader.tsx
 * Simple mascot image with breathing/thinking/working CSS animations.
 * No external dependencies, no stores, no third-party libraries.
 */

export type MadCopState = 'ready' | 'thinking' | 'working'

export interface MadCopLoaderProps {
  state: MadCopState
  size?: number
  label?: string
}

const props = withDefaults(defineProps<MadCopLoaderProps>(), {
  size: 192,
})

const STAGE_LABELS: Record<MadCopState, string> = {
  ready: 'MadCop 已准备好',
  thinking: 'MadCop 正在思考',
  working: 'MadCop 正在工作',
}

const mascotSrc = ref('./mascot.png')
const animClass = computed(() =>
  props.state === 'thinking' ? 'madcop-anim-think'
  : props.state === 'working' ? 'madcop-anim-work'
  : 'madcop-anim-breathe'
)
const displayLabel = computed(() => props.label ?? STAGE_LABELS[props.state])

let observer: MutationObserver | null = null
onMounted(() => {
  mascotSrc.value = './mascot.png?v=2633'
  observer = new MutationObserver(() => { mascotSrc.value = './mascot.png?v=2633' })
  observer.observe(document.body, { attributes: true, attributeFilter: ['class'] })
})
onUnmounted(() => { observer?.disconnect() })
</script>

<template>
  <div class="madcop-loader" :role="'img'" :aria-label="displayLabel"
    style="display: flex; flex-direction: column; align-items: center; gap: 12px; background: transparent;">
    <div :class="animClass"
      :style="{ width: `${props.size}px`, height: `${props.size}px`, background: 'transparent', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }">
      <img :src="mascotSrc" alt="MadCop mascot" class="block" :draggable="false"
        style="width: 100%; height: 100%; image-rendering: auto; object-fit: contain; background: transparent; display: block;" />
    </div>
    <div style="font-size: 16px; color: var(--color-text-secondary); font-weight: 500; text-align: center;">{{ displayLabel }}</div>
    <style scoped>
.madcop-anim-breathe { animation: madcop-anim-breathe 3s ease-in-out infinite; transform-origin: center; }
.madcop-anim-think { animation: madcop-anim-think 1.6s ease-in-out infinite; transform-origin: center bottom; }
.madcop-anim-work { animation: madcop-anim-work 0.8s ease-in-out infinite; transform-origin: center; }
@keyframes madcop-anim-breathe { 0%, 100% { transform: scale(1) translateY(0); } 50% { transform: scale(1.04) translateY(-3px); } }
@keyframes madcop-anim-think { 0%, 100% { transform: rotate(-3deg); } 25% { transform: rotate(-5deg); } 50% { transform: rotate(0deg); } 75% { transform: rotate(5deg); } }
@keyframes madcop-anim-work { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-8px); } }
    </style>
  </div>
</template>
