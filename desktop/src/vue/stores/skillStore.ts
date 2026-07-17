import { defineStore } from 'pinia'
import { getApiUrl } from '../api/client'

/**
 * Skill source categories — mirrors the React app's SkillSource union.
 */
export type SkillSource = 'user' | 'project' | 'plugin' | 'mcp' | 'bundled'

/**
 * Rich skill metadata — matches the React app's SkillMeta shape so pages
 * like SkillList can render all fields without casting.
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

function normalizeSkill(raw: any, index: number): SkillDefinition {
  const name = raw?.name || raw?.id || `skill-${index}`
  const source = (raw?.source || 'user') as SkillSource
  return {
    id: raw?.id || `${source}:${name}`,
    name,
    displayName: raw?.displayName || raw?.title || name,
    description: raw?.description || '',
    enabled: raw?.enabled !== false,
    source,
    version: raw?.version,
    pluginName: raw?.pluginName,
    contentLength: Number(raw?.contentLength ?? raw?.content_length ?? 0),
    hasDirectory: Boolean(raw?.hasDirectory),
    userInvocable: raw?.userInvocable !== false,
  }
}

export const useSkillStore = defineStore('skill', {
  state: () => ({
    skills: [] as SkillDefinition[],
    selectedSkill: null as SkillDefinition | null,
    isLoading: false,
    isDistilling: false,
    error: null as string | null,
    lastDistillName: null as string | null,
  }),
  actions: {
    async fetchSkills(_workDir?: string) {
      this.isLoading = true
      this.error = null
      try {
        const res = await fetch(getApiUrl('/api/skills'))
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        const list = Array.isArray(data?.skills)
          ? data.skills
          : Array.isArray(data)
            ? data
            : []
        this.skills = list.map((s: any, i: number) => normalizeSkill(s, i))
      } catch (e: any) {
        this.error = e?.message || String(e)
        this.skills = []
      } finally {
        this.isLoading = false
      }
    },
    async fetchSkillDetail(
      source: SkillSource,
      name: string,
      _workDir?: string,
      _section?: string,
    ) {
      this.error = null
      try {
        const q = new URLSearchParams({ name, source })
        const res = await fetch(getApiUrl(`/api/skills/detail?${q}`))
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data = await res.json()
        const meta = data?.meta || data
        if (meta) {
          this.selectedSkill = normalizeSkill({ ...meta, source }, 0)
        }
        return data
      } catch (e: any) {
        this.error = e?.message || String(e)
        return null
      }
    },
    /**
     * Manually distill a SKILL.md from a user/assistant exchange
     * (POST /api/skills/distill).
     */
    async distillFromExchange(payload: {
      topic?: string
      userQuery: string
      assistantResponse: string
    }) {
      this.isDistilling = true
      this.error = null
      this.lastDistillName = null
      try {
        const res = await fetch(getApiUrl('/api/skills/distill'), {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            topic: payload.topic || '',
            userQuery: payload.userQuery,
            assistantResponse: payload.assistantResponse,
          }),
        })
        const data = await res.json().catch(() => ({}))
        if (!res.ok || data?.ok === false) {
          throw new Error(data?.error || `HTTP ${res.status}`)
        }
        this.lastDistillName = data?.skillName || null
        await this.fetchSkills()
        return data?.skillName as string | null
      } catch (e: any) {
        this.error = e?.message || String(e)
        return null
      } finally {
        this.isDistilling = false
      }
    },
    selectSkill(skill: SkillDefinition | null) {
      this.selectedSkill = skill
    },
    getState() {
      return { selectedSkill: this.selectedSkill, error: this.error }
    },
  },
})
