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
</script>

<template>
  <div style="max-width: 640px;">
    <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 4px;">
      <h2 class="text-[16px] font-semibold text-[var(--color-text-primary)]">计算机使用</h2>
      <span v-if="status?.dependencies?.bridge" class="text-[11px] text-[var(--color-text-tertiary)]">
        {{ status.dependencies.bridge === 'jxa' ? 'macOS 原生' : status.dependencies.bridge }}
      </span>
    </div>
    <p class="text-[13px] text-[var(--color-text-tertiary)] mb-6">
      允许 Agent 操控你的 macOS — 屏幕点击、键盘输入、应用切换
    </p>

    <!-- Loading -->
    <div v-if="loading" style="padding: 24px 0; text-align: center; font-size: 13px; color: var(--color-text-tertiary);">检测中...</div>

    <!-- Error -->
    <div v-if="error" style="padding: 12px; background: rgba(255,0,0,0.06); border-radius: 6px; font-size: 13px; color: var(--color-danger);">{{ error }}</div>

    <!-- Status sections -->
    <template v-if="status">
      <!-- 1. 权限检测 -->
      <div style="margin-top: 20px;">
        <div style="font-size: 13px; font-weight: 500; color: var(--color-text-primary); margin-bottom: 8px;">权限检测</div>
        <!-- Accessibility -->
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--color-border-separator);">
          <div>
            <div style="font-size: 13px; color: var(--color-text-primary);">辅助功能权限</div>
            <div style="font-size: 11px; color: var(--color-text-tertiary); margin-top: 2px;">控制其他应用的 UI 元素</div>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span v-if="status.permissions.accessibility === true" style="font-size: 11px; color: var(--color-text-success);">✓ 已授权</span>
            <span v-else-if="status.permissions.accessibility === false" style="font-size: 11px; color: var(--color-danger);">✗ 未授权</span>
            <span v-else style="font-size: 11px; color: var(--color-text-tertiary);">检测失败</span>
            <button v-if="status.permissions.accessibility === false"
              @click="openSettings('Privacy_Accessibility')"
              style="font-size: 11px; padding: 3px 10px; border-radius: 4px; border: 1px solid var(--color-border); background: transparent; color: var(--color-text-secondary); cursor: pointer;">
              打开设置
            </button>
          </div>
        </div>
        <!-- Screen Recording -->
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--color-border-separator);">
          <div>
            <div style="font-size: 13px; color: var(--color-text-primary);">屏幕录制权限</div>
            <div style="font-size: 11px; color: var(--color-text-tertiary); margin-top: 2px;">访问窗口列表和元素位置 (定位点击)</div>
          </div>
          <div style="display: flex; align-items: center; gap: 8px;">
            <span v-if="status.permissions.screenRecording === true" style="font-size: 11px; color: var(--color-text-success);">✓ 已授权</span>
            <span v-else-if="status.permissions.screenRecording === false" style="font-size: 11px; color: var(--color-danger);">✗ 未授权</span>
            <span v-else style="font-size: 11px; color: var(--color-text-tertiary);">检测失败</span>
            <button v-if="status.permissions.screenRecording === false"
              @click="openSettings('Privacy_ScreenCapture')"
              style="font-size: 11px; padding: 3px 10px; border-radius: 4px; border: 1px solid var(--color-border); background: transparent; color: var(--color-text-secondary); cursor: pointer;">
              打开设置
            </button>
          </div>
        </div>
      </div>

      <!-- 2. 运行环境 -->
      <div style="margin-top: 24px;">
        <div style="font-size: 13px; font-weight: 500; color: var(--color-text-primary); margin-bottom: 8px;">运行环境</div>
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--color-border-separator);">
          <div style="font-size: 13px; color: var(--color-text-primary);">平台</div>
          <span style="font-size: 13px; color: var(--color-text-secondary);">{{ status.platform }} / {{ status.supported ? '支持' : '不支持' }}</span>
        </div>
        <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid var(--color-border-separator);">
          <div>
            <div style="font-size: 13px; color: var(--color-text-primary);">Python</div>
            <div v-if="status.python.path" style="font-size: 11px; color: var(--color-text-tertiary); margin-top: 2px;">{{ status.python.path }}</div>
          </div>
          <span style="font-size: 13px; color: var(--color-text-secondary);">{{ status.python.installed ? status.python.version || 'ok' : '未找到' }}</span>
        </div>
      </div>

      <!-- 3. 运行中的应用 -->
      <div style="margin-top: 24px;">
        <div style="font-size: 13px; font-weight: 500; color: var(--color-text-primary); margin-bottom: 8px;">运行中的应用 ({{ status.apps?.length || '...' }})</div>
        <div v-if="loading" style="font-size: 12px; color: var(--color-text-tertiary);">加载中...</div>
        <div v-for="app in (status as any).apps" :key="app.bundleId"
          style="display: flex; align-items: center; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid var(--color-border-separator); font-size: 13px;">
          <span style="color: var(--color-text-primary);">{{ app.displayName || app.name }}</span>
          <span style="font-size: 11px; color: var(--color-text-tertiary);">{{ app.bundleId }}</span>
        </div>
      </div>
    </template>
  </div>
</template>