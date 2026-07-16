<script setup lang="ts">
/**
 * SessionControls — Vue 3 port of pages/SessionControls.tsx
 * Full-page demo component: sidebar + header + chat + controls + composer + footer.
 * Self-contained with mock data (inlined to avoid cross-import path issues).
 */

import { ref } from 'vue'

/* ────────────────────────────────────────────────────────────────────
   Mock data (inlined from ../mocks/data)
   ──────────────────────────────────────────────────────────────────── */
const mockSessions = {
  today: [
    { id: 's1', title: 'Refactor login flow' },
    { id: 's2', title: 'Fix CSS responsive layout' },
  ],
  previous7Days: [
    { id: 's3', title: 'Add user authentication' },
    { id: 's4', title: 'Database migration script' },
  ],
  older: [
    { id: 's5', title: 'Initial project setup' },
  ],
}

const mockPermissionModes = [
  { id: 'ask',    label: 'Ask permissions',        description: 'Confirm every file edit or terminal command.',    icon: 'lock' },
  { id: 'auto',   label: 'Auto accept edits',      description: 'MadCop writes to disk without asking.',             icon: 'edit_note' },
  { id: 'plan',   label: 'Plan mode',              description: 'Architecture & reasoning only. No writes.',          icon: 'architecture' },
  { id: 'bypass', label: 'Bypass permissions',     description: 'Full root access for shell and file system.',        icon: 'warning' },
]

const mockModels = [
  { id: 'opus',   name: 'Opus 4.7',   active: false },
  { id: 'sonnet', name: 'Sonnet 4.6', active: true  },
  { id: 'haiku',  name: 'Haiku 4.5',  active: false },
]

const mockEffortLevels = ['Low', 'Medium', 'High', 'Max']

const mockStatusBar = {
  user: 'User Avatar',
  username: 'username',
  plan: 'Pro Plan',
  branch: 'main-branch',
  worktreeToggle: 'worktree-toggle',
  localSwitch: 'local-switch',
}

/* ────────────────────────────────────────────────────────────────────
   Icon lookup tables
   ──────────────────────────────────────────────────────────────────── */
const permissionIcons: Record<string, { icon: string; color: string }> = {
  ask:    { icon: 'verified_user', color: 'text-outline' },
  auto:   { icon: 'bolt',          color: 'text-outline' },
  plan:   { icon: 'architecture',  color: 'text-tertiary' },
  bypass: { icon: 'gavel',         color: 'text-error' },
}

const modelIcons: Record<string, string> = {
  opus:   'psychology',
  sonnet: 'smart_toy',
  haiku:  'auto_awesome',
}

/* ────────────────────────────────────────────────────────────────────
   Reactive state (useState → ref)
   ──────────────────────────────────────────────────────────────────── */
const selectedPermission = ref('ask')
const selectedModel      = ref('sonnet')
const selectedEffort     = ref('Medium')
const showPermissions    = ref(true)
const showModelConfig    = ref(true)

/* ────────────────────────────────────────────────────────────────────
   Computed helpers
   ──────────────────────────────────────────────────────────────────── */
const activeModel = () => mockModels.find((m) => m.id === selectedModel.value)

const togglePermissions = () => { showPermissions.value = !showPermissions.value }
const toggleModelConfig = () => { showModelConfig.value  = !showModelConfig.value  }
</script>

<template>
  <div
    class="h-screen w-screen bg-background text-on-surface font-body selection:bg-primary-fixed overflow-hidden relative"
  >
    <!-- ═══════════════════════════════════════════════════════════════
         TopAppBar
         ═══════════════════════════════════════════════════════════════ -->
    <header
      class="bg-[var(--color-background)] font-headline font-semibold tracking-wide text-sm fixed top-0 left-0 right-0 flex justify-between items-center px-6 h-12 z-40"
    >
      <div class="flex items-center gap-6">
        <span
          class="text-sm font-bold text-[var(--color-text-primary)] uppercase tracking-tighter"
        >
          MadCop Agent Companion
        </span>
        <nav class="hidden md:flex gap-4">
          <a
            class="text-[var(--color-text-primary)] border-b-2 border-[var(--color-brand)] pb-1 cursor-pointer active:opacity-70"
          >
            Code
          </a>
          <a
            class="text-[var(--color-text-tertiary)] hover:text-[var(--color-brand)] transition-colors cursor-pointer active:opacity-70"
          >
            Terminal
          </a>
          <a
            class="text-[var(--color-text-tertiary)] hover:text-[var(--color-brand)] transition-colors cursor-pointer active:opacity-70"
          >
            History
          </a>
        </nav>
      </div>
      <div class="flex items-center gap-3">
        <span class="material-symbols-outlined text-[var(--color-text-tertiary)] cursor-pointer">
          arrow_back_ios
        </span>
        <span class="material-symbols-outlined text-[var(--color-text-tertiary)] cursor-pointer">
          arrow_forward_ios
        </span>
        <button
          class="ml-2 px-3 py-1 bg-surface-container-high rounded text-[var(--color-brand)] hover:bg-surface-container-highest transition-colors"
        >
          Settings
        </button>
      </div>
    </header>

    <!-- Separator line -->
    <div class="bg-[var(--color-surface-container-low)] h-[1px] w-full fixed top-12 z-40" />

    <!-- ═══════════════════════════════════════════════════════════════
         SideNavBar
         ═══════════════════════════════════════════════════════════════ -->
    <aside
      class="bg-[var(--color-surface-container-low)] font-body text-sm font-medium fixed left-0 top-0 h-full w-[280px] hidden md:flex flex-col p-4 gap-2 pt-16 z-30"
    >
      <!-- Project header -->
      <div class="px-2 mb-4">
        <div class="flex items-center gap-3 mb-1">
          <img
            class="w-8 h-8 rounded-full"
            src="https://lh3.googleusercontent.com/aida-public/AB6AXuCjFls9oDx5jX7Zv8P7BA9QbodBzvDJFhVNIiVjAhp_OhnXT6lmE-uYCDDZvNS4kWHssfxAYuiH05KsXLBWgLd4K-8prrjodVjSsKAG1LhvKWN90nyVzDBSrreWkpW7reNC1N_T4J_Pdr9mgAYVwYRS10nvUMZs_ajpTg2CoTtMkQRRGZGZXLk_gU94EoaeDEPNbvwaxOeeTeGgOxwnzcPIUn6EFzqc5Bjug00IDIrhRYiuwEaGNkTuz39mNFxJl2bKiHES5HxUM60"
            alt="project avatar"
          />
          <div>
            <h3 class="text-on-surface font-bold leading-none">All projects</h3>
            <p class="text-[10px] text-outline uppercase tracking-widest mt-1">
              Active Session
            </p>
          </div>
        </div>
      </div>

      <!-- Nav items -->
      <button
        class="w-full text-left p-2.5 bg-[var(--color-background)] text-[var(--color-text-primary)] rounded-lg relative before:content-[''] before:absolute before:left-[-8px] before:w-1 before:h-4 before:bg-[var(--color-brand)] before:rounded-full before:top-1/2 before:-translate-y-1/2 transition-all duration-200 ease-in-out flex items-center gap-3"
      >
        <span class="material-symbols-outlined text-[var(--color-brand)]">add</span>
        <span>New session</span>
      </button>
      <button
        class="w-full text-left p-2.5 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] rounded-lg transition-all duration-200 ease-in-out flex items-center gap-3"
      >
        <span class="material-symbols-outlined">calendar_today</span>
        <span>Scheduled</span>
      </button>
      <button
        class="w-full text-left p-2.5 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] rounded-lg transition-all duration-200 ease-in-out flex items-center gap-3"
        :data-count="mockSessions.today.length"
      >
        <span class="material-symbols-outlined">history</span>
        <span>Today</span>
      </button>
      <button
        class="w-full text-left p-2.5 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] rounded-lg transition-all duration-200 ease-in-out flex items-center gap-3"
        :data-count="mockSessions.previous7Days.length"
      >
        <span class="material-symbols-outlined">event_note</span>
        <span>Previous 7 Days</span>
      </button>
      <button
        class="w-full text-left p-2.5 text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-hover)] rounded-lg transition-all duration-200 ease-in-out flex items-center gap-3"
        :data-count="mockSessions.older.length"
      >
        <span class="material-symbols-outlined">archive</span>
        <span>Older</span>
      </button>

      <!-- Bottom modes -->
      <div class="mt-auto pt-4 border-t border-outline/10 flex flex-col gap-1">
        <button class="flex items-center gap-3 p-2 text-outline hover:text-primary transition-colors">
          <span class="material-symbols-outlined text-xs">computer</span>
          <span class="text-xs">Local Mode</span>
        </button>
        <button class="flex items-center gap-3 p-2 text-outline hover:text-primary transition-colors">
          <span class="material-symbols-outlined text-xs">cloud</span>
          <span class="text-xs">Remote Mode</span>
        </button>
      </div>
    </aside>

    <!-- ═══════════════════════════════════════════════════════════════
         Main Content Area (blurred / dimmed behind overlays)
         ═══════════════════════════════════════════════════════════════ -->
    <main class="md:ml-[280px] pt-12 pb-8 min-h-screen blur-[2px] opacity-60">
      <div class="max-w-4xl mx-auto px-8 py-12">
        <div class="grid grid-cols-12 gap-6">
          <!-- Main Thread -->
          <div class="col-span-8 space-y-8">
            <!-- AI message -->
            <div class="bg-surface-container-low rounded-xl p-6">
              <div class="flex items-center gap-3 mb-4">
                <div
                  class="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-on-primary font_BOLD text-xs"
                >
                  AI
                </div>
                <span class="font-semibold text-sm">MadCop 默认模型</span>
              </div>
              <p class="text-on-surface-variant leading-relaxed">
                I've analyzed the
                <code class="bg-surface-dim px-1.5 py-0.5 rounded font-mono text-sm">
                  auth_provider.go
                </code>
                file. The race condition occurs during the token refresh cycle. I recommend
                wrapping the session update in a mutex lock.
              </p>
            </div>

            <!-- User message -->
            <div class="flex justify-end">
              <div class="bg-surface-container-highest rounded-xl p-6 max-w-[80%]">
                <p class="text-on-surface leading-relaxed">
                  Can you implement that? Also check if this affects the WebSocket connection
                  longevity.
                </p>
              </div>
            </div>

            <!-- Code Block Preview -->
            <div class="bg-surface-dim rounded-lg overflow-hidden font-mono text-sm">
              <div class="bg-surface-container-high px-4 py-2 flex justify-between items-center">
                <span class="text-xs text-on-surface-variant">
                  internal/auth/provider.go
                </span>
                <span
                  class="material-symbols-outlined text-sm text-outline cursor-pointer"
                >
                  content_copy
                </span>
              </div>
              <pre class="p-4 text-on-surface"><code>{{ `func (p *Provider) RefreshToken(ctx context.Context) error {
  p.mu.Lock()
  defer p.mu.Unlock()

  // logic to refresh token...
  return nil
}` }}</code></pre>
            </div>
          </div>

          <!-- Session Meta -->
          <div class="col-span-4 space-y-6">
            <div
              class="bg-surface-container-lowest border border-outline-variant/20 rounded-xl p-4"
            >
              <h4
                class="text-xs font-bold uppercase tracking-widest text-outline mb-4"
              >
                Context Files
              </h4>
              <ul class="space-y-3">
                <li class="flex items-center gap-2 text-sm text-on-surface-variant">
                  <span class="material-symbols-outlined text-sm">description</span>
                  auth_provider.go
                </li>
                <li class="flex items-center gap-2 text-sm text-on-surface-variant">
                  <span class="material-symbols-outlined text-sm">description</span>
                  main.go
                </li>
                <li class="flex items-center gap-2 text-sm text-on-surface-variant">
                  <span class="material-symbols-outlined text-sm">description</span>
                  session_test.go
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </main>

    <!-- ═══════════════════════════════════════════════════════════════
         Overlay Layer (Active Selectors) — createPortal → <teleport>
         ═══════════════════════════════════════════════════════════════ -->
    <teleport to="body">
      <div
        class="fixed inset-0 z-50 flex flex-col justify-end items-center pointer-events-none p-8"
      >
        <!-- Floating Dropdown Overlay Container -->
        <div class="w-full max-w-2xl flex gap-4 mb-4 pointer-events-auto items-end">
          <!-- ── Permissions Dropdown ─────────────────────────────── -->
          <div
            v-if="showPermissions"
            class="w-80 rounded-xl border border-[var(--color-border)] overflow-hidden flex flex-col"
            :style="{
              background: 'var(--color-surface-glass)',
              backdropFilter: 'blur(20px)',
              boxShadow:
                '0 4px 20px rgba(27, 28, 26, 0.04), 0 12px 40px rgba(27, 28, 26, 0.08)',
            }"
          >
            <div
              class="px-4 py-3 bg-surface-container-low border-b border-[var(--color-border)]"
            >
              <span class="text-[10px] font-bold uppercase tracking-widest text-outline">
                Execution Permissions
              </span>
            </div>
            <div class="p-2 space-y-1">
              <button
                v-for="mode in mockPermissionModes"
                :key="mode.id"
                @click="selectedPermission = mode.id"
                :class="[
                  'w-full text-left p-3 rounded-lg transition-colors flex gap-3 group',
                  mode.id === 'plan'   ? 'hover:bg-tertiary-container/10'
                    : mode.id === 'bypass' ? 'hover:bg-error-container/20'
                    : 'hover:bg-surface-container-high',
                ]"
              >
                <span
                  class="material-symbols-outlined mt-0.5"
                  :class="
                    permissionIcons[mode.id]?.color || 'text-outline'
                  "
                >
                  {{ permissionIcons[mode.id]?.icon || mode.icon }}
                </span>
                <div class="flex-1">
                  <div class="flex items-center justify-between">
                    <span
                      class="text-sm font-semibold"
                      :class="
                        mode.id === 'plan'   ? 'text-tertiary'
                          : mode.id === 'bypass' ? 'text-error'
                          : ''
                      "
                    >
                      {{ mode.label }}
                    </span>
                    <span
                      v-if="selectedPermission === mode.id"
                      class="material-symbols-outlined text-primary text-sm"
                    >
                      check_circle
                    </span>
                  </div>
                  <p class="text-xs text-on-surface-variant">{{ mode.description }}</p>
                </div>
              </button>
            </div>
          </div>

          <!-- ── Model & Effort Dropdown ─────────────────────────── -->
          <div
            v-if="showModelConfig"
            class="w-64 rounded-xl border border-[var(--color-border)] overflow-hidden flex flex-col"
            :style="{
              background: 'var(--color-surface-glass)',
              backdropFilter: 'blur(20px)',
              boxShadow:
                '0 4px 20px rgba(27, 28, 26, 0.04), 0 12px 40px rgba(27, 28, 26, 0.08)',
            }"
          >
            <div
              class="px-4 py-3 bg-surface-container-low border-b border-[var(--color-border)]"
            >
              <span class="text-[10px] font-bold uppercase tracking-widest text-outline">
                Model Configuration
              </span>
            </div>

            <!-- Models -->
            <div class="p-2">
              <button
                v-for="model in mockModels"
                :key="model.id"
                @click="selectedModel = model.id"
                :class="[
                  'w-full text-left p-2.5 rounded-lg flex items-center justify-between transition-colors',
                  selectedModel === model.id
                    ? 'bg-primary/5 text-primary'
                    : 'hover:bg-surface-container-high',
                ]"
              >
                <div
                  class="flex items-center gap-2"
                  :class="{ 'font-semibold': selectedModel === model.id }"
                >
                  <span
                    class="material-symbols-outlined text-sm"
                    :class="{
                      'text-outline': selectedModel !== model.id,
                    }"
                  >
                    {{ modelIcons[model.id] || 'smart_toy' }}
                  </span>
                  <span class="text-sm">{{ model.name }}</span>
                </div>
                <span
                  v-if="selectedModel === model.id"
                  class="material-symbols-outlined text-sm"
                >
                  radio_button_checked
                </span>
              </button>
            </div>

            <!-- Divider -->
            <div class="mx-4 h-[1px] bg-[var(--color-border)]" />

            <!-- Effort levels -->
            <div class="p-2">
              <div class="px-2 mb-2">
                <span class="text-[9px] font_bold text-outline uppercase tracking-tighter">
                  Thinking Effort
                </span>
              </div>
              <div class="grid grid-cols-2 gap-1">
                <button
                  v-for="level in mockEffortLevels"
                  :key="level"
                  @click="selectedEffort = level"
                  :class="[
                    'text-xs py-2 px-3 rounded-md transition-all',
                    selectedEffort === level
                      ? 'bg-primary text-on-primary'
                      : 'border border-outline-variant/30 hover:border-primary',
                    level === 'Max' ? 'font-bold' : '',
                  ]"
                >
                  {{ level === 'Medium' ? 'Med' : level }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- ── The Composer (Anchor) ─────────────────────────────── -->
        <div
          class="w-full max-w-2xl p-4 rounded-xl border border-outline-variant/15 pointer-events-auto flex flex-col gap-3"
          :style="{
            background: 'rgba(255, 255, 255, 0.85)',
            backdropFilter: 'blur(20px)',
            boxShadow:
              '0 4px 20px rgba(27, 28, 26, 0.04), 0 12px 40px rgba(27, 28, 26, 0.08)',
          }"
        >
          <textarea
            class="w-full bg-transparent border-none focus:ring-0 focus:outline-none resize-none font-body text-on-surface placeholder:text-outline"
            placeholder="Reply to MadCop..."
            rows="2"
          />
          <div class="flex justify-between items-center">
            <div class="flex items-center gap-2">
              <!-- Permission pill -->
              <button
                @click="togglePermissions"
                class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-surface-container-low border border-[var(--color-border)] text-xs font-medium hover:bg-surface-container-high transition-all"
              >
                <span class="material-symbols-outlined text-base">
                  {{ permissionIcons[selectedPermission]?.icon || 'verified_user' }}
                </span>
                {{
                  mockPermissionModes.find((m) => m.id === selectedPermission)?.label ||
                  'Ask permissions'
                }}
              </button>

              <!-- Model pill -->
              <button
                @click="toggleModelConfig"
                class="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-surface-container-low border border-[var(--color-border)] text-xs font-medium hover:bg-surface-container-high transition-all"
              >
                <span class="material-symbols-outlined text-base">
                  {{ modelIcons[selectedModel] || 'smart_toy' }}
                </span>
                {{ activeModel()?.name || 'Sonnet 4.6' }}
              </button>

              <!-- Attach file button -->
              <button
                class="p-1.5 rounded-lg text-outline hover:bg-surface-container-low transition-colors"
              >
                <span class="material-symbols-outlined">attach_file</span>
              </button>
            </div>

            <!-- Run button -->
            <button
              class="bg-primary text-on-primary px-4 py-1.5 rounded-lg font-semibold text-sm flex items-center gap-2 hover:opacity-90 transition-opacity"
            >
              Run
              <span class="material-symbols-outlined text-base">send</span>
            </button>
          </div>
        </div>
      </div>
    </teleport>

    <!-- ═══════════════════════════════════════════════════════════════
         Footer / Status Bar
         ═══════════════════════════════════════════════════════════════ -->
    <footer
      class="bg-[var(--color-background)] font-body text-xs tracking-tight fixed bottom-0 left-0 w-full h-8 border-t border-[var(--color-border)]/20 flex items-center justify-between px-4 z-[60]"
    >
      <div class="flex items-center gap-3">
        <div class="flex items-center gap-1.5">
          <div
            class="w-4 h-4 rounded_full bg-primary-fixed flex items-center justify-center"
          >
            <span
              class="material-symbols-outlined text-[10px] text-on-primary-fixed"
              style="fontVariationSettings: 'FILL' 1"
            >
              person
            </span>
          </div>
          <span class="text-outline">
            {{ mockStatusBar.user }} &bull; {{ mockStatusBar.username }} &bull; {{ mockStatusBar.plan }}
          </span>
        </div>
      </div>
      <div class="flex items-center gap-4">
        <button
          class="text-primary font-bold hover:bg-[var(--color-surface-container-low)] transition-colors px-2 py-0.5 rounded"
        >
          {{ mockStatusBar.branch }}
        </button>
        <button
          class="text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-container-low)] transition-colors px-2 py-0.5 rounded"
        >
          {{ mockStatusBar.worktreeToggle }}
        </button>
        <button
          class="text-[var(--color-text-tertiary)] hover:bg-[var(--color-surface-container-low)] transition-colors px-2 py-0.5 rounded"
        >
          {{ mockStatusBar.localSwitch }}
        </button>
      </div>
    </footer>
  </div>
</template>