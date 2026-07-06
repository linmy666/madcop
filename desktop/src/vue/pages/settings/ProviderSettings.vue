<script setup lang="ts">
/**
 * ProviderSettings — Vue 3 port of the React ProviderSettings component.
 * Manages model providers: add, edit, delete, test, activate.
 * Fetches from /api/settings and /api/settings/providers endpoints.
 */

import { ref, onMounted, computed } from 'vue'

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
  is_active?: boolean
  notes?: string
}

interface ProviderPreset {
  id: string
  label: string
  base_url: string
  default_model: string
}

const t = (key: string) => key

// ── State ──────────────────────────────────────────────────────────────

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
  model: '',
  api_key: '',
  preset_id: '',
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
  model: '',
  api_key: '',
  preset_id: '',
})

// ── Load data ──────────────────────────────────────────────────────────

async function loadData() {
  loading.value = true
  try {
    const res = await fetch('/api/settings')
    if (res.ok) {
      const data = await res.json()
      activeProviderId.value = data.active_provider || null
      providers.value = (data.providers || []).filter((p: Provider) => p.model || p.label)
    }
    // Load presets
    const res2 = await fetch('/api/settings/providers/presets')
    if (res2.ok) {
      const data2 = await res2.json()
      presets.value = data2.presets || []
    }
  } catch {
    // ignore
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
  createForm.value = {
    ...createForm.value,
    preset_id: preset.id,
    label: preset.label,
    base_url: preset.base_url,
    model: preset.default_model,
  }
}

function applyPresetToEdit(preset: ProviderPreset) {
  editForm.value = {
    ...editForm.value,
    preset_id: preset.id,
    label: preset.label,
    base_url: preset.base_url,
    model: preset.default_model,
  }
}

// ── Create provider ───────────────────────────────────────────────────

async function createProvider() {
  if (!createForm.value.label || !createForm.value.base_url) return
  const body: any = {
    label: createForm.value.label,
    base_url: createForm.value.base_url,
    model: createForm.value.model || 'default',
  }
  if (createForm.value.api_key) body.api_key = createForm.value.api_key
  if (createForm.value.preset_id) body.preset_id = createForm.value.preset_id

  try {
    const res = await fetch('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ providers: [body] }),
    })
    if (res.ok) {
      showCreateModal.value = false
      createForm.value = { label: '', base_url: '', model: '', api_key: '', preset_id: '' }
      // Reload
      const settingsRes = await fetch('/api/settings')
      if (settingsRes.ok) {
        const data = await settingsRes.json()
        providers.value = (data.providers || []).filter((p: Provider) => p.model || p.label)
      }
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
  }
  showEditModal.value = true
}

async function saveEdit() {
  if (!editingProvider.value) return
  const body: any = {
    label: editForm.value.label,
    base_url: editForm.value.base_url,
    model: editForm.value.model,
  }
  if (editForm.value.api_key) body.api_key = editForm.value.api_key

  try {
    await fetch(`/api/settings`, {
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
    await fetch('/api/settings/active', {
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
    const res = await fetch(`/api/settings/providers/${providerId}/test`, { method: 'POST' })
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
</script>

<template>
  <div style="max-width: 640px;">
    <div class="flex items-center justify-between mb-4">
      <div>
        <h2 class="text-[16px] font-semibold text-[var(--color-text-primary)]">模型供应商</h2>
        <p class="text-[13px] text-[var(--color-text-tertiary)] mt-0.5">管理你的 LLM API 提供方</p>
      </div>
      <button
        @click="showCreateModal = true"
        style="padding: 8px 16px; background: var(--color-brand); color: #fff; border: none; border-radius: 6px; font-size: 12px; font-weight: 500; cursor: pointer; display: flex; align-items: center; gap: 6px;"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        添加供应商
      </button>
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
            <div class="provider-card__model">{{ p.model }}</div>
          </div>
          <div class="provider-card__actions">
            <button
              v-if="activeProviderId !== p.provider_id"
              @click="activateProvider(p.provider_id)"
              title="设为当前"
              class="provider-card__btn"
            >设为当前</button>
            <button
              @click="testProvider(p.provider_id)"
              :disabled="testResults[p.provider_id]?.loading"
              title="测试连接"
              class="provider-card__btn"
            >{{ testResults[p.provider_id]?.loading ? '测试中…' : '测试' }}</button>
            <button @click="openEdit(p)" class="provider-card__btn">编辑</button>
            <button
              v-if="activeProviderId !== p.provider_id"
              @click="confirmDelete(p)"
              class="provider-card__btn provider-card__btn--danger"
            >删除</button>
          </div>
        </div>
        <div class="provider-card__details">
          <span class="provider-card__detail" style="font-family: ui-monospace, monospace;">{{ p.base_url }}</span>
          <span class="provider-card__detail" v-if="p.has_key">Key: {{ maskKey(p.api_key_masked) }}</span>
          <span class="provider-card__detail provider-card__detail--warn" v-else>未配置 API Key</span>
        </div>
        <!-- Test result -->
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
              <button
                v-for="preset in presetOptions"
                :key="preset.id"
                @click="applyPreset(preset)"
                :class="['modal-chip', createForm.preset_id === preset.id ? 'modal-chip--active' : '']"
              >{{ preset.label }}</button>
            </div>
          </div>

          <div class="modal-field">
            <label class="modal-label">名称</label>
            <input v-model="createForm.label" type="text" class="modal-input" placeholder="例如: 我的GLM" />
          </div>
          <div class="modal-field">
            <label class="modal-label">API 地址</label>
            <input v-model="createForm.base_url" type="text" class="modal-input" placeholder="https://api.openai.com/v1" />
          </div>
          <div class="modal-field">
            <label class="modal-label">模型名</label>
            <input v-model="createForm.model" type="text" class="modal-input" placeholder="gpt-4o-mini" />
          </div>
          <div class="modal-field">
            <label class="modal-label">API Key</label>
            <input v-model="createForm.api_key" type="password" class="modal-input" placeholder="sk-..." />
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
              <button
                v-for="preset in presetOptions"
                :key="preset.id"
                @click="applyPresetToEdit(preset)"
                :class="['modal-chip', editForm.preset_id === preset.id ? 'modal-chip--active' : '']"
              >{{ preset.label }}</button>
            </div>
          </div>

          <div class="modal-field">
            <label class="modal-label">名称</label>
            <input v-model="editForm.label" type="text" class="modal-input" />
          </div>
          <div class="modal-field">
            <label class="modal-label">API 地址</label>
            <input v-model="editForm.base_url" type="text" class="modal-input" />
          </div>
          <div class="modal-field">
            <label class="modal-label">模型名</label>
            <input v-model="editForm.model" type="text" class="modal-input" />
          </div>
          <div class="modal-field">
            <label class="modal-label">API Key (留空不修改)</label>
            <input v-model="editForm.api_key" type="password" class="modal-input" placeholder="不修改则留空" />
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
  font-family: ui-monospace, monospace;
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
  width: 480px;
  max-width: 90vw;
  max-height: 80vh;
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
.modal-label {
  display: block;
  font-size: 11px;
  font-weight: 500;
  color: var(--color-text-secondary);
  margin-bottom: 4px;
}
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