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
  <div v-if="pending" class="clarify">
    <div class="clarify__icon">
      <span class="material-symbols-outlined text-[20px]">help</span>
    </div>
    <div class="clarify__body">
      <div class="clarify__question">{{ pending.question }}</div>
      <div class="clarify__options">
        <button
          v-for="opt in (pending.options || [])"
          :key="opt"
          class="clarify__chip"
          @click="choose(opt)"
        >{{ opt }}</button>
        <button
          v-if="!showFreeText"
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
        <button class="clarify__send" @click="submitFreeText">发送</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.clarify {
  display: flex; gap: 12px; padding: 14px 16px; margin: 12px 0;
  background: var(--color-primary-fixed);
  border: 1px solid color-mix(in srgb, var(--color-primary) 24%, transparent);
  border-radius: var(--radius-lg);
}
.clarify__icon { color: var(--color-primary); flex-shrink: 0; padding-top: 2px; }
.clarify__body { flex: 1; min-width: 0; }
.clarify__question { font-size: 14px; font-weight: 600; color: var(--color-text-primary); margin-bottom: 10px; }
.clarify__options { display: flex; flex-wrap: wrap; gap: 8px; }
.clarify__chip {
  padding: 6px 14px; font-size: 13px; font-weight: 500; cursor: pointer;
  background: var(--color-surface); color: var(--color-primary);
  border: 1px solid color-mix(in srgb, var(--color-primary) 30%, transparent);
  border-radius: var(--radius-full);
  transition: background 140ms;
}
.clarify__chip:hover { background: var(--color-primary); color: var(--color-on-primary); }
.clarify__chip--ghost { background: transparent; color: var(--color-text-secondary); border-color: var(--color-border); }
.clarify__chip--ghost:hover { background: var(--color-surface-hover); color: var(--color-text-primary); }
.clarify__freetext { display: flex; gap: 8px; margin-top: 10px; }
.clarify__input {
  flex: 1; padding: 8px 12px; font-size: 13px; color: var(--color-text-primary);
  background: var(--color-surface); border: 1px solid var(--color-border); outline: none;
  border-radius: var(--radius-md);
}
.clarify__input:focus { border-color: var(--color-primary); }
.clarify__send {
  padding: 8px 16px; font-size: 13px; font-weight: 500; cursor: pointer;
  background: var(--color-primary); color: var(--color-on-primary); border: none;
  border-radius: var(--radius-md);
}
</style>
