<script setup lang="ts">
/**
 * Animated agent on the studio floor: walk path + itch-style step frames
 * (mascot bob) + optional 16×18 walk sheet (OpenGameArt green-cap style).
 */
import { ref, watch, onMounted, onBeforeUnmount, computed } from 'vue'
import MascotAvatar from '../common/MascotAvatar.vue'
import {
  type ScenePoint,
  buildWalkPath,
  walkDurationMs,
  facingBetween,
  stationPoint,
} from '../../lib/spriteSceneLayout'
import { poseLabel, poseToMood, type SpritePose } from '../../lib/spriteStudio'
import { sanitizeAgentDisplayText } from '../../lib/agentDisplayText'
import { publicAssetPath } from '../../lib/publicAsset'

const props = defineProps<{
  id: string
  name: string
  color: string
  pose: SpritePose | string
  station: string
  bubble?: string
  selected?: boolean
  /** Prefer pixel walk-sheet when walking (itch-style) */
  usePixelSheet?: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  arrived: [id: string]
}>()

const pos = ref<ScenePoint>(stationPoint(props.station))
const walking = ref(false)
const facing = ref<'left' | 'right' | 'down' | 'up'>('down')
const stepFrame = ref(0) // 0–2 for sheet columns
const moveMs = ref(280)
let stepTimer: number | undefined
let walkTimer: number | undefined
let prevStation = props.station

const sheetUrl = publicAssetPath('studio/walk-sheet.png')

// walk-sheet: 48×72 = 3 cols × 4 rows, frame 16×18
const sheetStyle = computed(() => {
  const col = stepFrame.value % 3
  const row = { down: 0, left: 1, right: 2, up: 3 }[facing.value]
  const x = -col * 16
  const y = -row * 18
  return {
    backgroundImage: `url(${sheetUrl})`,
    backgroundPosition: `${x}px ${y}px`,
    backgroundSize: '48px 72px',
    imageRendering: 'pixelated' as const,
    width: '32px',
    height: '36px',
    transform: 'scale(2)',
    transformOrigin: 'bottom center',
  }
})

function startStepLoop() {
  stopStepLoop()
  stepTimer = window.setInterval(() => {
    stepFrame.value = (stepFrame.value + 1) % 3
  }, 120)
}

function stopStepLoop() {
  if (stepTimer) {
    clearInterval(stepTimer)
    stepTimer = undefined
  }
  stepFrame.value = 1 // idle frame
}

function walkToStation(station: string) {
  const to = stationPoint(station)
  const from = { ...pos.value }
  const path = buildWalkPath(from, to)
  const ms = walkDurationMs(path)
  if (ms <= 0 || path.length < 2) {
    pos.value = to
    walking.value = false
    stopStepLoop()
    emit('arrived', props.id)
    return
  }
  walking.value = true
  startStepLoop()
  // Face first segment
  facing.value = facingBetween(path[0], path[1])

  // CSS transition along segments sequentially
  let i = 1
  const go = () => {
    if (i >= path.length) {
      walking.value = false
      stopStepLoop()
      pos.value = to
      emit('arrived', props.id)
      return
    }
    const next = path[i]
    const prev = path[i - 1]
    facing.value = facingBetween(prev, next)
    const segMs = Math.max(
      200,
      Math.round(
        ms *
          (Math.hypot(next.x - prev.x, next.y - prev.y) /
            path.reduce((acc, p, idx) => {
              if (idx === 0) return 0
              return acc + Math.hypot(p.x - path[idx - 1].x, p.y - path[idx - 1].y)
            }, 0.001)),
      ),
    )
    moveMs.value = segMs
    // next frame so transition-duration applies before left/top change
    requestAnimationFrame(() => {
      pos.value = next
    })
    walkTimer = window.setTimeout(() => {
      i++
      go()
    }, segMs)
  }
  go()
}

watch(
  () => props.station,
  (st) => {
    if (st === prevStation) return
    prevStation = st
    walkToStation(st)
  },
)

// Assigned / justice call-up: re-walk to desk even if station string unchanged
watch(
  () => props.pose,
  (pose, prev) => {
    if (pose === 'assigned' && prev !== 'assigned') {
      prevStation = ''
      walkToStation(props.station)
    }
  },
)

onMounted(() => {
  // Enter from door then walk to seat
  pos.value = stationPoint('door')
  walkToStation(props.station)
})

onBeforeUnmount(() => {
  stopStepLoop()
  if (walkTimer) clearTimeout(walkTimer)
})

const rootStyle = computed(() => ({
  left: `${pos.value.x}%`,
  top: `${pos.value.y}%`,
  transition: walking.value
    ? `left ${moveMs.value}ms linear, top ${moveMs.value}ms linear`
    : 'left 0.35s ease, top 0.35s ease',
  zIndex: Math.round(10 + pos.value.y),
}))

const showPixel = computed(
  () => props.usePixelSheet && walking.value,
)

const cleanBubble = computed(() =>
  props.bubble ? sanitizeAgentDisplayText(props.bubble, 40) : '',
)

const mood = computed(() =>
  walking.value ? 'work' : poseToMood(props.pose),
)
</script>

<template>
  <button
    type="button"
    class="sw"
    :class="[
      `sw--${pose}`,
      {
        'sw--walking': walking,
        'sw--selected': selected,
        'sw--face-left': facing === 'left',
      },
    ]"
    :style="rootStyle"
    :title="`${name} · ${poseLabel(pose as any)}`"
    @click="emit('select', id)"
  >
    <!-- Thinking dots (MadCop justice thinking) -->
    <span v-if="!walking && pose === 'thinking'" class="sw__think" aria-hidden="true">
      <i /><i /><i />
    </span>
    <span v-if="cleanBubble && !walking" class="sw__bubble">{{ cleanBubble }}</span>
    <span class="sw__shadow" />
    <!-- Always MadCop mascot by default; optional pixel sheet only if enabled -->
    <span v-if="showPixel" class="sw__pixel" :style="sheetStyle" />
    <span v-else class="sw__mascot" :class="{ 'sw__mascot--walk': walking }">
      <MascotAvatar :size="40" :color="color" :mood="mood" />
    </span>
    <!-- Work desk glow under mascot when typing/tools -->
    <span
      v-if="!walking && (pose === 'working' || pose === 'tool_file' || pose === 'tool_web')"
      class="sw__desk-fx"
      aria-hidden="true"
    />
    <span class="sw__badge" :data-pose="walking ? 'working' : pose" />
    <span class="sw__name">{{ name }}</span>
    <span class="sw__pose">{{ walking ? '赶路上岗' : poseLabel(pose as any) }}</span>
  </button>
</template>

<style scoped>
.sw {
  position: absolute;
  transform: translate(-50%, -88%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 4px 6px;
  border-radius: 12px;
  pointer-events: auto;
}
.sw--selected {
  background: rgba(255, 255, 255, 0.14);
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.4);
}
.sw:hover {
  filter: brightness(1.08);
}
.sw__shadow {
  position: absolute;
  bottom: 14px;
  width: 28px;
  height: 8px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.35);
  filter: blur(2px);
  z-index: 0;
}
.sw__mascot {
  position: relative;
  z-index: 1;
  filter: drop-shadow(0 4px 8px rgba(0, 0, 0, 0.35));
}
.sw__mascot--walk {
  animation: sw-step 0.28s steps(2) infinite;
}
.sw--walking .sw__mascot {
  animation: sw-step 0.28s steps(2) infinite;
}
.sw__pixel {
  position: relative;
  z-index: 1;
  display: block;
  margin-bottom: 4px;
  filter: drop-shadow(0 3px 0 rgba(0, 0, 0, 0.25));
}
.sw__badge {
  position: absolute;
  top: 2px;
  right: 2px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  border: 1.5px solid #fff;
  background: #9ca3af;
  z-index: 2;
}
.sw__badge[data-pose='thinking'],
.sw__badge[data-pose='working'],
.sw__badge[data-pose='tool_file'],
.sw__badge[data-pose='tool_web'] {
  background: #22c55e;
  animation: sw-pulse 1s ease infinite;
}
.sw__badge[data-pose='blocked'] {
  background: #f59e0b;
}
.sw__badge[data-pose='done'] {
  background: #6366f1;
}
.sw__badge[data-pose='error'] {
  background: #ef4444;
}
.sw__name {
  font-size: 10px;
  font-weight: 700;
  color: #fff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.75);
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sw__pose {
  font-size: 9px;
  color: rgba(255, 255, 255, 0.75);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}
.sw__bubble {
  position: absolute;
  bottom: calc(100% - 2px);
  left: 50%;
  transform: translateX(-50%);
  max-width: 132px;
  padding: 5px 9px;
  border-radius: 10px 10px 10px 4px;
  background: #fff;
  color: #1f2937;
  font-size: 10px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.18);
  z-index: 5;
  animation: sw-bubble 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
  pointer-events: none;
}
.sw--face-left .sw__mascot {
  transform: scaleX(-1);
}
.sw__think {
  position: absolute;
  bottom: calc(100% + 2px);
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 3px;
  z-index: 6;
}
.sw__think i {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #fff;
  opacity: 0.5;
  animation: sw-dot 1s ease infinite;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
}
.sw__think i:nth-child(2) {
  animation-delay: 0.15s;
}
.sw__think i:nth-child(3) {
  animation-delay: 0.3s;
}
.sw__desk-fx {
  position: absolute;
  bottom: 18px;
  width: 42px;
  height: 10px;
  border-radius: 50%;
  background: radial-gradient(ellipse, rgba(167, 139, 250, 0.55), transparent 70%);
  animation: sw-desk 1.1s ease-in-out infinite;
  z-index: 0;
  pointer-events: none;
}

@keyframes sw-step {
  0% {
    transform: translateY(0) rotate(-2deg);
  }
  50% {
    transform: translateY(-3px) rotate(2deg);
  }
  100% {
    transform: translateY(0) rotate(-2deg);
  }
}
@keyframes sw-bob {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-4px);
  }
}
@keyframes sw-pulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.2);
  }
}
@keyframes sw-bubble {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(4px) scale(0.9);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0) scale(1);
  }
}
@keyframes sw-dot {
  0%,
  100% {
    opacity: 0.35;
    transform: translateY(0);
  }
  50% {
    opacity: 1;
    transform: translateY(-3px);
  }
}
@keyframes sw-desk {
  0%,
  100% {
    opacity: 0.45;
    transform: scaleX(1);
  }
  50% {
    opacity: 0.9;
    transform: scaleX(1.15);
  }
}
</style>
