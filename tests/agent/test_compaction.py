"""P1-6 — token-driven compaction (pi-mono design).

Covers: cut-point selection (user-message boundary, keep-recent
budget), threshold triggering (provider usage wins over estimate),
compaction-event replay in derive_messages, and checkpoint prompts
(first-time vs incremental UPDATE).
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from madcop.agent import compaction as C
from madcop.harness.core import (
    SessionLog, EventDomain, HarnessEvent,
    reasoning_event, answer_event, system_event, tool_event,
)


class TestCutPoint(unittest.TestCase):

    def _msgs(self, n: int, chars: int = 400):
        out = []
        for i in range(n):
            role = "user" if i % 2 == 0 else "assistant"
            out.append({"role": role, "content": "x" * chars})
        return out

    def test_cut_at_user_boundary(self):
        msgs = self._msgs(40)  # ~400 tokens/msg → 16k total
        cut = C.select_cut_point(msgs, keep_recent_tokens=3000)
        self.assertGreater(cut, 0)
        self.assertLess(cut, len(msgs))
        # The cut is at a user message (no orphaned assistant turn).
        self.assertEqual(msgs[cut]["role"], "user")

    def test_small_history_no_cut(self):
        msgs = self._msgs(4)
        self.assertEqual(C.select_cut_point(msgs, keep_recent_tokens=100000),
                         len(msgs))

    def test_degenerate_huge_messages_compact_all(self):
        """Even ONE message blows the budget → cut 0 (compact everything;
        the caller bumps 0 to 1 so the head is never empty)."""
        msgs = self._msgs(6, chars=10000)  # way over keep-recent
        cut = C.select_cut_point(msgs, keep_recent_tokens=100)
        self.assertEqual(cut, 0)


class TestThreshold(unittest.TestCase):

    def test_usage_wins_over_estimate(self):
        msgs = [{"role": "user", "content": "x" * 400}]  # ~100 tokens est
        # Provider says 120k prompt tokens → over 128k-16k threshold.
        self.assertTrue(C.should_compact(msgs, {"prompt_tokens": 120_000}))
        # Small usage + small estimate → fine.
        self.assertFalse(C.should_compact(msgs, {"prompt_tokens": 500}))

    def test_env_window_override(self):
        msgs = [{"role": "user", "content": "x" * 400_000}]  # ~100k est
        self.assertTrue(C.should_compact(msgs, None, context_window=50_000))


class _FakeSummarizer:
    """chat() returns a canned checkpoint summary; records the prompt."""

    def __init__(self, summary="## 目标\n做游戏\n## 进展\n已完成脚手架"):
        self.summary = summary
        self.prompts: list[str] = []

    def chat(self, messages, model=None, temperature=0.3, max_tokens=2000):
        self.prompts.append(messages[-1].content)
        return SimpleNamespace(content=self.summary)


class TestCompactMessages(unittest.TestCase):

    def test_first_time_checkpoint(self):
        msgs = [
            {"role": "user", "content": "做个游戏 " + "y" * 4000},
            {"role": "assistant", "content": "好的 " + "y" * 4000},
        ] * 20
        msgs.append({"role": "user", "content": "继续"})
        fake = _FakeSummarizer()
        new_msgs, record = C.compact_messages(msgs, fake, keep_recent_tokens=2000)
        self.assertTrue(record["compacted"])
        self.assertIn("目标", fake.prompts[0])          # checkpoint prompt
        self.assertNotIn("旧检查点", fake.prompts[0])   # first-time variant
        self.assertEqual(new_msgs[0]["role"], "user")
        self.assertIn("<summary>", new_msgs[0]["content"])
        self.assertIn("做游戏", new_msgs[0]["content"])  # summary surfaced
        self.assertEqual(new_msgs[-1]["content"], "继续")  # fresh turn kept

    def test_incremental_update_prompt(self):
        msgs = [{"role": "user", "content": "z" * 8000},
                {"role": "assistant", "content": "z" * 8000}] * 6
        fake = _FakeSummarizer()
        _, record = C.compact_messages(
            msgs, fake, prev_summary="## 目标\n旧目标", keep_recent_tokens=1500)
        self.assertTrue(record["compacted"])
        self.assertTrue(record["used_prev_summary"])
        self.assertIn("旧检查点", fake.prompts[0])       # UPDATE variant
        self.assertIn("旧目标", fake.prompts[0])

    def test_summary_failure_falls_back_not_raises(self):
        class _Boom:
            def chat(self, *a, **k):
                raise RuntimeError("no llm")

        msgs = [{"role": "user", "content": "z" * 8000},
                {"role": "assistant", "content": "z" * 8000}] * 6
        new_msgs, record = C.compact_messages(msgs, _Boom(), keep_recent_tokens=1500)
        self.assertTrue(record["compacted"])
        self.assertIn("<summary>", new_msgs[0]["content"])  # note kept


class TestDeriveWithCompaction(unittest.TestCase):

    def test_compaction_event_replaces_history(self):
        with tempfile.TemporaryDirectory() as d:
            log = SessionLog(Path(d) / "s.jsonl")
            # Turn 1-2 (old history)
            log.append(system_event("turn_start", "第一个问题"))
            log.append(answer_event("text_delta", "第一个回答"))
            log.append(system_event("turn_end", ""))
            # Compaction event (P1-6)
            log.append(HarnessEvent(
                domain=EventDomain.SYSTEM, kind="compaction",
                content="## 目标\n做游戏",
                metadata={"keep_tail_n": 1},
            ))
            # Turn 3 (post-compaction, survives)
            log.append(system_event("turn_start", "继续"))
            log.append(answer_event("text_delta", "好的，继续"))
            log.append(system_event("turn_end", ""))

            msgs = log.derive_messages()
            # [summary, tail(1: last pre-compaction assistant msg), turn-3 user+assistant]
            self.assertEqual(msgs[0]["role"], "user")
            self.assertIn("做游戏", msgs[0]["content"])
            self.assertIn("<summary>", msgs[0]["content"])
            # The pre-compaction user turn text is GONE (replaced by summary).
            self.assertFalse(any("第一个问题" in m["content"] for m in msgs))
            # The kept tail assistant message + post-compaction turns survive.
            self.assertTrue(any("第一个回答" in m["content"] for m in msgs))
            self.assertTrue(any("继续" in m["content"] for m in msgs))


class TestOverflowError(unittest.TestCase):

    def test_overflow_detection(self):
        self.assertTrue(C.is_overflow_error(
            Exception("This model's maximum context length is 4096 tokens")))
        self.assertTrue(C.is_overflow_error(Exception("prompt is too long: 200000 tokens")))
        self.assertFalse(C.is_overflow_error(Exception("connection error")))
        self.assertFalse(C.is_overflow_error(Exception("The read operation timed out")))


if __name__ == "__main__":
    unittest.main()


class TestThinkStrip(unittest.TestCase):
    """E2E regression: the summarizer's <think> leakage used to be stored
    verbatim in the checkpoint — after compaction the model lost ALL
    session facts because the summary was reasoning fragments."""

    def test_think_stripped_from_summary(self):
        class _Thinky:
            def chat(self, messages, model=None, temperature=0.3, max_tokens=2000):
                return SimpleNamespace(
                    content="<think>让我想想怎么合并……</think>\n\n## 目标\n做笔记应用 Phoenix")

        msgs = [{"role": "user", "content": "z" * 8000},
                {"role": "assistant", "content": "z" * 8000}] * 6
        new_msgs, record = C.compact_messages(msgs, _Thinky(), keep_recent_tokens=1500)
        self.assertNotIn("<think>", record["summary"])
        self.assertIn("Phoenix", record["summary"])

    def test_unclosed_think_truncated_generation(self):
        class _Truncated:
            def chat(self, *a, **k):
                return SimpleNamespace(content="## 目标\nX\n<think>未写完的推理")

        msgs = [{"role": "user", "content": "z" * 8000},
                {"role": "assistant", "content": "z" * 8000}] * 6
        _, record = C.compact_messages(msgs, _Truncated(), keep_recent_tokens=1500)
        self.assertNotIn("<think>", record["summary"])
        self.assertIn("X", record["summary"])
