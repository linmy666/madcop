<script setup lang="ts">
// v3.0 — ImageGalleryModal (Vue 3)
// Direct translation — same Tailwind classes, same keyboard navigation.
import { onMounted, onUnmounted, computed } from 'vue'
import Modal from '../shared/Modal.vue'

interface GalleryImage { src: string; name: string }

const props = defineProps<{
  open: boolean
  images: GalleryImage[]
  activeIndex: number
}>()

const emit = defineEmits<{
  (e: 'close'): void
  (e: 'select', index: number): void
}>()

const activeImage = computed(() => props.images[props.activeIndex])

function onKey(e: KeyboardEvent) {
  if (!props.open || props.images.length <= 1) return
  if (e.key === 'ArrowLeft') {
    e.preventDefault()
    emit('select', (props.activeIndex - 1 + props.images.length) % props.images.length)
  } else if (e.key === 'ArrowRight') {
    e.preventDefault()
    emit('select', (props.activeIndex + 1) % props.images.length)
  }
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Modal :open="open" :width="960" @close="emit('close')">
    <div v-if="activeImage" class="space-y-4">
      <div class="flex items-center justify-between gap-4">
        <div class="min-w-0">
          <div class="text-sm font-semibold text-[var(--color-text-primary)]">{{ activeImage.name }}</div>
          <div class="text-xs text-[var(--color-text-tertiary)]">{{ activeIndex + 1 }} / {{ images.length }}</div>
        </div>
        <div v-if="images.length > 1" class="flex items-center gap-2">
          <button
            @click="emit('select', (activeIndex - 1 + images.length) % images.length)"
            class="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--color-border)] text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]"
            aria-label="上一张"
          >
            <span class="material-symbols-outlined text-[18px]">chevron_left</span>
          </button>
          <button
            @click="emit('select', (activeIndex + 1) % images.length)"
            class="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--color-border)] text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)]"
            aria-label="下一张"
          >
            <span class="material-symbols-outlined text-[18px]">chevron_right</span>
          </button>
        </div>
      </div>

      <div class="flex max-h-[70vh] items-center justify-center overflow-hidden rounded-2xl bg-[#111]">
        <img :src="activeImage.src" :alt="activeImage.name" class="max-h-[70vh] w-full object-contain" />
      </div>

      <div v-if="images.length > 1" class="flex gap-2 overflow-x-auto pb-1">
        <button
          v-for="(image, index) in images" :key="`${image.name}-${index}`"
          @click="emit('select', index)"
          :class="[
            'overflow-hidden rounded-xl border transition-all',
            index === activeIndex ? 'border-[var(--color-brand)] shadow-[0_0_0_1px_var(--color-brand)]' : 'border-[var(--color-border)]',
          ]"
        >
          <img :src="image.src" :alt="image.name" class="h-16 w-16 object-cover" />
        </button>
      </div>
    </div>
  </Modal>
</template>
