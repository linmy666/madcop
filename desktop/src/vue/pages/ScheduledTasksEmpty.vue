<script setup lang="ts">
/**
 * ScheduledTasksEmpty — Vue 3 port of pages/ScheduledTasksEmpty.tsx
 * Empty state page for scheduled tasks. Uses mock data.
 * Self-contained demo page.
 */

const statusBar = {
  user: 'MadCop',
  username: 'dev',
  plan: 'Pro',
  branch: 'main',
  worktreeToggle: 'Worktree',
  localSwitch: 'Local',
}

const t = (key: string) => key // identity translation for demo
</script>

<template>
  <div class="bg-[var(--color-background)] text-[var(--color-text-primary)] flex min-h-screen font-[Inter,sans-serif]">
    <!-- Sidebar -->
    <aside class="fixed left-0 top-0 h-full w-[280px] bg-[var(--color-surface-container-low)] flex flex-col p-4 gap-2 text-sm font-medium z-40">
      <div class="flex items-center gap-3 px-2 mb-6 mt-12">
        <div class="w-8 h-8 rounded bg-[var(--color-surface-container-highest)] flex items-center justify-center">
          <span class="material-symbols-outlined text-[var(--color-text-tertiary)]">filter_list</span>
        </div>
        <div>
          <div class="text-[var(--color-text-primary)] font-bold">All Projects</div>
          <div class="text-[10px] text-[var(--color-text-tertiary)] uppercase tracking-widest">Active Session</div>
        </div>
      </div>
      <nav class="flex-1 space-y-1">
        <div class="px-3 py-2 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] transition-all rounded-lg cursor-pointer duration-200 ease-in-out flex items-center gap-3">
          <span class="material-symbols-outlined">add</span><span>New Session</span>
        </div>
        <div class="px-3 py-2 bg-[var(--color-background)] text-[var(--color-text-primary)] rounded-lg relative before:content-[''] before:absolute before:left-[-8px] before:w-1 before:h-4 before:bg-[var(--color-brand)] before:rounded-full cursor-pointer duration-200 ease-in-out flex items-center gap-3">
          <span class="material-symbols-outlined">calendar_today</span><span>Scheduled</span>
        </div>
        <div class="px-3 py-2 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] transition-all rounded-lg cursor-pointer duration-200 ease-in-out flex items-center gap-3">
          <span class="material-symbols-outlined">history</span><span>Today</span>
        </div>
        <div class="px-3 py-2 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] transition-all rounded-lg cursor-pointer duration-200 ease-in-out flex items-center gap-3">
          <span class="material-symbols-outlined">event_note</span><span>Last 7 days</span>
        </div>
        <div class="px-3 py-2 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] transition-all rounded-lg cursor-pointer duration-200 ease-in-out flex items-center gap-3">
          <span class="material-symbols-outlined">archive</span><span>Older</span>
        </div>
      </nav>
      <div class="mt-auto pt-4 border-t border-[var(--color-border)]/10">
        <div class="text-[10px] text-[var(--color-text-tertiary)] uppercase tracking-widest px-3 mb-2">Execution Mode</div>
        <div class="px-3 py-2 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] transition-all rounded-lg cursor-pointer duration-200 ease-in-out flex items-center gap-3">
          <span class="material-symbols-outlined">computer</span><span>Local</span>
        </div>
        <div class="px-3 py-2 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] transition-all rounded-lg cursor-pointer duration-200 ease-in-out flex items-center gap-3">
          <span class="material-symbols-outlined">cloud</span><span>Remote</span>
        </div>
      </div>
    </aside>

    <!-- Main -->
    <main class="flex-1 ml-[280px] flex flex-col min-h-screen">
      <header class="fixed top-0 right-0 left-[280px] z-30 bg-[var(--color-background)] flex justify-between items-center px-6 h-12 w-full border-b border-[var(--color-border)]">
        <div class="flex items-center gap-6 h-full">
          <div class="text-sm font-bold text-[var(--color-text-primary)] uppercase tracking-tighter font-[Manrope,sans-serif]">MadCop Agent Companion</div>
          <nav class="flex items-center gap-4 h-full font-[Manrope,sans-serif] font-semibold tracking-wide text-sm">
            <span class="text-[var(--color-text-tertiary)] hover:text-[var(--color-brand)] transition-colors cursor-pointer h-full flex items-center">Code</span>
            <span class="text-[var(--color-text-tertiary)] hover:text-[var(--color-brand)] transition-colors cursor-pointer h-full flex items-center">Terminal</span>
            <span class="text-[var(--color-text-primary)] border-b-2 border-[var(--color-brand)] pb-1 h-full flex items-center pt-1">History</span>
          </nav>
        </div>
        <div class="flex items-center gap-4">
          <div class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[var(--color-text-tertiary)] text-sm cursor-pointer">arrow_back_ios</span>
            <span class="material-symbols-outlined text-[var(--color-text-tertiary)] text-sm cursor-pointer">arrow_forward_ios</span>
          </div>
          <div class="h-4 w-[1px] bg-[var(--color-text-tertiary)]/20"></div>
          <div class="text-[var(--color-text-tertiary)] hover:text-[var(--color-brand)] transition-colors cursor-pointer text-xs font-semibold uppercase tracking-wider">Settings</div>
        </div>
      </header>

      <div class="flex-1 mt-12 mb-8 flex flex-col items-center justify-center p-8 bg-[var(--color-background)]">
        <div class="max-w-2xl w-full text-center">
          <h1 class="text-3xl font-[Manrope,sans-serif] font-extrabold text-[var(--color-text-primary)] tracking-tight mb-16">Scheduled Tasks</h1>
          <div class="relative group">
            <div class="absolute -inset-4 bg-[var(--color-surface-container-low)] rounded-[32px] -z-10 transition-all"></div>
            <div class="flex flex-col items-center py-20 px-8">
              <div class="w-32 h-32 rounded-full bg-[var(--color-surface-container-high)] flex items-center justify-center mb-10 shadow-sm">
                <div class="w-20 h-20 rounded-full bg-[var(--color-surface-container-lowest)] flex items-center justify-center border border-[var(--color-border)]/10">
                  <span class="material-symbols-outlined text-[var(--color-brand)] text-5xl" style="fontVariationSettings: "'wght' 300"">schedule</span>
                </div>
              </div>
              <p class="text-[var(--color-text-secondary)] font-[Inter,sans-serif] text-lg max-w-sm mx-auto leading-relaxed mb-12">
                You don't have any scheduled tasks yet. Create your first one to automate your workflow.
              </p>
              <button class="group relative px-8 py-4 bg-[var(--color-brand)] text-white rounded-xl font-[Manrope,sans-serif] font-bold text-sm tracking-wide shadow-lg hover:shadow-[var(--color-brand)]/20 transition-all flex items-center gap-3 overflow-hidden">
                <div class="absolute inset-0 bg-gradient-to-b from-white/10 to-transparent opacity-30"></div>
                <span class="material-symbols-outlined text-lg">add_task</span>
                <span>Create Task</span>
              </button>
            </div>
          </div>
          <div class="grid grid-cols-3 gap-4 mt-20 opacity-40">
            <div class="h-24 bg-[var(--color-surface-container-low)] rounded-xl border border-[var(--color-border)]/10 flex flex-col items-center justify-center p-4">
              <span class="material-symbols-outlined text-[var(--color-text-tertiary)] mb-2">commit</span>
              <div class="w-12 h-1 bg-[var(--color-border)]/30 rounded-full"></div>
            </div>
            <div class="h-24 bg-[var(--color-surface-container-low)] rounded-xl border border-[var(--color-border)]/10 flex flex-col items-center justify-center p-4">
              <span class="material-symbols-outlined text-[var(--color-text-tertiary)] mb-2">terminal</span>
              <div class="w-8 h-1 bg-[var(--color-border)]/30 rounded-full"></div>
            </div>
            <div class="h-24 bg-[var(--color-surface-container-low)] rounded-xl border border-[var(--color-border)]/10 flex flex-col items-center justify-center p-4">
              <span class="material-symbols-outlined text-[var(--color-text-tertiary)] mb-2">code_blocks</span>
              <div class="w-10 h-1 bg-[var(--color-border)]/30 rounded-full"></div>
            </div>
          </div>
        </div>
      </div>

      <footer class="fixed bottom-0 left-0 w-full h-8 bg-[var(--color-background)] flex items-center justify-between px-4 z-50 border-t border-[var(--color-border)]/20 font-[Inter,sans-serif] text-xs tracking-tight">
        <div class="flex items-center gap-3 text>[var(--color-text-tertiary)]">
          <div class="w-2 h-2 rounded-full bg-[var(--color-success)]"></div>
          <span>{{ statusBar.user }} &bull; {{ statusBar.username }} &bull; {{ statusBar.plan }}</span>
        </div>
        <div class="flex items-center gap-6">
          <span class="text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-container-low)] px-2 py-0.5 rounded transition-colors cursor-pointer flex items-center gap-1">
            <span class="material-symbols-outlined text-[14px]">account_tree</span>{{ statusBar.branch }}
          </span>
          <span class="text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-container-low)] px-2 py-0.5 rounded transition-colors cursor-pointer flex items-center gap-1">
            <span class="material-symbols-outlined text-[14px]">workspaces</span>{{ statusBar.worktreeToggle }}
          </span>
          <span class="text-[var(--color-brand)] font-bold hover:bg-[var(--color-surface-container-low)] px-2 py-0.5 rounded transition-colors cursor-pointer flex items-center gap-1">
            <span class="material-symbols-outlined text-[14px]">toggle_on</span>{{ statusBar.localSwitch }}
          </span>
        </div>
      </footer>
    </main>
  </div>
</template>
