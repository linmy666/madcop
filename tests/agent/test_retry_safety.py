"""P1-8 — typed retry + replay safety.

Connection-level stream failures (zero chunks) retry with backoff;
mid-stream failures propagate as categorized, user-replayable errors —
the engine never auto-restarts a half-delivered stream.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from madcop.agent.runtime import RunContext, StepKind
from madcop.llm.client import Message
from madcop.llm.retry import classify_stream_error, stream_with_retry


class TestClassification(unittest.TestCase):

    def test_categories(self):
        cases = [
            (Exception("The read operation timed out"), "timeout", True),
            (Exception("Error code: 429 — rate limit exceeded"), "rate_limit", True),
            (Exception("Error code: 401 invalid api key"), "auth", False),
            (Exception("This model's maximum context length is 4096"), "context_length", False),
            (Exception("503 overloaded"), "server", True),
            (Exception("Connection error"), "network", True),
            (Exception("some weird failure"), "other", False),
        ]
        for exc, cat, retryable in cases:
            info = classify_stream_error(exc)
            self.assertEqual(info.category, cat, exc)
            self.assertEqual(info.retryable, retryable, exc)

    def test_retry_after_parsed(self):
        info = classify_stream_error(Exception("429 rate limit; retry-after: 7"))
        self.assertEqual(info.retry_after_s, 7.0)


class _FlakyStream:
    """Fails N times with zero chunks, then streams normally."""

    def __init__(self, fail_times: int, exc: Exception, then_fail_midstream=False):
        self.fail_times = fail_times
        self.exc = exc
        self.then_fail_midstream = then_fail_midstream
        self.attempts = 0

    def stream(self, messages, model=None, temperature=0.1, max_tokens=2048, tools=None):
        self.attempts += 1
        if self.attempts <= self.fail_times:
            raise self.exc
        yield SimpleNamespace(text="第一段", finish_reason=None)
        if self.then_fail_midstream:
            raise self.exc
        yield SimpleNamespace(text="第二段", finish_reason="stop")


class TestStreamRetry(unittest.TestCase):

    def test_zero_chunk_failure_retries(self):
        flaky = _FlakyStream(2, Exception("Connection error"))
        out = list(stream_with_retry(lambda: flaky.stream([]), max_retries=3))
        self.assertEqual(len(out), 2)
        self.assertEqual(flaky.attempts, 3)

    def test_midstream_failure_propagates(self):
        flaky = _FlakyStream(0, Exception("503 overloaded"), then_fail_midstream=True)
        got = []
        with self.assertRaises(Exception):
            for c in stream_with_retry(lambda: flaky.stream([]), max_retries=3):
                got.append(c)
        # First chunk was delivered, then the failure surfaced —
        # exactly one attempt (no silent replay).
        self.assertEqual(flaky.attempts, 1)
        self.assertEqual(len(got), 1)

    def test_non_retryable_propagates_immediately(self):
        flaky = _FlakyStream(5, Exception("Error code: 401 invalid api key"))
        with self.assertRaises(Exception):
            list(stream_with_retry(lambda: flaky.stream([]), max_retries=3))
        self.assertEqual(flaky.attempts, 1)


class TestEngineErrorMetadata(unittest.TestCase):

    def test_engine_error_carries_category(self):
        from madcop.agent.react_v4 import ReActEngineV4

        class _AlwaysConnFail:
            def stream(self, *a, **k):
                raise Exception("Connection error")
                yield  # pragma: no cover

        ctx = RunContext(
            messages=[Message(role="user", content="你好")],
            model="f", agent_mode="standard", client=_AlwaysConnFail(),
        )
        steps = list(ReActEngineV4().run(ctx))
        errs = [s for s in steps if s.kind == StepKind.ERROR]
        self.assertEqual(len(errs), 1)
        self.assertEqual(errs[0].metadata.get("error_category"), "network")
        self.assertFalse(errs[0].metadata.get("replay_safe"))


if __name__ == "__main__":
    unittest.main()
