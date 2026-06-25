"""L7 — LLM client.

A thin wrapper over OpenAI-compatible chat completion APIs (works with
OpenAI, DeepSeek, 通义千问, 智谱, NVIDIA NIM, etc.).

Two implementations:

1. `MockClient` (default in tests) — deterministic responses from a
   canned prompt → response table. No network.
2. `OpenAICompatClient` — uses the `openai` Python SDK against any
   `base_url` + `api_key`. Reads env vars by default.

The interface (`ChatClient`) is the same for both so agent code can
swap them via injection.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable


# --------------------------------------------------------------------------- #
# Message / Response types
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Message:
    """One chat message."""
    role: str                          # "system" | "user" | "assistant" | "tool"
    content: str
    name: str | None = None
    tool_call_id: str | None = None     # for role="tool"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name is not None:
            d["name"] = self.name
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        return d


@dataclass(frozen=True)
class ToolCall:
    """An LLM-requested tool invocation."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class ChatResponse:
    """One model response."""
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    usage: dict[str, int] = field(default_factory=dict)
    model: str = ""


# --------------------------------------------------------------------------- #
# Abstract client
# --------------------------------------------------------------------------- #

class ChatClient(ABC):
    """Abstract chat client. Both Mock and OpenAICompat implement this."""

    @abstractmethod
    def chat(
        self,
        messages: Iterable[Message],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        """Send messages, return one ChatResponse."""
        raise NotImplementedError


# --------------------------------------------------------------------------- #
# Mock client (deterministic, for tests)
# --------------------------------------------------------------------------- #

class MockClient(ChatClient):
    """Deterministic mock. Useful in tests and air-gapped demos.

    By default returns a canned "summary" that reflects the last user
    message. Tests can pre-program responses via the `script` argument.
    """

    def __init__(
        self,
        default_response: str = "OK (mock LLM response)",
        scripted: list[str] | None = None,
        model: str = "mock-model",
    ):
        self.default_response = default_response
        self.script = list(scripted) if scripted else []
        self._script_idx = 0
        self.model = model
        # Telemetry for tests
        self.calls: list[list[Message]] = []

    def chat(
        self,
        messages: Iterable[Message],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        msgs = list(messages)
        self.calls.append(msgs)
        # Pull next scripted response if available, else default
        if self._script_idx < len(self.script):
            response = self.script[self._script_idx]
            self._script_idx += 1
        else:
            response = self.default_response
        return ChatResponse(
            content=response,
            usage={"prompt_tokens": 0, "completion_tokens": len(response)},
            model=model or self.model,
        )


# --------------------------------------------------------------------------- #
# OpenAI-compatible client
# --------------------------------------------------------------------------- #

class OpenAICompatClient(ChatClient):
    """OpenAI SDK wrapper. Works with any compatible endpoint.

    Config via constructor args or env vars:
        api_key     -> MADCOP_OPENAI_API_KEY  (or OPENAI_API_KEY)
        base_url    -> MADCOP_OPENAI_BASE_URL (default OpenAI)
        model       -> MADCOP_OPENAI_MODEL    (default 'gpt-4o-mini')
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ):
        # Late import so the package isn't a hard dependency for mock users
        from openai import OpenAI
        self._OpenAI = OpenAI  # for test mocking
        self.api_key = api_key or os.environ.get("MADCOP_OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY")
        self.base_url = base_url or os.environ.get(
            "MADCOP_OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        )
        self.model = model or os.environ.get("MADCOP_OPENAI_MODEL", "gpt-4o-mini")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError(
                "OpenAICompatClient requires an API key. "
                "Set MADCOP_OPENAI_API_KEY or pass api_key=. "
                "Or use MockClient for offline / testing."
            )
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
        )

    def chat(
        self,
        messages: Iterable[Message],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
    ) -> ChatResponse:
        payload = [m.to_dict() for m in messages]
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": payload,
            "temperature": temperature,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = tools
        resp = self._client.chat.completions.create(**kwargs)
        choice = resp.choices[0]
        msg = choice.message
        tool_calls: list[ToolCall] = []
        if getattr(msg, "tool_calls", None):
            for tc in msg.tool_calls:
                import json as _json
                try:
                    args = _json.loads(tc.function.arguments)
                except (TypeError, ValueError):
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id, name=tc.function.name, arguments=args,
                ))
        usage = {}
        if getattr(resp, "usage", None):
            usage = {
                "prompt_tokens": resp.usage.prompt_tokens,
                "completion_tokens": resp.usage.completion_tokens,
                "total_tokens": resp.usage.total_tokens,
            }
        return ChatResponse(
            content=msg.content or "",
            tool_calls=tuple(tool_calls),
            usage=usage,
            model=resp.model,
        )


# --------------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------------- #

def make_client(use_real: bool = False) -> ChatClient:
    """Build the right client.

    - `use_real=False` (default): MockClient (safe for tests / air-gap).
    - `use_real=True`: OpenAICompatClient (reads env vars).
    """
    if use_real:
        return OpenAICompatClient()
    return MockClient()