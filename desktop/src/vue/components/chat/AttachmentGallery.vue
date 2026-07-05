<script setup lang="ts">
import { computed } from 'vue'

/**
 * AttachmentGallery — Vue 3 port of components/chat/AttachmentGallery.tsx
 *
 * Displays image/file attachments with optional selection notes and remove button.
 * ImageGalleryModal dependency skipped (no Vue equivalent) — images rendered inline only.
 * Prop-driven: parent passes attachments[] and onRemove callback.
 */

export type AttachmentPreview = {
  id?: string
  type: 'image' | 'file'
  name: string
  path?: string
  data?: string
  previewUrl?: string
  isDirectory?: boolean
  lineStart?: number
  lineEnd?: number
  note?: string
  quote?: string
}

export interface AttachmentGalleryProps {
  attachments: AttachmentPreview[]
  variant?: 'composer' | 'message'
}

const props = withDefaults(defineProps<AttachmentGalleryProps>(), {
  variant: 'message',
})

const emit = defineEmits<{
  remove: [id: string]
}>()

const isComposer = computed(() => props.variant === 'composer')

const images = computed(() =>
  props.attachments
    .filter((a) => a.type === 'image' && (a.previewUrl || a.data))
    .map((a) => ({ src: a.previewUrl || a.data || '', name: a.name }))
)

function attachmentKey(a: AttachmentPreview, index: number): string {
  return a.id || `${a.name}-${index}`
}

function hasQuotePreview(attachment: AttachmentPreview): boolean {
  return !!(attachment.quote?.trim())
}

function lineLabel(attachment: AttachmentPreview): string {
  if (!attachment.lineStart) return ''
  if (attachment.lineEnd && attachment.lineEnd !== attachment.lineStart) {
    return `:L${attachment.lineStart}-L${attachment.lineEnd}`
  }
  return `:L${attachment.lineStart}`
}
</script>

<template>
  <div v-if="props.attachments.length > 0">
    <div :class="isComposer ? 'flex flex-wrap items-center gap-2' : 'flex flex-wrap justify-end gap-2'">
      <template v-for="(attachment, index) in props.attachments" :key="attachmentKey(attachment, index)">
        <!-- Image attachment -->
        <div v-if="attachment.type === 'image' && (attachment.previewUrl || attachment.data)"
          :class="isComposer ? 'group relative' : 'group/selection relative flex max-w-full flex-col items-end gap-1.5'">
          <button type="button"
            :aria-label="'Open ' + attachment.name"
            :class="isComposer
              ? 'overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)]'
              : 'overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] text-left shadow-sm transition-transform hover:scale-[1.01]'">
            <img :src="attachment.previewUrl || attachment.data || ''" :alt="attachment.name"
              :class="isComposer ? 'h-16 w-16 object-cover' : 'max-h-[340px] w-full max-w-[360px] object-cover'" />
          </button>

          <template v-if="!isComposer && attachment.note?.trim()">
            <span :aria-label="'Selection note: ' + (attachment.note || '')" :title="attachment.note || ''"
              class="inline-flex h-7 max-w-[260px] items-center gap-1.5 rounded-full border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-2.5 text-[12px] font-medium leading-none text-[var(--color-text-primary)] shadow-[0_1px_2px_rgba(0,0,0,0.04)] transition-colors hover:border-[var(--color-brand)]/45 hover:bg-[var(--color-surface-container)]">
              <span class="material-symbols-outlined text-[15px] text-[var(--color-text-tertiary)]">ads_click</span>
              <span class="min-w-0 truncate">{{ attachment.name }}</span>
            </span>
          </template>

          <button v-if="attachment.id" type="button" @click="emit('remove', attachment.id!)"
            class="absolute -right-1 -top-1 flex h-5 w-5 items-center justify-center rounded-full bg-[var(--color-error)] text-[10px] text-white opacity-0 transition-opacity group-hover:opacity-100"
            :aria-label="'Remove ' + attachment.name">×</button>
        </div>

        <!-- File attachment -->
        <div v-else
          :class="['group/file inline-flex max-w-full min-w-0 border border-[var(--color-border)] bg-[var(--color-surface-container-low)] text-[var(--color-text-secondary)] shadow-[0_1px_2px_rgba(0,0,0,0.04)]',
            hasQuotePreview(attachment) ? 'items-start gap-2 rounded-[8px] px-2.5 py-2' : 'h-9 items-center gap-2 rounded-full px-3']">
          <span class="material-symbols-outlined shrink-0 text-[17px] text-[var(--color-text-tertiary)]"
            :class="hasQuotePreview(attachment) ? 'mt-0.5' : ''">
            {{ hasQuotePreview(attachment) ? 'chat_bubble' : attachment.isDirectory ? 'folder' : 'description' }}
          </span>
          <span class="min-w-0">
            <span class="block min-w-0 max-w-[260px] truncate text-[13px] font-medium leading-5 text-[var(--color-text-primary)]">
              {{ attachment.name }}{{ lineLabel(attachment) }}
            </span>
            <span v-if="hasQuotePreview(attachment)"
              class="mt-0.5 block max-w-[320px] truncate font-[var(--font-mono)] text-[11px] leading-4 text-[var(--color-text-tertiary)]">
              {{ attachment.quote?.trim().replace(/\s+/g, ' ') }}
            </span>
          </span>
          <button v-if="attachment.id" type="button" @click="emit('remove', attachment.id!)"
            :class="hasQuotePreview(attachment) ? 'mt-0.5' : 'ml-0.5'"
            class="flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[var(--color-text-tertiary)] transition-colors hover:text-[var(--color-text-primary)]"
            :aria-label="'Remove ' + attachment.name">
            <span class="material-symbols-outlined text-[17px]">close</span>
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
