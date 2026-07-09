"""v2.8.0 — 12 Agent design patterns as workflow templates.
Based on Google Cloud's "Choose a design pattern for your agentic AI system".
Each mode is a pre-built workflow that can be triggered from chat.
"""
from __future__ import annotations
from typing import Any


def _llm_node(node_id: str, x: int, y: int, label: str, prompt: str, system: str = "",
              model: str = "") -> dict[str, Any]:
    data: dict[str, Any] = {"label": label, "prompt": prompt}
    if system:
        data["system"] = system
    if model:
        data["model"] = model
    return {"id": node_id, "type": "llm", "position": {"x": x, "y": y}, "data": data}


def _start(x: int, y: int) -> dict[str, Any]:
    return {"id": "start", "type": "start", "position": {"x": x, "y": y}, "data": {"label": "开始"}}


def _end(x: int, y: int) -> dict[str, Any]:
    return {"id": "end", "type": "end", "position": {"x": x, "y": y}, "data": {"label": "结束"}}


def _edge(src: str, tgt: str) -> dict[str, Any]:
    return {"id": f"e-{src}-{tgt}", "source": src, "target": tgt}


MODES: dict[str, dict[str, Any]] = {
    # ──────────────────────────────────────────────────────────
    "single_agent": {
        "name": "单 Agent",
        "description": "一个 LLM + 工具调用, 适合大多数任务。这是默认模式。",
        "category": "basic",
        "icon": "⚡",
        "nodes": [
            _start(50, 200),
            _llm_node("llm", 280, 200, "AI 助手", "请回答: {{input}}",
                      "你是专业助手, 可以调用工具。"),
            _end(510, 200),
        ],
        "edges": [_edge("start", "llm"), _edge("llm", "end")],
    },

    # ──────────────────────────────────────────────────────────
    "sequential": {
        "name": "顺序流水线",
        "description": "Agent A → B → C, 每步处理上一步结果。适合数据处理流水线。",
        "category": "multi_agent",
        "icon": "🔗",
        "nodes": [
            _start(50, 200),
            _llm_node("a", 250, 200, "提取数据", "从以下内容提取关键数据:\n{{input}}"),
            _llm_node("b", 480, 200, "清洗格式", "把以下数据整理成标准格式:\n{{a.output.text}}"),
            _llm_node("c", 710, 200, "分析总结", "分析以下数据并给出结论:\n{{b.output.text}}"),
            _end(940, 200),
        ],
        "edges": [_edge("start", "a"), _edge("a", "b"), _edge("b", "c"), _edge("c", "end")],
    },

    # ──────────────────────────────────────────────────────────
    "parallel": {
        "name": "并行分析",
        "description": "多个 Agent 同时分析不同维度, 最后汇总。适合多角度分析。",
        "category": "multi_agent",
        "icon": "🔀",
        "nodes": [
            _start(50, 250),
            _llm_node("dim1", 280, 100, "维度1分析", "从市场角度分析: {{input}}"),
            _llm_node("dim2", 280, 250, "维度2分析", "从技术角度分析: {{input}}"),
            _llm_node("dim3", 280, 400, "维度3分析", "从竞争角度分析: {{input}}"),
            {"id": "agg", "type": "aggregator", "position": {"x": 510, "y": 250},
             "data": {"label": "汇总结果", "mode": "merge"}},
            _llm_node("summary", 740, 250, "综合报告", "基于以下多维度分析, 写一份综合报告:\n{{agg.output.combined}}"),
            _end(970, 250),
        ],
        "edges": [
            _edge("start", "dim1"), _edge("start", "dim2"), _edge("start", "dim3"),
            _edge("dim1", "agg"), _edge("dim2", "agg"), _edge("dim3", "agg"),
            _edge("agg", "summary"), _edge("summary", "end"),
        ],
    },

    # ──────────────────────────────────────────────────────────
    "loop": {
        "name": "循环优化",
        "description": "反复执行直到达到质量标准。适合需要迭代的任务。",
        "category": "advanced",
        "icon": "🔄",
        "nodes": [
            _start(50, 200),
            _llm_node("worker", 280, 200, "执行任务", "完成任务 (第N次尝试):\n{{input}}"),
            _llm_node("checker", 510, 200, "质量检查", "检查以下结果是否达标, 回答true/false:\n{{worker.output.text}}"),
            {"id": "cond", "type": "condition", "position": {"x": 740, "y": 200},
             "data": {"label": "达标?", "condition": "{{checker.output.text}} contains 'true'", "use_llm": False}},
            _end(970, 200),
        ],
        "edges": [
            _edge("start", "worker"), _edge("worker", "checker"), _edge("checker", "cond"),
            {"id": "e-cond-end", "source": "cond", "target": "end", "sourceHandle": "true"},
            {"id": "e-cond-loop", "source": "cond", "target": "worker", "sourceHandle": "false"},
        ],
    },

    # ──────────────────────────────────────────────────────────
    "review_critique": {
        "name": "审核评判",
        "description": "生成器 → 审核器 → 打回重写。适合代码生成、文案审核。",
        "category": "multi_agent",
        "icon": "🔍",
        "nodes": [
            _start(50, 200),
            _llm_node("writer", 280, 200, "生成内容", "请完成以下任务:\n{{input}}",
                      "你是内容生成专家。"),
            _llm_node("reviewer", 510, 200, "审核内容", "审核以下内容是否有问题。如果没有问题回答'true', 有问题指出具体问题:\n{{writer.output.text}}",
                      "你是严格的质量审核专家。"),
            {"id": "cond", "type": "condition", "position": {"x": 740, "y": 200},
             "data": {"label": "通过?", "condition": "{{reviewer.output.text}} contains 'true'", "use_llm": False}},
            _end(970, 200),
        ],
        "edges": [
            _edge("start", "writer"), _edge("writer", "reviewer"), _edge("reviewer", "cond"),
            {"id": "e-cond-end", "source": "cond", "target": "end", "sourceHandle": "true"},
            {"id": "e-cond-loop", "source": "cond", "target": "writer", "sourceHandle": "false"},
        ],
    },

    # ──────────────────────────────────────────────────────────
    "iterative_refine": {
        "name": "迭代精炼",
        "description": "草稿 → 评估 → 修改 → 再评估, 逐步提升质量。",
        "category": "advanced",
        "icon": "✨",
        "nodes": [
            _start(50, 200),
            _llm_node("draft", 250, 200, "写草稿", "写一份草稿:\n{{input}}"),
            _llm_node("evaluate", 480, 200, "评估质量", "给以下内容打分 (0-100) 并指出改进点:\n{{draft.output.text}}"),
            _llm_node("refine", 710, 200, "修改提升", "根据以下评估意见修改原文:\n评估:{{evaluate.output.text}}\n原文:{{draft.output.text}}"),
            _end(940, 200),
        ],
        "edges": [_edge("start", "draft"), _edge("draft", "evaluate"), _edge("evaluate", "refine"), _edge("refine", "end")],
    },

    # ──────────────────────────────────────────────────────────
    "coordinator": {
        "name": "协调器路由",
        "description": "中央 Agent 判断用户意图, 派给专业 Agent。",
        "category": "multi_agent",
        "icon": "🎯",
        "nodes": [
            _start(50, 250),
            _llm_node("coordinator", 250, 250, "意图识别", "分析用户请求, 判断应该交给哪个专家处理。回答 'tech' / 'business' / 'creative':\n{{input}}"),
            {"id": "cond", "type": "condition", "position": {"x": 480, "y": 250},
             "data": {"label": "路由", "condition": "{{coordinator.output.text}}", "use_llm": False}},
            _llm_node("tech", 710, 100, "技术专家", "从技术角度回答:\n{{input}}"),
            _llm_node("business", 710, 250, "商业专家", "从商业角度回答:\n{{input}}"),
            _llm_node("creative", 710, 400, "创意专家", "从创意角度回答:\n{{input}}"),
            _end(940, 250),
        ],
        "edges": [
            _edge("start", "coordinator"), _edge("coordinator", "cond"),
            {"id": "e1", "source": "cond", "target": "tech", "sourceHandle": "tech"},
            {"id": "e2", "source": "cond", "target": "business", "sourceHandle": "business"},
            {"id": "e3", "source": "cond", "target": "creative", "sourceHandle": "creative"},
            _edge("tech", "end"), _edge("business", "end"), _edge("creative", "end"),
        ],
    },

    # ──────────────────────────────────────────────────────────
    "hierarchical": {
        "name": "分层分解",
        "description": "根 Agent 拆任务 → 中层 Agent 再拆 → 底层执行。",
        "category": "advanced",
        "icon": "🏗️",
        "nodes": [
            _start(50, 300),
            _llm_node("root", 250, 300, "任务拆解", "把以下任务拆成2个子任务, 输出JSON数组:\n{{input}}"),
            _llm_node("mgr_a", 480, 200, "子任务A", "执行子任务A:\n{{root.output.text}}"),
            _llm_node("mgr_b", 480, 400, "子任务B", "执行子任务B:\n{{root.output.text}}"),
            {"id": "agg", "type": "aggregator", "position": {"x": 710, "y": 300},
             "data": {"label": "合并", "mode": "merge"}},
            _llm_node("final", 940, 300, "整合输出", "整合以下两部分结果:\n{{agg.output.combined}}"),
            _end(1170, 300),
        ],
        "edges": [
            _edge("start", "root"), _edge("root", "mgr_a"), _edge("root", "mgr_b"),
            _edge("mgr_a", "agg"), _edge("mgr_b", "agg"),
            _edge("agg", "final"), _edge("final", "end"),
        ],
    },

    # ──────────────────────────────────────────────────────────
    "swarm": {
        "name": "群智协作",
        "description": "多专家自由讨论, 互相补充, 最后汇总。适合产品设计等创意任务。",
        "category": "advanced",
        "icon": "🐝",
        "nodes": [
            _start(50, 300),
            _llm_node("expert_a", 280, 100, "市场专家", "从市场角度发表观点:\n{{input}}",
                      "你是市场分析专家, 请发表专业观点。"),
            _llm_node("expert_b", 280, 300, "技术专家", "从技术角度发表观点:\n{{input}}",
                      "你是技术架构专家, 请发表专业观点。"),
            _llm_node("expert_c", 280, 500, "财务专家", "从财务角度发表观点:\n{{input}}",
                      "你是财务建模专家, 请发表专业观点。"),
            {"id": "agg", "type": "aggregator", "position": {"x": 510, "y": 300},
             "data": {"label": "收集观点", "mode": "merge"}},
            _llm_node("debate", 740, 300, "交叉讨论",
                      "以下是三位专家的观点。请模拟一轮交叉讨论, 让他们互相补充和挑战:\n{{agg.output.combined}}",
                      "你是讨论主持人。"),
            _llm_node("synthesis", 970, 300, "综合方案",
                      "基于以下讨论, 给出最终综合方案:\n{{debate.output.text}}"),
            _end(1200, 300),
        ],
        "edges": [
            _edge("start", "expert_a"), _edge("start", "expert_b"), _edge("start", "expert_c"),
            _edge("expert_a", "agg"), _edge("expert_b", "agg"), _edge("expert_c", "agg"),
            _edge("agg", "debate"), _edge("debate", "synthesis"), _edge("synthesis", "end"),
        ],
    },

    # ──────────────────────────────────────────────────────────
    "react": {
        "name": "ReAct 推理",
        "description": "边想边做边看, 动态调整。当前默认聊天模式。",
        "category": "basic",
        "icon": "🧠",
        "nodes": [
            _start(50, 200),
            _llm_node("thinker", 280, 200, "思考+行动",
                      "请完成以下任务。你可以调用工具(web_search/get_weather等):\n{{input}}",
                      "使用 ReAct 模式: Thought → Action → Observation → 循环。"),
            _end(510, 200),
        ],
        "edges": [_edge("start", "thinker"), _edge("thinker", "end")],
    },

    # ──────────────────────────────────────────────────────────
    "human_in_loop": {
        "name": "人工审核",
        "description": "AI 生成 → 暂停等人审核 → 通过则继续。",
        "category": "advanced",
        "icon": "👤",
        "nodes": [
            _start(50, 200),
            _llm_node("generator", 250, 200, "AI 生成", "完成以下任务:\n{{input}}"),
            {"id": "review_input", "type": "input", "position": {"x": 480, "y": 200},
             "data": {"label": "等待人工审核", "prompt": "请审核以上内容, 输入'通过'或修改意见:"}},
            {"id": "cond", "type": "condition", "position": {"x": 710, "y": 200},
             "data": {"label": "通过?", "condition": "{{review_input.output.result}} contains '通过'", "use_llm": False}},
            _end(940, 200),
        ],
        "edges": [
            _edge("start", "generator"), _edge("generator", "review_input"),
            _edge("review_input", "cond"),
            {"id": "e-pass", "source": "cond", "target": "end", "sourceHandle": "true"},
            {"id": "e-fail", "source": "cond", "target": "generator", "sourceHandle": "false"},
        ],
    },

    # ──────────────────────────────────────────────────────────
    "custom": {
        "name": "自定义逻辑",
        "description": "用 Python 代码控制流程, 最灵活但也最复杂。",
        "category": "advanced",
        "icon": "🔧",
        "nodes": [
            _start(50, 200),
            {"id": "code", "type": "code", "position": {"x": 250, "y": 200},
             "data": {"label": "Python 逻辑",
                      "code": "# 接收 input 和 upstream 变量\n# 设置 output 变量为结果\noutput = {\"processed\": input}}"}},
            _llm_node("llm", 480, 200, "LLM 处理", "处理以下数据:\n{{code.output.processed}}"),
            _end(710, 200),
        ],
        "edges": [_edge("start", "code"), _edge("code", "llm"), _edge("llm", "end")],
    },
}


def list_modes() -> list[dict[str, Any]]:
    # Min number of distinct model providers required for each mode.
    # Single-agent modes can run on 1 model. Multi-agent modes need multiple.
    requires: dict[str, int] = {
        "single_agent": 1,
        "sequential": 2,
        "parallel": 2,
        "loop": 1,
        "review_critique": 2,
        "iterative_refine": 1,
        "coordinator": 2,
        "hierarchical": 3,
        "swarm": 3,
        "react": 1,
        "human_in_loop": 1,
    }
    out = []
    for mid, mode in MODES.items():
        out.append({
            "id": mid,
            "name": mode["name"],
            "description": mode["description"],
            "category": mode["category"],
            "icon": mode["icon"],
            "node_count": len(mode["nodes"]),
            "requires_models": requires.get(mid, 1),
        })
    return out


def get_mode(mode_id: str) -> dict[str, Any] | None:
    if mode_id not in MODES:
        return None
    return {"id": mode_id, **MODES[mode_id]}


__all__ = ["MODES", "list_modes", "get_mode"]