<script setup lang="ts">
// MascotAvatar — the MadCop sprite, with blink/breathe animations.
// Optional `color` prop tints the sprite via CSS filters (hue-rotate +
// saturate) so a single mascot.png renders as different-colored agents
// (planner purple, coder blue, reviewer orange, …) — no extra assets.
import { ref, onMounted, onUnmounted, computed } from 'vue'

const props = withDefaults(defineProps<{ size?: number; color?: string }>(), {
  size: 32,
  color: '',
})

const blinking = ref(false)
let timeoutId: number | undefined
let cancelled = false

function loop() {
  if (cancelled) return
  const delay = 4000 + Math.random() * 2000
  timeoutId = window.setTimeout(() => {
    if (cancelled) return
    blinking.value = true
    window.setTimeout(() => {
      if (cancelled) return
      blinking.value = false
      loop()
    }, 120)
  }, delay)
}

onMounted(() => loop())
onUnmounted(() => {
  cancelled = true
  if (timeoutId) clearTimeout(timeoutId)
})

// Convert a target hex color into a hue-rotate filter. The base mascot is
// ~#7C3AED (hue ≈ 263°); we rotate by (targetHue − 263) so the sprite takes
// on the agent's theme color. Saturate slightly to keep it vivid.
function hueFor(hex: string): number {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) return 0
  const r = parseInt(m[1].slice(0, 2), 16) / 255
  const g = parseInt(m[1].slice(2, 4), 16) / 255
  const b = parseInt(m[1].slice(4, 6), 16) / 255
  const max = Math.max(r, g, b), min = Math.min(r, g, b)
  if (max === min) return 0
  const d = max - min
  let h = 0
  if (max === r) h = ((g - b) / d + (g < b ? 6 : 0))
  else if (max === g) h = ((b - r) / d + 2)
  else h = ((r - g) / d + 4)
  return Math.round(h * 60 - 263)
}

const colorFilter = computed(() => {
  if (!props.color) return 'none'
  return `hue-rotate(${hueFor(props.color)}deg) saturate(1.15)`
})

const imgStyle = computed(() => ({
  width: props.size + 'px',
  height: props.size + 'px',
  transform: blinking.value ? 'scaleY(0.05)' : 'scaleY(1)',
  transformOrigin: 'center 60%',
  transition: 'transform 80ms ease-in-out',
  animation: 'mascot-breathe 4s ease-in-out infinite',
  filter: colorFilter.value,
}))
</script>

<template>
  <div class="relative flex-shrink-0" :style="{ width: size + 'px', height: size + 'px' }">
    <img
      src="./mascot.png?v=2633"
      alt="MadCop mascot"
      class="absolute inset-0 h-full w-full"
      :style="imgStyle"
      draggable="false"
    />
  </div>
</template>

<style>
@keyframes mascot-breathe {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.04); }
}
</style>
