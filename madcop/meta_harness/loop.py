"""Outer Meta-Harness loop (Phase 0: local search proposer).

Phase 1 will swap ``propose_local`` for a coding-agent proposer that
``grep``s the archive filesystem (paper-style).
"""
from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from madcop.meta_harness.archive import HarnessArchive
from madcop.meta_harness.evaluate import EvalArtifacts, evaluate_harness
from madcop.meta_harness.task_harness import (
    ChatTaskHarness,
    load_active_harness,
    save_active_harness,
)


@dataclass
class LoopResult:
    iterations: int
    best: ChatTaskHarness
    best_pass_rate: float
    history: list[dict[str, Any]]


def propose_local(parent: ChatTaskHarness, rng: random.Random | None = None) -> ChatTaskHarness:
    """Simple random walk over numeric/bool knobs (cheap offline proposer)."""
    rng = rng or random.Random()
    child = parent.mutate()
    axis = rng.choice(
        [
            "profile_budget",
            "relevant_budget",
            "preferences_budget",
            "skills_budget",
            "inject_skills",
            "max_skills",
        ]
    )
    if axis == "inject_skills":
        child.inject_skills = not parent.inject_skills
    elif axis == "max_skills":
        child.max_skills = max(0, min(30, parent.max_skills + rng.choice([-3, -1, 1, 3])))
    else:
        delta = rng.choice([-200, -100, 100, 200])
        cur = getattr(parent, axis)
        setattr(child, axis, max(0, min(4000, int(cur) + delta)))
    child.name = f"mut_{axis}"
    child.notes = f"local mutate {axis} from {parent.name}"
    return child


class MetaHarnessLoop:
    def __init__(
        self,
        archive: HarnessArchive | None = None,
        *,
        seed: int = 0,
        promote_best: bool = False,
    ) -> None:
        self.archive = archive or HarnessArchive()
        self.rng = random.Random(seed)
        self.promote_best = promote_best

    def run(
        self,
        *,
        iterations: int = 5,
        start: ChatTaskHarness | None = None,
        live_llm: bool = False,
    ) -> LoopResult:
        current = start or load_active_harness()
        history: list[dict[str, Any]] = []

        def _eval(h: ChatTaskHarness) -> EvalArtifacts:
            if live_llm:
                from madcop.meta_harness.evaluate import evaluate_with_live_llm
                return evaluate_with_live_llm(h)
            return evaluate_harness(h)

        # seed evaluation
        art = _eval(current)
        rec = self.archive.write(
            current,
            pass_rate=art.report.pass_rate,
            total=art.report.total,
            passed=art.report.passed,
            failed=art.report.failed,
            notes="seed",
            case_traces=art.case_traces,
            name_suffix=current.name or "seed",
        )
        best_h, best_rate = current, art.report.pass_rate
        history.append({"id": rec.id, "pass_rate": best_rate, "name": current.name})

        for i in range(iterations):
            child = propose_local(best_h, self.rng)
            art = _eval(child)
            rec = self.archive.write(
                child,
                pass_rate=art.report.pass_rate,
                total=art.report.total,
                passed=art.report.passed,
                failed=art.report.failed,
                parent_id=history[-1]["id"],
                notes=child.notes,
                case_traces=art.case_traces,
                name_suffix=child.name,
            )
            history.append({"id": rec.id, "pass_rate": art.report.pass_rate, "name": child.name})
            if art.report.pass_rate >= best_rate:
                best_h, best_rate = child, art.report.pass_rate

        if self.promote_best:
            save_active_harness(best_h)

        return LoopResult(
            iterations=iterations,
            best=best_h,
            best_pass_rate=best_rate,
            history=history,
        )
