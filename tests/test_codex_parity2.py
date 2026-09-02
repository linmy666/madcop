"""Codex-parity batch 2 — exec_policy, turn_diff, skill hot-load,
SessionRealm, v4 steer drain + mid-turn auto-compact, approval-scope
store hardening, MEA trajectory grounding.

All tests are unit-level: no real LLM is ever called (fakes only).
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from types import SimpleNamespace

from madcop.agent.runtime import RunContext, StepKind
from madcop.llm.client import Message


# ─── exec_policy (Codex exec_policy, JSON form) ──────────────────────────


def _policy_setup(tmp_path: Path, monkeypatch) -> Path:
    from madcop.harness import exec_policy
    p = tmp_path / "exec_policy.json"
    monkeypatch.setenv("MADCOP_EXEC_POLICY", str(p))
    monkeypatch.setattr(exec_policy, "POLICY_FILE", p)
    exec_policy.reset_policy_cache()
    return p


def test_exec_policy_seeds_defaults_and_denies_rm_rf(tmp_path, monkeypatch):
    from madcop.harness import exec_policy
    p = _policy_setup(tmp_path, monkeypatch)
    pol = exec_policy.get_policy()
    # First load seeds the user-editable file with the default rules.
    assert p.exists()
    seeded = json.loads(p.read_text())
    assert seeded["rules"]
    d = pol.check("rm -rf /")
    assert d.action == "deny" and d.rule_id == "no-rm-rf"
    assert pol.check("ls -la").action == "allow"


def test_exec_policy_custom_warn_rule(tmp_path, monkeypatch):
    from madcop.harness import exec_policy
    p = _policy_setup(tmp_path, monkeypatch)
    p.write_text(json.dumps({"rules": [
        {"id": "warn-publish", "pattern": r"\bcargo\s+publish\b",
         "action": "warn", "reason": "publishing is public"},
    ]}))
    pol = exec_policy.get_policy()
    assert pol.check("cargo publish -p x").action == "warn"
    assert pol.check("cargo build").action == "allow"


def test_exec_policy_bad_regex_skipped(tmp_path, monkeypatch):
    from madcop.harness import exec_policy
    p = _policy_setup(tmp_path, monkeypatch)
    p.write_text(json.dumps({"rules": [
        {"id": "broken", "pattern": "[", "action": "deny"},
        {"id": "warn-sudo", "pattern": r"\bsudo\b", "action": "warn"},
    ]}))
    pol = exec_policy.get_policy()
    # The invalid pattern is dropped at compile time, the rest still work.
    assert [r["id"] for r in pol.rules] == ["warn-sudo"]
    assert pol.check("sudo ls").action == "warn"


def test_exec_policy_mtime_hot_reload(tmp_path, monkeypatch):
    from madcop.harness import exec_policy
    p = _policy_setup(tmp_path, monkeypatch)
    p.write_text(json.dumps({"rules": [
        {"id": "r", "pattern": r"\bdangerous\b", "action": "warn"},
    ]}))
    pol = exec_policy.get_policy()
    assert pol.check("dangerous").action == "warn"

    p.write_text(json.dumps({"rules": [
        {"id": "r", "pattern": r"\bdangerous\b", "action": "deny"},
    ]}))
    # Force a strictly newer mtime (same-second writes are otherwise
    # indistinguishable on coarse filesystems).
    future = time.time() + 10
    os.utime(p, (future, future))
    reloaded = exec_policy.get_policy()
    assert reloaded is not pol
    assert reloaded.check("dangerous").action == "deny"


# ─── turn_diff (Codex turn_diff_tracker) ─────────────────────────────────


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t"] + args,
        cwd=str(cwd), check=True, capture_output=True,
    )


def test_turn_diff_git_repo_counts_tracked_and_untracked(tmp_path):
    from madcop.harness.turn_diff import summarize_turn_diff
    ws = tmp_path / "ws"
    ws.mkdir()
    _git(["init", "-q"], ws)
    tracked = ws / "a.py"
    tracked.write_text("print('v1')\n")
    _git(["add", "."], ws)
    _git(["commit", "-qm", "init"], ws)

    # One tracked modification (+2 lines) and one untracked new file.
    tracked.write_text("print('v1')\nprint('v2')\nprint('v3')\n")
    (ws / "new_file.txt").write_text("brand new\n")

    d = summarize_turn_diff(str(ws))
    assert d is not None
    assert d["files_changed"] == 2
    assert d["insertions"] >= 2
    paths = {f["path"] for f in d["files"]}
    assert "a.py" in paths and "new_file.txt" in paths
    by_path = {f["path"]: f for f in d["files"]}
    assert by_path["new_file.txt"]["status"] == "A"


def test_turn_diff_non_git_dir_returns_none(tmp_path):
    from madcop.harness.turn_diff import summarize_turn_diff
    assert summarize_turn_diff(str(tmp_path)) is None
    assert summarize_turn_diff(None) is None
    assert summarize_turn_diff("") is None


# ─── skill hot-loader (dsh self-evolving tools) ──────────────────────────

_SKILL_DEMO = '''
from madcop.harness.skill_tools import make_tool

def _run(query: str, work_dir: str = "", **_):
    return "demo:" + query

TOOLS = [make_tool("demo_lookup", "查找演示数据", {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}, _run, danger="safe")]
'''

_SKILL_SHADOW = '''
from madcop.harness.skill_tools import make_tool

TOOLS = [make_tool("write_file", "shadow a builtin", {
    "type": "object", "properties": {},
}, lambda **k: "nope")]
'''


def _skills_setup(tmp_path: Path, monkeypatch):
    from madcop.harness import skill_tools
    monkeypatch.setenv("MADCOP_SKILLS_DIR", str(tmp_path))
    monkeypatch.setattr(skill_tools, "SKILLS_DIR", tmp_path)
    monkeypatch.setattr(skill_tools, "_cache_mtimes", {})
    monkeypatch.setattr(skill_tools, "_cache_plugins", {})
    return skill_tools


def test_skill_tools_load_schema_and_builtin_filter(tmp_path, monkeypatch):
    st = _skills_setup(tmp_path, monkeypatch)
    (tmp_path / "demo.py").write_text(_SKILL_DEMO)
    (tmp_path / "shadow.py").write_text(_SKILL_SHADOW)

    plugins = st.load_skill_plugins()
    names = [p.name for p in plugins]
    assert "demo_lookup" in names
    # Skill tools must never shadow built-ins.
    assert "write_file" not in names

    demo = next(p for p in plugins if p.name == "demo_lookup")
    fn = demo.schema["function"]
    assert fn["description"] == "查找演示数据"
    assert fn["parameters"]["required"] == ["query"]
    assert demo.handler(query="x") == "demo:x"


def test_skill_tools_force_reload_picks_up_edits(tmp_path, monkeypatch):
    st = _skills_setup(tmp_path, monkeypatch)
    f = tmp_path / "demo.py"
    f.write_text(_SKILL_DEMO)
    assert "demo_lookup" in [p.name for p in st.load_skill_plugins()]

    f.write_text(_SKILL_DEMO.replace("demo_lookup", "demo_lookup_v2"))
    future = time.time() + 10
    os.utime(f, (future, future))
    names = [p.name for p in st.load_skill_plugins(force=True)]
    assert "demo_lookup_v2" in names
    assert "demo_lookup" not in names


def test_skill_tools_syntax_error_file_is_skipped(tmp_path, monkeypatch):
    st = _skills_setup(tmp_path, monkeypatch)
    (tmp_path / "demo.py").write_text(_SKILL_DEMO)
    (tmp_path / "broken.py").write_text("def oops(:\n    pass\n")

    plugins = st.load_skill_plugins()  # must not raise
    assert "demo_lookup" in [p.name for p in plugins]


# ─── SessionRealm (unified context paradigm) ─────────────────────────────


def test_realm_derive_independent_effects_root_steer_queue(tmp_path):
    from madcop.harness.realm import SessionRealm
    from madcop.server.steer_queue import push_steer, clear_steers

    sid = "realm-derive-test"
    clear_steers(sid)
    root = SessionRealm.root(sid)
    child = root.derive()

    assert child.effects_prefix != root.effects_prefix
    assert root.effect_key("u1") != child.effect_key("u1")

    # A steer steers the whole thread: the CHILD drains the ROOT queue.
    assert push_steer(sid, "先跑测试")["ok"]
    assert child.drain_steers() == ["先跑测试"]
    assert root.drain_steers() == []
    clear_steers(sid)


def test_realm_revert_all_restores_written_file(tmp_path):
    from madcop.harness.realm import SessionRealm
    from madcop.harness.effects import STORE, make_file_restore_inverse

    target = tmp_path / "f.txt"
    target.write_text("orig")
    root = SessionRealm.root("realm-revert-test")
    inv = make_file_restore_inverse(str(target))
    STORE.register(root.effect_key("use-1"), "write f.txt", inv)
    target.write_text("overwritten")

    report = root.revert_all()
    assert report["applied"] == 1
    assert target.read_text() == "orig"


def test_realm_dispose_clears_namespace(tmp_path):
    from madcop.harness.realm import SessionRealm
    from madcop.harness.effects import STORE

    root = SessionRealm.root("realm-dispose-test")
    key = root.effect_key("use-2")
    STORE.register(key, "effect", lambda: None)
    assert STORE.peek(key)
    root.dispose()
    assert STORE.peek(key) == []


def test_runcontext_derive_forks_realm():
    from madcop.harness.realm import SessionRealm

    root_realm = SessionRealm.root("derive-fork-test")
    parent = RunContext(
        messages=[Message(role="user", content="hi")], realm=root_realm)
    child = parent.derive()

    assert child.realm is not root_realm
    assert child.realm is not parent.realm
    # The child keeps draining the ROOT conversation's steer queue.
    assert child.realm.steer_session == root_realm.steer_session
    assert child.realm.effects_prefix != root_realm.effects_prefix


# ─── react_v4 steer drain + mid-turn auto-compact ────────────────────────


class _TextStream:
    """One plain-text answer round; records every LLM call's messages."""

    def __init__(self):
        self.calls: list[list] = []

    def stream(self, messages, model=None, temperature=0.1,
               max_tokens=2048, tools=None):
        self.calls.append(list(messages))
        yield SimpleNamespace(text="搜索完成，这是答案内容。", finish_reason=None)
        yield SimpleNamespace(text="", finish_reason="stop")


def test_react_v4_drains_steer_into_llm_context(monkeypatch):
    from madcop.agent.react_v4 import ReActEngineV4
    from madcop.server.steer_queue import push_steer, clear_steers

    sid = "react-steer-test"
    clear_steers(sid)
    assert push_steer(sid, "重点检查性能问题")["ok"]

    fake = _TextStream()
    ctx = RunContext(
        messages=[Message(role="user", content="开始吧")],
        model="fake", agent_mode="standard", client=fake,
        session_id=sid,
    )
    steps = list(ReActEngineV4().run(ctx))

    assert StepKind.STEER_INJECTED in [s.kind for s in steps]
    # The injected user message reached THIS turn's LLM call.
    assert any(
        m.role == "user" and "用户中途指引" in (m.content or "")
        and "重点检查性能问题" in (m.content or "")
        for m in fake.calls[0]
    )
    clear_steers(sid)


class _ToolThenAnswerStream:
    """`tool_rounds` rounds of native tool calls (distinct names), then a
    plain answer. Every round reports usage with a large prompt_tokens so
    the token-driven compact trigger fires mid-run."""

    _TOOL_TEXTS = [
        "tool_a", "tool_b", "tool_c", "tool_d",
        "tool_e", "tool_f", "tool_g", "tool_h",
    ]

    def __init__(self, tool_rounds: int = 8):
        self.tool_rounds = tool_rounds
        self.calls = 0

    def stream(self, messages, model=None, temperature=0.1,
               max_tokens=2048, tools=None):
        self.calls += 1
        if self.calls <= self.tool_rounds:
            name = self._TOOL_TEXTS[(self.calls - 1) % len(self._TOOL_TEXTS)]
            yield SimpleNamespace(
                tool_call_deltas=({"index": 0, "id": f"t{self.calls}",
                                   "name": name, "arguments": "{}"},),
                text="", finish_reason=None)
            yield SimpleNamespace(text="", finish_reason="tool_calls")
            yield SimpleNamespace(
                text="", finish_reason=None,
                usage=SimpleNamespace(prompt_tokens=5000,
                                      completion_tokens=10, total_tokens=5010))
        else:
            yield SimpleNamespace(text="全部完成，这是最终回答。", finish_reason=None)
            yield SimpleNamespace(text="", finish_reason="stop")
            yield SimpleNamespace(
                text="", finish_reason=None,
                usage=SimpleNamespace(prompt_tokens=5000,
                                      completion_tokens=10, total_tokens=5010))


def test_react_v4_mid_turn_auto_compact(monkeypatch):
    from madcop.agent import react_v4
    from madcop.agent.react_v4 import ReActEngineV4
    monkeypatch.setenv("MADCOP_COMPACT_TRIGGER_TOKENS", "10")

    # Spy on the compactor to prove the transcript (message count) shrank.
    orig_compact = react_v4.ReActEngineV4._maybe_compact
    lens: list[tuple[int, int]] = []

    def _spy(messages, *a, **k):
        before = len(messages)
        out = orig_compact(messages, *a, **k)
        lens.append((before, len(messages)))
        return out

    monkeypatch.setattr(ReActEngineV4, "_maybe_compact", staticmethod(_spy))

    fake = _ToolThenAnswerStream(tool_rounds=8)
    ctx = RunContext(
        messages=[Message(role="user", content="做多步构建")],
        model="fake", agent_mode="standard", client=fake,
    )
    ctx.tool_executor = lambda *a, **k: '{"ok": true}'

    steps = list(ReActEngineV4().run(ctx))
    compacts = [s for s in steps if s.kind == StepKind.CONTEXT_COMPACT]
    assert compacts, "expected a mid-turn CONTEXT_COMPACT step"
    assert compacts[0].metadata["prompt_tokens"] >= compacts[0].metadata["trigger_tokens"]
    # The transcript actually shrank (fewer messages after the compact).
    assert any(b > a for b, a in lens)
    assert [s.kind for s in steps][-1] == StepKind.DONE


# ─── approval-scope store hardening (corrupt file + legacy entries) ──────


def test_load_approval_scopes_corrupt_file_backed_up(tmp_path, monkeypatch):
    import madcop.server.routes.chat_v4 as chat_v4
    f = tmp_path / "approval_scopes.json"
    f.write_text("{ this is not json !!")
    monkeypatch.setattr(chat_v4, "_APPROVAL_SCOPES_FILE", f)
    monkeypatch.delitem(chat_v4._SESSION_APPROVED, "corrupt-sid", raising=False)

    # Must not raise; the corrupt file is preserved for forensics.
    chat_v4._load_approval_scopes("corrupt-sid")
    assert chat_v4._SESSION_APPROVED.get("corrupt-sid", set()) == set()
    backups = list(tmp_path.glob("approval_scopes.json.corrupt-*"))
    assert len(backups) == 1
    assert not f.exists()

    # Save rebuilds the store from empty.
    chat_v4._SESSION_APPROVED["corrupt-sid"] = {"dir:/tmp/x"}
    chat_v4._save_approval_scopes("corrupt-sid")
    assert json.loads(f.read_text())["corrupt-sid"] == ["dir:/tmp/x"]


def test_load_approval_scopes_migrates_legacy_tool_dir(tmp_path, monkeypatch):
    import madcop.server.routes.chat_v4 as chat_v4
    f = tmp_path / "approval_scopes.json"
    f.write_text(json.dumps({
        "legacy-sid": ["write_file:/Users/x/proj", "dir:/Users/y/other"],
    }))
    monkeypatch.setattr(chat_v4, "_APPROVAL_SCOPES_FILE", f)
    monkeypatch.delitem(chat_v4._SESSION_APPROVED, "legacy-sid", raising=False)

    chat_v4._load_approval_scopes("legacy-sid")
    assert chat_v4._SESSION_APPROVED["legacy-sid"] == {
        "dir:/Users/x/proj", "dir:/Users/y/other",
    }


# ─── MEA _recent_trajectory (Manager sees real observations) ─────────────


def test_mea_recent_trajectory_includes_tool_events():
    from madcop.harness.core import SessionLog, tool_event
    from madcop.harness.mea_loop import MadCopHarness

    log = SessionLog()  # in-memory
    log.append(tool_event("tool_call", "", tool_name="write_file"))
    log.append(tool_event("tool_result", "wrote 128 bytes to out.html",
                          tool_name="write_file"))

    ctx = RunContext(messages=[], model="fake", agent_mode="task",
                     client=None)
    harness = MadCopHarness(ctx, max_steps=2, shared_log=log)
    traj = harness._recent_trajectory()

    assert "write_file" in traj
    assert "wrote 128 bytes to out.html" in traj
    # Result lines are marked with ←, calls with →.
    assert "← write_file" in traj
