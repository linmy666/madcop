<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { computerUseApi, type ComputerUseStatus } from '../api/computerUse'

const status = ref<ComputerUseStatus | null>(null)
const loading = ref(true)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    status.value = await computerUseApi.getStatus()
  } catch (e: any) {
    error.value = e?.message || 'Failed to load status'
  } finally {
    loading.value = false
  }
})

function openSettings(pane: 'Privacy_ScreenCapture' | 'Privacy_Accessibility') {
  computerUseApi.openSettings(pane).catch(() => {})
}

function permLabel(v: boolean | null | undefined): { text: string; ok: boolean | null } {
  if (v === true) return { text: '已授权', ok: true }
  if (v === false) return { text: '未授权', ok: false }
  return { text: '检测失败', ok: null }
}
</script>

<template>
  <div class="cu mx-auto max-w-2xl space-y-5">
    <header class="flex items-start justify-between gap-3">
      <div>
        <div class="cu__eyebrow">系统</div>
        <h2 class="cu__title">计算机使用</h2>
        <p class="cu__desc">允许 Agent 操控 macOS — 屏幕点击、键盘输入、应用切换</p>
      </div>
      <span v-if="status?.dependencies?.bridge" class="cu-badge">
        {{ status.dependencies.bridge === 'jxa' ? 'macOS 原生' : status.dependencies.bridge }}
      </span>
    </header>

    <div v-if="loading" class="cu-state">
      <span class="material-symbols-outlined animate-spin text-[20px]">progress_activity</span>
      检测权限与环境…
    </div>

    <div v-if="error" class="cu-error">
      <span class="material-symbols-outlined text-[18px]">error</span>
      {{ error }}
    </div>

    <template v-if="status">
      <!-- Permissions -->
      <section class="cu-card">
        <div class="cu-card__head">
          <span class="material-symbols-outlined cu-card__icon">security</span>
          <h3 class="cu-card__title">权限检测</h3>
        </div>

        <div class="cu-row">
          <div class="cu-row__info">
            <div class="cu-row__label">辅助功能权限</div>
            <div class="cu-row__desc">控制其他应用的 UI 元素</div>
          </div>
          <div class="cu-row__actions">
            <span
              class="cu-perm"
              :class="{
                'cu-perm--ok': permLabel(status.permissions.accessibility).ok === true,
                'cu-perm--bad': permLabel(status.permissions.accessibility).ok === false,
              }"
            >
              {{ permLabel(status.permissions.accessibility).text }}
            </span>
            <button
              v-if="status.permissions.accessibility === false"
              type="button"
              class="cu-btn"
              @click="openSettings('Privacy_Accessibility')"
            >
              打开设置
            </button>
          </div>
        </div>

        <div class="cu-row">
          <div class="cu-row__info">
            <div class="cu-row__label">屏幕录制权限</div>
            <div class="cu-row__desc">访问窗口列表和元素位置（定位点击）</div>
          </div>
          <div class="cu-row__actions">
            <span
              class="cu-perm"
              :class="{
                'cu-perm--ok': permLabel(status.permissions.screenRecording).ok === true,
                'cu-perm--bad': permLabel(status.permissions.screenRecording).ok === false,
              }"
            >
              {{ permLabel(status.permissions.screenRecording).text }}
            </span>
            <button
              v-if="status.permissions.screenRecording === false"
              type="button"
              class="cu-btn"
              @click="openSettings('Privacy_ScreenCapture')"
            >
              打开设置
            </button>
          </div>
        </div>
      </section>

      <!-- Runtime -->
      <section class="cu-card">
        <div class="cu-card__head">
          <span class="material-symbols-outlined cu-card__icon">memory</span>
          <h3 class="cu-card__title">运行环境</h3>
        </div>
        <div class="cu-row">
          <div class="cu-row__label">平台</div>
          <span class="cu-mono">{{ status.platform }} / {{ status.supported ? '支持' : '不支持' }}</span>
        </div>
        <div class="cu-row">
          <div class="cu-row__info">
            <div class="cu-row__label">Python</div>
            <div v-if="status.python.path" class="cu-row__desc cu-mono">{{ status.python.path }}</div>
          </div>
          <span class="cu-mono">{{ status.python.installed ? status.python.version || 'ok' : '未找到' }}</span>
        </div>
      </section>

      <!-- Apps -->
      <section class="cu-card">
        <div class="cu-card__head">
          <span class="material-symbols-outlined cu-card__icon">apps</span>
          <h3 class="cu-card__title">运行中的应用</h3>
          <span class="cu-count">{{ status.apps?.length ?? 0 }}</span>
        </div>
        <div v-if="!(status as any).apps?.length" class="cu-empty">暂无检测到前台应用列表</div>
        <div
          v-for="app in (status as any).apps"
          :key="app.bundleId"
          class="cu-app"
        >
          <span class="cu-app__name">{{ app.displayName || app.name }}</span>
          <span class="cu-app__id">{{ app.bundleId }}</span>
        </div>
      </section>
    </template>
  </div>
</template>

<style scoped>
.cu__eyebrow {
  font-size: 11px; font-weight: 600; letter-spacing: 0.04em;
  color: var(--color-text-tertiary); margin-bottom: 6px;
}
.cu__title { margin: 0; font-size: 18px; font-weight: 700; color: var(--color-text-primary); }
.cu__desc { margin: 6px 0 0; font-size: 13px; color: var(--color-text-secondary); line-height: 1.45; max-width: 36rem; }

.cu-badge {
  flex-shrink: 0; font-size: 11px; font-weight: 600;
  padding: 4px 10px; border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-surface-container-low);
  color: var(--color-text-tertiary);
}

.cu-state {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  padding: 32px; font-size: 13px; color: var(--color-text-tertiary);
  border: 1px dashed var(--color-border); border-radius: 16px;
}
.cu-error {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 14px; border-radius: 12px; font-size: 13px;
  color: var(--color-error, var(--color-danger));
  background: color-mix(in srgb, var(--color-error, #ef4444) 8%, transparent);
  border: 1px solid color-mix(in srgb, var(--color-error, #ef4444) 20%, transparent);
}

.cu-card {
  border: 1px solid var(--color-border);
  border-radius: 16px;
  background: var(--color-surface);
  overflow: hidden;
}
.cu-card__head {
  display: flex; align-items: center; gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-surface-container-low);
}
.cu-card__icon { font-size: 18px; color: var(--color-brand); }
.cu-card__title { margin: 0; font-size: 13px; font-weight: 600; color: var(--color-text-primary); flex: 1; }
.cu-count {
  font-size: 11px; font-weight: 600; font-variant-numeric: tabular-nums;
  padding: 2px 8px; border-radius: 999px;
  background: var(--color-surface-container-high);
  color: var(--color-text-tertiary);
}

.cu-row {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--color-border-separator, var(--color-border));
}
.cu-row:last-child { border-bottom: none; }
.cu-row__info { flex: 1; min-width: 0; }
.cu-row__label { font-size: 13px; font-weight: 500; color: var(--color-text-primary); }
.cu-row__desc { font-size: 11px; color: var(--color-text-tertiary); margin-top: 2px; word-break: break-all; }
.cu-row__actions { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

.cu-perm {
  font-size: 11px; font-weight: 600; padding: 3px 8px; border-radius: 999px;
  background: var(--color-surface-container-high); color: var(--color-text-tertiary);
}
.cu-perm--ok {
  background: color-mix(in srgb, var(--color-success) 12%, transparent);
  color: var(--color-success);
}
.cu-perm--bad {
  background: color-mix(in srgb, var(--color-error, #ef4444) 12%, transparent);
  color: var(--color-error, var(--color-danger));
}
.cu-btn {
  font-size: 11px; font-weight: 500; padding: 5px 10px; border-radius: 8px;
  border: 1px solid var(--color-border); background: var(--color-surface);
  color: var(--color-text-secondary); cursor: pointer;
}
.cu-btn:hover { background: var(--color-surface-hover); color: var(--color-text-primary); }

.cu-mono { font-family: var(--font-mono); font-size: 12px; color: var(--color-text-secondary); }
.cu-empty { padding: 20px 16px; text-align: center; font-size: 12px; color: var(--color-text-tertiary); }

.cu-app {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--color-border-separator, var(--color-border));
}
.cu-app:last-child { border-bottom: none; }
.cu-app__name { font-size: 13px; color: var(--color-text-primary); }
.cu-app__id {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--color-text-tertiary); max-width: 45%; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
</style>
