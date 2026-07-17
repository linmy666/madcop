# MadCop Session 交接文档

**日期：** 2026-07-17  
**仓库：** `https://github.com/linmy666/madcop`（`main`）  
**工作区：** `/Users/linruihan/PycharmProjects/madcop`  
**桌面前端：** Vue 3 + Electron，产物 `desktop/dist-vue/`  
**后端：** `python -m madcop.server` → 默认 `http://127.0.0.1:8765`

本文覆盖本 session 内讨论、实现、踩坑与验收结论（含更早延续的 Meta-Harness / UI 工作摘要）。

---

## 1. 本 session 目标与结果总览

| 主题 | 目标 | 结果 |
|------|------|------|
| 前端界面 | 优化二级/三级设置与 Agent 相关页 | 已 polish + build |
| 深度多 Agent | 讲清场景分类与侧栏两个 Agent 差异 | 已说明 + 扩展分类引擎 |
| 透明真专家 (方案 B) | 专家绑工具、客户无感、单 LLM 可用 | 已落地 |
| 附件分析失败 | 上传简历分析从未成功 | 已修多条链路 |
| 写文件到工作区/下载 | 改完放下载目录从未成功 | 已修 allowlist + 历史上下文 |
| clarify 无 UI | 工具跑了聊天区空白 | 已修 SSE + 面板位置 |
| 计划面板假加载 | 分析完仍「生成执行计划…」 | 已修 idle 态 |
| 最终答案显示 JSON | 成功写文件但气泡是 `{"message":"...\n"}` | 已 unwrap |
| 端到端自测 | 分析 + 写 Downloads | **API 实测 PASS** |

**勿动：** 用户根目录/项目中的 `快递调研报告.md`（既有约定）。

---

## 2. 关键提交（本 session 相关，`main`）

按时间从旧到新（节选）：

```
fc0e8e0 polish(ui): secondary/tertiary settings screens and Agent detail
ca66b51 feat: score-based deep multi-agent routing + sidebar Agent split
9658b50 feat: transparent specialist mini-ReAct with role-scoped tools
a2d9950 fix: attachments reach deep/standard modes; writes honor work_dir
9a0468f fix: surface ask_user/clarify in standard and plan modes
cf2d0be fix: detect Word without .docx suffix; skip plan/clarify when attachment present
7712f61 fix: default agent_mode to standard; disable plan_mode when attachments present
24083b5 fix: plan panel idle state; clarification card placement; allow Downloads writes
f058ee9 fix: pass conversation history into standard ReAct mode
f2e2ed8 fix: unwrap JSON FINAL_ANSWER so UI shows markdown not escaped \n
```

更早（同主线、session 前已有）：Meta-Harness Phases 0–4、`SIDEBAR.MORE` i18n、UI shell 等（`1c456ad` 及更早）。

---

## 3. 架构要点（给接手人）

### 3.1 双栈前端

- **生产渲染：** 仅 Vue → `desktop/dist-vue/`  
- Electron `main` 加载 `dist-vue/index.html`  
- 改 UI 后务必：`cd desktop && npx vite build --config vite.vue.config.ts`  
- 用户需 **Cmd+Q 完全退出 App 再开**，否则仍跑旧前端

### 3.2 对话模式（`agent_mode`）

| 模式 | 后端行为 |
|------|----------|
| `quick` | 单次 LLM，`messages` 全量（含附件注入） |
| `standard` | **ReAct** 工具环；需带 **历史 context**（本 session 已修） |
| `deep` | 多 Agent DAG + 场景分类 + 专家 mini-ReAct |
| `auto`/null | 走后续 Phase（含 plan_mode 等），易进「澄清计划」坑 |

**UI 与请求曾不一致：** 选择器默认显示「标准」，但 `chatStore` 曾把未选择写成 `auto` → 后端走 plan+clarify、中间空白。已改为默认发送 `standard`。

### 3.3 Plan-and-Execute（`plan_mode`）

- 会话默认 **`planModeEnabled: false`**（已改；此前 true 导致右侧假计划）  
- 有附件时前端强制 `plan_mode=false`  
- 后端有 ATTACHMENT 正文时也跳过 plan 循环  

### 3.4 工作区与写文件

- 工具 allowlist：`workspace_dir`、cwd、home、**`~/Downloads`、`~/Desktop`**、`~/.madcop/preview`  
- 相对路径 resolve 到 allowlist **第一项**（通常是 session `work_dir`）  
- Chat 请求字段：`work_dir`（来自 session / localStorage `madcop_workspace_dir`）  
- 全局 `_ws_state` 可被请求中的 `work_dir` 同步  

### 3.5 附件链路

```
前端 FileReader → dataUrl
  → POST /api/chat attachments[{id,name,path?,dataUrl}]
  → _read_attachment_direct (txt/pdf/docx/xlsx…)
  → 拼进 messages 最后一条 user：
       --- ATTACHMENT: name (ID: …) ---
       <正文>
       --- END ---
```

**深度/标准曾用 `body.messages[-1].content`（无附件）** → 已改为用 **注入后的 messages** 作为 `_task_text`。

Word 无 `.docx` 后缀时：用 mime / 文件名含 Word / zip 魔数识别。

### 3.6 标准 ReAct 上下文（关键修复）

- 以前：`run(_task_text)` 只有最新一句  
- 现在：`context=` 最近多轮 user/assistant（含分析正文）  
- 规则：有历史/附件则勿无脑 `ask_user`；下载目录直接 `write_file`  
- `FINAL_ANSWER`：`normalize_final_answer` 拆 `{"message":"...\\n"}`  

### 3.7 深度多 Agent 场景分类

**文件：** `madcop/agent_network/engine.py`、`specialist_runtime.py`

- 打分 + 混合规则：coding / design / research / writing / data / security / fullstack / general  
- 骨架：`planner → specialists∥ → synthesizer`  
- 专家工具硬 allowlist（非仅 prompt）：  

| 角色 | 工具倾向 |
|------|----------|
| planner | read_file, get_time |
| coder | read/write/edit/xlsx |
| designer | read, write |
| researcher | web_search, web_fetch, read |
| reviewer | read only |
| synthesizer | 无工具，专用合并 prompt |

- 单 LLM：无 `agent_routing` 时共用 active provider model  

### 3.8 侧栏两个「Agent」

| 入口 | 页面 |
|------|------|
| 主栏 **Agent** | `AgentOverview`（拓扑协作） |
| 更多 → **工作流** | `WorkflowsListPage`（已改名，避免重复） |
| 设置 → Agent | `AgentsSettings`（定义 + 模型路由） |

### 3.9 Clarify / ask_user

- 工具名：`ask_user`（ClarifyTool）  
- 标准 ReAct / plan 自动执行后：发 `clarification_request` + 可见 `text`  
- 前端：`clarificationPending` + `ClarificationPanel`（输入框上方实心卡，勿盖消息区）  

---

## 4. 关键代码路径

| 路径 | 职责 |
|------|------|
| `madcop/server/app.py` | chat SSE、附件注入、quick/standard/deep、plan、clarify 事件 |
| `madcop/server/models.py` | `ChatRequest.work_dir`、`ChatAttachment` |
| `madcop/agent_network/engine.py` | 深度 DAG、分类、`build_engine` |
| `madcop/agent_network/specialist_runtime.py` | 角色工具表、mini-ReAct 前缀 |
| `madcop/agent_network/react_engine.py` | 标准 ReAct、`normalize_final_answer` |
| `madcop/agent_network/task_router.py` | auto 时 quick/standard/deep 启发式 |
| `madcop/tools/__init__.py` | default_registry allowlist |
| `madcop/tools/files.py` | read/write/edit、相对路径、docx 提取 |
| `madcop/tools/clarify.py` | ask_user |
| `desktop/src/vue/stores/chatStore.ts` | SSE、history、agent_mode/plan_mode、JSON unwrap |
| `desktop/src/vue/components/chat/ChatInput.vue` | 附件 dataUrl |
| `desktop/src/vue/components/chat/ClarificationPanel.vue` | 澄清卡 UI |
| `desktop/src/vue/components/plan/PlanTasksPanel.vue` | 任务监控 idle/busy |
| `desktop/src/vue/pages/Settings.vue` 等 | 设置二级页 polish |
| `desktop/vite.vue.config.ts` | 构建到 `dist-vue` |

---

## 5. 运维与本地启动

### 后端

```bash
cd /Users/linruihan/PycharmProjects/madcop
export PYTHONPATH=/Users/linruihan/PycharmProjects/madcop
# 若已有旧进程，先 kill 再起（改 app.py 必须重启！）
python3 -m madcop.server
# health: curl -s http://127.0.0.1:8765/api/health
```

**踩坑：** 曾出现 Python 进程从下午一直跑到晚上，**代码已改但进程未重启** → 用户侧「依然如此」。

### 前端

```bash
cd /Users/linruihan/PycharmProjects/madcop/desktop
npx vite build --config vite.vue.config.ts
# Electron 开发/加载 dist-vue 后：完全退出再开
```

### 端到端 API 实测结论（本 session 已跑通）

1. 上传 txt 简历 +「这个简历怎么样」→ 有结构化分析，无 ask_user  
2. 同会话「优化写到 `~/Downloads/madcop_e2e_resume_opt.md`」→ `write_file`，文件存在  
3. 用户真实路径示例：`~/Downloads/姚振炀简历_优化版.md`（已写出；当时 UI 把答案显示成 JSON，文件本身正常）

---

## 6. 用户可见问题 ↔ 根因 ↔ 状态

| 现象 | 根因 | 状态 |
|------|------|------|
| 上传 docx/pdf「没有分析对象」 | deep/standard 丢附件；plan+clarify | 已修 |
| 改文件从不落盘 | allowlist 无 Downloads；ReAct 无历史；相对路径 | 已修 |
| 右侧任务假转圈 | plan=null 时永远「生成中」 | 已修 idle |
| clarify 中间空白 | 无 clarification_request；FINAL 空 | 已修 |
| UI「标准」实际 auto | chatStore 默认 auto | 已修 standard |
| 后端改了不生效 | server 未重启 | 运维注意 |
| 成功但显示 JSON `\n` | FINAL_ANSWER 包成 message JSON | 已修 |
| 两个侧栏 Agent | 曾重复指向 workflows | 已拆拓扑/工作流 |

---

## 7. 产品/设计说明（曾向用户解释）

### 深度 vs 标准 ReAct

- 标准：单 Agent + 工具环（现在带历史）  
- 深度：场景分类 + 多角色并行 + 综合；专家工具硬切；默认同模型也可跑  
- 客户无感：无新设置页；单 LLM 共用 active model  

### 专家「能力」如何定义

- 主要：`BUILTIN_AGENTS` 的 description/capabilities → system prompt  
- 加上：工具 allowlist + 图位置 + 可选 `agent_routing` 模型  
- 不是插件式硬技能安装  

---

## 8. 测试

```bash
cd /Users/linruihan/PycharmProjects/madcop
python3 -m pytest tests/test_attachment_and_workdir.py \
  tests/test_specialist_runtime.py tests/test_deep_engine.py \
  tests/test_agent_mode.py tests/test_react_normalize.py -q
```

手动验收建议：

1. 重启 server + Cmd+Q 重启 App  
2. 新对话上传简历 → 分析  
3. 同会话：`请优化简历并 write_file 到 ~/Downloads/xxx.md`  
4. 打开下载目录确认文件；UI 应为正常 Markdown 而非 JSON  

---

## 9. 已知残留 / 后续可选

1. **模型仍可能**调用多余 `echo` / 偶发 `ask_user`（提示已加强，非 100% 消除）  
2. **旧会话气泡**不会自动重排版；JSON 显示只影响当时那条  
3. **Electron 与独立 `python -m madcop.server`** 若各起一份，端口/代码版本可能不一致——确认只跑一份新代码  
4. **深度模式写盘**：依赖 coder 节点 mini-ReAct；复杂多轮仍建议标准模式 + 明确路径  
5. **plan 侧栏** 默认关闭 plan 后意义变弱；可考虑仅 deep 时自动开  
6. **Meta-Harness**（`~/.madcop/meta_harness/`）本 session 未大改；设置 → Meta-Harness 可用  
7. **i18n** 用户偏好中文/英文；部分设置文案仍硬编码中文  

---

## 10. 配置与数据目录

| 路径 | 用途 |
|------|------|
| `~/.madcop/` | 用户数据、memory、preview、meta_harness |
| `~/Library/Application Support/Electron` 等 | Electron 用户数据（视启动方式） |
| `localStorage madcop_workspace_dir` | 前端工作区记忆 |
| Settings active_provider | 如 sensenova / nvidia 等 |

---

## 11. 交接检查清单

- [ ] `git pull` 到 `f2e2ed8` 或更新  
- [ ] 重启 `python -m madcop.server`  
- [ ] `dist-vue` 已 build 且 App 全量重启  
- [ ] 附件分析 + 写 Downloads 手测一遍  
- [ ] 确认未误删用户业务文件（快递报告等）  
- [ ] 知悉：UI 默认标准、附件关 plan、Downloads 可写  

---

## 12. 一句话总结

本 session 把 MadCop 从「深度/附件/写盘/澄清 UI 系统性断链」修到 **API 端到端可分析附件并写入 Downloads**；前端需 **build dist-vue + 杀进程重启后端** 才与源码一致。后续重点是模型服从度与深度模式写盘稳定性，而非再找「完全没读到文件」的主路径 bug。

---

*文档生成自 2026-07-17 Grok Build session 交接请求。*
