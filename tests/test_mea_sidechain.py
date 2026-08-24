"""P2-11 — MEA executor runs as an isolated sidechain subagent.

The Coder gets a FRESH context (goal + contract only, never the main
history); its full trajectory lands in a dedicated sidechain log; the
main log receives only the bounded subagent_result summary.
"""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import madcop.harness.mea_loop as ml
import madcop.harness.core as hc
from madcop.agent.runtime import RunContext
from madcop.harness.core import SessionLog, HarnessEvent, EventDomain
from madcop.llm.client import Message


class _CoderClient:
    """Manager contract → coder tool call → tester verdict → complete."""

    def __init__(self):
        self.last_coder_ctx: list[str] = []

    def stream(self, messages, model=None, temperature=0.1, max_tokens=2048, tools=None):
        self.last_coder_ctx = [m.content for m in messages if m.role == "user"]
        yield SimpleNamespace(
            tool_call_deltas=({"index": 0, "id": "t", "name": "write_file",
                                "arguments": '{"path": "/tmp/a.txt", "content": "hi"}'},),
            text="", finish_reason=None)
        yield SimpleNamespace(text="文件已写入。", finish_reason=None)
        yield SimpleNamespace(text="", finish_reason="stop")

    def chat(self, messages, model=None, temperature=0.3, max_tokens=400):
        text = messages[-1].content or ""
        if "子任务" in text or "subtask" in text.lower():
            return SimpleNamespace(content='{"description": "写 a.txt", "acceptance_criteria": "文件存在"}')
        if "verify" in text.lower() or "审" in text:
            return SimpleNamespace(content='{"status": "complete", "notes": "ok"}')
        return SimpleNamespace(content='{"description": "TASK_COMPLETE"}')


def _read_jsonl(path: Path) -> list[HarnessEvent]:
    """Read a JSONL log file directly (bypass the loader's hard-coded root)."""
    out: list[HarnessEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        data = json.loads(line)
        out.append(HarnessEvent(
            id=data.get("id") or "",
            domain=EventDomain(data.get("domain", "system")),
            kind=data.get("kind", ""),
            content=data.get("content", ""),
            metadata=data.get("metadata", {}) or {},
            timestamp=data.get("timestamp", 0),
            parent_id=data.get("parent_id"),
        ))
    return out


class TestSidechainIsolation(unittest.TestCase):

    def test_sidechain_and_summary(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            with mock.patch.object(ml, "_HARNESS_ROOT", root), \
                 mock.patch.object(hc, "_HARNESS_ROOT", root):
                client = _CoderClient()
                main_log = SessionLog("main-x", persist_dir=root)
                ctx = RunContext(
                    messages=[Message(role="user", content="做个工具")],
                    model="f", agent_mode="task", client=client,
                )
                ctx.tool_executor = lambda *a, **k: '{"ok": true}'
                harness = ml.MadCopHarness(ctx, max_steps=3, shared_log=main_log)
                list(harness.run())

            # Sidechain log created under the patched root
            sc_files = sorted(root.glob("main-x-sc*/log.jsonl"))
            self.assertTrue(sc_files, f"no sidechain log written; saw: {list(root.glob('**/*.jsonl'))}")
            sc = _read_jsonl(sc_files[0])
            kinds = [e.kind for e in sc]
            self.assertIn("sidechain_of", kinds)
            self.assertIn("tool_start", kinds)
            self.assertGreater(len(sc), 1)

            # Main log: bounded subagent_result summary
            main_reloaded = _read_jsonl(root / "main-x" / "log.jsonl")
            main_kinds = [e.kind for e in main_reloaded]
            self.assertIn("subagent_result", main_kinds)

            # Coder context contains goal + contract, not main history
            coder_text = " ".join(client.last_coder_ctx)
            self.assertIn("做个工具", coder_text)
            self.assertIn("子任务合约", coder_text)


if __name__ == "__main__":
    unittest.main()