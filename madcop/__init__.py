"""madcop: a local-first AI agent framework.

madcop is a personal AI agent for your terminal. You point it at a
goal, it walks that goal through a middleware-driven plan-execute-replan
loop, dispatches to specialised sub-agents when it helps, and writes
what it learned to a local memory store. Next time you ask a similar
question, it already knows.

v1.0.0-rc.1 introduces the middleware chain — a Qian-control-theory
inspired extension point that lets you observe, mutate, and halt
plan-execute runs at well-defined hook points. The included
QianControlMiddleware enforces the design invariants (closed-loop
feedback, early correction, controllability) that every other
middleware should follow.

Public API (stable as of v1.0.0):
- madcop.agent: PlanExecuteLoop + middleware chain + sub-agents
- madcop.strategy: scratchpad, WAL, cost tracking, model router
- madcop.llm: OpenAI-compatible chat client (real + mock)
- madcop.tools: Tool registry, EchoTool, GetTimeTool, FunctionTool
- madcop.memory: 4-layer working/episodic/semantic/reflective memory
- madcop.doctor: self-check CLI (`python -m madcop doctor`)
- madcop.run_* (CLI subcommands): run, plan, replay, decisions, eval,
  skill, config, doctor, resume

Install:
    pip install madcop

Quick start:
    from madcop import __version__
    print(__version__)
    # -> 1.0.0rc1

    from madcop.agent.middleware import (
        MiddlewareChain, QianControlMiddleware, LoggingMiddleware,
    )
    chain = MiddlewareChain([LoggingMiddleware(), QianControlMiddleware()])
"""
from __future__ import annotations

__version__ = "1.0.0rc1"

# Public API surface. Listed here as a stability signal — anything
# not in this list may change between minor versions.
__all__ = [
    "__version__",
    # Agent layer
    "agent",
    "memory",
    # Strategy layer
    "strategy",
    # LLM + tools
    "llm",
    "tools",
    # CLI
    "doctor",
]
