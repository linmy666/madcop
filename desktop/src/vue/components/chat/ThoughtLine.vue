<script setup lang="ts">
/**
 * ThoughtLine — the thinking capsule (product spec v2):
 *   pending:  ◉ 思考中 · 8s
 *             └ 最近一句思考实时预览（单行截断，真实 thought_delta 驱动）
 *             ↳ click expands the full reasoning text
 *   done:     🧠 思考过程 · 持续了 42 秒  (collapsed, expandable)
 *
 * The "animation" is the REAL streaming reasoning text updating the
 * preview line — no decorative motion (matrix-rain etc. explicitly
 * rejected in the frontend presentation spec).
 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useTranslation } from '../../i18n'

const props = withDefaults(defineProps<{
  pending?: boolean
  elapsedMs?: number
  text?: string
}>(), { pending: false, elapsedMs: undefined, text: '' })

const t = useTranslation()
const open = ref(false)

// Live elapsed clock while pending (no real number → no display, per
// the "no fake indicators" rule; the tick starts when the capsule
// mounts in pending state, which is when the block started arriving).
const tick = ref(0)
let timer: ReturnType<typeof setInterval> | null = null
watch(
  () => props.pending,
  (p) => {
    if (p && !timer) {
      timer = setInterval(() => { tick.value++ }, 1000)
    } else if (!p && timer) {
      clearInterval(timer)
      timer = null
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => { if (timer) clearInterval(timer) })

const elapsedLabel = computed(() => {
  if (!props.pending) return ''
  void tick.value // re-evaluate on tick
  const s = Math.max(1, Math.round((props.elapsedMs || 0) / 1000) + tick.value)
  return s >= 60 ? `${Math.floor(s / 60)} 分 ${s % 60} 秒` : `${s} 秒`
})

const durationLabel = computed(() => {
  if (!props.elapsedMs && props.pending) return elapsedLabel.value
  const s = Math.max(1, Math.round((props.elapsedMs || 0) / 1000))
  return s >= 60 ? `${Math.floor(s / 60)} 分 ${s % 60} 秒` : `${s} 秒`
})

// Real-data preview: the LAST non-empty line of the live reasoning
// buffer, single-line truncated. This is what makes the capsule feel
// alive — it updates as thought_delta chunks arrive.
const previewLine = computed(() => {
  if (!props.pending) return ''
  const lines = (props.text || '').split('\n').map(l => l.trim()).filter(Boolean)
  const last = lines[lines.length - 1] || ''
  return last.length > 90 ? last.slice(0, 90) + '…' : last
})
</script>

<template>
  <div class="tline" :class="{ 'tline--pending': pending }" data-testid="thought-line">
    <button type="button" class="tline__head" :aria-expanded="open" @click="open = !open">
      <span class="tline__icon" aria-hidden="true">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z" />
          <path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z" />
          <path d="M12 5v13" />
        </svg>
      </span>
      <span class="tline__label">{{ t('chat.thinkingProcess', '思考过程') }}</span>
      <span v-if="pending" class="tline__live">{{ t('chat.thinkingNow', '思考中') }}</span>
      <span v-if="pending && elapsedLabel" class="tline__meta">· {{ elapsedLabel }}</span>
      <span v-else-if="!pending && durationLabel" class="tline__meta">· {{ t('chat.lasted', '持续了') }} {{ durationLabel }}</span>
      <svg class="tline__chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
        <polyline v-if="!open" points="6 9 12 15 18 9" />
        <polyline v-else points="6 15 12 9 18 15" />
      </svg>
    </button>
    <div v-if="pending && previewLine" class="tline__preview" aria-live="polite">{{ previewLine }}</div>
    <pre v-if="open && text" class="tline__body">{{ text }}</pre>
  </div>
</template>

<style scoped>
.tline {
  margin: 6px 0;
}
.tline__head {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 100%;
  padding: 4px 2px;
  background: transparent;
  border: 0;
  cursor: pointer;
  font-size: 13px;
  color: var(--color-text-tertiary);
  font-family: inherit;
  text-align: left;
}
.tline--pending .tline__icon {
  color: var(--color-primary, #7c5cff);
  animation: tline-pulse 1.6s ease-in-out infinite;
}
.tline__label { font-weight: 600; color: var(--color-text-secondary); }
.tline__live {
  color: var(--color-primary, #7c5cff);
  animation: tline-pulse 1.6s ease-in-out infinite;
}
.tline__meta { font-variant-numeric: tabular-nums; }
.tline__chev { flex-shrink: 0; }
.tline__preview {
  margin: 2px 0 2px 21px;
  padding: 2px 0 2px 10px;
  border-left: 2px solid var(--color-border);
  font-size: 12px;
  line-height: 1.5;
  color: var(--color-text-tertiary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  /* The "scrolling" feel: latest line fades in as the buffer grows. */
  animation: tline-preview-in 240ms ease-out;
}
.tline__body {
  margin: 4px 0 0 21px;
  padding: 8px 10px;
  border-left: 2px solid var(--color-border);
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.6;
  color: var(--color-text-secondary);
  max-height: 320px;
  overflow: auto;
}
@keyframes tline-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.45; }
}
@keyframes tline-preview-in {
  from { opacity: 0.35; }
  to { opacity: 1; }
}
@media (prefers-reduced-motion: reduce) {
  .tline--pending .tline__icon,
  .tline__live { animation: none; }
  .tline__preview { animation: none; }
}
</style>
