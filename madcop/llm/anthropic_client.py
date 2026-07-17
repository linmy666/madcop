"""Native Anthropic Messages API client (ChatClient interface).

Uses the Anthropic HTTP API shape:
  POST {base}/v1/messages
  headers: x-api-key, anthropic-version
  body: model, max_tokens, system, messages, tools, stream
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterable, Iterator

from madcop.llm.client import (
    ChatClient,
    ChatResponse,
    Message,
    StreamChunk,
    ToolCall,
)


def _openai_tools_to_anthropic(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
    if not tools:
        return None
    out = []
    for t in tools:
        if t.get("type") == "function" and "function" in t:
            fn = t["function"]
            out.append({
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "input_schema": fn.get("parameters") or {"type": "object", "properties": {}},
            })
        elif "name" in t and "input_schema" in t:
            out.append(t)
    return out or None


def messages_to_anthropic(messages: list[Message]) -> tuple[str, list[dict[str, Any]]]:
    """Split system prompt and convert messages to Anthropic format."""
    system_parts: list[str] = []
    out: list[dict[str, Any]] = []
    for m in messages:
        if m.role == "system":
            if isinstance(m.content, str):
                system_parts.append(m.content)
            continue
        if m.role == "tool":
            block = {
                "type": "tool_result",
                "tool_use_id": m.tool_call_id or "",
                "content": m.content if isinstance(m.content, str) else json.dumps(m.content),
            }
            if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list):
                out[-1]["content"].append(block)
            else:
                out.append({"role": "user", "content": [block]})
            continue
        if m.role == "assistant" and m.tool_calls:
            content: list[dict[str, Any]] = []
            if m.content:
                content.append({
                    "type": "text",
                    "text": m.content if isinstance(m.content, str) else str(m.content),
                })
            for tc in m.tool_calls:
                content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": tc.arguments or {},
                })
            out.append({"role": "assistant", "content": content})
            continue
        content_val: Any
        if isinstance(m.content, list):
            content_val = m.content
        else:
            content_val = m.content or ""
        role = "user" if m.role == "user" else "assistant"
        out.append({"role": role, "content": content_val})
    return "\n\n".join(system_parts), out


class AnthropicMessagesClient(ChatClient):
    """HTTP client for Anthropic Messages API."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 120.0,
        default_temperature: float | None = None,
        default_max_tokens: int | None = None,
    ):
        self.api_key = (
            api_key
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("MADCOP_ANTHROPIC_API_KEY")
        )
        raw_base = (base_url or "https://api.anthropic.com").rstrip("/")
        if raw_base.endswith("/v1"):
            raw_base = raw_base[:-3]
        self.base_url = raw_base
        self.model = model or "claude-sonnet-4-20250514"
        self.timeout = timeout
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens or 4096
        if not self.api_key:
            raise ValueError("AnthropicMessagesClient requires an API key")

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key or "",
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _body(
        self,
        messages: Iterable[Message],
        *,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        tools: list[dict[str, Any]] | None,
        stream: bool,
    ) -> dict[str, Any]:
        system, msgs = messages_to_anthropic(list(messages))
        body: dict[str, Any] = {
            "model": model or self.model,
            "max_tokens": max_tokens or self.default_max_tokens or 4096,
            "messages": msgs,
            "stream": stream,
        }
        if system:
            body["system"] = system
        t = temperature if temperature is not None else self.default_temperature
        if t is not None:
            body["temperature"] = t
        a_tools = _openai_tools_to_anthropic(tools)
        if a_tools:
            body["tools"] = a_tools
        return body

    def chat(
        self,
        messages: Iterable[Message],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        effort: str | None = None,
    ) -> ChatResponse:
        import urllib.request

        body = self._body(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            stream=False,
        )
        body.pop("stream", None)
        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return self._parse_response(data)

    def _parse_response(self, data: dict[str, Any]) -> ChatResponse:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in data.get("content") or []:
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text") or "")
            elif btype == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.get("id") or "",
                    name=block.get("name") or "",
                    arguments=block.get("input") or {},
                ))
        usage = {}
        if data.get("usage"):
            usage = {
                "prompt_tokens": data["usage"].get("input_tokens", 0),
                "completion_tokens": data["usage"].get("output_tokens", 0),
                "total_tokens": (
                    data["usage"].get("input_tokens", 0)
                    + data["usage"].get("output_tokens", 0)
                ),
            }
        return ChatResponse(
            content="".join(text_parts),
            tool_calls=tuple(tool_calls),
            usage=usage,
            model=data.get("model") or self.model,
        )

    def stream(
        self,
        messages: Iterable[Message],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        effort: str | None = None,
    ) -> Iterator[StreamChunk]:
        """SSE stream from Anthropic Messages API."""
        import urllib.request

        body = self._body(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            stream=True,
        )
        req = urllib.request.Request(
            f"{self.base_url}/v1/messages",
            data=json.dumps(body).encode("utf-8"),
            headers=self._headers(),
            method="POST",
        )
        emitted_model = model or self.model
        tc_acc: dict[int, dict[str, Any]] = {}
        current_tc_index = -1
        saw_finish = False

        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            event_type = ""
            data_buf = ""
            for raw_line in resp:
                line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                    continue
                if line.startswith("data:"):
                    data_buf = line[5:].strip()
                    continue
                if line != "":
                    continue
                if not data_buf:
                    continue
                try:
                    payload = json.loads(data_buf)
                except json.JSONDecodeError:
                    data_buf = ""
                    continue
                data_buf = ""
                et = event_type or payload.get("type", "")

                if et == "content_block_delta":
                    delta = payload.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        yield StreamChunk(text=delta.get("text") or "", model=emitted_model)
                    elif delta.get("type") == "input_json_delta":
                        partial = delta.get("partial_json") or ""
                        if current_tc_index >= 0:
                            slot = tc_acc.setdefault(
                                current_tc_index, {"id": "", "name": "", "arguments": ""},
                            )
                            slot["arguments"] += partial
                            yield StreamChunk(
                                model=emitted_model,
                                tool_call_deltas=({
                                    "index": current_tc_index,
                                    "id": slot.get("id"),
                                    "name": slot.get("name"),
                                    "arguments": partial,
                                },),
                            )
                elif et == "content_block_start":
                    block = payload.get("content_block") or {}
                    if block.get("type") == "tool_use":
                        current_tc_index += 1
                        tc_acc[current_tc_index] = {
                            "id": block.get("id") or "",
                            "name": block.get("name") or "",
                            "arguments": "",
                        }
                        yield StreamChunk(
                            model=emitted_model,
                            tool_call_deltas=({
                                "index": current_tc_index,
                                "id": block.get("id"),
                                "name": block.get("name"),
                                "arguments": "",
                            },),
                        )
                elif et == "message_delta":
                    stop = (payload.get("delta") or {}).get("stop_reason")
                    if stop:
                        saw_finish = True
                        fr = "tool_calls" if stop == "tool_use" else "stop"
                        yield StreamChunk(finish_reason=fr, model=emitted_model)
                elif et == "message_start":
                    msg = payload.get("message") or {}
                    if msg.get("model"):
                        emitted_model = msg["model"]
                event_type = ""

        if not saw_finish:
            yield StreamChunk(finish_reason="stop", model=emitted_model)
