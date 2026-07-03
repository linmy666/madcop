# MadCop 工作流模式设计 (v2.8.0)

> 用户需求：
> 1. 把 Google 12 种 Agent 设计模式全部编排成工作流模板
> 2. 模板可以在聊天里直接选择使用
> 3. 不同节点可以选不同的 LLM 模型
> 4. 生成的图表可以保存到本地
> 5. 表格渲染优化

---

## 1. 数据模型

### 1.1 模式 (Mode)
模式 = 工作流模板 + 描述 + 触发方式

```python
Mode {
    id: str               # "single_agent", "sequential", ...
    name: str             # "单 Agent 模式"
    description: str      # 用户可见的描述
    category: str         # "basic" / "multi_agent" / "advanced"
    icon: str             # emoji
    nodes: list           # React Flow nodes
    edges: list           # React Flow edges
    variables: dict       # 模式默认变量
    triggers: list[str]   # ["chat", "workflow_editor"]
}
```

### 1.2 节点模型增强
每个 LLM 节点可以选择不同的模型：

```python
LLMNode.data = {
    "prompt": str,
    "system": str,
    "model": str | null,     # null = 使用当前 active provider
    "provider": str | null,  # "sensenova" / "nvidia" / 自定义
    "temperature": float,    # 0.0-1.0
    "max_tokens": int,       # 输出长度限制
}
```

---

## 2. 12 种模式编排

### 模式 1: 单 Agent (Single Agent)
**节点**: Start → LLM (调工具) → End
**触发**: 默认聊天模式
**已有**: ✅ 这就是当前的聊天

### 模式 2: 顺序模式 (Sequential Pipeline)
**节点**: Start → LLM_A → LLM_B → LLM_C → End
**用例**: 提取 → 清洗 → 分析
**画布**: 横向 3 个 LLM 节点串联

### 模式 3: 并行模式 (Parallel)
**节点**: Start → [LLM_A, LLM_B, LLM_C] → Aggregator → LLM_Summary → End
**用例**: 多角度分析 (情感 + 关键词 + 分类)

### 模式 4: 循环模式 (Loop)
**节点**: Start → LLM → Condition (达标?) → (No: loop back) / (Yes: End)
**用例**: 反复改进直到满意

### 模式 5: 审核与评判 (Review & Critique)
**节点**: Start → LLM_Generator → LLM_Reviewer → Condition (通过?) → (No: loop to Generator) / (Yes: End)
**用例**: 写代码 + 审代码

### 模式 6: 迭代优化 (Iterative Refinement)
**节点**: Start → LLM_Draft → LLM_Evaluate → Condition (达标?) → (No: LLM_Refine → loop) / (Yes: End)
**用例**: 写文章，反复打磨

### 模式 7: 协调器 (Coordinator)
**节点**: Start → LLM_Coordinator → Condition (路由判断) → [LLM_A, LLM_B, LLM_C] → End
**用例**: 智能客服路由

### 模式 8: 分层任务分解 (Hierarchical)
**节点**: Start → LLM_Root → [LLM_Manager_A, LLM_Manager_B] → [LLM_Worker_1..4] → Aggregator → End
**用例**: 复杂项目管理

### 模式 9: Swarm (群智协作)
**节点**: Start → [LLM_Expert_A ↔ LLM_Expert_B ↔ LLM_Expert_C] → Aggregator → LLM_Synthesizer → End
**新增**: 双向连线 + 最大辩论轮次
**用例**: 产品设计讨论

### 模式 10: ReAct (边想边做)
**节点**: Start → LLM (with tools) → Loop (Thought → Action → Observation) → End
**已有**: ✅ 当前聊天就是这个模式

### 模式 11: Human-in-the-Loop (人工审核)
**节点**: Start → LLM → InputNode (暂停等人审核) → Condition (通过?) → End
**已有**: ✅ ask_user 工具 + ClarificationPanel

### 模式 12: 自定义逻辑 (Custom)
**节点**: Start → CodeNode → LLM → End
**用例**: 用户自己写 Python 逻辑控制流程

---

## 3. 前端交互

### 3.1 聊天里选模式
在 ChatInput 旁边加一个"模式选择器"下拉菜单：
```
[⚡ 默认(ReAct)]  [输入框]  [运行]
```
点击下拉显示 12 种模式列表，选一个就切换。

### 3.2 图表保存
Mermaid 图表右上角加一个"保存"按钮：
- 保存为 PNG (SVG → Canvas → toBlob → download)
- 保存为 .mmd 文件 (Mermaid 源码)

### 3.3 LLM 节点模型选择
LLM 节点配置面板加一个下拉：
```
模型: [使用默认 ▾]
       ┌──────────────────────┐
       │ 使用默认 (GLM-5.2)    │
       │ GLM-5.2              │
       │ DeepSeek-V4-Flash    │
       │ Qwen3-80B (NVIDIA)   │
       │ Sensenova-6.7-Lite   │
       └──────────────────────┘
```

---

## 4. 后端 API

### 4.1 模式管理
```
GET    /api/workflows/modes          → 列出所有模式
GET    /api/workflows/modes/{id}     → 获取模式详情
POST   /api/workflows/modes/{id}/run → 在聊天里运行模式
```

### 4.2 聊天里用模式
WebSocket 新增消息类型：
```json
{
  "type": "user_message",
  "content": "帮我分析快递行业",
  "mode": "parallel_bi"  // 可选，不填就是默认 ReAct
}
```

---

## 5. 实施计划

### Phase A (今天)
1. ✅ 后端: 12 种模式模板定义
2. ✅ 后端: /api/workflows/modes API
3. ✅ 前端: Mermaid 图表保存按钮
4. ✅ 前端: 表格渲染优化

### Phase B (1-2 天)
5. 前端: 聊天里的模式选择器
6. 后端: WebSocket 支持按模式执行
7. 前端: LLM 节点模型选择器

### Phase C (持续)
8. Swarm 模式的双向通信
9. 模式自定义 (用户自己编排保存为模式)
10. 模式分享 / 导入导出