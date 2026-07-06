<script setup lang="ts">
// v3.0 — OfficialLogin (Vue 3)
// Replaces ClaudeOfficialLogin.tsx + ChatGPTOfficialLogin.tsx with a
// single generic component. Same Tailwind classes, same OAuth flow.
// The store name 'hahaOAuthStore' is renamed to 'oauthStore'.
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  providerName: string  // 'MadCop' or 'OpenAI'
}>()

const status = ref<'loading' | 'logged_out' | 'pending' | 'logged_in'>('loading')
const error = ref('')
const userName = ref('')
let pollTimer: number | null = null

onMounted(async () => {
  await fetchStatus()
})
onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })

async function fetchStatus() {
  try {
    const r = await fetch('/api/auth/oauth/status')
    const data = await r.json()
    status.value = data.authenticated ? 'logged_in' : 'logged_out'
    userName.value = data.userName || ''
  } catch {
    status.value = 'logged_out'
  }
}

async function handleLogin() {
  status.value = 'pending'
  error.value = ''
  try {
    const r = await fetch('/api/auth/oauth/login', { method: 'POST' })
    const data = await r.json()
    if (data.authorizeUrl) {
      globalThis.window.open(data.authorizeUrl, '_blank')
      pollTimer = window.setInterval(fetchStatus, 2000)
    }
  } catch (e: any) {
    error.value = e?.message || '无法启动登录流程'
    status.value = 'logged_out'
  }
}

async function handleLogout() {
  try {
    await fetch('/api/auth/oauth/logout', { method: 'POST' })
    status.value = 'logged_out'
    userName.value = ''
  } catch {}
}
</script>

<template>
  <div>
    <div v-if="status === 'loading'" class="text-xs text-[var(--color-text-tertiary)]">加载中…</div>

    <div v-else-if="error" class="text-xs text-[var(--color-error)]">错误: {{ error }}</div>

    <div v-else-if="status === 'logged_in'" class="flex items-center gap-3">
      <span class="inline-flex items-center gap-1.5 rounded-full bg-[var(--color-success-container)] px-2.5 py-1 text-xs font-medium text-[var(--color-success)]">
        <span class="material-symbols-outlined text-[14px]">check_circle</span>
        已登录{{ userName ? ` (${userName})` : '' }}
      </span>
      <button
        @click="handleLogout"
        class="px-3 py-1 text-xs rounded-[var(--radius-md)] border border-[var(--color-border)] text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)] transition-colors"
      >登出</button>
    </div>

    <div v-else class="flex items-center gap-3">
      <button
        @click="handleLogin"
        :disabled="status === 'pending'"
        class="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-[var(--radius-md)] bg-[image:var(--gradient-btn-primary)] text-[var(--color-btn-primary-fg)] shadow-[var(--shadow-button-primary)] transition-all hover:brightness-105 disabled:opacity-50"
      >
        <span class="material-symbols-outlined text-[14px]">login</span>
        登录 {{ providerName }}
      </button>
      <span v-if="status === 'pending'" class="text-xs text-[var(--color-text-tertiary)]">等待授权中…</span>
    </div>
  </div>
</template>
