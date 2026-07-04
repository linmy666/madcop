<script setup lang="ts">
// v3.0 — Button (Vue 3)
// Direct translation of Button.tsx — same Tailwind classes, same variants.
withDefaults(defineProps<{
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  loading?: boolean
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
  class?: string
}>(), {
  variant: 'primary',
  size: 'md',
  loading: false,
  disabled: false,
  type: 'button',
})

defineEmits<{ (e: 'click', ev: MouseEvent): void }>()
</script>

<template>
  <button
    :type="type"
    :disabled="disabled || loading"
    :class="[
      'inline-flex items-center justify-center gap-1.5 rounded-[var(--radius-md)] font-medium transition-colors duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed',
      {
        'bg-[image:var(--gradient-btn-primary)] text-[var(--color-btn-primary-fg)] shadow-[var(--shadow-button-primary)] hover:bg-[image:var(--gradient-btn-primary-hover)] hover:brightness-105 active:translate-y-[1px]': variant === 'primary',
        'bg-[var(--color-surface)] text-[var(--color-text-primary)] border border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]': variant === 'secondary',
        'bg-[var(--color-error)] text-white hover:opacity-90': variant === 'danger',
        'bg-transparent text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text-primary)]': variant === 'ghost',
      },
      {
        'px-2 py-1 text-xs': size === 'sm',
        'px-4 py-2 text-sm': size === 'md',
        'px-5 py-2.5 text-sm': size === 'lg',
      },
      $props.class
    ]"
    @click="(e) => $emit('click', e)"
  >
    <svg v-if="loading" class="animate-spin h-4 w-4" viewBox="0 0 24 24" fill="none">
      <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" />
      <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
    <slot v-else name="icon" />
    <slot />
  </button>
</template>
