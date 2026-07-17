"""Outer Meta-Harness loop with pluggable proposers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from madcop.meta_harness.archive import HarnessArchive
from madcop.meta_harness.evaluate import EvalArtifacts, evaluate_harness
from madcop.meta_harness.proposer import Proposer, get_proposer
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
    proposer: str = "local"


# Back-compat for tests that import propose_local
def propose_local(parent: ChatTaskHarness, rng=None) -> ChatTaskHarness:
    from madcop.meta_harness.proposer import LocalRandomProposer
    import random
    p = LocalRandomProposer(rng or random.Random())
    return p.propose(HarnessArchive(), parent)


class MetaHarnessLoop:
    def __init__(
        self,
        archive: HarnessArchive | None = None,
        *,
        seed: int = 0,
        promote_best: bool = False,
        proposer: str | Proposer = "local",
        suite: str = "smoke",
    ) -> None:
        self.archive = archive or HarnessArchive()
        self.promote_best = promote_best
        self.suite = suite
        if isinstance(proposer, str):
            self.proposer_name = proposer
            self._proposer: Proposer = get_proposer(proposer, seed=seed)
        else:
            self.proposer_name = "custom"
            self._proposer = proposer

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
                return evaluate_with_live_llm(h, suite=self.suite)
            return evaluate_harness(h, suite=self.suite)

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
        history.append({
            "id": rec.id,
            "pass_rate": best_rate,
            "name": current.name,
            "parent_id": None,
        })

        for _i in range(iterations):
            parent_id = history[-1]["id"]
            child = self._proposer.propose(
                self.archive, best_h, parent_id=parent_id
            )
            art = _eval(child)
            rec = self.archive.write(
                child,
                pass_rate=art.report.pass_rate,
                total=art.report.total,
                passed=art.report.passed,
                failed=art.report.failed,
                parent_id=parent_id,
                notes=child.notes,
                case_traces=art.case_traces,
                name_suffix=child.name,
            )
            history.append({
                "id": rec.id,
                "pass_rate": art.report.pass_rate,
                "name": child.name,
                "parent_id": parent_id,
            })
            if art.report.pass_rate >= best_rate:
                best_h, best_rate = child, art.report.pass_rate

        if self.promote_best:
            save_active_harness(best_h)

        return LoopResult(
            iterations=iterations,
            best=best_h,
            best_pass_rate=best_rate,
            history=history,
            proposer=self.proposer_name,
        )
