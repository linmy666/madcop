"""L5 — LangGraph orchestration + v0.6.0 plan-execute loop.

Public surface:
  v0.5.0 (linear graph):  `MadcopState`, `build_graph`, `run_agent`
  v0.6.0 (free-form loop): `PlanExecuteLoop`, `Plan`, `PlanStep`,
                            `StepExecutor`, `Planner`, `ExecutionMode`,
                            `TrivialPlanner`, `FnStepExecutor`
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

__all__ = [
    # v0.5.0
    "MadcopState", "build_graph", "run_agent",
    # v0.6.0
    "ExecutionMode", "Plan", "PlanExecuteConfig", "PlanExecuteLoop",
    "PlanExecuteResult", "Planner", "PlanStep", "StepExecutor", "StepOutcome",
    "TrivialPlanner", "FnStepExecutor",
]
