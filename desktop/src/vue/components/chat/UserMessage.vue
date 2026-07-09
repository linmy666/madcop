<template>
  <!-- User message: right-aligned, soft bubble (no avatar, no name) -->
  <div data-message-shell="user" class="user-message group py-3">
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
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

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
}>()

const hasText = computed(() => (props.content || '').trim().length > 0)

const imageAttachments = computed(() =>
  (props.attachments || []).filter((a) => a.type?.startsWith('image/') || /\.(png|jpe?g|gif|webp|svg)$/i.test(a.name || ''))
)
const fileAttachments = computed(() =>
  (props.attachments || []).filter((a) => !imageAttachments.value.includes(a))
)
</script>

<style scoped>
.user-message {
  display: flex;
  justify-content: flex-end;
}
.user-message__bubble {
  max-width: 80%;
  background: var(--color-surface-container-low, #f5f5f5);
  padding: 10px 14px;
  border-radius: 14px;
  border: 1px solid var(--color-border-separator, rgba(0,0,0,0.06));
}

.user-message__image {
  width: 96px;
  height: 96px;
  background-size: cover;
  background-position: center;
  background-color: var(--color-surface);
  border-radius: 8px;
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
  border-radius: 6px;
  color: var(--color-text-secondary);
}
</style>
