# AI Design 工具调研 + .madcop 文件格式

## 一、AI Design 工具市场调研

### 1.1 主流产品

| 产品 | 定位 | 核心能力 | 操作方式 |
|---|---|---|---|
| **Galileo AI** | UI 设计生成 | 文字描述 → 完整 UI 界面（Figma 格式） | Prompt → 生成 → Figma 编辑 |
| **Uizard** | 快速原型 | 截图/草稿 → 可编辑 UI | 上传→AI识别→拖拽编辑 |
| **Visual Copilot** (Builder.io) | 设计转代码 | Figma 设计 → 生产级 React/Vue 代码 | Figma 插件 → 导出代码 |
| **Locofy.ai** | 设计转代码 | Figma/Adobe XD → React/Next.js 代码 | 设计文件 → 配置 → 导出 |
| **Figma AI** | 设计辅助 | 重命名图层、生成原型、自动布局 | Figma 内置 AI 命令 |
| **Looom** | 动效设计 | 手绘风格动画制作 | iPad 手绘 → 动效 |
| **v0.dev** (Vercel) | 前端代码生成 | 文字描述 → React/Tailwind 组件 | Prompt → 实时预览 → 修改 |
| **Morphic** | 自适应 UI | 文字 → 可编辑界面 | Prompt → 生成 → 修改 |

### 1.2 核心架构（通用模式）

```
用户输入 (Prompt / 手绘 / 截图)
       ↓
[LLM / 视觉模型]  → 理解意图
       ↓
[组件树生成] → JSON 描述 UI 结构（类型、位置、属性、文字、颜色）
       ↓
[渲染引擎] → Canvas / Figma / HTML
       ↓
[交互编辑]  ← 拖拽 / 属性面板 / 文字编辑
       ↓
[导出] → Figma / React / HTML / PDF
```

### 1.3 关键技术点

**1. 组件树（Component Tree）**
AI 生成的是**结构化的 JSON**，不直接画像素：

```json
{
  "type": "page",
  "children": [
    {
      "type": "header",
      "props": { "title": "Dashboard", "bgColor": "#fff" },
      "children": [
        { "type": "button", "props": { "text": "Login", "variant": "primary" } }
      ]
    },
    {
      "type": "section",
      "props": { "layout": "grid", "columns": 3 },
      "children": [...]
    }
  ]
}
```

**2. 渲染引擎**
这层把 JSON 组件树变成**真正可交互的 UI**。方案：
- **iframe / WebComponent**：安全性高，编辑需 postMessage 桥接
- **内联 React 渲染**：灵活度高，但风险是执行用户代码
- **Canvas (HTML5 Canvas / Fabric.js)**：完全可控，但交互实现复杂

**3. 编辑能力**
编辑分三层：
- **属性面板**：选中组件，右侧显示可编辑属性（文字、颜色、大小）
- **画布直接操作**：拖拽移动、拉伸大小、双击改文字
- **Prompt 修改**：选中组件后，用文字指令修改

---

## 二、MadCop 设计方案

### 2.1 设计工具功能范围（Phase 1）

```
用户: "帮我设计一个登录页面"
  → LLM 生成组件树 JSON
  → 渲染到交互画布
  → 用户可拖拽 / 修改属性
  → 导出为 HTML / Markdown / React
```

### 2.2 组件树 Schema

```typescript
interface DesignComponent {
  id: string
  type: 'page' | 'header' | 'section' | 'button' | 'input' | 'image' |
        'text' | 'card' | 'list' | 'form' | 'table' | 'icon' | 'divider'
  props: {
    text?: string
    placeholder?: string
    width?: number | string
    height?: number | string
    x?: number
    y?: number
    bgColor?: string
    color?: string
    fontSize?: number
    fontWeight?: number
    borderRadius?: number
    border?: string
    gap?: number
    padding?: number
    layout?: 'flex' | 'grid' | 'column'
    columns?: number
    src?: string  // for images
    href?: string  // for links
    icon?: string  // icon name
  }
  children: DesignComponent[]
}

interface DesignProject {
  id: string
  title: string
  description: string
  width: number      // canvas width in px
  height: number     // canvas height in px
  components: DesignComponent[]
  createdAt: number
  updatedAt: number
}
```

### 2.3 流程

```
1. 用户输入 Prompt
2. LLM 生成 DesignProject JSON
3. 前端用 React 渲染到画布 (每个组件是一个可拖拽的 React 组件)
4. 用户编辑：
   - 点击选中 → 右侧属性面板
   - 拖拽移动 → 更新 x/y
   - 双击文字 → 内联编辑
   - Prompt 二次修改 → LLM 更新组件树
5. 导出：
   - HTML（内联样式）
   - Markdown（简化版）
   - .madcop 文件（完整项目格式）
```

---

## 三、.madcop 文件格式

### 3.1 设计原则

- **纯 JSON**，人类可读，可 diff
- **自包含**：一个 .madcop 文件 = 完整的可恢复项目
- **可导入导出**：本地优先，可选分享
- **兼容 Git**：纯文本，可版本管理

### 3.2 文件格式

```json
{
  "_format": "madcop-project",
  "_version": "1.0",
  "_created_by": "MadCop Agent v2.8.0",
  "_generated_at": "2026-07-04T01:30:00Z",

  "project": {
    "id": "uuid",
    "title": "登录页面设计",
    "description": "用户登录界面原型",
    "type": "design",
    "tags": ["ui", "prototype", "login"],
    "thumbnail": "data:image/png;base64,..."
  },

  "settings": {
    "canvas_width": 1440,
    "canvas_height": 900,
    "theme": {
      "primary": "#7C3AED",
      "bg": "#FAFAFA",
      "text": "#1A1A1A",
      "radius": 8,
      "font": "Inter, sans-serif"
    }
  },

  "components": [
    {
      "id": "page-1",
      "type": "page",
      "props": {
        "width": 1440,
        "height": 900,
        "bgColor": "#FAFAFA",
        "layout": "flex",
        "padding": 40
      },
      "children": [
        {
          "id": "header-1",
          "type": "header",
          "props": {
            "text": "欢迎回来",
            "fontSize": 32,
            "fontWeight": 700,
            "color": "#1A1A1A",
            "x": 100,
            "y": 200,
            "width": 400,
            "height": 48
          }
        },
        {
          "id": "input-email",
          "type": "input",
          "props": {
            "placeholder": "输入邮箱",
            "x": 100,
            "y": 280,
            "width": 400,
            "height": 48,
            "border": "1px solid #E2E8F0",
            "borderRadius": 8
          }
        },
        {
          "id": "btn-login",
          "type": "button",
          "props": {
            "text": "登录",
            "variant": "primary",
            "width": 400,
            "height": 48,
            "x": 100,
            "y": 360,
            "bgColor": "#7C3AED",
            "color": "#FFFFFF",
            "borderRadius": 8
          }
        }
      ]
    }
  ],

  "chat_context": {
    "original_prompt": "帮我设计一个登录页面",
    "model": "glm-5.2",
    "session_id": "..."
  }
}
```

### 3.3 文件扩展名

`.madcop` — 单一格式，涵盖所有类型：
- `project.madcop` — 纯设计项目
- `workflow.madcop` — 工作流编排
- `report.madcop` — BI 报告

### 3.4 应用场景

| 场景 | 操作 |
|---|---|
| 导出一份设计 | 画布 → 右键 → 导出 .madcop |
| 导入一个设计 | 工作流/设计页 → 导入 .madcop |
| 分享一个工作流 | 发送 .madcop 文件给其他人 |
| Git 版本管理 | .madcop 是纯 JSON，可直接 commit |
| 二次编辑 | 导入 .madcop → LLM 读取 → 用户继续改 |

### 3.5 实施计划

| Phase | 内容 |
|---|---|
| Phase 1 | .madcop 格式定义 + 导出/导入 JSON |
| Phase 2 | 设计画布（拖拽组件 + 属性面板） |
| Phase 3 | LLM → 组件树生成 |
| Phase 4 | Canvas 直接修改（拖拽、拉伸、内联编辑） |
| Phase 5 | 导出为 HTML / React / Markdown |

---

## 四、多 Agent 模式模型选择问卷

### 4.1 问题

选择多 Agent 模式（并行/协调器/Swarm/分层/审核等）时，用户需要给每个 Agent 分配 LLM 模型：

```
选择了「并行分析」模式 (3 个 Agent + 1 汇总 Agent)

模式配置：
┌─────────────────────────────────────────────────┐
│ 模式: 并行分析                                   │
│ Agent 1: 维度1分析                               │
│   LLM: [GLM-5.2 ▾]  [token: 预估 2K]            │
│ Agent 2: 维度2分析                               │
│   LLM: [DeepSeek-V4-Flash ▾]  [token: 预估 2K]  │
│ Agent 3: 维度3分析                               │
│   LLM: [Qwen3-80B ▾]  [token: 预估 3K]          │
│ 汇总 Agent: 综合报告                             │
│   LLM: [GLM-5.2 ▾]  [token: 预估 4K]            │
│                                                 │
│ 预算总计: ~11K tokens                           │
│ [确认配置]  [使用默认]                           │
└─────────────────────────────────────────────────┘
```

### 4.2 实现方式

- 选多 Agent 模式时，先弹 ModelAssignmentPanel
- 从后端拉取可用模型列表（providers 列表）
- 每个 Agent 节点默认使用 active provider，用户可单独切换
- 确认后，节点数据里写入 `model: "model_name"` 字段
- 执行时 LLMNode 读取 `data.model` 覆盖默认模型