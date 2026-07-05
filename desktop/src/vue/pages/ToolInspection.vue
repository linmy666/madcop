<script setup lang="ts">
import { ref } from 'vue'

/**
 * ToolInspection — Vue 3 port of pages/ToolInspection.tsx
 * Mock demo page showing a tool inspection/diff view.
 * Self-contained with mock data.
 */

const activeDiffTab = ref<'split' | 'unified'>('split')

const mockToolInspection = {
  toolType: 'WRITE',
  toolName: 'write_file',
  description: 'Writes or overwrites content to a file on disk.',
  filePath: 'src/auth/legacyAuthService.ts',
  dryRunStatus: 'Pass',
  linesChanged: { added: 42, removed: 18 },
  diffLines: [
    { type: 'removed', lineNo: 12, content: '  const token = await fetchToken(username, password);' },
    { type: 'added', lineNo: 13, content: '  const token = await oauthClient.getToken({ username, codeVerifier });' },
    { type: 'removed', lineNo: 15, content: '  if (!token) throw new Error("Auth failed");' },
    { type: 'added', lineNo: 16, content: '  if (!token.access_token) throw new Error("OAuth2 flow failed: no access token");' },
    { type: 'added', lineNo: 17, content: '  if (!token.refresh_token) throw new Error("OAuth2 flow failed: no refresh token");' },
    { type: 'added', lineNo: 20, content: '  return new AuthService(token.access_token, token.refresh_token, token.expires_at);' },
  ],
}
</script>

<template>
  <div class="flex-1 flex flex-col overflow-hidden bg-[var(--color-surface)]">
    <div class="h-px w-full bg-[var(--color-surface-container)]" />
    <main class="flex-1 overflow-y-auto p-8 max-w-6xl mx-auto w-full">
      <div class="flex flex-col gap-6">
        <!-- Title row -->
        <div class="flex items-start justify-between">
          <div class="space-y-1">
            <div class="flex items-center gap-2">
              <span class="px-2 py-0.5 bg-[var(--color-primary-fixed)] text-[var(--color-on-primary)] text-[10px] font-bold rounded uppercase tracking-widest">{{ mockToolInspection.toolType }}</span>
              <h1 class="font-[var(--font-headline)] font-extrabold text-2xl text-[var(--color-on-surface)] tracking-tight">{{ mockToolInspection.toolName }}</h1>
            </div>
            <p class="text-[var(--color-on-surface-variant)] font-medium">{{ mockToolInspection.description }}</p>
          </div>
          <div class="flex gap-2">
            <button class="px-4 py-2 bg-[var(--color-surface-container-high)] rounded-lg text-sm font-semibold hover:bg-[var(--color-surface-variant)] transition-all">Revert Change</button>
            <button class="px-4 py-2 bg-[var(--color-primary)] text-[var(--color-on-primary)] rounded-lg text-sm font-semibold shadow-sm hover:opacity-90 transition-all">Apply to All</button>
          </div>
        </div>

        <!-- Metadata cards -->
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div class="bg-[var(--color-surface-container-low)] rounded-xl p-4 flex flex-col gap-1">
            <span class="text-[10px] font-bold text-[var(--color-outline)] uppercase tracking-wider">Target File</span>
            <div class="flex items-center gap-2 text-[var(--color-on-surface)]">
              <span class="material-symbols-outlined text-[18px]">description</span>
              <span class="font-[var(--font-mono)] text-sm">{{ mockToolInspection.filePath }}</span>
            </div>
          </div>
          <div class="bg-[var(--color-surface-container-low)] rounded-xl p-4 flex flex-col gap-1">
            <span class="text-[10px] font-bold text-[var(--color-outline)] uppercase tracking-wider">Status</span>
            <div class="flex items-center gap-2 text-[var(--color-tertiary)]">
              <span class="material-symbols-outlined text-[18px]" style="fontVariationSettings: 'FILL' 1">check_circle</span>
              <span class="font-semibold text-sm">{{ mockToolInspection.dryRunStatus }}</span>
            </div>
          </div>
          <div class="bg-[var(--color-surface-container-low)] rounded-xl p-4 flex flex-col gap-1">
            <span class="text-[10px] font-bold text-[var(--color-outline)] uppercase tracking-wider">Lines Modified</span>
            <div class="flex items-center gap-2 text-[var(--color-on-surface)]">
              <span class="material-symbols-outlined text-[18px]">edit_note</span>
              <span class="font-semibold text-sm">+{{ mockToolInspection.linesChanged.added }} / -{{ mockToolInspection.linesChanged.removed }}</span>
            </div>
          </div>
        </div>

        <!-- Diff Viewer -->
        <div class="bg-[var(--color-surface-dim)] rounded-xl overflow-hidden border border-[var(--color-outline-variant)]/20 shadow-sm">
          <div class="px-4 py-2.5 bg-[var(--color-surface-container-high)] flex items-center justify-between border-b border-[var(--color-outline-variant)]/20">
            <div class="flex items-center gap-3">
              <div class="flex gap-1.5">
                <div class="w-2.5 h-2.5 rounded-full bg-[var(--color-error)] opacity-30" />
                <div class="w-2.5 h-2.5 rounded-full bg-[var(--color-primary-fixed-dim)]" />
                <div class="w-2.5 h-2.5 rounded-full bg-[var(--color-tertiary-container)] opacity-30" />
              </div>
              <span class="font-[var(--font-mono)] text-xs text-[var(--color-outline)] px-2 border-l border-[var(--color-outline-variant)]/30">{{ mockToolInspection.filePath }} — Diff View</span>
            </div>
            <div class="flex items-center gap-4">
              <span class="text-[11px] text-[var(--color-outline)] font-medium">
                L{{ mockToolInspection.diffLines[0]?.lineNo ?? 1 }} — L{{ mockToolInspection.diffLines[mockToolInspection.diffLines.length - 1]?.lineNo ?? 1 }}
              </span>
              <div class="flex bg-[var(--color-surface-container-low)] rounded p-0.5">
                <button @click="activeDiffTab = 'split'"
                  :class="['px-2 py-1 text-[10px] font-bold uppercase', activeDiffTab === 'split' ? 'bg-[var(--color-surface)] rounded shadow-sm text-[var(--color-on-surface)]' : 'text-[var(--color-outline)]']">Split</button>
                <button @click="activeDiffTab = 'unified'"
                  :class="['px-2 py-1 text-[10px] font-bold uppercase', activeDiffTab === 'unified' ? 'bg-[var(--color-surface)] rounded shadow-sm text-[var(--color-on-surface)]' : 'text-[var(--color-outline)]']">Unified</button>
              </div>
            </div>
          </div>
          <div class="font-[var(--font-mono)] text-[13px] leading-relaxed p-4 overflow-x-auto whitespace-pre">
            <div v-for="(line, idx) in mockToolInspection.diffLines" :key="idx"
              :class="['flex w-full', line.type === 'added' ? 'bg-[var(--color-diff-added-bg)]' : 'bg-[var(--color-diff-removed-bg)]']">
              <span :class="['w-10 flex-shrink-0 text-right pr-4 select-none', line.type === 'added' ? 'text-[var(--color-tertiary)] opacity-40' : 'text-[var(--color-error)] opacity-40']">{{ line.lineNo }}</span>
              <span class="text-[var(--color-on-surface-variant)]">
                {{ line.type === 'added' ? '+   ' : '-   ' }}{{ line.content }}
              </span>
            </div>
          </div>
        </div>

        <!-- Implementation Context -->
        <div class="p-6 bg-[var(--color-surface-container-lowest)] rounded-2xl border border-[var(--color-outline-variant)]/10">
          <h3 class="font-[var(--font-headline)] font-bold text-sm text-[var(--color-on-surface)] mb-4">Implementation Context</h3>
          <div class="grid grid-cols-1 lg:grid-cols-2 gap-8">
            <div class="space-y-4">
              <div class="flex items-start gap-3">
                <div class="mt-1 w-6 h-6 rounded bg-[var(--color-primary-fixed)] flex items-center justify-center">
                  <span class="material-symbols-outlined text-[14px] text-[var(--color-on-primary)]">psychology</span>
                </div>
                <div>
                  <p class="text-xs font.bold uppercase tracking.widest text-[var(--color-outline)] mb-1">Reasoning</p>
                  <p class="text-sm text-[var(--color-on-surface-variant)] leading-relaxed">The legacy auth was deprecated in RFC-204. The new SDK provides automatic session refresh.</p>
                </div>
              </div>
              <div class="flex items-start gap-3">
                <div class="mt-1 w-6 h-6 rounded bg-[var(--color-diff-added-bg)] flex items-center justify-center">
                  <span class="material-symbols-outlined text-[14px] text-[var(--color-diff-added-text)]">science</span>
                </div>
                <div>
                  <p class="text-xs font-bold uppercase tracking-widest text-[var(--color-outline)] mb-1">Impact Analysis</p>
                  <p class="text-sm text-[var(--color-on-surface-variant)] leading-relaxed">No changes needed in calling components. The interface remains compatible.</p>
                </div>
              </div>
            </div>
            <div class="flex items-center justify-center">
              <div class="w-full h-32 rounded-xl bg-[var(--color-surface-container)] relative overflow-hidden">
                <div class="absolute inset-0 bg-gradient-to-br from-[var(--color-primary)]/5 to-[var(--color-secondary)]/5" />
                <div class="absolute inset-0 flex items-center justify-center gap-4">
                  <div class="flex flex-col items-center gap-1">
                    <div class="p-2 bg-[var(--color-surface)] rounded-lg shadow-sm">
                      <span class="material-symbols-outlined text-[var(--color-outline)]">description</span>
                    </div>
                    <span class="text-[9px] font.bold text-[var(--color-outline)]">auth.ts</span>
                  </div>
                  <span class="material-symbols-outlined text-[var(--color-outline)] animate-pulse">keyboard_double_arrow_right</span>
                  <div class="flex flex-col items-center gap-1">
                    <div class="p-2 bg-[var(--color-surface)] rounded-lg shadow-sm border border-[var(--color-tertiary)]/20">
                      <span class="material-symbols-outlined text-[var(--color-tertiary)]">check_circle</span>
                    </div>
                    <span class="text-[9px] font.bold text-[var(--color-tertiary)]">Verified</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </main>
  </div>
</template>
