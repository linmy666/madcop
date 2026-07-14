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
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable, Iterator


# --------------------------------------------------------------------------- #
# Message / Response types
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Message:
    """One chat message."""
    role: str                          # "system" | "user" | "assistant" | "tool"
    content: str | list = ""           # str for text-only, list[dict] for multimodal blocks
    name: str | None = None
    tool_call_id: str | None = None     # for role="tool"
    tool_calls: tuple[ToolCall, ...] = ()  # for role="assistant" with tool use

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name is not None:
            d["name"] = self.name
        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id
        if self.tool_calls:
            import json as _json
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": _json.dumps(tc.arguments, ensure_ascii=False),
                    },
                }
                for tc in self.tool_calls
            ]
        return d


@dataclass(frozen=True)
class ToolCall:
    """An LLM-requested tool invocation."""
    id: str
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class StreamChunk:
    """One piece from a streaming chat completion.

    `text` is the incremental content for this chunk (may be empty
    when the chunk carries only a finish_reason or tool_calls).
    `reasoning` carries reasoning-model thinking tokens (e.g. MiniMax
    M2.7, DeepSeek R1) — optional, separate from final answer text.
    `finish_reason` is non-None on the final chunk.
    """
    text: str = ""
    reasoning: str = ""
    finish_reason: str | None = None
    model: str = ""


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
        effort: str | None = None,
    ) -> ChatResponse:
        """Send messages, return one ChatResponse."""
        raise NotImplementedError

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
        """Stream chat completion as a sequence of StreamChunks.

        Default implementation just calls `chat()` and yields one
        chunk with the full content + finish_reason='stop'. Subclasses
        that support real streaming override this.
        """
        resp = self.chat(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
        )
        yield StreamChunk(text=resp.content, finish_reason="stop", model=resp.model or "")


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
        effort: str | None = None,
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
        """Word-level streaming of the scripted/default response.

        Records the call (telemetry), pulls the canned response the
        same way `chat()` does, then yields one chunk per token plus
        a final stop chunk. Useful for SSE end-to-end tests without
        hitting the network.
        """
        msgs = list(messages)
        self.calls.append(msgs)
        if self._script_idx < len(self.script):
            response = self.script[self._script_idx]
            self._script_idx += 1
        else:
            response = self.default_response
        mod = model or self.model
        # Split on whitespace, keep the whitespace as part of the token
        # so downstream rendering matches the original spacing.
        tokens = response.split(" ")
        for i, tok in enumerate(tokens):
            # Re-insert leading space for everything except the first token.
            text = tok if i == 0 else " " + tok
            yield StreamChunk(text=text, model=mod)
        yield StreamChunk(finish_reason="stop", model=mod)


# --------------------------------------------------------------------------- #
# OpenAI-compatible client
# --------------------------------------------------------------------------- #

class OpenAICompatClient(ChatClient):
    """OpenAI SDK wrapper. Works with any compatible endpoint.

    Config via constructor args or env vars:
        api_key     -> MADCOP_OPENAI_API_KEY  (or OPENAI_API_KEY)
        base_url    -> MADCOP_OPENAI_BASE_URL (default OpenAI)
        model       -> MADCOP_OPENAI_MODEL    (default 'gpt-4o-mini')

    Reasoning intensity (effort): when ``effort`` is set and the target
    model is a reasoning model (OpenAI o-series / GPT-5), the client
    injects ``extra_body={"reasoning_effort": <level>}``. Non-reasoning
    models (e.g. GLM via Sensenova, Qwen via NVIDIA) silently ignore the
    setting — see ``_supports_reasoning``.
    """

    # UI effort level -> OpenAI ``reasoning_effort`` value.
    _REASONING_EFFORT_MAP = {
        "low": "low",
        "medium": "medium",
        "high": "high",
        "max": "xhigh",
    }
    # Models that accept ``reasoning_effort`` (OpenAI reasoning series).
    _REASONING_RE = re.compile(r"(?:^|/)(o1|o3|o4)[-_a-z0-9]*$|gpt-5", re.IGNORECASE)

    @staticmethod
    def _supports_reasoning(model_id: str | None) -> bool:
        if not model_id:
            return False
        return bool(OpenAICompatClient._REASONING_RE.search(model_id))

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
        effort: str | None = None,
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
        # Per-client default reasoning intensity; can be overridden per call.
        self.effort = effort
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

    def _reasoning_effort_extra_body(self, effort: str | None, model: str | None) -> dict | None:
        """Return ``extra_body`` with reasoning_effort, or None if N/A."""
        eff = effort if effort is not None else self.effort
        if not eff or eff == "auto":
            return None
        effective_model = model or self.model
        if not self._supports_reasoning(effective_model):
            return None
        level = self._REASONING_EFFORT_MAP.get(eff, "medium")
        return {"reasoning_effort": level}

    def chat(
        self,
        messages: Iterable[Message],
        *,
        model: str | None = None,
        temperature: float = 0.0,
        max_tokens: int | None = None,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        effort: str | None = None,
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
            if tool_choice:
                kwargs["tool_choice"] = tool_choice
        extra = self._reasoning_effort_extra_body(effort, model or self.model)
        if extra:
            kwargs["extra_body"] = extra
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
            content=msg.content or getattr(msg, "reasoning_content", "") or "",
            tool_calls=tuple(tool_calls),
            usage=usage,
            model=resp.model,
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
        """Real token-level streaming via the OpenAI SDK.

        Uses `client.chat.completions.create(stream=True)`, which
        returns an iterator of ChatCompletionChunk. Each chunk's
        `delta.content` is yielded as one StreamChunk. The final
        chunk carries `finish_reason='stop'` from the last delta
        (or 'length' if the model hit max_tokens).
        """
        payload = [m.to_dict() for m in messages]
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": payload,
            "temperature": temperature,
            "stream": True,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        if tools:
            kwargs["tools"] = tools
        extra = self._reasoning_effort_extra_body(effort, model or self.model)
        if extra:
            kwargs["extra_body"] = extra
        # `stream=True` makes the SDK return a Stream iterator rather
        # than a single ChatCompletion.
        stream_obj = self._client.chat.completions.create(**kwargs)
        emitted_model = ""
        saw_finish = False
        for event in stream_obj:
            # Newer SDK (>=1.50) yields ChatCompletionChunk objects.
            # Each has .choices[0].delta with .content and a model id.
            try:
                choice = event.choices[0]
                delta = choice.delta
            except (AttributeError, IndexError):
                # Malformed chunk — skip it but keep streaming.
                continue
            text = getattr(delta, "content", None) or ""
            reasoning = getattr(delta, "reasoning_content", None) or ""
            finish = getattr(choice, "finish_reason", None)
            model_name = getattr(event, "model", "") or ""
            if model_name and not emitted_model:
                emitted_model = model_name
            if finish:
                saw_finish = True
            yield StreamChunk(
                text=text,
                reasoning=reasoning,
                finish_reason=finish,
                model=emitted_model,
            )
        # Defensive: if the provider forgot to emit a finish_reason,
        # synthesise one so downstream consumers can finalise.
        if not saw_finish:  # pragma: no cover
            yield StreamChunk(finish_reason="stop", model=emitted_model)


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