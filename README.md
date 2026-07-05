# MadCop

> 周思万虑，巡行无疆 — 你的本地 AI Agent 桌面工作站

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-green.svg)](https://python.org)
[![Vue 3](https://img.shields.io/badge/Vue-3.5-brightgreen.svg)](https://vuejs.org)
[![Electron](https://img.shields.io/badge/Electron-42-blueviolet.svg)](https://electronjs.org)

MadCop 是一个**本地优先**的 AI Agent 桌面应用，支持多模型对话、可视化工作流编排、AI 原型设计、Agent 网络和知识库管理。

## ✨ 核心功能

### 🤖 多模型对话
- 支持 OpenAI 兼容协议（GLM-5.2 / DeepSeek-V4 / Qwen3 等）
- 流式输出、工具调用、Mermaid 图表渲染
- WebSocket 实时通信，多会话并行

### 🧠 Agent 网络
- **6 个内置 Agent**：通用助手、编码专家、设计助手、研究员、规划师、审查员
- **可视化编排**：拖拽式 Agent Network 画布，连线定义消息流
- **Agent Hub**：发现和安装第三方 Agent

### 📚 知识库
- 文档 / 链接 / 笔记 / 代码 四种类型
- 标签管理 + 置顶 + 搜索
- Agent 对话中可引用知识条目

### 🎨 AI 原型设计
- 自然语言 → UI 组件树 → 可视化画布
- 11 种组件 + 嵌套容器
- 多页面项目管理 + 批量生成
- 撤销/重做 + 视口切换 + 导出 `.madcop`

### ⚙️ 工作流引擎
- 12 种 Google Agent 设计模式预设
- 可视化节点编辑器
- 9 种高级节点类型（条件/循环/HTTP/代码执行）

### 🔧 工具系统
- 天气查询、网页搜索、文件读写、Shell 执行
- 自定义工具注册（MCP 兼容）
- 工具调用可视化追踪

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────┐
│                Electron Shell                │
│  ┌─────────────┐  ┌───────────────────────┐ │
│  │   Vue 3 UI   │  │   Python Backend      │ │
│  │  (Vite +     │  │   (FastAPI +          │ │
│  │   Pinia +    │←→│   Uvicorn)            │ │
│  │   Tailwind)  │  │                       │ │
│  └─────────────┘  │  ┌─────────────────┐  │ │
│                    │  │  LLM Client     │  │ │
│  ┌─────────────┐  │  │  (OpenAI Compat)│  │ │
│  │  Design Tool │  │  └─────────────────┘  │ │
│  │  (Canvas)    │  │  ┌─────────────────┐  │ │
│  └─────────────┘  │  │  Tool Registry  │  │ │
│                    │  └─────────────────┘  │ │
│  ┌─────────────┐  │  ┌─────────────────┐  │ │
│  │ Agent Network│  │  │ Agent Registry  │  │ │
│  │   Canvas     │  │  │ + Knowledge Base│  │ │
│  └─────────────┘  │  └─────────────────┘  │ │
│                    └───────────────────────┘ │
└─────────────────────────────────────────────┘
```

| 层 | 技术 | 说明 |
|---|---|---|
| **前端** | Vue 3 + Pinia + Tailwind v4 | Electron 渲染进程 |
| **后端** | Python 3.11 + FastAPI + Uvicorn | 本地 HTTP + WebSocket |
| **LLM** | OpenAI 兼容协议 | GLM-5.2 / DeepSeek / Qwen3 |
| **桌面** | Electron 42 | macOS / Windows / Linux |
| **存储** | SQLite + JSON | 会话历史 + 工作流 + 知识库 |
| **工具** | MCP 兼容 | 天气 / 搜索 / 文件 / Shell |

## 🚀 快速开始

### 环境要求
- Python 3.11+
- Node.js 23+ (或 Bun)
- macOS 13+ / Windows 10+ / Ubuntu 22+

### 安装

```bash
# 克隆仓库
git clone https://github.com/linmy666/madcop.git
cd madcop

# 后端
pip install -e .
python -m madcop.server

# 前端（另一个终端）
cd desktop
bun install
bun run build:electron

# 启动
./node_modules/electron/dist/Electron.app/Contents/MacOS/Electron \
  ./electron-dist/main.cjs --no-sandbox
```

### 配置模型

打开 MadCop → 设置 → 供应商 → 添加你的 API key：
- **Sensenova** (GLM-5.2) — `https://token.sensenova.cn/v1`
- **DeepSeek** — `https://api.deepseek.com/v1`
- **NVIDIA NIM** (Qwen3) — `https://integrate.api.nvidia.com/v1`
- 或任何 OpenAI 兼容 API

## 📁 项目结构

```
madcop/
├── desktop/                 # Electron 桌面端
│   ├── src/vue/             # Vue 3 前端 (154+ .vue 文件)
│   ├── electron/            # Electron 主进程
│   └── theme/               # CSS 主题系统
├── madcop/                  # Python 后端
│   ├── server/              # FastAPI 应用
│   ├── agent_network/       # Agent 网络 API
│   ├── llm/                 # LLM 客户端
│   ├── tools/               # 工具注册
│   └── workflow/            # 工作流引擎
├── docs/                    # 文档
└── README.md
```

## 📝 License

MIT

## 👤 Author

**林芮翰**
- GitHub: [@linmy666](https://github.com/linmy666)
- Email: chuiniu@me.com