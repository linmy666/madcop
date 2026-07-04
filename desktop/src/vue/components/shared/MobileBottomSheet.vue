<script setup lang="ts">
// v3.0 — MobileBottomSheet (Vue 3)
// Direct translation — Teleport replaces createPortal, same Tailwind classes.
import { onMounted, onUnmounted } from 'vue'

const props = withDefaults(defineProps<{
  open: boolean
  title?: string
  closeLabel?: string
  testId?: string
}>(), {
  closeLabel: '关闭',
})

const emit = defineEmits<{ (e: 'close'): void }>()

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && props.open) emit('close')
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <Transition name="sheet-fade">
      <div v-if="open" class="fixed inset-0 z-[10000] bg-black/25" @click="emit('close')">
        <div
          :data-testid="testId"
          role="dialog"
          aria-modal="true"
          :aria-label="title"
          class="absolute inset-x-0 bottom-0 flex max-h-[min(78dvh,640px)] min-h-0 flex-col overflow-hidden rounded-t-2xl border-x-0 border-y border-[var(--color-border)] bg-[var(--color-surface-container-lowest)] shadow-[0_-18px_48px_rgba(54,35,28,0.22)]"
          @click.stop
        >
          <div class="shrink-0 border-b border-[var(--color-border)] px-4 py-3">
            <div class="flex min-h-10 items-center justify-between gap-3">
              <div class="min-w-0 text-[11px] font-bold uppercase tracking-widest text-[var(--color-outline)]">
                {{ title }}
              </div>
              <button
                type="button"
                :aria-label="closeLabel"
                @click="emit('close')"
                class="grid h-10 w-10 shrink-0 place-items-center rounded-full text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-border-focus)]"
              >
                <span class="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>
            <slot name="header-extra" />
          </div>

          <div class="min-h-0 flex-1 overflow-y-auto">
            <slot />
          </div>

          <div v-if="$slots.footer" class="shrink-0 border-t border-[var(--color-border)]">
            <slot name="footer" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style>
.sheet-fade-enter-active, .sheet-fade-leave-active { transition: opacity 200ms; }
.sheet-fade-enter-from, .sheet-fade-leave-to { opacity: 0; }
</style>
