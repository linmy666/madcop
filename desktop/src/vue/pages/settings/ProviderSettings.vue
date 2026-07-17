<script setup lang="ts">
/**
 * ProviderSettings — Vue 3 provider management.
 * - Rich fields: auth strategy, API format, runtime kind, tool search,
 *   auto-compact window, notes.
 * - "Fetch models" pulls the live model catalog from {base_url}/models
 *   using the key you typed (no save required) so you can pick from the
 *   provider's real list.
 * - Model name is OPTIONAL: leave it empty and choose a model later in
 *   the session model selector.
 */

import { ref, onMounted, computed } from 'vue'
import { getApiUrl } from '../../../api/client'

interface Provider {
  provider_id: string
  label: string
  base_url: string
  model: string
  api_key: string
  api_key_masked?: string
  has_key: boolean
  preset_id?: string
  api_format?: string
  auth_strategy?: string
  runtime_kind?: string
  tool_search_enabled?: boolean
  auto_compact_window?: number
  notes?: string
  is_active?: boolean
  // Sampling parameters (v2.7) — returned by GET /api/settings, edited in
  // the form below, and applied by the backend chat handler.
  temperature?: number
  max_tokens?: number
  top_p?: number
}

interface ProviderPreset {
  id: string
  provider_id?: string // backend returns this instead of 'id'
  label: string
  base_url: string
  default_model: string
  apiFormat?: string
  authStrategy?: string
}

interface FetchedModel {
  id: string
  name: string
  context_window: number | null
}

const t = (key: string) => key

// ── Enums ───────────────────────────────────────────────────────────
const AUTH_STRATEGIES = [
  { value: 'api_key', label: 'API Key' },
  { value: 'auth_token', label: 'Auth Token' },
  { value: 'auth_token_empty_api_key', label: 'Auth Token (空 API Key)' },
  { value: 'dual_same_token', label: 'Dual (同 Token)' },
  { value: 'dual_dummy', label: 'Dual (Dummy Key)' },
]
const API_FORMATS = [
  { value: 'openai_chat', label: 'OpenAI Chat Completions' },
  { value: 'openai_responses', label: 'OpenAI Responses' },
  { value: 'anthropic', label: 'Anthropic' },
]
const RUNTIME_KINDS = [
  { value: '', label: '默认 (无)' },
  { value: 'anthropic_compatible', label: 'Anthropic Compatible' },
  { value: 'openai_oauth', label: 'OpenAI OAuth' },
]

// ── State ───────────────────────────────────────────────────────────
const providers = ref<Provider[]>([])
const presets = ref<ProviderPreset[]>([])
const activeProviderId = ref<string | null>(null)
const loading = ref(false)
const presetsLoading = ref(false)

// Edit modal
const showEditModal = ref(false)
const editingProvider = ref<Provider | null>(null)
const editForm = ref({
  provider_id: '',
  label: '',
  base_url: '',
  model: '' as string,
  api_key: '',
  preset_id: '',
  auth_strategy: 'api_key',
  api_format: 'openai_chat',
  runtime_kind: '',
  tool_search_enabled: true,
  auto_compact_window: 0 as number,
  notes: '',
  temperature: 0.7 as number,
  max_tokens: 8192 as number,
  top_p: 1.0 as number,
})

// Delete confirm
const pendingDelete = ref<Provider | null>(null)
const isDeleting = ref(false)

// Test results
const testResults = ref<Record<string, { loading: boolean; result?: any }>>({})

// Create modal
const showCreateModal = ref(false)
const createForm = ref({
  label: '',
  base_url: '',
  model: '' as string,
  api_key: '',
  preset_id: '',
  auth_strategy: 'api_key',
  api_format: 'openai_chat',
  runtime_kind: '',
  tool_search_enabled: true,
  auto_compact_window: 0 as number,
  notes: '',
  temperature: 0.7 as number,
  max_tokens: 8192 as number,
  top_p: 1.0 as number,
})

// Fetched models (cached per base_url+api_key signature)
const fetchedModels = ref<Record<string, { models: FetchedModel[]; loading: boolean; error?: string }>>({})
const fetchedSignature = ref<string>('')

function fetchKey(base: string, key: string) {
  return `${base}|${key}`
}

async function fetchModels(form: typeof createForm.value | typeof editForm.value) {
  const base = form.base_url.trim()
  const key = form.api_key.trim()
  if (!base || !key) {
    fetchedModels.value = { ...fetchedModels.value, [fetchKey(base, key)]: { models: [], loading: false, error: '请先填写 API 地址和 API Key' } }
    return
  }
  const k = fetchKey(base, key)
  fetchedModels.value = { ...fetchedModels.value, [k]: { models: [], loading: true } }
  try {
    const res = await fetch(getApiUrl('/api/settings/providers/fetch-models'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ base_url: base, api_key: key }),
    })
    const data = await res.json()
    fetchedModels.value = {
      ...fetchedModels.value,
      [k]: { models: data.models || [], loading: false, error: data.error },
    }
    fetchedSignature.value = k
  } catch (e: any) {
    fetchedModels.value = { ...fetchedModels.value, [k]: { models: [], loading: false, error: e?.message || '网络错误' } }
  }
}

const currentFetched = computed(() => {
  const form = showEditModal.value ? editForm.value : createForm.value
  const k = fetchKey(form.base_url.trim(), form.api_key.trim())
  return fetchedModels.value[k] || { models: [], loading: false }
})

// ── Load data ──────────────────────────────────────────────────────────
const loadError = ref<string | null>(null)

async function loadData() {
  loading.value = true
  loadError.value = null
  try {
    const res = await fetch(getApiUrl('/api/settings'))
    if (!res.ok) {
      loadError.value = `加载失败：后端返回 ${res.status}`
    } else {
      const data = await res.json()
      activeProviderId.value = data.active_provider || null
      providers.value = (data.providers || []).filter((p: Provider) => p.model || p.label)
    }
    const res2 = await fetch(getApiUrl('/api/settings/providers/presets'))
    if (res2.ok) {
      const data2 = await res2.json()
      // Backend returns 'provider_id' but the UI expects 'id' — normalize.
      presets.value = (data2.presets || []).map((p: any) => ({
        ...p,
        id: p.id || p.provider_id,
      }))
    }
  } catch (e: any) {
    loadError.value = `加载失败：${e?.message || '网络错误'}`
  } finally {
    loading.value = false
  }
}

onMounted(loadData)

// ── Provider presets ──────────────────────────────────────────────────
const presetOptions = computed(() => {
  const unique = new Map<string, ProviderPreset>()
  for (const p of presets.value) {
    if (!unique.has(p.id)) unique.set(p.id, p)
  }
  return Array.from(unique.values())
})

function applyPreset(preset: ProviderPreset) {
  createForm.value.preset_id = preset.id
  createForm.value.label = preset.label
  createForm.value.base_url = preset.base_url
  createForm.value.model = preset.default_model
  createForm.value.api_format = preset.apiFormat || 'openai_chat'
  createForm.value.auth_strategy = preset.authStrategy || 'api_key'
}

function applyPresetToEdit(preset: ProviderPreset) {
  editForm.value.preset_id = preset.id
  editForm.value.label = preset.label
  editForm.value.base_url = preset.base_url
  editForm.value.model = preset.default_model
  editForm.value.api_format = preset.apiFormat || 'openai_chat'
  editForm.value.auth_strategy = preset.authStrategy || 'api_key'
}

// ── Build payload ─────────────────────────────────────────────────────
function buildPayload(form: typeof createForm.value | typeof editForm.value) {
  const base: any = {
    label: form.label,
    base_url: form.base_url,
    api_format: form.api_format,
    auth_strategy: form.auth_strategy,
    runtime_kind: form.runtime_kind || '',
    tool_search_enabled: form.tool_search_enabled,
    notes: form.notes || '',
    // model is OPTIONAL — may be empty; user picks in session selector
    model: form.model || '',
    // keep the richer mapping consistent with the flat model
    models: { main: form.model || '', haiku: form.model || '', sonnet: form.model || '', opus: form.model || '' },
    // Sampling parameters — persisted per provider so different models
    // can use different temperatures (e.g. R1 at 0.6, code at 0.0).
    temperature: form.temperature,
    max_tokens: form.max_tokens,
    top_p: form.top_p,
  }
  if (form.api_key) base.api_key = form.api_key
  if (form.preset_id) base.preset_id = form.preset_id
  if (form.auto_compact_window && form.auto_compact_window > 0) {
    base.auto_compact_window = form.auto_compact_window
  }
  return base
}

// ── Create provider ───────────────────────────────────────────────────
async function createProvider() {
  if (!createForm.value.label || !createForm.value.base_url) return
  const body = buildPayload(createForm.value)
  try {
    const res = await fetch(getApiUrl('/api/settings'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ providers: [body] }),
    })
    if (res.ok) {
      showCreateModal.value = false
      createForm.value = {
        label: '', base_url: '', model: '', api_key: '', preset_id: '',
        auth_strategy: 'api_key', api_format: 'openai_chat', runtime_kind: '',
        tool_search_enabled: true, auto_compact_window: 0, notes: '',
      }
      await loadData()
    }
  } catch (e) {
    console.error('Failed to create provider', e)
  }
}

// ── Edit provider ─────────────────────────────────────────────────────
function openEdit(provider: Provider) {
  editingProvider.value = provider
  editForm.value = {
    provider_id: provider.provider_id,
    label: provider.label || '',
    base_url: provider.base_url || '',
    model: provider.model || '',
    api_key: '',
    preset_id: provider.preset_id || '',
    auth_strategy: provider.auth_strategy || 'api_key',
    api_format: provider.api_format || 'openai_chat',
    runtime_kind: provider.runtime_kind || '',
    tool_search_enabled: provider.tool_search_enabled !== false,
    auto_compact_window: provider.auto_compact_window || 0,
    notes: provider.notes || '',
    temperature: (provider as any).temperature ?? 0.7,
    max_tokens: (provider as any).max_tokens ?? 8192,
    top_p: (provider as any).top_p ?? 1.0,
  }
  showEditModal.value = true
}

async function saveEdit() {
  if (!editingProvider.value) return
  const body = buildPayload(editForm.value)
  try {
    await fetch(getApiUrl('/api/settings'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ providers: [{ ...body, provider_id: editForm.value.provider_id }] }),
    })
    showEditModal.value = false
    editingProvider.value = null
    await loadData()
  } catch (e) {
    console.error('Failed to save provider', e)
  }
}

// ── Delete provider ───────────────────────────────────────────────────
function confirmDelete(provider: Provider) {
  pendingDelete.value = provider
}

async function executeDelete() {
  if (!pendingDelete.value) return
  isDeleting.value = true
  try {
    await fetch(`/api/settings/${pendingDelete.value.provider_id}`, { method: 'DELETE' })
    pendingDelete.value = null
    await loadData()
  } catch (e) {
    console.error('Failed to delete provider', e)
  } finally {
    isDeleting.value = false
  }
}

// ── Activate provider ─────────────────────────────────────────────────
async function activateProvider(providerId: string) {
  try {
    await fetch(getApiUrl('/api/settings/active'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ provider_id: providerId }),
    })
    activeProviderId.value = providerId
  } catch (e) {
    console.error('Failed to activate provider', e)
  }
}

// ── Test provider ─────────────────────────────────────────────────────
async function testProvider(providerId: string) {
  testResults.value = { ...testResults.value, [providerId]: { loading: true } }
  try {
    const res = await fetch(getApiUrl(`/api/settings/providers/${providerId}/test`), { method: 'POST' })
    if (res.ok) {
      const result = await res.json()
      testResults.value = { ...testResults.value, [providerId]: { loading: false, result } }
    } else {
      testResults.value = { ...testResults.value, [providerId]: { loading: false, result: { error: 'Test failed' } } }
    }
  } catch {
    testResults.value = { ...testResults.value, [providerId]: { loading: false, result: { error: 'Network error' } } }
  }
}

// ── Mask API key ──────────────────────────────────────────────────────
function maskKey(key: string | undefined): string {
  if (!key) return ''
  if (key.length < 8) return '••••••••'
  return key.slice(0, 4) + '••••' + key.slice(-4)
}

function authLabel(v?: string) {
  return AUTH_STRATEGIES.find((x) => x.value === v)?.label || v || 'api_key'
}
function formatLabel(v?: string) {
  return API_FORMATS.find((x) => x.value === v)?.label || v || 'openai_chat'
}
function fmtContext(n: number | null | undefined) {
  if (!n) return '未知'
  if (n >= 1000000) return `${(n / 1000000).toFixed(n % 1000000 === 0 ? 0 : 1)}M`
  if (n >= 1000) return `${Math.round(n / 1000)}K`
  return `${n}`
}
</script>

<template>
  <div style="max-width: 720px;">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-[16px] font-semibold text-[var(--color-text-primary)]">模型供应商</h2>
        <p class="text-[13px] text-[var(--color-text-tertiary)] mt-0.5">管理你的 LLM API 提供方</p>
      </div>
      <div style="display: flex; gap: 8px; align-items: center;">
        <button
          @click="loadData"
          title="刷新"
          style="padding: 8px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 6px; cursor: pointer; color: var(--color-text-secondary); display: flex; align-items: center;"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M1 4v6h6M23 20v-6h-6"/><path d="M20.49 9A9 9 0 0 0 5.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 0 1 3.51 15"/></svg>
        </button>
        <button
          @click="showCreateModal = true"
          style="padding: 8px 16px; background: var(--color-brand); color: #fff; border: none; border-radius: 6px; font-size: 12px; font-weight: 500; cursor: pointer; display: flex; align-items: center; gap: 6px;"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          添加供应商
        </button>
      </div>
    </div>

    <!-- Error banner (shows when fetch fails so the user knows why the list is empty) -->
    <div v-if="loadError" style="padding: 12px 16px; background: rgba(239,68,68,0.08); border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; color: #dc2626; font-size: 13px; margin-bottom: 12px;">
      {{ loadError }}
    </div>

    <!-- Loading -->
    <div v-if="loading" style="padding: 40px; text-align: center; color: var(--color-text-tertiary); font-size: 13px;">
      加载中…
    </div>

    <!-- Empty state -->
    <div v-else-if="providers.length === 0" style="padding: 60px 20px; text-align: center; border: 1px dashed var(--color-border); border-radius: 8px;">
      <div style="font-size: 32px; margin-bottom: 12px; opacity: 0.3;">∅</div>
      <div style="font-size: 14px; color: var(--color-text-tertiary);">还没有配置模型供应商</div>
      <div style="font-size: 12px; color: var(--color-text-tertiary); margin-top: 4px; opacity: 0.7;">点击"添加供应商"开始配置</div>
    </div>

    <!-- Provider list -->
    <div v-else style="display: flex; flex-direction: column; gap: 8px;">
      <div
        v-for="p in providers"
        :key="p.provider_id"
        :class="['provider-card', activeProviderId === p.provider_id ? 'provider-card--active' : '']"
      >
        <div class="provider-card__header">
          <div class="provider-card__info">
            <div class="provider-card__name">
              {{ p.label || p.provider_id }}
              <span v-if="activeProviderId === p.provider_id" class="provider-card__badge">当前</span>
            </div>
            <div class="provider-card__model">{{ p.model || '未指定模型（在会话中选择）' }}</div>
          </div>
          <div class="provider-card__actions">
            <button v-if="activeProviderId !== p.provider_id" @click="activateProvider(p.provider_id)" class="provider-card__btn">设为当前</button>
            <button @click="testProvider(p.provider_id)" :disabled="testResults[p.provider_id]?.loading" class="provider-card__btn">{{ testResults[p.provider_id]?.loading ? '测试中…' : '测试' }}</button>
            <button @click="openEdit(p)" class="provider-card__btn">编辑</button>
            <button v-if="activeProviderId !== p.provider_id" @click="confirmDelete(p)" class="provider-card__btn provider-card__btn--danger">删除</button>
          </div>
        </div>
        <div class="provider-card__details">
          <span class="provider-card__detail" style="font-family: var(--font-mono);">{{ p.base_url }}</span>
          <span class="provider-card__detail" v-if="p.has_key">Key: {{ maskKey(p.api_key_masked) }}</span>
          <span class="provider-card__detail provider-card__detail--warn" v-else>未配置 API Key</span>
          <span class="provider-card__detail">{{ authLabel(p.auth_strategy) }}</span>
          <span class="provider-card__detail">{{ formatLabel(p.api_format) }}</span>
          <span class="provider-card__detail" v-if="p.tool_search_enabled">工具搜索</span>
          <!-- Sampling params summary (v2.7) — shows the persisted temp /
               max_tokens so the user can see what's configured at a glance. -->
          <span class="provider-card__detail" v-if="p.temperature != null">temp {{ Number(p.temperature).toFixed(2) }}</span>
          <span class="provider-card__detail" v-if="p.max_tokens">{{ p.max_tokens }} tokens</span>
          <span class="provider-card__detail" v-if="p.top_p != null && p.top_p < 1">top_p {{ Number(p.top_p).toFixed(2) }}</span>
        </div>
        <div v-if="testResults[p.provider_id]?.result" :class="['provider-card__test', testResults[p.provider_id]?.result?.connectivity?.success ? 'provider-card__test--ok' : 'provider-card__test--fail']">
          <template v-if="testResults[p.provider_id]?.result?.connectivity">
            {{ testResults[p.provider_id]?.result?.connectivity?.success ? '✓ 连接成功' : '✗ 连接失败' }}
            · {{ testResults[p.provider_id]?.result?.connectivity?.latencyMs }}ms
          </template>
          <template v-else>
            {{ testResults[p.provider_id]?.result?.error || '未知错误' }}
          </template>
        </div>
      </div>
    </div>

    <!-- ====================== Create Modal ====================== -->
    <Teleport to="body">
      <div v-if="showCreateModal" class="modal-overlay" @click.self="showCreateModal = false">
        <div class="modal-panel">
          <h3 class="modal-title">添加供应商</h3>

          <div style="margin-bottom: 12px;">
            <label class="modal-label">预设 (可选)</label>
            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
              <button v-for="preset in presetOptions" :key="preset.id" @click="applyPreset(preset)" :class="['modal-chip', createForm.preset_id === preset.id ? 'modal-chip--active' : '']">{{ preset.label }}</button>
            </div>
          </div>

          <div class="modal-field">
            <label class="modal-label">名称 <span class="req">*</span></label>
            <input v-model="createForm.label" type="text" class="modal-input" placeholder="例如: 我的GLM" />
          </div>
          <div class="modal-field">
            <label class="modal-label">API 地址 <span class="req">*</span></label>
            <input v-model="createForm.base_url" type="text" class="modal-input" placeholder="https://api.openai.com/v1" />
          </div>

          <!-- Fetch models -->
          <div class="modal-field">
            <div class="modal-label-row">
              <label class="modal-label">模型 (可选)</label>
              <button @click="fetchModels(createForm)" :disabled="currentFetched.loading" class="modal-btn modal-btn--small">
                {{ currentFetched.loading ? '拉取中…' : '拉取模型列表' }}
              </button>
            </div>
            <select v-model="createForm.model" class="modal-input" :disabled="currentFetched.loading">
              <option value="">— 不指定（在会话中选择）—</option>
              <option v-for="m in currentFetched.models" :key="m.id" :value="m.id">
                {{ m.name }} ({{ m.id }}) · ctx {{ fmtContext(m.context_window) }}
              </option>
            </select>
            <div v-if="currentFetched.error" class="modal-hint modal-hint--warn">{{ currentFetched.error }}</div>
            <div v-else-if="currentFetched.models.length" class="modal-hint">共 {{ currentFetched.models.length }} 个模型（也可留空，稍后在会话选择器里挑）</div>
          </div>

          <div class="modal-field">
            <label class="modal-label">API Key</label>
            <input v-model="createForm.api_key" type="password" class="modal-input" placeholder="sk-..." />
          </div>

          <div class="modal-grid">
            <div class="modal-field">
              <label class="modal-label">认证策略</label>
              <select v-model="createForm.auth_strategy" class="modal-input">
                <option v-for="o in AUTH_STRATEGIES" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div class="modal-field">
              <label class="modal-label">API 格式</label>
              <select v-model="createForm.api_format" class="modal-input">
                <option v-for="o in API_FORMATS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
          </div>

          <div class="modal-grid">
            <div class="modal-field">
              <label class="modal-label">运行类型 (Runtime)</label>
              <select v-model="createForm.runtime_kind" class="modal-input">
                <option v-for="o in RUNTIME_KINDS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div class="modal-field">
              <label class="modal-label">自动压缩窗口 (token)</label>
              <input v-model.number="createForm.auto_compact_window" type="number" min="0" step="1000" class="modal-input" placeholder="0 = 默认" />
            </div>
          </div>

          <!-- Sampling parameters — per-provider defaults for the LLM call.
               These replace the global hardcoded temperature=0.7/max_tokens=8192
               that ignored whatever the user chose. -->
          <div class="modal-grid-2">
            <div class="modal-field">
              <label class="modal-label">Temperature <span class="modal-hint">{{ createForm.temperature.toFixed(2) }}</span></label>
              <input v-model.number="createForm.temperature" type="range" min="0" max="2" step="0.05" class="modal-input" />
            </div>
            <div class="modal-field">
              <label class="modal-label">Max Tokens</label>
              <input v-model.number="createForm.max_tokens" type="number" min="256" step="256" class="modal-input" placeholder="8192" />
            </div>
            <div class="modal-field">
              <label class="modal-label">Top P <span class="modal-hint">{{ createForm.top_p.toFixed(2) }}</span></label>
              <input v-model.number="createForm.top_p" type="range" min="0.1" max="1" step="0.05" class="modal-input" />
            </div>
          </div>

          <div class="modal-field" style="display: flex; align-items: center; gap: 8px;">
            <input type="checkbox" v-model="createForm.tool_search_enabled" id="create-toolsearch" />
            <label for="create-toolsearch" class="modal-label" style="margin: 0;">启用工具搜索 (Tool Search)</label>
          </div>

          <div class="modal-field">
            <label class="modal-label">备注</label>
            <input v-model="createForm.notes" type="text" class="modal-input" placeholder="可选" />
          </div>

          <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px;">
            <button @click="showCreateModal = false" class="modal-btn">取消</button>
            <button
              @click="createProvider"
              :disabled="!createForm.label || !createForm.base_url"
              :class="['modal-btn modal-btn--primary', (!createForm.label || !createForm.base_url) ? 'modal-btn--disabled' : '']"
            >添加</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ====================== Edit Modal ====================== -->
    <Teleport to="body">
      <div v-if="showEditModal" class="modal-overlay" @click.self="showEditModal = false">
        <div class="modal-panel">
          <h3 class="modal-title">编辑供应商</h3>

          <div style="margin-bottom: 12px;">
            <label class="modal-label">预设 (可选)</label>
            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
              <button v-for="preset in presetOptions" :key="preset.id" @click="applyPresetToEdit(preset)" :class="['modal-chip', editForm.preset_id === preset.id ? 'modal-chip--active' : '']">{{ preset.label }}</button>
            </div>
          </div>

          <div class="modal-field">
            <label class="modal-label">名称 <span class="req">*</span></label>
            <input v-model="editForm.label" type="text" class="modal-input" />
          </div>
          <div class="modal-field">
            <label class="modal-label">API 地址 <span class="req">*</span></label>
            <input v-model="editForm.base_url" type="text" class="modal-input" />
          </div>

          <div class="modal-field">
            <div class="modal-label-row">
              <label class="modal-label">模型 (可选)</label>
              <button @click="fetchModels(editForm)" :disabled="currentFetched.loading" class="modal-btn modal-btn--small">
                {{ currentFetched.loading ? '拉取中…' : '拉取模型列表' }}
              </button>
            </div>
            <select v-model="editForm.model" class="modal-input" :disabled="currentFetched.loading">
              <option value="">— 不指定（在会话中选择）—</option>
              <option v-for="m in currentFetched.models" :key="m.id" :value="m.id">
                {{ m.name }} ({{ m.id }}) · ctx {{ fmtContext(m.context_window) }}
              </option>
            </select>
            <div v-if="currentFetched.error" class="modal-hint modal-hint--warn">{{ currentFetched.error }}</div>
            <div v-else-if="currentFetched.models.length" class="modal-hint">共 {{ currentFetched.models.length }} 个模型</div>
          </div>

          <div class="modal-field">
            <label class="modal-label">API Key (留空不修改)</label>
            <input v-model="editForm.api_key" type="password" class="modal-input" placeholder="不修改则留空" />
          </div>

          <div class="modal-grid">
            <div class="modal-field">
              <label class="modal-label">认证策略</label>
              <select v-model="editForm.auth_strategy" class="modal-input">
                <option v-for="o in AUTH_STRATEGIES" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div class="modal-field">
              <label class="modal-label">API 格式</label>
              <select v-model="editForm.api_format" class="modal-input">
                <option v-for="o in API_FORMATS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
          </div>

          <div class="modal-grid">
            <div class="modal-field">
              <label class="modal-label">运行类型 (Runtime)</label>
              <select v-model="editForm.runtime_kind" class="modal-input">
                <option v-for="o in RUNTIME_KINDS" :key="o.value" :value="o.value">{{ o.label }}</option>
              </select>
            </div>
            <div class="modal-field">
              <label class="modal-label">自动压缩窗口 (token)</label>
              <input v-model.number="editForm.auto_compact_window" type="number" min="0" step="1000" class="modal-input" placeholder="0 = 默认" />
            </div>
          </div>

          <!-- Sampling parameters (same as create form). -->
          <div class="modal-grid-2">
            <div class="modal-field">
              <label class="modal-label">Temperature <span class="modal-hint">{{ editForm.temperature.toFixed(2) }}</span></label>
              <input v-model.number="editForm.temperature" type="range" min="0" max="2" step="0.05" class="modal-input" />
            </div>
            <div class="modal-field">
              <label class="modal-label">Max Tokens</label>
              <input v-model.number="editForm.max_tokens" type="number" min="256" step="256" class="modal-input" placeholder="8192" />
            </div>
            <div class="modal-field">
              <label class="modal-label">Top P <span class="modal-hint">{{ editForm.top_p.toFixed(2) }}</span></label>
              <input v-model.number="editForm.top_p" type="range" min="0.1" max="1" step="0.05" class="modal-input" />
            </div>
          </div>

          <div class="modal-field" style="display: flex; align-items: center; gap: 8px;">
            <input type="checkbox" v-model="editForm.tool_search_enabled" id="edit-toolsearch" />
            <label for="edit-toolsearch" class="modal-label" style="margin: 0;">启用工具搜索 (Tool Search)</label>
          </div>

          <div class="modal-field">
            <label class="modal-label">备注</label>
            <input v-model="editForm.notes" type="text" class="modal-input" placeholder="可选" />
          </div>

          <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px;">
            <button @click="showEditModal = false" class="modal-btn">取消</button>
            <button
              @click="saveEdit"
              :disabled="!editForm.label || !editForm.base_url"
              :class="['modal-btn modal-btn--primary', (!editForm.label || !editForm.base_url) ? 'modal-btn--disabled' : '']"
            >保存</button>
          </div>
        </div>
      </div>
    </Teleport>

    <!-- ====================== Delete Confirm ====================== -->
    <Teleport to="body">
      <div v-if="pendingDelete" class="modal-overlay" @click.self="pendingDelete = null">
        <div class="modal-panel" style="max-width: 400px;">
          <h3 class="modal-title">确认删除</h3>
          <p style="font-size: 13px; color: var(--color-text-secondary); margin: 8px 0;">
            确定要删除供应商「{{ pendingDelete.label || pendingDelete.provider_id }}」？
          </p>
          <div style="display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px;">
            <button @click="pendingDelete = null" class="modal-btn">取消</button>
            <button
              @click="executeDelete"
              :disabled="isDeleting"
              :class="['modal-btn', isDeleting ? 'modal-btn--disabled' : 'modal-btn--danger']"
            >{{ isDeleting ? '删除中…' : '删除' }}</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.provider-card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 14px 16px;
  transition: border-color 0.15s;
}
.provider-card:hover { border-color: var(--color-border-focus); }
.provider-card--active {
  border-color: var(--color-brand);
  background: color-mix(in srgb, var(--color-brand) 3%, var(--color-surface));
}
.provider-card__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.provider-card__info { flex: 1; }
.provider-card__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  display: flex;
  align-items: center;
  gap: 8px;
}
.provider-card__badge {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding: 1px 6px;
  border-radius: 8px;
  background: var(--color-brand);
  color: #fff;
  font-weight: 600;
}
.provider-card__model {
  font-size: 11px;
  color: var(--color-text-tertiary);
  margin-top: 2px;
  font-family: var(--font-mono);
}
.provider-card__actions {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  flex-shrink: 0;
}
.provider-card__btn {
  padding: 4px 10px;
  font-size: 11px;
  background: var(--color-surface-container);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all 0.1s;
  white-space: nowrap;
}
.provider-card__btn:hover { background: var(--color-surface-container-high); }
.provider-card__btn--danger { color: var(--color-error); border-color: color-mix(in srgb, var(--color-error) 30%, transparent); }
.provider-card__btn--danger:hover { background: color-mix(in srgb, var(--color-error) 5%, transparent); }
.provider-card__details {
  margin-top: 8px;
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: var(--color-text-tertiary);
  flex-wrap: wrap;
}
.provider-card__detail--warn { color: var(--color-warning); }
.provider-card__test {
  margin-top: 8px;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 11px;
}
.provider-card__test--ok { background: color-mix(in srgb, var(--color-success) 8%, transparent); color: var(--color-success); }
.provider-card__test--fail { background: color-mix(in srgb, var(--color-error) 8%, transparent); color: var(--color-error); }

/* Modal styles */
.modal-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(0, 0, 0, 0.4);
  display: flex; align-items: center; justify-content: center;
}
.modal-panel {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 20px 24px;
  width: 540px;
  max-width: 92vw;
  max-height: 85vh;
  overflow-y: auto;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
}
.modal-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0 0 16px;
}
.modal-field { margin-bottom: 12px; }
.modal-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.modal-label {
  display: block;
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}
.modal-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}
.modal-label-row .modal-label { margin-bottom: 0; }
.req { color: var(--color-error); }
.modal-input {
  width: 100%;
  padding: 8px 10px;
  background: var(--color-surface-container);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 13px;
  color: var(--color-text-primary);
  font-family: inherit;
  outline: none;
  box-sizing: border-box;
}
.modal-input:focus { border-color: var(--color-brand); }
.modal-hint { font-size: 11px; color: var(--color-text-tertiary); margin-top: 4px; }
.modal-hint--warn { color: var(--color-warning); }
.modal-btn {
  padding: 8px 16px;
  border: 1px solid var(--color-border);
  border-radius: 6px;
  background: var(--color-surface);
  color: var(--color-text-primary);
  font-size: 12px;
  cursor: pointer;
  font-weight: 500;
}
.modal-btn--small { padding: 4px 10px; font-size: 11px; }
.modal-btn--primary { background: var(--color-brand); color: #fff; border-color: var(--color-brand); }
.modal-btn--danger { color: var(--color-error); border-color: var(--color-error); }
.modal-btn--disabled { opacity: 0.4; cursor: not-allowed; }
.modal-chip {
  padding: 4px 10px;
  font-size: 11px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  cursor: pointer;
}
.modal-chip--active { background: var(--color-brand); color: #fff; border-color: var(--color-brand); }
</style>
