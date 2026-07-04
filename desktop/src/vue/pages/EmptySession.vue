<script setup lang="ts">
// v3.0 — Empty session placeholder (Vue 3)
// Shown when no tab is active. Tells the user to pick a section from
// the sidebar or start a new chat.
</script>

<template>
  <div class="empty-session">
    <div class="empty-session__inner">
      <div class="empty-session__brand">M</div>
      <h1 class="empty-session__title">欢迎使用 MadCop</h1>
      <p class="empty-session__subtitle">
        从左侧选择一个面板开始，或创建一个新会话。
      </p>
      <div class="empty-session__actions">
        <button class="empty-session__btn empty-session__btn--primary" @click="$emit('new-chat')">
          新建会话
        </button>
        <button class="empty-session__btn" @click="$emit('open-design')">
          打开设计工具
        </button>
      </div>
      <div class="empty-session__hints">
        <div class="empty-session__hint">
          <span class="empty-session__hint-glyph">◇</span>
          <span>聊天 — 与多模型对话，本地记忆</span>
        </div>
        <div class="empty-session__hint">
          <span class="empty-session__hint-glyph">◰</span>
          <span>设计 — AI 生成 UI 原型</span>
        </div>
        <div class="empty-session__hint">
          <span class="empty-session__hint-glyph">⬡</span>
          <span>工作流 — 12 种 Agent 编排模板</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.empty-session {
  height: 100%;
  display: flex; align-items: center; justify-content: center;
  background: var(--madcop-panel);
  padding: 40px 20px;
}
.empty-session__inner {
  max-width: 480px; text-align: center;
}
.empty-session__brand {
  width: 56px; height: 56px;
  background: var(--madcop-accent);
  color: var(--madcop-accent-ink);
  font-weight: 700; font-size: 24px;
  display: flex; align-items: center; justify-content: center;
  margin: 0 auto 20px;
  font-family: 'Geist Mono', monospace;
}
.empty-session__title {
  font-size: 24px; font-weight: 600; color: var(--madcop-ink);
  margin: 0 0 8px; letter-spacing: -0.01em;
}
.empty-session__subtitle {
  font-size: 13px; color: var(--madcop-ink-muted);
  margin: 0 0 24px; line-height: 1.6;
}
.empty-session__actions {
  display: flex; gap: 8px; justify-content: center; margin-bottom: 32px;
}
.empty-session__btn {
  padding: 8px 18px; border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-raised); color: var(--madcop-ink-body);
  font-size: 13px; cursor: pointer;
}
.empty-session__btn--primary {
  background: var(--madcop-accent); color: var(--madcop-accent-ink);
  border-color: var(--madcop-accent);
}
.empty-session__btn:hover { background: var(--madcop-panel-sunken); }
.empty-session__btn--primary:hover { background: var(--madcop-accent-hover); }

.empty-session__hints {
  text-align: left; padding: 16px;
  border: 1.5px solid var(--madcop-line);
  background: var(--madcop-panel-raised);
  display: grid; gap: 8px;
}
.empty-session__hint {
  display: flex; align-items: center; gap: 10px;
  font-size: 12px; color: var(--madcop-ink-body);
}
.empty-session__hint-glyph {
  width: 18px; text-align: center; color: var(--madcop-accent);
  font-family: 'Geist Mono', monospace;
}
</style>
