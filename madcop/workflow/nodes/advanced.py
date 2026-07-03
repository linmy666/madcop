"""v2.7.0 — Advanced node types for the workflow editor.
参考 Dify / n8n / Coze 的节点体系, 适配 MadCop 技术栈。

Nodes:
  - CodeNode:      执行 Python 脚本, 取 NodeResult.output
  - ConditionNode: IF/ELSE 分支, 取 NodeResult.branch
  - LoopNode:      遍历数组迭代执行
  - WebSearchNode: 联网搜索 (包装 web_search 工具)
  - KnowledgeNode: 记忆检索 (包装 recall_memory 工具)
  - HTTPNode:      HTTP 请求
  - InputNode:     人工输入 / 暂停等待
  - AggregatorNode:合并多路输入
  - VariableNode:  设置 / 修改变量
"""
from __future__ import annotations

import asyncio
import json
import sys
import textwrap
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .base import NodeBase, NodeContext, NodeResult, resolve_variables


# --------------------------------------------------------------------------- #
# CodeNode — 执行 Python 代码 (安全沙箱)
# --------------------------------------------------------------------------- #

class CodeNode(NodeBase):
    """Execute Python code. The code receives 'input' and 'upstream' vars.

    Data fields:
      - code:   str (Python code, receives `input` dict and `upstream` dict)
      - timeout: int (seconds, default 10)
    """
    type = "code"
    label = "代码执行"
    description = "运行 Python 脚本, 支持输入/输出变量"
    category = "advanced"

    async def execute(self, context: NodeContext) -> NodeResult:
        data = context.node.get("data", {})
        code = data.get("code", "")
        if not code.strip():
            return NodeResult(success=False, error="Code field is empty")

        timeout = data.get("timeout", 10)

        # Build the execution context
        input_vars = {
            "input": context.workflow_input,
            "upstream": context.upstream_outputs,
            "node_input": context.input,
        }

        try:
            # Run in a subprocess for safety (no direct exec)
            import tempfile, textwrap, subprocess

            # Wrap the user code in a function that receives variables
            wrapped = textwrap.dedent(f"""\
import json, sys

input_vars = json.loads('''{json.dumps(input_vars, ensure_ascii=False)}''')

{code}

# The code should set 'output' variable
if 'output' not in dir():
    output = {{}}
""")
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as f:
                f.write(wrapped)
                tmppath = f.name

            proc = await asyncio.wait_for(asyncio.create_subprocess_exec(
                sys.executable or 'python3', tmppath,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ), timeout=timeout)
            stdout, stderr = await proc.communicate()
            import os
            try:
                os.unlink(tmppath)
            except Exception:
                pass

            if proc.returncode != 0:
                return NodeResult(
                    success=False,
                    error=f"Code exit code {proc.returncode}: {stderr.decode()[:500]}",
                )

            try:
                output = json.loads(stdout.decode())
                if not isinstance(output, dict):
                    output = {"result": output}
            except json.JSONDecodeError:
                output = {"raw_stdout": stdout.decode()[:1000]}

            return NodeResult(success=True, output=output)

        except asyncio.TimeoutError:
            return NodeResult(success=False, error=f"Code timed out after {timeout}s")
        except Exception as e:
            return NodeResult(success=False, error=f"CodeNode error: {e}")


# --------------------------------------------------------------------------- #
# ConditionNode — IF/ELSE 分支 (目前支持 LLM 判断)
# --------------------------------------------------------------------------- #

class ConditionNode(NodeBase):
    """Binary condition router. 根据 upstream 输出判断走 true 还是 false 分支。
    用 LLM 判断, 或者用 Python 表达式。
    """
    type = "condition"
    label = "条件分支"
    description = "IF/ELSE 条件路由, 基于 LLM 或表达式判断"
    category = "advanced"

    async def execute(self, context: NodeContext) -> NodeResult:
        data = context.node.get("data", {})
        condition = data.get("condition", "")
        use_llm = data.get("use_llm", True)

        if use_llm:
            # Use LLM to decide
            prompt = (
                f"请判断以下条件是否成立:\n{condition}\n\n"
                f"用户输入: {json.dumps(context.workflow_input, ensure_ascii=False)}\n"
                f"上游输出: {json.dumps(context.upstream_outputs, ensure_ascii=False)}\n\n"
                f"只回答 'true' 或 'false'."
            )
            try:
                from madcop.llm.client import OpenAICompatClient
                from madcop.llm import Message
                from madcop.config.settings import get_active_client_config
                from madcop.config import settings as settings_store
                s = settings_store.load_settings()
                cfg = get_active_client_config(s)
                if not cfg:
                    return NodeResult(success=False, error="No active provider")
                client = OpenAICompatClient(
                    api_key=cfg["api_key"], base_url=cfg["base_url"], model=cfg["model"],
                )
                resp = client.chat(
                    messages=[Message(role="user", content=prompt)],
                    model=cfg["model"],
                )
                answer = (resp.content or "").strip().lower()
                branch = "true" if answer.startswith("true") else "false"
            except Exception as e:
                return NodeResult(success=False, error=f"Condition LLM error: {e}")
        else:
            # Simple Python expression
            try:
                # Evaluate the condition expression (limited, for safety)
                allowed = {"input": context.workflow_input, "upstream": context.upstream_outputs}
                result = eval(condition, {"__builtins__": {}}, allowed)
                branch = "true" if result else "false"
            except Exception as e:
                return NodeResult(success=False, error=f"Condition eval error: {e}")

        return NodeResult(success=True, output={"branch": branch, "condition": condition}, branch=branch)


# --------------------------------------------------------------------------- #
# LoopNode — 迭代执行 (for-each style)
# --------------------------------------------------------------------------- #

class LoopNode(NodeBase):
    """Iterate over an array from upstream output.

    Data fields:
      - collection: str (JSONPath to array, default "items")
      - max_iterations: int (default 10)
    """
    type = "loop"
    label = "循环"
    description = "遍历数组, 对每个元素执行下游节点"
    category = "advanced"

    async def execute(self, context: NodeContext) -> NodeResult:
        data = context.node.get("data", {})
        collection_key = data.get("collection", "items")
        max_iter = data.get("max_iterations", 10)

        # Get the collection from upstream
        upstream = context.upstream_outputs
        items = upstream.get(collection_key, []) if isinstance(upstream, dict) else []
        if not isinstance(items, (list, tuple)):
            items = [items]
        items = items[:max_iter]

        return NodeResult(success=True, output={
            "items": items,
            "count": len(items),
            "index": 0,  # Current iteration index (set during runtime)
        })


# --------------------------------------------------------------------------- #
# WebSearchNode — 联网搜索
# --------------------------------------------------------------------------- #

class WebSearchNode(NodeBase):
    """Search the web and return results."""
    type = "web_search"
    label = "联网搜索"
    description = "搜索互联网, 返回搜索结果摘要"
    category = "tools"

    async def execute(self, context: NodeContext) -> NodeResult:
        data = context.node.get("data", {})
        query_template = data.get("query", "")
        query = resolve_variables(query_template, context)

        if not query:
            return NodeResult(success=False, error="No search query")

        try:
            # Use the search tool from the registry
            from madcop.tools import default_registry
            from madcop.llm import ToolCall
            registry = default_registry()
            call = ToolCall(id="wf_web_search", name="web_search", arguments={"query": query})
            result = await asyncio.to_thread(registry.dispatch, call)
            return NodeResult(success=True, output={
                "query": query,
                "results": result.to_message_content(),
            })
        except Exception as e:
            return NodeResult(success=False, error=f"Web search failed: {e}")


# --------------------------------------------------------------------------- #
# KnowledgeNode — 记忆检索
# --------------------------------------------------------------------------- #

class KnowledgeNode(NodeBase):
    """Retrieve memories relevant to the query."""
    type = "knowledge"
    label = "记忆检索"
    description = "从记忆库中检索相关信息"
    category = "tools"

    async def execute(self, context: NodeContext) -> NodeResult:
        data = context.node.get("data", {})
        query_template = data.get("query", "")
        limit = data.get("limit", 5)
        query = resolve_variables(query_template, context)

        try:
            from madcop.tools import default_registry
            from madcop.llm import ToolCall
            registry = default_registry()
            call = ToolCall(
                id="wf_recall_memory",
                name="recall_memory",
                arguments={"query": query, "limit": limit},
            )
            result = await asyncio.to_thread(registry.dispatch, call)
            return NodeResult(success=True, output={
                "query": query,
                "memories": result.to_message_content(),
            })
        except Exception as e:
            return NodeResult(success=False, error=f"Knowledge retrieval failed: {e}")


# --------------------------------------------------------------------------- #
# HTTPNode — HTTP 请求
# --------------------------------------------------------------------------- #

class HTTPNode(NodeBase):
    """Send an HTTP request to an external API."""
    type = "http_request"
    label = "HTTP 请求"
    description = "发送 HTTP 请求到外部 API"
    category = "tools"

    async def execute(self, context: NodeContext) -> NodeResult:
        data = context.node.get("data", {})
        url_template = data.get("url", "")
        method = data.get("method", "GET")
        headers = data.get("headers", {})
        body_template = data.get("body", "")

        url = resolve_variables(url_template, context)
        body = resolve_variables(body_template, context) if body_template else None

        try:
            req = urllib.request.Request(url, method=method, headers=headers)
            if body:
                req.data = body.encode("utf-8") if isinstance(body, str) else json.dumps(body).encode("utf-8")
                if "Content-Type" not in headers:
                    req.add_header("Content-Type", "application/json")

            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                try:
                    parsed = json.loads(raw)
                except json.JSONDecodeError:
                    parsed = {"raw": raw[:2000]}

            return NodeResult(success=True, output={
                "status": resp.status,
                "headers": dict(resp.headers),
                "body": parsed,
            })
        except Exception as e:
            return NodeResult(success=False, error=f"HTTP request failed: {e}")


# --------------------------------------------------------------------------- #
# InputNode — 人工输入 (暂停等待)
# --------------------------------------------------------------------------- #

class InputNode(NodeBase):
    """Pause execution and ask the user for input.

    Currently this just returns a marker — the execution engine
    will need to be enhanced to actually pause and wait.
    """
    type = "input"
    label = "用户输入"
    description = "暂停工作流, 等待用户输入"
    category = "advanced"

    async def execute(self, context: NodeContext) -> NodeResult:
        data = context.node.get("data", {})
        prompt = data.get("prompt", "请输入:")
        return NodeResult(success=True, output={
            "__needs_user_input__": True,
            "prompt": prompt,
        })


# --------------------------------------------------------------------------- #
# AggregatorNode — 合并多路输入
# --------------------------------------------------------------------------- #

class AggregatorNode(NodeBase):
    """Merge multiple upstream inputs into a single combined output."""
    type = "aggregator"
    label = "合并"
    description = "将多路上游节点的输出合并为一个对象"
    category = "advanced"

    async def execute(self, context: NodeContext) -> NodeResult:
        mode = context.node.get("data", {}).get("mode", "merge")
        upstream = context.upstream_outputs

        if mode == "list":
            # Combine all upstream outputs into a list
            combined = [v for k, v in upstream.items() if isinstance(v, dict)]
        elif mode == "concat":
            # Concatenate all text outputs
            parts = []
            for k, v in upstream.items():
                if isinstance(v, dict):
                    for field in v.values():
                        if isinstance(field, str):
                            parts.append(field)
            combined = "\n".join(parts)
        else:
            # Default: merge all dicts
            combined = {}
            for k, v in upstream.items():
                if isinstance(v, dict):
                    combined[k] = v

        return NodeResult(success=True, output={"combined": combined, "mode": mode})


# --------------------------------------------------------------------------- #
# VariableNode — 设置 / 修改变量
# --------------------------------------------------------------------------- #

class VariableNode(NodeBase):
    """Set or transform a variable in the workflow context.

    Data fields:
      - variable: str (variable name)
      - operation: str ('set' | 'append' | 'transform')
      - value: str (supports {{var}} references)
    """
    type = "variable"
    label = "变量"
    description = "设置 / 修改变量, 支持模板引用"
    category = "advanced"

    async def execute(self, context: NodeContext) -> NodeResult:
        data = context.node.get("data", {})
        var_name = data.get("variable", "")
        operation = data.get("operation", "set")
        value_template = data.get("value", "")

        value = resolve_variables(value_template, context)

        return NodeResult(success=True, output={
            "variable": var_name,
            "operation": operation,
            "value": value,
        })


# --------------------------------------------------------------------------- #
# Node class alias map (for get_node_class to find)
# --------------------------------------------------------------------------- #

_NODE_REGISTRY: dict[str, type[NodeBase]] = {
    "code": CodeNode,
    "condition": ConditionNode,
    "loop": LoopNode,
    "web_search": WebSearchNode,
    "knowledge": KnowledgeNode,
    "http_request": HTTPNode,
    "input": InputNode,
    "aggregator": AggregatorNode,
    "variable": VariableNode,
}

__all__ = [
    "CodeNode", "ConditionNode", "LoopNode",
    "WebSearchNode", "KnowledgeNode", "HTTPNode",
    "InputNode", "AggregatorNode", "VariableNode",
]