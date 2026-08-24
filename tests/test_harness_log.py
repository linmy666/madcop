"""Phase 2b — SessionLog + derive_messages tests.

Covers: JSONL round-trip, for_session reload, derive_messages against the
event shapes chat_v4 and mea_loop actually write, reasoning exclusion,
and tool pair rendering.
"""
from __future__ import annotations

import json

from madcop.harness.core import (
    SessionLog, EventDomain,
    reasoning_event, tool_event, answer_event, system_event,
)


def _simulate_chat_turn(log: SessionLog, user_text: str, answer: str) -> None:
    """Write events in the exact shape chat_v4's worker writes."""
    log.append(system_event("turn_start", user_text))
    # reasoning (must be excluded from derived context)
    log.append(reasoning_event("thought_start", ""))
    log.append(reasoning_event("thought_delta", "internal reasoning here"))
    log.append(reasoning_event("thought_end", ""))
    # tool pair
    log.append(tool_event("tool_call", "", tool_name="web_search"))
    log.append(tool_event("tool_result", '[{"title": "hit"}]'))
    # answer (streamed as deltas)
    for chunk in (answer[:10], answer[10:20], answer[20:]):
        if chunk:
            log.append(answer_event("text_delta", chunk))
    log.append(answer_event("done", ""))
    log.append(system_event("turn_end", ""))


def test_jsonl_roundtrip(tmp_path, monkeypatch):
    import madcop.harness.core as core
    monkeypatch.setattr(core, "_HARNESS_ROOT", tmp_path)

    log = SessionLog.for_session("rt1")
    log.append(system_event("turn_start", "hello"))
    log.append(answer_event("text_delta", "world"))

    # reopen from disk via for_session (the reload path)
    log2 = SessionLog.for_session("rt1")
    assert len(log2.events()) == 2
    assert log2.events()[0].content == "hello"
    assert log2.events()[1].domain == EventDomain.ANSWER


def test_for_session_reloads_prior_turns(tmp_path, monkeypatch):
    import madcop.harness.core as core
    monkeypatch.setattr(core, "_HARNESS_ROOT", tmp_path)

    log = SessionLog.for_session("sess-abc")
    _simulate_chat_turn(log, "Q1", "A1 answer text")
    assert len(log.events()) > 0

    # New instance (e.g. next HTTP request) must see prior events.
    log2 = SessionLog.for_session("sess-abc")
    assert any(e.kind == "turn_start" and e.content == "Q1" for e in log2.events())
    msgs = log2.derive_messages()
    assert msgs[0] == {"role": "user", "content": "Q1"}


def test_derive_messages_shape():
    log = SessionLog()  # in-memory only
    _simulate_chat_turn(log, "什么是递归", "递归是函数调用自身的技巧。")

    msgs = log.derive_messages()
    roles = [m["role"] for m in msgs]

    # Expected: user → assistant(tool note) → user(observation) → assistant
    assert roles[0] == "user"
    assert msgs[0]["content"] == "什么是递归"
    assert "assistant" in roles
    # Final assistant message reconstructs the streamed answer
    final_assistant = [m for m in msgs if m["role"] == "assistant"][-1]
    assert "递归是函数调用自身的技巧。" in final_assistant["content"]


def test_derive_messages_excludes_reasoning():
    log = SessionLog()
    log.append(system_event("turn_start", "q"))
    log.append(reasoning_event("thought_delta", "SECRET_CHAIN_OF_THOUGHT"))
    log.append(answer_event("text_delta", "public answer"))
    log.append(system_event("turn_end", ""))

    msgs = log.derive_messages()
    flat = " ".join(m["content"] for m in msgs)
    assert "SECRET_CHAIN_OF_THOUGHT" not in flat, "reasoning leaked into context!"
    assert "public answer" in flat


def test_derive_messages_tool_pair_valid_sequence():
    """Tool events are EXCLUDED from derived context — they're execution
    details, not conversation. Including them made the model echo
    '[used tool: web_search]' instead of making real tool calls."""
    log = SessionLog()
    log.append(system_event("turn_start", "search it"))
    log.append(tool_event("tool_call", "", tool_name="web_search"))
    log.append(tool_event("tool_result", "results here"))
    log.append(answer_event("text_delta", "based on results"))
    log.append(system_event("turn_end", ""))

    msgs = log.derive_messages()
    roles = [m["role"] for m in msgs]
    # Clean user/assistant alternation; no tool annotations at all.
    assert roles == ["user", "assistant"]
    flat = " ".join(m["content"] for m in msgs)
    assert "web_search" not in flat, "tool annotation leaked into context!"
    assert "results here" not in flat, "raw tool result leaked!"
    assert "based on results" in msgs[1]["content"]


def test_multi_turn_derive():
    log = SessionLog()
    _simulate_chat_turn(log, "Q1", "Answer one")
    _simulate_chat_turn(log, "Q2", "Answer two")

    msgs = log.derive_messages()
    user_turns = [m for m in msgs if m["role"] == "user" and m["content"].startswith("Q")]
    assert len(user_turns) == 2
    # Q2 comes after Q1's answer
    idx_q1 = next(i for i, m in enumerate(msgs) if m["content"] == "Q1")
    idx_q2 = next(i for i, m in enumerate(msgs) if m["content"] == "Q2")
    assert idx_q2 > idx_q1


def test_corrupt_jsonl_line_does_not_crash(tmp_path, monkeypatch):
    import madcop.harness.core as core
    monkeypatch.setattr(core, "_HARNESS_ROOT", tmp_path)

    log = SessionLog.for_session("corrupt")
    log.append(system_event("turn_start", "good"))
    # append a garbage line directly to the file
    p = tmp_path / "corrupt" / "log.jsonl"
    with open(p, "a", encoding="utf-8") as f:
        f.write("{not valid json\n")

    log2 = SessionLog.for_session("corrupt")  # must not raise
    assert any(e.content == "good" for e in log2.events())


# ═══════════════════════════════════════════════════════════════════════
# P2-10 — session tree: parent chain, fork, crash recovery
# ═══════════════════════════════════════════════════════════════════════

import unittest
from pathlib import Path
class TestSessionTree(unittest.TestCase):
    def _write_turns(self, tmpdir, sid, turns):
        log = SessionLog.for_session(sid) if False else SessionLog(sid, persist_dir=Path(tmpdir))
        for user, ans in turns:
            log.append(system_event("turn_start", user))
            log.append(answer_event("text_delta", ans))
            log.append(system_event("turn_end", ""))
        return log

    def test_parent_chain_autolinked(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            log = self._write_turns(d, "chain", [("q1", "a1")])
            evs = log.events()
            self.assertIsNone(evs[0].parent_id)
            for prev, cur in zip(evs, evs[1:]):
                self.assertEqual(cur.parent_id, prev.id)

    def test_fork_snaps_to_turn_boundary_and_preserves_ids(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            log = self._write_turns(d, "src", [("q1", "a1"), ("q2", "a2")])
            log.append(system_event("turn_start", "q3"))  # half-finished turn
            log.append(answer_event("text_delta", "a3-partial"))

            fork = SessionLog.fork_session("src", source=log)  # no target → last complete turn
            # forked under a fresh fork- id with lineage marker
            self.assertTrue(fork.run_id.startswith("fork-"))
            kinds = [e.kind for e in fork.events()]
            self.assertIn("forked_from", kinds)
            # q3's partial events did NOT carry over
            contents = [e.content for e in fork.events()]
            self.assertFalse(any("q3" in c for c in contents))
            self.assertFalse(any("a3-partial" in c for c in contents))
            # event ids preserved (stable replay)
            src_ids = {e.id for e in log.events() if e.kind != "turn_start" or e.content != "q3"}
            fork_ids = {e.id for e in fork.events()}
            self.assertTrue(src_ids & fork_ids)
            # derive works on the fork
            msgs = fork.derive_messages()
            self.assertTrue(any("q2" in m["content"] for m in msgs))
            self.assertFalse(any("q3" in m["content"] for m in msgs))

    def test_fork_at_specific_event(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            log = self._write_turns(d, "src2", [("q1", "a1"), ("q2", "a2")])
            first_turn_end = next(e for e in log.events()
                                  if e.kind == "turn_end")
            # target an event in turn 2 → snap back to turn 1's end
            t2_start = next(e for e in log.events()
                            if e.kind == "turn_start" and e.content == "q2")
            fork = SessionLog.fork_session("src2", t2_start.id, source=log)
            msgs = fork.derive_messages()
            self.assertTrue(any("q1" in m["content"] for m in msgs))
            self.assertFalse(any("q2" in m["content"] for m in msgs))

    def test_unclosed_turn_hint(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            log = self._write_turns(d, "crash", [("q1", "a1")])
            self.assertIsNone(log.unclosed_turn())
            log.append(system_event("turn_start", "died here"))
            self.assertEqual(log.unclosed_turn(), "died here")
