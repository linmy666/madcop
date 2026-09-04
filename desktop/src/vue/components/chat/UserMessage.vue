<template>
  <!-- User message: right-aligned quiet bubble. No avatar — Qoder/ChatGPT
       language: the bubble's alignment alone identifies the speaker, and a
       person-icon circle next to every message reads as visual noise. -->
  <div data-message-shell="user" class="user-message group flex items-start justify-end py-3">
    <div class="flex max-w-[80%] flex-col items-end">
      <div class="user-message__bubble">
        <!-- Image attachments (inline thumbnails) -->
        <div v-if="imageAttachments.length > 0" class="flex flex-wrap gap-2 mb-2">
          <div
            v-for="att in imageAttachments"
            :key="att.id"
            class="user-message__image"
            :style="{ backgroundImage: `url('${att.previewUrl || att.dataUrl || att.path}')` }"
            :title="att.name"
          />
        </div>
        <!-- File attachments (other than images) -->
        <div v-if="fileAttachments.length > 0" class="flex flex-wrap gap-1.5 mb-2">
          <div
            v-for="att in fileAttachments"
            :key="att.id"
            class="user-message__file"
          >
            <span class="material-symbols-outlined text-[14px]">attach_file</span>
            <span class="text-[12px]">{{ att.name }}</span>
          </div>
        </div>
        <div
          v-if="hasText"
          class="text-[14px] leading-[1.6] text-[var(--color-text-primary)] whitespace-pre-wrap break-words"
        >
          {{ content }}
        </div>
      </div>
      <!-- Hover actions -->
      <div class="user-message__actions mt-1 flex items-center gap-0.5 opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-within:opacity-100">
        <button type="button" class="msg-action" :title="copied ? '已复制' : '复制'" @click="copy">
          <span class="material-symbols-outlined text-[16px]">{{ copied ? 'check' : 'content_copy' }}</span>
        </button>
        <button type="button" class="msg-action" title="重发" @click="retry">
          <span class="material-symbols-outlined text-[16px]">replay</span>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useChatStore } from '../../stores/chatStore'

export interface UserAttachment {
  id: string
  name: string
  type: string
  path?: string
  /** Base64 data URL (e.g. "data:image/png;base64,...") — used for inline image previews. */
  previewUrl?: string
  dataUrl?: string
}

const props = defineProps<{
  content: string
  attachments?: UserAttachment[]
  sessionId?: string
}>()

const chatStore = useChatStore()
const copied = ref(false)

const hasText = computed(() => (props.content || '').trim().length > 0)

const imageAttachments = computed(() =>
  (props.attachments || []).filter((a) => a.type?.startsWith('image/') || /\.(png|jpe?g|gif|webp|svg)$/i.test(a.name || ''))
)
const fileAttachments = computed(() =>
  (props.attachments || []).filter((a) => !imageAttachments.value.includes(a))
)

async function copy() {
  try {
    await navigator.clipboard.writeText(props.content)
    copied.value = true
    window.setTimeout(() => (copied.value = false), 1500)
  } catch {
    /* clipboard unavailable */
  }
}

function retry() {
  if (!props.sessionId) return
  chatStore.sendMessage(props.sessionId, props.content)
}
</script>

<style scoped>
.user-message {
  display: flex;
  justify-content: flex-end;
}
.user-message__bubble {
  max-width: 100%;
  /* ChatGPT-style bubble: solid fill, no border/shadow — the surface
     tone alone separates it from the canvas. */
  background: var(--color-surface-user-msg, var(--color-surface-container));
  padding: 10px 16px;
  border-radius: 18px;
}

.user-message__actions {
  align-self: flex-end;
}

.msg-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 28px;
  border-radius: 4px;
  color: var(--color-text-secondary);
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  transition: background 0.12s, color 0.12s, border-color 0.12s;
}
.msg-action:hover {
  background: var(--color-surface-hover);
  color: var(--color-text-primary);
  border-color: var(--color-border);
}
.msg-action:active {
  transform: scale(0.94);
}


.user-message__image {
  width: 96px;
  height: 96px;
  background-size: cover;
  background-position: center;
  background-color: var(--color-surface);
  border-radius: 4px;
  border: 1px solid var(--color-border);
  cursor: pointer;
  background-repeat: no-repeat;
}

.user-message__file {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-secondary);
}
</style>
