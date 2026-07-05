<script setup lang="ts">
import { computed } from 'vue'

/**
 * PlanModePreview — Vue 3 port of components/chat/PlanModePreview.tsx
 *
 * Renders a plan preview card with file path, plan content, and allowed prompts.
 * NOTE: Uses plain HTML for plan rendering. Prop-driven: no React store imports.
 */

type AllowedPrompt = { tool: string; prompt: string }

interface PlanPreviewModel {
  plan: string
  filePath: string
  allowedPrompts: AllowedPrompt[]
}

interface PlanPreviewCardProps {
  title: string
  plan: string
  filePath?: string
  allowedPrompts?: AllowedPrompt[]
  requestedPermissionsTitle?: string
  emptyLabel?: string
}

const props = withDefaults(defineProps<PlanPreviewCardProps>(), {
  allowedPrompts: () => [],
  emptyLabel: 'No plan content available.',
})

const trimmedPlan = computed(() => props.plan.trim())
const hasPermissions = computed(() => props.allowedPrompts.length > 0 && props.requestedPermissionsTitle)
</script>

<template>
  <div data-testid="plan-preview-card" class="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
    <div class="flex items-start gap-2 border-b border-[var(--color-border)]/65 bg-[var(--color-surface-container-low)] px-3 py-2.5">
      <span class="material-symbols-outlined mt-0.5 shrink-0 text-[15px] text-[var(--color-brand)]" aria-hidden="true">description</span>
      <div class="min-w-0 flex-1">
        <div class="text-[12px] font-semibold text-[var(--color-text-primary)]">{{ title }}</div>
        <div v-if="filePath" class="mt-0.5 truncate font-[var(--font-mono)] text-[11px] text-[var(--color-text-tertiary)]">
          {{ filePath }}
        </div>
      </div>
    </div>

    <div class="max-h-[520px] overflow-auto px-3 py-3">
      <template v-if="trimmedPlan">
        <pre class="m-0 whitespace-pre-wrap font-[var(--font-mono)] text-[12px] leading-relaxed text-[var(--color-text-primary)]">{{ trimmedPlan }}</pre>
      </template>
      <div v-else class="text-xs text-[var(--color-text-tertiary)]">{{ emptyLabel }}</div>
    </div>

    <div v-if="hasPermissions" class="border-t border-[var(--color-border)]/65 bg-[var(--color-surface-container-low)] px-3 py-2.5">
      <div class="mb-1.5 flex items-center gap-2 text-[11px] font-semibold uppercase text-[var(--color-outline)]">
        <span class="material-symbols-outlined text-[13px]" aria-hidden="true">shield_check</span>
        {{ requestedPermissionsTitle }}
      </div>
      <div class="space-y-1">
        <div v-for="(prompt, index) in allowedPrompts" :key="`${prompt.tool}-${prompt.prompt}-${index}`"
          class="rounded-md border border-[var(--color-border)]/70 bg-[var(--color-surface)] px-2.5 py-1.5 text-[11px] text-[var(--color-text-secondary)]">
          <span class="font-[var(--font-mono)] font-semibold text-[var(--color-text-primary)]">{{ prompt.tool }}</span>
          <span class="text-[var(--color-text-tertiary)]"> · </span>
          <span>{{ prompt.prompt }}</span>
        </div>
      </div>
    </div>
  </div>
</template>
