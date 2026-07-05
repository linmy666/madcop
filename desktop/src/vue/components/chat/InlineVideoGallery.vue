<script setup lang="ts">
import { computed } from 'vue'

/**
 * InlineVideoGallery — Vue 3 port of components/chat/InlineVideoGallery.tsx
 * Renders AI-output video paths inline. No autoplay, vertical stack.
 * Prop-driven: parent passes text, sessionId, workDir.
 */

export interface InlineVideoGalleryProps {
  text: string
  sessionId?: string
  workDir?: string | null
}

const props = withDefaults(defineProps<InlineVideoGalleryProps>(), {
  workDir: null,
})

const videos = computed(() => {
  if (!props.sessionId) return [] as Array<{ src: string; name: string }>
  // Extract video paths from text (mp4/webm/mov/m4v)
  const regex = /((?:^|[\s`"'(])(\/?(?:[A-Za-z]:[\/]|\/)[^\s`"'<>]+)\.(?:mp4|webm|mov|m4v))/gim
  const seen = new Set<string>()
  const result: Array<{ src: string; name: string }> = []
  let match
  while ((match = regex.exec(props.text)) !== null) {
    const src = match[1].trim()
    if (seen.has(src)) continue
    seen.add(src)
    const name = src.split('/').pop() || src
    result.push({ src, name })
  }
  return result
})

const hasVideos = computed(() => videos.value.length > 0)
</script>

<template>
  <div v-if="hasVideos" class="mt-3 space-y-2">
    <div v-for="video in videos" :key="video.src"
      class="overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] shadow-sm">
      <video :src="video.src" controls preload="metadata" playsInline
        class="w-full rounded-t-xl bg-black" style="max-height: 420px" />
      <div class="flex items-center gap-1.5 px-2.5 py-1.5 text-[10px] font-medium text-[var(--color-text-tertiary)]">
        <span class="material-symbols-outlined text-[12px]">movie</span>
        <span class="truncate">{{ video.name }}</span>
      </div>
    </div>
  </div>
</template>
