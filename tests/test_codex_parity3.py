"""Codex-parity batch 3 — seek_sequence edit, get_context_remaining,
shell snapshot, compaction hooks.

Ported-verbatim algorithm (codex-rs/apply-patch seek_sequence.rs) gets
polarity tests on all four tiers; the tools get registry-wiring and
behaviour tests; compaction hooks get fired/not-fired coverage.
"""
from __future__ import annotations

import json

import pytest

from madcop.tools.files import EditFileTool, _seek_sequence


# ── #1 seek_sequence (codex apply-patch port) ─────────────────────────────

def test_seek_exact_match():
    lines = ["foo", "bar", "baz"]
    assert _seek_sequence(lines, ["bar", "baz"]) == (1, "exact")


def test_seek_rstrip_tier():
    lines = ["foo   ", "bar\t\t", "baz"]
    idx, tier = _seek_sequence(lines, ["foo", "bar"])
    assert idx == 0 and tier == "rstrip"


def test_seek_trim_tier():
    lines = ["  foo", "  bar"]
    idx, tier = _seek_sequence(lines, ["foo", "bar"])
    assert idx == 0 and tier == "trim"


def test_seek_unicode_punctuation_tier():
    # File contains smart quotes + em dash + full-width space; anchor
    # authored as plain ASCII must still land (tier 4).
    lines = ["\u201chello\u201d", "x \u2014 y", "\u3000indented"]
    idx, tier = _seek_sequence(lines, ['"hello"', "x - y", " indented"])
    assert idx == 0 and tier == "unicode"


def test_seek_no_match_and_short_pattern():
    assert _seek_sequence(["a", "b"], ["zzz"])[0] is None
    assert _seek_sequence(["a", "b"], [])[0] == 0
    assert _seek_sequence(["a"], ["a", "b"])[0] is None  # pattern > lines


def test_edit_file_fuzzy_rescues_whitespace_anchor(tmp_path):
    f = tmp_path / "code.js"
    f.write_text("function a() {\n\treturn 1;   \n}\n", encoding="utf-8")
    tool = EditFileTool(allowed_dirs=[tmp_path])
    # Multi-line anchor with a bare trailing brace: the exact substring
    # fails (the file line has trailing spaces after "1;"), the trim
    # tier rescues it.
    out = tool(path=str(f), old_text="return 1;\n}", new_text="return 2;\n}")
    assert out.get("status") == "ok", out
    assert out.get("match") == "trim"
    assert "return 2;" in f.read_text()


def test_edit_file_unicode_anchor(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("标题：\u201c台风季\u201d\n正文一行\n", encoding="utf-8")
    tool = EditFileTool(allowed_dirs=[tmp_path])
    out = tool(path=str(f), old_text='标题："台风季"', new_text='标题："洪水季"')
    assert out.get("status") == "ok" and out.get("match") == "unicode"
    assert "洪水季" in f.read_text()


def test_edit_file_not_found_error(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("hello\n", encoding="utf-8")
    tool = EditFileTool(allowed_dirs=[tmp_path])
    out = tool(path=str(f), old_text="zzzz", new_text="y")
    assert "error" in out


# ── #2 get_context_remaining ──────────────────────────────────────────────

def test_budget_tool_reads_usage_store():
    from madcop.agent import usage_store
    from madcop.tools.context_budget import GetContextRemainingTool
    usage_store.record_usage("s-budget", {"prompt_tokens": 1000,
                                          "completion_tokens": 50})
    tool = GetContextRemainingTool(session_id="s-budget", context_window=8000)
    out = tool()
    assert out["tokens_left"] == 7000
    assert out["prompt_tokens"] == 1000
    assert "偏小" not in out["note"]
    # Low budget → advisory note flips on.
    tool2 = GetContextRemainingTool(session_id="s-budget", context_window=1100)
    assert "偏小" in tool2()["note"]
    usage_store.drop_session("s-budget")


def test_budget_tool_registered_and_safe():
    from madcop.agent.tool_executor import build_default_registry
    from madcop.tools.safety import danger_level
    reg, _exec = build_default_registry(bound_keys=set())
    assert reg.get("get_context_remaining") is not None
    assert danger_level("get_context_remaining") == "safe"
    schemas = reg.visible_schemas(set(), phase="all")
    assert any(
        (s.get("function") or {}).get("name") == "get_context_remaining"
        for s in schemas
    )


# ── #3 shell snapshot ─────────────────────────────────────────────────────

def test_snapshot_ensure_and_wrap(tmp_path, monkeypatch):
    from madcop.tools import shell_snapshot as ss
    monkeypatch.setattr(ss, "SNAPSHOT_DIR", tmp_path)
    snap = ss.ensure_snapshot("sess-snap", force=True)
    if snap is None:  # no usable shell in environment — skip gracefully
        pytest.skip("no user shell available")
    p = tmp_path / "sess-snap.sh"
    assert p.exists() and p.stat().st_size >= 0
    # TTL cache: second call returns same path without regenerating.
    assert ss.ensure_snapshot("sess-snap") == str(p)
    assert ss.wrap_command("ls -la", str(p)).startswith(". '")
    assert ss.wrap_command("ls", None) == "ls"


def test_snapshot_filters_pwd_exports(monkeypatch):
    from madcop.tools import shell_snapshot as ss
    text = "export HOME=/x\nexport PWD=/now\ndeclare -x OLDPWD=/old\nalias ll='ls -l'\n"
    out = ss._filter_exports(text)
    assert "PWD=" not in out and "OLDPWD=" not in out
    assert "export HOME=/x" in out and "alias ll" in out


def test_bash_tool_sources_snapshot_in_shell_mode(tmp_path, monkeypatch):
    from madcop.tools.sandbox import BashTool, SubprocessSandbox
    calls = {}

    def fake_provider():
        snap = tmp_path / "snap.sh"
        snap.write_text("export SNAPPED=1\n", encoding="utf-8")
        calls["snap"] = str(snap)
        return str(snap)

    sandbox = SubprocessSandbox(allowed_dirs=[tmp_path], shell=True)
    tool = BashTool(sandbox, snapshot_provider=fake_provider)
    out = tool(command="echo $SNAPPED", cwd=str(tmp_path))
    assert out["returncode"] == 0
    assert "1" in (out["stdout"] or "")
    # Non-shell sandbox → no snapshot prefix attempted.
    plain = BashTool(SubprocessSandbox(allowed_dirs=[tmp_path]))
    out2 = plain(command="echo hi", cwd=str(tmp_path))
    assert out2["returncode"] == 0


# ── #4 compaction lifecycle hooks ─────────────────────────────────────────

class _RecordingChain:
    def __init__(self):
        self.events = []

    def run(self, ctx):
        self.events.append(ctx)
        from madcop.agent.hooks import HookResult
        return HookResult()


def test_compaction_hooks_fire_with_chain():
    from madcop.agent.compaction import fire_pre_compact, fire_post_compact
    chain = _RecordingChain()
    fire_pre_compact(chain, trigger="auto", prompt_tokens=123)
    fire_post_compact(chain, trigger="auto", record={"summary": "s", "head_turns": 2})
    kinds = [e.event for e in chain.events]
    assert kinds == ["PreCompact", "PostCompact"]
    assert chain.events[0].metadata["prompt_tokens"] == 123
    assert chain.events[1].metadata["summary"] == "s"
    # None chain must be a silent no-op.
    fire_pre_compact(None, trigger="auto")
    fire_post_compact(None, trigger="manual", record={})


def test_compact_messages_force(tmp_path):
    from madcop.agent.compaction import compact_messages

    class FakeResp:
        content = "## 目标\n测试"

    class FakeClient:
        def chat(self, messages, **kwargs):
            return FakeResp()

    msgs = [{"role": "user", "content": f"turn {i}"} for i in range(6)]
    # Not forced: everything fits the keep-recent budget → no compaction.
    _, rec = compact_messages(msgs, FakeClient(), "m", keep_recent_tokens=100000)
    assert rec.get("compacted") is False
    # Forced (manual): summarizes even a small history, keeps last 2.
    new_msgs, rec2 = compact_messages(
        msgs, FakeClient(), "m", keep_recent_tokens=100000, force=True)
    assert rec2.get("compacted") is True
    assert len(new_msgs) == 3  # summary + last 2
    assert new_msgs[-1]["content"] == "turn 5"


# ── printed-clarify rescue (react_v4) ─────────────────────────────────────

def test_extract_clarify_bare_object():
    from madcop.agent.react_v4 import _extract_clarify
    text = '{"clarify":true,"question":"你想查哪个城市的天气？ ","options":["北京","上海","深圳","杭州","自定义"]}'
    out = _extract_clarify(text)
    assert out is not None
    q, opts, rest = out
    assert "哪个城市" in q
    assert "北京" in opts and "自定义" in opts
    assert rest == ""


def test_extract_clarify_wrapped_array():
    from madcop.agent.react_v4 import _extract_clarify
    text = '[{"clarify":true,"question":"查哪个城市？","options":["北京"]}]'
    q, opts, rest = _extract_clarify(text)
    assert q == "查哪个城市？" and opts == ["北京"] and rest == ""


def test_extract_clarify_ignores_embedded_fragment():
    from madcop.agent.react_v4 import _extract_clarify
    long_prose = "这是一段很长的正常回答，讨论天气的形成机制。" * 20
    text = long_prose + ' {"clarify":true,"question":"q","options":["a"]}'
    assert _extract_clarify(text) is None


def test_extract_clarify_no_blob():
    from madcop.agent.react_v4 import _extract_clarify
    assert _extract_clarify("普通回答，没有 JSON。") is None
