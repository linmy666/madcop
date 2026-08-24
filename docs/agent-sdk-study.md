# 开源 Agent SDK 技术原理研究 & MadCop 优化路线

> 2026-08 · 源码级研究（非文档转述）。四个参照系：**OpenAI Agents SDK**（openai-agents-python）、
> **Claude Agent SDK**（claude-agent-sdk-python，Claude Code 官方 harness）、**LangGraph**、
> **pi-mono**（Mario Zechner 极简实现）。所有结论带源码出处。

## 一、四大 SDK 的核心技术决策

### 1. Agent Loop：显式单步结果 + 纯工具调用

**OpenAI Agents SDK** — `run_loop.py:1184` 的 `while True` 循环，每轮产出**可序列化的
`next_step` 状态对象**（`NextStepRunAgain / Handoff / FinalOutput / Interruption`）。
中断/恢复/重放全部建立在这个基础上。

**pi-agent** — `agent-loop.ts:170-222`，双层 while，约 150 行核心：
流式取 assistant 消息 → 过滤 toolCall → 按执行模式并行/顺序执行 → 结果回填 → 循环。
**没有文本协议解析**——全靠原生 function calling。

**关键共识：没有任何一个成熟 SDK 用文本协议（`Thought:/Action:`）做工具调用。**
MadCop 的 ReActEngineV4 以文本协议为主、tool_calls 为覆盖，正是本次会话里
FA-marker 泄露、拼接 JSON、协议误匹配等一系列流式 bug 的共同根源。

### 2. 截断安全：stopReason=length 时工具调用全部作废

**pi** `agent-loop.ts:208-214`：`stopReason === "length"` 时所有 toolCall 参数可能被截断，
**全部报错不执行**，让模型重发。MadCop 目前会照常执行截断的参数（写半个文件的风险）。

### 3. 并行工具执行

**OpenAI SDK** `tool_execution.py:1643-1683`：每轮收集全部 tool call，
`asyncio.create_task` 并发执行（`max_function_tool_concurrency` 控槽位），
`asyncio.wait(FIRST_COMPLETED)` 排水；多工具失败采用隔离策略。
MadCop 引擎每步只执行一个工具（index 0），MiniMax 发多个调用时后面的被丢弃。

### 4. HITL：可持久化的中断，不是内存 Future

**LangGraph**：`interrupt()` = 节点内抛 `GraphInterrupt`（`types.py:967`），状态随
checkpoint **落盘**；resume 时 `Command(resume=v)` 经 pending writes 匹配回原任务，
**节点从头纯函数重放**——不需要序列化执行栈。

**Claude SDK**：权限回调是反转的 RPC——CLI 发 `control_request{can_use_tool}`，
SDK 阻塞等 `control_response`（`query.py:478-530`），返回值可携带
`updatedInput`（改写工具参数）和 `updatedPermissions`（升级为持久规则）。

MadCop 现状：`concurrent.futures.Future` + 内存字典 + **120 秒超时自动拒绝**，
刷新页面即失效——本次 E2E 就撞上了 "no pending confirmation" 竞态。

### 5. 上下文压缩：token 驱动 + 结构化摘要 + 合法切点

**pi** `compaction.ts:147-422`（最可复刻的完整实现）：
- 触发：`contextTokens > contextWindow - reserveTokens`（reserve 默认 16384）
- 摘要 prompt：结构化 checkpoint——Goal / Constraints / Progress(Done/In
  Progress/Blocked) / Key Decisions / Next Steps / Critical Context，要求保留精确路径与报错
- 切点：尾部保留 `keepRecentTokens`（默认 20000），回退到合法边界
  （user / bashExecution / branchSummary），**跳过 toolResult 防孤儿**
- 二次压缩：增量 UPDATE prompt 合并旧摘要
- 摘要请求走独立 session，不污染主对话缓存
- token 计数：以 provider usage 为准 + 尾部增量 `chars/4` 估算
  （`compaction.ts:216-244`）；usage 早于最近压缩则跳过触发防误判

**Claude Code**：压缩后旧消息被 `isCompactSummary` 消息取代，`logicalParentUuid`
指向边界；fork 时重映射边界指针（`session_mutations.py:423-427`）。

MadCop 现状：`chat_v4.py` 的压缩 = 保留头 2 条 + 尾 12 条 + 中间每条**截断 200 字符**，
无 token 计数、无 LLM 摘要——长会话上下文质量塌方。

### 6. Prompt 缓存友好的系统提示组织

**Claude SDK** `types.py:46-57`：`exclude_dynamic_sections` 把 cwd/git status/日期等
**动态段从 system prompt 剥离，改注入首条 user message**——system prompt 跨请求稳定，
provider 前缀缓存才能命中。MadCop 每个请求都在拼装不同的 `sys_prefix`
（日期 + 记忆 + 风格 + 模式指令 + build 指令），缓存完全失效。

### 7. 会话持久化：append-only JSONL + 父链树 + fork

**pi**（`harness/session/jsonl/`）：首行 header（版本/id/cwd），每行 mutation 带
`seq/timestamp`；**Record 层操作审计**（operation_started/step_attempt/tool_started）
支持崩溃恢复（未闭合 operation 即恢复点）；fork = 沿父链复制 entry + 重排 seq + 原子写。

**Claude Code**：`~/.claude/projects/<dir>/<session>.jsonl`，`uuid/parentUuid` 树形，
`--resume-session-at=<uuid>` 可截断到任意消息，`--fork-session` 离线 fork
（过滤 sidechain → 全量 uuid 重映射 → `O_EXCL` 原子写）。

MadCop 的 SessionLog 已经是 append-only JSONL + EventDomain，方向正确，缺：父链
（无法分支）、操作审计层（无法崩溃恢复）、fork。

### 8. 子代理：隔离上下文，agent-as-tool

**OpenAI SDK**：handoff = "返回新 agent 的工具"（`transfer_to_{name}`），新 agent
继承全量历史；`Agent.as_tool`（`agent.py:583-612`）= 子代理拿**全新生成的 input**、
原 agent 继续对话——上下文完全隔离。
**Claude Code**：Task 工具创建子代理，独立 JSONL（`isSidechain` 标记），无压缩，
完成后唤醒主代理产生后续 turn。

MadCop 的 MEA（Manager→Coder→Tester→Reviewer）共享同一个执行器上下文，
没有子代理上下文隔离。

### 9. 重试与可观测

**OpenAI SDK** `retry.py`：错误归一化（status/code/is_timeout/retry_after）+
`approve_unsafe_replay` **与**普通 retry 分离——流式响应已吐出一半时，重放需要显式批准。
**Tracing**：contextvars 维护 trace→span 树（agent→turn→generation→tool），
usage 挂 span。MadCop 的 trace store 只有根节点。

## 二、MadCop 差距矩阵与优先级

| # | 差距 | 参照 | MadCop 现状 | 优先级 |
|---|---|---|---|---|
| 1 | 截断工具调用不执行 | pi agent-loop.ts:208 | 照常执行截断参数 | **P0 · 半天** |
| 2 | 原生工具调用为主协议 | 所有 SDK | 文本协议为主，双路径 | **P0 · 2天** |
| 3 | 并行工具执行 | OpenAI tool_execution | 每步一个，丢弃 index>0 | **P0 · 1天** |
| 4 | 持久化 HITL | LangGraph interrupt | 内存 Future + 120s 自动拒 | **P0 · 1天** |
| 5 | token 驱动压缩 + 结构化摘要 | pi compaction.ts | 头2尾12 + 200字符截断 | **P1 · 2天** |
| 6 | prompt 缓存友好前缀 | Claude exclude_dynamic_sections | sys_prefix 每请求变化 | **P1 · 半天** |
| 7 | 类型化重试 + 重放安全 | OpenAI retry.py | 无重试，读超时直接 ERROR | **P1 · 1天** |
| 8 | usage/token 预算管理 | pi compaction.ts:216 | 全链路无 token 计数 | **P1 · 1天** |
| 9 | trace span 树 | OpenAI tracing | 仅根节点 | P2 |
| 10 | 会话树 + fork + 崩溃恢复 | pi/Claude session | 线性 log | P2 |
| 11 | 子代理上下文隔离（MEA 重构） | Agent.as_tool / Task 工具 | 共享上下文 | P2 |
| 12 | hooks 体系（PreToolUse 链） | Claude hooks | 仅 confirm_handler | P2 |

### 落地顺序建议

**第一批（P0，约一周）——正确性**：
1. `finish_reason=length` → 丢弃本轮全部工具调用，观察结果回填让模型重发（#1）
2. ReActEngineV4 切换为 tool_calls 主路径，文本协议降级为兼容开关（#2）
   ——顺手消灭 ThinkSeparator 与文本协议交织的整类 bug
3. 一轮内并发执行全部工具调用，结果按 index 全量回填（#3）
4. 确认事件写入 SessionLog（`tool_confirm_request/pending` 事件），刷新页面后
   从 log 重建确认卡；超时从"自动拒绝"改为"保持挂起"（#4）

**第二批（P1，约一周）——效率与体验**：
5. 采集 provider usage（chat 响应里有）→ 上下文 token 预算 → 驱动压缩；
   压缩换 pi 的结构化 checkpoint prompt + 合法切点（#5 #8）
6. 系统前缀稳定化：静态段（人设/工具说明）与动态段（日期/记忆/指令）分离，
   动态段注入首条 user message（#6）
7. LLM 调用重试：网络类错误退避重试；流式中断错误单独分类（#7）

**第三批（P2）——架构升级**：trace span 树、会话 fork、MEA 子代理隔离、hooks。

## 三、源码速查

| 主题 | 位置 |
|---|---|
| OpenAI 主循环 | openai-agents-python `src/agents/run_internal/run_loop.py:1184` |
| 并行工具 | 同上 `tool_execution.py:1643` |
| 重试归一 | 同上 `retry.py:50-129` |
| tracing contextvars | 同上 `tracing/scope.py:11` |
| LangGraph 超步循环 | langgraph `libs/langgraph/langgraph/pregel/main.py:2959` |
| checkpoint 结构 | `libs/checkpoint/.../base/__init__.py:92` |
| interrupt 实现 | `libs/langgraph/langgraph/pregel/_algo.py:1290` |
| Claude 权限控制协议 | claude-agent-sdk-python `src/claude_agent_sdk/_internal/query.py:478` |
| Claude fork | 同上 `session_mutations.py:348-447` |
| pi 极简 loop | pi-mono `packages/agent/src/agent-loop.ts:170` |
| pi 压缩全实现 | 同上 `packages/agent/src/harness/compaction/compaction.ts:147-422` |
| pi session 编解码 | 同上 `packages/agent/src/harness/session/jsonl/codec.ts:70` |
