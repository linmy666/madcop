"""Tests for factory, retry, anthropic conversion, multimodal."""

from __future__ import annotations

import pytest

from madcop.llm.client import Message, MockClient, ToolCall
from madcop.llm.factory import build_client_from_config, merge_agent_routing
from madcop.llm.retry import is_retryable_error, with_retry
from madcop.llm.anthropic_client import messages_to_anthropic
from madcop.llm.capabilities import detect_capabilities, image_content_block
from madcop.llm.multimodal import user_message_with_images


def test_factory_mock_without_key():
    c = build_client_from_config(None)
    assert isinstance(c, MockClient)


def test_factory_openai_compat():
    from madcop.llm.client import OpenAICompatClient
    c = build_client_from_config({
        "api_key": "sk-test",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "api_format": "openai_chat",
    })
    assert isinstance(c, OpenAICompatClient)


def test_factory_anthropic_native():
    from madcop.llm.anthropic_client import AnthropicMessagesClient
    c = build_client_from_config({
        "api_key": "sk-ant-test",
        "base_url": "https://api.anthropic.com",
        "model": "claude-sonnet-4-20250514",
        "api_format": "anthropic",
    })
    assert isinstance(c, AnthropicMessagesClient)


def test_merge_agent_routing():
    base = {"api_key": "k", "base_url": "u", "model": "gpt-4o", "temperature": 0.5}
    routing = {"planner": {"model": "o3-mini", "temperature": 0.1}}
    m = merge_agent_routing(base, routing, "planner")
    assert m["model"] == "o3-mini"
    assert m["temperature"] == 0.1
    assert merge_agent_routing(base, routing, "coder")["model"] == "gpt-4o"


def test_retry_succeeds_after_transient():
    n = {"i": 0}

    def flaky():
        n["i"] += 1
        if n["i"] < 3:
            raise ConnectionError("connection reset")
        return "ok"

    assert with_retry(flaky, max_attempts=3, base_delay_s=0.01) == "ok"
    assert n["i"] == 3


def test_retry_gives_up_on_auth():
    def bad():
        raise ValueError("401 unauthorized invalid api key")

    with pytest.raises(ValueError):
        with_retry(bad, max_attempts=3, base_delay_s=0.01)


def test_is_retryable():
    assert is_retryable_error(ConnectionError("x"))
    assert is_retryable_error(RuntimeError("429 rate limit"))
    assert not is_retryable_error(ValueError("invalid model"))


def test_messages_to_anthropic_system_and_tools():
    msgs = [
        Message(role="system", content="You are helpful."),
        Message(role="user", content="hi"),
        Message(
            role="assistant", content="",
            tool_calls=(ToolCall(id="t1", name="read_file", arguments={"path": "a"}),),
        ),
        Message(role="tool", content="ok", tool_call_id="t1"),
    ]
    system, out = messages_to_anthropic(msgs)
    assert "helpful" in system
    assert out[0]["role"] == "user"
    assert out[1]["role"] == "assistant"
    assert out[1]["content"][0]["type"] == "tool_use"
    assert out[2]["role"] == "user"
    assert out[2]["content"][0]["type"] == "tool_result"


def test_image_blocks_openai_vs_anthropic():
    oai = image_content_block(data_url="data:image/png;base64,AAA", api_format="openai_chat")
    assert oai["type"] == "image_url"
    ant = image_content_block(data_url="data:image/png;base64,AAA", api_format="anthropic")
    assert ant["type"] == "image"
    assert ant["source"]["type"] == "base64"


def test_user_message_with_images():
    m = user_message_with_images(
        "see this",
        [{"data_url": "data:image/png;base64,xx"}],
        api_format="openai_chat",
    )
    assert m.role == "user"
    assert isinstance(m.content, list)
    assert m.content[0]["type"] == "text"
    assert m.content[1]["type"] == "image_url"


def test_detect_capabilities_o3():
    r = detect_capabilities(model="o3-mini", force_refresh=True)
    assert r.supports_temperature is False
    assert r.max_tokens_field == "max_completion_tokens"
