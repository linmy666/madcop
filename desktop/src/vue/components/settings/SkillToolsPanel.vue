<script setup lang="ts">
/**
 * SkillToolsPanel — hot-loaded skill tools from ~/.madcop/skills/*.py.
 * Shows the live tools the runtime registered (codex-parity skill
 * hot-load) with a one-click reload; skills edited on disk take
 * effect for the next turn without a server restart.
 */
import { computed, onMounted, ref } from 'vue'
import { useTranslation } from '../../i18n'
import { useUIStore } from '../../stores/uiStore'
import { getApiUrl } from '../../api/client'

const t = useTranslation()
const uiStore = useUIStore()

const loading = ref(false)
const reloading = ref(false)
const skillsDir = ref('')
const files = ref<string[]>([])
const tools = ref<{ name: string; description: string; danger: string }[]>([])
const loaded = ref(false)

const dangerLabel = computed(() => ({
  safe: '只读',
  mutating: '写入',
  destructive: '危险',
}))

async function fetchSkills() {
  loading.value = true
  try {
    const res = await fetch(getApiUrl('/api/v4/skills'))
    const data = await res.json()
    skillsDir.value = data.skills_dir || ''
    files.value = data.files || []
    tools.value = data.tools || []
    loaded.value = true
  } catch {
    uiStore.addToast({ type: 'error', message: '技能列表加载失败' })
  } finally {
    loading.value = false
  }
}

async function reload() {
  reloading.value = true
  try {
    const res = await fetch(getApiUrl('/api/v4/skills/reload'), { method: 'POST' })
    const data = await res.json()
    skillsDir.value = data.skills_dir || skillsDir.value
    const names: string[] = data.tools || []
    uiStore.addToast({
      type: 'success',
      message: names.length ? `已重载 ${names.length} 个技能工具` : '已重载（目录中暂无技能）',
    })
    await fetchSkills()
  } catch {
    uiStore.addToast({ type: 'error', message: '重载失败' })
  } finally {
    reloading.value = false
  }
}

onMounted(fetchSkills)
</script>

<template>
  <section class="border-t border-[var(--color-border)] px-5 py-5">
    <div class="mb-3 flex flex-wrap items-center justify-between gap-3">
      <div class="min-w-0">
        <div class="flex items-center gap-2">
          <span class="material-symbols-outlined text-[18px] text-[var(--color-brand)]">bolt</span>
          <h3 class="text-sm font-semibold text-[var(--color-text-primary)]">技能工具（热加载）</h3>
        </div>
        <p class="mt-1 max-w-3xl text-xs leading-5 text-[var(--color-text-secondary)]">
          把 Python 模块放进
          <code class="rounded bg-[var(--color-surface-container)] px-1 py-0.5 text-[11px]">{{ skillsDir || '~/.madcop/skills/' }}</code>
          ，导出 <code class="rounded bg-[var(--color-surface-container)] px-1 py-0.5 text-[11px]">TOOLS = [make_tool(...)]</code>
          即成为可执行工具；编辑文件后点重载立即生效，无需重启。
        </p>
      </div>
      <button
        type="button"
        class="inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] px-3 text-xs font-medium text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-hover)]"
        :disabled="reloading || loading"
        @click="reload"
      >
        <span v-if="reloading" class="material-symbols-outlined animate-spin text-[14px]">progress_activity</span>
        <span v-else class="material-symbols-outlined text-[14px]">refresh</span>
        重载技能
      </button>
    </div>

    <div v-if="loading && !loaded" class="py-3 text-xs text-[var(--color-text-tertiary)]">加载中…</div>
    <template v-else>
      <div v-if="!tools.length" class="rounded-xl border border-dashed border-[var(--color-border)] px-4 py-6 text-center text-xs text-[var(--color-text-tertiary)]">
        暂无技能工具 — 在 {{ skillsDir || '~/.madcop/skills' }} 下创建 <code>.py</code> 文件即可
      </div>
      <div v-else class="grid gap-2 sm:grid-cols-2">
        <div
          v-for="tool in tools"
          :key="tool.name"
          class="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2.5"
        >
          <div class="flex items-center gap-2">
            <span class="font-mono text-[12px] font-medium text-[var(--color-text-primary)]">{{ tool.name }}</span>
            <span
              :class="[
                'rounded-full px-1.5 py-0.5 text-[10px] font-medium',
                tool.danger === 'safe'
                  ? 'bg-[var(--color-surface-container)] text-[var(--color-text-tertiary)]'
                  : tool.danger === 'mutating'
                    ? 'bg-[#b45309]/10 text-[#b45309]'
                    : 'bg-[var(--color-error)]/10 text-[var(--color-error)]'
              ]"
            >{{ (dangerLabel as any)[tool.danger] || tool.danger }}</span>
          </div>
          <p class="mt-1 line-clamp-2 text-[11px] leading-4 text-[var(--color-text-secondary)]">
            {{ tool.description || '（无描述）' }}
          </p>
        </div>
      </div>
      <p v-if="files.length" class="mt-2 text-[11px] text-[var(--color-text-tertiary)]">
        已加载文件：{{ files.join('、') }}
      </p>
    </template>
  </section>
</template>
