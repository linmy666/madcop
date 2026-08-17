"""L5 — v0.6.0 plan-execute loop + v0.7.0 sub-agent + v1.0.0 middleware
chain + v1.2.0 tracing.

Lazy-import facade: the cold-chain orchestration stack (LangGraph graph,
plan-execute, middleware chain) is NOT imported at package load. The
chat path (server routes, react_v4, harness) never touches these —
eager imports pulled langgraph + the whole legacy supply-chain stack
into every server boot. Symbols remain importable from this package for
backwards compatibility via module-level __getattr__.
"""
from __future__ import annotations

from typing import Any

# Mapping: public name → (module, attr)
_LAZY: dict[str, tuple[str, str]] = {
    # v0.5.0 linear graph (LangGraph)
    "MadcopState": (".graph", "MadcopState"),
    "build_graph": (".graph", "build_graph"),
    "run_agent": (".graph", "run_agent"),
    # v0.6.0 plan-execute
    "ExecutionMode": (".plan_execute", "ExecutionMode"),
    "Plan": (".plan_execute", "Plan"),
    "PlanExecuteConfig": (".plan_execute", "PlanExecuteConfig"),
    "PlanExecuteLoop": (".plan_execute", "PlanExecuteLoop"),
    "PlanExecuteResult": (".plan_execute", "PlanExecuteResult"),
    "Planner": (".plan_execute", "Planner"),
    "PlanStep": (".plan_execute", "PlanStep"),
    "StepExecutor": (".plan_execute", "StepExecutor"),
    "StepOutcome": (".plan_execute", "StepOutcome"),
    "TrivialPlanner": (".plan_execute", "TrivialPlanner"),
    "FnStepExecutor": (".plan_execute", "FnStepExecutor"),
    # v0.7.2 routing
    "RoutingStepExecutor": (".routing_executor", "RoutingStepExecutor"),
    # v1.0.0 middleware
    "ALL_HOOKS": (".middleware", "ALL_HOOKS"),
    "Directive": (".middleware", "Directive"),
    "HookContext": (".middleware", "HookContext"),
    "LoggingMiddleware": (".middleware", "LoggingMiddleware"),
    "MiddlewareChain": (".middleware", "MiddlewareChain"),
    "MiddlewareHalt": (".middleware", "MiddlewareHalt"),
    "QianControlMiddleware": (".middleware", "QianControlMiddleware"),
    "apply_directives": (".middleware", "apply_directives"),
    "HOOK_PLAN_END": (".middleware", "HOOK_PLAN_END"),
    "HOOK_PLAN_START": (".middleware", "HOOK_PLAN_START"),
    "HOOK_REPLAN": (".middleware", "HOOK_REPLAN"),
    "HOOK_STEP_END": (".middleware", "HOOK_STEP_END"),
    "HOOK_STEP_START": (".middleware", "HOOK_STEP_START"),
    "ClarificationMiddleware": (".clarification", "ClarificationMiddleware"),
    "ClarificationRequested": (".clarification", "ClarificationRequested"),
    "LoopDetectionMiddleware": (".loop_detection", "LoopDetectionMiddleware"),
    "TodoMiddleware": (".todo_middleware", "TodoMiddleware"),
    "TodoPlan": (".todo_middleware", "TodoPlan"),
    "TodoStep": (".todo_middleware", "TodoStep"),
    # v1.2.0 tracing
    "Tracer": (".tracing", "Tracer"),
    "TraceMiddleware": (".tracing", "TraceMiddleware"),
    "print_summary": (".tracing", "print_summary"),
    "read_traces": (".tracing", "read_traces"),
    # v1.3.0 loop engineering
    "DEFAULT_TOP_K": (".retrieval", "DEFAULT_TOP_K"),
    "DEFAULT_RECENCY_WEIGHT": (".retrieval", "DEFAULT_RECENCY_WEIGHT"),
    "DEFAULT_RECENCY_HALF_LIFE_DAYS": (".retrieval", "DEFAULT_RECENCY_HALF_LIFE_DAYS"),
    "DEFAULT_MIN_BM25": (".retrieval", "DEFAULT_MIN_BM25"),
    "PriorLesson": (".retrieval", "PriorLesson"),
    "RetrievalMiddleware": (".retrieval", "RetrievalMiddleware"),
    "filter_hits": (".retrieval", "filter_hits"),
    "format_lessons": (".retrieval", "format_lessons"),
    "rerank": (".retrieval", "rerank"),
    "DEFAULT_REFLECTION_PROMPT": (".reflection", "DEFAULT_REFLECTION_PROMPT"),
    "ReflectionMiddleware": (".reflection", "ReflectionMiddleware"),
    "parse_reflections": (".reflection", "parse_reflections"),
    "summarize_plan": (".reflection", "summarize_plan"),
    "DEFAULT_OUTCOME_HALF_LIFE_DAYS": (".outcome", "DEFAULT_OUTCOME_HALF_LIFE_DAYS"),
    "DEFAULT_OUTCOME_WEIGHT": (".outcome", "DEFAULT_OUTCOME_WEIGHT"),
    "OUTCOME_FAILURE": (".outcome", "OUTCOME_FAILURE"),
    "OUTCOME_SUCCESS": (".outcome", "OUTCOME_SUCCESS"),
    "OUTCOME_UNKNOWN": (".outcome", "OUTCOME_UNKNOWN"),
    "OutcomePrioritizer": (".outcome", "OutcomePrioritizer"),
    "boost_outcome": (".outcome", "boost_outcome"),
    "format_lessons_with_outcome": (".outcome", "format_lessons_with_outcome"),
    "lesson_outcome_score": (".outcome", "lesson_outcome_score"),
    "CRYSTALLIZED_SAVED_BY": (".crystallize", "CRYSTALLIZED_SAVED_BY"),
    "CRYSTALLIZED_SOURCE": (".crystallize", "CRYSTALLIZED_SOURCE"),
    "CRYSTALLIZED_TAG": (".crystallize", "CRYSTALLIZED_TAG"),
    "DEFAULT_MIN_CLUSTER_SIZE": (".crystallize", "DEFAULT_MIN_CLUSTER_SIZE"),
    "DEFAULT_PREFIX_SPLIT": (".crystallize", "DEFAULT_PREFIX_SPLIT"),
    "SkillCrystallizer": (".crystallize", "SkillCrystallizer"),
    "aggregate_outcome": (".crystallize", "aggregate_outcome"),
    "cluster_topics": (".crystallize", "cluster_topics"),
    "crystallize_skills": (".crystallize", "crystallize_skills"),
    "render_skill_body": (".crystallize", "render_skill_body"),
}


def __getattr__(name: str) -> Any:
    if name in _LAZY:
        import importlib
        mod_path, attr = _LAZY[name]
        mod = importlib.import_module(mod_path, __name__)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(list(globals().keys()) + list(_LAZY.keys()))
