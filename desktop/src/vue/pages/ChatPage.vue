<script setup lang="ts">
// v3.0 — Chat placeholder
// Real chat page (ActiveSession) is a 600-line React component.
// Migrating it to Vue 3 is Phase 3. For now, this placeholder
// lets the Vue shell mount and prove end-to-end Vue 3 wiring.
</script>

<template>
  <div class="vue-chat">
    <h2>Vue 3 聊天 (Phase 3 待迁移)</h2>
    <p>React 端的 ActiveSession.tsx 即将转换为 Vue 3 Composition API。</p>
    <p>当前显示此页面证明 Vue 3 框架 + Pinia 路由 + Shell 全部跑通。</p>
  </div>
</template>

<style scoped>
.vue-chat { padding: 60px 40px; max-width: 640px; margin: 0 auto; color: var(--madcop-ink-muted); }
.vue-chat h2 { color: var(--madcop-accent); font-size: 20px; margin-bottom: 12px; }
.vue-chat p  { font-size: 13px; line-height: 1.6; margin-bottom: 8px; }
</style>
