"""End-to-end tests for tool-use flow in the chat endpoint.

Verifies:
- When the LLM returns tool_calls, the server executes them and emits SSE events.
- The tool result is passed back to the LLM in a second call.
- The final response is streamed to the client.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi.testclient import TestClient

from madcop.config import settings as S
from madcop.llm import ChatResponse, Message, StreamChunk, ToolCall
from madcop.server.app import create_app


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """TestClient with isolated settings (no real API key → mock path)."""
    spath = tmp_path / "settings.json"
    kpath = tmp_path / "master.key"
    monkeypatch.setattr(S, "DEFAULT_SETTINGS_PATH", spath)
    monkeypatch.setattr(S, "DEFAULT_MASTER_KEY_PATH", kpath)
    app = create_app()
    return TestClient(app)


def parse_sse(body: str) -> list[dict]:
    """Parse SSE response body into list of event dicts."""
    lines = [l for l in body.strip().split("\n") if l.startswith("data: ")]
    return [json.loads(l[6:]) for l in lines]


# --------------------------------------------------------------------------- #
# Fake LLM client that returns tool_calls on first call
# --------------------------------------------------------------------------- #

class FakeToolClient:
    """A fake LLM client for testing tool-use flow.

    First chat() call returns a tool_call. Subsequent calls return normal text.
    stream() streams the final text response.
    """

    def __init__(self):
        self._call_count = 0
        self.chat_calls: list[list[Message]] = []
        self.stream_calls: list[list[Message]] = []

    def chat(self, messages, *, model=None, temperature=0.0, max_tokens=None, tools=None, effort=None):
        msgs = list(messages)
        self.chat_calls.append(msgs)
        self._call_count += 1

        if self._call_count == 1:
            # Return a weather tool call
            return ChatResponse(
                content="",
                tool_calls=(
                    ToolCall(id="call_1", name="get_weather", arguments={"city": "Shanghai"}),
                ),
                model="test-model",
            )
        # Second call: return final text
        return ChatResponse(
            content="The weather in Shanghai is 22°C and partly cloudy.",
            model="test-model",
        )

    def stream(self, messages, *, model=None, temperature=0.0, max_tokens=None, tools=None, effort=None):
        msgs = list(messages)
        self.stream_calls.append(msgs)
        # First stream call is the Phase-1 tool-routing call: emit the
        # tool_call as a delta so the streaming Phase-1 path can accumulate it.
        if len(self.stream_calls) == 1 and tools:
            yield StreamChunk(
                model="test-model",
                tool_call_deltas=({"index": 0, "id": "call_1", "name": "get_weather", "arguments": ""},),
            )
            yield StreamChunk(
                model="test-model",
                tool_call_deltas=({"index": 0, "arguments": '{"city": "Shanghai"}'},),
            )
            yield StreamChunk(finish_reason="tool_calls", model="test-model")
            return
        # Second call (final synthesis): stream the text answer.
        text = "The weather in Shanghai is 22°C and partly cloudy."
        yield StreamChunk(text=text, model="test-model")
        yield StreamChunk(finish_reason="stop", model="test-model")


class FakeNoToolClient:
    """A fake LLM client that returns text directly (no tool calls)."""

    def __init__(self):
        self.chat_calls: list[list[Message]] = []
        self.stream_calls: list[list[Message]] = []

    def chat(self, messages, *, model=None, temperature=0.0, max_tokens=None, tools=None, effort=None):
        msgs = list(messages)
        self.chat_calls.append(msgs)
        return ChatResponse(
            content="Hello! How can I help?",
            model="test-model",
        )

    def stream(self, messages, *, model=None, temperature=0.0, max_tokens=None, tools=None, effort=None):
        msgs = list(messages)
        self.stream_calls.append(msgs)
        yield StreamChunk(text="Hello! How can I help?", model="test-model")
        yield StreamChunk(finish_reason="stop", model="test-model")


class FakeMultiToolClient:
    """Fake client that calls two tools in one response."""

    def __init__(self):
        self._call_count = 0
        self.chat_calls: list[list[Message]] = []
        self.stream_calls: list[list[Message]] = []

    def chat(self, messages, *, model=None, temperature=0.0, max_tokens=None, tools=None, effort=None):
        msgs = list(messages)
        self.chat_calls.append(msgs)
        self._call_count += 1

        if self._call_count == 1:
            return ChatResponse(
                content="",
                tool_calls=(
                    ToolCall(id="call_1", name="get_weather", arguments={"city": "Tokyo"}),
                    ToolCall(id="call_2", name="echo", arguments={"text": "hello"}),
                ),
                model="test-model",
            )
        return ChatResponse(
            content="Done with both tools.",
            model="test-model",
        )

    def stream(self, messages, *, model=None, temperature=0.0, max_tokens=None, tools=None, effort=None):
        self.stream_calls.append(list(messages))
        # Phase-1: emit both tool_calls as deltas (different indices).
        if len(self.stream_calls) == 1 and tools:
            yield StreamChunk(model="test-model", tool_call_deltas=({"index": 0, "id": "call_1", "name": "get_weather", "arguments": ""},))
            yield StreamChunk(model="test-model", tool_call_deltas=({"index": 0, "arguments": '{"city": "Tokyo"}'},))
            yield StreamChunk(model="test-model", tool_call_deltas=({"index": 1, "id": "call_2", "name": "echo", "arguments": ""},))
            yield StreamChunk(model="test-model", tool_call_deltas=({"index": 1, "arguments": '{"text": "hello"}'},))
            yield StreamChunk(finish_reason="tool_calls", model="test-model")
            return
        yield StreamChunk(text="Done with both tools.", model="test-model")
        yield StreamChunk(finish_reason="stop", model="test-model")


# --------------------------------------------------------------------------- #
# Tests: tool-use flow
# --------------------------------------------------------------------------- #

def test_tool_use_flow_with_mock_weather(client: TestClient):
    """Test the actual tool execution path by patching the weather tool.

    Since we can't easily inject a fake LLM into the endpoint (it builds the
    client internally from settings), we test the tool-use logic at the
    registry level + test the SSE format separately.
    """
    from madcop.tools.weather import WeatherTool

    t = WeatherTool()
    # Patch weather to return a fixed string
    with patch.object(t, "_fetch_json", return_value={
        "current_condition": [{
            "temp_C": "20",
            "FeelsLikeC": "21",
            "humidity": "50",
            "windspeedKmph": "10",
            "weatherDesc": [{"value": "Sunny"}],
        }],
        "nearest_area": [{"areaName": [{"value": "Shanghai"}]}],
    }):
        result = t(city="Shanghai")
    assert "Shanghai" in result
    assert "20" in result
    assert "Sunny" in result


def test_tool_use_flow_with_mock_web_search(client: TestClient):
    """Test web_search execution with mocked HTTP."""
    from madcop.tools.web import WebSearchTool

    t = WebSearchTool()
    fake_html = """
    <a rel="nofollow" href="//duckduckgo.com/l/?uddg=https://example.com" class='result-link'>Example Result</a>
    <td class='result-snippet'>A great example.</td>
    """
    with patch.object(t, "_search_ddg", return_value=fake_html):
        result = t(query="example")
    assert "Example Result" in result
    assert "example.com" in result


# --------------------------------------------------------------------------- #
# Tests: SSE event format for tools
# --------------------------------------------------------------------------- #

def test_sse_tool_event_format():
    """Verify the SSE JSON format for tool events."""
    tool_event = {"type": "tool", "name": "get_weather", "args": {"city": "Shanghai"}}
    sse = f"data: {json.dumps(tool_event, ensure_ascii=False)}\n\n"
    assert sse.startswith("data: ")
    assert sse.endswith("\n\n")
    parsed = json.loads(sse[6:].strip())
    assert parsed["type"] == "tool"
    assert parsed["name"] == "get_weather"
    assert parsed["args"]["city"] == "Shanghai"


def test_sse_tool_result_event_format():
    """Verify the SSE JSON format for tool_result events."""
    result_event = {
        "type": "tool_result",
        "name": "get_weather",
        "result": "Shanghai: Sunny, 20°C",
    }
    sse = f"data: {json.dumps(result_event, ensure_ascii=False)}\n\n"
    parsed = json.loads(sse[6:].strip())
    assert parsed["type"] == "tool_result"
    assert parsed["name"] == "get_weather"
    assert "Sunny" in parsed["result"]


# --------------------------------------------------------------------------- #
# Integration: real endpoint with injected mock client
# --------------------------------------------------------------------------- #

def test_chat_endpoint_tool_flow_via_injection(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Inject a fake LLM client by patching the _get_client closure.

    We recreate the app and patch the internal _get_client to use our fake.
    """
    spath = tmp_path / "settings.json"
    kpath = tmp_path / "master.key"
    monkeypatch.setattr(S, "DEFAULT_SETTINGS_PATH", spath)
    monkeypatch.setattr(S, "DEFAULT_MASTER_KEY_PATH", kpath)

    fake = FakeToolClient()

    # We patch MockClient to be our fake when instantiated
    import madcop.server.app as app_module
    monkeypatch.setattr(app_module, "MockClient", lambda **kw: fake)

    app = create_app()
    tc = TestClient(app)

    # Also patch the weather tool to not hit the network
    from madcop.tools.weather import WeatherTool

    def fake_fetch_json(self, city):
        return {
            "current_condition": [{
                "temp_C": "22",
                "FeelsLikeC": "24",
                "humidity": "65",
                "windspeedKmph": "12",
                "weatherDesc": [{"value": "Partly cloudy"}],
            }],
            "nearest_area": [{"areaName": [{"value": "Shanghai"}]}],
        }

    monkeypatch.setattr(WeatherTool, "_fetch_json", fake_fetch_json)

    r = tc.post("/api/chat", json={
        "messages": [{"role": "user", "content": "What's the weather in Shanghai?"}],
    })

    assert r.status_code == 200
    events = parse_sse(r.text)

    # Should have: tool event, tool_result event, text events, done event
    tool_events = [e for e in events if e["type"] == "tool"]
    tool_result_events = [e for e in events if e["type"] == "tool_result"]
    text_events = [e for e in events if e["type"] == "text"]
    done_events = [e for e in events if e["type"] == "done"]

    assert len(tool_events) >= 1
    assert tool_events[0]["name"] == "get_weather"
    assert tool_events[0]["args"]["city"] == "Shanghai"

    assert len(tool_result_events) >= 1
    assert tool_result_events[0]["name"] == "get_weather"
    assert "Shanghai" in tool_result_events[0]["result"]
    assert "22" in tool_result_events[0]["result"]

    assert len(text_events) >= 1
    full_text = "".join(e["content"] for e in text_events)
    assert "weather" in full_text.lower() or "Shanghai" in full_text

    assert len(done_events) == 1
    assert done_events[0]["finish_reason"] == "stop"

    # Phase-1 (tool routing) now streams too, so both calls go through
    # stream(); the Phase-2 (final synthesis) call carries the tool result.
    assert len(fake.stream_calls) == 2

    # The second stream call (Phase-2) should have the tool result message.
    stream_msgs = fake.stream_calls[1]
    tool_msgs = [m for m in stream_msgs if m.role == "tool"]
    assert len(tool_msgs) == 1
    assert "Shanghai" in tool_msgs[0].content


def test_chat_endpoint_no_tools_normal_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """When LLM returns no tool_calls, the response streams normally."""
    spath = tmp_path / "settings.json"
    kpath = tmp_path / "master.key"
    monkeypatch.setattr(S, "DEFAULT_SETTINGS_PATH", spath)
    monkeypatch.setattr(S, "DEFAULT_MASTER_KEY_PATH", kpath)

    fake = FakeNoToolClient()

    import madcop.server.app as app_module
    monkeypatch.setattr(app_module, "MockClient", lambda **kw: fake)

    app = create_app()
    tc = TestClient(app)

    r = tc.post("/api/chat", json={
        "messages": [{"role": "user", "content": "Hello"}],
    })

    assert r.status_code == 200
    events = parse_sse(r.text)

    # Should have text + done, but NO tool events
    tool_events = [e for e in events if e["type"] == "tool"]
    text_events = [e for e in events if e["type"] == "text"]
    done_events = [e for e in events if e["type"] == "done"]

    assert len(tool_events) == 0
    assert len(text_events) >= 1
    assert len(done_events) == 1

    full_text = "".join(e["content"] for e in text_events)
    assert "Hello" in full_text


def test_chat_endpoint_multi_tool_flow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Multiple tool calls in one response are all executed."""
    spath = tmp_path / "settings.json"
    kpath = tmp_path / "master.key"
    monkeypatch.setattr(S, "DEFAULT_SETTINGS_PATH", spath)
    monkeypatch.setattr(S, "DEFAULT_MASTER_KEY_PATH", kpath)

    fake = FakeMultiToolClient()

    import madcop.server.app as app_module
    monkeypatch.setattr(app_module, "MockClient", lambda **kw: fake)

    app = create_app()
    tc = TestClient(app)

    r = tc.post("/api/chat", json={
        "messages": [{"role": "user", "content": "Weather in Tokyo and echo hello"}],
    })

    assert r.status_code == 200
    events = parse_sse(r.text)

    tool_events = [e for e in events if e["type"] == "tool"]
    tool_result_events = [e for e in events if e["type"] == "tool_result"]

    # Two tools called
    assert len(tool_events) == 2
    tool_names = {e["name"] for e in tool_events}
    assert "get_weather" in tool_names
    assert "echo" in tool_names

    # Two results
    assert len(tool_result_events) == 2

    # Phase-2 (second stream call) should have both tool result messages.
    stream_msgs = fake.stream_calls[1]
    tool_msgs = [m for m in stream_msgs if m.role == "tool"]
    assert len(tool_msgs) == 2
