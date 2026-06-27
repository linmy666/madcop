"""Tests for the ToolRegistry with mocked tools."""

from __future__ import annotations

import pytest

from madcop.llm import ToolCall
from madcop.tools.registry import (
    EchoTool,
    FunctionTool,
    GetTimeTool,
    Tool,
    ToolRegistry,
    ToolResult,
)


# --------------------------------------------------------------------------- #
# ToolResult
# --------------------------------------------------------------------------- #

def test_tool_result_str_output():
    r = ToolResult(tool_name="x", output="hello")
    assert r.to_message_content() == "hello"
    assert r.error is None


def test_tool_result_dict_output():
    r = ToolResult(tool_name="x", output={"a": 1})
    assert '"a"' in r.to_message_content()
    assert "1" in r.to_message_content()


def test_tool_result_error():
    r = ToolResult(tool_name="x", output=None, error="boom")
    assert r.to_message_content() == "ERROR: boom"


def test_tool_result_none_output():
    r = ToolResult(tool_name="x", output=None)
    assert r.to_message_content() == "null"


# --------------------------------------------------------------------------- #
# ToolRegistry — register / get / names
# --------------------------------------------------------------------------- #

def test_register_and_get():
    reg = ToolRegistry()
    echo = EchoTool()
    reg.register(echo)
    assert "echo" in reg
    assert reg.get("echo") is echo


def test_duplicate_register_raises():
    reg = ToolRegistry()
    reg.register(EchoTool())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(EchoTool())


def test_get_unknown_raises():
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_names_sorted():
    reg = ToolRegistry()
    reg.register(EchoTool())
    reg.register(GetTimeTool())
    assert reg.names() == ["echo", "get_current_time"]


# --------------------------------------------------------------------------- #
# openai_schemas
# --------------------------------------------------------------------------- #

def test_openai_schemas_format():
    reg = ToolRegistry()
    reg.register(EchoTool())
    schemas = reg.openai_schemas()
    assert len(schemas) == 1
    s = schemas[0]
    assert s["type"] == "function"
    assert s["function"]["name"] == "echo"
    assert "description" in s["function"]
    assert "parameters" in s["function"]
    assert s["function"]["parameters"]["properties"]["text"]["type"] == "string"


def test_openai_schemas_multiple():
    reg = ToolRegistry()
    reg.register(EchoTool())
    reg.register(GetTimeTool())
    schemas = reg.openai_schemas()
    assert len(schemas) == 2
    names = {s["function"]["name"] for s in schemas}
    assert names == {"echo", "get_current_time"}


# --------------------------------------------------------------------------- #
# dispatch
# --------------------------------------------------------------------------- #

def test_dispatch_echo():
    reg = ToolRegistry()
    reg.register(EchoTool())
    call = ToolCall(id="c1", name="echo", arguments={"text": "hi"})
    result = reg.dispatch(call)
    assert result.error is None
    assert result.output == "hi"
    assert result.tool_name == "echo"


def test_dispatch_unknown_tool():
    reg = ToolRegistry()
    call = ToolCall(id="c1", name="nonexistent", arguments={})
    result = reg.dispatch(call)
    assert result.error is not None
    assert "unknown tool" in result.error
    assert result.output is None


def test_dispatch_tool_raises_error():
    """When a tool raises, dispatch catches it and returns an error."""
    reg = ToolRegistry()

    def boom(**kw):
        raise ValueError("kaboom")

    reg.register(FunctionTool(
        name="boom_tool",
        description="always fails",
        fn=boom,
        parameters_schema={"type": "object", "properties": {}, "required": []},
    ))
    call = ToolCall(id="c1", name="boom_tool", arguments={})
    result = reg.dispatch(call)
    assert result.error is not None
    assert "ValueError" in result.error
    assert "kaboom" in result.error


def test_dispatch_get_time():
    reg = ToolRegistry()
    reg.register(GetTimeTool())
    call = ToolCall(id="c1", name="get_current_time", arguments={})
    result = reg.dispatch(call)
    assert result.error is None
    assert "T" in result.output  # ISO format


# --------------------------------------------------------------------------- #
# FunctionTool
# --------------------------------------------------------------------------- #

def test_function_tool():
    def add(a, b):
        return a + b

    t = FunctionTool(
        name="add",
        description="Add two numbers",
        fn=add,
        parameters_schema={
            "type": "object",
            "properties": {
                "a": {"type": "integer"},
                "b": {"type": "integer"},
            },
            "required": ["a", "b"],
        },
    )
    assert t.name == "add"
    assert t(a=2, b=3) == 5
    schema = t.to_openai_schema()
    assert schema["function"]["name"] == "add"


# --------------------------------------------------------------------------- #
# Tool ABC
# --------------------------------------------------------------------------- #

def test_tool_is_abstract():
    """Can't instantiate Tool directly."""
    with pytest.raises(TypeError):
        Tool()  # type: ignore[abstract]


def test_default_registry():
    """default_registry builds a registry with built-in tools."""
    from madcop.tools import default_registry
    reg = default_registry()
    names = reg.names()
    assert "echo" in names
    assert "get_current_time" in names
    assert "web_search" in names
    assert "get_weather" in names
