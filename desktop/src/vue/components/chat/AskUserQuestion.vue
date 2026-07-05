<script setup lang="ts">
import { ref, computed } from 'vue'

/**
 * AskUserQuestion — Vue 3 port of components/chat/AskUserQuestion.tsx
 * Renders a question with options and free-text answer.
 * Prop-driven: no React stores. Parent passes callbacks.
 */

interface QuestionOption { label: string; description?: string }
interface Question { question: string; header?: string; options?: QuestionOption[]; multiSelect?: boolean }

export interface AskUserQuestionProps {
  input: unknown
  result?: unknown
  t?: (key: string) => string
  /** Callback when user submits answers */
  onSubmit?: (answers: Record<string, string>) => void
}

const props = withDefaults(defineProps<AskUserQuestionProps>(), {
  t: () => '',
})

function parseInput(input: unknown): Question[] {
  if (!input || typeof input !== 'object') return []
  const obj = input as { questions?: Question[]; question?: string; header?: string; options?: QuestionOption[]; multiSelect?: boolean }
  if (Array.isArray(obj.questions)) return obj.questions
  if (typeof obj.question === 'string') {
    return [{ question: obj.question, header: obj.header, options: obj.options, multiSelect: obj.multiSelect }]
  }
  return []
}

const questions = computed(() => parseInput(props.input))
const activeTab = ref(0)
const selections = ref<Record<number, string[]>>({})
const freeTexts = ref<Record<number, string>>({})
const hasSubmitted = ref(false)

const activeQuestion = computed(() => {
  const safe = Math.min(activeTab.value, questions.value.length - 1)
  return questions.value[safe] || null
})

const safeActiveTab = computed(() => Math.min(activeTab.value, questions.value.length - 1))

const allAnswered = computed(() => {
  return questions.value.every((_, i) => Boolean(freeTexts.value[i]?.trim()) || (selections.value[i]?.length ?? 0) > 0)
})

function handleSelect(qIndex: number, label: string) {
  if (hasSubmitted.value) return
  const q = questions.value[qIndex]
  const selected = selections.value[qIndex] ?? []
  if (q?.multiSelect) {
    const next = selected.includes(label) ? selected.filter((v) => v !== label) : [...selected, label]
    const nextSel = { ...selections.value }
    if (next.length > 0) nextSel[qIndex] = next; else delete nextSel[qIndex]
    selections.value = nextSel
  } else {
    const nextSel = { ...selections.value }
    if (selected[0] === label) { delete nextSel[qIndex]; selections.value = nextSel; return }
    nextSel[qIndex] = [label]
    selections.value = nextSel
  }
  if (freeTexts.value[qIndex]) {
    const next = { ...freeTexts.value }; delete next[qIndex]; freeTexts.value = next
  }
}

function handleFreeTextChange(qIndex: number, value: string) {
  if (hasSubmitted.value) return
  const next = { ...freeTexts.value }
  if (value) next[qIndex] = value; else delete next[qIndex]
  freeTexts.value = next
  if (value.trim()) {
    const nextSel = { ...selections.value }; delete nextSel[qIndex]; selections.value = nextSel
  }
}

function handleSubmit() {
  if (hasSubmitted.value || !allAnswered.value) return
  const answers: Record<string, string> = {}
  for (let i = 0; i < questions.value.length; i++) {
    const q = questions.value[i]!
    const free = freeTexts.value[i]?.trim()
    if (free) { answers[q.question] = free; continue }
    const sel = selections.value[i]
    if (sel && sel.length > 0) { answers[q.question] = q.multiSelect ? sel.join(', ') : sel[0] }
  }
  if (props.onSubmit) props.onSubmit(answers)
  hasSubmitted.value = true
}
</script>

<template>
  <div v-if="questions.length > 0"
    :class="['mb-4 rounded-[var(--radius-lg)] border overflow-hidden',
      hasSubmitted ? 'border-[var(--color-outline-variant)]/40 bg-[var(--color-surface-container-low)] opacity-70' : 'border-[var(--color-secondary)] bg-[var(--color-surface-container-lowest)]']">
    <!-- Header -->
    <div :class="['flex items-center gap-3 px-4 py-3', hasSubmitted ? 'bg-[var(--color-surface-container-low)]' : 'bg-[var(--color-surface-container)]']">
      <div class="flex items-center justify-center w-8 h-8 rounded-[var(--radius-md)] bg-[var(--color-secondary)]/10">
        <span class="material-symbols-outlined text-[18px] text-[var(--color-secondary)]">help</span>
      </div>
      <div class="flex-1 min-w-0">
        <span class="text-sm font-semibold text-[var(--color-text-primary)]">{{ t('question.needsInput') }}</span>
        <span v-if="hasSubmitted" class="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider bg-[var(--color-surface-container-high)] text-[var(--color-text-tertiary)]">
          {{ t('question.answered') }}
        </span>
      </div>
    </div>

    <!-- Tabs -->
    <div v-if="questions.length > 1" class="flex px-4 border-b border-[var(--color-outline-variant)]/20 bg-[var(--color-surface-container-low)] overflow-x-auto">
      <button v-for="(q, i) in questions" :key="i" @click="activeTab = i"
        :class="['relative flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium whitespace-nowrap transition-colors',
          safeActiveTab === i ? 'text-[var(--color-secondary)]' : 'text-[var(--color-text-tertiary)] hover:text-[var(--color-text-secondary)]']">
        <span v-if="freeTexts[i]?.trim() || (selections[i]?.length ?? 0) > 0" class="material-symbols-outlined text-[14px] text-[var(--color-success)]">check_circle</span>
        {{ q.header || `Q${i + 1}` }}
        <div v-if="safeActiveTab === i" class="absolute bottom-0 left-2 right-2 h-[2px] bg-[var(--color-secondary)] rounded-t" />
      </button>
    </div>

    <!-- Content -->
    <div class="px-4 py-3">
      <p class="text-sm font-medium text-[var(--color-text-primary)] mb-3">{{ activeQuestion?.question }}</p>

      <!-- Options -->
      <div v-if="activeQuestion?.options && activeQuestion.options.length > 0" class="space-y-2 mb-3">
        <button v-for="(opt, optIndex) in activeQuestion.options" :key="optIndex"
          @click="handleSelect(safeActiveTab, opt.label)" :disabled="hasSubmitted"
          :class="['w-full text-left px-4 py-3 rounded-[var(--radius-md)] border transition-all duration-150 cursor-pointer',
            (selections[safeActiveTab]?.includes(opt.label) ?? false)
              ? 'border-[var(--color-secondary)] bg-[var(--color-secondary)]/8 ring-1 ring-[var(--color-secondary)]/30'
              : 'border-[var(--color-outline-variant)]/40 bg-[var(--color-surface)] hover:border-[var(--color-outline-variant)] hover:bg-[var(--color-surface-container-low)]',
            hasSubmitted ? 'cursor-default' : '']">
          <div class="flex items-start gap-3">
            <div :class="['mt-0.5 flex-shrink-0 w-4 h-4 rounded-full border-2 flex items-center justify-center transition-colors',
              (selections[safeActiveTab]?.includes(opt.label) ?? false)
                ? 'border-[var(--color-secondary)] bg-[var(--color-secondary)]' : 'border-[var(--color-outline)]',
              activeQuestion.multiSelect ? 'rounded-[var(--radius-xs)]' : 'rounded-full']">
              <svg v-if="selections[safeActiveTab]?.includes(opt.label)" width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
            </div>
            <div class="flex-1 min-w-0">
              <span :class="['text-sm font-medium', (selections[safeActiveTab]?.includes(opt.label) ?? false) ? 'text-[var(--color-secondary)]' : 'text-[var(--color-text-primary)]']">{{ opt.label }}</span>
              <p v-if="opt.description" class="text-xs text-[var(--color-text-secondary)] mt-0.5">{{ opt.description }}</p>
            </div>
          </div>
        </button>
      </div>

      <!-- Free text -->
      <div v-if="!hasSubmitted">
        <label class="text-xs text-[var(--color-text-tertiary)] mb-1.5 block">{{ t('question.customResponse') }}</label>
        <textarea
          :value="freeTexts[safeActiveTab] ?? ''"
          @input="handleFreeTextChange(safeActiveTab, ($event.target as HTMLTextAreaElement).value)"
          :placeholder="t('question.typePlaceholder')"
          rows="3" wrap="soft"
          class="max-h-48 min-h-[84px] w-full resize-y rounded-[var(--radius-md)] border border-[var(--color-outline-variant)]/40 bg-[var(--color-surface)] px-3 py-2 text-sm leading-relaxed text-[var(--color-text-primary)] placeholder:text-[var(--color-text-tertiary)] focus:border-[var(--color-secondary)] focus:outline-none focus:ring-1 focus:ring-[var(--color-secondary)]/30" />
      </div>

      <!-- Submitted answer -->
      <div v-if="hasSubmitted" class="flex items-center gap-2 text-xs text-[var(--color-text-secondary)]">
        <span class="material-symbols-outlined text-[14px] text-[var(--color-success)]">check_circle</span>
        <span>{{ t('question.answeredPrefix') }}<strong>{{ questions.map((q, i) => freeTexts[i]?.trim() || (selections[i] || []).join(', ')).filter(Boolean).join('; ') }}</strong></span>
      </div>
    </div>

    <!-- Submit -->
    <div v-if="!hasSubmitted" class="flex items-center gap-2 px-4 py-3 border-t border-[var(--color-outline-variant)]/20 bg-[var(--color-surface-container-low)]">
      <button @click="handleSubmit" :disabled="!allAnswered"
        :class="['inline-flex items-center gap-1 rounded-[var(--radius-md)] px-3 py-1.5 text-[12px] font-medium transition-colors',
          allAnswered ? 'bg-[var(--color-brand)] text-white hover:bg-[var(--color-brand)]/85' : 'bg-[var(--color-surface-container)] text-[var(--color-text-tertiary)] cursor-not-allowed']">
        <span class="material-symbols-outlined text-[14px]">send</span>
        {{ t('question.submit') }}
      </button>
    </div>
  </div>
</template>
