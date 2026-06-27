"""madcop.server — FastAPI app with settings API + chat SSE + memory.

Routes:
  /               — WebUI (static HTML)
  /api/health     — health check
  /api/settings   — GET (masked) / POST (plaintext -> encrypted)
  /api/settings/active — POST (set active provider)
  /api/settings/{id}   — DELETE (remove provider)
  /api/chat       — POST -> SSE stream of StreamChunks (with memory injection)
  /api/memory     — GET (list) / POST (add)
  /api/memory/search — GET (search ?q=)
  /api/memory/{id}   — DELETE
  /docs           — Swagger UI
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from madcop.config import settings as settings_store
from madcop.llm import Message, MockClient, OpenAICompatClient
from madcop.memory import (
    MemoryStore,
    EpisodicMemory,
    SemanticMemory,
    ReflectiveMemory,
    Retriever,
)
from madcop.memory.retriever import RetrievalConfig
from madcop.tools import default_registry

# --------------------------------------------------------------------------- #
# Pydantic models
# --------------------------------------------------------------------------- #

class ProviderInput(BaseModel):
    provider_id: str
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    label: str = ""
    make_active: bool = True


class ChatMessage(BaseModel):
    role: str = "user"
    content: str = ""


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = 0.7


class SetActiveRequest(BaseModel):
    provider_id: str


class MemoryCreateRequest(BaseModel):
    """Manual memory creation via API."""
    kind: str = "semantic"          # "episodic" | "semantic" | "reflective"
    title: str
    content: str = ""
    tags: list[str] = []


# --------------------------------------------------------------------------- #
# Memory helpers
# --------------------------------------------------------------------------- #

# Module-level singleton — lazily initialised so tests can swap it.
_memory_store: MemoryStore | None = None


def get_memory_store() -> MemoryStore:
    """Return (and lazily create) the global MemoryStore singleton."""
    global _memory_store
    if _memory_store is None:
        _memory_store = MemoryStore()
    return _memory_store


def reset_memory_store(store: MemoryStore) -> None:
    """Replace the global store — used by tests for isolation."""
    global _memory_store
    _memory_store = store


def _build_memory_system_prompt(user_query: str) -> str:
    """Build a system prompt enriched with relevant memories + user prefs.

    Steps:
    1. Always include user-profile facts (name, preferences) from L3 —
       these are critical context regardless of the query.
    2. Search all layers for memories relevant to *user_query*.
    3. Fetch L4 user preferences / dislikes.
    4. Format into a single system-prompt string.
    """
    store = get_memory_store()
    retriever = Retriever(
        episodic=EpisodicMemory(store),
        semantic=SemanticMemory(store),
        reflective=ReflectiveMemory(store),
    )
    parts: list[str] = [
        "You are madcop, a personal AI agent. "
        "You can remember facts about the user across sessions."
    ]

    # --- user-profile facts (always injected) --------------------------- #
    # These are memories tagged "user-profile" — e.g. the user's
    # name.  We always include them because identity is always relevant.
    # We query MemoryStore directly (returns MemoryRecord) so both
    # auto-extracted (Fact) and manually-added (MemoryRecord) memories
    # are surfaced — SemanticMemory.list_recent returns Fact objects
    # which only have subject/predicate/object.
    try:
        # Direct SQL query: recent memory_records tagged user-profile
        rows = store._conn.execute(
            "SELECT id, kind, title, content, tags FROM memory_records "
            "WHERE tags LIKE '%user-profile%' "
            "ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
        profile_lines: list[str] = []
        for row in rows:
            content = row["content"] or ""
            text = content
            if text.startswith("{"):
                try:
                    parsed = __import__("json").loads(text)
                    text = parsed.get("object") or row["title"] or ""
                except Exception:
                    text = row["title"] or ""
            if text:
                profile_lines.append(f"- {text}")
        if profile_lines:
            parts.append("# Known facts about the user\n" + "\n".join(profile_lines))
    except Exception:
        pass

    # --- relevant memories (L2/L3/L4 via FTS5) -------------------------- #
    try:
        results = retriever.retrieve(user_query)
    except Exception:
        results = []
    if results:
        ctx = retriever.format_for_prompt(results)
        if ctx:
            parts.append(ctx)

    # --- L4 user preferences -------------------------------------------- #
    try:
        prefs = ReflectiveMemory(store).find_preferences(limit=10)
    except Exception:
        prefs = []
    if prefs:
        lines = ["\n# User preferences"]
        for p in prefs:
            tag = "likes" if p.kind.value == "user_preference" else "dislikes"
            lines.append(f"- User {tag}: {p.text}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


# --- Heuristic fact extraction (no LLM call) ------------------------------- #

# Regex patterns for common fact-bearing sentences.
_NAME_PATTERNS = [
    # 我叫X (X is not "谁"/null/whitespace/etc.)
    re.compile(r"我(?:叫|是)\s*(\S+?)[\s,，。.!？?！]", re.UNICODE),
    re.compile(r"(?:my name is|i am|i'm)\s+([A-Za-z][\w'-]{0,30})", re.IGNORECASE),
]
# Words that should NOT be treated as a name (question words, pronouns)
_NAME_BLACKLIST = {"谁", "什么", "哪", "我", "你", "他", "她", "它", "的"}

_PREF_PATTERNS = [
    re.compile(r"我(?:喜欢|偏好|爱)\s*(.{2,40}?)[\s,，。.!？?！]", re.UNICODE),
    re.compile(r"(?:i like|i prefer|i love)\s+(.{2,60}?)[\s.,，!?！]", re.IGNORECASE),
]


def _extract_facts_from_text(text: str) -> list[dict]:
    """Return a list of ``{title, content, tags}`` dicts for auto-extraction.

    Uses simple regex heuristics — no LLM call.  Only covers the two
    patterns requested: user name and user preference.
    """
    extracted: list[dict] = []

    for pat in _NAME_PATTERNS:
        m = pat.search(text)
        if m:
            name = m.group(1).strip()
            # Reject question words and pronouns
            if name in _NAME_BLACKLIST or len(name) < 1:
                continue
            extracted.append({
                "title": f"User name: {name}",
                "content": f"The user's name is {name}.",
                "tags": ["auto-extracted", "user-profile", "name"],
            })
            break  # one name is enough

    for pat in _PREF_PATTERNS:
        for m in pat.finditer(text):
            pref = m.group(1).strip().rstrip(".,")
            if len(pref) < 2:
                continue
            extracted.append({
                "title": f"User likes: {pref}",
                "content": f"The user likes/prefers {pref}.",
                "tags": ["auto-extracted", "user-profile", "preference"],
            })

    return extracted


def _store_extracted_facts(messages: list[Message]) -> int:
    """Scan user messages for extractable facts and store them in L3.

    Returns the number of facts stored.
    """
    store = get_memory_store()
    sem = SemanticMemory(store)
    count = 0
    for msg in messages:
        if msg.role != "user" or not msg.content:
            continue
        for fact in _extract_facts_from_text(msg.content):
            sem.add(
                subject="user",
                predicate="has_property",
                object=fact["content"],
                tags=tuple(fact["tags"]),
            )
            count += 1
    return count


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #

def create_app() -> FastAPI:
    app = FastAPI(title="madcop", version="2.1.0", docs_url="/docs")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------- #
    # Health
    # ------------------------------------------------------------------- #

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": "2.1.0"}

    # ------------------------------------------------------------------- #
    # Settings
    # ------------------------------------------------------------------- #

    @app.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        s = settings_store.load_settings()
        return settings_store.settings_to_public_dict(s)

    @app.post("/api/settings")
    async def post_settings(body: ProviderInput) -> dict[str, Any]:
        s = settings_store.load_settings()
        s = settings_store.upsert_provider(
            s,
            provider_id=body.provider_id,
            base_url=body.base_url,
            api_key=body.api_key,
            model=body.model,
            label=body.label,
            make_active=body.make_active,
        )
        settings_store.save_settings(s)
        return settings_store.settings_to_public_dict(s)

    @app.post("/api/settings/active")
    async def set_active_provider(body: SetActiveRequest) -> dict[str, Any]:
        s = settings_store.load_settings()
        ids = [p.provider_id for p in s.providers]
        if body.provider_id not in ids:
            raise HTTPException(404, f"provider '{body.provider_id}' not found")
        s.active_provider = body.provider_id
        settings_store.save_settings(s)
        return settings_store.settings_to_public_dict(s)

    @app.delete("/api/settings/{provider_id}")
    async def delete_provider(provider_id: str) -> dict[str, Any]:
        s = settings_store.load_settings()
        s.providers = [p for p in s.providers if p.provider_id != provider_id]
        if s.active_provider == provider_id:
            s.active_provider = s.providers[0].provider_id if s.providers else ""
        settings_store.save_settings(s)
        return settings_store.settings_to_public_dict(s)

    # ------------------------------------------------------------------- #
    # Chat (SSE streaming)
    # ------------------------------------------------------------------- #

    def _get_client():
        """Build an LLM client from stored settings, fall back to Mock."""
        s = settings_store.load_settings()
        cfg = settings_store.get_active_client_config(s)
        if cfg and cfg.get("api_key"):
            return OpenAICompatClient(
                api_key=cfg["api_key"],
                base_url=cfg["base_url"],
                model=cfg["model"],
            )
        # No key configured — use mock so the UI still works for demo
        return MockClient(
            default_response="⚠️ No API key configured. Open Settings (⚙️) to add one."
        )

    def _stream_chunks(client, messages, body):
        """Yield SSE formatted strings from a streaming LLM call."""
        for chunk in client.stream(
            messages,
            model=body.model,
            temperature=body.temperature,
        ):
            if chunk.reasoning:
                yield f"data: {json.dumps({'type': 'reasoning', 'content': chunk.reasoning})}\n\n"
            if chunk.text:
                yield f"data: {json.dumps({'type': 'text', 'content': chunk.text})}\n\n"
            if chunk.finish_reason:
                yield f"data: {json.dumps({'type': 'done', 'model': chunk.model, 'finish_reason': chunk.finish_reason})}\n\n"

    @app.post("/api/chat")
    async def chat(body: ChatRequest) -> StreamingResponse:
        """Stream chat completion as SSE events.

        Memory integration:
        1. Before the LLM call: build a system prompt with relevant
           memories + user prefs and prepend it to the messages.
        2. After the stream: extract facts (name, preferences) from
           user messages and store them in L3 semantic memory.

        Tool-use flow:
        1. Call LLM with tools schema. If it returns text (no tool_calls),
           stream normally.
        2. If it returns tool_calls, execute each tool, emit SSE progress
           events, then make a second LLM call with the tool results and
           stream that response.

        SSE format:
          data: {"type":"text","content":"Hello"}

          data: {"type":"tool","name":"weather","args":{...}}

          data: {"type":"tool_result","name":"weather","result":"..."}

          data: {"type":"done","model":"..."}
        """
        client = _get_client()
        messages = [Message(role=m.role, content=m.content) for m in body.messages]

        # ---- Memory injection (before LLM call) ---------------------- #
        # Find the latest user message and use it as the retrieval query.
        latest_user_msg = ""
        for m in reversed(messages):
            if m.role == "user":
                latest_user_msg = m.content
                break
        if latest_user_msg:
            try:
                sys_prompt = _build_memory_system_prompt(latest_user_msg)
            except Exception:
                sys_prompt = (
                    "You are madcop, a personal AI agent. "
                    "You can remember facts about the user across sessions."
                )
        else:
            sys_prompt = (
                "You are madcop, a personal AI agent. "
                "You can remember facts about the user across sessions."
            )
        # Prepend system prompt (replace if one already exists)
        if messages and messages[0].role == "system":
            messages[0] = Message(role="system", content=sys_prompt)
        else:
            messages.insert(0, Message(role="system", content=sys_prompt))

        registry = default_registry()
        tool_schemas = registry.openai_schemas()

        async def event_stream() -> AsyncIterator[str]:
            try:
                # -- Phase 1: initial call with tools ------------------ #
                # Use non-streaming chat() for the first call so we can
                # inspect tool_calls before deciding how to proceed.
                resp = client.chat(
                    messages,
                    model=body.model,
                    temperature=body.temperature,
                    tools=tool_schemas,
                )

                # No tool calls? Stream the text content normally.
                if not resp.tool_calls:
                    for sse in _stream_chunks(client, messages, body):
                        yield sse
                    # -- Memory extraction (after response) -------------- #
                    try:
                        _store_extracted_facts(messages)
                    except Exception:
                        pass
                    return

                # Has tool calls — execute them, then do a second call.
                # First, append the assistant's tool-call message WITH
                # the tool_calls so the API accepts the following tool
                # messages.
                messages.append(Message(
                    role="assistant",
                    content=resp.content or "",
                    tool_calls=resp.tool_calls,
                ))

                # Execute each tool call and collect results.
                for call in resp.tool_calls:
                    yield f"data: {json.dumps({'type': 'tool', 'name': call.name, 'args': call.arguments}, ensure_ascii=False)}\n\n"
                    result = registry.dispatch(call)
                    result_str = result.to_message_content()
                    # Emit the tool result as an SSE event
                    yield f"data: {json.dumps({'type': 'tool_result', 'name': call.name, 'result': result_str}, ensure_ascii=False)}\n\n"
                    # Append tool result to the conversation for the second call
                    messages.append(Message(
                        role="tool",
                        content=result_str,
                        name=call.name,
                        tool_call_id=call.id,
                    ))

                # -- Phase 2: second call with tool results ------------ #
                # Stream the final response normally.
                for sse in _stream_chunks(client, messages, body):
                    yield sse

                # -- Memory extraction (after response) ------------------ #
                try:
                    _store_extracted_facts(messages)
                except Exception:
                    pass

            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    # ------------------------------------------------------------------- #
    # Memory CRUD API
    # ------------------------------------------------------------------- #

    @app.get("/api/memory")
    async def list_memory() -> dict[str, Any]:
        """List all memories, grouped by kind (episodic / semantic / reflective)."""
        store = get_memory_store()
        result: dict[str, Any] = {}

        from madcop.memory import MemoryKind
        for kind_label, mk in [
            ("episodic", MemoryKind.EPISODIC),
            ("semantic", MemoryKind.SEMANTIC),
            ("reflective", MemoryKind.REFLECTIVE),
        ]:
            records = store.list_by_kind(mk, limit=200)
            result[kind_label] = [
                {
                    "id": r.id,
                    "kind": r.kind.value,
                    "title": r.title,
                    "content": r.content,
                    "tags": list(r.tags),
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                }
                for r in records
            ]
        result["total"] = store.total_count()
        return result

    @app.post("/api/memory")
    async def add_memory(body: MemoryCreateRequest) -> dict[str, Any]:
        """Manually add a memory record."""
        from madcop.memory import MemoryKind
        kind_map = {
            "episodic": MemoryKind.EPISODIC,
            "semantic": MemoryKind.SEMANTIC,
            "reflective": MemoryKind.REFLECTIVE,
        }
        mk = kind_map.get(body.kind)
        if mk is None:
            raise HTTPException(400, f"Invalid kind '{body.kind}'. "
                                     f"Must be one of: {list(kind_map)}")
        store = get_memory_store()
        rec = store.insert(
            kind=mk,
            title=body.title,
            content=body.content,
            tags=tuple(body.tags),
        )
        return {
            "id": rec.id,
            "kind": rec.kind.value,
            "title": rec.title,
            "content": rec.content,
            "tags": list(rec.tags),
            "created_at": rec.created_at,
        }

    @app.delete("/api/memory/{memory_id}")
    async def delete_memory(memory_id: str) -> dict[str, Any]:
        """Delete a memory by ID."""
        store = get_memory_store()
        deleted = store.delete(memory_id)
        if not deleted:
            raise HTTPException(404, f"Memory '{memory_id}' not found")
        return {"deleted": True, "id": memory_id}

    @app.get("/api/memory/search")
    async def search_memory(q: str = Query(..., description="Search query")) -> dict[str, Any]:
        """Full-text search across all memory layers."""
        from madcop.memory import MemoryKind
        store = get_memory_store()
        # Quote the query to avoid FTS5 syntax errors with special chars
        safe_q = q.replace('"', '""')
        records = store.search_fts(f'"{safe_q}"', limit=50)
        return {
            "query": q,
            "count": len(records),
            "results": [
                {
                    "id": r.id,
                    "kind": r.kind.value,
                    "title": r.title,
                    "content": r.content,
                    "tags": list(r.tags),
                    "created_at": r.created_at,
                }
                for r in records
            ],
        }

    # ------------------------------------------------------------------- #
    # WebUI (static HTML at /)
    # ------------------------------------------------------------------- #

    web_dir = Path(__file__).resolve().parent.parent.parent / "web"
    if web_dir.exists():
        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(web_dir / "index.html", media_type="text/html")

        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    return app


# Module-level app for uvicorn
app = create_app()
