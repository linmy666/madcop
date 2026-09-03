"""Codex-parity batch 4 — Guardian full mechanism set, tokenized
command safety net, apply_patch multi-hunk tool.

Guardian tests use fake clients (no real LLM). The circuit breaker,
cache, timeout and fail-closed escalation are pinned by behaviour.
"""
from __future__ import annotations

import json
import time

import pytest


# ── helpers ───────────────────────────────────────────────────────────────

def _client_returning(payload: str, calls: list | None = None):
    class _Resp:
        content = payload

    class _Client:
        def chat(self, messages, **kwargs):
            if calls is not None:
                calls.append(messages)
            return _Resp()

    return _Client()


def _verdict_payload(decision, risk="low", reason="r"):
    return json.dumps({"decision": decision, "risk": risk, "reason": reason})


@pytest.fixture(autouse=True)
def _fast_guardian(monkeypatch):
    import madcop.harness.guardian as g
    monkeypatch.setenv("MADCOP_GUARDIAN", "1")
    yield


# ── A. Guardian ───────────────────────────────────────────────────────────

def test_guardian_allow_skips_card():
    from madcop.harness.guardian import GuardianReviewer
    calls: list = []
    g = GuardianReviewer(
        client_getter=lambda: _client_returning(
            _verdict_payload("allow"), calls))
    v = g.review("ls -la")
    assert v.decision == "allow" and v.source == "llm"
    assert len(calls) == 1


def test_guardian_cache_same_command_one_call():
    from madcop.harness.guardian import GuardianReviewer
    calls: list = []
    g = GuardianReviewer(
        client_getter=lambda: _client_returning(
            _verdict_payload("allow"), calls))
    g.review("npm test")
    g.review("npm   test")  # whitespace-normalized → cache hit
    assert len(calls) == 1


def test_guardian_deny_anti_workaround_note():
    from madcop.harness.guardian import (
        GuardianReviewer, anti_workaround_observation)
    g = GuardianReviewer(client_getter=lambda: _client_returning(
        _verdict_payload("deny", reason="删除系统目录")))
    v = g.review("rm -rf /")
    assert v.decision == "deny"
    note = anti_workaround_observation(v)
    assert "绕过" in note and "删除系统目录" in note


def test_guardian_circuit_breaker_after_denials():
    from madcop.harness.guardian import GuardianReviewer, DENIAL_CIRCUIT_LIMIT
    g = GuardianReviewer(client_getter=lambda: _client_returning(
        _verdict_payload("deny")))
    for i in range(DENIAL_CIRCUIT_LIMIT):
        g.review(f"cmd-{i}")  # each distinct → real LLM call
    # Circuit open: distinct commands stop hitting the LLM entirely.
    calls_marker = []
    g._client_getter = lambda: _client_returning(
        _verdict_payload("allow", reason="should not run"),
        calls_marker)
    v = g.review("totally-fresh-command")
    assert v.decision == "escalate" and v.source == "circuit-breaker"
    assert calls_marker == []  # LLM never consulted


def test_guardian_escalate_and_fail_closed():
    from madcop.harness.guardian import GuardianReviewer
    # Malformed output → escalate (fail-closed).
    g1 = GuardianReviewer(client_getter=lambda: _client_returning(
        "我觉得这个命令挺好的，没什么问题。"))
    assert g1.review("some command").decision == "escalate"
    # No client → escalate.
    g2 = GuardianReviewer(client_getter=lambda: None)
    v = g2.review("ls")
    assert v.decision == "escalate" and v.source == "no-client"
    # Client getter raising → escalate, never raises.
    def _boom():
        raise RuntimeError("boom")
    g3 = GuardianReviewer(client_getter=_boom)
    assert g3.review("ls").decision == "escalate"


def test_guardian_timeout_escalates(monkeypatch):
    import madcop.harness.guardian as g

    class _SlowClient:
        def chat(self, *a, **k):
            time.sleep(30)

    monkeypatch.setattr(g, "REVIEW_TIMEOUT_S", 0.2)
    gr = g.GuardianReviewer(client_getter=lambda: _SlowClient())
    v = gr.review("slow command")
    assert v.decision == "escalate" and v.source == "timeout"


def test_guardian_disabled_via_env(monkeypatch):
    from madcop.harness.guardian import GuardianReviewer
    monkeypatch.setenv("MADCOP_GUARDIAN", "0")
    calls: list = []
    g = GuardianReviewer(client_getter=lambda: _client_returning(
        _verdict_payload("allow"), calls))
    v = g.review("ls")
    assert v.decision == "escalate" and v.source == "disabled"
    assert calls == []


def test_guardian_think_wrapped_json_parsed():
    from madcop.harness.guardian import GuardianReviewer
    payload = "<think>分析一下……</think>" + _verdict_payload("allow", risk="low")
    g = GuardianReviewer(client_getter=lambda: _client_returning(payload))
    assert g.review("git status").decision == "allow"


# ── B. tokenized command safety net ───────────────────────────────────────

def test_command_safety_unwraps_wrappers():
    from madcop.harness.command_safety import dangerous_command_match as m
    assert m("sudo rm -rf /data").value == "forced_rm"
    assert m("env rm -rf /data").value == "forced_rm"
    assert m("sudo -u root rm -rf /data").value == "forced_rm"
    assert m("rm -fr ./build").value == "forced_rm"
    assert m("nohup rm --force -r x").value == "forced_rm"
    assert m("timeout 10 rm -rf x").value == "forced_rm"
    assert m("dd if=zero of=/dev/sda").value == "other"
    assert m("diskutil eraseDisk APFS X disk1").value == "other"
    assert m("echo hi; sudo rm -rf /").value == "other"


def test_command_safety_passes_benign():
    from madcop.harness.command_safety import dangerous_command_match as m
    assert m("ls -la") is None
    assert m("npm test") is None
    assert m("git push origin main") is None  # exec_policy warns, net passes
    assert m("rm -rf").value == "forced_rm"  # bare forced rm still flagged
    assert m("rm file.txt") is None
    assert m("python /tmp/setup.py") is None
    assert m("echo hello && grep x y") is None


def test_safety_hook_second_layer_vetoes():
    from madcop.agent.hooks import SafetyHook, HookContext, HookEvent
    hook = SafetyHook()
    # `env rm -fr` slips past the exec_policy regex (flags reversed,
    # env wrapper) — the tokenized net must catch it.
    ctx = HookContext(event=HookEvent.PRE_TOOL_USE, tool_name="bash",
                      tool_input={"command": "env rm -fr /important"})
    res = hook(ctx)
    assert res.continue_ is False
    assert "token 级检测" in (res.error or "")
    # Benign command passes cleanly.
    ok = hook(HookContext(event=HookEvent.PRE_TOOL_USE, tool_name="bash",
                          tool_input={"command": "ls -la"}))
    assert ok.continue_ is True and not ok.error


# ── C. apply_patch ────────────────────────────────────────────────────────

def test_parse_patch_all_ops():
    from madcop.tools.apply_patch import parse_patch
    ops = parse_patch("""*** Begin Patch
*** Add File: new.txt
+hello
+world
*** Update File: app.py
@@ def main
 def main():
-    print("old")
+    print("new")
*** Update File: tail.txt
 context
-old end
+new end
*** End of File
*** Delete File: junk.log
*** End Patch""")
    by_path = {o["path"]: o for o in ops}
    assert set(by_path) == {"new.txt", "app.py", "tail.txt", "junk.log"}
    assert by_path["new.txt"]["action"] == "add"
    assert by_path["new.txt"]["lines"] == ["hello", "world"]
    assert by_path["junk.log"]["action"] == "delete"
    up = by_path["app.py"]["chunks"][0]
    assert up["pre"] == ["def main():"]
    assert up["removed"] == ['    print("old")']
    assert up["added"] == ['    print("new")']
    assert by_path["tail.txt"]["chunks"][-1]["eof"] is True


def test_parse_patch_rejects_garbage():
    from madcop.tools.apply_patch import parse_patch
    with pytest.raises(ValueError):
        parse_patch("no markers here")
    with pytest.raises(ValueError):
        parse_patch("")


def test_apply_patch_end_to_end(tmp_path):
    from madcop.tools.apply_patch import ApplyPatchTool
    (tmp_path / "app.py").write_text(
        "def main():\n    print('old')\n    return 0\n", encoding="utf-8")
    (tmp_path / "tail.txt").write_text("a\nb\nold end\n", encoding="utf-8")
    tool = ApplyPatchTool(allowed_dirs=[tmp_path])
    out = tool(patch=f"""*** Begin Patch
*** Update File: app.py
 def main():
-    print('old')
+    print('new')
*** Update File: tail.txt
*** Move to: renamed.txt
 b
-old end
+NEW tail
*** End of File
*** Add File: extra.md
+created
*** End Patch""")
    assert out.get("status") == "ok", out
    assert out["files_changed"] == 3
    app = (tmp_path / "app.py").read_text()
    assert "print('new')" in app and "print('old')" not in app
    assert not (tmp_path / "tail.txt").exists()
    assert "NEW tail" in (tmp_path / "renamed.txt").read_text()
    assert (tmp_path / "extra.md").read_text().strip() == "created"


def test_apply_patch_context_mismatch_errors(tmp_path):
    from madcop.tools.apply_patch import ApplyPatchTool
    (tmp_path / "f.py").write_text("x = 1\n", encoding="utf-8")
    tool = ApplyPatchTool(allowed_dirs=[tmp_path])
    out = tool(patch="""*** Begin Patch
*** Update File: f.py
 y = totally absent
-old z
+new z
*** End Patch""")
    assert "error" in out and "定位失败" in out["error"]


def test_apply_patch_fuzzy_context_via_unicode(tmp_path):
    from madcop.tools.apply_patch import ApplyPatchTool
    (tmp_path / "d.md").write_text(
        "标题：\u201c引号\u201d\n内容行\n", encoding="utf-8")
    tool = ApplyPatchTool(allowed_dirs=[tmp_path])
    out = tool(patch='''*** Begin Patch
*** Update File: d.md
 标题："引号"
-内容行
+内容已改
*** End Patch''')
    assert out.get("status") == "ok", out
    assert "内容已改" in (tmp_path / "d.md").read_text()


def test_apply_patch_registered_and_effects_captured(tmp_path):
    from madcop.agent.tool_executor import build_default_registry
    from madcop.tools.safety import danger_level
    reg, _exec = build_default_registry(bound_keys=set())
    assert reg.get("apply_patch") is not None
    assert danger_level("apply_patch") == "mutating"

    # Effect layer: one inverse per touched path under one key.
    from madcop.harness.effects import STORE
    f = tmp_path / "e.txt"
    f.write_text("before", encoding="utf-8")
    report = STORE  # noqa: F841
    from madcop.harness.effects import capture_file_inverse
    key = "sess-x:tool-1"
    cap = capture_file_inverse("apply_patch", {"patch":
        "*** Begin Patch\n*** Update File: " + str(f) + "\n before\n-before\n+after\n*** End Patch"}, key)
    assert cap.get("reversible") is True and cap.get("files") == 1
    rep = STORE.revert(key)
    assert rep["applied"] == 1
    assert f.read_text() == "before"


def test_seek_sequence_eof_anchor():
    from madcop.tools.files import _seek_sequence
    lines = ["a", "tail-one", "tail-two", "tail-three"]
    # eof=True searches from the end first.
    idx, tier = _seek_sequence(lines, ["tail-two", "tail-three"], eof=True)
    assert (idx, tier) == (2, "exact")
    # Non-matching eof anchor falls back to forward search.
    idx2, tier2 = _seek_sequence(lines, ["a"], start=0, eof=True)
    assert (idx2, tier2) == (0, "exact")
