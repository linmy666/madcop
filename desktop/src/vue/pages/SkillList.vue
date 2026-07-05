<script setup lang="ts">
import { useSkillStore } from '../stores/skillStore'
import { onMounted } from 'vue'

const skillStore = useSkillStore()

onMounted(() => {
  void skillStore.fetchSkills()
})
</script>

<template>
  <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
    <div v-if="skillStore.isLoading" class="flex justify-center py-12">
      <div class="animate-spin w-5 h-5 border-2 border-[var(--color-brand)] border-t-transparent rounded-full" />
    </div>
    <div v-else-if="skillStore.skills.length === 0" class="text-center py-12 text-[var(--color-text-tertiary)]">
      No skills available
    </div>
    <div v-else class="space-y-2">
      <div
        v-for="skill in skillStore.skills"
        :key="skill.id"
        class="flex items-center justify-between p-3 rounded-lg hover:bg-[var(--color-surface-container-low)] cursor-pointer transition-colors"
        @click="skillStore.selectSkill(skill)"
      >
        <div class="min-w-0">
          <div class="text-sm font-medium text-[var(--color-text-primary)] truncate">{{ skill.name }}</div>
          <div class="text-xs text-[var(--color-text-tertiary)] truncate">{{ skill.description }}</div>
        </div>
        <span class="text-[10px] uppercase tracking-wider text-[var(--color-text-tertiary)]">{{ skill.source }}</span>
      </div>
    </div>
  </div>
</template>