<script setup lang="ts">
import { ref } from 'vue'

/**
 * AgentTeams — Vue 3 port of pages/AgentTeams.tsx
 * Mock demo page showing a team of AI agents collaborating.
 * Self-contained with mock data.
 */

const inputValue = ref('')
const mockTeam = {
  name: 'dev-cluster',
  memberCount: 4,
  members: [
    { id: '1', role: 'Architect', status: 'completed' },
    { id: '2', role: 'Coder', status: 'running' },
    { id: '3', role: 'Reviewer', status: 'queued' },
    { id: '4', role: 'Tester', status: 'queued' },
  ],
}
const mockMessages = {
  userMessage: 'Refactor the authentication service to use OAuth2 PKCE.',
  assistantMessage: 'Understood. I will coordinate a team to handle this refactoring in parallel.',
}
</script>

<template>
  <div class="flex-1 flex flex-col relative overflow-hidden bg-[var(--color-surface)] text-[var(--color-text-primary)]" style="font-family: var(--font-body)">
    <style>
    @keyframes pulse-subtle {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.7; transform: scale(0.98); }
    }
    .animate-pulse-subtle { animation: pulse-subtle 2s ease-in-out infinite; }
    </style>

    <div class="flex-1 overflow-y-auto p-6 md:p-10 max-w-5xl mx-auto w-full">
      <div class="space-y-8">
        <!-- Message Thread -->
        <div class="space-y-6">
          <div class="flex gap-4 group">
            <div class="w-8 h-8 rounded-full bg-[var(--color-primary-fixed)] flex-shrink-0 flex items-center justify-center text-[var(--color-on-primary)] font-bold text-xs">U</div>
            <div class="space-y-2">
              <p class="text-xs font-semibold text-[var(--color-text-tertiary)] uppercase tracking-widest">User</p>
              <p class="text-[var(--color-text-primary)] leading-relaxed">{{ mockMessages.userMessage }}</p>
            </div>
          </div>
          <div class="flex gap-4 group">
            <div class="w-8 h-8 rounded-full bg-[var(--color-tertiary-container)] flex-shrink-0 flex items-center justify-center text-[var(--color-tertiary)]">
              <span class="material-symbols-outlined text-sm" style="fontVariationSettings: 'FILL' 1">smart_toy</span>
            </div>
            <div class="space-y-4 flex-1">
              <p class="text-xs font-semibold text-[var(--color-text-tertiary)] uppercase tracking-widest">MadCop Agent</p>
              <div class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)] p-5 shadow-[var(--shadow-dropdown)]">
                <p class="mb-4 text-[var(--color-text-primary)]">{{ mockMessages.assistantMessage }}</p>
                <div class="rounded-lg bg-[var(--color-surface-container-high)] p-4 font-[var(--font-mono)] text-[13px] text-[var(--color-text-secondary)] overflow-x-auto">
                  <span class="text-[var(--color-brand)]">info:</span> spawning child_processes for parallel development<br />
                  <span class="text-[var(--color-secondary)]">active:</span> session-dev cluster initiated<br />
                  <span class="text-[var(--color-tertiary)]">ready:</span> 4 agents assigned
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Team Strip -->
        <div class="relative py-8">
          <div class="absolute inset-x-0 top-1/2 -translate-y-1/2 h-px bg-[var(--color-border-separator)]" />
          <div class="relative glass-panel p-4 rounded-2xl flex flex-col md:flex-row md:items-center gap-4 overflow-hidden">
            <div class="flex items-center gap-3 pr-4 md:border-r border-[var(--color-border-separator)]">
              <div class="p-2 bg-[var(--color-primary-fixed)]/20 rounded-lg">
                <span class="material-symbols-outlined text-[var(--color-brand)] text-xl">groups</span>
              </div>
              <div>
                <h3 class="text-sm font-bold text-[var(--color-text-primary)]" style="font-family: var(--font-headline)">Team: {{ mockTeam.name }}</h3>
                <p class="text-[11px] font-medium text-[var(--color-text-tertiary)] uppercase tracking-tighter">{{ mockTeam.memberCount }} members</p>
              </div>
            </div>
            <div class="flex flex-wrap gap-2 items-center flex-1">
              <div v-for="member in mockTeam.members" :key="member.id"
                :class="[
                  'flex items-center gap-2 px-3 py-1.5 rounded-full border cursor-pointer transition-all',
                  member.status === 'completed' ? 'bg-[var(--color-surface-container-high)] border-[var(--color-success)]/20 hover:border-[var(--color-success)]/50' :
                  member.status === 'running' ? 'bg-[var(--color-surface-container-high)] border-[var(--color-brand)]/20 animate-pulse-subtle hover:border-[var(--color-brand)]/50' :
                  'bg-[var(--color-surface-container-low)] border-[var(--color-border)] grayscale hover:grayscale-0 hover:border-[var(--color-secondary)]/50'
                ]">
                <div :class="['w-2 h-2 rounded-full', member.status === 'completed' ? 'bg-[var(--color-success)]' : member.status === 'running' ? 'bg-[var(--color-warning)]' : 'bg-[var(--color-text-tertiary)]']" />
                <span :class="['text-xs font-semibold', member.status === 'completed' || member.status === 'running' ? 'text-[var(--color-text-primary)]' : 'text-[var(--color-text-tertiary)]']">{{ member.role }}</span>
                <span :class="['material-symbols-outlined text-[14px]', member.status === 'completed' ? 'text-[var(--color-success)]' : member.status === 'running' ? 'text-[var(--color-warning)]' : 'text-[var(--color-text-tertiary)]']"
                  :style="{ fontVariationSettings: member.status === 'running' || member.status === 'completed' ? "'FILL' 1" : undefined }">
                  {{ member.status === 'completed' ? 'check_circle' : member.status === 'running' ? 'sync' : (member.role === 'Tester' ? 'schedule' : 'pause_circle') }}
                </span>
              </div>
            </div>
            <button class="ml-auto p-2 hover:bg-[var(--color-surface-hover)] rounded-full transition-colors text-[var(--color-text-tertiary)]">
              <span class="material-symbols-outlined text-sm">expand_more</span>
            </button>
          </div>
        </div>

        <!-- Chat Composer -->
        <div class="max-w-3xl mx-auto w-full mt-auto">
          <div class="glass-panel relative rounded-xl p-1.5 flex items-center gap-2 transition-all">
            <div class="p-2 text-[var(--color-text-secondary)]"><span class="material-symbols-outlined">attach_file</span></div>
            <input class="flex-1 bg-transparent border-none focus:ring-0 focus:outline-none text-sm text-[var(--color-text-primary)] py-2"
              placeholder="Type a command or ask MadCop..." type="text" v-model="inputValue" />
            <button class="bg-[image:var(--gradient-btn-primary)] text-[var(--color-btn-primary-fg)] shadow-[var(--shadow-button-primary)] w-9 h-9 rounded-lg flex items-center justify-center transition-all hover:brightness-105 active:scale-95">
              <span class="material-symbols-outlined text-lg" style="fontVariationSettings: 'FILL' 1">send</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
