import { defineStore } from 'pinia'

/**
 * Skill source categories — mirrors the React app's SkillSource union.
 */
export type SkillSource = 'user' | 'project' | 'plugin' | 'mcp' | 'bundled'

/**
 * Rich skill metadata — matches the React app's SkillMeta shape so pages
 * like SkillList can render all fields (displayName, version, pluginName,
 * contentLength, hasDirectory, userInvocable) without casting.
 */
export interface SkillDefinition {
  id: string
  name: string
  displayName: string
  description: string
  enabled: boolean
  source: SkillSource
  version?: string
  pluginName?: string
  contentLength: number
  hasDirectory: boolean
  userInvocable: boolean
}

export const useSkillStore = defineStore('skill', {
  state: () => ({
    skills: [] as SkillDefinition[],
    selectedSkill: null as SkillDefinition | null,
    isLoading: false,
    error: null as string | null,
  }),
  actions: {
    async fetchSkills(_workDir?: string) {
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
    async fetchSkillDetail(
      _source: SkillSource,
      _name: string,
      _workDir?: string,
      _section?: string,
    ) {
      // TODO: wire to backend API
    },
    selectSkill(skill: SkillDefinition | null) {
      this.selectedSkill = skill
    },
    getState() {
      return { selectedSkill: this.selectedSkill, error: this.error }
    },
  },
})