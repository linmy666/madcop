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
from .factory import build_client_from_config, merge_agent_routing
from .retry import is_retryable_error, with_retry
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
    "build_client_from_config",
    "merge_agent_routing",
    "is_retryable_error",
    "with_retry",
    "prompts",
]