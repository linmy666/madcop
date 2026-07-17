<script setup lang="ts">
import { ref } from 'vue'
import { useSkillStore } from '../stores/skillStore'
import { useTranslation } from '../i18n'
import { useUIStore } from '../stores/uiStore'
import SkillList from './SkillList.vue'
import SkillDetail from './SkillDetail.vue'

const skillStore = useSkillStore()
const uiStore = useUIStore()
const t = useTranslation()

const showDistill = ref(false)
const distillTopic = ref('')
const distillQuery = ref('')
const distillAnswer = ref('')

async function runDistill() {
  if (!distillQuery.value.trim() || !distillAnswer.value.trim()) {
    uiStore.addToast({ type: 'error', message: t('settings.skills.distillNeedBoth') || '请填写问题与回答' })
    return
  }
  const name = await skillStore.distillFromExchange({
    topic: distillTopic.value.trim(),
    userQuery: distillQuery.value.trim(),
    assistantResponse: distillAnswer.value.trim(),
  })
  if (name) {
    uiStore.addToast({
      type: 'success',
      message: t('settings.skills.distillSuccess', { name }) || `已蒸馏技能：${name}`,
    })
    showDistill.value = false
    distillTopic.value = ''
    distillQuery.value = ''
    distillAnswer.value = ''
  } else {
    uiStore.addToast({
      type: 'error',
      message: skillStore.error || t('settings.skills.distillFailed') || '蒸馏失败',
    })
  }
}
</script>

<template>
  <div class="w-full min-w-0">
    <template v-if="skillStore.selectedSkill">
      <SkillDetail />
    </template>
    <template v-else>
      <section class="mb-5 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)]">
        <div class="flex flex-wrap items-start justify-between gap-3 px-5 py-5">
          <div class="min-w-0">
            <div class="mb-2 text-[11px] font-semibold tracking-wide text-[var(--color-text-tertiary)]">
              {{ t('settings.nav.ai') || 'AI' }}
            </div>
            <div class="mb-2 flex items-center gap-2">
              <span class="material-symbols-outlined text-[20px] text-[var(--color-brand)]" style="fontVariationSettings: 'FILL' 1">auto_awesome</span>
              <h2 class="text-lg font-semibold text-[var(--color-text-primary)]">
                {{ t('settings.skills.title') }}
              </h2>
            </div>
            <p class="max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">
              {{ t('settings.skills.description') }}
            </p>
          </div>
          <button
            type="button"
            class="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 text-xs font-medium text-[var(--color-text-primary)] shadow-sm transition-colors hover:bg-[var(--color-surface-hover)]"
            @click="showDistill = !showDistill"
          >
            <span class="material-symbols-outlined text-[16px]">auto_awesome</span>
            {{ t('settings.skills.distill') || '从对话蒸馏技能' }}
          </button>
        </div>
      </section>

      <div
        v-if="showDistill"
        class="mb-5 space-y-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-sm"
      >
        <p class="text-xs text-[var(--color-text-tertiary)] leading-relaxed">
          {{ t('settings.skills.distillHint') || '把一次「教我 / 怎么做」的问答落成 SKILL.md，之后相似问题可自动引用。' }}
        </p>
        <div>
          <label class="mb-1 block text-[11px] font-medium text-[var(--color-text-secondary)]">
            {{ t('settings.skills.distillTopic') || '主题（可选）' }}
          </label>
          <input
            v-model="distillTopic"
            type="text"
            class="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm outline-none focus:border-[var(--color-border-focus)]"
            :placeholder="t('settings.skills.distillTopicPh') || '例如：部署 FastAPI'"
          />
        </div>
        <div>
          <label class="mb-1 block text-[11px] font-medium text-[var(--color-text-secondary)]">
            {{ t('settings.skills.distillQuery') || '用户问题' }}
          </label>
          <textarea
            v-model="distillQuery"
            rows="2"
            class="w-full resize-y rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm outline-none focus:border-[var(--color-border-focus)]"
            :placeholder="t('settings.skills.distillQueryPh') || '教我如何…'"
          />
        </div>
        <div>
          <label class="mb-1 block text-[11px] font-medium text-[var(--color-text-secondary)]">
            {{ t('settings.skills.distillAnswer') || '助手回答' }}
          </label>
          <textarea
            v-model="distillAnswer"
            rows="5"
            class="w-full resize-y rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-sm outline-none focus:border-[var(--color-border-focus)]"
            :placeholder="t('settings.skills.distillAnswerPh') || '粘贴一段可复用的完整回答…'"
          />
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="inline-flex h-9 items-center gap-1.5 rounded-lg bg-[var(--color-brand)] px-3 text-xs font-medium text-white disabled:opacity-50"
            :disabled="skillStore.isDistilling"
            @click="runDistill"
          >
            <span v-if="skillStore.isDistilling" class="material-symbols-outlined animate-spin text-[16px]">progress_activity</span>
            {{ skillStore.isDistilling
              ? (t('common.loading') || '处理中…')
              : (t('settings.skills.distillSubmit') || '蒸馏为技能') }}
          </button>
          <button
            type="button"
            class="inline-flex h-9 items-center rounded-lg px-3 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
            @click="showDistill = false"
          >
            {{ t('common.cancel') || '取消' }}
          </button>
        </div>
      </div>

      <SkillList />
    </template>
  </div>
</template>
