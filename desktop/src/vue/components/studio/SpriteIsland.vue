<script setup lang="ts">
/**
 * P0 Sprite Island — compact dock of tinted mascots bound to session roster.
 */
import { ref, computed, watch } from 'vue'
import MascotAvatar from '../common/MascotAvatar.vue'
import {
  type SpriteAgent,
  type SpriteDetail,
  type StudioSkinId,
  poseLabel,
  loadIslandCollapsed,
  saveIslandCollapsed,
  loadIslandEnabled,
  saveIslandEnabled,
  loadStudioSkin,
  saveAgentHubView,
} from '../../lib/spriteStudio'
import { useTabStore } from '../../stores/tabs'

const props = defineProps<{
  roster: SpriteAgent[]
  selectedId?: string | null
  /** Show even when roster empty as a calm idle tip (default false) */
  forceShow?: boolean
}>()

const emit = defineEmits<{
  select: [id: string]
  openStudio: []
}>()

const enabled = ref(loadIslandEnabled())
const collapsed = ref(loadIslandCollapsed())
const skin = ref<StudioSkinId>(loadStudioSkin())

const visible = computed(() => {
  if (!enabled.value) return false
  if (props.forceShow) return true
  return props.roster.length > 0
})

watch(collapsed, (v) => saveIslandCollapsed(v))

function toggleCollapsed() {
  collapsed.value = !collapsed.value
}

function turnOff() {
  enabled.value = false
  saveIslandEnabled(false)
}

function turnOn() {
  enabled.value = true
  saveIslandEnabled(true)
}

function onSelect(id: string) {
  emit('select', id)
}

function openStudio() {
  saveAgentHubView('studio')
  try {
    useTabStore().openAgentHubTab()
  } catch {
    /* optional */
  }
  emit('openStudio')
}

function poseClass(pose: SpriteAgent['pose']): string {
  return `si-sprite--${pose}`
}
</script>

<template>
  <!-- Re-enable chip when user turned island off -->
  <button
    v-if="!enabled && roster.length > 0"
    type="button"
    class="si-reenable"
    @click="turnOn"
  >
    <span class="material-symbols-outlined" style="font-size: 14px">pets</span>
    显示精灵岛
  </button>

  <div
    v-else-if="visible"
    class="si"
    :class="[`si--skin-${skin}`, { 'si--collapsed': collapsed }]"
  >
    <header class="si__bar">
      <button type="button" class="si__toggle" @click="toggleCollapsed">
        <span class="material-symbols-outlined" style="font-size: 15px">hub</span>
        <span class="si__title">
          {{
            roster.some((r) => r.pose !== 'idle' && r.pose !== 'done')
              ? '精灵协作中'
              : roster.length
                ? '精灵工作室'
                : '精灵岛'
          }}
        </span>
        <span class="si__count">{{ roster.length }}</span>
        <span class="material-symbols-outlined si__chevron" style="font-size: 16px">
          {{ collapsed ? 'expand_more' : 'expand_less' }}
        </span>
      </button>
      <div class="si__actions">
        <button type="button" class="si__btn" title="打开工作室" @click="openStudio">
          工作室
        </button>
        <button type="button" class="si__btn si__btn--mute" title="关闭精灵岛" @click="turnOff">
          关闭
        </button>
      </div>
    </header>

    <div v-show="!collapsed" class="si__dock">
      <button
        v-for="s in roster"
        :key="s.id"
        type="button"
        class="si-sprite"
        :class="[poseClass(s.pose), { 'si-sprite--selected': selectedId === s.id }]"
        :title="`${s.name} · ${poseLabel(s.pose)}`"
        @click="onSelect(s.id)"
      >
        <div class="si-sprite__avatar" :style="{ boxShadow: `0 0 0 2px ${s.color}33` }">
          <MascotAvatar :size="28" :color="s.color" />
          <span class="si-sprite__dot" :data-pose="s.pose" />
        </div>
        <span class="si-sprite__name" :style="{ color: s.color }">{{ s.name }}</span>
        <span class="si-sprite__pose">{{ poseLabel(s.pose) }}</span>
        <span v-if="s.bubble" class="si-sprite__bubble">{{ s.bubble }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.si {
  margin: 10px 0 4px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface-container-lowest, #fff);
  overflow: hidden;
}
.si--skin-study {
  background: linear-gradient(180deg, #faf6ef 0%, var(--color-surface-container-lowest, #fff) 100%);
}
.si--skin-cabin {
  background: linear-gradient(180deg, #eef6ea 0%, var(--color-surface-container-lowest, #fff) 100%);
}
.si__bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px 4px 4px;
  background: var(--color-surface-container-low, #f3f4f6);
  border-bottom: 1px solid var(--color-border);
}
.si--collapsed .si__bar {
  border-bottom: none;
}
.si__toggle {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: transparent;
  cursor: pointer;
  padding: 6px 8px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-text-secondary);
  text-align: left;
  min-width: 0;
}
.si__toggle:hover {
  background: var(--color-surface-hover, rgba(0, 0, 0, 0.04));
}
.si__toggle .material-symbols-outlined {
  color: var(--color-brand, #7c3aed);
}
.si__title {
  flex: 0 1 auto;
}
.si__count {
  font-size: 10px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--color-brand, #7c3aed) 12%, transparent);
  color: var(--color-brand, #7c3aed);
}
.si__chevron {
  color: var(--color-text-tertiary) !important;
  margin-left: auto;
}
.si__actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.si__btn {
  border: 1px solid var(--color-border);
  background: var(--color-surface, #fff);
  border-radius: 8px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
  color: var(--color-text-secondary);
}
.si__btn:hover {
  border-color: var(--color-brand, #7c3aed);
  color: var(--color-brand, #7c3aed);
}
.si__btn--mute {
  opacity: 0.75;
}
.si__dock {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px;
}
.si-sprite {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 88px;
  padding: 8px 6px;
  border: 1px solid transparent;
  border-radius: 12px;
  background: transparent;
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s;
}
.si-sprite:hover {
  background: var(--color-surface-container-low, #f9fafb);
}
.si-sprite--selected {
  border-color: color-mix(in srgb, var(--color-brand, #7c3aed) 40%, transparent);
  background: color-mix(in srgb, var(--color-brand, #7c3aed) 8%, transparent);
}
.si-sprite__avatar {
  position: relative;
  border-radius: 50%;
  padding: 2px;
}
.si-sprite__dot {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1.5px solid #fff;
  background: #9ca3af;
}
.si-sprite__dot[data-pose='thinking'],
.si-sprite__dot[data-pose='working'],
.si-sprite__dot[data-pose='tool_file'],
.si-sprite__dot[data-pose='tool_web'] {
  background: #22c55e;
  animation: si-pulse 1.2s ease-in-out infinite;
}
.si-sprite__dot[data-pose='blocked'] {
  background: #f59e0b;
}
.si-sprite__dot[data-pose='done'] {
  background: #6366f1;
}
.si-sprite__dot[data-pose='error'] {
  background: #ef4444;
}
.si-sprite__name {
  font-size: 11px;
  font-weight: 600;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.si-sprite__pose {
  font-size: 10px;
  color: var(--color-text-tertiary);
}
.si-sprite__bubble {
  position: absolute;
  top: -2px;
  left: 50%;
  transform: translate(-50%, -100%);
  max-width: 120px;
  padding: 3px 6px;
  border-radius: 6px;
  background: var(--color-surface, #fff);
  border: 1px solid var(--color-border);
  font-size: 9px;
  color: var(--color-text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  pointer-events: none;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06);
  opacity: 0;
  transition: opacity 0.15s;
}
.si-sprite:hover .si-sprite__bubble,
.si-sprite--selected .si-sprite__bubble {
  opacity: 1;
}
.si-sprite--thinking .si-sprite__avatar,
.si-sprite--working .si-sprite__avatar {
  animation: si-bob 2s ease-in-out infinite;
}
.si-reenable {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin: 8px 0;
  border: 1px dashed var(--color-border);
  background: transparent;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
  color: var(--color-text-tertiary);
  cursor: pointer;
}
.si-reenable:hover {
  color: var(--color-brand, #7c3aed);
  border-color: var(--color-brand, #7c3aed);
}
@keyframes si-pulse {
  0%,
  100% {
    transform: scale(1);
    opacity: 1;
  }
  50% {
    transform: scale(1.25);
    opacity: 0.7;
  }
}
@keyframes si-bob {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-2px);
  }
}
</style>
