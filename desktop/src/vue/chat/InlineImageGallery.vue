<script setup lang="ts">
import { ref, computed } from 'vue'

/**
 * InlineImageGallery — Vue 3 port of components/chat/InlineImageGallery.tsx
 * Renders image paths found in text content. Prop-driven.
 */

const IMAGE_EXTENSIONS = /\.(png|jpe?g|gif|webp|svg|bmp|avif|ico)$/i

function extractImagePaths(text: string): string[] {
  const regex = /(?:^|[\s`"'(])(\/?(?:[A-Za-z]:[\\/]|\/)[^\s`"'<>]+\.(?:png|jpe?g|gif|webp|svg|bmp|avif|ico))/gim
  const paths: string[] = []
  const seen = new Set<string>()
  let match
  while ((match = regex.exec(text)) !== null) {
    const p = match[1].trim()
    if (!seen.has(p) && IMAGE_EXTENSIONS.test(p)) {
      seen.add(p)
      paths.push(p)
    }
  }
  return paths
}

function fileUrl(filePath: string): string {
  return `/api/filesystem/file?path=${encodeURIComponent(filePath)}`
}

function fileName(filePath: string): string {
  return filePath.split('/').pop() || filePath
}

export interface InlineImageGalleryProps {
  text: string
  sessionId?: string
  workDir?: string | null
}

const props = withDefaults(defineProps<InlineImageGalleryProps>(), {
  workDir: null,
})

const activeIndex = ref<number | null>(null)

const imagePaths = computed(() => extractImagePaths(props.text))

const images = computed(() => {
  return imagePaths.value.map((p) => ({ src: fileUrl(p), name: fileName(p) }))
})

const hasImages = computed(() => images.value.length > 0)

function setActiveIndex(idx: number) {
  activeIndex.value = activeIndex.value === idx ? null : idx
}
</script>

<template>
  <div v-if="hasImages">
    <div class="mt-3 space-y-2">
      <div class="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[var(--color-outline)]">
        <span class="material-symbols-outlined text-[12px]">image</span>
        {{ images.length === 1 ? '1 image' : images.length + ' images' }}
      </div>
      <div :class="['grid gap-2', images.length === 1 ? 'grid-cols-1' : 'grid-cols-2']">
        <button v-for="(img, i) in images" :key="img.src" type="button"
          @click="setActiveIndex(i)"
          class="group/image relative overflow-hidden rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] text-left shadow-sm transition-all hover:shadow-md hover:border-[var(--color-brand)]/40">
          <img :src="img.src" :alt="img.name" loading="lazy"
            class="w-full object-cover" :style="{ maxHeight: images.length === 1 ? 400 : 240 }" />
          <div class="absolute inset-0 flex items-center justify-center bg-black/0 opacity-0 transition-all group-hover/image:bg-black/20 group-hover/image:opacity-100">
            <span class="material-symbols-outlined rounded-full bgwhite/90 p-2 text-[20px] text-[var(--color-text-primary)] shadow-lg">fullscreen</span>
          </div>
          <div class="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/60 to-transparent px-2.5 pb-2 pt-6">
            <span class="text-[10px] font-medium text-white/90 drop-shadow-sm">{{ img.name }}</span>
          </div>
        </button>
      </div>
    </div>

    <Teleport v-if="activeIndex !== null" to="body">
      <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/80" @click="activeIndex = null">
        <div class="relative max-h-[90vh] max-w-[90vw]" @click.stop>
          <img :src="images[activeIndex]!.src" :alt="images[activeIndex]!.name"
            class="max-h-[90vh] max-w-[90vw] rounded-xl object-contain" />
          <button class="absolute -top-2 -right-2 flex h-7 w-7 items-center justify-center rounded-full bg-black/60 text-white"
            @click="activeIndex = null">
            <span class="material-symbols-outlined text-[18px]">close</span>
          </button>
          <div class="absolute bottom-2 left-0 right-0 text-center text-white/80 text-xs">{{ images[activeIndex]!.name }}</div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
