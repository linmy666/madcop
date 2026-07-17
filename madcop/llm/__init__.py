"""L7 — LLM client + prompts + multi-vendor harness."""

from .client import (
    ChatClient,
    ChatResponse,
    Message,
    MockClient,
    OpenAICompatClient,
    StreamChunk,
    ToolCall,
    make_client,
)
from .harness import ProviderHarness, infer_context_window, resolve_harness
from . import prompts

__all__ = [
    "ChatClient",
    "ChatResponse",
    "Message",
    "MockClient",
    "OpenAICompatClient",
    "StreamChunk",
    "ToolCall",
    "make_client",
    "ProviderHarness",
    "resolve_harness",
    "infer_context_window",
    "prompts",
]