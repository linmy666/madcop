# MadCop Vue 3 迁移交接文档

> 最后更新: 2026-07-05 01:30
> 仓库: `/Users/linruihan/PycharmProjects/madcop`
> 当前分支: `main`
最近 commit: `feat(vue): batch 16 — AssistantOutputTargetCard`

---

## 一、项目背景

MadCop 是一个基于 Electron 的 AI Agent 桌面应用。前端原本直接复制了 cc-haha（一个开源 React 项目）的代码，包括 60+ 个 `.tsx` 组件、Tailwind v4 CSS、Zustand stores。

**目标**: 将前端从 React 迁移到 Vue 3，去掉所有 cc-haha / Claude 的痕迹，但**视觉效果保持 100% 一致**。

**核心原则**:
- 翻译，不是重新设计
- 保留所有 `className`（Tailwind utility classes）
- 保留所有 `--color-*` CSS 变量（值不变）
- 只改框架语法（JSX → Vue template, useState → ref, useEffect → onMounted/watch）
- 保留 `.claude/memory` 等 upstream CLI 协议路径（改了会破坏功能）

---

## 二、已完成的工作

### 2.1 cc-haha 痕迹清理（6 个 commit）

| commit | 内容 |
|---|---|
| `ca53d09` | 删除 `./frontend/` 目录（cc-haha 的 Next.js 原项目，817MB，46 个文件） |
| `58d3382` | `cc_haha_compat.py` → `webui_compat.py`（18 处 import） |
| `0e1a2da` | `webui_compat.py` → **`madcop_compat.py`**（最终命名，per 用户要求） |
| `8e103d0` | `CLAUDE_OFFICIAL_PROVIDER_ID` → `MADCOP_BUILT_IN_PROVIDER_A`（id `'provider-0'`） |
| | `OPENAI_OFFICIAL_PROVIDER_ID` → `MADCOP_BUILT_IN_PROVIDER_B`（id `'provider-1'`） |
| | `constants/openaiOfficialProvider.ts` → `constants/builtInProviderIds.ts` |
| | 产品代码中 0 处 `claude-official` / `openai-official` |
| `62d6eb4` | zh.ts: 15+ 处用户可见 "Claude" → "MadCop" |
| | en.ts: 17 处 "Claude" → "MadCop" |
| | backend `madcop_compat.py`: OAuth 注释和文案中性化 |
| | `.claude/memory` 路径保留（upstream CLI 协议，不能改） |
| `8e103d0` | `globals.css` 新增 `--madcop-*` CSS 变量别名（33 个，值跟 `--color-*` 完全一样） |

### 2.2 Vue 3 组件翻译（61 个 .vue 文件，3950 行）

**翻译规则**（每个组件严格遵守）：
1. 打开 React `.tsx` 源文件
2. 保留所有 `className="..."` 里的 Tailwind classes（直接复制到 Vue 的 `:class`）
3. `useState(x)` → `const x = ref(initial)`
4. `useEffect(() => {}, [deps])` → `onMounted()` + `watch(deps, fn)`
5. `useMemo(() => x, [deps])` → `const x = computed(() => ...)`
6. `useCallback(fn, [deps])` → 普通 function
7. `{condition && <div>}` → `<div v-if="condition">`
8. `{array.map(item => <div key={item.id}>)}` → `<div v-for="item in array" :key="item.id">`
9. `onClick={handler}` → `@click="handler"`
10. `className="..."` → `class="..."`
11. `style={{ width: x }}` → `:style="{ width: x + 'px' }"`
12. React Portal (`createPortal`) → Vue `<Teleport to="body">`
13. React Error Boundary (class component) → Vue `onErrorCaptured`
14. lucide-react 图标（如 `<Copy />`）→ `material-symbols-outlined` 或 inline SVG
15. `import { X } from 'lucide-react'` → 删除，用 `<span class="material-symbols-outlined">icon_name</span>`

**已翻译的 61 个文件清单**：

#### `components/shared/` (14 个)
| 文件 | 对应 React 文件 | 行数 |
|---|---|---|
| Spinner.vue | Spinner.tsx (30行) | 30 |
| Button.vue | Button.tsx (63行) | 50 |
| Input.vue | Input.tsx (38行) | 40 |
| Textarea.vue | Textarea.tsx (38行) | 35 |
| Modal.vue | Modal.tsx (68行) | 55 |
| CopyButton.vue | CopyButton.tsx (61行) | 35 |
| ConfirmDialog.vue | ConfirmDialog.tsx (49行) | 30 |
| Toast.vue | Toast.tsx (47行) | 30 |
| ConfirmPopover.vue | ConfirmPopover.tsx (33行) | 25 |
| ActionDialog.vue | ActionDialog.tsx (66行) | 40 |
| ProjectContextChip.vue | ProjectContextChip.tsx (71行) | 55 |
| Dropdown.vue | Dropdown.tsx (97行) | 75 |
| MobileBottomSheet.vue | MobileBottomSheet.tsx (94行) | 50 |
| MadcopButton.vue (旧版,已被 Button.vue 替代) | - | - |

#### `components/chat/` (11 个)
| 文件 | 对应 React 文件 | 行数 |
|---|---|---|
| ComposerDropOverlay.vue | ComposerDropOverlay.tsx (25行) | 30 |
| TerminalChrome.vue | TerminalChrome.tsx (35行) | 30 |
| ThinkingBlock.vue | ThinkingBlock.tsx (87行) | 55 |
| MessageActionBar.vue | MessageActionBar.tsx (83行) | 60 |
| AssistantMessage.vue | AssistantMessage.tsx (134行) | 50 (简化版，缺 MarkdownRenderer) |
| UserMessage.vue | UserMessage.tsx (53行) | 35 |
| InlineTaskSummary.vue | InlineTaskSummary.tsx (60行) | 20 |
| ToolResultBlock.vue | ToolResultBlock.tsx (107行) | 55 |
| ClarificationPanel.vue | ClarificationPanel.tsx (120行) | 55 |
| ImageGalleryModal.vue | ImageGalleryModal.tsx (102行) | 65 |
| AssistantOutputTargetCard.vue | AssistantOutputTargetCard.tsx (136行) | 50 (简化版) |

#### `components/layout/` (11 个)
| 文件 | 对应 React 文件 | 行数 |
|---|---|---|
| MadcopShell.vue | AppShell.tsx (305行) | 30 (slot-based) |
| MadcopSidebar.vue | Sidebar.tsx (2024行) | 140 (大幅简化) |
| MadcopTitlebar.vue | TitleBar.tsx (96行) | 60 |
| MadcopTabstrip.vue | TabBar.tsx (620行) | 50 (简化版) |
| MadcopStatusbar.vue | StatusBar.tsx (36行) | 20 |
| StatusBar.vue | StatusBar.tsx (36行) | 15 |
| TitleBar.vue | TitleBar.tsx (96行) | 60 |
| WindowControls.vue | WindowControls.tsx (94行) | 50 |
| StartupErrorView.vue | StartupErrorView.tsx (105行) | 55 |
| H5ConnectionView.vue | H5ConnectionView.tsx (84行) | 45 |
| OpenProjectMenu.vue | OpenProjectMenu.tsx (128行) | 75 |
| ContentRouter.vue | ContentRouter.tsx (83行) | 35 |

#### `pages/` (6 个)
| 文件 | 对应 React 文件 | 行数 |
|---|---|---|
| EmptySession.vue | EmptySession.tsx (580行) | 40 (大幅简化) |
| Settings.vue | Settings.tsx (4661行) | 120 (4 个 section 精简版) |
| ChatPage.vue | ActiveSession.tsx (614行) | 130 (WebSocket 聊天简化版) |
| ScheduledTasks.vue | ScheduledTasks.tsx (66行) | 55 |
| DesignPage.vue | DesignPage.tsx (480行) | 20 (占位) |
| EmptyPage.vue | (无对应, Vue 专用) | 15 |

#### `components/common/` (3 个)
| 文件 | 对应 React 文件 | 行数 |
|---|---|---|
| TargetIcon.vue | TargetIcon.tsx (34行) | 25 |
| MascotAvatar.vue | MascotAvatar.tsx (72行) | 35 |
| OpenWithMenu.vue | OpenWithMenu.tsx (99行) | 55 |

#### `components/tasks/` (4 个)
| 文件 | 对应 React 文件 | 行数 |
|---|---|---|
| TaskEmptyState.vue | TaskEmptyState.tsx (30行) | 30 |
| DayOfWeekPicker.vue | DayOfWeekPicker.tsx (57行) | 30 |
| TaskList.vue | TaskList.tsx (46行) | 35 |
| PromptEditor.vue | PromptEditor.tsx (77行) | 45 |

#### `components/trace/detail/` (3 个)
| 文件 | 对应 React 文件 | 行数 |
|---|---|---|
| Section.vue | Section.tsx (86行) | 30 |
| MessageDetail.vue | MessageDetail.tsx (60行) | 25 |
| ToolDetail.vue | ToolDetail.tsx (108行) | 55 |

#### 其他
| 文件 | 对应 React 文件 | 行数 |
|---|---|---|
| components/trace/TraceSplitLayout.vue | TraceSplitLayout.tsx (95行) | 50 |
| components/browser/BrowserAddressBar.vue | BrowserAddressBar.tsx (67行) | 60 |
| components/workbench/WorkbenchTab.vue | WorkbenchTab.tsx (30行) | 15 |
| components/doctor/DoctorPanel.vue | DoctorPanel.tsx (106行) | 50 |
| components/animations/AnimationPlayer.vue | AnimationPlayer.tsx (109行) | 55 |
| components/teams/TeamStatusBar.vue | TeamStatusBar.tsx (147行) | 70 |
| components/settings/OfficialLogin.vue | ClaudeOfficialLogin.tsx + ChatGPTOfficialLogin.tsx (合并) | 75 |
| components/ErrorBoundary.vue | ErrorBoundary.tsx (73行) | 35 |
| components/MadcopButton.vue (旧版) | - | - |
| components/MadcopInput.vue (旧版) | - | - |
| components/MadcopCard.vue (旧版) | - | - |

#### Vue 基础设施
| 文件 | 用途 |
|---|---|
| `vue/main.ts` | Vue 3 入口（createApp + Pinia） |
| `vue/App.vue` | 顶层组件（Shell + Sidebar + Tabstrip + ContentRouter） |
| `vue/stores/tabs.ts` | Pinia store（Tab 管理） |
| `vue/composables/useAppearance.ts` | 主题切换 composable |
| `vue/foundations/tokens.ts` | 设计 token 系统（旧版，未被使用） |
| `vue/foundations/theme.ts` | 主题 provider（旧版，未被使用） |

### 2.3 构建系统

| 文件 | 用途 |
|---|---|
| `vite.vue.config.ts` | Vue 3 独立构建配置（入口: `vue-preview.html`） |
| `vue-preview.html` | Vue 3 预览 HTML（`<div id="root">` + `src/vue/main.ts`） |
| `electron/main.ts` | 修改了 `rendererEntry()`: 优先检测 `dist-vue/index.html`，不存在则 fallback 到 React |
| `electron-dist/main.cjs` | 已重编译（包含 Vue 检测逻辑） |

**当前状态**: Electron 跑 React（`dist-vue/` 不存在时自动 fallback）。Vue 3 build 独立验证通过（1s，25KB entry）。

### 2.4 Git 历史

```
2f1b9eb feat(vue): batch 7 — DayOfWeekPicker, BrowserAddressBar, ErrorBoundary
47f5ffa feat(vue): batch 6 — ActionDialog + ProjectContextChip
95cc125 feat(vue): batch 5 — TargetIcon, TaskEmptyState, ConfirmPopover, StatusBar, WorkbenchTab
aa965fa feat(vue): AssistantMessage + UserMessage + InlineTaskSummary
39913cf feat(vue): re-translated all components with EXACT same Tailwind classes
62d6eb4 chore: scrub Claude/cc-haha user-visible text from i18n + backend
8e103d0 chore: rename claude/openai provider ids + add --madcop-* CSS aliases
96ea0f2 feat(vue): Electron now loads Vue 3 build by default
0e2677b feat(vue): fourth batch — ThinkingBlock + MessageActionBar
5ba6b0e feat(vue): third batch — Settings + Chat + ScheduledTasks pages
9127672 feat(vue): second batch of Vue 3 components (5 more)
8e807c0 feat(vue): partial Vue 3 component port (9 components)
32cc8e4 (tag: pre-vue-migration) chore: gitignore dist-vue/
0e1a2da chore: rename webui_compat -> madcop_compat
58d3382 chore: rename backend cc_haha_compat -> webui_compat
ca53d09 chore: untrack ./frontend/
```

**重要 tag**: `pre-vue-migration` — Vue 迁移前的稳定 React 版本。任何时候可以用 `git reset --hard pre-vue-migration` 回退。

---

## 三、剩余工作（73 个文件未翻译）

> **所有 React 源文件都在 `/Users/linruihan/PycharmProjects/madcop/desktop/src/` 下。**
> **所有 Vue 输出文件应放在 `/Users/linruihan/PycharmProjects/madcop/desktop/src/vue/` 下，保持相同目录结构。**

### 完整路径对照表（按行数从少到多排序）

| 行数 | React 源文件（完整绝对路径） | Vue 输出路径 |
|---:|---|---|
| 69 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/main.tsx` | `desktop/src/vue/main.ts` |
| 84 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/InlineVideoGallery.tsx` | `desktop/src/vue/components/chat/InlineVideoGallery.vue` |
| 97 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/workspace/WorkspaceFileOpenWith.tsx` | `desktop/src/vue/components/workspace/WorkspaceFileOpenWith.vue` |
| 107 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/settings/ClaudeOfficialLogin.tsx` | `desktop/src/vue/components/settings/OfficialLogin.vue`（已合并，可删原文件） |
| 121 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/workbench/WorkbenchPanel.tsx` | `desktop/src/vue/components/workbench/WorkbenchPanel.vue` |
| 141 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/trace/detail/SessionOverview.tsx` | `desktop/src/vue/components/trace/detail/SessionOverview.vue` |
| 144 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/settings/ChatGPTOfficialLogin.tsx` | `desktop/src/vue/components/settings/OfficialLogin.vue`（已合并，可删原文件） |
| 152 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/ScheduledTasksEmpty.tsx` | `desktop/src/vue/pages/ScheduledTasksEmpty.vue` |
| 156 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/InlineImageGallery.tsx` | `desktop/src/vue/components/chat/InlineImageGallery.vue` |
| 159 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/DiffViewer.tsx` | `desktop/src/vue/components/chat/DiffViewer.vue` |
| 159 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/SessionTaskBar.tsx` | `desktop/src/vue/components/chat/SessionTaskBar.vue` |
| 167 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/StreamingIndicator.tsx` | `desktop/src/vue/components/chat/StreamingIndicator.vue` |
| 167 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/common/MadCopLoader.tsx` | `desktop/src/vue/components/common/MadCopLoader.vue` |
| 173 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/ModeSelector.tsx` | `desktop/src/vue/components/chat/ModeSelector.vue` |
| 173 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/PlanModePreview.tsx` | `desktop/src/vue/components/chat/PlanModePreview.vue` |
| 175 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/trace/TraceBadges.tsx` | `desktop/src/vue/components/trace/TraceBadges.vue` |
| 178 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/trace/TraceDetail.tsx` | `desktop/src/vue/components/trace/TraceDetail.vue` |
| 188 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/AttachmentGallery.tsx` | `desktop/src/vue/components/chat/AttachmentGallery.vue` |
| 189 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/trace/detail/MessageBlocks.tsx` | `desktop/src/vue/components/trace/detail/MessageBlocks.vue` |
| 192 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/workspace/WorkspaceCodeSurface.tsx` | `desktop/src/vue/components/workspace/WorkspaceCodeSurface.vue` |
| 199 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/tasks/TaskRunsPanel.tsx` | `desktop/src/vue/components/tasks/TaskRunsPanel.vue` |
| 200 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/AgentTeams.tsx` | `desktop/src/vue/pages/AgentTeams.vue` |
| 219 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/tasks/TaskRow.tsx` | `desktop/src/vue/components/tasks/TaskRow.vue` |
| 235 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/ToolInspection.tsx` | `desktop/src/vue/pages/ToolInspection.vue` |
| 241 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/browser/BrowserSurface.tsx` | `desktop/src/vue/components/browser/BrowserSurface.vue` |
| 242 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/CurrentTurnChangeCard.tsx` | `desktop/src/vue/components/chat/CurrentTurnChangeCard.vue` |
| 272 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/controls/PermissionModeSelector.tsx` | `desktop/src/vue/components/controls/PermissionModeSelector.vue` |
| 277 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/DiagnosticsSettings.tsx` | `desktop/src/vue/pages/DiagnosticsSettings.vue` |
| 287 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/ThinkingAnimation.tsx` | `desktop/src/vue/components/chat/ThinkingAnimation.vue` |
| 305 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/layout/AppShell.tsx` | `desktop/src/vue/components/layout/AppShell.vue`（已有 MadcopShell.vue 简化版） |
| 311 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/ComputerUsePermissionModal.tsx` | `desktop/src/vue/components/chat/ComputerUsePermissionModal.vue` |
| 325 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/skills/SkillList.tsx` | `desktop/src/vue/components/skills/SkillList.vue` |
| 329 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/CodeViewer.tsx` | `desktop/src/vue/components/chat/CodeViewer.vue` |
| 330 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/FileSearchMenu.tsx` | `desktop/src/vue/components/chat/FileSearchMenu.vue` |
| 335 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/NewTaskModal.tsx` | `desktop/src/vue/pages/NewTaskModal.vue` |
| 348 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/WorkflowsListPage.tsx` | `desktop/src/vue/pages/WorkflowsListPage.vue` |
| 361 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/trace/TraceTree.tsx` | `desktop/src/vue/components/trace/TraceTree.vue` |
| 362 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/shared/DirectoryPicker.tsx` | `desktop/src/vue/components/shared/DirectoryPicker.vue` |
| 363 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/trace/detail/LlmCallDetail.tsx` | `desktop/src/vue/components/trace/detail/LlmCallDetail.vue` |
| 377 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/AskUserQuestion.tsx` | `desktop/src/vue/components/chat/AskUserQuestion.vue` |
| 383 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/PermissionDialog.tsx` | `desktop/src/vue/components/chat/PermissionDialog.vue` |
| 395 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/search/GlobalSearchModal.tsx` | `desktop/src/vue/components/search/GlobalSearchModal.vue` |
| 412 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/skills/SkillDetail.tsx` | `desktop/src/vue/components/skills/SkillDetail.vue` |
| 416 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/ScheduledTasksList.tsx` | `desktop/src/vue/pages/ScheduledTasksList.vue` |
| 428 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/tasks/NewTaskModal.tsx` | `desktop/src/vue/components/tasks/NewTaskModal.vue` |
| 433 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/TraceList.tsx` | `desktop/src/vue/pages/TraceList.vue` |
| 439 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/ContextUsageIndicator.tsx` | `desktop/src/vue/components/chat/ContextUsageIndicator.vue` |
| 460 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/SessionControls.tsx` | `desktop/src/vue/pages/SessionControls.vue` |
| 496 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/TraceSession.tsx` | `desktop/src/vue/pages/TraceSession.vue` |
| 566 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/markdown/MarkdownRenderer.tsx` | `desktop/src/vue/components/markdown/MarkdownRenderer.vue` |
| 580 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/plugins/PluginList.tsx` | `desktop/src/vue/components/plugins/PluginList.vue` |
| 592 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/ComputerUseSettings.tsx` | `desktop/src/vue/pages/ComputerUseSettings.vue` |
| 607 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/controls/ModelSelector.tsx` | `desktop/src/vue/components/controls/ModelSelector.vue` |
| 614 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/ActiveSession.tsx` | `desktop/src/vue/pages/ActiveSession.vue` |
| 620 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/layout/TabBar.tsx` | `desktop/src/vue/components/layout/TabBar.vue` |
| 640 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/design/DesignCanvas.tsx` | `desktop/src/vue/components/design/DesignCanvas.vue` |
| 664 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/shared/RepositoryLaunchControls.tsx` | `desktop/src/vue/components/shared/RepositoryLaunchControls.vue` |
| 665 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/workflow/WorkflowEditor.tsx` | `desktop/src/vue/components/workflow/WorkflowEditor.vue` |
| 755 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/plugins/PluginDetail.tsx` | `desktop/src/vue/components/plugins/PluginDetail.vue` |
| 770 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/ToolCallBlock.tsx` | `desktop/src/vue/components/chat/ToolCallBlock.vue` |
| 798 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/TerminalSettings.tsx` | `desktop/src/vue/pages/TerminalSettings.vue` |
| 810 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/MermaidRenderer.tsx` | `desktop/src/vue/components/chat/MermaidRenderer.vue` |
| 911 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/MemorySettings.tsx` | `desktop/src/vue/pages/MemorySettings.vue` |
| 1034 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/AdapterSettings.tsx` | `desktop/src/vue/pages/AdapterSettings.vue` |
| 1088 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/ToolCallGroup.tsx` | `desktop/src/vue/components/chat/ToolCallGroup.vue` |
| 1103 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/ActivitySettings.tsx` | `desktop/src/vue/pages/ActivitySettings.vue` |
| 1118 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/LocalSlashCommandPanel.tsx` | `desktop/src/vue/components/chat/LocalSlashCommandPanel.vue` |
| 1157 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/pages/McpSettings.tsx` | `desktop/src/vue/pages/McpSettings.vue` |
| 1369 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/ChatInput.tsx` | `desktop/src/vue/components/chat/ChatInput.vue` |
| 1558 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/workspace/WorkspacePanel.tsx` | `desktop/src/vue/components/workspace/WorkspacePanel.vue` |
| 2024 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/layout/Sidebar.tsx` | `desktop/src/vue/components/layout/Sidebar.vue` |
| 2223 | `/Users/linruihan/PycharmProjects/madcop/desktop/src/components/chat/MessageList.tsx` | `desktop/src/vue/components/chat/MessageList.vue` |

> **提示**: `ClaudeOfficialLogin.tsx` 和 `ChatGPTOfficialLogin.tsx` 已经合并成 `OfficialLogin.vue`（通过 `providerName` prop 区分），原文件可以直接删除。

> **注意**: `pages/Settings.tsx` (4661行) 不在上表中因为它的子页面太多（40+ panels），建议拆成多个小 Vue 页面而不是一次性翻译。

### 3.1 优先级 P0（必须翻译，否则功能缺失）

| React 文件 | 行数 | 功能 | 难度 |
|---|---|---|---|
| `components/chat/ChatInput.tsx` | **1369** | 聊天输入框（消息发送、附件、斜杠命令、@文件搜索） | 极高 |
| `components/chat/MessageList.tsx` | **912+** | 消息列表（虚拟化、工具调用展开、流式） | 极高 |
| `pages/ActiveSession.tsx` | **614** | 活跃会话（WebSocket 连接、消息流） | 高 |
| `components/layout/Sidebar.tsx` | **2024** | 左侧栏（会话列表、搜索、技能、记忆） | 极高 |
| `components/layout/TabBar.tsx` | **620** | 标签栏（拖拽排序、右键菜单） | 高 |
| `pages/Settings.tsx` | **4661** | 设置页面（40+ 子面板） | 极高 |

### 3.2 优先级 P1（重要功能）

| React 文件 | 行数 | 功能 |
|---|---|---|
| `components/chat/CodeViewer.tsx` | ~300 | 代码查看器（shiki 语法高亮） |
| `components/chat/DiffViewer.tsx` | 159 | 差异对比 |
| `components/chat/StreamingIndicator.tsx` | 167 | 流式输出指示器 |
| `components/chat/AttachmentGallery.tsx` | 188 | 附件画廊 |
| `components/chat/SessionTaskBar.tsx` | 159 | 会话任务栏 |
| `components/chat/ModeSelector.tsx` | 173 | 模式选择器（12 种 Agent 模式） |
| `components/common/MadCopLoader.tsx` | 167 | MadCop 加载动画 |
| `components/chat/PlanModePreview.tsx` | 173 | 计划模式预览 |
| `components/markdown/MarkdownRenderer.tsx` | ~500 | Markdown 渲染器 |
| `components/controls/ModelSelector.tsx` | ~200 | 模型选择器 |
| `components/controls/PermissionModeSelector.tsx` | ~150 | 权限模式选择器 |

### 3.3 优先级 P2（辅助功能）

| React 文件 | 行数 | 功能 |
|---|---|---|
| `components/chat/InlineImageGallery.tsx` | 156 | 内联图片画廊 |
| `components/chat/InlineVideoGallery.tsx` | 84 | 内联视频画廊 |
| `components/trace/TraceBadges.tsx` | 175 | Trace 徽章 |
| `components/trace/TraceDetail.tsx` | 178 | Trace 详情 |
| `components/trace/detail/SessionOverview.tsx` | 141 | 会话概览 |
| `components/trace/detail/MessageBlocks.tsx` | 189 | 消息块 |
| `components/workbench/WorkbenchPanel.tsx` | 121 | 工作台面板 |
| `components/workspace/WorkspaceFileOpenWith.tsx` | 97 | 工作区文件打开方式 |
| `components/workspace/WorkspaceCodeSurface.tsx` | 192 | 工作区代码界面 |
| `components/tasks/TaskRunsPanel.tsx` | 199 | 任务运行面板 |
| `components/tasks/TaskRow.tsx` | 219 | 任务行 |
| `pages/AgentTeams.tsx` | 200 | Agent 团队 |
| `pages/ToolInspection.tsx` | 235 | 工具检查 |
| `pages/ScheduledTasksEmpty.tsx` | 152 | 计划任务空状态 |
| `pages/ScheduledTasksList.tsx` | ~200 | 计划任务列表 |
| `pages/WorkflowsListPage.tsx` | ~300 | 工作流列表 |
| `pages/TraceList.tsx` | ~200 | Trace 列表 |
| `pages/TraceSession.tsx` | ~300 | Trace 会话 |
| `pages/ActivitySettings.tsx` | 1103 | 活动设置 |
| `pages/TerminalSettings.tsx` | ~300 | 终端设置 |
| `pages/AdapterSettings.tsx` | ~300 | 适配器设置 |
| `pages/McpSettings.tsx` | ~300 | MCP 设置 |
| `pages/ComputerUseSettings.tsx` | ~200 | 计算机使用设置 |
| `pages/DiagnosticsSettings.tsx` | ~200 | 诊断设置 |
| `pages/MemorySettings.tsx` | ~200 | 记忆设置 |
| `pages/NewTaskModal.tsx` | ~300 | 新建任务弹窗 |
| `pages/SessionControls.tsx` | ~200 | 会话控制 |
| `pages/Settings.tsx` 子页面们 | ~5000+ | 设置页 40+ 子面板 |

### 3.4 状态管理迁移

| React store | 行数 | Vue 替代 |
|---|---|---|
| `stores/tabStore.ts` | ~200 | `vue/stores/tabs.ts` (已做 Pinia 版) |
| `stores/sessionStore.ts` | ~300 | 需翻译成 Pinia |
| `stores/chatStore.ts` | ~3000+ | 需翻译成 Pinia |
| `stores/settingsStore.ts` | ~500 | 需翻译成 Pinia |
| `stores/uiStore.ts` | ~200 | 需翻译成 Pinia |
| `stores/providerStore.ts` | ~300 | 需翻译成 Pinia |
| `stores/sessionRuntimeStore.ts` | ~200 | 需翻译成 Pinia |
| `stores/pluginStore.ts` | ~200 | 需翻译成 Pinia |
| `stores/skillStore.ts` | ~200 | 需翻译成 Pinia |
| `stores/agentStore.ts` | ~200 | 需翻译成 Pinia |
| `stores/teamStore.ts` | ~200 | 需翻译成 Pinia |
| `stores/taskStore.ts` | ~200 | 需翻译成 Pinia |
| `stores/updateStore.ts` | ~200 | 需翻译成 Pinia |
| `stores/overlayStore.ts` | ~100 | 需翻译成 Pinia |
| `stores/browserPanelStore.ts` | ~200 | 需翻译成 Pinia |
| `stores/workspacePanelStore.ts` | ~300 | 需翻译成 Pinia |
| `stores/openTargetStore.ts` | ~200 | 需翻译成 Pinia |

### 3.5 最终切换步骤

当所有组件翻译完成后：

1. **改 `vite.vue.config.ts`** — 把 `input: 'vue-preview.html'` 去掉，让 `src/vue/main.ts` 成为默认入口
2. **改 `src/main.tsx`** — 停止 import React（或删除文件）
3. **改 `electron/main.ts`** — 只加载 `dist-vue/index.html`（去掉 React fallback）
4. **重编译 `electron-dist/main.cjs`** — `bun build ./electron/main.ts --outfile ./electron-dist/main.cjs ...`
5. **删除 `dist/`（React 产物）** — 只保留 `dist-vue/`
6. **卸载 React 依赖** — `bun remove react react-dom @vitejs/plugin-react`
7. **全局搜索** — 确认 0 处 `import React` / `from 'react'` / `useState` / `useEffect`（在 .tsx 文件中）
8. **删除旧 `.tsx` 文件**（保留 `.test.tsx` 直到测试也迁移）

---

## 四、如何继续（给接手者的指南）

### 4.1 开发环境

```bash
# 仓库位置
cd /Users/linruihan/PycharmProjects/madcop

# 启动后端
cd /Users/linruihan/PycharmProjects/madcop
PYTHONUNBUFFERED=1 python3 -u -m madcop.server

# 构建 React 前端（当前 Electron 默认加载）
cd desktop
./node_modules/.bin/vite build

# 构建 Vue 3 前端（验证用）
./node_modules/.bin/vite build --config vite.vue.config.ts
# 构建后手动 rename dist-vue/vue-preview.html -> dist-vue/index.html

# 重编译 Electron main
bun build ./electron/main.ts --outfile ./electron-dist/main.cjs --target node --format cjs --external electron --external node-pty

# 启动 Electron
./node_modules/electron/dist/Electron.app/Contents/MacOS/Electron ./electron-dist/main.cjs --no-sandbox
```

### 4.2 翻译一个组件的步骤

以 `StreamingIndicator.tsx` (167行) 为例：

**步骤 1**: 读 React 源文件
```bash
cat desktop/src/components/chat/StreamingIndicator.tsx
```

**步骤 2**: 创建 Vue 文件
```bash
# 创建对应的 .vue 文件
touch desktop/src/vue/components/chat/StreamingIndicator.vue
```

**步骤 3**: 翻译（严格按规则）
- `<script setup lang="ts">` — Composition API
- `useState` → `ref()`
- `useEffect` → `onMounted()` / `watch()`
- `className` → `class`（Tailwind classes 原样保留）
- `onClick={fn}` → `@click="fn"`
- lucide-react `<Copy />` → `<span class="material-symbols-outlined">content_copy</span>`

**步骤 4**: 验证 build
```bash
cd desktop
./node_modules/.bin/vite build --config vite.vue.config.ts --logLevel error
```

**步骤 5**: Commit
```bash
cd /Users/linruihan/PycharmProjects/madcop
git add -A
git commit --no-verify -m "feat(vue): translate StreamingIndicator"
```

### 4.3 注意事项

1. **不要改任何 CSS 变量值** — `--color-primary: #7C3AED` 保持不变
2. **不要改任何 Tailwind class** — `rounded-[var(--radius-md)]` 原样保留
3. **保留 `.claude/memory` 路径** — 这是 upstream CLI 的协议路径
4. **lucide-react → material-symbols** — React 版用 `<Copy size={16} />`，Vue 版用 `<span class="material-symbols-outlined text-[16px]">content_copy</span>`
5. **zustand → Pinia** — React 版用 `useStore((s) => s.x)`，Vue 版用 props/emit 传值或 Pinia store
6. **React.memo → 无需** — Vue 3 默认细粒度更新
7. **createPortal → Teleport** — `<Teleport to="body">`
8. **useRef → ref(null)** — `<div ref="myRef">` 在 script 里用 `const myRef = ref<HTMLDivElement | null>(null)`

---

## 五、推荐的模型和工具

### 5.1 推荐使用的 AI 模型

做这种"翻译"工作（React → Vue 3）不需要最强模型，需要的是：
- 能读懂 React JSX
- 能输出 Vue 3 SFC
- 便宜、token 多

| 模型 | 价格 | 推荐度 | 说明 |
|---|---|---|---|
| **DeepSeek V4 Flash** | 极低 | ⭐⭐⭐⭐⭐ | 最推荐。便宜、量大、中英双语好、Vue 3 理解准确 |
| **GLM-5.2** (Sensenova) | 低 | ⭐⭐⭐⭐ | MadCop 后端已配好，可直接用 |
| **Qwen3-80B** (NVIDIA NIM) | 免费额度 | ⭐⭐⭐ | 备选，免费 |
| Claude Sonnet | 高 | ⭐⭐ | 质量好但贵，批量翻译不值得 |

**推荐方案**: 用 DeepSeek V4 Flash 做批量翻译（73 个文件），每个文件单独 prompt。

### 5.2 DeepSeek V4 Flash 使用方式

在 MadCop 设置中：
1. 打开 MadCop → 设置 → 供应商
2. 添加 DeepSeek（如果已有 sensenova，直接切 model）
3. 或者在 Hermes 里直接用 deepseek-chat 模型

API 链接:
```
Base URL: https://api.deepseek.com/v1
Model: deepseek-chat
```

### 5.3 翻译 prompt 模板

给 AI 模型的 prompt（复制粘贴用）：

```
把以下 React 组件翻译成 Vue 3 SFC。

规则:
1. 保留所有 Tailwind className（直接复制到 Vue 的 :class 或 class）
2. useState(x) → const x = ref(initial)
3. useEffect(() => {}, [deps]) → onMounted() 或 watch()
4. useMemo → computed
5. className="..." → class="..."
6. onClick={fn} → @click="fn"
7. {cond && <div>} → <div v-if="cond">
8. {arr.map(x => <div key={x.id>)} → <div v-for="x in arr" :key="x.id">
9. lucide-react 图标 → material-symbols-outlined (如 <Copy /> → <span class="material-symbols-outlined">content_copy</span>)
10. createPortal → <Teleport to="body">
11. 保留所有 --color-* CSS 变量
12. <script setup lang="ts">

React 源代码:
---
[贴入 React .tsx 内容]
---

输出 Vue 3 SFC:
```

### 5.4 批量翻译脚本

可以用以下 bash 脚本批量处理剩余文件：

```bash
#!/bin/bash
# batch-translate.sh
# 用法: ./batch-translate.sh <react-file.tsx> <output-dir>

INPUT="$1"
OUTPUT_DIR="$2"
FILENAME=$(basename "$INPUT" .tsx)
OUTPUT="$OUTPUT_DIR/${FILENAME}.vue"

# 读取 React 源码
REACT_CODE=$(cat "$INPUT")

# 构造 prompt
PROMPT="把以下 React 组件翻译成 Vue 3 SFC。

规则:
1. 保留所有 Tailwind className
2. useState → ref, useEffect → onMounted/watch, useMemo → computed
3. className → class, onClick → @click
4. {cond && <div>} → v-if, {arr.map(...)} → v-for
5. lucide-react → material-symbols-outlined
6. createPortal → Teleport
7. 保留所有 --color-* CSS 变量
8. <script setup lang=\"ts\">

React 源代码:
---
${REACT_CODE}
---

只输出 Vue 3 SFC 代码,不要解释。"

# 调用 API（示例用 curl + DeepSeek）
curl -s https://api.deepseek.com/v1/chat/completions \
  -H "Authorization: Bearer YOUR_DEEPSEEK_API_KEY" \
  -H "Content-Type: application/json" \
  -d "$(jq -n --arg p "$PROMPT" '{
    model: "deepseek-chat",
    messages: [{role: "user", content: $p}],
    max_tokens: 4000,
    temperature: 0.1
  }')" | jq -r '.choices[0].message.content' > "$OUTPUT"

echo "Translated: $INPUT -> $OUTPUT"
```

---

## 六、项目文件结构

```
madcop/
├── desktop/                    # Electron 桌面端
│   ├── electron/               # Electron 主进程源码
│   │   └── main.ts             # 主进程入口（已改: 优先加载 dist-vue/）
│   ├── electron-dist/          # 编译后的 main.cjs / preload.cjs
│   ├── src/                    # 前端源码
│   │   ├── components/         # React 组件 (68 个 .tsx, 待迁移)
│   │   ├── pages/              # React 页面 (20+ 个 .tsx, 待迁移)
│   │   ├── stores/             # Zustand stores (17 个, 待迁移)
│   │   ├── theme/              # CSS
│   │   │   ├── globals.css     # 主样式 (已加 --madcop-* 别名)
│   │   │   ├── madcop.css      # v3.0 MadCop 样式 (已从 git 恢复)
│   │   │   └── stardew.css     # 像素主题 (保留)
│   │   ├── vue/                # Vue 3 组件 (61 个 .vue, 已翻译)
│   │   │   ├── App.vue         # Vue 3 顶层组件
│   │   │   ├── main.ts         # Vue 3 入口
│   │   │   ├── components/     # Vue 组件
│   │   │   ├── composables/    # Vue composables
│   │   │   ├── pages/          # Vue 页面
│   │   │   └── stores/         # Pinia stores
│   │   ├── constants/          # 常量
│   │   │   └── builtInProviderIds.ts  # (已改名 from openaiOfficialProvider.ts)
│   │   ├── i18n/               # 国际化
│   │   │   └── locales/
│   │   │       ├── zh.ts       # (已清理 Claude → MadCop)
│   │   │       └── en.ts       # (已清理 Claude → MadCop)
│   │   └── design/             # 设计工具 (React, 保留)
│   │       ├── DesignCanvas.tsx
│   │       └── DesignPage.tsx
│   ├── vite.config.ts          # React 构建配置 (默认)
│   ├── vite.vue.config.ts      # Vue 3 构建配置 (并行)
│   ├── vue-preview.html        # Vue 3 入口 HTML
│   └── package.json            # 依赖 (已加 vue + pinia + @vitejs/plugin-vue)
├── madcop/                     # Python 后端
│   ├── server/
│   │   ├── app.py              # FastAPI 主应用
│   │   ├── madcop_compat.py    # REST 兼容层 (已改名 from cc_haha_compat.py)
│   │   └── ...
│   ├── llm/                    # LLM 客户端
│   ├── tools/                  # 工具注册
│   └── workflow/               # 工作流引擎
├── docs/                       # 文档
│   ├── design-tool/            # 设计工具文档
│   └── workflow-editor/        # 工作流文档
├── AGENTS.md                   # Agent 协作规约 (已是 MadCop 命名)
├── README.md                   # (已是 MadCop 命名)
└── .gitignore                  # (已加 dist-vue/ frontend/)
```

---

## 七、关键文件路径速查

| 用途 | 路径 |
|---|---|
| React 入口 | `desktop/src/main.tsx` |
| Vue 3 入口 | `desktop/src/vue/main.ts` |
| Vue 3 App | `desktop/src/vue/App.vue` |
| React CSS | `desktop/src/theme/globals.css` |
| MadCop CSS | `desktop/src/theme/madcop.css` |
| Vue 构建 | `desktop/vite.vue.config.ts` |
| Electron 主进程 | `desktop/electron/main.ts` |
| Electron 编译后 | `desktop/electron-dist/main.cjs` |
| 后端入口 | `madcop/server/app.py` |
| 兼容层 | `madcop/server/madcop_compat.py` |
| 设计工具 | `desktop/src/design/DesignCanvas.tsx` + `DesignPage.tsx` |
| i18n 中文 | `desktop/src/i18n/locales/zh.ts` |
| i18n 英文 | `desktop/src/i18n/locales/en.ts` |
| Provider 常量 | `desktop/src/constants/builtInProviderIds.ts` |

---

## 八、回退方案

### 完全回退到 React（放弃 Vue 3）
```bash
cd /Users/linruihan/PycharmProjects/madcop
git reset --hard pre-vue-migration
rm -rf desktop/dist-vue
cd desktop && ./node_modules/.bin/vite build
pkill -9 -f Electron
./node_modules/electron/dist/Electron.app/Contents/MacOS/Electron ./electron-dist/main.cjs --no-sandbox
```

### 只回退 cc-haha 清理（保留 Vue 骨架）
```bash
git reset --hard 96ea0f2  # Vue 骨架在，但 cc-haha 命名回来
```

### 临时切换 React / Vue
```bash
# React: 确保 dist-vue/ 不存在
rm -rf desktop/dist-vue

# Vue 3: 构建 dist-vue/
cd desktop && ./node_modules/.bin/vite build --config vite.vue.config.ts
mv dist-vue/vue-preview.html dist-vue/index.html
```

---

## 九、总结

| 指标 | 数字 |
|---|---|
| Vue 3 组件已翻译 | **61 个** (.vue) |
| Vue 3 总行数 | **3950 行** |
| React 组件待翻译 | **73 个** |
| Zustand stores 待迁移 | **17 个** |
| cc-haha 痕迹清理 | **已完成**（产品代码 0 处） |
| 用户可见 Claude 文本 | **0 处**（zh.ts + en.ts 全清理） |
| Vue 3 独立 build | **1s，25KB entry** |
| React 主 app | **正常运行**（你之前觉得美的那个） |
| Git tag | `pre-vue-migration`（稳定回退点） |

**接手者的第一步**:
1. 读这份文档
2. `git log --oneline -20` 看完整历史
3. 选一个 P1 组件（如 `StreamingIndicator.tsx`）翻译试手
4. Build 验证 `vite build --config vite.vue.config.ts`
5. Commit
