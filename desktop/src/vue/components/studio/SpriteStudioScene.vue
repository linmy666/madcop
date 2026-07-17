<script setup lang="ts">
/**
 * P1–P3 Sprite Studio scene — stations + bubbles + skins + selection detail.
 * Consumes the same SpriteAgent roster as SpriteIsland (no demo roster).
 */
import { ref, computed, watch } from 'vue'
import MascotAvatar from '../common/MascotAvatar.vue'
import {
  type SpriteAgent,
  type SpriteDetail,
  type StudioSkinId,
  STUDIO_SKINS,
  ROLE_META,
  poseLabel,
  selectSpriteDetail,
  loadStudioSkin,
  saveStudioSkin,
} from '../../lib/spriteStudio'

const props = defineProps<{
  roster: SpriteAgent[]
  /** Optional route banner from deepRoute */
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

/** Fixed stations laid out on the floor plan */
const stations = computed(() => {
  const order = ['planner', 'coder', 'designer', 'researcher', 'reviewer', 'synthesizer', 'general']
  return order.map((st, i) => {
    const meta = ROLE_META[st] || ROLE_META.general
    const agents = props.roster.filter((a) => a.station === st || a.role === st)
    // Layout: 3 columns × rows
    const col = i % 3
    const row = Math.floor(i / 3)
    return {
      id: st,
      label: meta.label,
      color: meta.color,
      agents,
      style: {
        left: `${12 + col * 30}%`,
        top: `${18 + row * 34}%`,
      },
    }
  })
})

const loungeAgents = computed(() =>
  props.roster.filter((a) => a.pose === 'idle' || a.pose === 'done'),
)

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
        <h2 class="ss__title">精灵工作室</h2>
        <p class="ss__sub">
          {{ routeLabel || '多 Agent 可视化工位' }}
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
          {{ s.label }}
        </button>
      </div>
    </header>

    <div class="ss__body">
      <div class="ss__floor">
        <!-- Decor zones -->
        <div class="ss__zone ss__zone--board">
          <span class="material-symbols-outlined">dashboard</span>
          白板
        </div>
        <div class="ss__zone ss__zone--tools">
          <span class="material-symbols-outlined">handyman</span>
          工具墙
        </div>
        <div class="ss__zone ss__zone--cafe">
          <span class="material-symbols-outlined">coffee</span>
          咖啡角
          <div class="ss__lounge">
            <MascotAvatar
              v-for="a in loungeAgents.slice(0, 3)"
              :key="'lounge-' + a.id"
              :size="20"
              :color="a.color"
            />
          </div>
        </div>

        <div
          v-for="st in stations"
          :key="st.id"
          class="ss-desk"
          :style="st.style"
        >
          <div class="ss-desk__plate" :style="{ borderColor: st.color + '55' }">
            <span class="ss-desk__label" :style="{ color: st.color }">{{ st.label }}</span>
            <div v-if="st.agents.length === 0" class="ss-desk__empty">空位</div>
            <button
              v-for="a in st.agents"
              :key="a.id"
              type="button"
              class="ss-agent"
              :class="[
                `ss-agent--${a.pose}`,
                { 'ss-agent--selected': selectedId === a.id },
              ]"
              @click="onSelect(a.id)"
            >
              <MascotAvatar :size="36" :color="a.color" />
              <span v-if="a.bubble" class="ss-agent__bubble">{{ a.bubble }}</span>
              <span class="ss-agent__name">{{ a.name }}</span>
              <span class="ss-agent__pose">{{ poseLabel(a.pose) }}</span>
            </button>
          </div>
        </div>

        <div v-if="roster.length === 0" class="ss__empty">
          <MascotAvatar :size="48" color="#7C3AED" />
          <p>当前没有活跃的多 Agent 任务</p>
          <p class="ss__empty-hint">在会话里用「深度」模式跑一轮，精灵会坐到对应工位</p>
        </div>
      </div>

      <!-- P2 detail pane -->
      <aside class="ss__detail">
        <h3 class="ss__detail-title">精灵详情</h3>
        <div v-if="!detail" class="ss__detail-empty">
          点击工位上的精灵，查看其输出流（与会话 agentStreams 同源）
        </div>
        <div v-else class="ss__detail-card">
          <div class="ss__detail-head">
            <MascotAvatar :size="40" :color="detail.color" />
            <div>
              <div class="ss__detail-name" :style="{ color: detail.color }">{{ detail.name }}</div>
              <div class="ss__detail-meta">
                {{ poseLabel(detail.pose) }} · {{ detail.status }}
                <span v-if="detail.elapsed_ms"> · {{ Math.round(detail.elapsed_ms / 1000) }}s</span>
              </div>
            </div>
          </div>
          <div v-if="detail.bubble" class="ss__detail-bubble">{{ detail.bubble }}</div>
          <div class="ss__detail-stream">
            <div class="ss__detail-stream-label">
              {{ detail.hasStream ? '实时输出' : '暂无文本（可能尚未开始）' }}
            </div>
            <pre v-if="detail.text" class="ss__detail-text">{{ detail.text }}</pre>
            <p v-else class="ss__detail-empty">—</p>
          </div>
          <p class="ss__detail-note">
            选择仅聚焦展示，不会改写服务端路由（无拖拽指派 API）。
          </p>
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
  min-height: 420px;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
}
.ss--studio {
  --ss-floor: #e8ecf4;
  --ss-desk: #ffffff;
  --ss-accent: #7c3aed;
}
.ss--study {
  --ss-floor: #f0e6d4;
  --ss-desk: #fffaf0;
  --ss-accent: #b45309;
}
.ss--cabin {
  --ss-floor: #dfead8;
  --ss-desk: #f4faf0;
  --ss-accent: #15803d;
}
.ss__top {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-container-lowest, #fff);
  flex-shrink: 0;
}
.ss__title {
  margin: 0;
  font-size: 16px;
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
.ss__skins {
  display: flex;
  gap: 4px;
  padding: 3px;
  background: var(--color-surface-container-low, #f3f4f6);
  border-radius: 10px;
}
.ss__skin {
  border: none;
  background: transparent;
  padding: 6px 10px;
  border-radius: 8px;
  font-size: 12px;
  cursor: pointer;
  color: var(--color-text-secondary);
}
.ss__skin--on {
  background: var(--color-surface, #fff);
  color: var(--ss-accent, #7c3aed);
  font-weight: 600;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.06);
}
.ss__body {
  flex: 1;
  min-height: 0;
  display: flex;
  overflow: hidden;
}
.ss__floor {
  flex: 1;
  min-width: 0;
  position: relative;
  background:
    radial-gradient(circle at 1px 1px, rgba(0, 0, 0, 0.05) 1px, transparent 0) 0 0 / 18px 18px,
    var(--ss-floor);
  overflow: hidden;
}
.ss__zone {
  position: absolute;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 10px;
  font-weight: 600;
  color: var(--color-text-tertiary);
  padding: 4px 8px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--ss-desk) 80%, transparent);
  border: 1px dashed color-mix(in srgb, var(--ss-accent) 30%, transparent);
}
.ss__zone .material-symbols-outlined {
  font-size: 14px;
}
.ss__zone--board {
  top: 8px;
  left: 50%;
  transform: translateX(-50%);
}
.ss__zone--tools {
  top: 40%;
  right: 8px;
  writing-mode: vertical-rl;
}
.ss__zone--cafe {
  bottom: 10px;
  left: 12px;
  flex-direction: column;
  align-items: flex-start;
}
.ss__lounge {
  display: flex;
  gap: 2px;
  margin-top: 4px;
}
.ss-desk {
  position: absolute;
  width: 28%;
  transform: translate(-50%, -50%);
}
.ss-desk__plate {
  background: var(--ss-desk);
  border: 1.5px solid var(--color-border);
  border-radius: 12px;
  padding: 8px;
  min-height: 88px;
  box-shadow: 0 6px 16px rgba(15, 23, 42, 0.08);
}
.ss-desk__label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.ss-desk__empty {
  margin-top: 10px;
  font-size: 11px;
  color: var(--color-text-tertiary);
  text-align: center;
}
.ss-agent {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 100%;
  margin-top: 6px;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  padding: 6px 4px;
}
.ss-agent:hover,
.ss-agent--selected {
  background: color-mix(in srgb, var(--ss-accent) 8%, transparent);
  border-color: color-mix(in srgb, var(--ss-accent) 30%, transparent);
}
.ss-agent--thinking,
.ss-agent--working,
.ss-agent--tool_file,
.ss-agent--tool_web {
  animation: ss-bob 2s ease-in-out infinite;
}
.ss-agent__bubble {
  position: absolute;
  top: -6px;
  left: 50%;
  transform: translate(-50%, -100%);
  max-width: 140px;
  padding: 4px 8px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid var(--color-border);
  font-size: 10px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.08);
  z-index: 2;
}
.ss-agent__name {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-primary);
}
.ss-agent__pose {
  font-size: 10px;
  color: var(--color-text-tertiary);
}
.ss__empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  color: var(--color-text-secondary);
  font-size: 13px;
  pointer-events: none;
}
.ss__empty-hint {
  margin: 0;
  font-size: 11px;
  color: var(--color-text-tertiary);
}
.ss__detail {
  width: 280px;
  flex-shrink: 0;
  border-left: 1px solid var(--color-border);
  background: var(--color-surface-container-lowest, #fff);
  padding: 14px;
  overflow-y: auto;
}
.ss__detail-title {
  margin: 0 0 12px;
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--color-text-tertiary);
}
.ss__detail-empty {
  font-size: 12px;
  color: var(--color-text-tertiary);
  line-height: 1.5;
}
.ss__detail-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ss__detail-head {
  display: flex;
  gap: 10px;
  align-items: center;
}
.ss__detail-name {
  font-size: 14px;
  font-weight: 700;
}
.ss__detail-meta {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
}
.ss__detail-bubble {
  font-size: 12px;
  padding: 8px 10px;
  border-radius: 8px;
  background: var(--color-surface-container-low, #f3f4f6);
  color: var(--color-text-secondary);
}
.ss__detail-stream-label {
  font-size: 10px;
  font-weight: 700;
  color: var(--color-text-tertiary);
  margin-bottom: 6px;
}
.ss__detail-text {
  margin: 0;
  max-height: 220px;
  overflow: auto;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-surface, #fff);
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  color: var(--color-text-primary);
}
.ss__detail-note {
  margin: 0;
  font-size: 10px;
  color: var(--color-text-tertiary);
  line-height: 1.4;
}
@keyframes ss-bob {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-3px);
  }
}
</style>
