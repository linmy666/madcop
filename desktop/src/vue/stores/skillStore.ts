import { defineStore } from 'pinia'

export interface SkillDefinition {
  id: string
  name: string
  description: string
  enabled: boolean
  source: string
}

export const useSkillStore = defineStore('skill', {
  state: () => ({
    skills: [] as SkillDefinition[],
    selectedSkill: null as SkillDefinition | null,
    isLoading: false,
    error: null as string | null,
  }),
  actions: {
    async fetchSkills() {
      this.isLoading = true
      this.error = null
      try {
        // TODO: wire to backend API
        await new Promise((resolve) => setTimeout(resolve, 200))
      } catch (e: any) {
        this.error = e.message
      } finally {
        this.isLoading = false
      }
    },
    selectSkill(skill: SkillDefinition | null) {
      this.selectedSkill = skill
    },
  },
})