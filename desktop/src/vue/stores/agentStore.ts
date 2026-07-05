import { defineStore } from 'pinia'
import { agentsApi, type AgentDefinition } from '../../api/agents'

export type AgentSource =
  | 'built-in'
  | 'plugin'
  | 'userSettings'
  | 'projectSettings'
  | 'localSettings'
  | 'flagSettings'
  | 'policySettings'

export type AgentDetailReturnTab = 'agents' | 'plugins'

export type AgentStoreState = {
  activeAgents: AgentDefinition[]
  allAgents: AgentDefinition[]
  isLoading: boolean
  error: string | null
  selectedAgent: AgentDefinition | null
  selectedAgentReturnTab: AgentDetailReturnTab
}

export const useAgentStore = defineStore('agent', {
  state: (): AgentStoreState => ({
    activeAgents: [],
    allAgents: [],
    isLoading: false,
    error: null,
    selectedAgent: null,
    selectedAgentReturnTab: 'agents',
  }),

  getters: {
    activeAgentsCount: (state) => state.activeAgents.length,
    allAgentsCount: (state) => state.allAgents.length,
  },

  actions: {
    async fetchAgents(cwd?: string) {
      this.isLoading = true
      this.error = null
      try {
        const response = await agentsApi.list(cwd)
        this.activeAgents = response.activeAgents
        this.allAgents = response.allAgents
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to load agents'
        this.error = message
      }
      this.isLoading = false
    },

    selectAgent(agent: AgentDefinition | null, returnTab: AgentDetailReturnTab = 'agents') {
      this.selectedAgent = agent
      this.selectedAgentReturnTab = agent ? returnTab : 'agents'
    },
  },
})
