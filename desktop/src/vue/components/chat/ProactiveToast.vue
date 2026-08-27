<script setup lang="ts">
import { useTranslation } from '../../i18n'
const t = useTranslation()
/**
 * Sprint 5 — ProactiveToast: a bottom-right toast that surfaces a
 * proactive observation from the observer. Offers "采纳" (paste the
 * suggestion into the chat input) and "忽略" (dismiss).
 *
 * Mount once globally (e.g. in AppShell). It reads the shared
 * `proactiveObservation` ref from useProactive.
 */
import { computed } from 'vue'
import { proactiveObservation, useProactive } from '../../composables/useProactive'
import { useTabStore } from '../../stores/tabs'

const { dismiss, adoptInto } = useProactive()

const emit = defineEmits<{
  (e: 'adopt', suggestion: string): void
}>()

const tabStore = useTabStore()

const sourceIcon = computed(() =>
  proactiveObservation.value?.source === 'terminal' ? 'terminal' : 'edit_note',
)
const sourceLabel = computed(() =>
  proactiveObservation.value?.source === 'terminal' ? '终端' : '文件',
)

function onAdopt() {
  const suggestion = adoptInto('')
  if (suggestion) emit('adopt', suggestion)
  dismiss()
}
</script>

<template>
  <Teleport to="body">
    <Transition name="pt-slide">
      <div
        v-if="proactiveObservation"
        class="pt-toast"
        role="alert"
        aria-live="assertive"
      >
        <div class="pt-head">
          <span class="material-symbols-outlined pt-icon">{{ sourceIcon }}</span>
          <span class="pt-source">{{ sourceLabel }}观察</span>
          <button class="pt-x" @click="dismiss" aria-label="忽略">
            <span class="material-symbols-outlined">close</span>
          </button>
        </div>
        <p class="pt-summary">{{ proactiveObservation.summary }}</p>
        <p v-if="proactiveObservation.suggestion" class="pt-suggestion">
          {{ proactiveObservation.suggestion }}
        </p>
        <div class="pt-actions">
          <button class="pt-btn pt-btn--ghost" @click="dismiss">{{ t('common.dismiss', '忽略') }}</button>
          <!-- P2-6 — only offer "采纳" when there's a concrete suggestion;
               otherwise the button would silently no-op. -->
          <button
            v-if="proactiveObservation.suggestion"
            class="pt-btn pt-btn--primary"
            @click="onAdopt"
          >
            <span class="material-symbols-outlined">north_east</span>
            {{ t('proactive.adopt', '采纳') }}
          </button>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.pt-toast {
  position: fixed;
  right: 20px;
  bottom: 20px;
  z-index: 200;
  width: min(360px, 90vw);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-left: 3px solid var(--color-warning, #d97706);
  border-radius: 10px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.18);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.pt-head {
  display: flex;
  align-items: center;
  gap: 6px;
}
.pt-icon {
  font-size: 18px;
  color: var(--color-warning, #d97706);
}
.pt-source {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--color-text-tertiary);
}
.pt-x {
  margin-left: auto;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-text-tertiary);
  border-radius: 5px;
}
.pt-x:hover {
  background: var(--color-surface-container);
  color: var(--color-text-primary);
}
.pt-x .material-symbols-outlined {
  font-size: 16px;
}
.pt-summary {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--color-text-primary);
  line-height: 1.4;
}
.pt-suggestion {
  margin: 0;
  font-size: 12.5px;
  color: var(--color-text-secondary);
  line-height: 1.5;
}
.pt-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
  margin-top: 2px;
}
.pt-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 12px;
  font-size: 12.5px;
  font-weight: 500;
  border-radius: 6px;
  cursor: pointer;
  font-family: inherit;
  transition: background 120ms;
}
.pt-btn .material-symbols-outlined {
  font-size: 14px;
}
.pt-btn--ghost {
  background: transparent;
  border: 1px solid var(--color-border);
  color: var(--color-text-secondary);
}
.pt-btn--ghost:hover {
  background: var(--color-surface-container);
}
.pt-btn--primary {
  background: var(--color-brand, #0a0a0a);
  border: 1px solid var(--color-brand, #0a0a0a);
  color: #fff;
}
.pt-btn--primary:hover {
  background: #1f2937;
}

.pt-slide-enter-active,
.pt-slide-leave-active {
  transition: transform 260ms cubic-bezier(0.22, 1, 0.36, 1), opacity 200ms;
}
.pt-slide-enter-from,
.pt-slide-leave-to {
  transform: translateY(20px);
  opacity: 0;
}
</style>
