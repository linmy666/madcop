"""Direct unit tests for llm.client Message / MockClient."""
from __future__ import annotations

from madcop.llm.client import ChatResponse, Message, MockClient, ToolCall
from madcop.llm.capabilities import detect_capabilities, probe_live


def test_message_to_dict_basic():
    m = Message(role="user", content="hi")
    assert m.to_dict() == {"role": "user", "content": "hi"}


def test_message_to_dict_tool_calls():
    tc = ToolCall(id="1", name="read", arguments={"path": "a.py"})
    m = Message(role="assistant", content="", tool_calls=(tc,))
    d = m.to_dict()
    assert d["tool_calls"][0]["function"]["name"] == "read"
    assert "path" in d["tool_calls"][0]["function"]["arguments"]


def test_mock_client_scripted():
    c = MockClient(scripted=["one", "two"])
    r1 = c.chat([Message(role="user", content="a")])
    r2 = c.chat([Message(role="user", content="b")])
    assert r1.content == "one"
    assert r2.content == "two"
    assert len(c.calls) == 2


def test_detect_capabilities_heuristic():
    r = detect_capabilities(model="gpt-4o", base_url="https://api.openai.com/v1")
    assert r.supports_tools is True
    assert r.context_window > 0
    assert r.source in ("heuristic", "cache")


def test_probe_live_without_key_falls_back():
    r = probe_live(api_key="", model="gpt-4o-mini")
    assert r.source == "heuristic"
