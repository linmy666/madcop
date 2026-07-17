"""Meta-Harness Phase 0: task harness config, archive, loop."""
from __future__ import annotations

from pathlib import Path

import pytest

from madcop.meta_harness.archive import HarnessArchive
from madcop.meta_harness.evaluate import evaluate_harness
from madcop.meta_harness.loop import MetaHarnessLoop, propose_local
from madcop.meta_harness.task_harness import ChatTaskHarness


@pytest.fixture()
def mh_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import madcop.meta_harness.task_harness as th
    import madcop.meta_harness.archive as ar

    monkeypatch.setattr(th, "_ROOT", tmp_path)
    monkeypatch.setattr(th, "_ACTIVE_PATH", tmp_path / "active.json")
    monkeypatch.setattr(ar, "ensure_root", lambda: tmp_path)
    return tmp_path


def test_harness_roundtrip(mh_root):
    from madcop.meta_harness.task_harness import load_active_harness, save_active_harness

    h = ChatTaskHarness(profile_budget=500, inject_skills=False, name="t")
    save_active_harness(h)
    loaded = load_active_harness()
    assert loaded.profile_budget == 500
    assert loaded.inject_skills is False


def test_evaluate_offline(mh_root):
    art = evaluate_harness(ChatTaskHarness())
    assert art.report.total >= 1
    assert 0.0 <= art.report.pass_rate <= 1.0


def test_archive_and_loop(mh_root):
    arch = HarnessArchive(root=mh_root)
    loop = MetaHarnessLoop(archive=arch, seed=1, promote_best=True)
    result = loop.run(iterations=3)
    assert result.iterations == 3
    assert len(result.history) == 4  # seed + 3
    cands = arch.list_candidates()
    assert len(cands) >= 4
    assert (mh_root / "active.json").exists()


def test_propose_local_changes_something():
    parent = ChatTaskHarness()
    child = propose_local(parent)
    assert child.to_dict() != parent.to_dict() or child.name != parent.name
