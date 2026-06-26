"""v0.8.0 — A real-LLM-backed Runner for sub-agents, with optional tool-use.

LLMRunner wraps any ChatClient (e.g. madcop.llm.OpenAICompatClient) and
adapts it to the sub-agent Runner protocol. Two modes:

1. `tool_registry=None` (the v0.7.1 default) — single chat() call per
   sub-agent. Quick, simple, no tool access.

2. `tool_registry=...` — full tool-use loop. The runner keeps calling
   chat() until either:
     - the model returns no tool_calls (i.e. it has produced a final
       answer), or
     - `max_tool_iterations` is hit (safety cap), or
     - the user cancels via result_holder.cancel_event.

   Each tool call is dispatched via the registry; the result is fed
   back as a `role="tool"` message (with the matching `tool_call_id`).
   The final assistant content is returned as the sub-agent's output.

Usage (single-call, unchanged):
    from madcop.llm import OpenAICompatClient
    from madcop.agent.subagent import SubagentExecutor, ExecutorConfig
    from madcop.agent.subagent.llm_runner import LLMRunner
    from madcop.tools import ToolRegistry, EchoTool

    client = OpenAICompatClient()
    runner = LLMRunner(client, tool_registry=ToolRegistry().register(EchoTool()))
    executor = SubagentExecutor(runner=runner, config=ExecutorConfig(max_concurrent=3))

The runner is intentionally framework-light: it doesn't know about
the agent graph, the scratchpad, or the plan-execute loop. It's a
synchronous adapter — async execution lives in the executor (v0.8.0
async mode handles I/O-bound sub-agents separately).
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from ...llm import ChatClient, Message
from ...tools import ToolRegistry
from .executor import Runner
from .spec import SubagentSpec
from .status import SubagentResult

logger = logging.getLogger(__name__)


# Default safety cap for the tool-use loop. A well-behaved agent
# usually converges in 1-3 iterations; 8 gives headroom for genuinely
# multi-step tasks without runaway loops.
DEFAULT_MAX_TOOL_ITERATIONS = 8


class LLMRunner(Runner):
    """Adapt a ChatClient to the sub-agent Runner protocol.

    With `tool_registry=None`: one chat() call per sub-agent.
    With `tool_registry=...`: a tool-use loop that calls chat() until
    the model emits a final answer (no tool_calls) or a stop condition
    is hit.
    """

    def __init__(
        self,
        client: ChatClient,
        *,
        max_tokens: int | None = 512,
        temperature: float = 0.0,
        include_context: bool = True,
        tool_registry: ToolRegistry | None = None,
        max_tool_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
    ):
        self._client = client
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._include_context = include_context
        self._tool_registry = tool_registry
        self._max_tool_iterations = max_tool_iterations

    @property
    def tool_registry(self) -> ToolRegistry | None:
        return self._tool_registry

    def run(
        self,
        *,
        agent: SubagentSpec,
        prompt: str,
        context: Mapping[str, Any],
        result_holder: SubagentResult,
    ) -> str:
        # Build the initial messages list (system + user). For tool-use
        # mode this list will grow as we append tool responses.
        messages = self._initial_messages(agent, prompt, context)

        # No tool registry? Single chat() call (v0.7.1 behavior).
        if self._tool_registry is None:
            return self._single_call(messages, result_holder)

        # Tool-use mode: loop until the model stops calling tools.
        return self._tool_use_loop(messages, result_holder)

    # ----- message construction -------------------------------------------

    def _initial_messages(
        self,
        agent: SubagentSpec,
        prompt: str,
        context: Mapping[str, Any],
    ) -> list[Message]:
        messages: list[Message] = []
        if agent.system_prompt:
            messages.append(Message(role="system", content=agent.system_prompt))
        messages.append(Message(role="user", content=self._build_user_msg(agent, prompt, context)))
        return messages

    def _build_user_msg(
        self,
        agent: SubagentSpec,
        prompt: str,
        context: Mapping[str, Any],
    ) -> str:
        # Same as v0.7.1 — include context so the sub-agent knows what
        # the parent has already done, and (if tools are available) hint
        # that it should prefer them.
        if not (self._include_context and context):
            return prompt
        visible = {
            k: v for k, v in context.items()
            if not k.startswith("__subagent_")
        }
        if not visible:
            return prompt
        ctx_str = "\n".join(
            f"- {k}: {repr(v)[:200]}" for k, v in visible.items()
        )
        return (
            f"Task: {prompt}\n\n"
            f"Parent context:\n{ctx_str}\n\n"
            "Complete the task and return a concise result."
        )

    # ----- single-call (v0.7.1 behavior) ----------------------------------

    def _single_call(self, messages: list[Message], result_holder: SubagentResult) -> str:
        if result_holder.cancel_event.is_set():
            return "[cancelled]"
        resp = self._client.chat(
            list(messages),
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        content = self._extract_content(resp)
        return self._strip_thinking(content)

    # ----- tool-use loop --------------------------------------------------

    def _tool_use_loop(self, messages: list[Message], result_holder: SubagentResult) -> str:
        """Iteratively call chat() and dispatch tool calls until the
        model produces a final answer."""
        assert self._tool_registry is not None  # checked by caller
        tool_schemas = self._tool_registry.openai_schemas()
        final_content = ""

        for iteration in range(self._max_tool_iterations):
            if result_holder.cancel_event.is_set():
                return "[cancelled]"

            resp = self._client.chat(
                list(messages),
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                tools=tool_schemas,
            )

            # Post-call cancellation check: if the user cancelled while
            # the LLM was generating, bail out now — don't keep looping.
            if result_holder.cancel_event.is_set():
                return "[cancelled]"

            # Extract content + tool calls (frozen dataclass, so we
            # reconstruct Message objects from fields we have).
            content = self._extract_content(resp)
            raw_calls: Any = getattr(resp, "tool_calls", ()) or ()
            tool_calls: tuple[Any, ...] = tuple(raw_calls)

            # No tool calls? Model produced a final answer — done.
            if not tool_calls:
                return self._strip_thinking(content)

            # Otherwise: append the assistant message (with its tool_calls)
            # to the conversation, then dispatch each tool call and
            # append a `role="tool"` response for each.
            messages.append(Message(
                role="assistant",
                content=content or "",
            ))
            for call in tool_calls:
                result = self._tool_registry.dispatch(call)
                logger.info(
                    "subagent tool-use iter=%d call=%s ok=%s",
                    iteration, call.name, result.error is None,
                )
                messages.append(Message(
                    role="tool",
                    content=result.to_message_content(),
                    name=call.name,
                    tool_call_id=call.id,
                ))

            # Stash the latest content as the running best-answer.
            # If we hit the iteration cap below, the user gets this.
            final_content = content or final_content

        # Hit max_tool_iterations. The model kept wanting more tools —
        # return what we have so far. Caller can re-prompt with a
        # reminder if needed.
        logger.warning(
            "LLMRunner hit max_tool_iterations=%d, returning best so far",
            self._max_tool_iterations,
        )
        return self._strip_thinking(final_content) or "[max_tool_iterations reached with no content]"

    # ----- helpers --------------------------------------------------------

    @staticmethod
    def _extract_content(resp: Any) -> str:
        if hasattr(resp, "content"):
            return resp.content if isinstance(resp.content, str) else str(resp.content)
        return str(resp)

    @staticmethod
    def _strip_thinking(content: str) -> str:
        # v0.7.1 quirk: reasoning models emit <think>...</think> blocks
        # before the actual answer. Strip them so the calling context
        # only sees the useful bit.
        if "<think>" in content and "</think>" in content:
            return content.split("</think>", 1)[-1].strip()
        return content


__all__ = ["LLMRunner", "DEFAULT_MAX_TOOL_ITERATIONS"]
