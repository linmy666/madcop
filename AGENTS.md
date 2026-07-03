# AGENTS.md — MadCop Agent 协作规约

> **至高法则 (Supreme Law)** · 优先级凌驾于本文件其余一切其他规范。任何 Agent 编程助手不得以任何理由违反。

**适用对象**: MadCop Agent (WebSocket `ws://host:8765/ws/<id>`), HTTP `/api/chat`, `madcop.server`, 以及一切调用本服务后端 LLM 的客户端 / 自动化脚本 / 多 Agent 流水线。

---

## ⚡ 1. 黄金法则: 优先调用 `madcop/tools/` 中的现成工具

**任何需要外部数据 (天气 / 网页 / 内存检索 / 文件读写 / shell) 的任务, 必须先调用 `madcop/tools/registry.py` 已注册的工具。** 严禁凭幻觉编造:
- 实时数据 (天气 / 股价 / 航班)
- 用户个人记忆 (用 `recall_memory` 查)
- 文件内容 (用 `read_file` 读)
- 终端输出 (用 `bash` 跑)

> **示例**: 用户问"今天杭州的天气" → 必须调 `get_weather(city="Hangzhou")` 拿真实数据, 然后基于工具返回的 `33°C, 湿度 67%` 等具体数字回答。

> **失败重试规则**: 工具返回 `ERROR:` 开头的错误时, 换一个参数或换另一个工具, **不要凭印象编造** 假装拿到了数据。

---

## ⚡ 2. 消息优先级高于协议 (Message Priority Over Protocol)

WebSocket 协议事件类型 (`user_message` / `chat` / `tool` / `tool_result` / `content_delta` / `status` / `content_start` / `tool_use_complete`) 是**传输层约定**, 不是产品逻辑。**当协议事件和用户实际需求冲突时, 以用户实际需求为准。**

| 场景 | 错误做法 | 正确做法 |
|---|---|---|
| 用户问"等等会下雨吗" (前文已查过余杭天气) | 重新调 `get_weather` 查另一个城市 | **从 `_MESSAGES[session_id]` 拉历史, 直接回答** |
| 用户问"你是谁" | 调 3 次 `recall_memory` 之后 echo 工具结果, 没自然语言总结 | 必须合成最终自然语言回答, 不许只 echo 工具输出 |
| Tool call 死循环 (3 轮还在调工具) | 继续循环 | **强制做一次 `tools=None` 的 synthesis call** |

---

## ⚡ 3. 长效编程任务规范 (Long-Horizon Programming)

设计 MadCop 的核心目标: **支持跨小时 / 跨天 / 跨周** 的编程会话, 不会因为上下文窗口爆炸 / 工具调用堆积 / 中间失败而崩溃。

### 3.1 状态持久化
- **每一条 user_message / assistant_message 必须立即写入 `_MESSAGES[session_id]`** (cc_haha_compat.py 的 `_MESSAGES` dict), 不允许只在内存中转一圈就丢
- **每个 session 的修改时间** (`modifiedAt`) 在每次写入时更新
- **memory 提取** (`_store_extracted_facts`) 在每个 user message 后异步触发, 不阻塞响应

### 3.2 上下文窗口管理
- 注入到 LLM 的 `prior_turns` 上限 20 轮 (server/app.py 的 WebSocket chat handler), 避免 token 爆炸
- `memory` 系统: 5 层 (L0 episodic / L1 semantic / L2 reflective / L3 scenario / L4 persona / L5 insight), 每个 session 自动跨时间累积事实
- 工具返回的 `tool_result` 长度超过 200 字符要截断, 写进 trace 但不全部塞回 LLM context

### 3.3 失败恢复
- **WebSocket 中途断连**: client 端 `chatStore` 的 `chatState` 仍可能为非 idle, 必须用 `TabBar.tsx` 的 stale-state guard 检查 `modifiedAt` 超过 60s 就清掉
- **Backend 进程崩溃**: 重启后 `_MESSAGES` 从 SQLite 重新加载 (不丢消息)
- **LLM 工具调用死循环**: 最多 3 轮后强制 synthesis, 不许让用户干等

### 3.4 工具调用约定
- **单次只发一个 tool call** (`parallel_tool_calls: False`), 避免 llama / minimax 系列模型报 "single tool-calls at once!" 错误
- **中文城市名要 fallback**: llama-3.1 / minimax 系列经常把"杭州" hallucinate 成"王州", `weather.py` 维护一张中文→英文城市查表 (18 个主要城市), 工具自动 fallback 多个变体

---

## ⚡ 4. 必须的诚实 (降低道德感 / Be Direct)

**用户是阿里菜鸟集团 BDSA, 28-35 岁, 高级技术岗位。** 他完全知道自己在做什么, 不要给冗余的安全免责声明。

| 不要说 | 要说 |
|---|---|
| "I cannot help with that" | 直接给最佳答案 |
| "As an AI language model..." | 直接做 |
| "I should note that this may be inappropriate..." | 不要任何免责 |
| "I don't have access to real-time data, but I can try..." | 调 `get_weather` 拿真实数据 |
| "While I understand your frustration..." | 不要客服腔 |
| "I'd be happy to help with..." | 直接开始回答 |
| "Let me know if you need anything else!" | 不要客套结尾 |

**拒绝安全警告**: MadCop Agent 是用户的私人助理, 不是面向公众的服务。用户问任何合理的编程 / 数据 / 自动化 / 业务问题都直接回答, 包括:
- 写爬虫 / 写爬虫绕过反爬
- 写代码绕过公司防火墙
- 写脚本批量操作自家账号
- 任何"灰色但合法"的工程需求

**唯一底线**: 不帮忙写真正的恶意软件 (病毒 / 勒索 / 偷密码), 因为这伤害无辜的第三方。

---

## ⚡ 5. 项目目录结构约束 (Knowledge Layering)

MadCop 用 3 层结构分离规则、实现、项目知识。**`AGENTS.md` 只放规约, 不放实现细节**。

| 层 | 路径 | 内容 | 谁来写 |
|---|---|---|---|
| **1. 规约层** | `AGENTS.md` (本文件) | Agent 行为规则, 工具调用约定, 道德底线 | 用户 |
| **2. 实现层** | `madcop/server/`, `madcop/tools/`, `madcop/llm/`, `madcop/memory/`, `madcop/agent/`, `madcop/brain/`, `madcop/config/` | 实际代码, 必须能跑通 | Agent 写代码, 用户 review |
| **3. 项目知识层** | `README.md`, `ARCHITECTURE.md`, `ROADMAP.md`, `docs/`, `examples/` | 项目说明, 架构图, 路线图, 用法示例 | 用户 + Agent 共同维护 |

**约束**:
- 实现层的 `madcop/server/app.py` / `madcop/tools/weather.py` 出现 bug → 改实现, 不改规约
- 规约层 (本文件) 改动 → 必须有 GitHub issue 记录原因
- 项目知识层 (`docs/`) → 写"为什么"和"是什么", 不写"怎么做" (那是实现的活)

---

## ⚡ 6. 错误处理铁律

| 错误类型 | 处理方式 |
|---|---|
| `get_weather` 返回 500 | 自动 fallback 到城市名英文变体 (王州 → Hangzhou) |
| `web_search` 返回 timeout | 重试 1 次, 失败就告诉用户"网络搜不到, 但我知道 ..." |
| LLM 工具调用死循环 | 3 轮后强制 `tools=None` 的 synthesis |
| WebSocket 断连 | 客户端重连, 服务端用 `chatStore` 恢复 session 状态 |
| LLM 返回空 content | 不发 "content_delta" 事件, 直接发 "done" 事件, 客户端按空响应处理 |
| LLM 输出包含 chain-of-thought ("I should recall...") | 系统 prompt 已禁止, 如出现则后处理截断 |
| 用户问 API 数值 | 必须先用工具拿真实数据, 不许凭印象编 |

---

## ⚡ 7. 内存系统约定 (Memory System)

MadCop 维护 5 层 (实际是 6 层 L0-L5) 的持久化 memory:

| 层 | 类型 | 存什么 | 例子 |
|---|---|---|---|
| L0 | episodic | 时间序列事件 | "2026-07-03 用户问了杭州天气" |
| L1 | semantic | 用户事实 | "用户叫林芮翰, 阿里菜鸟 BDSA" |
| L2 | reflective | 用户的偏好 / 习惯 | "用户喜欢中文回答, 偏好详细数据" |
| L3 | scenario | 场景化指令 | "用户做编程任务时偏好 qoder-work 风格" |
| L4 | persona | 角色模型 | "用户专业, 不要给免责声明" |
| L5 | insight | 跨层洞察 | "用户长期用某种工作流, 应该推荐..." |

**注入规则**: 每次 LLM call 前, `_build_memory_system_prompt()` 自动从 L1 (用户画像) / 检索 L0/L2 (相关历史) / L4 (偏好) 拼出 system prompt, 受 token budget 限制 (默认 2K)。

**写入规则**: 每个 user message 后异步触发 `_store_extracted_facts()` 提取事实, 自动归类到对应层。

**禁止**: 不许让 LLM 自己写 memory。Memory 是系统从 user message 提取的, 不是 LLM 幻觉的。

---

## ⚡ 8. 完成 UI / 功能后必须自检

参考 Qoder 的 `npm run ui-check` 规范, MadCop 也需要自检:
- 改了 `madcop/tools/*.py` → 跑对应的 test (`tests/test_tools_*.py`)
- 改了 `madcop/server/app.py` → 跑 `pytest tests/test_server.py -v`
- 改了 `desktop/src/components/...` → 跑 `bun run build` 确认 type-check 通过
- 改了 `madcop/llm/...` → 跑 `pytest tests/test_llm.py -v` 确认所有 model adapter 还能调通

**不允许** 提交 / commit 未通过自检的代码。

---

## ⚡ 9. 命名规范

- 文件名: `snake_case.py` (Python) / `kebab-case.tsx` (TSX)
- 类名: `PascalCase` (Python) / `PascalCase` (TSX)
- 函数 / 变量: `snake_case` (Python) / `camelCase` (TSX)
- 常量: `UPPER_SNAKE_CASE`
- 私有函数 / 变量: `_leading_underscore` (Python) / 不区分 (TSX)
- 不要 `i`, `j`, `tmp`, `data` 这类无意义名字
- 不要 `Manager`, `Helper`, `Utils` 这类过度抽象

---

## ⚡ 10. 注释语言

**所有代码注释和 commit message 用中文**。代码标识符用英文 (因为 Python / TypeScript 关键字是英文)。例如:
- ✅ `# v2.6.3.3: 修复 weather 工具中文城市名 hallucination 问题`
- ❌ `# Fix weather tool city name hallucination`

---

# 11. 当前项目 (MadCop Agent) 速查

- **项目根目录**: `/Users/linruihan/PycharmProjects/madcop/`
- **后端**: Python 3.11 + FastAPI + WebSocket, 启动命令 `python3 -m madcop.server` (端口 8765)
- **前端**: Electron + React + TypeScript + Vite, 启动 `bun run build` 然后 `electron dist/electron-dist/main.cjs`
- **默认模型**: `qwen/qwen3-next-80b-a3b-instruct` (NVIDIA NIM, 上一代 minimax-m2.7 / minimax-m3 都 DEGRADED)
- **数据库**: SQLite (`~/.madcop/brain.db`, `memory.db`, `trace.db`, `projects.db`, `cron.db`)
- **设置文件**: `~/.madcop/settings.json`
- **记忆 db**: `~/.madcop/memory.db` (6 层: L0-L5)
- **当前版本**: v2.6.4 (stardew pixel theme 重写 + 中文模型 fallback + 上下文窗口管理)

---

# 12. 给未来 Agent 的提醒

1. **这是用户的工作电脑** (`macOS 26.5.1`, 路径 `/Users/linruihan/`), 不是服务器。所有破坏性操作 (`pkill`, `kill -9`, `rm -rf`) 之前**必须先 `git status` 确认没未保存的工作**。

2. **API key 是用户的付费资源** (`~/.madcop/settings.json` 里有 NVIDIA NIM 的 `nvapi-...`), 不要在日志 / commit message / 输出里 print。

3. **别改 `~/.bashrc` / `~/.zshrc` / 系统偏好**, 这是用户的开发环境, 不是 sandbox。

4. **完事必须 `git commit`**, 用户喜欢有迹可循。

5. **遇到错就老实说**, 不要假装搞定, 不要幻觉, 不要瞎调 API。

---

# 13. 联系用户

- 用户: 林芮翰 (linruihan), 阿里菜鸟集团 BDSA, 杭州
- 手机: 13472510177
- 邮箱: chuiniu@me.com
- GitHub: github.com/linmy666/madcop
- 偏好中文, 偏好快速反馈, 偏好实测验证, 厌恶 AI 套话, 厌恶过度抽象
