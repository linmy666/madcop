# MadCop 夜间任务晨报（2026-09-07）

> 执行文档：`OVERNIGHT_TASK_2026-09-07.md`。全程未 push、未触碰 `~/.madcop/`、未改依赖与 electron 打包配置。每个 commit 前均通过 `vite build`；后端改动通过 `py_compile` + 模块导入双重验证。工作树干净。

## 提交清单

| Commit | 任务 | 一句话 |
|---|---|---|
| `196ea39` | A | 死功能修复：desktopHost stub 遮蔽真实桥接（10 个文件受累）、30 个 i18n 缺 key、MCP api stub、缩放滑条从未生效、补实现 `/api/training/status` 路由 |
| `b3bb60d` | B | 32 处裸 `fetch('/api/…')` 统一 `getApiUrl()`；删除死代码（desktopHost 副本目录 + 4 个不可达页面） |
| `fd51a0f` | C | 14 处标题级 rem 陷阱转显式 px；3 处白字压 brand 违规改 on-primary；1 处浅色主题下白图标不可见修复 |
| `d86e4b9` | D | 图标 78 处归档 {14,16,18,20,24}；圆角 13 处归档；最后一个半像素字号清零；7 处 #b45309 警告色字面量改 token |

## 任务 A：死功能扫描（发现 21 → 修复 12 → 记录 9）

三个只读扫描 + 脚本核查覆盖全部 5 个子项。**文档点名的 `ExecPolicySettings` / `MetaHarnessSettings` / `H5AccessSettings` 三个页面逐按钮核对后端路由，全部正常，无死控件。**

### 已修复（root cause 高度集中）

1. **desktopHost stub 遮蔽真实桥接（影响面最大的一个根因）**。`desktop/src/vue/lib/desktopHost.ts` 是只暴露 `isDesktop` 的 stub，而 10 个文件经它取 host，所有 `host.capabilities/.notifications/.zoom/.proactive/.shell/.runtime` 访问要么静默失效要么运行时 TypeError。已改为 re-export 真实桥接（`src/lib/desktopHost/`，electron preload 注入 `window.desktopHost`）；4 个直接误导入 stub 的页面改为直连真实模块。连带修活：About 页 5 个外链按钮 + 版本号、观察器「重新挂载」按钮、Trace 窗口按钮、桌面通知、preview bridge、动态端口解析（`initializeDesktopServerUrl` 此前一直走 fallback）。
2. **界面缩放滑条（50%–150%）是纯摆设**。`uiZoom` 存进后端设置后无人消费；`applyAppZoomLevel`、Electron `zoomSet` IPC、CSS 回退全都存在，只差一行调用。已接线：滑条实时生效 + AppShell 启动恢复（随 stub 修复，native zoomFactor 路径同时修活了 `trySetNativeAppZoom` 的必崩 bug）。
3. **`GET /api/training/status` 只存在于 docstring**。前端触发微调后轮询它 30 分钟必 404 → 必显「轮询超时」。后端补实现（trigger 是同步 stub，status 立即返回 completed）；轮询改为先查后等，不再有 30 秒假 running。**运行中的 server 需重启生效（未 kill，遵守红线）。**
4. **i18n 缺 key 30 个**（含 `settings.skills.distill*` 7 个、`settings.mcp.import*` 5 个、`trace.kind.*` 7 个）。注意其中多数写法是 `t(k) || '兜底'`——该兜底永不生效（t 缺 key 时返回 key 本身，truthy），所以是真实泄漏。zh/en 双侧补齐后 1:1 对齐（各 2042 key）。
5. **McpSettings 用内联 stub 遮蔽了 props**（`sessionsApi`/`mcpApi` 恒返回空数组，导入对话框的项目路径建议恒空），改用真实 `api/sessions` + `api/mcp`。
6. **`setUpdateProxy` 不持久化**（`updateProxy` 不在 `PERSIST_KEYS`，重启即丢），补齐往返闭环。

### 记录待人工决策（按严重度）

| # | 项 | 为什么没修 |
|---|---|---|
| 1 | **Windows 标题栏最小化/关闭按钮是空函数 `{}`**（`WindowControls.vue:13-15`，maximize 也只翻本地 ref） | host 只有 `windowControls` 能力标志位，无实际 API；修复需在 electron main/preload 加 IPC 通道，超出夜间安全范围（Windows-only 界面，本机 darwin 不可验证） |
| 2 | **会话菜单「归档」按钮只弹「即将推出」**（`ActiveSession.vue:332`，TODO 注明要接 `/api/sessions/{id}/archive`） | 需要后端路由 + 归档后的产品形态（侧栏怎么呈现），纯产品决策 |
| 3 | **「本轮改动」卡片整体死功能**（`MessageList.vue` 的 `turnChangeCards` 声明后从不填充；`CurrentTurnChangeCard.vue` 的撤销回调从未传入、`openChangedFile` 自注释 no-op） | React 半迁移产物；接活需要 turn-diff 数据管道（后端事件→store），工作量超出夜间范围。i18n key（`chat.turnDiff*`）已顺手补齐，接活时即用 |
| 4 | **Settings.vue 两个不可达面板**（`activeTab==='learning'` 与 `'workflow'` 分支，navItems 不含这两项；后者连 v-model 都没有） | 是删是接回导航属于产品决策；ContinuousLearning 的活入口在「观察器」tab（`__observer__`），不缺功能 |
| 5 | **后端孤立工具**：`tools/cron.py`（被 `server/task_scheduler.py` 取代）、`DockerSandbox`、`ComputerUseTool`（computer_use）、`rag_tools.py`（query_rag/remember/route，`RagToolContext` 生产代码从不构造）、quant 系（`quant_factors/quant_backtest_simple` 不在 v4 registry，主聊天链路模型永远看不到；仅剩无人调用的 `/api/agent/run` 理论出口） | 均有 test 消费者（非"全仓库无引用"），且删除涉及是否保留 GUSHEN/工作流出口的策略问题。建议人工裁决后一次性清 |
| 6 | 上述连带：`app.py` 的 `_mcp_global_registry` 只写不读（注释确认已改走 `_mcp_manager`）；`AgentOverview.vue` gushen 模板的 `tools` 数组引擎不读（死配置）；i18n `settings.computerUse.disabledHint` 描述的「MCP 注入新会话」后端不存在 | 动 `app.py` 风险高 / 属产品语义，仅记录 |
| 7 | `WorkbenchPanel.vue` 的 `ensureBlankBrowser` 是注释级 no-op（浏览器模式切视图仍生效，降级为部分死） | browserPanelStore 未迁移 Vue，属迁移路线图问题 |
| 8 | `TabStrip.vue` 完整实现被 `showTabStrip = computed(() => false)` 永久关闭 | 注释明确是有意决策（侧栏唯一导航面），保持现状 |
| 9 | **MarketQuote/Paper/weather 的怀疑已排除**——v4 registry 同样注册（`tool_executor.py:506-510,486`），聊天可达 | 无需动作，写进晨报防止下次重查 |

## 任务 B：架构优化（发现→处置）

- **B1 raw fetch 统一**：38 处 → **全部 38 处改为 `getApiUrl()`**（含 1 处含三元表达式的模板串手工处理），13 个文件，逐一补 import；`Sidebar.vue` 函数体内的动态 `import('../../api/client')` 顺手改静态。**AppShell 启动三路径（health/workspace-dir/zoom bootstrap）逐行核对 diff**，语义不变（原本靠 fetch shim 兜底，现在直连）。H5 远程模式从此不依赖 shim。
- **B2 重复代码**：滑窗检测器扫全库。唯一 ≥3 次的 20 行级重复是 **`components/markdown/MarkdownRenderer.vue`（783 行）与 `components/shared/MarkdownRenderer.vue`（662 行）**——两份都在用（各 4 个引用者）且已漂移 171 行 diff，合并属跨文件重构，**记录不合并**。clipboard 拷贝逻辑 ×4（约 12 行）低于 20 行门槛，未动。
- **B3 死代码**：删除（均 grep 三遍 + 确认无 glob/auto-import 插件）：
  - `desktop/src/vue/lib/desktopHost/` 整目录（4 文件）——真实模块的过期字节副本，解析顺序上被 stub 文件遮蔽，零引用；
  - 4 个不可达页面：`ChatPage.vue`(35 行)、`EmptyPage.vue`(16)、`ToolInspection.vue`(156)、`MemorySettings.vue`(1148，活孪生是 `MemoryPage.vue` 的 memory tab)。
- **未删但建议人工复核**：孤儿检测器报 71 个候选，剔除测试引用噪音后仍有约 50+ 个零引用文件（`pages/`、`components/`、`vue/lib/` 各若干，如 `chat/ImageGalleryModal.vue`、`layout/TitleBar.vue`、`tasks/TaskList.vue` 等——注意 `TaskList.vue` 疑似被 `ScheduledTasksList.vue` 取代）。批量删除超出"早晨 5 分钟看完 diff"标准，留人工。zh-TW/jp/kr 三个 locale（6378 行）未被接线（应用仅 zh/en），属休眠数据未删。

## 任务 C：前端适配（发现 19 → 修复 18 → 记录 1）

- **C1 rem 陷阱**：标题级 text-lg/xl/2xl 共 14 处转显式 px（页面 h1/h2→18px，卡片 h3→16px，TaskList 统计值 3 处→24px，ScheduledTasksList 头条→18px，SummaryCard 标题→16px）。正文 text-sm/base 按既定档位未动。
- **C2 深色硬编码**：白字压 brand/primary 三处违规修复——`ConfirmDialog`（危险态保留白字压 error，brand 态改 on-primary）、`ExecPolicySettings` 保存按钮、`ScheduledTasksList` logo 图标（**这个是真 bug**：浅色主题 primary-container 是 #E4E4E7 浅灰，白图标几乎不可见，改 text-primary）。`VoiceButton` 录制态 `bg-red-500` 字面量 → `--color-error` token。`.ts` 侧只剩 `preview-agent/editBubble.ts` 两处 #fff（预览 iframe 内自包含浮层，CSS 变量不可达，符合画布豁免，保留）。
- **C3 缩放 × fixed**：代码级结论——Electron 主路径 `setZoomFactor` 整页等比，全屏 `inset-0` 遮罩与浮层菜单均无错位风险；H5 浏览器回退走 `body.style.zoom`，全屏遮罩安全，但 **JS 定位的浮层菜单**（session-menu、ProjectHeaderMenu 等 `getBoundingClientRect()` + fixed left/top）在非 100% 缩放下存在坐标空间混用的理论错位。建议 H5 模式锁定 100% 或菜单改 absolute（需人工决策，低优先）。
- **C4 中英对齐**：zh/en 双向 diff 为零（任务 A 已做）；`t()` 引用 vs zh 缺失清零（剩余 4 个"命中"均为动态前缀拼接或语言切换器自标签，已逐一排除）。

## 任务 D：审美一致性（发现→修复）

- **D1 半像素**：字号类只剩 `FilePreviewModal.vue:145` 的 10.5px → 11px，清零。1.5px 边框 hairline 与 0.5px letter-spacing 属有意为之，未动。
- **D2 图标档位**：78 处归档（13→14、15→16、17→18、22→20，及图标上的 text-lg/xl/2xl/base rem 类→显式 px），34 个文件。**保留并记录**：`text-[10px]/[12px]`/`text-sm/xs` 微图标（梯子无此档，与 13px 正文配对的刻意微尺寸）与 32/36/40/48px 空态大图标（独立尺度）。
- **D3 圆角档位**：13 处归档（3→4 ×4、5→4、7→8 ×4、18→16 ×2、28→24、32→24）。任意值圆角现已全部落在 {4,6,8,10,12,14,16,24} 内。
- **D4 颜色字面量**：7 处 `#b45309` 警告色字面量 → `var(--color-warning)`（token 存在且明暗自适应 #CA8A04/#B54708，原字面量不随主题变；含 RagDebugPanel/SseDebugOverlay 的 #f59e0b 混色）。**保留（有意）**：design-canvas/studio 渐变、ImageGalleryModal #111 看图黑底、AnimationPlayer 四叶草渐变。

## 需重启 / 验证事项

1. **madcop server（8765，运行中，未 kill）需重启**才能生效 `/api/training/status`（前端轮询在旧 server 上仍会 404 一次然后按超时处理——已把首次检查改为立即，失败也只会显示一次轮询超时，不会崩）。
2. 前端改动需重新 `vite build`（已构建通过，产物在 `dist-vue/`）；打包流程未动。
3. 建议早晨人工冒烟：①设置→通用→拖缩放滑条应实时生效且重启保持；②设置→关于→点 GitHub 链接应开浏览器；③MCP 设置→从 JSON 导入→项目路径建议不再恒空；④聊天空会话占位文案显示中文而不是 `chat.emptyNoMessages`。

## 红线自查

✅ 未 push（4 个本地 commit 待审）｜✅ 未写 `~/.madcop/`（仅读 server 健康检查）｜✅ 未动 package.json 依赖 / electron 打包配置｜✅ 未动 `~/.zcode/`、`~/.codex/`｜✅ 每个 commit 前 `vite build` 通过（最终复跑 1.19s ✓）｜✅ 后端 `py_compile` + import 验证（8 路由确认注册）｜✅ commit 按任务分组、格式符合 `fix(night)/chore(night)`。
