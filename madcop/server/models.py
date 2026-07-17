"""Shared API models and limits for madcop.server."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

_MAX_CHAT_CONTENT_CHARS = 500_000
_MAX_CHAT_MESSAGES = 200
_MAX_ATTACHMENT_DATAURL_CHARS = 2_500_000

class ProviderInput(BaseModel):
    provider_id: str
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    label: str = ""
    make_active: bool = True
    # Extended fields — previously dropped by Pydantic at the API boundary,
    # which is why editing them in the UI never persisted. Now round-tripped.
    preset_id: str | None = None
    api_format: str | None = None
    auth_strategy: str | None = None
    runtime_kind: str | None = None
    tool_search_enabled: bool | None = None
    notes: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    top_p: float | None = None
    auto_compact_window: int | None = None
    model_params: dict | None = None

class FetchModelsRequest(BaseModel):
    """Fetch the live model list from a provider's /v1/models endpoint.

    The caller passes the base_url + api_key they are *currently* typing
    into the settings form (not a saved provider), so the UI can populate
    the model dropdown before the provider is persisted.
    """
    base_url: str = ""
    api_key: str = ""

class ChatMessage(BaseModel):
    role: str = "user"
    content: str = Field(default="", max_length=_MAX_CHAT_CONTENT_CHARS)
    # Optional client-side id — when set, backend persists with the same id
    # so branch/rewind can match frontend transcriptMessageId.
    id: str | None = None

class ChatAttachment(BaseModel):
    id: str
    name: str
    type: str = "file"
    path: str | None = None
    dataUrl: str | None = Field(default=None, max_length=_MAX_ATTACHMENT_DATAURL_CHARS)

    @field_validator("dataUrl")
    @classmethod
    def _reject_huge_dataurl(cls, v: str | None) -> str | None:
        if v is not None and len(v) > _MAX_ATTACHMENT_DATAURL_CHARS:
            raise ValueError(
                f"attachment dataUrl too large ({len(v)} > {_MAX_ATTACHMENT_DATAURL_CHARS})"
            )
        return v

class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(default_factory=list, max_length=_MAX_CHAT_MESSAGES)
    model: str | None = None
    temperature: float | None = None  # None = use provider config default
    max_tokens: int | None = None  # None = use provider config default
    conversation_id: str | None = None  # optional id for trace persistence
    skip_title_gen: bool = False  # set true to skip Claude-style auto title generation
    attachments: list[ChatAttachment] = []  # file/image attachments from the user
    plan_mode: bool = False  # enable Plan-and-Execute mode
    effort: str | None = None  # reasoning intensity: auto|low|medium|high|max (per session)
    agent_mode: str | None = None  # unified mode: auto|quick|standard|deep (overrides workflow)
    # Session project folder — file tools read/write here. Prefer over global workspace state.
    work_dir: str | None = None

class SetActiveRequest(BaseModel):
    provider_id: str

class MemoryCreateRequest(BaseModel):
    """Manual memory creation via API."""
    kind: str = "semantic"          # "episodic" | "semantic" | "reflective"
    title: str
    content: str = ""
    tags: list[str] = []

