<p align="center">
  <img src="docs/img/characters/madcop-mascot.png" width="120" alt="MadCop mascot"/>
</p>

<h1 align="center">MadCop</h1>

<p align="center">
  <strong>周思万虑，巡行无疆</strong> — 你的本地 AI Agent 桌面工作站
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg" alt="License: MIT"/></a>
  <img src="https://img.shields.io/badge/version-v0.9-blue" alt="version"/>
  <img src="https://img.shields.io/badge/Python-3.11+-green.svg" alt="Python"/>
  <img src="https://img.shields.io/badge/Vue-3.5-brightgreen.svg" alt="Vue 3"/>
  <img src="https://img.shields.io/badge/Electron-42-blueviolet.svg" alt="Electron"/>
</p>

<p align="center">
  <b>本地优先 · 多模型 · 工具调用 · 可视化工作流 · AI 原型设计 · Agent 网络 · 知识库</b>
</p>

---

## ✨ 预览

<table>
  <tr>
    <td align="center"><b>多模型对话</b><br/>侧栏 + Tab + 工作区 + 工具调用</td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/01-chat.png" alt="Chat"/></td>
  </tr>
  <tr>
    <td align="center"><b>实时生成报告</b><br/>LLM 流式输出 + 自动任务拆解</td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/02-generating.png" alt="Generating"/></td>
  </tr>
  <tr>
    <td align="center"><b>多模态报告 + 表格</b><br/>Markdown + 数据可视化</td>
  </tr>
  <tr>
    <td><img src="docs/screenshots/03-report.png" alt="Report"/></td>
  </tr>
</table>

---

## 🎯 核心能力

### 🤖 多模型对话
- **OpenAI 兼容协议**：GLM-5.2 / DeepSeek / Qwen3 / GPT-4o 等任何兼容端点
- **流式 SSE 输出**，工具调用可视化追踪
- **多 Tab + 多 Session**，本地消息历史持久化
- **Mermaid 图表渲染**、Markdown 完整支持
- **可配置默认 LLM**，用户自由切换

### 🛠️ 工具系统
- `web_search` — 联网搜索（基于 DuckDuckGo，零配置）
- `web_fetch` — 抓取任意 URL 文本
- `read_file` / `write_file` / `edit_file` — 文件 I/O
- `weather` — 实时天气
- `clarify` — 反问澄清
- **MCP 兼容** — 加载第三方 MCP 服务器工具
- 用户自定义工具注册

### 🧠 Agent 网络
- **6 个内置 Agent**：通用助手 / 编码专家 / 设计助手 / 研究员 / 规划师 / 审查员
- **可视化编排画布**（拖拽节点、连线定义消息流）
- **Agent Hub**：发现、安装、切换第三方 Agent
- **本地优先**：所有 Agent 元数据存本地 SQLite

### 📚 知识库
- 文档 / 链接 / 笔记 / 代码 四种类型
- 标签管理 + 置顶 + 全文搜索
- **对话中可引用知识条目**（@ 提及）

### ⚙️ 工作流引擎（v0.9 新增）
- **12 种 Google Agent 设计模式**预设
  - `single_agent` · `sequential` · `parallel` · `coordinator`
  - `hierarchical` · `swarm` · `loop` · `human_in_loop`
  - `review_critique` · `iterative_refine` · `react` · `custom`
- **可视化节点编辑器**
- **9 种高级节点**：条件路由、循环、HTTP 请求、代码执行等

### 🎨 AI 原型设计
- 自然语言 → UI 组件树 → 可视化画布
- 11 种基础组件 + 嵌套容器
- 多页面项目 + 批量生成
- 撤销/重做 + 视口切换 + 导出 `.madcop` 项目

### 🏗️ 多 Agent 路由（v0.9）
- **意图识别**：用配置的默认 LLM 自动分类用户请求
- **任务拆解**：多步骤任务自动注入"搜索→写→回复"等子计划
- **工具强提示**：系统消息强制 LLM 主动调用工具（不再把工具参数当文本输出）

### 🔄 Continuous Learning（v0.9）
- 反馈本地持久化
- 不向云端发送训练数据
- 可选微调（LoRA 默认关闭）

---

## 🏗️ 技术架构

```
┌───────────────────────────────────────────────────────┐
│                   Electron Shell                     │
│  ┌─────────────────────┐  ┌──────────────────────┐  │
│  │   Vue 3 + Pinia +   │  │   Python Backend     │  │
│  │   Tailwind v4 UI    │  │   (FastAPI + Uvicorn)│  │
│  │   (Electron Renderer)│←→│                       │  │
│  └─────────────────────┘  │  ┌──────────────────┐ │  │
│                            │  │  LLM Client     │ │  │
│  ┌─────────────────────┐  │  │  (OpenAI Compat)│ │  │
│  │  Agent Network     │  │  └──────────────────┘ │  │
│  │  + Design Tool     │  │  ┌──────────────────┐ │  │
│  │  + Workflow Editor  │  │  │  Tool Registry  │ │  │
│  │  + Knowledge Base  │  │  │  + MCP Client   │ │  │
│  └─────────────────────┘  │  └──────────────────┘ │  │
│                            │  ┌──────────────────┐ │  │
│                            │  │  Workflow Engine │ │  │
│                            │  │  + 12 Modes      │ │  │
│                            │  └──────────────────┘ │  │
│                            └──────────────────────┘  │
└───────────────────────────────────────────────────────┘
```

| 层 | 技术栈 | 角色 |
|---|---|---|
| **桌面壳** | Electron 42 | macOS / Windows / Linux 跨平台 |
| **前端** | Vue 3.5 + Pinia + Tailwind v4 | 渲染进程 UI |
| **后端** | Python 3.11 + FastAPI + Uvicorn | 本地 HTTP + WebSocket |
| **LLM** | OpenAI 兼容协议 | GLM-5.2 / DeepSeek / Qwen3 / 自定义 |
| **存储** | SQLite + JSON | 会话、工作流、知识库 |
| **工具** | MCP 兼容 | web / file / shell / 自定义 |

---

## 🚀 快速开始

### 环境要求

- **Python** 3.11+
- **Node.js** 23+ (或 Bun)
- **操作系统**：macOS 13+ / Windows 10+ / Ubuntu 22+

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/linmy666/madcop.git
cd madcop

# 2. 后端依赖
pip install -e .

# 3. 启动后端（一个终端）
python -m madcop.server
#  → http://127.0.0.1:8765

# 4. 前端依赖（另一个终端）
cd desktop
bun install  # 或 npm install / pnpm install

# 5. 构建 Electron
bun run build:electron  # 或 npm run build:electron

# 6. 启动桌面端
./node_modules/electron/dist/Electron.app/Contents/MacOS/Electron \
  ./electron-dist/main.cjs --no-sandbox
```

### 配置 LLM

打开 MadCop → **设置** → **供应商** → 添加你的 API key：

| 供应商 | Base URL | 推荐模型 |
|---|---|---|
| **Sensenova 智谱** | `https://token.sensenova.cn/v1` | GLM-5.2 |
| **DeepSeek** | `https://api.deepseek.com/v1` | DeepSeek-V3 |
| **NVIDIA NIM** | `https://integrate.api.nvidia.com/v1` | Qwen3-80B |
| **OpenAI** | `https://api.openai.com/v1` | GPT-4o-mini |
| **自部署** | `http://your-host/v1` | 任何 OpenAI 兼容模型 |

---

## 📁 项目结构

```
madcop/
├── desktop/                  # Electron 桌面端
│   ├── src/vue/              # Vue 3 前端（~155 个 .vue 文件）
│   ├── public/               # 静态资源（吉祥物、图标）
│   ├── electron/             # Electron 主进程
│   └── theme/                # CSS 主题系统
│
├── madcop/                   # Python 后端包
│   ├── server/               # FastAPI 应用
│   │   ├── app.py            # 主路由（chat / workspace / sessions / chatStore）
│   │   └── madcop_compat.py  # 兼容层（保留旧 React UI 协议）
│   ├── llm/                  # OpenAI 兼容客户端
│   ├── tools/                # 工具注册（web_search / write_file / MCP / ...）
│   ├── workflow/             # 工作流引擎 + 12 种 mode 预设
│   ├── workflow/nodes/       # 节点类型（llm / 条件 / 循环 / 编排器）
│   ├── agent_network/        # Agent 网络 API
│   ├── memory/               # 7 层记忆系统
│   ├── training/             # Continuous learning（本地反馈）
│   ├── arena/                # 多 LLM 对比
│   ├── design/               # AI 原型设计后端
│   └── analysis/             # 供应链分析模块
│
├── docs/                     # 文档
│   ├── screenshots/          # README 截图
│   ├── img/                  # 历史图片
│   ├── design-tool/          # 设计工具文档
│   └── workflow-editor/      # 工作流编辑器文档
│
├── README.md
└── LICENSE
```

---

## 🆕 v0.9 新增

- ✅ **多 Agent 路由**（intent classification + task planning）
- ✅ **本地消息历史持久化**（reload 不丢历史）
- ✅ **侧栏工作空间自动归类**（按目录分组）
- ✅ **Continuous Learning**（本地反馈，零云端）
- ✅ **MCP 服务器自动加载**
- ✅ **工具调用追踪**（侧栏可见工具执行进度）
- ✅ **工作目录感知**（`write_file` 自动写到用户选的工作区）
- ✅ **大输出不再截断**（`max_tokens: 8192`）
- ✅ **Vue 3 完整迁移**（旧的 React UI 已弃用）
- ✅ **Workspace 路径管理**（侧栏底部快速切换）

---

## 📜 版本历史

| 版本 | 状态 | 主要变更 |
|---|---|---|
| **v0.9** | ✅ 当前 | 多 Agent 路由 / 持久化历史 / MCP / Continuous Learning |
| v0.6 | 历史 | Vue 3 迁移 / 工作流引擎 / 12 种 mode |
| v0.3 | 历史 | Agent 网络 / 知识库 / 工具系统 |
| v0.1 | 历史 | 多模型对话原型 |

---

## 🛣️ 路线图

- [ ] **本地推理引擎**（MLX / llama.cpp）— 完全离线
- [ ] **多模态视觉**（图像理解）
- [ ] **Agent Marketplace**（云端可选发现）
- [ ] **Mobile Companion**（手机端 + 同步）
- [ ] **Skill Marketplace**（技能商店）

---

## 🤝 贡献

欢迎提 Issue / PR。开发前请先读 `docs/VUE3_MIGRATION_HANDBOOK.md` 了解架构。

---

## 📝 License

[MIT](LICENSE)

---

## 👤 Author

**林芮翰 (Lin Ruihan)**

- GitHub: [@linmy666](https://github.com/linmy666)
- Email: chuiniu@me.com
- 项目主页: [github.com/linmy666/madcop](https://github.com/linmy666/madcop)

<p align="center">
  <sub>Built with ❤️ using Vue 3 · Python · Electron · and a lot of coffee</sub>
</p>
