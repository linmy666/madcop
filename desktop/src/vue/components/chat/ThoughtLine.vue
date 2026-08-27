<script setup lang="ts">
/**
 * ThoughtLine — ZCode-style collapsed thinking phase:
 *   🧠 思考过程 · 持续了 42 秒   (click expands the reasoning text)
 * Pending state shows a soft pulsing brain + '思考中…' instead of a spinner.
 */
import { computed, ref } from 'vue'
import { useTranslation } from '../../i18n'

const props = withDefaults(defineProps<{
  pending?: boolean
  elapsedMs?: number
  text?: string
}>(), { pending: false, elapsedMs: undefined, text: '' })

const t = useTranslation()
const open = ref(false)

const durationLabel = computed(() => {
  if (!props.elapsedMs && props.pending) return ''
  const s = Math.max(1, Math.round((props.elapsedMs || 0) / 1000))
  return s >= 60 ? `${Math.floor(s / 60)} 分 ${s % 60} 秒` : `${s} 秒`
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
      <span v-if="pending" class="tline__live">{{ t('chat.thinkingNow', '思考中…') }}</span>
      <span v-else-if="durationLabel" class="tline__meta">· {{ t('chat.lasted', '持续了') }} {{ durationLabel }}</span>
      <svg class="tline__chev" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
        <polyline v-if="!open" points="6 9 12 15 18 9" />
        <polyline v-else points="6 15 12 9 18 15" />
      </svg>
    </button>
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
@media (prefers-reduced-motion: reduce) {
  .tline--pending .tline__icon,
  .tline__live { animation: none; }
}
</style>

__zcode_status=$?
if [ "$__zcode_status" -eq 0 ]; then pwd -P > '/var/folders/lh/jp2j6wyd1q3bjqvqy58vlb500000gn/T/zcode-8cde69af-3678-4632-b6be-9594fb57f214-cwd'; fi
exit "$__zcode_status"