"""v1.1.0 — Tests for DeferredToolCatalog."""
from __future__ import annotations

import pytest

from madcop.tools import DeferredToolCatalog, EchoTool, GetTimeTool
from madcop.tools.registry import FunctionTool, Tool, ToolRegistry


# ---------------------------------------------------------------------------
# Custom test tools
# ---------------------------------------------------------------------------


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a file from disk"

    @property
    def parameters_schema(self) -> dict:
        return {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}

    def __call__(self, **kwargs):
        return kwargs.get("path", "")


class WriteFileTool(Tool):
    name = "write_file"
    description = "Write content to a file"

    @property
    def parameters_schema(self) -> dict:
        return {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}

    def __call__(self, **kwargs):
        return f"wrote {kwargs.get('content', '')} to {kwargs.get('path', '')}"


class HttpGetTool(Tool):
    name = "http_get"
    description = "Fetch a URL"

    @property
    def parameters_schema(self) -> dict:
        return {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}

    def __call__(self, **kwargs):
        return f"fetched {kwargs.get('url', '')}"


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_empty_catalog_has_no_categories():
    cat = DeferredToolCatalog()
    assert cat.categories == []


def test_register_adds_category():
    cat = DeferredToolCatalog()
    cat.register(EchoTool(), category="demo", description="echoes")
    assert "demo" in cat.categories
    # But registry is empty (not loaded yet)
    assert "echo" not in cat.registry


def test_register_many():
    cat = DeferredToolCatalog()
    cat.register_many([
        (EchoTool(), "demo", "echoes"),
        (GetTimeTool(), "utils", "current time"),
    ])
    assert sorted(cat.categories) == ["demo", "utils"]


def test_same_tool_can_belong_to_multiple_categories_via_different_instances():
    cat = DeferredToolCatalog()
    cat.register(EchoTool(), category="a", description="x")
    cat.register(EchoTool(), category="b", description="x")
    assert "a" in cat.categories
    assert "b" in cat.categories


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_empty_query_returns_nothing():
    cat = DeferredToolCatalog()
    cat.register(EchoTool(), category="demo", description="echoes")
    assert cat.search("") == []


def test_search_finds_tool_by_name():
    cat = DeferredToolCatalog()
    cat.register(ReadFileTool(), category="filesystem", description="read a file")
    matches = cat.search("read_file")
    assert ("filesystem", ["read_file"]) in matches


def test_search_finds_tool_by_description():
    cat = DeferredToolCatalog()
    cat.register(ReadFileTool(), category="filesystem", description="read a file from disk")
    matches = cat.search("disk")
    assert ("filesystem", ["read_file"]) in matches


def test_search_finds_category_by_name():
    cat = DeferredToolCatalog()
    cat.register(ReadFileTool(), category="filesystem", description="r")
    cat.register(WriteFileTool(), category="filesystem", description="w")
    matches = cat.search("filesystem")
    assert len(matches) == 1
    assert matches[0][0] == "filesystem"
    assert set(matches[0][1]) == {"read_file", "write_file"}


def test_search_case_insensitive():
    cat = DeferredToolCatalog()
    cat.register(ReadFileTool(), category="filesystem", description="read a file")
    matches = cat.search("READ_FILE")
    assert ("filesystem", ["read_file"]) in matches


def test_search_returns_empty_for_no_match():
    cat = DeferredToolCatalog()
    cat.register(ReadFileTool(), category="filesystem", description="read a file")
    assert cat.search("nonexistent_xyz") == []


def test_search_is_sorted_by_relevance():
    """A category with an exact name match should rank above one
    that only has a description match."""
    cat = DeferredToolCatalog()
    cat.register(ReadFileTool(), category="filesystem", description="read a file")
    cat.register(HttpGetTool(), category="network", description="fetch data")
    matches = cat.search("read_file")
    assert matches[0][0] == "filesystem"  # exact name match first


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------


def test_load_category_adds_tools_to_registry():
    cat = DeferredToolCatalog()
    cat.register(ReadFileTool(), category="filesystem", description="r")
    cat.register(WriteFileTool(), category="filesystem", description="w")
    added = cat.load_category("filesystem")
    assert sorted(added) == ["read_file", "write_file"]
    assert "read_file" in cat.registry
    assert "write_file" in cat.registry


def test_load_category_again_is_noop():
    cat = DeferredToolCatalog()
    cat.register(ReadFileTool(), category="filesystem", description="r")
    cat.load_category("filesystem")
    added_again = cat.load_category("filesystem")
    assert added_again == []


def test_load_unknown_category_returns_empty():
    cat = DeferredToolCatalog()
    assert cat.load_category("nonexistent") == []


def test_loaded_categories_tracks_state():
    cat = DeferredToolCatalog()
    cat.register(ReadFileTool(), category="fs", description="r")
    cat.register(EchoTool(), category="demo", description="e")
    assert cat.loaded_categories == []
    cat.load_category("fs")
    assert cat.loaded_categories == ["fs"]
    cat.load_category("demo")
    assert cat.loaded_categories == ["demo", "fs"]


def test_load_search_results_loads_every_category():
    cat = DeferredToolCatalog()
    cat.register(ReadFileTool(), category="filesystem", description="r")
    cat.register(EchoTool(), category="demo", description="e")
    matches = cat.search("read")
    assert ("filesystem", ["read_file"]) in matches
    result = cat.load_search_results(matches)
    assert "filesystem" in result
    assert "read_file" in result["filesystem"]


# ---------------------------------------------------------------------------
# Integration with the LLM tool-call flow
# ---------------------------------------------------------------------------


def test_loaded_tools_have_openai_schemas():
    cat = DeferredToolCatalog()
    cat.register(ReadFileTool(), category="filesystem", description="r")
    cat.load_category("filesystem")
    schemas = cat.registry.openai_schemas()
    assert any(s["function"]["name"] == "read_file" for s in schemas)


def test_loaded_tool_dispatches_correctly():
    cat = DeferredToolCatalog()
    cat.register(ReadFileTool(), category="filesystem", description="r")
    cat.load_category("filesystem")
    from madcop.llm import ToolCall
    result = cat.registry.dispatch(ToolCall(id="t1", name="read_file", arguments={"path": "/tmp/x"}))
    assert result.error is None
    assert result.output == "/tmp/x"
