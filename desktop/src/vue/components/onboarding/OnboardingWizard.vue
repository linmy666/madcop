<script setup lang="ts">
/**
 * OnboardingWizard — 3-step first-run setup (P0).
 *
 * Appears when: no provider configured AND no workspace picked AND
 * not previously dismissed. Guides the user through:
 *   Step 1: Pick a provider preset + paste API key + test
 *   Step 2: Pick a workspace folder (auto-enables Observer)
 *   Step 3: Done — shows suggestion chips
 *
 * Skippable ("稍后设置"); dismissal sets localStorage.madcop_onboarded='1'.
 * The wizard is an overlay — it doesn't replace the main UI, so the
 * existing ensureActiveTab flow is unaffected.
 */
import { ref, computed, onMounted } from 'vue'
import { getApiUrl } from '../../api/client'
import { getDesktopHost } from '../../../lib/desktopHost'

const emit = defineEmits<{ (e: 'close'): void }>()

const step = ref(1)  // 1=provider, 2=workspace, 3=done

// ── Provider step ──────────────────────────────────────────────────
interface Preset { id: string; provider_id?: string; label: string; base_url: string; default_model: string; apiFormat?: string; authStrategy?: string }
const presets = ref<Preset[]>([])
const selectedPreset = ref<Preset | null>(null)
const apiKey = ref('')
const providerLabel = ref('')
const testing = ref(false)
const testResult = ref<{ ok: boolean; msg: string } | null>(null)
const providerError = ref('')

async function loadPresets() {
  try {
    const res = await fetch(getApiUrl('/api/settings/providers/presets'))
    if (res.ok) {
      const data = await res.json()
      presets.value = (data.presets || []).slice(0, 6)  // top 6
    }
  } catch { /* keep empty */ }
}

function pickPreset(p: Preset) {
  selectedPreset.value = p
  providerLabel.value = p.label
  apiKey.value = ''
  testResult.value = null
}

async function testAndSave() {
  if (!selectedPreset.value || !apiKey.value.trim()) return
  testing.value = true
  testResult.value = null
  providerError.value = ''
  try {
    // Save provider via flat POST (same fix as ProviderSettings)
    const pid = selectedPreset.value.provider_id || selectedPreset.value.id
    const res = await fetch(getApiUrl('/api/settings'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        provider_id: pid,
        label: providerLabel.value || selectedPreset.value.label,
        base_url: selectedPreset.value.base_url,
        api_key: apiKey.value.trim(),
        model: selectedPreset.value.default_model,
        api_format: selectedPreset.value.apiFormat || 'openai_chat',
        auth_strategy: selectedPreset.value.authStrategy || 'api_key',
        make_active: true,
      }),
    })
    if (!res.ok) {
      const detail = await res.text().catch(() => '')
      providerError.value = `保存失败 (HTTP ${res.status}): ${detail.slice(0, 100)}`
      testing.value = false
      return
    }
    // Test the connection
    const testRes = await fetch(getApiUrl(`/api/settings/providers/${pid}/test`), { method: 'POST' })
    const testData = await testRes.json().catch(() => ({}))
    if (testRes.ok && testData.success !== false) {
      testResult.value = { ok: true, msg: '连接成功!' }
      setTimeout(() => { step.value = 2 }, 600)
    } else {
      testResult.value = { ok: false, msg: testData.message || testData.error || '测试失败,但已保存(可在设置中修改)' }
      // Still allow proceeding — the provider is saved, user can fix later
      setTimeout(() => { step.value = 2 }, 1200)
    }
  } catch (e: any) {
    providerError.value = e?.message || '网络错误'
  } finally {
    testing.value = false
  }
}

// ── Workspace step ─────────────────────────────────────────────────
const workspacePath = ref('')
const workspaceError = ref('')

async function pickFolder() {
  const host = getDesktopHost()
  if (!host?.capabilities?.dialogs) {
    workspaceError.value = '当前环境不支持文件夹选择,请跳过此步'
    return
  }
  try {
    const selected = await host.dialogs.open({ directory: true, multiple: false, title: '选择项目文件夹' })
    if (typeof selected === 'string' && selected.trim()) {
      workspacePath.value = selected.trim()
      // Save workspace + auto-enable observer
      try { localStorage.setItem('madcop_workspace_dir', selected.trim()) } catch {}
      workspaceError.value = ''
    }
  } catch (e: any) {
    workspaceError.value = e?.message || '选择失败'
  }
}

function finishWorkspace() {
  // If workspace was picked, observer auto-enables via settingsStore._initialProactiveState
  step.value = 3
}

// ── Done step ──────────────────────────────────────────────────────
const suggestions = [
  '帮我分析这个项目的架构',
  '解释一下这段代码的作用',
  '搜一下最新的技术动态',
  '写一个单元测试',
]

function pickSuggestion(text: string) {
  emit('close')
  // Dispatch to composer — AppShell will handle filling the input
  try { localStorage.setItem('madcop_pending_input', text) } catch {}
}

function skipAll() {
  try { localStorage.setItem('madcop_onboarded', '1') } catch {}
  dismissed.value = true
  emit('close')
}

function complete() {
  try { localStorage.setItem('madcop_onboarded', '1') } catch {}
  dismissed.value = true
  emit('close')
}

onMounted(loadPresets)

// ── Visibility trigger ─────────────────────────────────────────────
// localStorage isn't reactive, so skipping only updated the stored
// flag and the computed below never re-evaluated — the overlay stayed
// on screen (blocking the composer) until a full page reload. Track
// dismissal in a ref so shouldShow flips immediately.
const dismissed = ref(false)
const shouldShow = computed(() => {
  if (dismissed.value) return false
  try {
    if (localStorage.getItem('madcop_onboarded') === '1') return false
    return true
  } catch { return false }
})
</script>

<template>
  <Teleport to="body">
    <div v-if="shouldShow" class="ob-overlay">
      <div class="ob-modal">
        <!-- Step indicator -->
        <div class="ob-steps">
          <div v-for="n in 3" :key="n" class="ob-step-dot" :class="{ active: step >= n, current: step === n }">{{ n }}</div>
        </div>

        <!-- Step 1: Provider -->
        <div v-if="step === 1" class="ob-content">
          <h2 class="ob-title">配置 AI 模型</h2>
          <p class="ob-subtitle">选择一个供应商,粘贴你的 API Key。所有数据只存在本机。</p>

          <div class="ob-presets">
            <button
              v-for="p in presets" :key="p.id"
              class="ob-preset"
              :class="{ selected: selectedPreset?.id === p.id }"
              @click="pickPreset(p)"
            >
              <span class="ob-preset-label">{{ p.label }}</span>
            </button>
          </div>

          <div v-if="selectedPreset" class="ob-fields">
            <div class="ob-field">
              <label>名称</label>
              <input v-model="providerLabel" type="text" class="ob-input" />
            </div>
            <div class="ob-field">
              <label>API Key <span class="ob-req">*</span></label>
              <input v-model="apiKey" type="password" class="ob-input" placeholder="sk-..." @keyup.enter="testAndSave" />
            </div>
            <div v-if="providerError" class="ob-error">{{ providerError }}</div>
            <div v-if="testResult" class="ob-test" :class="{ ok: testResult.ok, fail: !testResult.ok }">{{ testResult.msg }}</div>
            <button
              class="ob-btn ob-btn-primary"
              :disabled="!apiKey.trim() || testing"
              @click="testAndSave"
            >{{ testing ? '测试中…' : '连接并测试' }}</button>
          </div>

          <div class="ob-actions">
            <button class="ob-btn ob-btn-ghost" @click="skipAll">稍后设置</button>
          </div>
        </div>

        <!-- Step 2: Workspace -->
        <div v-if="step === 2" class="ob-content">
          <h2 class="ob-title">选择项目文件夹</h2>
          <p class="ob-subtitle">观察器会监控文件保存和终端输出,只在异常时提醒你(测试失败/编译错误/服务崩溃)。</p>

          <button class="ob-btn ob-btn-primary ob-picker-btn" @click="pickFolder">
            {{ workspacePath ? '✓ ' + workspacePath.split('/').pop() : '选择文件夹' }}
          </button>
          <p v-if="workspacePath" class="ob-path">{{ workspacePath }}</p>
          <div v-if="workspaceError" class="ob-error">{{ workspaceError }}</div>

          <div class="ob-actions">
            <button class="ob-btn ob-btn-ghost" @click="step = 1">上一步</button>
            <button class="ob-btn ob-btn-primary" @click="finishWorkspace">{{ workspacePath ? '下一步' : '跳过(稍后选)' }}</button>
          </div>
        </div>

        <!-- Step 3: Done -->
        <div v-if="step === 3" class="ob-content">
          <h2 class="ob-title">🎉 设置完成!</h2>
          <p class="ob-subtitle">试试这些,或者直接开始对话:</p>
          <div class="ob-suggestions">
            <button v-for="s in suggestions" :key="s" class="ob-suggestion" @click="pickSuggestion(s)">{{ s }}</button>
          </div>
          <div class="ob-actions">
            <button class="ob-btn ob-btn-primary" @click="complete">开始使用 →</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.ob-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0,0,0,0.6); backdrop-filter: blur(4px);
  display: flex; align-items: center; justify-content: center;
}
.ob-modal {
  width: 90%; max-width: 480px; max-height: 90vh; overflow-y: auto;
  background: var(--color-surface, #1e1e2e); border-radius: 16px;
  padding: 32px; box-shadow: 0 24px 80px rgba(0,0,0,0.4);
  border: 1px solid var(--color-border, rgba(255,255,255,0.1));
}
.ob-steps { display: flex; gap: 8px; margin-bottom: 24px; }
.ob-step-dot {
  width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 600;
  background: var(--color-surface-container, rgba(255,255,255,0.05));
  color: var(--color-text-tertiary, #888); transition: all .2s;
}
.ob-step-dot.active { background: var(--color-accent, #4a9eff); color: white; }
.ob-step-dot.current { box-shadow: 0 0 0 3px rgba(74,158,255,0.3); }
.ob-title { font-size: 22px; font-weight: 700; margin-bottom: 8px; color: var(--color-text, #fff); }
.ob-subtitle { font-size: 14px; color: var(--color-text-secondary, #aaa); margin-bottom: 20px; line-height: 1.5; }
.ob-presets { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 16px; }
.ob-preset {
  padding: 12px; border-radius: 10px; border: 1px solid var(--color-border, rgba(255,255,255,0.1));
  background: var(--color-surface-container, rgba(255,255,255,0.03)); cursor: pointer; transition: all .15s;
  text-align: center;
}
.ob-preset:hover { border-color: var(--color-border-focus, #4a9eff); }
.ob-preset.selected { border-color: var(--color-accent, #4a9eff); background: rgba(74,158,255,0.1); }
.ob-preset-label { font-size: 13px; font-weight: 500; color: var(--color-text, #fff); }
.ob-fields { margin-top: 16px; }
.ob-field { margin-bottom: 12px; }
.ob-field label { display: block; font-size: 12px; color: var(--color-text-secondary, #aaa); margin-bottom: 4px; }
.ob-req { color: #ef4444; }
.ob-input {
  width: 100%; padding: 10px 12px; border-radius: 8px; font-size: 14px;
  background: var(--color-input-bg, rgba(0,0,0,0.3)); border: 1px solid var(--color-border, rgba(255,255,255,0.1));
  color: var(--color-text, #fff); box-sizing: border-box;
}
.ob-input:focus { outline: none; border-color: var(--color-accent, #4a9eff); }
.ob-error { color: #fca5a5; font-size: 12px; margin: 8px 0; }
.ob-test { font-size: 12px; margin: 8px 0; font-weight: 500; }
.ob-test.ok { color: #4ade80; }
.ob-test.fail { color: #fbbf24; }
.ob-btn {
  padding: 10px 20px; border-radius: 8px; font-size: 14px; font-weight: 500; cursor: pointer; border: none;
  transition: all .15s;
}
.ob-btn-primary { background: var(--color-accent, #4a9eff); color: white; }
.ob-btn-primary:hover:not(:disabled) { filter: brightness(1.1); }
.ob-btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
.ob-btn-ghost { background: transparent; color: var(--color-text-secondary, #aaa); }
.ob-btn-ghost:hover { color: var(--color-text, #fff); }
.ob-picker-btn { width: 100%; margin-bottom: 8px; }
.ob-path { font-size: 11px; color: var(--color-text-tertiary, #888); word-break: break-all; margin: 4px 0; }
.ob-actions { display: flex; justify-content: space-between; margin-top: 24px; }
.ob-suggestions { display: flex; flex-direction: column; gap: 8px; margin: 16px 0; }
.ob-suggestion {
  padding: 12px 16px; border-radius: 10px; text-align: left; font-size: 13px; cursor: pointer;
  background: var(--color-surface-container, rgba(255,255,255,0.03));
  border: 1px solid var(--color-border, rgba(255,255,255,0.08)); color: var(--color-text, #fff);
  transition: all .15s;
}
.ob-suggestion:hover { border-color: var(--color-accent, #4a9eff); background: rgba(74,158,255,0.08); }
</style>
