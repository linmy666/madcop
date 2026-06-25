"""End-to-end demo: OMS 取消订单激增诊断.

v0.6.0 PlanExecuteLoop walks a 3-step plan:
  1. ingest OMS events (last 24h of orders)
  2. run the CUSUM cancel-spike rule
  3. summarise the findings (with a tiny LLM-style call)

This script is also our "v0.6.0 works end-to-end" smoke test. It
exercises the new plan_execute loop + the v0.5.0 anomaly rule together.

Run:
  python examples/v060_oms_cancel_demo.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make `madcop` importable when running this script directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from madcop.agent.plan_execute import (
    ExecutionMode,
    FnStepExecutor,
    PlanExecuteConfig,
    PlanExecuteLoop,
    PlanStep,
    TrivialPlanner,
)
from madcop.anomaly.rules import OMSOrderCancelSpikeRule
from madcop.event import EventType, SourceSystem, UnifiedEvent


# ---------------------------------------------------------------------------
# Step 1: synthetic OMS data (last 24h, 200 orders, ~50% cancel rate in
# the "apparel" category to force the rule to fire).
# ---------------------------------------------------------------------------

CATEGORY_BASELINE = "apparel"   # v0.5.0 rule: baseline cancel rate for apparel = 0.30


def _make_oms_events(n_orders: int = 200, cancel_rate: float = 0.55) -> list[UnifiedEvent]:
    """Build n_orders events for a single SKU in the apparel category.

    cancel_rate=0.55 → well above the 0.30 baseline → CUSUM should fire.
    """
    import random
    rng = random.Random(42)  # deterministic
    now = datetime.now(timezone.utc)
    events: list[UnifiedEvent] = []
    for i in range(n_orders):
        ts = (now - timedelta(hours=24) + timedelta(seconds=i * 60)).isoformat()
        is_cancel = rng.random() < cancel_rate
        events.append(UnifiedEvent(
            timestamp=ts,
            source_system=SourceSystem.OMS,
            event_type=EventType.ORDER_CANCELLED if is_cancel else EventType.ORDER_PLACED,
            subject_id="SKU-APPAREL-001",
            value=1.0 if is_cancel else 0.0,
            attributes={"category": CATEGORY_BASELINE, "order_id": f"O-{i:04d}"},
        ))
    return events


# ---------------------------------------------------------------------------
# Step executors (each gets a PlanStep + context, returns a StepOutcome)
# ---------------------------------------------------------------------------

def _ingest_step(step: PlanStep, ctx: dict):
    """Generate the synthetic OMS events and stash them in context."""
    events = _make_oms_events()
    ctx["events"] = events
    return _ok(step.name, f"ingested {len(events)} OMS events for {CATEGORY_BASELINE}")


def _detect_step(step: PlanStep, ctx: dict):
    """Run the CUSUM rule over the ingested events."""
    rule = OMSOrderCancelSpikeRule()
    findings = []
    for ev in ctx["events"]:
        f = rule.evaluate(ev)
        if f is not None:
            findings.append(f)
    ctx["findings"] = findings
    if findings:
        return _ok(
            step.name,
            f"CUSUM fired {len(findings)} time(s) on {CATEGORY_BASELINE}",
        )
    return _ok(step.name, "no CUSUM trigger (rate within baseline)")


def _summarise_step(step: PlanStep, ctx: dict):
    """Produce a small operator briefing. (v0.5.0 graph does this with an
    optional LLM call; for the demo we summarise deterministically.)"""
    findings = ctx.get("findings", [])
    events = ctx.get("events", [])
    n_cancels = sum(1 for e in events if e.event_type == EventType.ORDER_CANCELLED)
    rate = n_cancels / len(events) if events else 0.0

    lines = [
        f"## OMS cancel-spike diagnostic",
        f"**Window**: last 24h, {len(events)} orders",
        f"**Category**: {CATEGORY_BASELINE} (baseline cancel rate: 30%)",
        f"**Observed cancel rate**: {rate:.0%} ({n_cancels}/{len(events)})",
        f"**CUSUM findings**: {len(findings)}",
    ]
    if findings:
        first = findings[0]
        lines.append(f"**First fire**: at {first.timestamp} (severity {first.severity})")
        lines.append(f"**Diagnosis**: cancel rate has statistically deviated from baseline.")
    else:
        lines.append("**Diagnosis**: no anomaly detected.")
    return _ok(step.name, "\n".join(lines))


def _ok(step_name: str, output: str, cost: float = 0.0001):
    """Build a successful StepOutcome."""
    from madcop.agent.plan_execute import StepOutcome
    return StepOutcome(
        step_name=step_name,
        output=output,
        success=True,
        cost_usd=cost,
        duration_s=0.001,
    )


# ---------------------------------------------------------------------------
# Main: build the loop, run it in PRO mode
# ---------------------------------------------------------------------------

def main() -> int:
    steps = [
        PlanStep(name="ingest", action="collect last 24h OMS events"),
        PlanStep(name="detect", action="run CUSUM cancel-spike rule"),
        PlanStep(name="summarise", action="produce operator briefing"),
    ]

    # We don't use TrivialPlanner (which splits on dots) — we hand the plan
    # in via a tiny custom planner that returns our fixed 3 steps.
    class FixedPlanner:
        def plan(self, goal: str, mode: ExecutionMode):  # noqa: ARG002
            from madcop.agent.plan_execute import Plan
            return Plan(steps=steps, rationale="OMS cancel-spike 3-step plan")

    # Map step names to functions
    fn_map = {
        "ingest": _ingest_step,
        "detect": _detect_step,
        "summarise": _summarise_step,
    }

    def router_fn(step: PlanStep, ctx: dict):
        return fn_map[step.name](step, ctx)

    executor = FnStepExecutor(router_fn)

    loop = PlanExecuteLoop(
        FixedPlanner(),
        executor,
        PlanExecuteConfig(mode=ExecutionMode.PRO),
    )

    result = loop.run("diagnose OMS cancel spike on SKU-APPAREL-001")

    print("=" * 60)
    print("MADCOP v0.6.0 — OMS Cancel-Spike Demo")
    print("=" * 60)
    print(f"mode:           {result.mode.value}")
    print(f"replans:        {result.replan_count}")
    print(f"success:        {result.success}")
    print(f"total cost:     ${result.total_cost_usd:.4f}")
    print(f"total duration: {result.total_duration_s:.3f}s")
    print("-" * 60)
    for o in result.step_outcomes:
        status = "OK" if o.success else "FAIL"
        print(f"  [{status}] {o.step_name}: {o.output}")
    print("-" * 60)
    print("FINAL REPORT")
    print("-" * 60)
    print(result.final_output)

    # CI-friendly: 0 exit if demo worked
    if result.success:
        return 0
    print("DEMO FAILED", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
