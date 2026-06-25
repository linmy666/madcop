"""End-to-end demo: lead agent fans out to 2 sub-agents in parallel.

v0.7.0 sub-agent flow:
  1. Plan: 3 steps — 2 of them fan out to a sub-agent
     - step1: gather OMS events (inline)
     - step2: dispatch to general-purpose sub-agent (rules analysis)
     - step3: dispatch to bash sub-agent (build a CSV report)
  2. Executor runs step1 inline, then dispatches step2 + step3 to
     the sub-agent executor in parallel.
  3. Final output is the merged report.

This script also serves as the v0.7.0 "works end-to-end" smoke test.

Run:
  python examples/v070_subagent_demo.py
"""
from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madcop.agent.plan_execute import (
    ExecutionMode,
    FnStepExecutor,
    Plan,
    PlanExecuteConfig,
    PlanExecuteLoop,
    PlanStep,
    StepOutcome,
)
from madcop.agent.subagent import (
    ExecutorConfig,
    FnRunner,
    GENERAL_PURPOSE,
    SubagentExecutor,
)
from madcop.anomaly.detector import Detector
from madcop.anomaly.rules import ColdChainTemperatureRule, OMSOrderCancelSpikeRule
from madcop.event import EventType, SourceSystem, UnifiedEvent


# ---------------------------------------------------------------------------
# Step 1: inline — generate synthetic OMS events
# ---------------------------------------------------------------------------

def _make_oms_events(n: int = 200, cancel_rate: float = 0.55) -> list[UnifiedEvent]:
    import random
    rng = random.Random(42)
    now = datetime.now(timezone.utc)
    events = []
    for i in range(n):
        ts = (now - timedelta(hours=24) + timedelta(seconds=i * 60)).isoformat()
        is_cancel = rng.random() < cancel_rate
        events.append(UnifiedEvent(
            timestamp=ts,
            source_system=SourceSystem.OMS,
            event_type=EventType.ORDER_CANCELLED if is_cancel else EventType.ORDER_PLACED,
            subject_id="SKU-DEMO",
            value=1.0 if is_cancel else 0.0,
            attributes={"category": "apparel", "order_id": f"O-{i:04d}"},
        ))
    return events


def _inline_step(step: PlanStep, ctx: dict) -> StepOutcome:
    events = _make_oms_events()
    ctx["events"] = events
    return StepOutcome(
        step_name=step.name,
        output=f"ingested {len(events)} OMS events",
        success=True,
        cost_usd=0.0001,
        duration_s=0.001,
    )


# ---------------------------------------------------------------------------
# Sub-agent runner: simulates an LLM doing the analysis
# ---------------------------------------------------------------------------

def _make_subagent_runner(detector: Detector) -> FnRunner:
    """The 'real work' each sub-agent does.

    general-purpose: classifies findings by severity
    bash:           builds a CSV report (simulated — we just format text)
    """

    def fn(*, agent, prompt, context, result_holder):
        # Cancellation check (real LLMs poll this between calls)
        if result_holder.cancel_event.is_set():
            return "[cancelled]"

        if agent.name == "general-purpose":
            events = context.get("events", [])
            findings = []
            for ev in events:
                findings.extend(detector.evaluate_event(ev))
            high = sum(1 for f in findings if f.severity >= 3)
            return f"ANALYSIS: {len(findings)} findings, {high} high-severity"

        if agent.name == "bash":
            n_events = len(context.get("events", []))
            return (
                f"CSV: order_id,event_type,timestamp\n"
                f"# simulated {n_events} rows written to /tmp/oms_report.csv"
            )

        return f"unknown agent: {agent.name}"

    return FnRunner(fn)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 64)
    print("MADCOP v0.7.0 — Sub-agent fan-out demo")
    print("=" * 64)

    # Step 1: inline event gathering
    # Step 2: dispatch to general-purpose sub-agent (rule analysis)
    # Step 3: dispatch to bash sub-agent (build CSV)
    plan = Plan(
        steps=[
            PlanStep(name="ingest", action="gather OMS events"),
            PlanStep(
                name="analyze",
                action="classify findings by severity",
                subagent="general-purpose",
            ),
            PlanStep(
                name="report",
                action="build CSV report",
                subagent="bash",
            ),
        ],
        rationale="Fan out step 2 + 3 to sub-agents in parallel",
    )

    # The lead agent's executor only handles inline steps; sub-agent
    # steps are routed by a small wrapper that calls SubagentExecutor.
    detector = Detector(rules=[OMSOrderCancelSpikeRule(), ColdChainTemperatureRule()])
    subagent_runner = _make_subagent_runner(detector)
    subagent_executor = SubagentExecutor(
        runner=subagent_runner,
        config=ExecutorConfig(max_concurrent=2),  # 2 sub-agents fit
        parent_tools=("read", "write", "bash", "task"),
    )

    def router_fn(step: PlanStep, ctx: dict) -> StepOutcome:
        if step.subagent is None:
            return _inline_step(step, ctx)
        # Dispatch to sub-agent
        results = subagent_executor.run_many([(step.subagent, step.action, ctx)])
        r = results[0]
        return StepOutcome(
            step_name=step.name,
            output=r.result or "",
            success=(r.status.value == "completed"),
            cost_usd=r.cost_usd,
            duration_s=r.duration_s or 0.0,
            error=r.error,
        )

    class FixedPlanner:
        def plan(self, goal: str, mode: ExecutionMode):  # noqa: ARG002
            return plan

    loop = PlanExecuteLoop(
        FixedPlanner(),
        FnStepExecutor(router_fn),
        PlanExecuteConfig(mode=ExecutionMode.STANDARD),
    )

    t0 = time.time()
    result = loop.run("diagnose OMS cancel spike via sub-agents")
    elapsed = time.time() - t0

    print(f"mode:           {result.mode.value}")
    print(f"replans:        {result.replan_count}")
    print(f"success:        {result.success}")
    print(f"total cost:     ${result.total_cost_usd:.4f}")
    print(f"total duration: {elapsed*1000:.2f} ms")
    print("-" * 64)
    for o in result.step_outcomes:
        sub = " (sub-agent)" if o.step_name in {"analyze", "report"} else ""

        status = "OK" if o.success else "FAIL"
        print(f"  [{status}] {o.step_name}{sub}: {o.output}")
    print("-" * 64)
    print("FINAL REPORT")
    print("-" * 64)
    print(result.final_output)

    # Clean shutdown
    subagent_executor.shutdown(wait=True)

    if result.success:
        return 0
    print("DEMO FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
