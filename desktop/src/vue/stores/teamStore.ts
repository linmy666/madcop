import { defineStore } from 'pinia'

/**
 * Pinia mirror of stores/teamStore.ts
 * Agent team management.
 */

export type TeamMember = {
  id: string
  role: string
  status: string
  color?: string
}

export type Team = {
  id: string
  name: string
  members: TeamMember[]
  active: boolean
}

export const useTeamStore = defineStore('team', {
  state: () => ({
    teams: [] as Team[],
    activeTeam: null as Team | null,
    memberColors: {} as Record<string, string>,
    error: null as string | null,
  }),

  actions: {
    async fetchTeams() {
      this.error = null
      try {
        this.teams = [
          { id: '1', name: 'dev-cluster', members: [
            { id: '1', role: 'Architect', status: 'completed' },
            { id: '2', role: 'Coder', status: 'running' },
            { id: '3', role: 'Reviewer', status: 'queued' },
            { id: '4', role: 'Tester', status: 'queued' },
          ], active: true },
        ]
        this.activeTeam = this.teams[0] || null
      } catch (err) {
        this.error = err instanceof Error ? err.message : String(err)
      }
    },
    setActiveTeam(team: Team | null) {
      this.activeTeam = team
    },
    getMemberBySessionId(_sessionId: string): TeamMember | null {
      return this.activeTeam?.members[0] || null
    },
  },
})
