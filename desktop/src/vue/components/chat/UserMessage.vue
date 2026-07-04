<script setup lang="ts">
// v3.0 — UserMessage (Vue 3)
// Direct translation of UserMessage.tsx — same Tailwind classes, same bubble shape.
import { computed } from 'vue'
import MessageActionBar from './MessageActionBar.vue'
import type { ComposerAttachment } from '../../lib/composerAttachments'

const props = defineProps<{
  content: string
  attachments?: ComposerAttachment[]
  branchLabel?: string
  branchLoading?: boolean
  timestamp?: number
}>()

const hasText = computed(() => props.content.trim().length > 0)
</script>

<template>
  <div class="mb-5 flex justify-end">
    <div
      data-message-shell="user"
      class="group flex min-w-0 max-w-[82%] flex-col items-end sm:max-w-[78%] lg:max-w-[72%]"
    >
      <div class="flex max-w-full flex-col items-end gap-2">
        <slot name="attachments" />
        <div
          v-if="hasText"
          class="min-w-0 max-w-full bg-[var(--color-surface-user-msg)] px-4 py-3 text-sm leading-relaxed text-[var(--color-text-primary)] whitespace-pre-wrap break-words"
          style="border-radius: 18px 4px 18px 18px; overflow-wrap: anywhere; word-break: break-word;"
        >
          {{ content }}
        </div>
      </div>
      <MessageActionBar
        v-if="hasText"
        :copy-text="content"
        copy-label="复制提问"
        :branch-label="branchLabel"
        :branch-loading="branchLoading"
        align="end"
        :timestamp="timestamp"
        @branch="$emit('branch')"
      />
    </div>
  </div>
</template>
