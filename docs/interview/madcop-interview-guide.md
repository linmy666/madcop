# MadCop — 面试准备文档 / Interview Prep Guide

> **阅读时间：** ~10 分钟 | **建议面试前通读 2 遍**

---

## 一、一句话介绍 / Elevator Pitch

**中文：**
> MadCop 是一个本地优先的 AI 编程伙伴桌面应用。它在后台监控你的代码文件和终端输出，只在检测到异常（测试失败、编译错误、服务崩溃）时主动提醒你；每次有价值的对话会自动蒸馏成可复用的技能文件；搜索类回答附带引用来源；知识图谱随使用自动增长。所有数据留在本地，不上云。

**English:**
> MadCop is a local-first AI coding partner desktop app. It runs in the background, watching your files and terminal, and proactively alerts you only when anomalies appear — test failures, compile errors, crashes. It auto-distills valuable conversations into reusable skill files; every search-backed answer carries source citations; a knowledge graph grows automatically with use. All data stays on your machine — never the cloud.

---

## 二、核心特性详解 / Feature Deep-Dive

### 1. 主动观察器 / Proactive Observer
- **是什么：** 后台递归监控工作区的文件保存（`fs.watch recursive`）和终端输出（30s 轮询 PTY scrollback）
- **怎么工作：** 文件保存/终端输出变化 → 读取内容 → 发送到后端 LLM 判断 → 只有异常（SyntaxError、测试失败、崩溃堆栈）才弹通知
- **技术亮点：** 不是简单关键词匹配，而是用 LLM 做语义判断——区分"正常日志"和"真正需要关注的异常"
- **Demo 方式：** 在工作区文件里写个 `SyntaxError` 保存 → 看系统通知

### 2. 自动技能蒸馏 / Auto Skill Distillation
- **是什么：** 每次有价值的对话（≥400 字符 + 有代码/列表/标题结构）自动保存为 `~/.madcop/skills/*.md`
- **怎么工作：** 对话结束后，后端用启发式规则判断价值 → 提取主题 → 生成 SKILL.md（含标题、使用场景、完整内容）
- **实际效果：** 目前已自动生成 34 个技能文件
- **Demo 方式：** 问一个技术问题 → 完成后看 toast "Skill saved" → 打开技能页查看

### 3. 引用溯源 / Citation Traceability
- **是什么：** 当 Agent 调用 `web_search`/`web_fetch` 工具时，搜索结果作为 citations 附在回复末尾
- **怎么工作：** 后端收集 web_search/web_fetch 的 tool_result → 去重 → 附在 done 事件的 metadata → 前端渲染引用卡片
- **Demo 方式：** 问"搜一下 XXX" → 回复下方显示引用来源（可点击 URL）

### 4. 知识图谱自动增长 / Knowledge Graph Auto-Growth
- **是什么：** 每次有价值的对话自动提取知识点，写入 brain.db 知识图谱
- **怎么工作：** 对话结束后，`brain/auto_extract.py` 提取主题 + 内容 → 存为知识节点 → 知识画布可视化
- **实际效果：** 目前 17 个知识节点，全部 `source=chat-auto`
- **Demo 方式：** 打开知识画布 → 看节点随对话增多

### 5. 本地优先 / Local-First
- **所有数据在 `~/.madcop/`：** brain.db（知识图谱）、memory.db（4 层记忆）、skills/（技能文件）、runs/（trace）
- **无遥测：** 没有 analytics/telemetry/phone-home
- **API key 加密：** Fernet 对称加密存储，文件权限 600
- **Demo 方式：** `ls ~/.madcop/` + `cat ~/.madcop/settings.json`（看 key 是 `fernet:...`）

---

## 三、技术架构 / Architecture

```
┌─────────────────────────────────────────┐
│           Electron Desktop App           │
│  ┌──────────┐  ┌─────────────────────┐  │
│  │  Vue 3   │  │   Electron Main      │  │
│  │  Renderer│  │  - File Watcher      │  │
│  │  (Vite)  │  │  - Terminal (PTY)     │  │
│  │  Pinia   │  │  - Observer          │  │
│  │  Tailwind│  │  - Notifications     │  │
│  └────┬─────┘  └──────────┬──────────┘  │
│       │     IPC / HTTP     │             │
│  ─────┴────────────────────┴───────────  │
│                 127.0.0.1:8765           │
├─────────────────────────────────────────┤
│           FastAPI Backend (Python)       │
│  ┌──────────┐ ┌────────┐ ┌───────────┐  │
│  │ Agent    │ │ Memory │ │  Brain    │  │
│  │ Engine   │ │ (5层)  │ │  Graph    │  │
│  │(ReAct/   │ │ SQLite │ │  SQLite   │  │
│  │ Quick/   │ │ + FTS5 │ │           │  │
│  │ Deep)    │ └────────┘ └───────────┘  │
│  └──────────┘                            │
│  ┌──────────┐ ┌────────┐ ┌───────────┐  │
│  │ Skills   │ │ Tools  │ │ Observer  │  │
│  │ Distill  │ │(search,│ │ Judge API │  │
│  │          │ │ fetch, │ │           │  │
│  │          │ │ file…) │ │           │  │
│  └──────────┘ └────────┘ └───────────┘  │
├─────────────────────────────────────────┤
│         LLM Provider (用户自选)          │
│    MiniMax / OpenAI / Anthropic / GLM    │
└─────────────────────────────────────────┘
```

**关键设计决策：**
- SSE (Server-Sent Events) 流式输出，不是 WebSocket
- `<think>` 标签分离器：把模型的推理过程和答案分开流式显示
- HITL (Human-in-the-Loop) 确认协议：文件编辑前用户 Approve/Reject
- 增量状态更新：避免 O(n²) 的全量重算

---

## 四、Vibe Coding 说明 / About Vibe Coding

**中文：**
> MadCop 是我完全通过 vibe coding 构建的——我不是程序员，不会写代码，但我能清晰地描述产品需求和用户体验。我使用 AI 编程助手（ZCode）作为我的"编程伙伴"，通过自然语言对话的方式指导它实现我的产品构想。整个过程中，我做的是产品决策、架构思考、体验优化和质量验收，代码实现由 AI 完成。这恰恰证明了 MadCop 的核心理念：AI 不是替代人，而是放大人的能力。

**English:**
> MadCop was built entirely through vibe coding — I'm not a programmer and don't write code directly. Instead, I articulate clear product requirements and user experiences, and use an AI coding assistant (ZCode) as my "programming partner" to implement them. My role is product decisions, architectural thinking, experience optimization, and quality verification — the actual code is written by AI. This itself proves MadCop's core thesis: AI doesn't replace humans, it amplifies them.

---

## 五、面试常见问题 / Common Interview Questions

### Q1: 你不是程序员，怎么保证代码质量？/ How do you ensure code quality as a non-programmer?

**中文回答：**
> 我通过三层机制保证质量：第一，我做了三轮全模块字段审查（以产品经理视角检查每个字段是否合理、是否有死字段）；第二，我要求 AI 对每个修复写单元测试并跑通；第三，我做端到端验证——发真实请求看 SSE 事件流，确认每个功能从后端到前端完整工作。我不读代码的每一行，但我验证每一个用户能感知的行为。

**English:**
> Three layers: First, I conducted three rounds of full-module field audits from a PM perspective. Second, I required AI to write and pass unit tests for each fix. Third, I do end-to-end verification — sending real requests and checking SSE event streams to confirm each feature works from backend to frontend.

---

### Q2: 这个项目最难的部分是什么？/ What was the hardest part?

**中文回答：**
> 最难的是流式输出的体验。模型（MiniMax-M3）把推理过程放在 `<think>` 标签里混在正文流中，我需要实时分离推理和答案——这涉及一个状态机（ThinkSeparator），处理跨 chunk 的标签拆分。另外，ReAct 引擎的协议解析和 `<think>` 分离器之间有冲突——同一个文本被两套系统处理，导致答案重复 4 遍。最终通过"缓冲 30 字符窗口"解决了竞态条件。

**English:**
> The streaming UX was hardest. MiniMax-M3 embeds reasoning in `<think>` tags within the content stream. I built a stateful separator (ThinkSeparator) that splits reasoning from answers in real-time, handling tags split across chunks. Another challenge: the ReAct parser and ThinkSeparator both processed the same text, causing 4x answer duplication. I solved this with a "30-char buffer window" to resolve the race condition.

---

### Q3: 为什么选择本地优先？/ Why local-first?

**中文回答：**
> 两个原因：一是信任——开发者不希望把代码和 API key 托管在别人的云上；二是延迟——本地 SQLite + FTS5 搜索比云数据库快 10 倍以上。代价是没有多设备同步，但对于一个编程伙伴来说，你的代码本来就在一台机器上。

**English:**
> Two reasons: trust — developers don't want code and API keys on someone else's cloud; and latency — local SQLite + FTS5 is 10x faster than cloud DBs. The tradeoff is no multi-device sync, but for a coding partner, your code lives on one machine anyway.

---

### Q4: 观察器怎么判断什么是异常？/ How does the Observer decide what's an anomaly?

**中文回答：**
> 不是关键词匹配——而是用 LLM 做语义判断。文件内容/终端输出发送到 `/api/proactive/check`，后端用当前活跃的 LLM 判断 `worth: true/false`。Prompt 明确列了：报错、异常堆栈、测试失败、编译失败 = True；正常日志、成功命令 = False。这样能区分"print 调试信息"和"真正的 crash"。

**English:**
> It's not keyword matching — it's LLM-based semantic judgment. File/terminal content is sent to `/api/proactive/check`, where the active LLM returns `worth: true/false`. The prompt explicitly lists: errors, exception stacks, test failures, compile failures = True; normal logs, successful commands = False.

---

### Q5: 知识图谱是怎么增长的？/ How does the knowledge graph grow?

**中文回答：**
> 每次对话结束后，如果回复 ≥400 字符且有结构化内容（代码/列表/标题），后端自动提取主题和内容，写入 brain.db 作为知识节点。用户不需要手动创建——聊着聊着图谱就长大了。这呼应了"understanding you better over time"——用的越多，Agent 积累的上下文越丰富。

**English:**
> After each conversation, if the reply is ≥400 chars with structured content, the backend auto-extracts a topic + content into brain.db as a knowledge node. No manual creation needed — the graph grows as you chat. This embodies "understanding you better over time."

---

### Q6: 和 Cursor / Claude Code 有什么区别？/ How is this different from Cursor / Claude Code?

**中文回答：**
> 三个核心差异：第一，**主动观察器**——Cursor/Claude Code 是你问它才答，MadCop 会主动在后台监控并提醒；第二，**知识图谱**——对话自动沉淀成可视化的知识网络，Cursor 没有；第三，**Provider 无关**——MadCop 支持任何 OpenAI/Anthropic 兼容的 API，Cursor 绑定自己的模型。

**English:**
> Three core differences: First, the proactive Observer — Cursor/Claude Code are reactive, MadCop monitors in the background. Second, the knowledge graph — conversations auto-precipitate into a visual knowledge network. Third, provider-agnostic — MadCop works with any OpenAI/Anthropic-compatible API.

---

### Q7: 你在这个过程中学到了什么？/ What did you learn?

**中文回答：**
> 三点：第一，**产品思维比代码能力更重要**——我的价值在于定义"做什么"和"什么是好的体验"，而非"怎么写循环"；第二，**AI 协作需要精确的反馈**——与其说"修好它"，不如说"在文件 X 的 Y 行，期望行为是 Z，实际是 W"；第三，**验证是关键**——AI 生成的代码经常"看起来对但实际有 bug"，端到端测试不可省略。

**English:**
> Three things: First, product thinking matters more than coding ability — my value is defining "what" and "what good looks like." Second, AI collaboration needs precise feedback — "fix it" vs "in file X line Y, expected Z, got W." Third, verification is critical — AI-generated code often looks right but has subtle bugs.

---

### Q8: 如果让你继续做，下一步是什么？/ What's next?

**中文回答：**
> 三个方向：一是完整的代码 Diff Accept/Reject（目前 HITL 协议已通，但 Diff 渲染还需要打磨）；二是多 Agent 协作（deep 模式的专家分工）；三是从本地走向"本地优先 + 可选云同步"——让用户选择哪些数据同步。

**English:**
> Three directions: full code diff Accept/Reject (HITL protocol works, diff rendering needs polish); multi-agent collaboration (deep mode specialist teams); and evolving from local-only to "local-first with optional cloud sync."

---

## 六、Demo 清单 / Demo Checklist

面试时按这个顺序演示（约 5 分钟）：

| 步骤 | 操作 | 展示什么 | 对应特性 |
|---|---|---|---|
| 1 | 打开 MadCop | 侧边栏：观察器/记忆/知识画布 | 产品完整度 |
| 2 | 发"搜一下 XXX 的最新动态" | 思考过程流式 → 工具调用卡片 → 答案流式 → 引用来源 | 流式 + 搜索 + 引用 |
| 3 | 打开知识画布 | 看刚才的对话自动变成知识节点 | 知识图谱增长 |
| 4 | 打开技能页 | 看刚才的对话自动蒸馏成 SKILL.md | 技能蒸馏 |
| 5 | 打开记忆页 | 看 4 层记忆 | 记忆系统 |
| 6 | 在项目文件里写 SyntaxError 保存 | 看系统通知 | 观察器 |
| 7 | 终端: `ls ~/.madcop/` | 看所有数据在本地 | 本地优先 |

---

## 七、技术关键词 / Technical Keywords

面试时可以用这些词展示技术理解：

- **SSE (Server-Sent Events)** — 流式输出协议
- **ReAct Engine** — Thought → Action → Observation 循环
- **ThinkSeparator** — `<think>` 标签状态机，分离推理和答案
- **HITL (Human-in-the-Loop)** — 文件编辑前用户确认
- **FTS5** — SQLite 全文搜索
- **Fernet** — API key 对称加密
- **Pinia** — Vue 3 状态管理
- **Electron IPC** — 主进程/渲染进程通信
- **PTY** — 伪终端（终端监控）
- **Incremental State** — O(1) 增量更新 vs O(n²) 全量重算

---

## 八、诚实的局限 / Honest Limitations

面试时主动提到局限，显得真诚：

- **MiniMax-M3 在 ReAct 模式下不稳定**——有时不输出完整的 Action；quick 模式更可靠
- **Mermaid 图渲染偶有问题**——依赖 mermaid.js 的版本兼容
- **H5 手机访问是半成品**——桌面端优先，手机版布局不够完善
- **没有多设备同步**——本地优先的代价
- **测试覆盖率不够高**——vibe coding 的固有挑战

---

*Good luck! 🚀 祝面试顺利！*
