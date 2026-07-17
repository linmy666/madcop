"""HTTP API for Meta-Harness status / list / promote / run."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(tags=["meta-harness"])


class PromoteBody(BaseModel):
    id: str | None = None  # candidate id; None = best


class RunBody(BaseModel):
    iterations: int = Field(default=2, ge=1, le=20)
    suite: str = "smoke"
    proposer: str = "local"
    promote: bool = False
    seed: int = 0


@router.get("/api/meta-harness/status")
async def meta_harness_status() -> dict[str, Any]:
    from madcop.meta_harness.archive import HarnessArchive
    from madcop.meta_harness.task_harness import load_active_harness, list_knob_axes

    active = load_active_harness()
    arch = HarnessArchive()
    return {
        "active": active.to_dict(),
        "archive_best": arch.best(),
        "archive_count": len(arch.list_candidates()),
        "axes": list_knob_axes(),
    }


@router.get("/api/meta-harness/candidates")
async def meta_harness_candidates() -> dict[str, Any]:
    from madcop.meta_harness.archive import HarnessArchive

    return {"candidates": HarnessArchive().list_candidates()}


@router.post("/api/meta-harness/promote")
async def meta_harness_promote(body: PromoteBody | None = None) -> dict[str, Any]:
    from madcop.meta_harness.archive import HarnessArchive
    from madcop.meta_harness.task_harness import ChatTaskHarness, save_active_harness
    import json

    body = body or PromoteBody()
    arch = HarnessArchive()
    if body.id:
        score_path = arch.root / body.id / "score.json"
        if not score_path.exists():
            matches = [
                p for p in arch.root.iterdir()
                if p.is_dir() and p.name.startswith(body.id)
            ]
            if not matches:
                raise HTTPException(404, f"candidate not found: {body.id}")
            score_path = matches[0] / "score.json"
        data = json.loads(score_path.read_text(encoding="utf-8"))
    else:
        data = arch.best()
        if not data:
            raise HTTPException(404, "archive empty")
    h = ChatTaskHarness.from_dict(data.get("harness") or data)
    path = save_active_harness(h)
    return {"ok": True, "path": str(path), "active": h.to_dict()}


@router.post("/api/meta-harness/run")
async def meta_harness_run(body: RunBody | None = None) -> dict[str, Any]:
    """Offline search loop (no live LLM). May take a few seconds."""
    import asyncio

    body = body or RunBody()
    from madcop.meta_harness.loop import MetaHarnessLoop

    def _run():
        loop = MetaHarnessLoop(
            seed=body.seed,
            promote_best=body.promote,
            proposer=body.proposer,
            suite=body.suite,
        )
        return loop.run(iterations=body.iterations, live_llm=False)

    result = await asyncio.to_thread(_run)
    return {
        "ok": True,
        "iterations": result.iterations,
        "best_pass_rate": result.best_pass_rate,
        "best": result.best.to_dict(),
        "history": result.history,
        "proposer": result.proposer,
        "suite": body.suite,
        "promoted": body.promote,
    }


@router.get("/api/meta-harness/axes")
async def meta_harness_axes() -> dict[str, Any]:
    from madcop.meta_harness.task_harness import list_knob_axes
    return {"axes": list_knob_axes()}
