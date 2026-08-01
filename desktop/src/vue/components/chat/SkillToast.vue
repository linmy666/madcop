<script setup lang="ts">
/**
 * Sprint 1 — Auto-distill notification toast.
 *
 * Auto-fires when the chatStore receives a `skill_distilled` SSE event
 * from the backend. The toast is non-blocking and dismisses on click
 * or after 8s. Shows the skill name as a clickable link to the
 * SkillDetail page.
 *
 * Two visual states:
 *  - auto-distilled  → "✨ 新技能" (purple accent)
 *  - teach-me        → "已学习" (green accent, kept for parity with
 *                       the old distill_skill_from_exchange path)
 */
import { useRouter } from 'vue-router'

defineProps<{
  toasts: Array<{
    id: string
    kind: 'auto-distilled' | 'teach-me'
    skillName: string
  }>
}>()

const emit = defineEmits<{ (e: 'remove', id: string): void }>()

const router = useRouter()

function open(id: string, skillName: string) {
  router.push({ name: 'skills', query: { skill: skillName } })
  emit('remove', id)
}
</script>

<template>
  <div
    v-if="toasts.length > 0"
    class="fixed bottom-4 right-4 z-[110] flex flex-col gap-2 max-w-sm"
  >
    <div
      v-for="toast in toasts"
      :key="toast.id"
      :class="[
        'bg-[var(--color-surface)] rounded-[var(--radius-md)] shadow-[var(--shadow-dropdown)] px-4 py-3 text-sm text-[var(--color-text-primary)]',
        toast.kind === 'auto-distilled'
          ? 'border-l-4 border-l-[var(--color-brand)]'
          : 'border-l-4 border-l-[var(--color-success)]',
      ]"
    >
      <div class="flex items-center justify-between gap-3">
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-2 mb-1">
            <span class="material-symbols-outlined text-[16px] text-[var(--color-brand)]">
              {{ toast.kind === 'auto-distilled' ? 'auto_awesome' : 'school' }}
            </span>
            <span class="text-[12px] uppercase tracking-wide font-semibold text-[var(--color-text-tertiary)]">
              {{ toast.kind === 'auto-distilled' ? 'Skill saved' : 'New skill' }}
            </span>
          </div>
          <button
            class="text-left text-[var(--color-text-primary)] font-medium hover:text-[var(--color-brand)] truncate w-full"
            @click="open(toast.id, toast.skillName)"
          >
            {{ toast.skillName }}
          </button>
        </div>
        <button
          class="text-[var(--color-text-tertiary)] hover:text-[var(--color-text-primary)] text-lg leading-none"
          @click="emit('remove', toast.id)"
        >×</button>
      </div>
    </div>
  </div>
</template>
