<script setup lang="ts">
/**
 * ExecPolicySettings — editor for ~/.madcop/exec_policy.json
 * (codex exec_policy parity). Rules are ordered regex → action;
 * saving validates every pattern and hot-reloads the policy so the
 * next bash call sees the change without a server restart.
 */
import { computed, onMounted, ref } from 'vue'
import { useTranslation } from '../i18n'
import { useUIStore } from '../stores/uiStore'
import { getApiUrl } from '../api/client'

const t = useTranslation()
const uiStore = useUIStore()

interface Rule { id: string; pattern: string; action: string; reason: string }

const loading = ref(false)
const saving = ref(false)
const source = ref('')
const doc = ref('')
const rules = ref<Rule[]>([])
const dirty = ref(false)

const actionLabel: Record<string, string> = {
  deny: '拒绝',
  warn: '警告',
  allow: '放行',
}
const actionClass = computed(() => ({
  deny: 'bg-[var(--color-error)]/10 text-[var(--color-error)]',
  warn: 'bg-[#b45309]/10 text-[#b45309]',
  allow: 'bg-[var(--color-surface-container)] text-[var(--color-text-tertiary)]',
}))

async function load() {
  loading.value = true
  try {
    const res = await fetch(getApiUrl('/api/v4/exec_policy'))
    const data = await res.json()
    rules.value = (data.rules || []).map((r: Rule) => ({ ...r }))
    source.value = data.source || ''
    doc.value = data.doc || ''
    dirty.value = false
  } catch {
    uiStore.addToast({ type: 'error', message: '命令策略加载失败' })
  } finally {
    loading.value = false
  }
}

function markDirty() { dirty.value = true }

function addRule() {
  rules.value.push({ id: `rule-${rules.value.length + 1}`, pattern: '', action: 'warn', reason: '' })
  dirty.value = true
}

function removeRule(i: number) {
  rules.value.splice(i, 1)
  dirty.value = true
}

async function save() {
  saving.value = true
  try {
    const res = await fetch(getApiUrl('/api/v4/exec_policy'), {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rules: rules.value }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok || !data.ok) {
      throw new Error(typeof data.detail === 'string' ? data.detail : `HTTP ${res.status}`)
    }
    rules.value = (data.rules || []).map((r: Rule) => ({ ...r }))
    dirty.value = false
    uiStore.addToast({ type: 'success', message: `已保存 ${rules.value.length} 条规则并热生效` })
  } catch (e: any) {
    uiStore.addToast({ type: 'error', message: `保存失败：${e?.message || e}` })
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="w-full min-w-0">
    <section class="mb-5 overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface-container-low)]">
      <div class="flex flex-wrap items-start justify-between gap-3 px-5 py-5">
        <div class="min-w-0">
          <div class="mb-2 text-[11px] font-semibold tracking-wide text-[var(--color-text-tertiary)]">
            {{ t('settings.nav.system') || '系统' }}
          </div>
          <div class="mb-2 flex items-center gap-2">
            <span class="material-symbols-outlined text-[20px] text-[var(--color-brand)]" style="fontVariationSettings: 'FILL' 1">gavel</span>
            <h2 class="text-[18px] font-bold tracking-tight text-[var(--color-text-primary)]" style="font-family: var(--font-headline)">命令策略</h2>
          </div>
          <p class="max-w-3xl text-sm leading-6 text-[var(--color-text-secondary)]">
            {{ doc || 'bash 命令在执行前按规则匹配：deny 直接拒绝，warn 放行但提示模型，allow 显式放行。' }}
          </p>
          <p class="mt-1 text-[11px] text-[var(--color-text-tertiary)]">配置文件：{{ source || '~/.madcop/exec_policy.json' }}</p>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <button
            type="button"
            class="inline-flex h-9 items-center gap-1.5 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3.5 text-xs font-medium text-[var(--color-text-primary)] transition-colors hover:bg-[var(--color-surface-hover)]"
            :disabled="loading"
            @click="load"
          >
            <span class="material-symbols-outlined text-[15px]">refresh</span>
            重新加载
          </button>
          <button
            type="button"
            class="inline-flex h-9 items-center gap-1.5 rounded-xl bg-[var(--color-primary)] px-4 text-xs font-medium text-white disabled:opacity-50"
            :disabled="saving || loading || !dirty"
            @click="save"
          >
            <span v-if="saving" class="material-symbols-outlined animate-spin text-[15px]">progress_activity</span>
            保存并热生效
          </button>
        </div>
      </div>
    </section>

    <div v-if="loading && !rules.length" class="px-5 py-6 text-xs text-[var(--color-text-tertiary)]">加载中…</div>
    <template v-else>
      <div class="space-y-2 px-1">
        <div
          v-for="(rule, i) in rules"
          :key="i"
          class="grid grid-cols-[auto_1fr_auto_1fr_auto] items-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2.5"
        >
          <select
            v-model="rule.action"
            :class="[
              'h-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-2 text-xs font-medium outline-none',
              (actionClass as any)[rule.action] || ''
            ]"
            @change="markDirty"
          >
            <option value="deny">deny · 拒绝</option>
            <option value="warn">warn · 警告</option>
            <option value="allow">allow · 放行</option>
          </select>
          <input
            v-model="rule.pattern"
            type="text"
            placeholder="正则，如 \\bcurl[^|]*\\|\\s*(bash|sh)\\b"
            class="h-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-2.5 font-mono text-[12px] outline-none focus:border-[var(--color-border-focus)]"
            @input="markDirty"
          />
          <span class="text-[11px] text-[var(--color-text-tertiary)]">说明</span>
          <input
            v-model="rule.reason"
            type="text"
            placeholder="命中原因（展示给模型与用户）"
            class="h-8 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface-container-low)] px-2.5 text-[12px] outline-none focus:border-[var(--color-border-focus)]"
            @input="markDirty"
          />
          <button
            type="button"
            title="删除规则"
            class="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--color-text-tertiary)] hover:bg-[var(--color-error)]/10 hover:text-[var(--color-error)]"
            @click="removeRule(i)"
          >
            <span class="material-symbols-outlined text-[16px]">delete</span>
          </button>
        </div>
      </div>
      <div class="mt-3 flex items-center gap-2 px-1">
        <button
          type="button"
          class="inline-flex h-8 items-center gap-1 rounded-lg border border-dashed border-[var(--color-border)] px-3 text-xs text-[var(--color-text-secondary)] hover:bg-[var(--color-surface-hover)]"
          @click="addRule"
        >
          <span class="material-symbols-outlined text-[14px]">add</span>
          添加规则
        </button>
        <span v-if="dirty" class="text-[11px] text-[#b45309]">有未保存的修改</span>
      </div>
    </template>
  </div>
</template>
