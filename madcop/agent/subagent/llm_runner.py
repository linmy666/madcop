"""v0.7.1 — A real-LLM-backed Runner for sub-agents.

LLMRunner wraps any ChatClient (e.g. madcop.llm.OpenAICompatClient) and
adapts it to the sub-agent Runner protocol. Each sub-agent invocation
becomes a single chat() call with the sub-agent's system_prompt and the
task prompt as the user message.

Usage:
    from madcop.llm import OpenAICompatClient
    from madcop.agent.subagent import SubagentExecutor, ExecutorConfig
    from madcop.agent.subagent.llm_runner import LLMRunner

    client = OpenAICompatClient()
    runner = LLMRunner(client, max_tokens=512, temperature=0.0)
    executor = SubagentExecutor(runner=runner, config=ExecutorConfig(max_concurrent=3))

The runner is intentionally simple — one chat() call per sub-agent.
A real production system might need multi-turn tool-use here, but for
v0.7.1 a single response is enough.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

from ...llm import ChatClient, Message
from .executor import Runner
from .spec import SubagentSpec
from .status import SubagentResult

logger = logging.getLogger(__name__)


class LLMRunner(Runner):
    """Adapt a ChatClient to the sub-agent Runner protocol.

    Each call to `run()` performs one chat() round:
      - system: the sub-agent's system_prompt
      - user:   the task prompt (with optional context summary)

    The response content is returned as the sub-agent's output.
    """

    def __init__(
        self,
        client: ChatClient,
        *,
        max_tokens: int | None = 512,
        temperature: float = 0.0,
        include_context: bool = True,
    ):
        self._client = client
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._include_context = include_context

    def run(
        self,
        *,
        agent: SubagentSpec,
        prompt: str,
        context: Mapping[str, Any],
        result_holder: SubagentResult,
    ) -> str:
        # Build user message — optionally include a context summary so
        # the sub-agent knows what the parent has already done.
        if self._include_context and context:
            # Filter out the runner's own internal keys
            visible = {
                k: v for k, v in context.items()
                if not k.startswith("__subagent_")
            }
            if visible:
                ctx_str = "\n".join(
                    f"- {k}: {repr(v)[:200]}" for k, v in visible.items()
                )
                user_msg = (
                    f"Task: {prompt}\n\n"
                    f"Parent context:\n{ctx_str}\n\n"
                    "Complete the task and return a concise result."
                )
            else:
                user_msg = prompt
        else:
            user_msg = prompt

        # Build messages
        messages = []
        if agent.system_prompt:
            messages.append(Message(role="system", content=agent.system_prompt))
        messages.append(Message(role="user", content=user_msg))

        # Cancellation check before the call
        if result_holder.cancel_event.is_set():
            return "[cancelled]"

        # Make the call. If the LLM returns a thinking block, strip it.
        resp = self._client.chat(
            messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        content = resp.content if hasattr(resp, "content") else str(resp)

        if isinstance(content, str) and "<think>" in content and "</think>" in content:
            content = content.split("</think>", 1)[-1].strip()

        return content


__all__ = ["LLMRunner"]
