<script setup lang="ts">
/**
 * Sprite Studio — scene-first multi-agent stage.
 * Layered room SVG skins + animated mascots at hotspots (no empty desk spam).
 */
import { ref, computed, watch } from 'vue'
import MascotAvatar from '../common/MascotAvatar.vue'
import {
  type SpriteAgent,
  type SpriteDetail,
  type StudioSkinId,
  STUDIO_SKINS,
  poseLabel,
  selectSpriteDetail,
  loadStudioSkin,
  saveStudioSkin,
} from '../../lib/spriteStudio'
import { publicAssetPath } from '../../lib/publicAsset'

const props = defineProps<{
  roster: SpriteAgent[]
  routeLabel?: string | null
  routeReason?: string | null
}>()

const emit = defineEmits<{
  select: [id: string]
}>()

const skin = ref<StudioSkinId>(loadStudioSkin())
const selectedId = ref<string | null>(null)

watch(skin, (s) => saveStudioSkin(s))

const detail = computed<SpriteDetail | null>(() =>
  selectSpriteDetail(props.roster, selectedId.value),
)

const roomSrc = computed(() => {
  const map: Record<StudioSkinId, string> = {
    studio: publicAssetPath('studio/room-studio.svg'),
    study: publicAssetPath('studio/room-study.svg'),
    cabin: publicAssetPath('studio/room-cabin.svg'),
  }
  return map[skin.value] || map.studio
})

/** Hotspots aligned with furniture in room-*.svg (viewBox 1200×700) */
const HOTSPOTS: Record<string, { x: number; y: number; label: string }> = {
  planner: { x: 18, y: 52, label: '规划' },
  coder: { x: 50, y: 52, label: '写码' },
  designer: { x: 82, y: 52, label: '设计' },
  researcher: { x: 18, y: 72, label: '调研' },
  reviewer: { x: 50, y: 72, label: '审核' },
  synthesizer: { x: 82, y: 72, label: '合成' },
  general: { x: 12, y: 88, label: '助手' },
}

/** Only stations that have sprites — never flood the room with 空位 */
const activeStations = computed(() => {
  const byStation = new Map<string, SpriteAgent[]>()
  for (const a of props.roster) {
    const st = a.station || a.role || 'general'
    if (!byStation.has(st)) byStation.set(st, [])
    byStation.get(st)!.push(a)
  }
  return [...byStation.entries()].map(([station, agents]) => {
    const hs = HOTSPOTS[station] || HOTSPOTS.general
    return {
      station,
      label: hs.label,
      agents,
      style: {
        left: `${hs.x}%`,
        top: `${hs.y}%`,
      },
    }
  })
})

const idleLounge = computed(() =>
  props.roster.filter((a) => a.pose === 'idle' || a.pose === 'done'),
)

const isEmpty = computed(() => props.roster.length === 0)

function onSelect(id: string) {
  selectedId.value = id
  emit('select', id)
}

function setSkin(id: StudioSkinId) {
  skin.value = id
}

function poseClass(pose: string) {
  return `ssa--${pose}`
}
</script>

<template>
  <div class="ss" :class="`ss--${skin}`">
    <header class="ss__top">
      <div class="ss__heading">
        <div class="ss__live" v-if="!isEmpty">
          <span class="ss__live-dot" />
          LIVE
        </div>
        <h2 class="ss__title">精灵工作室</h2>
        <p class="ss__sub">
          {{ routeLabel || '多 Agent 场景舞台' }}
          <span v-if="routeReason" class="ss__reason"> · {{ routeReason }}</span>
        </p>
      </div>
      <div class="ss__skins" role="group" aria-label="场景皮肤">
        <button
          v-for="s in STUDIO_SKINS"
          :key="s.id"
          type="button"
          :class="['ss__skin', { 'ss__skin--on': skin === s.id }]"
          :title="s.hint"
          @click="setSkin(s.id)"
        >
          <span class="ss__skin-thumb" :data-skin="s.id" />
          <span class="ss__skin-label">{{ s.label }}</span>
        </button>
      </div>
    </header>

    <div class="ss__body">
      <div class="ss__stage">
        <!-- Room art -->
        <img class="ss__room" :src="roomSrc" :alt="skin + ' room'" draggable="false" />

        <!-- Ambient particles -->
        <div class="ss__particles" aria-hidden="true">
          <span v-for="n in 12" :key="n" class="ss__p" :style="{ '--i': n }" />
        </div>

        <!-- Empty hero -->
        <div v-if="isEmpty" class="ss__hero">
          <div class="ss__hero-glow" />
          <div class="ss__hero-mascot">
            <MascotAvatar :size="72" color="#7C3AED" />
          </div>
          <h3 class="ss__hero-title">工作室暂未开工</h3>
          <p class="ss__hero-sub">
            用「深度」模式跑一轮任务，彩色精灵会坐到对应工位
          </p>
          <div class="ss__hero-hint">
            <span class="ss__hero-chip">规划</span>
            <span class="ss__hero-chip">写码</span>
            <span class="ss__hero-chip">设计</span>
            <span class="ss__hero-chip">调研</span>
          </div>
        </div>

        <!-- Active agents at hotspots only -->
        <div
          v-for="st in activeStations"
          :key="st.station"
          class="ss-spot"
          :style="st.style"
        >
          <div class="ss-spot__label">{{ st.label }}</div>
          <button
            v-for="a in st.agents"
            :key="a.id"
            type="button"
            class="ssa"
            :class="[poseClass(a.pose), { 'ssa--selected': selectedId === a.id }]"
            @click="onSelect(a.id)"
          >
            <span v-if="a.bubble" class="ssa__bubble">
              <span class="ssa__bubble-text">{{ a.bubble }}</span>
            </span>
            <span class="ssa__shadow" />
            <span class="ssa__ring" :style="{ borderColor: a.color }" />
            <MascotAvatar :size="44" :color="a.color" />
            <span class="ssa__badge" :data-pose="a.pose" />
            <span class="ssa__name" :style="{ color: a.color }">{{ a.name }}</span>
            <span class="ssa__pose">{{ poseLabel(a.pose) }}</span>
          </button>
        </div>

        <!-- Lounge strip for done/idle (coffee corner) -->
        <div v-if="idleLounge.length && !isEmpty" class="ss__lounge">
          <span class="ss__lounge-label">休息区</span>
          <div
            v-for="a in idleLounge.slice(0, 4)"
            :key="'lounge-' + a.id"
            class="ss__lounge-item"
            @click="onSelect(a.id)"
          >
            <MascotAvatar :size="22" :color="a.color" />
          </div>
        </div>
      </div>

      <!-- Detail pane -->
      <aside class="ss__detail">
        <h3 class="ss__detail-title">精灵档案</h3>
        <div v-if="!detail" class="ss__detail-empty">
          <div class="ss__detail-empty-art">
            <MascotAvatar :size="40" color="#7C3AED" />
          </div>
          <p>点选场景里的精灵</p>
          <p class="ss__detail-muted">输出与会话 agentStreams 同源</p>
        </div>
        <div v-else class="ss__detail-card" :style="{ '--c': detail.color }">
          <div class="ss__detail-head">
            <div class="ss__detail-avatar">
              <MascotAvatar :size="48" :color="detail.color" />
            </div>
            <div>
              <div class="ss__detail-name">{{ detail.name }}</div>
              <div class="ss__detail-meta">
                <span class="ss__pill" :data-pose="detail.pose">{{ poseLabel(detail.pose) }}</span>
                <span v-if="detail.elapsed_ms">{{ Math.round(detail.elapsed_ms / 1000) }}s</span>
              </div>
            </div>
          </div>
          <div v-if="detail.bubble" class="ss__detail-bubble">{{ detail.bubble }}</div>
          <div class="ss__detail-stream">
            <div class="ss__detail-stream-label">
              {{ detail.hasStream && detail.text ? '实时输出' : '等待输出' }}
            </div>
            <pre v-if="detail.text" class="ss__detail-text">{{ detail.text }}</pre>
            <div v-else class="ss__detail-wait">
              <span class="ss__detail-dots"><i /><i /><i /></span>
            </div>
          </div>
          <p class="ss__detail-note">选择仅聚焦展示，不会改写服务端路由。</p>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.ss {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 480px;
  border-radius: 16px;
  overflow: hidden;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  box-shadow: 0 12px 40px rgba(15, 23, 42, 0.08);
}
.ss__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-container-lowest, #fff);
  flex-shrink: 0;
}
.ss__live {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.12em;
  color: #16a34a;
  margin-bottom: 4px;
}
.ss__live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22c55e;
  box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.5);
  animation: ss-live 1.6s ease infinite;
}
.ss__title {
  margin: 0;
  font-size: 18px;
  font-weight: 700;
  letter-spacing: -0.02em;
}
.ss__sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.ss__reason {
  color: var(--color-text-tertiary);
}
.ss__skins {
  display: flex;
  gap: 8px;
}
.ss__skin {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  border: 2px solid transparent;
  background: transparent;
  padding: 4px;
  border-radius: 12px;
  cursor: pointer;
  color: var(--color-text-secondary);
}
.ss__skin--on {
  border-color: var(--color-brand, #7c3aed);
  color: var(--color-brand, #7c3aed);
}
.ss__skin-thumb {
  width: 56px;
  height: 36px;
  border-radius: 8px;
  background-size: cover;
  background-position: center;
  box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.08);
}
.ss__skin-thumb[data-skin='studio'] {
  background: linear-gradient(145deg, #2a2540 30%, #7c3aed 100%);
}
.ss__skin-thumb[data-skin='study'] {
  background: linear-gradient(145deg, #f5e6c8 20%, #b45309 90%);
}
.ss__skin-thumb[data-skin='cabin'] {
  background: linear-gradient(145deg, #3d5c3a 25%, #86efac 70%, #fbbf24 100%);
}
.ss__skin-label {
  font-size: 10px;
  font-weight: 600;
}
.ss__body {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}
.ss__stage {
  flex: 1;
  min-width: 0;
  position: relative;
  overflow: hidden;
  background: #1a1628;
}
.ss__room {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  object-position: center bottom;
  user-select: none;
  pointer-events: none;
  animation: ss-room-in 0.5s ease;
}
.ss__particles {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}
.ss__p {
  position: absolute;
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.55);
  left: calc(8% * var(--i));
  bottom: -10%;
  animation: ss-float calc(8s + var(--i) * 0.4s) linear infinite;
  animation-delay: calc(var(--i) * -0.7s);
  opacity: 0.35;
}
.ss--study .ss__p {
  background: rgba(251, 191, 36, 0.55);
}
.ss--cabin .ss__p {
  background: rgba(134, 239, 172, 0.55);
}

/* Hero empty state */
.ss__hero {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  z-index: 5;
  text-align: center;
  padding: 24px;
  background: radial-gradient(ellipse at 50% 40%, rgba(0, 0, 0, 0.15), rgba(0, 0, 0, 0.45));
}
.ss__hero-glow {
  position: absolute;
  width: 200px;
  height: 200px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(124, 58, 237, 0.45), transparent 70%);
  animation: ss-glow 3s ease-in-out infinite;
}
.ss__hero-mascot {
  position: relative;
  z-index: 1;
  animation: ss-bob 2.4s ease-in-out infinite;
  filter: drop-shadow(0 12px 24px rgba(0, 0, 0, 0.35));
}
.ss__hero-title {
  position: relative;
  margin: 16px 0 6px;
  font-size: 18px;
  font-weight: 700;
  color: #fff;
  text-shadow: 0 2px 8px rgba(0, 0, 0, 0.4);
}
.ss__hero-sub {
  position: relative;
  margin: 0;
  font-size: 13px;
  color: rgba(255, 255, 255, 0.78);
  max-width: 320px;
  line-height: 1.5;
}
.ss__hero-hint {
  position: relative;
  display: flex;
  gap: 6px;
  margin-top: 14px;
  flex-wrap: wrap;
  justify-content: center;
}
.ss__hero-chip {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.18);
}

/* Hotspot agents */
.ss-spot {
  position: absolute;
  transform: translate(-50%, -70%);
  z-index: 4;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.ss-spot__label {
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: rgba(255, 255, 255, 0.7);
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.6);
  margin-bottom: 2px;
}
.ssa {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 4px 8px 6px;
  border-radius: 14px;
  transition: transform 0.15s ease;
}
.ssa:hover {
  transform: translateY(-4px) scale(1.05);
}
.ssa--selected {
  background: rgba(255, 255, 255, 0.12);
  box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.35);
}
.ssa__shadow {
  position: absolute;
  bottom: 18px;
  width: 36px;
  height: 10px;
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.35);
  filter: blur(3px);
  z-index: 0;
}
.ssa__ring {
  position: absolute;
  top: 2px;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  border: 2px solid transparent;
  opacity: 0.5;
  z-index: 0;
}
.ssa--thinking .ssa__ring,
.ssa--working .ssa__ring,
.ssa--tool_file .ssa__ring,
.ssa--tool_web .ssa__ring {
  animation: ss-ring 1.4s ease-out infinite;
}
.ssa :deep(img),
.ssa > :nth-child(3) {
  position: relative;
  z-index: 1;
}
.ssa__badge {
  position: absolute;
  top: 4px;
  right: 6px;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 2px solid #fff;
  background: #9ca3af;
  z-index: 2;
}
.ssa__badge[data-pose='thinking'],
.ssa__badge[data-pose='working'],
.ssa__badge[data-pose='tool_file'],
.ssa__badge[data-pose='tool_web'] {
  background: #22c55e;
  animation: ss-pulse 1.1s ease infinite;
}
.ssa__badge[data-pose='blocked'] {
  background: #f59e0b;
}
.ssa__badge[data-pose='done'] {
  background: #6366f1;
}
.ssa__badge[data-pose='error'] {
  background: #ef4444;
}
.ssa__name {
  font-size: 11px;
  font-weight: 700;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.7);
  color: #fff !important;
  max-width: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ssa__pose {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.75);
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.5);
}
.ssa__bubble {
  position: absolute;
  bottom: calc(100% - 4px);
  left: 50%;
  transform: translateX(-50%);
  z-index: 5;
  animation: ss-bubble-in 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.ssa__bubble-text {
  display: block;
  max-width: 140px;
  padding: 6px 10px;
  border-radius: 12px 12px 12px 4px;
  background: #fff;
  color: #1f2937;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.3;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.18);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ssa--thinking,
.ssa--working,
.ssa--tool_file,
.ssa--tool_web {
  animation: ss-bob 2s ease-in-out infinite;
}
.ssa--blocked {
  animation: ss-shake 2.5s ease-in-out infinite;
}
.ssa--done {
  animation: ss-celebrate 0.6s ease;
}

.ss__lounge {
  position: absolute;
  left: 16px;
  bottom: 14px;
  z-index: 6;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(255, 255, 255, 0.12);
}
.ss__lounge-label {
  font-size: 10px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.7);
  margin-right: 4px;
}
.ss__lounge-item {
  cursor: pointer;
  transition: transform 0.12s;
}
.ss__lounge-item:hover {
  transform: scale(1.15);
}

/* Detail */
.ss__detail {
  width: 280px;
  flex-shrink: 0;
  border-left: 1px solid var(--color-border);
  background: var(--color-surface-container-lowest, #fff);
  padding: 16px;
  overflow-y: auto;
}
.ss__detail-title {
  margin: 0 0 14px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
}
.ss__detail-empty {
  text-align: center;
  padding: 32px 8px;
  color: var(--color-text-secondary);
  font-size: 13px;
}
.ss__detail-empty-art {
  display: flex;
  justify-content: center;
  margin-bottom: 12px;
  opacity: 0.85;
  animation: ss-bob 3s ease-in-out infinite;
}
.ss__detail-muted {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 4px;
}
.ss__detail-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  border-radius: 14px;
  border: 1px solid color-mix(in srgb, var(--c, #7c3aed) 25%, var(--color-border));
  background: linear-gradient(
    160deg,
    color-mix(in srgb, var(--c, #7c3aed) 10%, transparent),
    transparent 60%
  );
}
.ss__detail-head {
  display: flex;
  gap: 12px;
  align-items: center;
}
.ss__detail-avatar {
  filter: drop-shadow(0 4px 12px color-mix(in srgb, var(--c) 40%, transparent));
}
.ss__detail-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--c, #7c3aed);
}
.ss__detail-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.ss__pill {
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 700;
  font-size: 10px;
  background: var(--color-surface-container-low, #f3f4f6);
  color: var(--color-text-secondary);
}
.ss__pill[data-pose='thinking'],
.ss__pill[data-pose='working'],
.ss__pill[data-pose='tool_file'],
.ss__pill[data-pose='tool_web'] {
  background: #dcfce7;
  color: #166534;
}
.ss__pill[data-pose='blocked'] {
  background: #fef3c7;
  color: #92400e;
}
.ss__pill[data-pose='error'] {
  background: #fee2e2;
  color: #991b1b;
}
.ss__detail-bubble {
  font-size: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--color-surface-container-low, #f3f4f6);
  color: var(--color-text-secondary);
  line-height: 1.4;
}
.ss__detail-stream-label {
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
}
.ss__detail-text {
  margin: 0;
  max-height: 200px;
  overflow: auto;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--color-border);
  background: var(--color-surface, #fff);
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.ss__detail-wait {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  border: 1px dashed var(--color-border);
}
.ss__detail-dots {
  display: flex;
  gap: 5px;
}
.ss__detail-dots i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--color-brand, #7c3aed);
  display: block;
  animation: ss-dot 1s ease infinite;
}
.ss__detail-dots i:nth-child(2) {
  animation-delay: 0.15s;
}
.ss__detail-dots i:nth-child(3) {
  animation-delay: 0.3s;
}
.ss__detail-note {
  margin: 0;
  font-size: 10px;
  color: var(--color-text-tertiary);
  line-height: 1.4;
}

@keyframes ss-live {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.5);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(34, 197, 94, 0);
  }
}
@keyframes ss-bob {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-5px);
  }
}
@keyframes ss-float {
  0% {
    transform: translateY(0) scale(1);
    opacity: 0;
  }
  10% {
    opacity: 0.5;
  }
  90% {
    opacity: 0.2;
  }
  100% {
    transform: translateY(-110vh) scale(0.6);
    opacity: 0;
  }
}
@keyframes ss-glow {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.7;
  }
  50% {
    transform: scale(1.15);
    opacity: 1;
  }
}
@keyframes ss-pulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.25);
  }
}
@keyframes ss-ring {
  0% {
    transform: scale(0.9);
    opacity: 0.6;
  }
  100% {
    transform: scale(1.35);
    opacity: 0;
  }
}
@keyframes ss-bubble-in {
  from {
    opacity: 0;
    transform: translateX(-50%) translateY(6px) scale(0.9);
  }
  to {
    opacity: 1;
    transform: translateX(-50%) translateY(0) scale(1);
  }
}
@keyframes ss-shake {
  0%,
  100% {
    transform: rotate(0);
  }
  25% {
    transform: rotate(-3deg);
  }
  75% {
    transform: rotate(3deg);
  }
}
@keyframes ss-celebrate {
  0% {
    transform: scale(1);
  }
  40% {
    transform: scale(1.12);
  }
  100% {
    transform: scale(1);
  }
}
@keyframes ss-room-in {
  from {
    opacity: 0;
    transform: scale(1.03);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
@keyframes ss-dot {
  0%,
  100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  50% {
    opacity: 1;
    transform: translateY(-3px);
  }
}
</style>
