"""Tests for the tool registry."""

from __future__ import annotations

import pytest

from madcop.llm import ToolCall
from madcop.tools import (
    EchoTool,
    FunctionTool,
    GetTimeTool,
    Tool,
    ToolRegistry,
    ToolResult,
)


# --------------------------------------------------------------------------- #
# EchoTool
# --------------------------------------------------------------------------- #

def test_echo_returns_text() -> None:
    assert EchoTool()(text="hi") == "hi"


def test_echo_schema_has_text() -> None:
    schema = EchoTool().parameters_schema  # access on instance
    assert "text" in schema["properties"]
    assert "text" in schema["required"]


def test_echo_to_openai_schema_format() -> None:
    s = EchoTool().to_openai_schema()
    assert s["type"] == "function"
    assert s["function"]["name"] == "echo"
    assert "parameters" in s["function"]


# --------------------------------------------------------------------------- #
# GetTimeTool
# --------------------------------------------------------------------------- #

def test_get_time_returns_iso_string() -> None:
    out = GetTimeTool()()
    assert "T" in out and out.endswith("+00:00")


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

def test_registry_register_and_get() -> None:
    reg = ToolRegistry()
    reg.register(EchoTool())
    assert "echo" in reg
    assert reg.get("echo").name == "echo"


def test_registry_rejects_duplicate() -> None:
    reg = ToolRegistry()
    reg.register(EchoTool())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(EchoTool())


def test_registry_unknown_tool() -> None:
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_registry_names_sorted() -> None:
    reg = ToolRegistry()
    reg.register(GetTimeTool())
    reg.register(EchoTool())
    assert reg.names() == ["echo", "get_current_time"]


def test_registry_openai_schemas_returns_list() -> None:
    reg = ToolRegistry()
    reg.register(EchoTool())
    schemas = reg.openai_schemas()
    assert isinstance(schemas, list)
    assert len(schemas) == 1
    assert schemas[0]["function"]["name"] == "echo"


def test_registry_dispatch_success() -> None:
    reg = ToolRegistry()
    reg.register(EchoTool())
    result = reg.dispatch(ToolCall(id="1", name="echo", arguments={"text": "hi"}))
    assert isinstance(result, ToolResult)
    assert result.error is None
    assert result.output == "hi"
    assert result.to_message_content() == "hi"


def test_registry_dispatch_unknown_tool() -> None:
    reg = ToolRegistry()
    result = reg.dispatch(ToolCall(id="1", name="unknown", arguments={}))
    assert result.error is not None
    assert "unknown tool" in result.error


def test_registry_dispatch_tool_exception() -> None:
    def bad(**kwargs):
        raise RuntimeError("boom")

    tool = FunctionTool(
        name="bad",
        description="raises",
        fn=bad,
        parameters_schema={"type": "object", "properties": {}, "required": []},
    )
    reg = ToolRegistry()
    reg.register(tool)
    result = reg.dispatch(ToolCall(id="1", name="bad", arguments={}))
    assert result.error is not None
    assert "RuntimeError" in result.error


def test_function_tool_basic() -> None:
    def add(a: int, b: int) -> int:
        return a + b

    tool = FunctionTool(
        name="add",
        description="adds",
        fn=add,
        parameters_schema={
            "type": "object",
            "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
            "required": ["a", "b"],
        },
    )
    assert tool(a=2, b=3) == 5


def test_tool_result_stringifies_non_string_output() -> None:
    r = ToolResult(tool_name="x", output={"a": 1})
    import json
    assert json.loads(r.to_message_content()) == {"a": 1}


def test_tool_result_error_message_format() -> None:
    r = ToolResult(tool_name="x", output=None, error="bad")
    assert r.to_message_content() == "ERROR: bad"