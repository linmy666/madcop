<script setup lang="ts">
// v3.0 — ComputerUseSettings (placeholder)
import { ref } from 'vue'
const enabled = ref(true)
</script>
<template>
  <div style="max-width: 640px;">
    <h2 class="text-[16px] font-semibold text-[var(--color-text-primary)] mb-1">计算机使用</h2>
    <p class="text-[13px] text-[var(--color-text-tertiary)] mb-6">计算机使用设置</p>
    <div style="display: flex; align-items: center; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid var(--color-border-separator);">
      <div>
        <div style="font-size: 13px; font-weight: 500; color: var(--color-text-primary);">启用计算机使用</div>
        <div style="font-size: 11px; color: var(--color-text-tertiary); margin-top: 2px;">允许 Agent 访问你的屏幕和键盘</div>
      </div>
      <div
        :class="['settings-toggle', enabled ? 'settings-toggle--on' : '']"
        @click="enabled = !enabled"
      >
        <div class="settings-toggle__thumb"></div>
      </div>
    </div>
  </div>
</template>
<style scoped>
.settings-toggle {
  width: 36px; height: 20px; border-radius: 10px;
  background: var(--color-border); cursor: pointer; position: relative;
  transition: background 0.15s;
}
.settings-toggle--on { background: var(--color-brand); }
.settings-toggle__thumb {
  width: 16px; height: 16px; border-radius: 50%;
  background: #fff; position: absolute; top: 2px; left: 2px;
  transition: transform 0.15s;
}
.settings-toggle--on .settings-toggle__thumb { transform: translateX(16px); }
</style>