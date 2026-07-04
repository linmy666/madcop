<script setup lang="ts">
// v3.0 — PromptEditor (Vue 3)
// Direct translation — same Tailwind classes, same layout.
const props = defineProps<{
  modelValue: string
  placeholder?: string
  folderPath?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'folderChange', path: string): void
}>()
</script>

<template>
  <div class="rounded-[var(--radius-lg)] border border-[var(--color-border)] focus-within:border-[var(--color-border-focus)] transition-colors overflow-visible">
    <textarea
      :value="modelValue"
      @input="(e) => emit('update:modelValue', (e.target as HTMLTextAreaElement).value)"
      :placeholder="placeholder"
      rows="4"
      class="w-full resize-y bg-transparent px-3 py-2.5 text-sm leading-relaxed text-[var(--color-text-primary)] outline-none placeholder:text-[var(--color-text-tertiary)]"
      style="min-height: 120px;"
    />

    <div class="border-t border-[var(--color-border)]/40 px-3 py-2 flex flex-col gap-2 bg-[var(--color-surface-container-low)] rounded-b-[var(--radius-lg)]">
      <div class="flex items-center justify-between">
        <div class="inline-flex items-center gap-1.5 rounded-full bg-[var(--color-error)]/8 px-2.5 py-1.5 text-xs font-medium text-[var(--color-error)]">
          <span class="material-symbols-outlined text-[14px]">gavel</span>
          完整权限
        </div>
        <slot name="model-selector" />
      </div>
      <div class="flex items-center justify-between">
        <slot name="folder-picker" :path="folderPath" :on-change="(p: string) => emit('folderChange', p)">
          <span v-if="folderPath" class="text-xs text-[var(--color-text-tertiary)] font-[var(--font-mono)] truncate max-w-[280px]">{{ folderPath }}</span>
        </slot>
      </div>
      <div class="flex items-center gap-1.5 px-2 py-1.5 rounded-md bg-[var(--color-error)]/8 text-[10px] text-[var(--color-error)]">
        <span class="material-symbols-outlined text-[12px]">warning</span>
        将跳过权限检查{{ folderPath ? ` (在 ${folderPath} 范围内)` : '（请先选择目录）' }}。
      </div>
    </div>
  </div>
</template>
