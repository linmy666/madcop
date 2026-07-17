<script setup lang="ts">
/**
 * MadCop mascot — recolor body via canvas while keeping white eyes / dark pupils.
 * Optional `mood` drives cute CSS poses (justice idle, slacking, assign sparkle).
 */
import { ref, watch, onMounted, onUnmounted, computed } from 'vue'
import { getRecoloredMascotUrl } from '../../lib/mascotRecolor'
import mascotSrc from './mascot.png?url'

const props = withDefaults(
  defineProps<{
    size?: number
    color?: string
    /** idle | work | slack | assign | celebrate | blocked */
    mood?: string
  }>(),
  {
    size: 32,
    color: '',
    mood: '',
  },
)

const blinking = ref(false)
const displaySrc = ref(mascotSrc)
let timeoutId: number | undefined
let cancelled = false
let recolorGen = 0

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

async function applyColor(hex: string) {
  const gen = ++recolorGen
  try {
    if (!hex) {
      displaySrc.value = mascotSrc
      return
    }
    const url = await getRecoloredMascotUrl(mascotSrc, hex)
    if (gen === recolorGen && !cancelled) displaySrc.value = url
  } catch {
    if (gen === recolorGen) displaySrc.value = mascotSrc
  }
}

watch(
  () => props.color,
  (c) => {
    void applyColor(c || '')
  },
  { immediate: true },
)

onMounted(() => loop())
onUnmounted(() => {
  cancelled = true
  if (timeoutId) clearTimeout(timeoutId)
})

const imgStyle = computed(() => ({
  width: props.size + 'px',
  height: props.size + 'px',
  transform: blinking.value ? 'scaleY(0.08)' : 'scaleY(1)',
  transformOrigin: 'center 58%',
  transition: 'transform 80ms ease-in-out',
}))
</script>

<template>
  <div
    class="mascot-avatar"
    :class="mood ? `mascot-avatar--${mood}` : ''"
    :style="{ width: size + 'px', height: size + 'px' }"
  >
    <img
      :src="displaySrc"
      alt="MadCop mascot"
      class="mascot-avatar__img"
      :style="imgStyle"
      draggable="false"
    />
    <!-- Justice sparkle when assigned -->
    <span v-if="mood === 'assign'" class="mascot-avatar__spark" aria-hidden="true">✦</span>
    <span v-if="mood === 'slack'" class="mascot-avatar__zzz" aria-hidden="true">z</span>
  </div>
</template>

<style scoped>
.mascot-avatar {
  position: relative;
  flex-shrink: 0;
  animation: mascot-breathe 4s ease-in-out infinite;
}
.mascot-avatar__img {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  user-select: none;
}
.mascot-avatar--work {
  animation: mascot-work 1.2s ease-in-out infinite;
}
.mascot-avatar--slack {
  animation: mascot-slack 2.8s ease-in-out infinite;
}
.mascot-avatar--assign {
  animation: mascot-assign 0.7s ease;
}
.mascot-avatar--celebrate {
  animation: mascot-celebrate 0.9s ease;
}
.mascot-avatar--blocked {
  animation: mascot-blocked 1.5s ease-in-out infinite;
}
.mascot-avatar__spark {
  position: absolute;
  top: -4px;
  right: -2px;
  font-size: 12px;
  color: #fbbf24;
  animation: mascot-spark 0.8s ease infinite;
  pointer-events: none;
}
.mascot-avatar__zzz {
  position: absolute;
  top: -2px;
  right: 0;
  font-size: 10px;
  font-weight: 800;
  color: #94a3b8;
  animation: mascot-zzz 1.4s ease-in-out infinite;
  pointer-events: none;
}

@keyframes mascot-breathe {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.04);
  }
}
@keyframes mascot-work {
  0%,
  100% {
    transform: translateY(0) rotate(0);
  }
  50% {
    transform: translateY(-3px) rotate(-2deg);
  }
}
@keyframes mascot-slack {
  0%,
  100% {
    transform: rotate(-4deg) translateY(2px);
  }
  50% {
    transform: rotate(4deg) translateY(0);
  }
}
@keyframes mascot-assign {
  0% {
    transform: scale(0.85);
  }
  50% {
    transform: scale(1.12);
  }
  100% {
    transform: scale(1);
  }
}
@keyframes mascot-celebrate {
  0%,
  100% {
    transform: translateY(0);
  }
  30% {
    transform: translateY(-8px) rotate(-8deg);
  }
  60% {
    transform: translateY(-4px) rotate(8deg);
  }
}
@keyframes mascot-blocked {
  0%,
  100% {
    transform: translateX(0);
  }
  25% {
    transform: translateX(-2px);
  }
  75% {
    transform: translateX(2px);
  }
}
@keyframes mascot-spark {
  0%,
  100% {
    opacity: 0.4;
    transform: scale(0.8);
  }
  50% {
    opacity: 1;
    transform: scale(1.2);
  }
}
@keyframes mascot-zzz {
  0%,
  100% {
    opacity: 0.4;
    transform: translateY(0);
  }
  50% {
    opacity: 1;
    transform: translateY(-4px);
  }
}
</style>
