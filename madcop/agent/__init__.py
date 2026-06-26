"""L5 — LangGraph orchestration + v0.6.0 plan-execute loop + v0.7.0 sub-agent
+ v1.0.0 middleware chain + v1.2.0 tracing.

Public surface:
  v0.5.0 (linear graph):  `MadcopState`, `build_graph`, `run_agent`
  v0.6.0 (free-form loop): `PlanExecuteLoop`, `Plan`, `PlanStep`,
                            `StepExecutor`, `Planner`, `ExecutionMode`,
                            `TrivialPlanner`, `FnStepExecutor`
  v0.7.2 (routing):       `RoutingStepExecutor`
  v1.0.0 (middleware):    `MiddlewareChain`, `HookContext`, `Directive`,
                            `QianControlMiddleware`, `TodoMiddleware`,
                            `LoopDetectionMiddleware`,
                            `ClarificationMiddleware`
  v1.2.0 (tracing):       `Tracer`, `TraceMiddleware`, `read_traces`,
                            `print_summary`
"""
from __future__ import annotations

from .graph import MadcopState, build_graph, run_agent
from .plan_execute import (
    ExecutionMode,
    Plan,
    PlanExecuteConfig,
    PlanExecuteLoop,
    PlanExecuteResult,
    Planner,
    PlanStep,
    StepExecutor,
    StepOutcome,
    TrivialPlanner,
    FnStepExecutor,
)
from .routing_executor import RoutingStepExecutor
from .middleware import (
    ALL_HOOKS,
    Directive,
    HookContext,
    LoggingMiddleware,
    MiddlewareChain,
    MiddlewareHalt,
    QianControlMiddleware,
    apply_directives,
    HOOK_PLAN_END,
    HOOK_PLAN_START,
    HOOK_REPLAN,
    HOOK_STEP_END,
    HOOK_STEP_START,
)
from .clarification import ClarificationMiddleware, ClarificationRequested
from .loop_detection import LoopDetectionMiddleware
from .todo_middleware import TodoMiddleware, TodoPlan, TodoStep
from .tracing import Tracer, TraceMiddleware, print_summary, read_traces

__all__ = [
    # v0.5.0
    "MadcopState", "build_graph", "run_agent",
    # v0.6.0
    "ExecutionMode", "Plan", "PlanExecuteConfig", "PlanExecuteLoop",
    "PlanExecuteResult", "Planner", "PlanStep", "StepExecutor", "StepOutcome",
    "TrivialPlanner", "FnStepExecutor",
    # v0.7.2
    "RoutingStepExecutor",
    # v1.0.0 middleware chain
    "ALL_HOOKS",
    "Directive",
    "HookContext",
    "LoggingMiddleware",
    "MiddlewareChain",
    "MiddlewareHalt",
    "QianControlMiddleware",
    "apply_directives",
    "HOOK_PLAN_END", "HOOK_PLAN_START", "HOOK_REPLAN",
    "HOOK_STEP_END", "HOOK_STEP_START",
    "ClarificationMiddleware", "ClarificationRequested",
    "LoopDetectionMiddleware",
    "TodoMiddleware", "TodoPlan", "TodoStep",
    # v1.2.0 tracing
    "Tracer", "TraceMiddleware", "read_traces", "print_summary",
]
