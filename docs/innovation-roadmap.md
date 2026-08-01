# MadCop 6 大创新功能 — 实施计划书与跟踪

> 创建于 2026-08-01，对应 GitHub 调研 + 内部审计后的路线图。
> 本文档追踪 6 个 Sprint 的实施状态、文件、提交。

---

## Sprint 1：Skill 自动蒸馏增强（Auto-Skill）— ✅ 后端完成

**目标**：Agent 完成任务后自动判断是否值得蒸馏为 Skill，不需要用户说"教我"。

### 1.1 后端 — ✅
- `madcop/memory/skill_distill.py` — 新增 `auto_distill_if_valuable()`：判断 answer >= 400 字 + 含代码块/列表/章节标记 + 提取主题。
- `madcop/server/app.py` — 3 个 SSE 触发点扩展：先调用 `auto_distill_if_valuable`，失败 fallback 到 `distill_skill_from_exchange`（仅"教我"模式）。
- `desktop/src/vue/types/skill.ts` — `SkillSource` 添加 `'auto-distilled'` 类型。

**提交**：`135bc98 feat(Sprint 1): auto-distill valuable exchanges (backend)`

### 1.2 前端 — 待办
- `desktop/src/vue/components/chat/SkillToast.vue` — 浮动通知条（已有 `Toast.vue` 模式可复用）。
- `desktop/src/vue/stores/chatStore.ts` — `skill_distilled` SSE 事件已存在，确认 toast 已弹。
- `desktop/src/vue/pages/SkillList.vue` — 区分 `source='user'` vs `source='auto-distilled'` 标签。
- 测试：单元测试 `auto_distill_if_valuable` 各种边界。

---

## Sprint 2：主动记忆召回（Proactive Recall）

**目标**：用户输入消息时，Agent 自动从 5 层记忆库中提取相关上下文注入 system prompt。

### 已有基础
- `madcop/memory/retriever.py:46` — `Retriever` 类（已实现 3 层 + 时间衰减 + 权重）
- `madcop/memory/hybrid.py:161` — `hybrid_search()` FTS5+TF-IDF（**当前未接入**）
- `madcop/server/app.py:458` — `_build_memory_system_system_prompt` 已注入记忆

### 2.1 后端 — 待办
- `madcop/memory/retriever.py` — 扩展 `retrieve()` 覆盖 5 层（+persona/insight/scenario）
- 用 `hybrid_search()` 替代纯 FTS5 排序
- SSE emit `memory_recall` 事件

### 2.2 前端 — 待办
- `desktop/src/vue/components/chat/MemoryRecallBadge.vue` — "📌 基于 3 条记忆回答"
- `desktop/src/vue/stores/chatStore.ts` — 处理新事件
- 修复 `MemoryPage.vue` DELETE/POST 真实 CRUD

---

## Sprint 3：语音交互（Voice Mode）

**目标**：用户按住空格键说话 → Agent 听到 → 回答 → 朗读出来。

### 方案 A（快，1 天）：浏览器原生
- STT: `webkitSpeechRecognition`（Electron Chromium）
- TTS: `speechSynthesis`

### 3.1 前端 — 待办
- `desktop/src/vue/composables/useVoiceMode.ts` — `isListening` + `start()/stop()` + `speak(text)`
- `desktop/src/vue/components/chat/VoiceButton.vue` — 麦克风按钮 + 录音波形
- `ChatInput.vue` — 加语音按钮 + 按住空格触发
- `AssistantMessage.vue` — 加"🔊 朗读"按钮

### 3.2 Electron — 待办
- `desktop/build/entitlements.mac.plist` — 加 `com.apple.security.device.audio-input`
- `desktop/electron/main.ts` — 麦克风权限请求

---

## Sprint 4：多模态创作工作流（Source-First Creation）

**目标**：借鉴 YouMind——"先收集材料→再创作"。自动搜索→抓取→提取→写作 pipeline。

### 4.1 后端 — 待办
- 新建 `madcop/agent/creation.py`：`CreationEngine` 编排 search→fetch→extract→outline→write
- 新建 `madcop/agent/creation_prompts.py`：创作 prompt 模板
- `chat_v4.py` — 新增 `agent_mode: "create"` 路由

### 4.2 前端 — 待办
- `desktop/src/vue/components/chat/CreationProgress.vue` — pipeline 进度 + 来源列表
- `chatStore.ts` — 处理 `creation_progress` + `creation_source` SSE 事件

---

## Sprint 5：后台主动助手（Proactive Watcher）

**目标**：Agent 不等你问——文件变化/终端报错时主动推送建议。

### 5.1 Electron — 待办
- 新建 `desktop/electron/services/file_watcher.ts` — `fs.watch` 监控 workspace
- 改 `desktop/electron/services/terminal.ts` — 加 ring buffer + `terminal:read-output` IPC

### 5.2 后端 — 待办
- 新建 `madcop/server/routes/proactive.py`：`POST /api/proactive/check` 接收文件内容/终端输出 → agent 分析

### 5.3 前端 — 待办
- `desktop/src/vue/components/chat/ProactiveToast.vue` — 浮动通知
- `settingsStore.ts` — proactive watcher 开关

---

## Sprint 6：知识画布（Knowledge Canvas）

**目标**：可视化可编辑的 agent 知识图谱。

### 6.1 后端 — 待办
- 新建 `madcop/server/routes/brain_graph.py`：
  - `GET /api/brain/graph` → `{nodes, edges}`
  - `POST /api/brain/link` → 添加边
  - `DELETE /api/brain/node/{id}` → 删除

### 6.2 前端 — 待办
- 安装 `cytoscape` + `cytoscape-fcose`（力导向布局）
- 新建 `KnowledgeCanvas.vue` — 全屏 graph 页面
- 新建 `NodeDetail.vue` + `NodeEditor.vue`

---

## 文件清单总结

| 文件 | 操作 | Sprint |
|---|---|---|
| `madcop/memory/skill_distill.py` | 改 | 1 ✅ |
| `madcop/server/app.py` | 改 | 1 ✅ |
| `desktop/src/vue/types/skill.ts` | 改 | 1 ✅ |
| `desktop/src/vue/components/chat/SkillToast.vue` | 新建 | 1 |
| `desktop/src/vue/stores/chatStore.ts` | 改 | 1 |
| `desktop/src/vue/pages/SkillList.vue` | 改 | 1 |
| `madcop/memory/retriever.py` | 改 | 2 |
| `madcop/memory/hybrid.py` | 改 | 2 |
| `madcop/server/app.py` (memory_recall SSE) | 改 | 2 |
| `desktop/src/vue/components/chat/MemoryRecallBadge.vue` | 新建 | 2 |
| `desktop/src/vue/pages/MemoryPage.vue` | 改 | 2 |
| `desktop/src/vue/composables/useVoiceMode.ts` | 新建 | 3 |
| `desktop/src/vue/components/chat/VoiceButton.vue` | 新建 | 3 |
| `desktop/src/vue/components/chat/ChatInput.vue` | 改 | 3 |
| `desktop/src/vue/components/chat/AssistantMessage.vue` | 改 | 3 |
| `desktop/build/entitlements.mac.plist` | 改 | 3 |
| `desktop/electron/main.ts` | 改 | 3 |
| `madcop/agent/creation.py` | 新建 | 4 |
| `madcop/agent/creation_prompts.py` | 新建 | 4 |
| `madcop/server/routes/chat_v4.py` | 改 | 4 |
| `desktop/src/vue/components/chat/CreationProgress.vue` | 新建 | 4 |
| `desktop/electron/services/file_watcher.ts` | 新建 | 5 |
| `desktop/electron/services/terminal.ts` | 改 | 5 |
| `desktop/electron/services/proactive_monitor.ts` | 新建 | 5 |
| `madcop/server/routes/proactive.py` | 新建 | 5 |
| `desktop/src/vue/components/chat/ProactiveToast.vue` | 新建 | 5 |
| `madcop/server/routes/brain_graph.py` | 新建 | 6 |
| `desktop/src/vue/pages/KnowledgeCanvas.vue` | 新建 | 6 |
| `desktop/src/vue/components/knowledge/NodeDetail.vue` | 新建 | 6 |
| `desktop/src/vue/components/knowledge/NodeEditor.vue` | 新建 | 6 |

---

## 进度跟踪

| Sprint | 状态 | 提交 | 后续 |
|---|---|---|---|
| 1 Auto-Skill | 后端 ✅，前端待办 | 135bc98 | SkillToast + chatStore 验证 + 测试 |
| 2 Proactive Recall | 待办 | — | retriever 扩展 + hybrid_search 接入 |
| 3 Voice Mode | 待办 | — | useVoiceMode + VoiceButton + ChatInput |
| 4 Source-First Creation | 待办 | — | CreationEngine pipeline |
| 5 Proactive Watcher | 待办 | — | file_watcher + terminal buffer |
| 6 Knowledge Canvas | 待办 | — | cytoscape + brain_graph API |

**Sprint 1 已完成 50%（后端 ✅，前端待办）。**
**Sprint 2-6 完全待办。**
