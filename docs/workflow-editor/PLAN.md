# MadCop 工作流编排器 — 实施规划 (v2.7.0)

> 用户目标: 把 MadCop 从 "聊天 Agent 平台" 升级为 "可视化工作流编排平台",
> 抄 AutoGen Studio + Dify 的设计, 适配 MadCop 现有的 Python/FastAPI/SQLite 技术栈。

---

## 1. 范围 (Scope)

### 1.1 核心节点类型 (Phase 1+2)

| 节点 | 类型 | 描述 |
|---|---|---|
| **开始节点** | trigger | 工作流起点, 接收 user input |
| **结束节点** | end | 工作流终点, 输出最终结果 |
| **LLM 节点** | llm | 调用 LLM (复用现有 chat infrastructure) |
| **工具节点** | tool | 调用 madcop/tools/registry 里的工具 (weather / recall_memory / bash 等) |
| **代码节点** | code | 执行 Python 或 JS 脚本 (Monaco editor) |
| **MCP 节点** | mcp | 调用任何 MCP server 工具 |
| **条件分支** | if_else | if/else 路由, LLM-decision 或表达式 |
| **循环** | loop | for-each 节点迭代 |
| **子工作流** | subworkflow | 嵌套调用另一个工作流 |
| **并行分支** | parallel | fan-out / fan-in |
| **多 Agent 团队** | team | AutoGen-style 角色编排 (researcher / coder / reviewer) |

### 1.2 变量 / 状态

- **节点输入**: 引用上游节点的输出 `{{node_id.output}}`
- **节点输出**: JSON 对象, 任意 schema
- **工作流输入**: 从 chat session / API / schedule trigger
- **工作流输出**: 返回到 chat session / webhook / database

### 1.3 编辑器能力

- 拖拽节点 + 连线 (React Flow)
- 节点配置面板 (右侧 drawer)
- 实时状态 (运行中高亮当前节点)
- 撤销/重做
- 复制/粘贴
- 导入/导出 JSON
- 版本历史

### 1.4 执行引擎

- **DAG 调度器**: topological sort, 并行节点用 asyncio.gather
- **状态管理**: 每个工作流运行有 unique run_id, 状态持久化到 SQLite
- **断点恢复**: 工作流运行可暂停 / 恢复
- **超时控制**: 每个节点可设 timeout
- **错误处理**: 节点失败可 retry / skip / fail-fast / fallback

---

## 2. 架构

### 2.1 数据模型 (SQLite)

```sql
-- 工作流定义
CREATE TABLE workflows (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  version INTEGER DEFAULT 1,
  nodes_json TEXT NOT NULL,    -- JSON 数组, 每个节点
  edges_json TEXT NOT NULL,    -- JSON 数组, 每条边
  variables_json TEXT,         -- 工作流输入变量定义
  created_at TIMESTAMP,
  updated_at TIMESTAMP
);

-- 工作流运行实例
CREATE TABLE workflow_runs (
  id TEXT PRIMARY KEY,
  workflow_id TEXT REFERENCES workflows(id),
  status TEXT,                  -- pending / running / paused / completed / failed
  input_json TEXT,
  output_json TEXT,
  current_node_ids TEXT,        -- JSON 数组, 正在执行的节点
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  error TEXT
);

-- 节点运行历史
CREATE TABLE workflow_node_runs (
  id TEXT PRIMARY KEY,
  run_id TEXT REFERENCES workflow_runs(id),
  node_id TEXT,                  -- 节点在工作流中的 ID (不是 SQL id)
  status TEXT,                   -- pending / running / success / failed / skipped
  input_json TEXT,
  output_json TEXT,
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  duration_ms INTEGER,
  error TEXT
);
```

### 2.2 后端架构 (Python/FastAPI)

```
madcop/workflow/
├── __init__.py
├── engine.py           # DAG 调度器
├── executor.py         # 单个节点的执行 (调 LLM / 调工具 / 跑代码)
├── nodes/
│   ├── base.py         # Node 基类
│   ├── llm.py          # LLM 节点
│   ├── tool.py         # 工具节点
│   ├── code.py         # 代码节点 (Python 沙箱)
│   ├── mcp.py          # MCP 节点
│   ├── if_else.py      # 条件分支
│   ├── loop.py         # 循环
│   ├── subworkflow.py  # 子工作流
│   ├── parallel.py     # 并行
│   └── team.py         # 多 Agent 团队
├── persistence.py     # SQLite CRUD
├── api.py              # FastAPI router (/api/workflows, /api/workflows/{id}/run)
├── importer.py        # 导入 / 导出 JSON
└── runtime.py          # 状态机, 断点恢复
```

### 2.3 前端架构 (React/Vite/Electron)

```
desktop/src/components/workflow/
├── WorkflowEditor.tsx       # 主画布 (抄 AutoGen builder.tsx)
├── ComponentLibrary.tsx     # 左侧节点库
├── NodeConfigPanel.tsx      # 右侧节点配置 drawer
├── nodes/
│   ├── BaseNode.tsx         # 节点基类
│   ├── LLMNode.tsx
│   ├── ToolNode.tsx
│   ├── CodeNode.tsx          # Monaco editor
│   ├── IfElseNode.tsx
│   ├── LoopNode.tsx
│   ├── TeamNode.tsx
│   └── ...
├── edges/
│   └── CustomEdge.tsx        # 边 (label / 条件分支的 yes/no)
├── ExecutionPanel.tsx       # 底部运行状态面板
├── toolbar.tsx
├── store.tsx                 # zustand store
└── types.ts                  # 节点 / 边 / 变量类型

desktop/src/api/workflow.ts   # workflow CRUD API client
desktop/src/pages/
├── WorkflowsPage.tsx         # 工作流列表
└── WorkflowEditPage.tsx      # 单个 workflow 编辑器

desktop/src/stores/
└── workflowStore.ts          # 全局 workflow 状态
```

### 2.4 通信

- **HTTP**: 工作流 CRUD 用普通 REST API
- **WebSocket**: 实时运行状态用 WebSocket (复用现有 cc-haha WS)

---

## 3. 实施计划 (4 Phase)

### Phase 1: MVP (3-4 天) — 画布 + 3 节点

**目标**: 能拖拽节点 + 连线 + 运行最简单的 LLM 链路

**Day 1**: 装依赖, 抄 AutoGen Studio builder.tsx 主结构
- `bun add @xyflow/react @dagrejs/dagre @dnd-kit/core`
- 建 `desktop/src/components/workflow/` 目录
- 抄 builder.tsx 的核心 (useNodesState / useEdgesState / 拖拽)

**Day 2**: 节点类型 + 配置
- 3 个节点: StartNode / LLMNode / EndNode
- 节点配置面板 (右侧 drawer)
- 边的样式 (实线箭头)

**Day 3**: 工作流定义 + 持久化
- 后端: `madcop/workflow/persistence.py` + API
- 前端: 工作流列表页 + 详情页

**Day 4**: 运行 + 测试
- 后端: 简单的顺序执行器 (DAG 还没做, 先 linear)
- 实时状态推送到前端
- 完整跑通: 用户拖一个 Start → LLM → End 工作流, 输入问题, 输出 LLM 答案

### Phase 2: 工具节点 + 实时执行 (1 周)

- 后端: 完整 DAG 调度器
- 节点: Tool / Code / MCP
- 实时状态: 当前节点高亮 + 节点状态徽章
- 变量引用: `{{node_id.output}}` 解析
- 运行历史: workflow_runs / workflow_node_runs 表

### Phase 3: 多 Agent 团队 + 条件分支 (1 周)

- 节点: Team (AutoGen-style) / IfElse / Loop / Subworkflow
- Agent 角色模板: researcher / coder / reviewer / planner
- 团队编排: 多 agent 对话 + 角色路由

### Phase 4: 高级特性 (持续)

- 版本历史
- 模板市场 (Gallery)
- 导入 / 导出 JSON
- Webhook trigger
- 定时 trigger
- 多人协作 (本地 SQLite 不支持, 可选云端)

---

## 4. 抄 AutoGen Studio 的具体清单

### 4.1 节点架构

- `nodeTypes` (dict) — 节点类型注册表
- 每种节点一个 React component, 接受 `data` prop (节点配置 JSON)
- `BaseNode.tsx` 统一所有节点的框架 (header / body / output handles)

### 4.2 执行器架构

- 节点执行接受 `context` 对象 (含所有上游节点的输出)
- 返回 `NodeResult { success, output, error }`
- DAG 调度器:
  1. topological sort
  2. 按层执行 (同层并行)
  3. 每节点完成后通知 WebSocket
  4. 失败时根据 error policy 处理

### 4.3 状态管理

- `workflowStore` (zustand) 持有:
  - 当前编辑的 workflow (nodes / edges)
  - 当前选中的节点
  - undo / redo 栈
  - dirty flag
- 后端 SQLite 持久化

---

## 5. 风险评估

| 风险 | 严重度 | 缓解 |
|---|---|---|
| React Flow + Electron 兼容 | 中 | React Flow 12 已支持 Electron, 测试后再用 |
| 节点执行超时 (LLM 长任务) | 中 | 节点 timeout 配置 + 异步 progress |
| DAG 死循环 (Loop 节点) | 中 | 最大迭代次数限制 |
| 工作流 JSON schema 演进 | 低 | 加 version 字段, 老 workflow 自动 migrate |
| Monaco editor 体积大 | 低 | 按需 lazy load |

---

## 6. 不在范围

- ❌ 多用户协作 (云端同步) — Phase 4+
- ❌ 工作流模板市场 — Phase 4
- ❌ 复杂权限系统 — 单一用户本地用
- ❌ 复杂 retry 策略 (指数退避等) — Phase 2+ 简单 retry, 后续
- ❌ 工作流 trigger 库 (webhook / cron / IM) — Phase 4

---

## 7. 验收标准 (Phase 1 MVP)

- [ ] 用户在 UI 里能拖拽 3 个节点 (Start / LLM / End)
- [ ] 用户能连线
- [ ] 用户能配置 LLM 节点的 prompt
- [ ] 用户能保存工作流到 SQLite
- [ ] 用户能加载已保存的工作流
- [ ] 用户能"运行"工作流, 输入问题, 收到 LLM 答案
- [ ] 运行状态实时显示在画布上 (哪个节点在跑)
- [ ] 用户能导出工作流为 JSON
- [ ] 用户能导入 JSON
- [ ] 写一个 e2e test: 创建 → 保存 → 运行 → 验证输出
