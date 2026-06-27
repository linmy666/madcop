"""Tests for memory tools (LLM-managed memory: store/recall/forget)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from madcop.memory import MemoryStore, MemoryKind
from madcop.tools.memory import (
    StoreMemoryTool,
    RecallMemoryTool,
    ForgetMemoryTool,
    default_memory_tools,
)
from madcop.tools.registry import ToolResult


@pytest.fixture
def store(tmp_path: Path) -> MemoryStore:
    s = MemoryStore(path=tmp_path / "memory.db")
    yield s
    s.close()


# --------------------------------------------------------------------------- #
# StoreMemoryTool
# --------------------------------------------------------------------------- #

class TestStoreMemoryTool:
    def test_schema(self, store):
        tool = StoreMemoryTool(store)
        schema = tool.parameters_schema
        assert "fact" in schema["properties"]
        assert "fact" in schema["required"]

    def test_store_new_fact(self, store):
        tool = StoreMemoryTool(store)
        result = tool(fact="The user is a software engineer")
        assert "Stored memory" in result
        # Verify via FTS5
        rows = store._conn.execute(
            "SELECT * FROM memory_fts WHERE memory_fts MATCH 'engineer'"
        ).fetchall()
        assert any("software engineer" in r["content"] for r in rows)

    def test_store_auto_tags_user_profile(self, store):
        tool = StoreMemoryTool(store)
        tool(fact="User likes Python")
        rec = store._conn.execute(
            "SELECT * FROM memory_records WHERE content LIKE '%Python%'"
        ).fetchone()
        assert rec is not None
        assert "user-profile" in rec["tags"]

    def test_store_dedup_noop(self, store):
        tool = StoreMemoryTool(store)
        r1 = tool(fact="User lives in Hangzhou")
        r2 = tool(fact="User lives in Hangzhou")
        assert "Stored" in r1
        assert "noop" in r2.lower(), f"expected noop message, got: {r2}"
        # Verify only one record exists
        all_recs = store._conn.execute(
            "SELECT * FROM memory_records WHERE content LIKE '%Hangzhou%'"
        ).fetchall()
        assert len(all_recs) == 1

    def test_store_empty_fact_errors(self, store):
        tool = StoreMemoryTool(store)
        result = tool(fact="")
        assert "ERROR" in result or "required" in result.lower()

    def test_store_without_store_errors(self):
        tool = StoreMemoryTool(store=None)
        result = tool(fact="x")
        assert "ERROR" in result


# --------------------------------------------------------------------------- #
# RecallMemoryTool
# --------------------------------------------------------------------------- #

class TestRecallMemoryTool:
    def test_schema(self, store):
        tool = RecallMemoryTool(store)
        schema = tool.parameters_schema
        assert "query" in schema["properties"]
        assert "query" in schema["required"]

    def test_recall_existing(self, store):
        store.insert(
            kind=MemoryKind.SEMANTIC,
            title="User's job",
            content="User works as a backend engineer",
            tags=("user-profile",),
        )
        tool = RecallMemoryTool(store)
        result = tool(query="backend engineer")
        assert "Found" in result
        assert "backend engineer" in result

    def test_recall_no_results(self, store):
        tool = RecallMemoryTool(store)
        result = tool(query="nonexistent topic xyz")
        assert "No memories" in result

    def test_recall_empty_query_errors(self, store):
        tool = RecallMemoryTool(store)
        result = tool(query="")
        assert "ERROR" in result

    def test_recall_respects_limit(self, store):
        # Insert 10 facts
        for i in range(10):
            store.insert(
                kind=MemoryKind.SEMANTIC,
                title=f"fact {i}",
                content=f"The user knows fact number {i}",
                tags=("user-profile",),
            )
        tool = RecallMemoryTool(store, limit=3)
        result = tool(query="fact")
        # Count "Found" + count of bullet lines
        lines = result.split("\n")
        fact_lines = [l for l in lines if l.startswith("- [")]
        assert len(fact_lines) == 3


# --------------------------------------------------------------------------- #
# ForgetMemoryTool
# --------------------------------------------------------------------------- #

class TestForgetMemoryTool:
    def test_schema(self, store):
        tool = ForgetMemoryTool(store)
        schema = tool.parameters_schema
        assert "memory_id" in schema["properties"]
        assert "content_match" in schema["properties"]

    def test_forget_by_id(self, store):
        rec = store.insert(
            kind=MemoryKind.SEMANTIC,
            title="obsolete",
            content="The user used to live in Beijing",
            tags=("user-profile",),
        )
        tool = ForgetMemoryTool(store)
        result = tool(memory_id=rec.id)
        assert "Deleted" in result
        assert store.get(rec.id) is None

    def test_forget_by_content_match(self, store):
        store.insert(
            kind=MemoryKind.SEMANTIC,
            title="old fact",
            content="The user previously worked at Microsoft",
            tags=("user-profile",),
        )
        tool = ForgetMemoryTool(store)
        result = tool(content_match="Microsoft")
        assert "Deleted" in result
        remaining = store._conn.execute(
            "SELECT * FROM memory_records WHERE content LIKE '%Microsoft%'"
        ).fetchall()
        assert len(remaining) == 0

    def test_forget_by_id_not_found(self, store):
        tool = ForgetMemoryTool(store)
        result = tool(memory_id="nonexistent-id-12345")
        assert "No memory" in result or "ERROR" in result

    def test_forget_no_args_errors(self, store):
        tool = ForgetMemoryTool(store)
        result = tool()
        assert "ERROR" in result


# --------------------------------------------------------------------------- #
# default_memory_tools factory
# --------------------------------------------------------------------------- #

class TestDefaultMemoryTools:
    def test_returns_three_tools(self, store):
        tools = default_memory_tools(store)
        assert len(tools) == 3
        names = {t.name for t in tools}
        assert names == {"store_memory", "recall_memory", "forget_memory"}

    def test_all_tools_have_schemas(self, store):
        for tool in default_memory_tools(store):
            schema = tool.parameters_schema
            assert "type" in schema
            assert schema["type"] == "object"
            assert "properties" in schema


# --------------------------------------------------------------------------- #
# OpenAI schema integration
# --------------------------------------------------------------------------- #

def test_tools_have_openai_schemas(store):
    for tool in default_memory_tools(store):
        schema = tool.to_openai_schema()
        assert schema["type"] == "function"
        assert "function" in schema
        assert "name" in schema["function"]
        assert "parameters" in schema["function"]


# --------------------------------------------------------------------------- #
# UPDATE: StoreMemoryTool with supersedes param (Gap 2)
# --------------------------------------------------------------------------- #

class TestStoreMemoryUpdate:
    def test_supersedes_updates_existing(self, store):
        """Storing a fact that supersedes an older one updates in place."""
        from madcop.tools.memory import StoreMemoryTool
        tool = StoreMemoryTool(store)
        # First fact
        r1 = tool(fact="The user lives in Beijing")
        assert "Stored" in r1
        # Extract id from response
        import re
        m = re.search(r"id=([\w-]+)", r1)
        assert m, f"could not find id in: {r1}"
        old_id = m.group(1)
        # Supersede
        r2 = tool(fact="The user lives in Shanghai", supersedes=old_id)
        assert "Updated" in r2
        # Verify the old id now has the new content
        rows = store._conn.execute(
            "SELECT * FROM memory_records WHERE id = ?", (old_id,)
        ).fetchall()
        assert len(rows) == 1
        assert "Shanghai" in rows[0]["content"]
        # Verify no second record was created
        all_rows = store._conn.execute(
            "SELECT * FROM memory_records WHERE content LIKE '%lives in%'"
        ).fetchall()
        assert len(all_rows) == 1
        # Verify metadata was patched
        import json
        meta = json.loads(rows[0]["metadata"])
        assert "superseded_by" in meta
        assert "updated_fact" in meta

    def test_supersedes_unknown_id_errors(self, store):
        from madcop.tools.memory import StoreMemoryTool
        tool = StoreMemoryTool(store)
        result = tool(fact="something", supersedes="nonexistent-id-xyz")
        assert "ERROR" in result or "not found" in result


# --------------------------------------------------------------------------- #
# Gap 4: Temporal validity
# --------------------------------------------------------------------------- #

class TestStoreMemoryTemporal:
    def test_valid_for_days_sets_metadata(self, store):
        from madcop.tools.memory import StoreMemoryTool
        import json, time
        tool = StoreMemoryTool(store)
        result = tool(fact="User is in Shanghai for 7 days", valid_for_days="7")
        assert "Stored" in result
        # Find the record
        rec = store._conn.execute(
            "SELECT * FROM memory_records WHERE content LIKE '%Shanghai%'"
        ).fetchone()
        assert rec is not None
        meta = json.loads(rec["metadata"])
        assert "valid_until" in meta
        # Should expire roughly 7 days from now
        expected = time.time() + 7 * 86400
        assert abs(meta["valid_until"] - expected) < 5

    def test_invalid_valid_for_days_errors(self, store):
        from madcop.tools.memory import StoreMemoryTool
        tool = StoreMemoryTool(store)
        result = tool(fact="x", valid_for_days="not-a-number")
        assert "ERROR" in result


class TestExpiredMemoriesExcluded:
    def test_expired_memory_not_in_prompt(self, tmp_path):
        """An expired user-profile memory is excluded from the system prompt."""
        from madcop.tools.memory import StoreMemoryTool
        from madcop.memory import MemoryStore, MemoryKind
        from madcop.server.app import _build_memory_system_prompt, reset_memory_store
        import time, json, tempfile

        with tempfile.TemporaryDirectory() as td:
            store = MemoryStore(path=__import__("pathlib").Path(td) / "m.db")
            reset_memory_store(store)
            # Insert one fresh and one expired memory
            store.insert(
                kind=MemoryKind.SEMANTIC, title="fresh",
                content="User is in Beijing",
                tags=("user-profile",),
            )
            # Expired one
            expired_meta = json.dumps({"valid_until": time.time() - 3600})
            store.insert(
                kind=MemoryKind.SEMANTIC, title="expired",
                content="User is in Mars",
                tags=("user-profile",),
                metadata=expired_meta,
            )
            try:
                prompt = _build_memory_system_prompt(
                    "anything", profile_budget=2000, relevant_budget=2000, preferences_budget=2000
                )
                assert "Beijing" in prompt
                assert "Mars" not in prompt
            finally:
                store.close()
                reset_memory_store(None)  # type: ignore[arg-type]
