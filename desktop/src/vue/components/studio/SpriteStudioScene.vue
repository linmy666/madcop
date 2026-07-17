<script setup lang="ts">
/**
 * Sprite Studio — pixel-aligned furniture seats + walk paths + itch-style frames.
 */
import { ref, computed, watch } from 'vue'
import MascotAvatar from '../common/MascotAvatar.vue'
import SpriteWalker from './SpriteWalker.vue'
import {
  type SpriteAgent,
  type SpriteDetail,
  type StudioSkinId,
  STUDIO_SKINS,
  selectSpriteDetail,
  loadStudioSkin,
  saveStudioSkin,
} from '../../lib/spriteStudio'
import { STATION_SPOTS } from '../../lib/spriteSceneLayout'
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
const usePixelWalk = ref(true)

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

/** Agents rendered as independent walkers (not stacked empty desks). */
const walkers = computed(() =>
  props.roster.map((a) => ({
    ...a,
    station: a.station || a.role || 'general',
  })),
)

/** Optional desk glow markers — only for stations currently occupied */
const litDesks = computed(() => {
  const ids = new Set(walkers.value.map((a) => a.station))
  return Object.values(STATION_SPOTS)
    .filter((s) => ids.has(s.id) && s.id !== 'door' && s.id !== 'lounge')
    .map((s) => ({
      id: s.id,
      label: s.label,
      style: { left: `${s.x}%`, top: `${s.y}%` },
    }))
})

const isEmpty = computed(() => props.roster.length === 0)

function onSelect(id: string) {
  selectedId.value = id
  emit('select', id)
}

function setSkin(id: StudioSkinId) {
  skin.value = id
}
</script>

<template>
  <div class="ss" :class="`ss--${skin}`">
    <header class="ss__top">
      <div class="ss__heading">
        <div v-if="!isEmpty" class="ss__live">
          <span class="ss__live-dot" />
          LIVE
        </div>
        <h2 class="ss__title">精灵工作室</h2>
        <p class="ss__sub">
          {{ routeLabel || '多 Agent 场景舞台' }}
          <span v-if="routeReason" class="ss__reason"> · {{ routeReason }}</span>
        </p>
      </div>
      <div class="ss__controls">
        <label class="ss__toggle" title="行走时使用像素步帧（itch 风格）">
          <input v-model="usePixelWalk" type="checkbox" />
          <span>像素步帧</span>
        </label>
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
      </div>
    </header>

    <div class="ss__body">
      <!-- Fixed aspect stage so % coords map 1:1 to SVG viewBox 1200×700 -->
      <div class="ss__viewport">
        <div class="ss__stage">
          <img class="ss__room" :src="roomSrc" :alt="skin + ' room'" draggable="false" />

          <!-- Soft desk highlight under occupied seats (pixel-aligned) -->
          <div
            v-for="d in litDesks"
            :key="'desk-' + d.id"
            class="ss__desk-glow"
            :style="d.style"
          >
            <span class="ss__desk-tag">{{ d.label }}</span>
          </div>

          <!-- Ambient particles -->
          <div class="ss__particles" aria-hidden="true">
            <span v-for="n in 14" :key="n" class="ss__p" :style="{ '--i': n }" />
          </div>

          <!-- Empty hero -->
          <div v-if="isEmpty" class="ss__hero">
            <div class="ss__hero-glow" />
            <div class="ss__hero-mascot">
              <MascotAvatar :size="72" color="#7C3AED" />
            </div>
            <h3 class="ss__hero-title">工作室暂未开工</h3>
            <p class="ss__hero-sub">深度模式启动后，精灵会从门口走到工位</p>
          </div>

          <!-- Walkers -->
          <SpriteWalker
            v-for="a in walkers"
            :key="a.id"
            :id="a.id"
            :name="a.name"
            :color="a.color"
            :pose="a.pose"
            :station="a.station"
            :bubble="a.bubble"
            :selected="selectedId === a.id"
            :use-pixel-sheet="usePixelWalk"
            @select="onSelect"
          />
        </div>
      </div>

      <aside class="ss__detail">
        <h3 class="ss__detail-title">精灵档案</h3>
        <div v-if="!detail" class="ss__detail-empty">
          <MascotAvatar :size="40" color="#7C3AED" />
          <p>点选正在走路或工作的精灵</p>
          <p class="ss__detail-muted">工位坐标与房间家具像素对齐</p>
        </div>
        <div v-else class="ss__detail-card" :style="{ '--c': detail.color }">
          <div class="ss__detail-head">
            <MascotAvatar :size="48" :color="detail.color" />
            <div>
              <div class="ss__detail-name">{{ detail.name }}</div>
              <div class="ss__detail-meta">{{ detail.pose }} · {{ detail.status }}</div>
            </div>
          </div>
          <div v-if="detail.bubble" class="ss__detail-bubble">{{ detail.bubble }}</div>
          <pre v-if="detail.text" class="ss__detail-text">{{ detail.text }}</pre>
          <p v-else class="ss__detail-muted">等待输出…</p>
          <p class="ss__detail-note">选择仅聚焦；不会改写服务端路由。</p>
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
  padding: 12px 16px;
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
  margin-bottom: 2px;
}
.ss__live-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22c55e;
  animation: ss-live 1.6s ease infinite;
}
.ss__title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
}
.ss__sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--color-text-secondary);
}
.ss__reason {
  color: var(--color-text-tertiary);
}
.ss__controls {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}
.ss__toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--color-text-secondary);
  cursor: pointer;
  user-select: none;
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
  width: 52px;
  height: 34px;
  border-radius: 8px;
}
.ss__skin-thumb[data-skin='studio'] {
  background: linear-gradient(145deg, #2a2540, #7c3aed);
}
.ss__skin-thumb[data-skin='study'] {
  background: linear-gradient(145deg, #f5e6c8, #b45309);
}
.ss__skin-thumb[data-skin='cabin'] {
  background: linear-gradient(145deg, #3d5c3a, #86efac 70%, #fbbf24);
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
.ss__viewport {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #0f0c18;
  overflow: auto;
  padding: 12px;
}
/* Critical: fixed aspect so % seats = SVG furniture pixels */
.ss__stage {
  position: relative;
  width: min(100%, calc((100vh - 220px) * 1200 / 700));
  max-width: 100%;
  aspect-ratio: 1200 / 700;
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 16px 48px rgba(0, 0, 0, 0.35);
  flex-shrink: 0;
}
.ss__room {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: fill; /* 1:1 with viewBox when stage aspect is locked */
  user-select: none;
  pointer-events: none;
  image-rendering: auto;
}
.ss__desk-glow {
  position: absolute;
  transform: translate(-50%, -20%);
  width: 88px;
  height: 36px;
  border-radius: 50%;
  background: radial-gradient(ellipse, rgba(167, 139, 250, 0.35), transparent 70%);
  pointer-events: none;
  z-index: 1;
  animation: ss-desk 2.4s ease-in-out infinite;
}
.ss__desk-tag {
  position: absolute;
  left: 50%;
  top: -14px;
  transform: translateX(-50%);
  font-size: 9px;
  font-weight: 800;
  letter-spacing: 0.06em;
  color: rgba(255, 255, 255, 0.75);
  text-shadow: 0 1px 3px #000;
  white-space: nowrap;
}
.ss__particles {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 2;
}
.ss__p {
  position: absolute;
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.5);
  left: calc(7% * var(--i));
  bottom: -8%;
  animation: ss-float calc(9s + var(--i) * 0.35s) linear infinite;
  animation-delay: calc(var(--i) * -0.6s);
}

.ss__hero {
  position: absolute;
  inset: 0;
  z-index: 5;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  background: radial-gradient(ellipse at 50% 45%, rgba(0, 0, 0, 0.2), rgba(0, 0, 0, 0.5));
  color: #fff;
}
.ss__hero-glow {
  position: absolute;
  width: 180px;
  height: 180px;
  border-radius: 50%;
  background: radial-gradient(circle, rgba(124, 58, 237, 0.45), transparent 70%);
  animation: ss-glow 3s ease-in-out infinite;
}
.ss__hero-mascot {
  position: relative;
  animation: ss-bob 2.4s ease-in-out infinite;
}
.ss__hero-title {
  position: relative;
  margin: 14px 0 6px;
  font-size: 17px;
  font-weight: 700;
}
.ss__hero-sub {
  position: relative;
  margin: 0;
  font-size: 12px;
  color: rgba(255, 255, 255, 0.78);
}

.ss__detail {
  width: 270px;
  flex-shrink: 0;
  border-left: 1px solid var(--color-border);
  background: var(--color-surface-container-lowest, #fff);
  padding: 14px;
  overflow-y: auto;
}
.ss__detail-title {
  margin: 0 0 12px;
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-tertiary);
}
.ss__detail-empty {
  text-align: center;
  padding: 28px 8px;
  font-size: 13px;
  color: var(--color-text-secondary);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.ss__detail-muted {
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.ss__detail-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
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
  gap: 10px;
  align-items: center;
}
.ss__detail-name {
  font-size: 15px;
  font-weight: 700;
  color: var(--c, #7c3aed);
}
.ss__detail-meta {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
}
.ss__detail-bubble {
  font-size: 12px;
  padding: 8px 10px;
  border-radius: 10px;
  background: var(--color-surface-container-low, #f3f4f6);
}
.ss__detail-text {
  margin: 0;
  max-height: 180px;
  overflow: auto;
  padding: 10px;
  border-radius: 10px;
  border: 1px solid var(--color-border);
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}
.ss__detail-note {
  margin: 0;
  font-size: 10px;
  color: var(--color-text-tertiary);
}

@keyframes ss-live {
  0%,
  100% {
    box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.45);
  }
  50% {
    box-shadow: 0 0 0 6px rgba(34, 197, 94, 0);
  }
}
@keyframes ss-float {
  0% {
    transform: translateY(0);
    opacity: 0;
  }
  12% {
    opacity: 0.5;
  }
  100% {
    transform: translateY(-110%);
    opacity: 0;
  }
}
@keyframes ss-desk {
  0%,
  100% {
    opacity: 0.55;
  }
  50% {
    opacity: 1;
  }
}
@keyframes ss-glow {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.12);
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
</style>
