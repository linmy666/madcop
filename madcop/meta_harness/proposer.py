"""Pluggable proposers for Meta-Harness outer loop (Phase 2)."""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Protocol

from madcop.meta_harness.archive import HarnessArchive
from madcop.meta_harness.task_harness import ChatTaskHarness


class Proposer(Protocol):
    def propose(
        self,
        archive: HarnessArchive,
        parent: ChatTaskHarness,
        *,
        parent_id: str | None = None,
    ) -> ChatTaskHarness:
        ...


class LocalRandomProposer:
    """Phase 0 random walk over knobs."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random()

    def propose(
        self,
        archive: HarnessArchive,
        parent: ChatTaskHarness,
        *,
        parent_id: str | None = None,
    ) -> ChatTaskHarness:
        child = parent.mutate()
        axis = self.rng.choice(
            [
                "profile_budget",
                "relevant_budget",
                "preferences_budget",
                "skills_budget",
                "inject_skills",
                "max_skills",
                "max_tools",
                "enable_tools",
                "enable_deep_mode",
                "enable_plan_mode",
                "enable_context_compact",
                "compact_threshold_messages",
            ]
        )
        if axis in (
            "inject_skills",
            "enable_tools",
            "enable_deep_mode",
            "enable_plan_mode",
            "enable_context_compact",
        ):
            setattr(child, axis, not getattr(parent, axis))
        elif axis == "max_skills":
            child.max_skills = max(0, min(30, parent.max_skills + self.rng.choice([-3, -1, 1, 3])))
        elif axis == "max_tools":
            child.max_tools = max(0, min(128, parent.max_tools + self.rng.choice([-8, -4, 4, 8])))
        elif axis == "compact_threshold_messages":
            child.compact_threshold_messages = max(
                8, min(200, parent.compact_threshold_messages + self.rng.choice([-8, -4, 4, 8]))
            )
        else:
            delta = self.rng.choice([-200, -100, 100, 200])
            cur = getattr(parent, axis)
            setattr(child, axis, max(0, min(4000, int(cur) + delta)))
        child.name = f"mut_{axis}"
        child.notes = f"local mutate {axis} from {parent.name}"
        return child


class ArchiveAwareCodeEditProposer:
    """Deterministic code-edit proposer: reads archive INDEX + prior scores,
    then writes a new system_addendum grounded in prior failures + mutates knobs.

    This is **not** only random walk: it inspects filesystem archive (list +
    score.json + optional traces) before proposing — paper-style access pattern
    with a deterministic edit instead of a paid coding agent.
    """

    def __init__(self, rng: random.Random | None = None) -> None:
        self.rng = rng or random.Random(0)

    def _read_archive_context(self, archive: HarnessArchive) -> dict[str, Any]:
        cands = archive.list_candidates()
        failed_traces: list[str] = []
        for c in cands[-5:]:
            cid = c.get("id") or ""
            tdir = archive.root / cid / "traces"
            if tdir.is_dir():
                for tf in sorted(tdir.glob("*.txt"))[:3]:
                    try:
                        text = tf.read_text(encoding="utf-8")[:400]
                        if "passed=False" in text or "failed" in text.lower():
                            failed_traces.append(f"{cid}/{tf.name}: {text[:200]}")
                    except Exception:
                        pass
        return {
            "n_candidates": len(cands),
            "best_rate": max((c.get("pass_rate") or 0) for c in cands) if cands else 0,
            "failed_traces": failed_traces[:5],
            "recent_ids": [c.get("id") for c in cands[-3:]],
        }

    def propose(
        self,
        archive: HarnessArchive,
        parent: ChatTaskHarness,
        *,
        parent_id: str | None = None,
    ) -> ChatTaskHarness:
        ctx = self._read_archive_context(archive)
        # Start from parent; apply archive-informed edits
        child = parent.mutate()
        # If prior failures exist, tighten brevity / tools; else expand memory slightly
        if ctx["failed_traces"]:
            child.system_addendum = (
                "Be concise. Prefer tool names when file access is needed. "
                f"(archive saw {len(ctx['failed_traces'])} failing traces among "
                f"{ctx['n_candidates']} candidates)"
            )
            child.max_tools = max(4, min(parent.max_tools, 16))
            child.inject_skills = True
            child.max_skills = max(3, parent.max_skills)
        else:
            child.system_addendum = (
                f"Archive context: {ctx['n_candidates']} prior candidates, "
                f"best_pass_rate={ctx['best_rate']:.2f}. Prefer direct answers."
            )
            child.profile_budget = min(4000, parent.profile_budget + 100)
            child.relevant_budget = min(4000, parent.relevant_budget + 100)

        # Also write a sidecar "implementation" snippet into archive workspace for proposer path
        impl_dir = archive.root / "_proposer_workspace"
        impl_dir.mkdir(parents=True, exist_ok=True)
        impl_path = impl_dir / "last_proposal.md"
        impl_path.write_text(
            "# Harness proposal\n\n"
            f"parent={parent.name} parent_id={parent_id}\n"
            f"recent={ctx['recent_ids']}\n"
            f"addendum={child.system_addendum}\n"
            f"knobs={json.dumps(child.to_dict(), ensure_ascii=False)}\n",
            encoding="utf-8",
        )
        child.name = "code_edit_archive"
        child.notes = f"archive-aware edit from {parent.name}; n={ctx['n_candidates']}"
        return child


class MockCodingProposer:
    """Test double: always applies a fixed, inspectable edit."""

    def propose(
        self,
        archive: HarnessArchive,
        parent: ChatTaskHarness,
        *,
        parent_id: str | None = None,
    ) -> ChatTaskHarness:
        # Prove we can list archive (filesystem access)
        _ = archive.list_candidates()
        child = parent.mutate(
            name="mock_coding",
            system_addendum="MOCK_CODING_PROPOSER: prefer structured answers.",
            max_tools=8,
            enable_plan_mode=True,
            notes=f"mock coding parent_id={parent_id}",
        )
        return child


def get_proposer(name: str, seed: int = 0) -> Proposer:
    n = (name or "local").lower()
    if n in ("code", "code_edit", "archive", "archive_aware"):
        return ArchiveAwareCodeEditProposer(random.Random(seed))
    if n in ("mock", "mock_coding"):
        return MockCodingProposer()
    return LocalRandomProposer(random.Random(seed))
