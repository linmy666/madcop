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
    `tool_call_deltas` carries incremental tool-call fragments when the
    model is emitting a function call mid-stream; each is a dict like
    {"index": 0, "id": "...", "name": "...", "arguments": "..."} where
    only the fields present in this delta are set. Consumers accumulate
    by index.
    """
    text: str = ""
    reasoning: str = ""
    finish_reason: str | None = None
    model: str = ""
    tool_call_deltas: tuple = ()


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
        *,
        api_format: str | None = None,
        auth_strategy: str | None = None,
        runtime_kind: str | None = None,
        preset_id: str | None = None,
        top_p: float | None = None,
        default_temperature: float | None = None,
        default_max_tokens: int | None = None,
        harness: Any | None = None,
    ):
        # Late import so the package isn't a hard dependency for mock users
        from openai import OpenAI
        from madcop.llm.harness import resolve_harness

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
        self.api_format = api_format or "openai_chat"
        self.auth_strategy = auth_strategy or "api_key"
        self.runtime_kind = runtime_kind or ""
        self.preset_id = preset_id or ""
        self.top_p = top_p
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        self.harness = harness or resolve_harness(
            model=self.model,
            api_format=self.api_format,
            runtime_kind=self.runtime_kind,
            base_url=self.base_url,
            preset_id=self.preset_id,
        )
        if not self.api_key:
            raise ValueError(
                "OpenAICompatClient requires an API key. "
                "Set MADCOP_OPENAI_API_KEY or pass api_key=. "
                "Or use MockClient for offline / testing."
            )
        default_headers = dict(self.harness.extra_headers)
        # auth_token strategy: some gateways want empty api_key header style
        # still use Bearer via SDK; dual strategies pass the same token.
        self._client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url,
            timeout=timeout,
            default_headers=default_headers or None,
        )

    def _reasoning_effort_extra_body(self, effort: str | None, model: str | None) -> dict | None:
        """Return ``extra_body`` with reasoning_effort, or None if N/A."""
        # Prefer harness profile; fall back to legacy o-series check.
        h = self.harness
        if h and h.reasoning_mode != "none":
            return h._reasoning_extra_body(effort if effort is not None else self.effort, model or self.model)
        eff = effort if effort is not None else self.effort
        if not eff or eff == "auto":
            return None
        effective_model = model or self.model
        if not self._supports_reasoning(effective_model):
            return None
        level = self._REASONING_EFFORT_MAP.get(eff, "medium")
        return {"reasoning_effort": level}

    def _build_kwargs(
        self,
        messages: Iterable[Message],
        *,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        tools: list[dict[str, Any]] | None,
        tool_choice: str | None,
        effort: str | None,
        stream: bool,
    ) -> dict[str, Any]:
        payload = [m.to_dict() for m in messages]
        mid = model or self.model
        # Re-resolve harness if model override changes family mid-call.
        from madcop.llm.harness import resolve_harness
        harness = resolve_harness(
            model=mid,
            api_format=self.api_format,
            runtime_kind=self.runtime_kind,
            base_url=self.base_url,
            preset_id=self.preset_id,
        )
        t = temperature if temperature is not None else self.default_temperature
        mt = max_tokens if max_tokens is not None else self.default_max_tokens
        return harness.build_chat_kwargs(
            model=mid,
            messages=payload,
            temperature=t,
            max_tokens=mt,
            tools=tools,
            tool_choice=tool_choice,
            top_p=self.top_p,
            effort=effort if effort is not None else self.effort,
            stream=stream,
        )

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
        kwargs = self._build_kwargs(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=tool_choice,
            effort=effort,
            stream=False,
        )
        # stream=False must not be passed as stream keyword to non-stream path
        kwargs.pop("stream", None)
        from madcop.llm.retry import with_retry
        resp = with_retry(
            lambda: self._client.chat.completions.create(**kwargs),
            label="openai_chat",
        )
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
        kwargs = self._build_kwargs(
            messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            tool_choice=None,
            effort=effort,
            stream=True,
        )
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
            # Capture incremental tool-call fragments (OpenAI streams
            # tool_calls as deltas: first chunk has id+name+empty args,
            # subsequent chunks append to arguments). Forward each so the
            # caller can accumulate by index.
            tc_deltas: tuple = ()
            raw_tcs = getattr(delta, "tool_calls", None)
            if raw_tcs:
                tc_deltas = tuple(
                    {
                        "index": getattr(tc, "index", 0),
                        "id": getattr(tc, "id", None),
                        "name": getattr(getattr(tc, "function", None), "name", None),
                        "arguments": getattr(getattr(tc, "function", None), "arguments", None),
                    }
                    for tc in raw_tcs
                )
            yield StreamChunk(
                text=text,
                reasoning=reasoning,
                finish_reason=finish,
                model=emitted_model,
                tool_call_deltas=tc_deltas,
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