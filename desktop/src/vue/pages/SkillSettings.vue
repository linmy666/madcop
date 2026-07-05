<script setup lang="ts">
import { useSkillStore } from '../stores/skillStore'
import { useTranslation } from '../i18n'
import SkillList from './SkillList.vue'
import SkillDetail from './SkillDetail.vue'

const skillStore = useSkillStore()
const t = useTranslation()
</script>

<template>
  <div class="w-full min-w-0">
    <template v-if="skillStore.selectedSkill">
      <SkillDetail />
    </template>
    <template v-else>
      <h2 class="text-base font-semibold text-[var(--color-text-primary)] mb-1">
        {{ t('settings.skills.title') }}
      </h2>
      <p class="text-sm text-[var(--color-text-tertiary)] mb-4">
        {{ t('settings.skills.description') }}
      </p>
      <SkillList />
    </template>
  </div>
</template>