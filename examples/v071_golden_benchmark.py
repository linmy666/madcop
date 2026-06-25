"""v0.7.1 — Real-LLM golden-set benchmark.

3 OMS cancel-spike scenarios. Each builds a synthetic event stream
of a known cancel rate, runs the v0.6.0 plan-execute loop with the
real LLM as the step executor, and scores the output.

Pass criteria per scenario:
  - scenario 1: cancel rate 55% (well above baseline) — CUSUM must fire
  - scenario 2: cancel rate 30% (at baseline) — CUSUM should NOT fire (or
    fire very few times)
  - scenario 3: cancel rate 45% (mild spike) — CUSUM must fire

This is the v0.7.1 version of the v0.6.0 benchmark — same logic, but
3 scenarios instead of 6 (we drop the synthetic-only ones and focus
on cases that exercise the real LLM response path).
"""
from __future__ import annotations

import json
import os
import random
import sys
import time
from dataclasses import asdict, dataclass
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
from madcop.anomaly.detector import Detector
from madcop.anomaly.rules import ColdChainTemperatureRule, OMSOrderCancelSpikeRule
from madcop.event import EventType, SourceSystem, UnifiedEvent
from madcop.llm import OpenAICompatClient, Message


# ---------------------------------------------------------------------------
# Scenario builders (deterministic)
# ---------------------------------------------------------------------------


def _events(n: int, cancel_rate: float, seed: int = 42) -> list[UnifiedEvent]:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    out: list[UnifiedEvent] = []
    for i in range(n):
        ts = (now - timedelta(hours=24) + timedelta(seconds=i * 30)).isoformat()
        is_cancel = rng.random() < cancel_rate
        out.append(UnifiedEvent(
            timestamp=ts,
            source_system=SourceSystem.OMS,
            event_type=EventType.ORDER_CANCELLED if is_cancel else EventType.ORDER_PLACED,
            subject_id="SKU-DEMO",
            value=1.0 if is_cancel else 0.0,
            attributes={"category": "apparel", "order_id": f"O-{i:04d}"},
        ))
    return out


@dataclass
class Scenario:
    name: str
    description: str
    cancel_rate: float
    n_events: int
    expected_cusum_fires_min: int   # CUSUM should fire at least this many times
    expected_cusum_fires_max: int   # ...at most this many times
    quality_keywords: tuple[str, ...] = ()  # the agent's final report must mention these


SCENARIOS: list[Scenario] = [
    Scenario(
        name="oms_cancel_55pct",
        description="OMS cancel rate is 55% (well above apparel baseline of 30%). "
                    "The agent should diagnose a confirmed CUSUM spike.",
        cancel_rate=0.55,
        n_events=200,
        expected_cusum_fires_min=1,
        expected_cusum_fires_max=100,  # upper bound loose
        quality_keywords=("cancel", "spike", "apparel"),
    ),
    Scenario(
        name="oms_cancel_30pct_baseline",
        description="OMS cancel rate is 30% (exactly at the apparel baseline). "
                    "The agent should NOT diagnose a spike.",
        cancel_rate=0.30,
        n_events=200,
        expected_cusum_fires_min=0,
        expected_cusum_fires_max=2,  # small noise OK
        quality_keywords=("baseline", "normal"),
    ),
    Scenario(
        name="oms_cancel_45pct",
        description="OMS cancel rate is 45% (mild spike above baseline). "
                    "The agent should diagnose a probable CUSUM spike.",
        cancel_rate=0.45,
        n_events=200,
        expected_cusum_fires_min=1,
        expected_cusum_fires_max=50,
        quality_keywords=("cancel", "spike"),
    ),
]


# ---------------------------------------------------------------------------
# Plan-execute runner
# ---------------------------------------------------------------------------


def run_scenario(scenario: Scenario, client: OpenAICompatClient) -> dict[str, Any]:
    """Run one scenario end-to-end. Returns metrics dict."""
    events = _events(scenario.n_events, scenario.cancel_rate)
    detector = Detector(rules=[OMSOrderCancelSpikeRule(), ColdChainTemperatureRule()])

    # Step 1: inline (no LLM) — detect findings
    # Step 2: inline (LLM) — produce a human-readable diagnosis
    def router_fn(step: PlanStep, ctx: dict) -> StepOutcome:
        if step.name == "detect":
            findings = []
            for ev in events:
                findings.extend(detector.evaluate_event(ev))
            ctx["findings"] = findings
            return StepOutcome(
                step_name=step.name,
                output=f"{len(findings)} findings",
                success=True,
                cost_usd=0.0,
                duration_s=0.001,
            )
        if step.name == "diagnose":
            findings = ctx.get("findings", [])
            cancel_count = sum(1 for e in events if e.event_type == EventType.ORDER_CANCELLED)
            obs_rate = cancel_count / len(events) if events else 0.0
            prompt = (
                f"You are a supply chain analyst. "
                f"Given this OMS data: {len(events)} orders in the last 24h, "
                f"{cancel_count} cancellations ({obs_rate:.0%}). "
                f"CUSUM detector found {len(findings)} anomaly hits on the apparel category "
                f"(baseline cancel rate 30%). "
                f"Scenario: {scenario.description}\n\n"
                f"In 2-3 sentences, give your diagnosis."
            )
            try:
                resp = client.chat([Message(role="user", content=prompt)], max_tokens=300, temperature=0.0)
                content = resp.content
                if "<think>" in content and "</think>" in content:
                    content = content.split("</think>", 1)[-1].strip()
                return StepOutcome(step_name=step.name, output=content, success=True,
                                   cost_usd=0.005, duration_s=1.0)
            except Exception as e:
                return StepOutcome(step_name=step.name, output="", success=False,
                                   error=f"{type(e).__name__}: {e}")
        return StepOutcome(step_name=step.name, output="ok", success=True)

    plan = Plan(steps=[
        PlanStep(name="detect", action="run CUSUM"),
        PlanStep(name="diagnose", action="produce human-readable diagnosis"),
    ])

    class FixedPlanner:
        def plan(self, goal, mode):  # noqa: ARG002
            return plan

    loop = PlanExecuteLoop(
        FixedPlanner(),
        FnStepExecutor(router_fn),
        PlanExecuteConfig(mode=ExecutionMode.STANDARD),
    )

    t0 = time.time()
    result = loop.run(scenario.description)
    elapsed = time.time() - t0

    # Extract findings from the detect step output
    n_findings = 0
    if result.step_outcomes and "findings" in result.step_outcomes[0].output:
        try:
            n_findings = int(result.step_outcomes[0].output.split(" ")[0])
        except (ValueError, IndexError):
            n_findings = 0

    # Quality check: do the LLM's keywords appear in the final report?
    final = result.final_output.lower()
    keyword_hits = sum(1 for kw in scenario.quality_keywords if kw.lower() in final)

    return {
        "name": scenario.name,
        "success": result.success,
        "elapsed_s": elapsed,
        "total_cost_usd": result.total_cost_usd,
        "n_findings": n_findings,
        "expected_min": scenario.expected_cusum_fires_min,
        "expected_max": scenario.expected_cusum_fires_max,
        "findings_ok": scenario.expected_cusum_fires_min <= n_findings <= scenario.expected_cusum_fires_max,
        "quality_score": keyword_hits,
        "quality_max": len(scenario.quality_keywords),
        "final_output": result.final_output[:300],
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    # Build the LLM client
    try:
        client = OpenAICompatClient()
    except ValueError as e:
        print(f"ERROR: {e}")
        print("Set MADCOP_OPENAI_API_KEY, MADCOP_OPENAI_BASE_URL, MADCOP_OPENAI_MODEL env vars.")
        return 1

    print("=" * 72)
    print(f"MADCOP v0.7.1 — real-LLM golden-set benchmark")
    print(f"  base_url: {client.base_url}")
    print(f"  model:    {client.model}")
    print("=" * 72)
    print()

    results: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        print(f"--- {scenario.name} ---")
        r = run_scenario(scenario, client)
        results.append(r)
        print(f"  success:    {r['success']}")
        print(f"  findings:   {r['n_findings']} (expected {r['expected_min']}..{r['expected_max']}) — "
              f"{'OK' if r['findings_ok'] else 'FAIL'}")
        print(f"  quality:    {r['quality_score']}/{r['quality_max']} keywords matched")
        print(f"  cost:       ${r['total_cost_usd']:.4f}")
        print(f"  elapsed:    {r['elapsed_s']:.2f}s")
        print(f"  final:      {r['final_output'][:150]}...")
        print()

    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    n_passed = sum(1 for r in results if r["findings_ok"] and r["success"])
    print(f"scenarios passed: {n_passed}/{len(SCENARIOS)}")
    total_cost = sum(r["total_cost_usd"] for r in results)
    total_time = sum(r["elapsed_s"] for r in results)
    print(f"total cost:       ${total_cost:.4f}")
    print(f"total elapsed:    {total_time:.2f}s")

    out = Path(__file__).parent / "v071_golden_results.json"
    out.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\nResults saved to: {out}")

    return 0 if n_passed == len(SCENARIOS) else 1


if __name__ == "__main__":
    sys.exit(main())
