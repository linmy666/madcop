"""Tests for revertible effects (paper §3.1) and reactive coeffects (§3.2)."""
from __future__ import annotations

from pathlib import Path
import json

import pytest

from madcop.harness.effects import EffectStore, make_file_restore_inverse
from madcop.harness.coeffects import CoeffectStore
from madcop.llm.client import Message


# ─── EffectStore ─────────────────────────────────────────────────────────


def test_revert_restores_deleted_file(tmp_path: Path):
    target = tmp_path / "new.txt"
    inverse = make_file_restore_inverse(str(target))
    assert inverse is not None
    target.write_text("created")  # the effect
    inverse()  # the inverse at the application point
    assert not target.exists()


def test_revert_restores_overwritten_file(tmp_path: Path):
    target = tmp_path / "exist.txt"
    target.write_text("original")
    inverse = make_file_restore_inverse(str(target))
    target.write_text("overwritten!")  # the effect
    inverse()
    assert target.read_text() == "original"


def test_effect_store_revert_key_removes_inverses(tmp_path: Path):
    store = EffectStore()
    target = tmp_path / "a.txt"
    inv = make_file_restore_inverse(str(target))
    store.register("k1", "write a.txt", inv)
    target.write_text("v1")
    report = store.revert("k1")
    assert report["applied"] == 1
    assert not target.exists()
    # Key cleared — a second revert is a no-op (no double-apply).
    report2 = store.revert("k1")
    assert report2["total"] == 0


def test_effect_store_reverse_order(tmp_path: Path):
    """Inverses apply newest-first (twisted composite, Definition 9)."""
    store = EffectStore()
    order: list[str] = []
    store.register("k", "first", lambda: order.append("first"))
    store.register("k", "second", lambda: order.append("second"))
    store.revert("k")
    assert order == ["second", "first"]


def test_effect_store_irreversible_is_skipped(tmp_path: Path):
    store = EffectStore()
    target = tmp_path / "x.txt"
    inv = make_file_restore_inverse(str(target))
    store.mark_irreversible("k", "bash side effects")
    store.register("k", "write x.txt", inv)
    target.write_text("v")
    report = store.revert("k")
    assert report["skipped"] == 1 and report["applied"] == 1
    assert not target.exists()


def test_inverse_failure_does_not_block_others(tmp_path: Path):
    store = EffectStore()

    def _boom():
        raise RuntimeError("no")

    ok_deleted = tmp_path / "del.txt"
    ok_del_inv = make_file_restore_inverse(str(ok_deleted))
    store.register("k", "broken", _boom)
    store.register("k", "good", ok_del_inv)
    ok_deleted.write_text("v")
    report = store.revert("k")
    assert report["failed"] == 1 and report["applied"] == 1
    assert not ok_deleted.exists()


# ─── CoeffectStore ────────────────────────────────────────────────────────


def test_provide_withdraw_notify():
    store = CoeffectStore()
    events: list[tuple[str, str]] = []
    store.on_change(lambda k, t: events.append((k, t)))
    dispose = store.provide("mcp:srv", {"server": "srv"})
    assert store.has("mcp:srv")
    assert events == [("mcp:srv", "activating")]
    dispose()
    assert not store.has("mcp:srv")
    assert events[-1] == ("mcp:srv", "deactivating")


def test_provide_existing_is_neutral():
    store = CoeffectStore()
    events: list[tuple[str, str]] = []
    store.on_change(lambda k, t: events.append((k, t)))
    store.provide("k", 1)
    store.provide("k", 2)  # neutral — satisfaction unchanged; per Algorithm 3
    # the notification still fires but classifies as neutral, which
    # refresh treats as a no-op. Our store keeps notifying; assert the
    # CLASSIFICATION, not suppression.
    assert events == [("k", "activating"), ("k", "neutral")]


def test_derived_store_overrides_parent_untouched():
    parent = CoeffectStore()
    parent.provide("approval.dir:/tmp", True)
    child = parent.derive({"workdir": "/stage"})
    assert child.has("approval.dir:/tmp", "workdir")
    child.withdraw("approval.dir:/tmp")
    # parent untouched (derived realization — recovery = discard child)
    assert parent.has("approval.dir:/tmp")


# ─── Registry coeffect gating ────────────────────────────────────────────


def test_registry_gates_unsatisfied_tools():
    from madcop.agent.tool_executor import (
        PluginRegistry, ToolPlugin,
    )

    reg = PluginRegistry()
    reg.register(ToolPlugin(
        name="web_search", handler=lambda **k: "",
        schema={"type": "function", "function": {"name": "web_search"}},
        requires=frozenset({"net"}),
    ))
    reg.register(ToolPlugin(
        name="echo", handler=lambda **k: "",
        schema={"type": "function", "function": {"name": "echo"}},
    ))

    assert [s["function"]["name"] for s in reg.satisfied_schemas({"net"})] == [
        "web_search", "echo",
    ]
    gated = reg.satisfied_schemas(set())
    assert [s["function"]["name"] for s in gated] == ["echo"]
    assert reg.unsatisfied_reason("web_search", set()) == "net"
    assert reg.unsatisfied_reason("echo", set()) == ""


# ─── MEA revert_step_effects (deterministic, no LLM) ─────────────────────


def test_mea_revert_step_effects_rolls_back_write(tmp_path, monkeypatch):
    """Executor writes via the real tool executor (effect registered),
    auditor blocks, revert_step_effects restores the pre-write state."""
    from madcop.agent.tool_executor import build_default_registry
    from madcop.harness import MadCopHarness
    from madcop.harness.coeffects import CoeffectStore
    from madcop.llm.client import Message
    from madcop.agent.runtime import RunContext

    ws = tmp_path / "ws"
    ws.mkdir()
    target = ws / "out.txt"

    reg, executor = build_default_registry(workspace_dir=str(ws))
    # Point the allowlist at tmp_path by rebuilding with it (done above);
    # write relative to workspace root.
    rel = ws / "out.txt"
    from madcop.harness.core import SessionLog

    ctx = RunContext(
        messages=[Message(role="user", content="write")],
        model="test", agent_mode="task",
        work_dir=str(ws), session_id="mea-test",
        client=None, tool_schemas=reg.get_all_schemas(),
        tool_executor=executor.execute,
        confirm_handler=lambda n, i, u: True,
    )
    harness = MadCopHarness(ctx, max_steps=2)
    harness.goal = "write out.txt"
    harness._last_contract_desc = "write out.txt"
    # Executor writes the file through the REAL tool executor with the
    # same effect_key convention react_v4 uses.
    key = "mea-test:use-1"
    r = executor.execute(
        "write_file",
        json.dumps({"path": str(rel), "content": "draft"}),
        str(ws), pre_approved=True, effect_key=key,
    )
    assert not r.is_error, r.to_observation()
    assert target.read_text() == "draft"
    harness._step_effect_keys.append(key)

    applied, keys = harness.revert_step_effects()
    assert applied == 1 and keys == [key]
    assert not target.exists()



def test_tail_promise_regex_polarities():
    """The plan-ending guard's regex: promises match, real answers don't."""
    from madcop.agent.react_v4 import _TAIL_PROMISE_RE
    promises = [
        "我读一下文件后面部分确认完整性，然后开始构建。",
        "接下来我会验证文件的完整性。",
        "先读取配置，然后再开始搭建。",
    ]
    answers = [
        "长城全长两万一千公里，被誉为世界文化遗产和中华民族的象征。",
        "已创建 /tmp/pvz.html，打开即可游玩。",
        "1+1=2。",
    ]
    for p in promises:
        assert _TAIL_PROMISE_RE.search(p[-90:]), f"should match: {p}"
    for a in answers:
        assert not _TAIL_PROMISE_RE.search(a[-90:]), f"should NOT match: {a}"
