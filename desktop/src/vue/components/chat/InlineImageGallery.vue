<script setup lang="ts">
import { computed } from 'vue'

/**
 * InlineImageGallery — Vue 3 port of components/chat/InlineImageGallery.tsx
 * Extracts image paths from text and renders them inline.
 * Prop-driven: no React stores. ImageGalleryModal skipped.
 */

export interface InlineImageGalleryProps {
  text: string
  sessionId?: string
  workDir?: string | null
}

const props = defineProps<InlineImageGalleryProps>()

const IMAGE_EXTENSIONS = /\.(png|jpe?g|gif|webp|svg|bmp|avif|ico)$/i

function extractImagePaths(text: string): string[] {
  const regex = /(?:^|[\s`"'(])(\/?(?:[A-Za-z]:[\\/]|\/)[^\s`"')<>]+\.(?:png|jpe?g|gif|webp|svg|bmp|avif|ico))/gim
  const paths: string[] = []
  const seen = new Set<string>()
  let match: RegExpExecArray | null
  while ((match = regex.exec(text)) !== null) {
    const p = match[1]!.trim()
    if (!seen.has(p) && IMAGE_EXTENSIONS.test(p)) { seen.add(p); paths.push(p) }
  }
  return paths
}

function fileUrl(filePath: string): string {
  return `/api/filesystem/file?path=${encodeURIComponent(filePath)}`
}

function fileName(filePath: string): string {
  return filePath.split('/').pop() || filePath
}

interface GalleryImage { src: string; name: string }

const images = computed<GalleryImage[]>(() => {
  const imagePaths = extractImagePaths(props.text)
  return imagePaths.map((p) => ({ src: fileUrl(p), name: fileName(p) }))
})

function handleImgError(event: Event) {
  const img = event.target as HTMLImageElement
  const button = img.closest('button') as HTMLElement
  if (button) button.style.display = 'none'
}
</script>

<template>
  <div v-if="images.length > 0" class="mt-3 space-y-2">
    <div class="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-outline)]">
      <span class="material-symbols-outlined text-[12px]">image</span>
      <span>{{ images.length === 1 ? '1 image' : `${images.length} images` }}</span>
    </div>
    <div :class="images.length === 1 ? 'grid grid-cols-1 gap-2' : 'grid grid-cols-2 gap-2'">
      <button v-for="(img, i) in images" :key="img.src" type="button"
        class="group/image relative overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] text-left shadow-sm transition-all hover:shadow-md hover:border-[var(--color-brand)]/40">
        <img :src="img.src" :alt="img.name" loading="lazy" @error="handleImgError"
          class="w-full object-cover" :style="{ maxHeight: images.length === 1 ? 400 : 240 }" />
        <div class="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-all group-hover/image:bg-black/20 group-hover/image:opacity-100">
          <span class="material-symbols-outlined rounded-full bg-white/90 p-2 text-[20px] text-[var(--color-text-primary)] shadow-lg">fullscreen</span>
        </div>
        <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent px-2.5 pb-2 pt-6">
          <span class="text-[10px] font-medium text-white/90 drop-shadow-sm">{{ img.name }}</span>
        </div>
      </button>
    </div>
  </div>
</template>
