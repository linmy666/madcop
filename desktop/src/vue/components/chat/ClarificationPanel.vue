<script setup lang="ts">
// ClarificationPanel — renders an inline clarification card when the agent
// asks the user to choose between options (or supply free text). Reads
// clarificationPending from the chat store for the given session.
import { ref, computed } from 'vue'
import { useChatStore } from '../../stores/chatStore'

const props = defineProps<{ sessionId: string }>()
const chatStore = useChatStore()

const pending = computed(() => {
  const s = (chatStore as any).sessions?.[props.sessionId]
  return s?.clarificationPending ?? null
})

const showFreeText = ref(false)
const freeText = ref('')

function choose(option: string) {
  chatStore.sendMessage(props.sessionId, option)
  clear()
}

function submitFreeText() {
  const text = freeText.value.trim()
  if (!text) return
  chatStore.sendMessage(props.sessionId, text)
  clear()
}

function clear() {
  const s = (chatStore as any).sessions?.[props.sessionId]
  if (s) s.clarificationPending = null
  showFreeText.value = false
  freeText.value = ''
}
</script>

<template>
  <div v-if="pending" class="clarify" role="region" aria-label="需要你的确认">
    <div class="clarify__icon">
      <span class="material-symbols-outlined text-[20px]">help</span>
    </div>
    <div class="clarify__body">
      <div class="clarify__question">{{ pending.question }}</div>
      <div class="clarify__options">
        <button
          v-for="opt in (pending.options || [])"
          :key="opt"
          type="button"
          class="clarify__chip"
          @click="choose(opt)"
        >{{ opt }}</button>
        <button
          v-if="!showFreeText"
          type="button"
          class="clarify__chip clarify__chip--ghost"
          @click="showFreeText = true"
        >其他…</button>
      </div>
      <div v-if="showFreeText" class="clarify__freetext">
        <input
          v-model="freeText"
          placeholder="输入你的回答…"
          class="clarify__input"
          @keydown.enter="submitFreeText"
        />
        <button type="button" class="clarify__send" @click="submitFreeText">发送</button>
      </div>
    </div>
    <button type="button" class="clarify__close" aria-label="关闭" @click="clear">
      <span class="material-symbols-outlined text-[16px]">close</span>
    </button>
  </div>
</template>

<style scoped>
.clarify {
  display: flex;
  gap: 12px;
  padding: 14px 16px;
  margin: 0 0 10px;
  /* Solid surface so history text never bleeds through */
  background: var(--color-surface, #fff);
  border: 1px solid color-mix(in srgb, var(--color-brand, #7c3aed) 28%, var(--color-border));
  border-radius: 14px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.06);
  position: relative;
  isolation: isolate;
}
.clarify__icon {
  color: var(--color-brand, #7c3aed);
  flex-shrink: 0;
  padding-top: 2px;
}
.clarify__body { flex: 1; min-width: 0; }
.clarify__question {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin-bottom: 10px;
  line-height: 1.45;
}
.clarify__options { display: flex; flex-wrap: wrap; gap: 8px; }
.clarify__chip {
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  background: var(--color-surface-container-low, #f5f5f7);
  color: var(--color-brand, #7c3aed);
  border: 1px solid color-mix(in srgb, var(--color-brand, #7c3aed) 28%, transparent);
  border-radius: 999px;
  transition: background 140ms, color 140ms;
  max-width: 100%;
  text-align: left;
  white-space: normal;
  line-height: 1.35;
}
.clarify__chip:hover {
  background: var(--color-brand, #7c3aed);
  color: #fff;
}
.clarify__chip--ghost {
  background: transparent;
  color: var(--color-text-secondary);
  border-color: var(--color-border);
}
.clarify__chip--ghost:hover {
  background: var(--color-surface-hover, #f0f0f2);
  color: var(--color-text-primary);
}
.clarify__freetext { display: flex; gap: 8px; margin-top: 10px; }
.clarify__input {
  flex: 1;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--color-text-primary);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  outline: none;
  border-radius: 10px;
}
.clarify__input:focus { border-color: var(--color-brand, #7c3aed); }
.clarify__send {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  background: var(--color-brand, #7c3aed);
  color: #fff;
  border: none;
  border-radius: 10px;
}
.clarify__close {
  flex-shrink: 0;
  width: 28px;
  height: 28px;
  border: none;
  background: transparent;
  color: var(--color-text-tertiary);
  cursor: pointer;
  border-radius: 8px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.clarify__close:hover {
  background: var(--color-surface-hover, #f0f0f2);
  color: var(--color-text-primary);
}
</style>
