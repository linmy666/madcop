<script setup lang="ts">
// v3.0 — MascotAvatar (Vue 3)
// Direct translation — same blink/breathe animations.
import { ref, onMounted, onUnmounted, computed } from 'vue'

const props = withDefaults(defineProps<{ size?: number }>(), {
  size: 32,
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

const imgStyle = computed(() => ({
  width: props.size + 'px',
  height: props.size + 'px',
  transform: blinking.value ? 'scaleY(0.05)' : 'scaleY(1)',
  transformOrigin: 'center 60%',
  transition: 'transform 80ms ease-in-out',
  animation: 'mascot-breathe 4s ease-in-out infinite',
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
