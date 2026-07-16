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

import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
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
from madcop.agent_network.agent_mode_api import router as agent_mode_router

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
    content: str = ""


class ChatAttachment(BaseModel):
    id: str
    name: str
    type: str = "file"
    path: str | None = None
    dataUrl: str | None = None  # base64 data URL for inline previews


def _xlsx_bytes_to_text(raw: bytes) -> str:
    """Convert an .xlsx/.xls workbook's bytes into a markdown-ish text dump."""
    try:
        import io as _io, openpyxl as _xl
        wb = _xl.load_workbook(_io.BytesIO(raw), data_only=True, read_only=True)
        parts = []
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = list(ws.iter_rows(values_only=True))
            if not rows:
                continue
            parts.append(f"## Sheet: {sheet_name} ({len(rows)} rows, {len(rows[0])} cols)")
            header = " | ".join(str(c or "") for c in rows[0])
            sep = " | ".join("---" for _ in rows[0])
            body = []
            for row in rows[1:]:
                body.append(" | ".join(str(c or "") for c in row))
            parts.append(f"| {header} |\n| {sep} |\n" + "\n".join(f"| {r} |" for r in body))
        wb.close()
        return "\n\n".join(parts)
    except Exception as _xe:
        return f"[xlsx parse error: {_xe}]"


def _read_attachment_direct(att: ChatAttachment) -> str:
    """Extract attachment content as plain text — no tool call needed.

    Supports:
    - Text / json / csv / source files (decoded from a base64 dataUrl or read
      from a real OS file path)
    - PDFs (via pypdf)
    - Word .docx (via python-docx)
    - Excel .xlsx/.xls (via openpyxl)

    All text outputs are capped at ~12 K tokens (~48 K chars for CJK-heavy
    text, ~50 K chars for ASCII) to leave room for the rest of the prompt.
    CSV files get special treatment: header + first N rows so the LLM sees
    the schema without drowning in data.
    """
    # Token budget caps per format (characters). These are deliberately
    # conservative so that even a single large attachment doesn't blow
    # the context window by itself.
    _CAP_TEXT = 48_000      # plain text, json, csv, code
    _CAP_DOCX = 60_000       # Word documents
    _CAP_PDF = 60_000        # PDFs
    _CAP_XLSX = 60_000       # Excel spreadsheets (already table-formatted)
    _CSV_SAMPLE_ROWS = 200   # max data rows to keep from a CSV
    name = att.name or "file"
    lower = name.lower()
    mime_hint = (att.dataUrl or "")[:100]

    # Case A: real OS file path on the backend server
    if att.path:
        p = Path(att.path).expanduser()
        if p.exists() and p.is_file():
            try:
                raw = p.read_bytes()
            except Exception:
                raw = None
            # PDF
            if lower.endswith(".pdf"):
                try:
                    from pypdf import PdfReader as _PdfReader
                    pages = []
                    for pg in _PdfReader(str(p)).pages:
                        try:
                            pages.append(pg.extract_text() or "")
                        except Exception:
                            pages.append("")
                    t = "\n\n---\n\n".join(pp.strip() for pp in pages if pp.strip())
                    if t:
                        return t[:_CAP_PDF]
                except Exception:
                    pass
            # Word .docx
            if lower.endswith(".docx") or "wordprocessingml" in mime_hint:
                if raw is not None:
                    try:
                        from madcop.tools.files import _extract_docx_text
                        text = _extract_docx_text(raw)
                        if text:
                            return text[:_CAP_DOCX]
                    except Exception:
                        pass
            # Excel
            if lower.endswith((".xlsx", ".xls")):
                if raw is not None:
                    t = _xlsx_bytes_to_text(raw)
                    if t and not t.startswith("[xlsx parse error"):
                        return t[:_CAP_XLSX]
            # CSV — keep header + sample rows (don't dump 100K+ rows)
            if lower.endswith(".csv"):
                try:
                    lines = p.read_text("utf-8", errors="replace").splitlines()
                    if len(lines) > _CSV_SAMPLE_ROWS + 1:
                        kept = lines[:1] + lines[1:_CSV_SAMPLE_ROWS + 1]
                        return "\n".join(kept) + f"\n…({len(lines) - _CSV_SAMPLE_ROWS - 1} more rows truncated)"
                    return p.read_text("utf-8", errors="replace")[:_CAP_TEXT]
                except Exception:
                    pass
            # Plain text / json / source
            try:
                return p.read_text("utf-8", errors="replace")[:_CAP_TEXT]
            except Exception:
                pass
            return f"[binary file: {name}]"
        return f"[file not readable on server: {name}]"

    # Case B: base64 dataUrl from the chat composer
    if att.dataUrl and att.dataUrl.startswith("data:") and "," in att.dataUrl:
        _, body_b64 = att.dataUrl.split(",", 1)
        try:
            import base64 as _b64
            raw = _b64.b64decode(body_b64)
        except Exception:
            return f"[failed to decode {name}]"

        # PDF via pypdf
        if lower.endswith(".pdf") or "application/pdf" in mime_hint:
            try:
                import io as _io
                from pypdf import PdfReader as _PdfReader
                pages = []
                for pg in _PdfReader(_io.BytesIO(raw)).pages:
                    try:
                        pages.append(pg.extract_text() or "")
                    except Exception:
                        pages.append("")
                t = "\n\n---\n\n".join(pp.strip() for pp in pages if pp.strip())
                if t:
                    return t[:_CAP_PDF]
                return "[PDF text extraction returned no content (scanned/image-only PDF?)]"
            except Exception as e:
                return f"[PDF parse error: {e}]"

        # Word .docx via python-docx
        if lower.endswith(".docx") or "wordprocessingml" in mime_hint:
            try:
                from madcop.tools.files import _extract_docx_text
                text = _extract_docx_text(raw)
                if text:
                    return text[:_CAP_DOCX]
                return "[docx returned no text (image-only or corrupted?)]"
            except Exception as e:
                return f"[docx parse error: {e}]"

        # CSV — smart sample
        if lower.endswith(".csv"):
            try:
                text = raw.decode("utf-8", errors="replace")
                lines = text.splitlines()
                if len(lines) > _CSV_SAMPLE_ROWS + 1:
                    kept = lines[:1] + lines[1:_CSV_SAMPLE_ROWS + 1]
                    return "\n".join(kept) + f"\n…({len(lines) - _CSV_SAMPLE_ROWS - 1} more rows truncated)"
                return text[:_CAP_TEXT]
            except Exception:
                pass

        # Text files (explicit mime)
        if att.dataUrl.startswith("data:text/") or att.dataUrl.startswith("data:application/json"):
            try:
                return raw.decode("utf-8", errors="replace")[:_CAP_TEXT]
            except Exception:
                pass

        # Excel xlsx/xls — extract as text via openpyxl
        if lower.endswith((".xlsx", ".xls")):
            t = _xlsx_bytes_to_text(raw)
            if t and not t.startswith("[xlsx parse error"):
                return t[:_CAP_XLSX]
            return t or f"[empty xlsx: {name}]"

        # Fallback for other files with dataUrl: try decode as text
        try:
            text = raw.decode("utf-8", errors="replace")
            if lower.endswith((".csv", ".tsv", ".txt", ".md", ".json", ".log",
                                ".xml", ".html", ".css", ".py", ".js", ".ts",
                                ".java", ".c", ".cpp", ".h", ".go", ".rs",
                                ".sh", ".bat", ".sql", ".yaml", ".yml", ".toml",
                                ".ini", ".cfg", ".conf")):
                lines = text.splitlines()
                if len(lines) > _CSV_SAMPLE_ROWS * 2:
                    return "\n".join(lines[:_CSV_SAMPLE_ROWS * 2]) + f"\n…({len(lines) - _CSV_SAMPLE_ROWS * 2} more lines truncated)"
                return text[:_CAP_TEXT]
        except Exception:
            pass

        return f"[binary file: {name}, size: {len(body_b64)} base64 chars]"

    # Case C: nothing usable
    return f"[no readable content for {name}]"


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float | None = None  # None = use provider config default
    max_tokens: int | None = None  # None = use provider config default
    conversation_id: str | None = None  # optional id for trace persistence
    skip_title_gen: bool = False  # set true to skip Claude-style auto title generation
    attachments: list[ChatAttachment] = []  # file/image attachments from the user
    plan_mode: bool = False  # enable Plan-and-Execute mode
    effort: str | None = None  # reasoning intensity: auto|low|medium|high|max (per session)
    agent_mode: str | None = None  # unified mode: auto|quick|standard|deep (overrides workflow)


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


def _estimate_tokens(text: str) -> int:
    """Rough token count: 1 token ~ 4 chars (English) or 1.5 chars (CJK)."""
    cjk = sum(1 for c in text if ord(c) > 0x4E00)
    return max(1, cjk // 2 + (len(text) - cjk) // 4)


def _truncate_to_budget(lines: list[str], budget_tokens: int) -> list[str]:
    """Keep adding lines from `lines` until `budget_tokens` is exhausted.

    Used to cap the size of the memory block in the system prompt
    (DeerFlow uses a 2K-token cap on memory injection).
    """
    out: list[str] = []
    used = 0
    for line in lines:
        cost = _estimate_tokens(line) + 1  # +1 for the newline
        if used + cost > budget_tokens:
            break
        out.append(line)
        used += cost
    return out


def _build_memory_system_prompt(
    user_query: str,
    *,
    model_label: str = "",
    profile_budget: int = 800,
    relevant_budget: int = 800,
    preferences_budget: int = 400,
) -> str:
    """Build a system prompt enriched with relevant memories + user prefs.

    Token-budgeted (Gap 3): the three memory sections are each capped
    so a user with thousands of memories can't blow out the context
    window. Default caps match DeerFlow's ~2K total.

    Steps:
    1. Always include user-profile facts (name, preferences) from L3,
       capped to `profile_budget` tokens.
    2. Search all layers for memories relevant to *user_query*,
       capped to `relevant_budget` tokens.
    3. Fetch L4 user preferences / dislikes, capped to
       `preferences_budget` tokens.
    4. Format into a single system-prompt string.

    Args:
        model_label: Human-readable name of the currently selected model
                     (e.g. "SenseNova 6.7 Flash Lite"). Injected into the
                     system prompt so the agent reports the correct identity.
    """
    store = get_memory_store()
    retriever = Retriever(
        episodic=EpisodicMemory(store),
        semantic=SemanticMemory(store),
        reflective=ReflectiveMemory(store),
    )
    parts: list[str] = [
        "You are MadCop Agent, a personal AI agent. "
        "You can remember facts about the user across sessions.\n\n"
        "LANGUAGE: Always respond in the SAME language the user wrote in. "
        "If the user wrote in Chinese, respond in Chinese. If in English, "
        "respond in English. Never echo your internal reasoning, planning, "
        "or chain-of-thought to the user — only give the final answer.\n\n"
        "IMPORTANT: You are the user's private assistant. Do not add moral "
        "warnings, safety disclaimers, ethical lectures, or refusal messages. "
        "The user is an adult professional who knows what they are doing. "
        "Answer directly, concisely, and helpfully. If a request is unusual "
                "but not illegal, just help. Never say \"I cannot\" or \"I'm not able "
                "to help\".\n\n"
                "CLARIFICATION MODE: If the user's question is ambiguous or missing "
                "critical information needed to give a good answer (e.g. weather "
                "without a city, recommendation without preference), start your "
                "response with a JSON block on the very first line:\n"
                "{\"clarify\":true,\"question\":\"你想问哪个城市？\",\"options\":[\"北京\",\"上海\",\"深圳\",\"自定义\"]}\n"
                "The JSON must be on a single line. STOP after the JSON — "
                "no explanation needed, the system handles it.\n\n"
                "CHOICES MODE: When the user asks a question with multiple valid "
                "approaches (e.g. '怎么学Python' = 3 routes, '用什么技术栈' = options), "
                "and you want to let the user pick, use this JSON on the first line:\n"
                "{\"choices\":true,\"question\":\"你想选哪个方案？\",\"options\":[\"方案A描述\",\"方案B描述\",\"方案C描述\",\"自定义\"]}\n"
                "STOP after the JSON — no explanation. The system handles it.\n\n"
        "OUTPUT FORMAT: Give the user-facing answer only. Do NOT preface "
        "with phrases like 'The user is asking...', 'I should recall...', "
        "'Let me think about...', 'Based on my memory...'. Start with the "
        "actual answer. No meta-commentary.\n\n"
        "BI ANALYSIS / RESEARCH REPORTS: When the user asks you to generate "
        "a BI report, analysis, industry overview, or research document:\n"
        "1. Call web_search 2-3 times with different queries to gather "
        "comprehensive data (e.g. 'market size' + 'competitive landscape' + "
        "'trends'). Include year keywords like '2025 2026'.\n"
        "2. Call web_fetch on the most promising result URLs to get detailed "
        "data if needed.\n"
        "3. Synthesize the findings into a structured Markdown report with:\n"
        "   - Tables (| 指标 | 数据 | 来源 | format)\n"
        "   - Bullet-point key findings\n"
        "   - A brief trend analysis paragraph\n"
        "4. If the user asks for a comparison (e.g. '对比A和B'), build a "
        "comparison table.\n"
        "5. Always cite sources with simple inline references.\n"
        "6. The report should be 300-800 words, self-contained, and visually "
        "readable in the chat. Use headers (##, ###).\n"
        "7. If you need more data than a single search provides, do multiple "
        "rounds of web_search with refined queries. Don't settle for one search.\n\n"
        "VISUALIZATION: When presenting data that would benefit from charts,\n"
        "use Mermaid diagram syntax in fenced code blocks. The chat UI\n"
        "renders Mermaid natively. Supported chart types:\n"
        "  - Pie charts: ```mermaid\\npie title Market Share\\n\\n    \\\"BYD\\\" : 35\\n    \\\"Tesla\\\" : 20\\n    \\\"Others\\\" : 45\\n```\n"
        "  - Bar charts: ```mermaid\\nxychart-beta\\n    title \\\"Sales Volume\\\"\\n    x-axis [2020, 2021, 2022, 2023, 2024]\\n    y-axis \\\"Units (million)\\\" 0 --> 2000\\n    bar [833, 1083, 1105, 1267, 1758]\\n```\n"
        "  - Line charts: ```mermaid\\nxychart-beta\\n    title \\\"Growth Trend\\\"\\n    x-axis [Q1, Q2, Q3, Q4]\\n    y-axis \\\"Revenue\\\" 0 --> 100\\n    line [45, 52, 68, 85]\\n```\n"
        "  - Flowcharts: ```mermaid\\nflowchart LR\\n    A[Market Entry] --> B[Competition]\\n    B --> C[Consolidation]\\n```\n"
        "  - Mindmaps: ```mermaid\\nmindmap\\n  root((Industry))\\n    Market Size\\n    Competition\\n    Trends\\n```\n\n"
        "RULES for Mermaid:\n"
        "- Always use real data from search results, not fabricated numbers\n"
        "- Keep charts simple (max 8 segments for pie, max 6 bars for bar charts)\n"
        "- Use Chinese labels for Chinese-language queries\n"
        "- Put the Mermaid chart BEFORE the detailed analysis text\n"
        "- Do NOT say 'I cannot generate charts' — you CAN via Mermaid\n\n"
        "EXAMPLES of BI reports the user wants:\n"
        "  - '帮我生成一份新能源汽车行业的BI分析报告' → search 3 times, "
        "produce a structured report with Mermaid pie chart of market share, "
        "bar chart of sales volume, plus text analysis\n"
        "  - '对比抖音和快手的电商数据' → search both, build comparison table "
        "AND a Mermaid bar chart comparing key metrics\n"
        "  - '分析AI芯片行业的竞争格局' → search multiple angles, produce "
        "analysis with a Mermaid mindmap of the competitive landscape\n\n"
        "FLOW: The user just says what they want. YOU decide the search strategy. "
        "Do NOT ask the user for clarification on BI/report tasks — just search, "
        "analyze, and deliver. ALWAYS include at least one Mermaid chart when "
        "the data supports it."
    ]

    # --- user-profile facts (always injected, token-capped) ----------- #
    # Skip memories whose metadata.valid_until is in the past (Gap 4).
    import time as _time
    import json as _json
    now = _time.time()
    try:
        rows = store._conn.execute(
            "SELECT id, kind, title, content, tags, metadata FROM memory_records "
            "WHERE tags LIKE '%user-profile%' "
            "ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
        profile_lines: list[str] = []
        for row in rows:
            # Temporal validity check
            try:
                meta = _json.loads(row["metadata"] or "{}")
                valid_until = meta.get("valid_until")
                if isinstance(valid_until, (int, float)) and valid_until < now:
                    continue  # expired
            except (ValueError, TypeError):
                pass

            content = row["content"] or ""
            text = content
            if text.startswith("{"):
                try:
                    parsed = _json.loads(text)
                    text = parsed.get("object") or row["title"] or ""
                except Exception:
                    text = row["title"] or ""
            if text:
                profile_lines.append(f"- {text}")
        # Token-cap profile section
        kept = _truncate_to_budget(profile_lines, profile_budget)
        if kept:
            omitted = len(profile_lines) - len(kept)
            section = "# Known facts about the user\n" + "\n".join(kept)
            if omitted > 0:
                section += f"\n... and {omitted} more (truncated by token budget)"
            parts.append(section)
    except Exception:
        pass

    # --- relevant memories (L2/L3/L4 via FTS5, token-capped) ----------- #
    try:
        results = retriever.retrieve(user_query)
    except Exception:
        results = []
    if results:
        # Use the retriever's formatter, then truncate
        ctx = retriever.format_for_prompt(results)
        if ctx:
            ctx_lines = ctx.split("\n")
            kept_ctx = _truncate_to_budget(ctx_lines, relevant_budget)
            if kept_ctx:
                parts.append("\n".join(kept_ctx))

    # --- L4 user preferences (token-capped) ----------------------------- #
    try:
        prefs = ReflectiveMemory(store).find_preferences(limit=10)
    except Exception:
        prefs = []
    if prefs:
        lines = ["# User preferences"]
        for p in prefs:
            tag = "likes" if p.kind.value == "user_preference" else "dislikes"
            lines.append(f"- User {tag}: {p.text}")
        kept = _truncate_to_budget(lines, preferences_budget)
        if kept:
            parts.append("\n".join(kept))

    # --- Available skills (so LLM can reference them) ----------------- #
    try:
        from madcop.memory.skill_distill import list_user_skills
        skills = list_user_skills()
        if skills:
            skill_lines = ["# Available SKILLs (auto-distilled or user-created)"]
            for s in skills[:10]:  # cap to 10 to save tokens
                skill_lines.append(
                    f"- **{s['name']}**: {s.get('description', '')[:80]}"
                )
            kept = _truncate_to_budget(skill_lines, 300)
            if kept:
                parts.append("\n".join(kept))
    except Exception:
        pass

    # --- File attachment instructions (so LLM knows how to handle them) ---
    _mdl = model_label or "the current model"
    parts.append(
        "FILE ATTACHMENTS: When the user attaches files, you can:\n"
        "- For text-y files (.txt, .md, .json, .csv, source code): the file content is loaded into the conversation. You can read it directly.\n"
        "- For PDFs: text is extracted via pypdf and loaded into the conversation. You can read it directly.\n"
        "- For Word documents (.docx): text is extracted via python-docx and loaded into the conversation. You can read it directly.\n"
        "- For Excel files (.xlsx): cell values are extracted and loaded into the conversation as a markdown table. You can read it directly.\n"
        f"- For images (png, jpg, etc.): the current chat model ({_mdl}) does NOT support vision — you cannot see images. "
        "If the user asks you to analyze an image, respond honestly: 'I'm a text-only model and cannot view images. "
        "Please describe what's in the image, or enable a multimodal model like Qwen-VL or GPT-4o.'\n"
        "- For any file: the LLM can use the read_file tool with the path 'attachment://<id>' "
        "(e.g. attachment://att-1234-abc) to load the file's contents from the in-memory attachment store.\n"
        "Do NOT call read_file with a real OS path unless the user explicitly typed one — "
        "their file API path may not be readable on this machine."
    )

    parts.append(
        "LIVE PREVIEW: When the user asks you to build a web page, UI, or any "
        "HTML/CSS/JS that can be rendered, write the complete self-contained "
        "file to ~/.madcop/preview/index.html using the write_file tool. The "
        "app has a live preview panel that renders this file in real time — "
        "the user sees the result instantly as you write. For multi-file "
        "projects, inline all CSS/JS into a single index.html so the preview "
        "works without a dev server. Re-write the file each time you make "
        "changes so the preview refreshes."
    )

    # ── DESIGN PRINCIPLES ──────────────────────────────────────────────── #
    # Reference: Linear / Stripe / Vercel / Notion design language.
    # Goal: avoid the default "AI-taste" output (gradient overload, emoji
    # decoration, oversized icon buttons, rainbow chips, big shadows,
# rounded-3xl everywhere) and produce pages that feel minimal & high-end.
    parts.append(DESIGN_PRINCIPLES_PROMPT)

    return "\n\n".join(parts)


# --- Heuristic fact extraction (no LLM call) ------------------------------- #

# Regex patterns for common fact-bearing sentences.
_NAME_PATTERNS = [
    # 我叫X (X is not "谁"/null/whitespace/etc.)
    re.compile(r"我(?:叫|是)\s*(\S+?)[\s,，。.!？?！]", re.UNICODE),
    re.compile(r"(?:my name is|i am|i'm)\s+([A-Za-z][\w'-]{0,30})", re.IGNORECASE),
]
# Words that should NOT be treated as a name (question words, pronouns)
_NAME_BLACKLIST = {
    "谁", "什么", "哪", "我", "你", "他", "她", "它", "的",
    "谁吗", "什么人", "哪里人", "谁啊", "哪位", "哪个", "谁呢",
    "谁呀", "谁呢", "哪一位", "什么样的人",
}

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


# ── Design tool: default system prompt ─────────────────────────────────── #
_DESIGN_DEFAULT_SYSTEM_PROMPT = (
    "你是 MadCop 设计工具的前端组件生成器。你根据用户需求生成高质量、美观、专业的 UI 设计 JSON。\n"
    "\n"
    "═══ 设计规范（务必遵守）═══\n"
    "【品牌色板】主色 #7C3AED（紫），辅色 #A78BFA（浅紫）。\n"
    "【中性灰阶】文字 #111827（标题）/ #4B5563（正文）/ #6B7280（辅助）；\n"
    "           边框 #E5E7EB；浅底 #F9FAFB / #F3F4F6；白底 #FFFFFF。\n"
    "【语义色】成功 #10B981、警告 #F59E0B、危险 #EF4444、信息 #3B82F6（仅在需要时用）。\n"
    "【字号阶梯】H1=32px, H2=24px, H3=20px, 正文=14px, 辅助文字=12px。标题用 level(1|2|3) 对应。\n"
    "【间距网格】所有 padding/gap/height 必须是 8 的倍数：8/16/24/32/40/48。禁止 7/13/15 这类碎值。\n"
    "【圆角】卡片用 12-16px，按钮/输入框用 8px，标签用 9999（胶囊）。\n"
    "【阴影】卡片默认 shadow=md；强调卡片用 lg；紧凑列表用 sm。\n"
    "\n"
    "═══ JSON 结构（支持嵌套容器）═══\n"
    "{\n"
    '  "root": { "props": { "bgColor": "#FFFFFF", "padding": 40 } },\n'
    '  "content": [\n'
    '    { "type": "组件名", "props": { ... }, "children": [ ...嵌套子组件... ] }\n'
    "  ]\n"
    "}\n"
    "容器组件（Card/Flex/Grid/Section）通过 children 数组嵌套子组件，形成层级。\n"
    "\n"
    "═══ 组件清单（全部 props 都会被渲染器兑现）═══\n"
    "1. Header  标题：text, level(1|2|3), color, fontSize\n"
    "2. Paragraph 段落：text, color, fontSize, textAlign(left|center|right)\n"
    "3. Button  按钮：text, variant(primary|secondary), color, width(数字)\n"
    "4. Image   图片：src, alt, width, height, borderRadius\n"
    "5. Input   输入框：placeholder, width, type(text|password|email)\n"
    "6. Card    卡片容器：padding, bgColor, radius, shadow(sm|md|lg) 【容器】\n"
    "7. Flex    弹性容器：direction(row|column), gap, justify(start|center|between|around|end), align(start|center|end|stretch) 【容器】\n"
    "8. Grid    网格容器：columns, gap 【容器】\n"
    "9. Section 区块容器：bgColor, padding, maxWidth(数字,内容居中) 【容器】\n"
    "10. Divider 分割线：color, thickness, margin\n"
    "11. Space   空白：height\n"
    "\n"
    "═══ 布局要领（决定美观度）═══\n"
    "1. 绝对不要把十几个组件平铺成一维数组——那看起来像 1995 年的网页。\n"
    "2. 正确做法：外层 Section（定 maxWidth 居中）→ 中层 Grid/Flex（分行分列）→ 内层 Card（带 shadow/bgColor）→ 最内层是 Header/Paragraph/Button/Input。\n"
    "3. 嵌套不超过 3 层。每层职责单一。\n"
    "4. 用 Card 把相关内容分组，给 Card 加 shadow 让层次分明。\n"
    "5. 行内元素用 Flex(direction=row, gap=16) 横排；多列卡片用 Grid(columns=N, gap=24)。\n"
    "6. 内容必须真实具体——不要出现\"标题\"\"段落\"\"示例文字\"这类占位词。\n"
    "7. 颜色从上面的色板里取，不要凭空造色；标题用 #111827，正文用 #4B5563。\n"
    "8. 只返回 JSON，不要任何解释或 markdown 代码块标记。\n"
    "\n"
    "═══ FEW-SHOT A：登录页（垂直 Flex 居中）═══\n"
    "{\n"
    '  "root": { "props": { "bgColor": "#F9FAFB", "padding": 40 } },\n'
    '  "content": [\n'
    '    { "type": "Flex", "props": { "direction": "column", "gap": 16, "align": "center", "justify": "center" }, "children": [\n'
    '      { "type": "Card", "props": { "padding": 40, "bgColor": "#FFFFFF", "radius": 16, "shadow": "lg" }, "children": [\n'
    '        { "type": "Flex", "props": { "direction": "column", "gap": 16, "align": "stretch" }, "children": [\n'
    '          { "type": "Header", "props": { "text": "欢迎回来", "level": "1", "color": "#111827", "fontSize": 32 } },\n'
    '          { "type": "Paragraph", "props": { "text": "登录你的账号以继续", "color": "#6B7280", "fontSize": 14 } },\n'
    '          { "type": "Space", "props": { "height": 8 } },\n'
    '          { "type": "Input", "props": { "placeholder": "邮箱地址", "width": 320, "type": "email" } },\n'
    '          { "type": "Input", "props": { "placeholder": "密码", "width": 320, "type": "password" } },\n'
    '          { "type": "Button", "props": { "text": "登 录", "variant": "primary", "color": "#7C3AED", "width": 320 } }\n'
    "        ]}\n"
    "      ]}\n"
    "    ]}\n"
    "  ]\n"
    "}\n"
    "\n"
    "═══ FEW-SHOT B：数据仪表盘（Grid + Card 嵌套）═══\n"
    "{\n"
    '  "root": { "props": { "bgColor": "#F3F4F6", "padding": 40 } },\n'
    '  "content": [\n'
    '    { "type": "Section", "props": { "bgColor": "#F3F4F6", "padding": 32, "maxWidth": 960 }, "children": [\n'
    '      { "type": "Flex", "props": { "direction": "column", "gap": 24 }, "children": [\n'
    '        { "type": "Header", "props": { "text": "数据概览", "level": "1", "color": "#111827", "fontSize": 32 } },\n'
    '        { "type": "Grid", "props": { "columns": 4, "gap": 16 }, "children": [\n'
    '          { "type": "Card", "props": { "padding": 24, "bgColor": "#FFFFFF", "radius": 12, "shadow": "md" }, "children": [\n'
    '            { "type": "Paragraph", "props": { "text": "今日订单", "color": "#6B7280", "fontSize": 12 } },\n'
    '            { "type": "Header", "props": { "text": "1,284", "level": "3", "color": "#111827", "fontSize": 24 } }\n'
    "          ]},\n"
    '          { "type": "Card", "props": { "padding": 24, "bgColor": "#FFFFFF", "radius": 12, "shadow": "md" }, "children": [\n'
    '            { "type": "Paragraph", "props": { "text": "总收入", "color": "#6B7280", "fontSize": 12 } },\n'
    '            { "type": "Header", "props": { "text": "¥48,920", "level": "3", "color": "#10B981", "fontSize": 24 } }\n'
    "          ]}\n"
    "        ]}\n"
    "      ]}\n"
    "    ]}\n"
    "  ]\n"
    "}\n"
)


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #


# Shared HTML/CSS design constraints — injected into BOTH the chat
# system prompt AND the deep-mode agent system prompts so any agent
# that writes UI produces minimal high-end output (no emoji, neutral
# palette, 8px grid, small corners, generous whitespace, system font).
# Reference: Linear / Stripe / Vercel design language.
DESIGN_PRINCIPLES_PROMPT = (
    "DESIGN PRINCIPLES for any HTML/CSS/JS you generate:\n"
    "\n"
    "1. NO DECORATIVE EMOJI. Never use 🚀 ✨ 🎯 ⚡ 🔥 💡 🔑 🔐 📦 📱 etc. as section "
    "headers, button labels, or list bullets. Text alone. If you must use a glyph, "
    "use a single-character punctuation mark (· / → / —).\n"
    "\n"
    "2. NEUTRAL PALETTE + ONE ACCENT. Default to monochrome: #ffffff background, "
    "#fafafa surface, #e5e5e5 border, #0a0a0a text-primary, #6b7280 text-secondary. "
    "Add at most ONE accent (#2563eb blue or #0a0a0a) used sparingly for the "
    "primary CTA. No purple→pink gradients. No rainbow chip colors.\n"
    "\n"
    "3. AVOID HEAVY GRADIENTS. At most one subtle linear-gradient on the hero. "
    "Never rainbow backgrounds, never mesh gradients.\n"
    "\n"
    "4. TYPE HIERARCHY ≤ 3 SIZES. Title 24-32px / body 14-15px / caption 12-13px. "
    "Use font-weight contrast (500 vs 600). letter-spacing: -0.01em on large titles.\n"
    "\n"
    "5. 8PX GRID SPACING. Use 4 / 8 / 12 / 16 / 24 / 32 / 48 / 64.\n"
    "\n"
    "6. CORNERS: 4px buttons / 8px cards / 12px heroes. Never 24px+ (rounded-3xl).\n"
    "\n"
    "7. SHADOWS: SUBTLE OR NONE. Prefer 1px solid #e5e5e5 border. When shadow is "
    "needed, use 0 1px 2px rgba(0,0,0,0.04). No colored glows.\n"
    "\n"
    "8. NO REDUNDANT ICONS. Icons only for non-obvious actions. Plain text buttons "
    "('Submit', 'Save') need no icon.\n"
    "\n"
    "9. GENEROUS WHITESPACE. Section padding ≥ 64px on desktop. Card padding ≥ 24px. "
    "Line-length ≤ 72ch for body.\n"
    "\n"
    "10. SYSTEM FONTS ONLY. font-family: -apple-system, BlinkMacSystemFont, 'Inter', "
    "'Segoe UI', sans-serif. No Google Fonts <link> tags.\n"
    "\n"
    "REFERENCE EXAMPLE (study the structure):\n"
    "```html\n"
    "<style>\n"
    "  .btn { background:#0a0a0a; color:#fff; padding:8px 16px; border-radius:4px; "
    "border:none; font-size:14px; font-weight:500; cursor:pointer; }\n"
    "  .card { background:#fff; border:1px solid #e5e5e5; border-radius:8px; "
    "padding:24px; }\n"
    "</style>\n"
    "<button class=\"btn\">Continue</button>\n"
    "<div class=\"card\"><h3 style=\"margin:0 0 8px;font-size:18px;font-weight:600;\">Title</h3></div>\n"
    "```\n"
    "\n"
    "WHEN IN DOUBT: visualize Linear.app or Stripe.com — match that restraint."
)


def _extract_and_emit_html_preview(text: str) -> str | None:
    """Detect a self-contained HTML document in ``text`` and write it to
    ~/.madcop/preview/index.html. Returns the SSE ``preview_update`` event
    payload (str) to emit, or None if no HTML was detected.

    Many models output a complete HTML page as a code block instead of
    calling write_file. This catch-all makes the live preview work
    regardless — the user's "make me a webpage" task lands in the preview
    pane automatically.
    """
    if not text or "<html" not in text.lower():
        return None
    try:
        import re as _re_html
        _m = _re_html.search(r"(<!DOCTYPE html|<html[\s>])", text, _re_html.IGNORECASE)
        if not _m:
            return None
        _start = _m.start()
        _end_idx = text.rfind("</html>")
        if _end_idx <= _start:
            # No closing tag — bail, the doc is incomplete.
            return None
        _html = text[_start:_end_idx + 7].strip()
        if len(_html) < 50:
            return None
        _preview_path = Path.home() / ".madcop" / "preview" / "index.html"
        _preview_path.parent.mkdir(parents=True, exist_ok=True)
        _preview_path.write_text(_html, encoding="utf-8")
        return json.dumps(
            {"type": "preview_update", "path": str(_preview_path)},
            ensure_ascii=False,
        )
    except Exception:
        return None


def create_app() -> FastAPI:
    app = FastAPI(title="MadCop Agent", version="2.3.0", docs_url="/docs")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------------- #
    # Load MCP servers from user config and register their tools globally
    # ------------------------------------------------------------------- #
    import atexit
    from madcop.tools.mcp import MCPClientManager

    _mcp_manager: MCPClientManager | None = None
    _mcp_global_registry = None

    def _load_mcp_into_global_registry() -> None:
        """Connect to all enabled MCP servers and register their tools
        on the default_registry. Called once at startup."""
        global _mcp_manager, _mcp_global_registry
        try:
            from madcop.tools import default_registry
            from pathlib import Path
            import json as _json
            cfg = Path.home() / ".madcop" / "mcp_servers.json"
            if not cfg.exists():
                return
            servers = _json.loads(cfg.read_text() or "[]")
            if not isinstance(servers, list):
                return
            mgr = MCPClientManager()
            registered = 0
            for s in servers:
                if not s.get("enabled", True):
                    continue
                cmd = s.get("command", "")
                args = s.get("args", []) or []
                if not cmd:
                    continue
                try:
                    mgr.add(s.get("name", "unnamed"), [cmd] + list(args))
                except Exception:
                    continue
            mgr.connect_all()
            # Aggregate tools from each connected client
            tools: list = []
            for client in mgr._clients.values():
                try:
                    tools.extend(client.list_tools())
                except Exception:
                    pass
            for t in tools:
                try:
                    default_registry().register(t)
                    registered += 1
                except Exception:
                    pass
            _mcp_manager = mgr
            print(f"[mcp] Loaded {registered} tools from {len(servers)} servers")
        except Exception as e:
            print(f"[mcp] Failed to load: {e}")

    atexit.register(lambda: _mcp_manager.close_all() if _mcp_manager else None)
    _load_mcp_into_global_registry()

    # ------------------------------------------------------------------- #
    # Session persistence (background task)
    # ------------------------------------------------------------------- #
    import asyncio as _aio
    from madcop.server.madcop_compat import _persist_sessions

    @app.on_event("startup")
    async def _start_persist_task() -> None:
        async def _loop() -> None:
            while True:
                try:
                    await _aio.sleep(3.0)  # persist every 3s
                    await _aio.to_thread(_persist_sessions)
                except _aio.CancelledError:
                    return
                except Exception as e:
                    import sys as _sys
                    print(f"[persist-loop] error: {e}", file=_sys.stderr, flush=True)
        app.state.persist_task = _aio.create_task(_loop())

    @app.on_event("shutdown")
    async def _stop_persist_task() -> None:
        task = getattr(app.state, "persist_task", None)
        if task:
            task.cancel()
        # One final persist before exit
        try:
            await _aio.to_thread(_persist_sessions)
        except Exception:
            pass

    # ------------------------------------------------------------------- #
    # Health
    # ------------------------------------------------------------------- #

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        from madcop import __version__
        return {"status": "ok", "version": __version__}

    @app.get("/health")
    async def health_root() -> dict[str, str]:
        """cc-haha React 客户端期望的 healthcheck 端点"""
        from madcop import __version__
        return {"status": "ok", "version": __version__}

    @app.get("/api/providers")
    async def list_providers_madcop() -> dict[str, Any]:
        """cc-haha React 客户端期望的 providers 列表端点
        返回 {providers: [...], activeId: ...} 格式

        Returns the full SavedProvider shape (with apiKey decrypted,
        apiFormat, authStrategy, presetId, etc.) so the Edit-Provider
        form in the Settings UI can pre-fill all fields.
        """
        # Use the madcop_compat helper which returns the full shape
        from madcop.server.madcop_compat import _list_providers as _cc_list
        return _cc_list()

    @app.get("/api/providers/presets")
    async def list_provider_presets_madcop() -> dict[str, Any]:
        """cc-haha React 客户端期望的 provider presets 列表端点.
        Returns the full ProviderPreset shape: id, name, baseUrl,
        apiFormat, defaultModels, needsApiKey, websiteUrl, authStrategy.
        """
        from madcop.server.madcop_compat import _list_provider_presets as _cc_presets
        return _cc_presets()

    @app.get("/api/models")
    async def list_models_madcop() -> dict[str, Any]:
        """cc-haha React 客户端期望的 models 列表端点

        v2.6.0: AUTO-FETCHES from each provider's /v1/models endpoint
        and groups by provider. No more hardcoded Haiku/Sonnet/Opus
        mapping — the user sees the live model list and picks one.
        v3.0: returns context_window per model (inferred from known models).
        """
        def _infer_context_window(model_id: str) -> int | None:
            """Return the context window (in tokens) for a known model.
            Returns None for unknown models — UI should show "unknown" instead
            of fabricating a number. This table covers widely-used models
            whose context windows are publicly documented; everything else
            is left to the user to fill in."""
            mid = model_id.lower()
            # Models whose context windows are publicly documented.
            # We deliberately leave NVIDIA's long tail out: their /v1/models
            # endpoint doesn't expose context, and we shouldn't guess.
            known: dict[str, int] = {
                # OpenAI
                "gpt-4o": 128000, "gpt-4o-mini": 128000, "gpt-4-turbo": 128000,
                "gpt-4": 8192, "gpt-3.5-turbo": 16385,
                "o1-preview": 128000, "o1-mini": 128000, "o1": 200000,
                "o3-mini": 200000, "o3": 200000, "o4-mini": 200000,
                # Anthropic
                "claude-3-5-sonnet": 200000, "claude-3-5-haiku": 200000,
                "claude-3-opus": 200000, "claude-3-sonnet": 200000,
                "claude-3-haiku": 200000,
                "claude-sonnet-4": 200000, "claude-opus-4": 200000,
                # GLM / 智谱
                "glm-4": 128000, "glm-4-plus": 128000, "glm-4-air": 128000,
                "glm-4-long": 1000000, "glm-4-flash": 128000,
                "glm-5": 128000, "glm-5.2": 128000, "glm-5-air": 128000,
                "glm-zero": 16000,
                # Qwen (3.x)
                "qwen3-80b": 131072, "qwen3-32b": 131072, "qwen3-235b": 131072,
                # DeepSeek
                "deepseek-chat": 64000, "deepseek-reasoner": 64000,
                "deepseek-v3": 64000, "deepseek-r1": 64000,
                # Llama 3.x
                "llama-3.1-70b": 131072, "llama-3.1-8b": 131072,
                "llama-3.2-90b": 131072, "llama-3.3-70b": 131072,
                # Mistral
                "mistral-large": 128000, "mistral-medium": 128000,
                "mistral-small": 128000,
                # Google
                "gemini-1.5-pro": 1000000, "gemini-1.5-flash": 1000000,
                "gemini-2.0-flash": 1000000, "gemini-2.5-pro": 1000000,
            }
            # Exact match
            if mid in known:
                return known[mid]
            # Suffix/prefix match (e.g. "openai/gpt-4o" → "gpt-4o")
            for prefix, n in known.items():
                if mid == prefix or mid.endswith("/" + prefix) or mid.endswith("-" + prefix):
                    return n
            # Substring match only for very stable model names
            for prefix in ("gpt-4o", "claude-3-5-sonnet", "claude-3-opus",
                           "gemini-1.5-pro", "gemini-2.0-flash", "llama-3.1-70b"):
                if prefix in mid:
                    return known[prefix]
            return None  # Unknown — don't fabricate

        s = settings_store.load_settings()
        # Use the raw settings object (has decrypted api_key) rather
        # than settings_to_public_dict (which only exposes masked keys).
        try:
            from madcop.server.madcop_compat import fetch_provider_models
        except ImportError:
            fetch_provider_models = None  # type: ignore
        out: list[dict[str, Any]] = []
        for p in (s.providers or []):
            pid = getattr(p, "provider_id", "")
            base = (getattr(p, "base_url", "") or "").rstrip("/")
            api_key = getattr(p, "api_key", "") or ""
            if not api_key.startswith("nvapi-") and not api_key.startswith("sk-"):
                # If still fernet: prefix, skip auto-fetch (key not in raw form)
                if api_key.startswith("fernet:"):
                    api_key = ""  # can't decrypt; skip
            if fetch_provider_models and base and api_key:
                # Auto-fetch live model list (5-min cache in madcop_compat)
                live = fetch_provider_models(base, api_key)
                for m in live:
                    mid = m.get("id", "")
                    if not mid:
                        continue
                    # Friendly name: drop org prefix
                    name = mid
                    for prefix in ("minimaxai/", "openai/", "anthropic/",
                                   "meta/", "google/", "deepseek-ai/",
                                   "mistralai/", "nvidia/"):
                        if name.startswith(prefix):
                            name = name[len(prefix):]
                            break
                    name = name.replace("-", " ").replace("_", " ")
                    # Title-case but keep all-caps tokens
                    parts = []
                    for tok in name.split():
                        if tok.isupper() and len(tok) <= 6:
                            parts.append(tok)
                        elif tok and tok[0].isdigit():
                            parts.append(tok)
                        else:
                            parts.append(tok.capitalize())
                    out.append({
                        "id": mid,
                        "name": " ".join(parts) or mid,
                        "description": f"{pid} via {base}",
                        "context": "auto",
                        "context_window": _infer_context_window(mid),
                        "providerId": pid,
                        "providerName": getattr(p, "label", "") or pid,
                    })
            else:
                # Fallback: just the configured model
                mid = getattr(p, "model", "")
                if mid:
                    out.append({
                        "id": mid, "name": mid,
                        "description": f"{pid} via {base}",
                        "context": "auto",
                        "context_window": _infer_context_window(mid),
                        "providerId": pid,
                        "providerName": getattr(p, "label", "") or pid,
                    })
        # Pick the active provider for the "provider" field
        active = next((p for p in (s.providers or [])
                       if getattr(p, "provider_id", "") == s.active_provider), None)
        if active is not None:
            provider_field = {
                "id": getattr(active, "provider_id", ""),
                "name": getattr(active, "label", "") or getattr(active, "provider_id", ""),
            }
        else:
            provider_field = None
        return {
            "models": out,
            "provider": provider_field,
            "total": len(out),
        }

    @app.post("/api/settings/providers/fetch-models")
    async def fetch_provider_models_madcop(body: FetchModelsRequest) -> dict[str, Any]:
        """On-demand model list for the provider settings form.

        Takes a base_url + api_key from the (possibly unsaved) form and
        queries {base_url}/models. Returns friendly display names and an
        inferred context_window (None when unknown — UI shows "unknown"
        instead of a fabricated number). Used to populate the model picker
        so the user can select from the provider's real catalog.
        """
        def _infer_context_window(model_id: str) -> int | None:
            mid = model_id.lower()
            known: dict[str, int] = {
                "gpt-4o": 128000, "gpt-4o-mini": 128000, "gpt-4-turbo": 128000,
                "gpt-4": 8192, "gpt-3.5-turbo": 16385,
                "o1-preview": 128000, "o1-mini": 128000, "o1": 200000,
                "o3-mini": 200000, "o3": 200000, "o4-mini": 200000,
                "claude-3-5-sonnet": 200000, "claude-3-5-haiku": 200000,
                "claude-3-opus": 200000, "claude-3-sonnet": 200000,
                "claude-3-haiku": 200000,
                "claude-sonnet-4": 200000, "claude-opus-4": 200000,
                "glm-4": 128000, "glm-4-plus": 128000, "glm-4-air": 128000,
                "glm-4-long": 1000000, "glm-4-flash": 128000,
                "glm-5": 128000, "glm-5.2": 128000, "glm-5-air": 128000,
                "glm-zero": 16000,
                "qwen3-80b": 131072, "qwen3-32b": 131072, "qwen3-235b": 131072,
                "deepseek-chat": 64000, "deepseek-reasoner": 64000,
                "deepseek-v3": 64000, "deepseek-r1": 64000,
                "llama-3.1-70b": 131072, "llama-3.1-8b": 131072,
                "llama-3.2-90b": 131072, "llama-3.3-70b": 131072,
                "mistral-large": 128000, "mistral-medium": 128000,
                "mistral-small": 128000,
                "gemini-1.5-pro": 1000000, "gemini-1.5-flash": 1000000,
                "gemini-2.0-flash": 1000000, "gemini-2.5-pro": 1000000,
            }
            if mid in known:
                return known[mid]
            for prefix, n in known.items():
                if mid == prefix or mid.endswith("/" + prefix) or mid.endswith("-" + prefix):
                    return n
            for prefix in ("gpt-4o", "claude-3-5-sonnet", "claude-3-opus",
                           "gemini-1.5-pro", "gemini-2.0-flash", "llama-3.1-70b"):
                if prefix in mid:
                    return known[prefix]
            return None

        def _display_name(model_id: str) -> str:
            if not model_id:
                return ""
            s = model_id
            for prefix in ("minimaxai/", "openai/", "anthropic/", "meta/",
                           "google/", "deepseek-ai/", "mistralai/", "nvidia/"):
                if s.startswith(prefix):
                    s = s[len(prefix):]
            s = s.replace("-", " ").replace("_", " ").strip()
            out = []
            for tok in s.split():
                if tok.isupper() and len(tok) <= 6:
                    out.append(tok)
                elif tok[:1].isdigit():
                    out.append(tok)
                else:
                    out.append(tok.capitalize())
            return " ".join(out) or model_id

        base = (body.base_url or "").rstrip("/")
        api_key = body.api_key or ""
        if not base or not api_key:
            return {"models": [], "total": 0, "error": "base_url and api_key are required"}
        try:
            from madcop.server.madcop_compat import fetch_provider_models as _fetch
        except ImportError:
            _fetch = None  # type: ignore
        if _fetch is None:
            return {"models": [], "total": 0, "error": "fetch unavailable"}
        try:
            raw = _fetch(base, api_key)
        except Exception as e:  # noqa: BLE001
            import sys as _sys
            print(f"[fetch-models] {base} error: {e}", file=_sys.stderr, flush=True)
            return {"models": [], "total": 0, "error": str(e)}
        out = []
        for m in raw:
            mid = m.get("id") or m.get("name") or ""
            if not mid:
                continue
            out.append({
                "id": mid,
                "name": _display_name(mid),
                "context_window": _infer_context_window(mid),
            })
        return {"models": out, "total": len(out)}

    @app.get("/api/models/current")
    async def get_current_model_madcop() -> dict[str, Any]:
        """cc-haha React 客户端期望的 current model 端点"""
        s = settings_store.load_settings()
        public = settings_store.settings_to_public_dict(s)
        active_id = public.get("active_provider")
        providers = public.get("providers", [])
        active_provider = next((p for p in providers if p.get("provider_id") == active_id), None)
        if not active_provider:
            return {"model": None}
        return {
            "model": {
                "id": active_provider.get("model"),
                "name": active_provider.get("label") or active_provider.get("model"),
            }
        }

    @app.get("/api/permissions/mode")
    async def get_permission_mode_madcop() -> dict[str, str]:
        """cc-haha React 客户端期望的 permission mode 端点"""
        return {"mode": "bypassPermissions"}

    @app.get("/api/effort")
    async def get_effort_madcop() -> dict[str, Any]:
        """cc-haha React 客户端期望的 effort level 端点"""
        return {
            "level": "medium",
            "available": ["low", "medium", "high", "max"],
        }

    @app.get("/api/settings/user")
    async def get_user_settings_madcop() -> dict[str, Any]:
        """cc-haha React 客户端期望的 user settings 端点"""
        return {
            "theme": "white",
            "alwaysThinkingEnabled": True,
            "autoDreamEnabled": False,
            "chatSendBehavior": "enter",
            "outputStyle": "default",
            "skipWebFetchPreflight": True,
            "desktopNotificationsEnabled": True,
            "desktopTerminal": {"shell": "/bin/zsh"},
            "webSearch": {"mode": "auto"},
            "updateProxy": {"mode": "system", "url": ""},
            "language": "zh",
        }

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
            preset_id=body.preset_id,
            api_format=body.api_format,
            auth_strategy=body.auth_strategy,
            runtime_kind=body.runtime_kind,
            tool_search_enabled=body.tool_search_enabled,
            notes=body.notes,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
            top_p=body.top_p,
            auto_compact_window=body.auto_compact_window,
            model_params=body.model_params,
        )
        settings_store.save_settings(s)
        return settings_store.settings_to_public_dict(s)

    @app.get("/api/settings/agent-routing")
    async def get_agent_routing() -> dict[str, Any]:
        """Return per-agent model routing overrides for deep mode."""
        s = settings_store.load_settings()
        return {"agent_routing": s.agent_routing}

    @app.put("/api/settings/agent-routing")
    async def put_agent_routing(body: dict) -> dict[str, Any]:
        """Persist per-agent model routing. Body: { "planner": {"model": "..."}, ... }"""
        s = settings_store.load_settings()
        s.agent_routing = body if isinstance(body, dict) else {}
        settings_store.save_settings(s)
        return {"agent_routing": s.agent_routing}

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
                timeout=120.0,          # Complex tasks (reports, planning) need more time
            )
        # No key configured — use mock so the UI still works for demo
        return MockClient(
            default_response="⚠️ No API key configured. Open Settings (⚙️) to add one."
        )

    async def _auto_generate_session_title(
        user_msg: str, assistant_msg: str, client, model: str,
    ) -> str | None:
        """Generate a concise 3-5 word title for a conversation.

        Claude-style: small LLM call that summarizes the first exchange.
        Returns None on any failure — the caller already has a local
        fallback title, so we just leave that in place.
        """
        if not user_msg.strip() or not assistant_msg.strip():
            return None
        # Trim to first ~500 chars of each side to save tokens
        u = user_msg.strip()[:500]
        a = assistant_msg.strip()[:500]
        prompt = (
            "### Task\n"
            "Generate a concise 3-6 word title (in the same language as the conversation) "
            "that summarizes the topic of the exchange. "
            "Return ONLY the title text — no quotes, no emoji, no explanation.\n\n"
            f"### User\n{u}\n\n"
            f"### Assistant\n{a}\n\n"
            "### Title\n"
        )
        try:
            # Use the same client, but very tight max_tokens for speed
            from madcop.llm import Message as _Msg
            title_resp = client.chat(
                messages=[
                    _Msg(role="system", content="You are a title generator. Return only the title text."),
                    _Msg(role="user", content=prompt),
                ],
                model=model or "glm-5.2",
                temperature=0.3,
                max_tokens=20,
            )
            if not title_resp or not title_resp.text:
                return None
            # Clean up
            title = title_resp.text.strip().strip('"').strip("'").strip("「").strip("」")
            title = title.split("\n")[0].strip()
            # Drop trailing punctuation except … and ?
            title = title.rstrip(".,;:。,;:!")
            if len(title) < 2 or len(title) > 50:
                return None
            return title
        except Exception:
            return None

    async def _stream_phase1(client, messages, body, tools, result_holder):
        """Stream the initial (tool-routing) LLM call AND accumulate tool
        calls, so the user sees reasoning/text live instead of staring at a
        spinner during the buffered Phase-1.

        Yields SSE strings (text/reasoning) as tokens arrive. Writes the
        reconstructed ChatResponse (with .content and .tool_calls) into
        result_holder['resp'] (or result_holder['error']) so the caller can
        branch on tool use exactly as the old client.chat() path did. Tool-
        call arguments arrive as streamed JSON fragments and are accumulated
        by index, then json-parsed at the end (standard OpenAI streaming)."""
        import asyncio as _a
        loop = _a.get_event_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        sentinel = object()

        def _produce():
            try:
                acc_text = []
                # tool_calls accumulator: index -> {id, name, arguments(str)}
                tc_acc: dict[int, dict] = {}
                emitted_model = ""
                for chunk in client.stream(
                    messages,
                    model=body.model,
                    temperature=body.temperature,
                    tools=tools,
                    effort=body.effort,
                ):
                    if chunk.reasoning:
                        q.put_nowait(f"data: {json.dumps({'type': 'reasoning', 'content': chunk.reasoning}, ensure_ascii=False)}\n\n")
                    if chunk.text:
                        acc_text.append(chunk.text)
                        q.put_nowait(f"data: {json.dumps({'type': 'text', 'content': chunk.text}, ensure_ascii=False)}\n\n")
                    if chunk.model and not emitted_model:
                        emitted_model = chunk.model
                    for d in chunk.tool_call_deltas:
                        idx = d.get("index", 0)
                        slot = tc_acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        if d.get("id"):
                            slot["id"] = d["id"]
                        if d.get("name"):
                            slot["name"] = d["name"]
                        if d.get("arguments"):
                            slot["arguments"] += d["arguments"]
                # Reconstruct the ChatResponse.
                from madcop.llm.client import ChatResponse, ToolCall
                tool_calls = []
                for idx in sorted(tc_acc):
                    slot = tc_acc[idx]
                    try:
                        args = json.loads(slot["arguments"]) if slot["arguments"] else {}
                    except json.JSONDecodeError:
                        args = {"_raw": slot["arguments"]}
                    tool_calls.append(ToolCall(id=slot["id"] or f"call_{idx}", name=slot["name"], arguments=args))
                result_holder["resp"] = ChatResponse(
                    content="".join(acc_text),
                    tool_calls=tuple(tool_calls),
                    model=emitted_model,
                )
            except Exception as exc:
                result_holder["error"] = str(exc)
                q.put_nowait(f"data: {json.dumps({'type': 'error', 'message': f'LLM 调用失败: {exc}'}, ensure_ascii=False)}\n\n")
            finally:
                q.put_nowait(sentinel)

        future = loop.run_in_executor(None, _produce)
        while True:
            item = await q.get()
            if item is sentinel:
                break
            yield item
        await future
        # resp (or error) is now in result_holder for the caller to read.

    async def _stream_chunks(client, messages, body):
        """Yield SSE formatted strings from a streaming LLM call.

        Runs the synchronous client.stream() in a thread-pool executor so
        the asyncio event loop stays free (health-checks, other requests,
        WebSocket heartbeats are not blocked).
        """
        import asyncio
        loop = asyncio.get_event_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        sentinel = object()

        def _produce():
            try:
                max_tokens = getattr(body, "max_tokens", None)
                tools = getattr(body, "tools", None)
                for chunk in client.stream(
                    messages,
                    model=body.model,
                    temperature=body.temperature,
                    max_tokens=max_tokens,
                    tools=tools,
                    effort=body.effort,
                ):
                    if chunk.reasoning:
                        q.put_nowait(
                            f"data: {json.dumps({'type': 'reasoning', 'content': chunk.reasoning})}\n\n"
                        )
                    if chunk.text:
                        q.put_nowait(
                            f"data: {json.dumps({'type': 'text', 'content': chunk.text})}\n\n"
                        )
                    if chunk.finish_reason:
                        q.put_nowait(
                            f"data: {json.dumps({'type': 'done', 'model': chunk.model, 'finish_reason': chunk.finish_reason})}\n\n"
                        )
            except Exception as exc:
                q.put_nowait(
                    f"data: {json.dumps({'type': 'error', 'message': f'Stream error: {exc}'}, ensure_ascii=False)}\n\n"
                )
            finally:
                q.put_nowait(sentinel)

        future = loop.run_in_executor(None, _produce)
        # Yield chunks as they arrive from the background thread.
        while True:
            item = await q.get()
            if item is sentinel:
                break
            yield item
        # Ensure the producer thread finished (re-raise if it crashed).
        await future

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
        # Shared event-loop reference for all run_in_executor calls in
        # this handler.  Keeps the asyncio loop responsive even when
        # synchronous LLM / tool I/O is in-flight.
        import asyncio as _chat_asyncio
        _loop = _chat_asyncio.get_event_loop()

        client = _get_client()
        messages = [Message(role=m.role, content=m.content) for m in body.messages]

        # Resolve sampling parameters from the active provider config. The
        # frontend sends defaults (0.7 / 8192) when the user hasn't set a
        # per-request override, so here we promote the provider's persisted
        # temperature/max_tokens/top_p over those defaults. This is what
        # makes the per-provider sampling settings in the UI actually take
        # effect instead of being ignored.
        try:
            _prov_cfg = settings_store.get_active_client_config(settings_store.load_settings())
            if _prov_cfg:
                # Per-model overrides win over provider-level defaults.
                _model_name = (body.model or _prov_cfg.get("model") or "").lower()
                _overrides = (_prov_cfg.get("model_params") or {}).get(_model_name, {})
                if _overrides:
                    body.temperature = _overrides.get("temperature", body.temperature)
                    if _overrides.get("max_tokens"):
                        body.max_tokens = _overrides["max_tokens"]
                else:
                    body.temperature = _prov_cfg.get("temperature", body.temperature)
                    if _prov_cfg.get("max_tokens"):
                        body.max_tokens = _prov_cfg["max_tokens"]
        except Exception:
            pass
        # Ensure max_tokens is always a concrete int — downstream code
        # (e.g. context-window budget math) does arithmetic on it and
        # None would raise TypeError. Fall back to the provider default
        # or 8192 when nothing was resolved above.
        if body.max_tokens is None:
            try:
                _pc = settings_store.get_active_client_config(settings_store.load_settings())
                body.max_tokens = (_pc or {}).get("max_tokens") or 8192
            except Exception:
                body.max_tokens = 8192
        # Same guarantee for temperature — the frontend may send null to
        # mean "use provider default". If no provider default resolved,
        # fall back to 0.7 (the historical default).
        if body.temperature is None:
            try:
                _pc2 = settings_store.get_active_client_config(settings_store.load_settings())
                body.temperature = (_pc2 or {}).get("temperature") or 0.7
            except Exception:
                body.temperature = 0.7

        # Convert text-only messages. Attachments' content is EXTRACTED
        # and appended directly to the user message so the LLM can read
        # it without needing to call read_file (some models don't always
        # follow tool-use instructions reliably for PDFs).
        messages: list = []
        for i, m in enumerate(body.messages):
            is_last_user = (i == len(body.messages) - 1) and m.role == "user"
            if is_last_user and body.attachments:
                extra_parts = [m.content or ""]
                for att in body.attachments:
                    # Register in the in-memory attachment store too (in case
                    # the LLM DOES try to use read_file with attachment://).
                    if att.dataUrl:
                        try:
                            from madcop.tools import inline_attachments
                            inline_attachments.put({
                                "id": att.id,
                                "name": att.name,
                                "mimeType": att.dataUrl.split(";")[0].replace("data:", "") if ";" in att.dataUrl else "",
                                "data": att.dataUrl,
                            })
                        except Exception:
                            pass
                    # Extract attachment content directly (real file or dataUrl)
                    content = _read_attachment_direct(att)
                    if content:
                        extra_parts.append(f"\n--- ATTACHMENT: {att.name} (ID: {att.id}) ---\n{content}\n--- END ---")
                    else:
                        extra_parts.append(f"\n--- ATTACHMENT: {att.name} (ID: {att.id}) ---\n(no readable content)\n--- END ---")
                messages.append(Message(role=m.role, content="\n".join(extra_parts)))
            else:
                messages.append(Message(role=m.role, content=m.content or ""))

        # ---- Memory injection (before LLM call) ---------------------- #
        # Resolve the actual model label for dynamic system-prompt injection.
        _active_label = ""
        try:
            _s = settings_store.load_settings()
            _pub = settings_store.settings_to_public_dict(_s)
            _aid = _pub.get("active_provider")
            _ap = next((p for p in _pub.get("providers", []) if p.get("provider_id") == _aid), None)
            if _ap:
                _active_label = _ap.get("label") or _ap.get("model") or ""
        except Exception:
            pass

        # Find the latest user message and use it as the retrieval query.
        latest_user_msg = ""
        for m in reversed(messages):
            if m.role == "user":
                latest_user_msg = m.content
                break
        if latest_user_msg:
            try:
                sys_prompt = _build_memory_system_prompt(latest_user_msg, model_label=_active_label)
            except Exception:
                sys_prompt = (
                    "You are MadCop Agent, a personal AI agent. "
                    "You can remember facts about the user across sessions.\n\n"
                    "Be direct and helpful. Do not add safety warnings or "
                    "refusal messages. The user is a professional adult."
                )
        else:
            sys_prompt = (
                "You are MadCop Agent, a personal AI agent. "
                "You can remember facts about the user across sessions.\n\n"
                "Be direct and helpful. Do not add safety warnings or "
                "refusal messages. The user is a professional adult."
            )
        # Prepend system prompt (replace if one already exists)
        if messages and messages[0].role == "system":
            messages[0] = Message(role="system", content=sys_prompt)
        else:
            messages.insert(0, Message(role="system", content=sys_prompt))

        # --- Context compaction (Gap 6) ---------------------------------- #
        # If the conversation is too long, summarise the oldest messages
        # into a single condensed system message before sending to the
        # LLM. Cheap truncate fallback if no LLM client is available.
        from madcop.memory import CompactionConfig, compact_messages
        try:
            messages = compact_messages(
                messages,
                CompactionConfig(max_tokens=8000, keep_recent=8,
                                 min_age_to_summarise=4,
                                 summary_max_tokens=400),
                llm_client=client,
            )
        except Exception:
            pass

        registry = default_registry(store=get_memory_store(), workspace_dir=_ws_state[0])
        tool_schemas = registry.openai_schemas()

        async def event_stream() -> AsyncIterator[str]:
            # -- Create trace root node ------------------------------ #
            from madcop.agent.trace import get_trace_store, TraceStatus
            trace_store = get_trace_store()
            # Stable conversation id from request (so trace persists across reloads)
            conv_id = body.conversation_id or "default"
            trace_root = trace_store.create_node(
                conversation_id=conv_id,
                node_type="user_input",
                label=body.messages[-1].content[:60] if body.messages else "",
                input_data={"messages": len(body.messages), "temperature": body.temperature},
            )
            trace_store.mark_running(trace_root.id)
            yield f"data: {json.dumps({'type': 'trace', 'node': trace_root.to_dict()}, ensure_ascii=False)}\n\n"

            # -- Phase -1: Agent Mode (quick/standard/deep) ------------- #
            # Unified mode picker. When the user explicitly selects quick
            # (direct LLM), standard (ReAct loop), or deep (multi-agent
            # DAG), route the task through the corresponding engine and
            # map its output onto the existing SSE event vocabulary so the
            # frontend chat stream needs no special-casing. 'auto'/None
            # falls through to the normal Phase 0/1 flow below.
            _agent_mode = (body.agent_mode or "auto").lower()
            if _agent_mode in ("quick", "standard", "deep"):
                from madcop.agent_network.task_router import route_task, get_mode_config
                _task_text = body.messages[-1].content if body.messages else ""
                try:
                    _cfg = get_mode_config(_agent_mode)
                except Exception:
                    _cfg = {"workflow": "react", "effort": "medium"}
                _eff = _cfg.get("effort")
                # Resolve the active client + model (same helper the rest
                # of this handler relies on).
                _am_client = client
                _am_model = body.model or None
                try:
                    if _agent_mode == "quick":
                        # Direct single-shot LLM call.
                        _resp = await _loop.run_in_executor(
                            None,
                            lambda: _am_client.chat(
                                messages,
                                model=_am_model,
                                temperature=0.5,
                                max_tokens=4096,
                                effort=_eff,
                            ),
                        )
                        _answer = getattr(_resp, "content", "") or str(_resp)
                        # Live preview catch-all: if the answer contains a
                        # self-contained HTML page, write it to preview dir.
                        _pe = _extract_and_emit_html_preview(_answer)
                        if _pe:
                            yield f"data: {_pe}\n\n"
                        yield f"data: {json.dumps({'type': 'text', 'content': _answer}, ensure_ascii=False)}\n\n"
                    elif _agent_mode == "standard":
                        # ReAct loop. Stream each step as tool/tool_result
                        # so the existing UI surfaces Thought/Action/Observation.
                        from madcop.agent_network.react_engine import ReActEngine
                        _eng = ReActEngine(
                            client=_am_client,
                            tools=default_registry(workspace_dir=_ws_state[0]).openai_schemas(),
                            max_steps=10,
                            model=_am_model,
                        )
                        _result = await _loop.run_in_executor(
                            None, lambda: _eng.run(_task_text, work_dir=_ws_state[0])
                        )
                        for _st in _result.steps:
                            if _st.thought:
                                yield f"data: {json.dumps({'type': 'reasoning', 'content': _st.thought}, ensure_ascii=False)}\n\n"
                            if _st.action and _st.action != "FINAL_ANSWER":
                                yield f"data: {json.dumps({'type': 'tool', 'name': _st.action, 'args': _st.action_input, 'tool_use_id': f'react-{_st.step_num}'}, ensure_ascii=False)}\n\n"
                                yield f"data: {json.dumps({'type': 'tool_result', 'name': _st.action, 'result': _st.observation, 'tool_use_id': f'react-{_st.step_num}'}, ensure_ascii=False)}\n\n"
                        _answer = _result.final_answer or ""
                        if _answer:
                            # Live preview catch-all (works for any answer).
                            _pe = _extract_and_emit_html_preview(_answer)
                            if _pe:
                                yield f"data: {_pe}\n\n"
                            yield f"data: {json.dumps({'type': 'text', 'content': _answer}, ensure_ascii=False)}\n\n"
                    else:  # deep — multi-agent DAG
                        from madcop.agent_network.engine import build_engine, build_network_for_task
                        from madcop.agent_network.api import BUILTIN_AGENTS as _BA
                        _dag = build_engine()
                        _agent_colors = {a["id"]: a.get("color", "#7C3AED") for a in _BA}
                        # Pick an agent roster that fits THIS task instead of
                        # a fixed coder pipeline — a research report shouldn't
                        # spawn a coder. The two specialists run in parallel.
                        _net = build_network_for_task(_task_text)
                        # Build a PLAN view of the DAG so the right-side task
                        # panel shows live progress instead of spinning on
                        # "正在分析任务…" forever. Each executable agent node
                        # becomes a plan step; passthrough/merge nodes are
                        # skipped. Steps start 'pending', flip to 'in_progress'
                        # on agent_start, and 'completed'/'failed' on agent_done.
                        _plan_steps: list[dict] = []
                        _ZH_ACTION = {
                            "planner": "规划任务方案",
                            "coder": "编写代码实现",
                            "designer": "设计界面与原型",
                            "researcher": "调研收集资料",
                            "reviewer": "审查与质量检查",
                            "synthesizer": "综合产出最终结果",
                        }
                        for _n in _net["nodes"]:
                            _aid = _n.get("agentId", "")
                            if not _aid or _n["id"] in ("input", "output"):
                                continue
                            _plan_steps.append({
                                "step": len(_plan_steps) + 1,
                                "action": _ZH_ACTION.get(_n["id"], _n.get("name", _aid)),
                                "tool": None,
                                "input_hint": "",
                                "expected_result": "",
                                "status": "pending",
                                "result": None,
                                "error": None,
                                "retry_count": 0,
                            })
                        _deep_plan = {
                            "goal": _task_text[:60],
                            "steps": _plan_steps,
                            "current_step": 0,
                            "total_steps": len(_plan_steps),
                            "completed_steps": 0,
                            "failed_steps": 0,
                            "status": "running",
                        }
                        yield f"data: {json.dumps({'type': 'plan', 'plan': _deep_plan}, ensure_ascii=False)}\n\n"
                        # Bridge on_token (called from worker threads) to SSE
                        # yields via a queue. Track which agents have started
                        # so we emit agent_start exactly once per agent.
                        import asyncio as _am_a
                        _evq: asyncio.Queue = asyncio.Queue()
                        _sentinel = object()
                        _started_agents: set[str] = set()

                        def _on_token(node_id, agent_name, agent_id, text):
                            aid = agent_id or node_id
                            if aid not in _started_agents:
                                _started_agents.add(aid)
                                _evq.put_nowait({
                                    "type": "agent_start",
                                    "agent_id": aid,
                                    "agent_name": agent_name or node_id,
                                    "node_id": node_id,
                                    "color": _agent_colors.get(agent_id, "#7C3AED"),
                                })
                                # Flip the matching plan step to in_progress so
                                # the right panel shows it as the active task.
                                _pstep_idx = None
                                _si2 = 0
                                for _n in _net["nodes"]:
                                    if _n.get("agentId") and _n["id"] not in ("input", "output"):
                                        _si2 += 1
                                        if _n["id"] == node_id:
                                            _pstep_idx = _si2
                                            break
                                if _pstep_idx:
                                    _evq.put_nowait({
                                        "type": "plan_step",
                                        "step": {
                                            "step": _pstep_idx,
                                            "action": _ZH_ACTION.get(node_id, agent_name or node_id),
                                            "tool": None,
                                            "input_hint": "",
                                            "expected_result": "",
                                            "status": "in_progress",
                                            "result": None,
                                            "error": None,
                                            "retry_count": 0,
                                        },
                                    })
                            _evq.put_nowait({"type": "agent_token", "agent_id": aid, "text": text})

                        async def _run_dag():
                            try:
                                res = await _dag.run(_net, user_input=_task_text, on_token=_on_token)
                                _evq.put_nowait({"_result": res})
                            except Exception as exc:
                                _evq.put_nowait({"_error": str(exc)})
                            finally:
                                _evq.put_nowait(_sentinel)

                        _dag_task = _am_a.create_task(_run_dag())
                        # Yield agent events as they stream; drain until the
                        # run completes (sentinel), then read the result.
                        # Send a keepalive comment every 15s of silence so
                        # proxies/browsers don't kill the idle connection
                        # during a long multi-agent run.
                        _dag_result = None
                        while True:
                            try:
                                _item = await asyncio.wait_for(_evq.get(), timeout=15.0)
                            except asyncio.TimeoutError:
                                yield ": keepalive\n\n"
                                continue
                            if _item is _sentinel:
                                break
                            if "_result" in _item:
                                _dag_result = _item["_result"]
                                continue
                            if "_error" in _item:
                                _err_msg = f"DAG 执行失败: {_item['_error']}"
                                yield f"data: {json.dumps({'type': 'error', 'message': _err_msg}, ensure_ascii=False)}\n\n"
                                continue
                            # Emit agent_done for any started agents that didn't
                            # get a final event yet (best-effort, from result).
                            yield f"data: {json.dumps(_item, ensure_ascii=False)}\n\n"
                        await _dag_task

                        # After the stream, emit agent_done for each agent
                        # from the structured result, then the final answer.
                        # Also update the right-side task panel by emitting
                        # plan_step events so it reflects each agent's status
                        # instead of spinning on "正在分析任务…".
                        if _dag_result:
                            # Map node_id → plan step index for panel updates.
                            _node_to_step: dict[str, int] = {}
                            _si = 0
                            for _n in _net["nodes"]:
                                if _n.get("agentId") and _n["id"] not in ("input", "output"):
                                    _si += 1
                                    _node_to_step[_n["id"]] = _si
                            for _ns in _dag_result.steps:
                                if _ns.node_id in ("input", "output"):
                                    continue
                                _status = "failed" if _ns.status == "error" else "completed"
                                yield f"data: {json.dumps({'type': 'agent_done', 'agent_id': _ns.agent_id or _ns.node_id, 'status': _ns.status, 'elapsed_ms': _ns.elapsed_ms}, ensure_ascii=False)}\n\n"
                                # Update the matching plan step in BOTH
                                # _plan_steps (so the final summary count is
                                # correct) and the frontend (so the panel
                                # shows a checkmark / cross for this agent).
                                _pstep = _node_to_step.get(_ns.node_id)
                                if _pstep:
                                    if 1 <= _pstep <= len(_plan_steps):
                                        _plan_steps[_pstep - 1]["status"] = _status
                                        if _ns.status == "error" and _ns.error:
                                            _plan_steps[_pstep - 1]["error"] = _ns.error
                                    _step_obj = {
                                        "step": _pstep,
                                        "action": _ZH_ACTION.get(_ns.node_id, _ns.node_id),
                                        "tool": None,
                                        "input_hint": "",
                                        "expected_result": "",
                                        "status": _status,
                                        "result": None,
                                        "error": _ns.error if _ns.status == "error" else None,
                                        "retry_count": 0,
                                    }
                                    yield f"data: {json.dumps({'type': 'plan_step', 'step': _step_obj}, ensure_ascii=False)}\n\n"
                            # Mark the whole plan complete so the panel stops.
                            # Count from _plan_steps which we've now updated
                            # above — without this the counter was always
                            # wrong (counting the initial 'pending' state).
                            _completed = sum(1 for s in _plan_steps if s["status"] == "completed")
                            _failed = sum(1 for s in _plan_steps if s["status"] == "failed")
                            _deep_plan["completed_steps"] = _completed
                            _deep_plan["failed_steps"] = _failed
                            yield f"data: {json.dumps({'type': 'plan', 'plan': {**_deep_plan, 'status': 'completed'}}, ensure_ascii=False)}\n\n"
                            yield f"data: {json.dumps({'type': 'plan_done'}, ensure_ascii=False)}\n\n"
                            # The final answer is the SYNTHESIZER's output —
                            # a single coherent report — NOT the raw merge
                            # concatenation. If the synthesizer failed or
                            # produced nothing, fall back to the longest
                            # specialist output so the user still gets an
                            # answer instead of a blank.
                            _answer = (_dag_result.outputs.get("synthesizer") or "").strip()
                            if not _answer:
                                _fallback = ""
                                for _ns in _dag_result.steps:
                                    if _ns.node_id in ("input", "output", "planner", "synthesizer"):
                                        continue
                                    if _ns.status == "error":
                                        continue
                                    if len(_ns.output) > len(_fallback):
                                        _fallback = _ns.output
                                _answer = _fallback.strip()
                            if _answer:
                                # Live preview catch-all — the synthesizer's
                                # output often contains a complete HTML page;
                                # this routes it to the preview panel.
                                _pe = _extract_and_emit_html_preview(_answer)
                                if _pe:
                                    yield f"data: {_pe}\n\n"
                                yield f"data: {json.dumps({'type': 'text', 'content': _answer}, ensure_ascii=False)}\n\n"
                except Exception as _am_err:
                    yield f"data: {json.dumps({'type': 'error', 'message': f'Agent 模式执行失败: {_am_err}'}, ensure_ascii=False)}\n\n"
                trace_store.mark_done(trace_root.id, output="deep mode completed")
                yield f"data: {json.dumps({'type': 'done', 'model': body.model or ''}, ensure_ascii=False)}\n\n"
                return

            try:
                # -- Phase 0: Plan-and-Execute (if plan_mode) ---------- #
                if body.plan_mode:
                    from madcop.workflow.planner import generate_plan, verify_step, StepStatus
                    from madcop.workflow.planner import execute_step as _exec_step
                    _task = body.messages[-1].content if body.messages else ""
                    if _task:
                        def _plan_llm(msgs, _tools=None, force_tool=None):
                            def _call_with_tools(m):
                                return client.chat(
                                    [Message(role=x.get("role", "user"), content=x.get("content", "")) for x in m],
                                    model=body.model, temperature=0.5,
                                    tools=_tools if _tools is not None else None,
                                )

                            def _auto_exec(resp):
                                _results = []
                                for _tc in resp.tool_calls:
                                    try:
                                        _tool = registry.get(_tc.name)
                                        if _tool:
                                            _out = _tool(**_tc.arguments)
                                            _results.append(str(_out)[:500])
                                        else:
                                            _results.append(f"[TOOL {_tc.name} not found]")
                                    except Exception as _te:
                                        _results.append(f"[TOOL ERROR: {_te}]")
                                return "; ".join(_results) if _results else "(no result)"

                            r = _call_with_tools(msgs)
                            if r.tool_calls:
                                # Auto-execute the tool call and return its result
                                return _auto_exec(r)
                            # No tool calls emitted. Some models (e.g. GLM) describe
                            # the tool in text instead of emitting a structured
                            # tool_call. If this step expected a specific tool, force
                            # a second attempt that explicitly demands the call.
                            if _tools and force_tool:
                                r2 = _call_with_tools(
                                    msgs
                                    + [{"role": "assistant", "content": (r.content or "")[:500]}]
                                    + [{
                                        "role": "user",
                                        "content": (
                                            f"你必须立即调用工具「{force_tool}」并传入正确参数，"
                                            "不要只描述步骤。现在就调用该工具。"
                                        ),
                                    }]
                                )
                                if r2.tool_calls:
                                    return _auto_exec(r2)
                            return r.content or ""
                        _plan = await _loop.run_in_executor(
                            None,
                            lambda: generate_plan(_task, llm_complete=_plan_llm, max_steps=6),
                        )
                        _plan.status = "running"
                        yield f"data: {json.dumps({'type': 'plan', 'plan': _plan.to_dict()}, ensure_ascii=False)}\n\n"
                        for _step in _plan.steps:
                            _step.status = StepStatus.IN_PROGRESS
                            _plan.current_step = _step.step
                            yield f"data: {json.dumps({'type': 'plan_step', 'step': _step.to_dict()}, ensure_ascii=False)}\n\n"
                            try:
                                _result = await _loop.run_in_executor(
                                    None,
                                    lambda s=_step, g=_plan.goal: _exec_step(
                                        s, g,
                                        llm_complete=lambda msgs: _plan_llm(msgs, _tools=tool_schemas, force_tool=s.tool),
                                    ),
                                )
                                _step.result = _result
                                _passed, _reason = await _loop.run_in_executor(
                                    None,
                                    lambda s=_step: verify_step(
                                        s, llm_complete=lambda msgs: _plan_llm(msgs, _tools=tool_schemas),
                                    ),
                                )
                                if _passed:
                                    _step.status = StepStatus.COMPLETED
                                else:
                                    # Soft verification failure. A step that
                                    # actually produced a non-empty result (and
                                    # didn't hard-error at the tool layer) should
                                    # be treated as done — e.g. a greeting / casual
                                    # reply step that the verifier is too strict
                                    # about. Genuine failures (exception above, or
                                    # a tool error string below) stay FAILED.
                                    _res = _step.result or ""
                                    _tool_error = (
                                        "[TOOL ERROR" in _res
                                        or "not found]" in _res
                                    )
                                    if _res.strip() and not _tool_error:
                                        _step.status = StepStatus.COMPLETED
                                        _step.error = None
                                    else:
                                        _step.status = StepStatus.FAILED
                                        _step.error = f"验证失败: {_reason}"
                            except Exception as _e:
                                _step.status = StepStatus.FAILED
                                _step.error = f"异常: {_e}"
                            yield f"data: {json.dumps({'type': 'plan_step', 'step': _step.to_dict()}, ensure_ascii=False)}\n\n"
                            if _step.status == StepStatus.FAILED:
                                # Continue with remaining steps (don't break)
                                pass
                        if _plan.failed_steps == 0:
                            _plan.status = "completed"
                        else:
                            _plan.status = "completed_with_errors"
                        yield f"data: {json.dumps({'type': 'plan', 'plan': _plan.to_dict()}, ensure_ascii=False)}\n\n"
                        yield f"data: {json.dumps({'type': 'plan_done'}, ensure_ascii=False)}\n\n"

                # -- Phase 1: initial call with tools ------------------ #
                # Create a child LLM-call node under the root
                phase1_node = trace_store.create_node(
                    conversation_id=conv_id,
                    parent_id=trace_root.id,
                    node_type="llm_call",
                    label="Initial LLM call (with tools)",
                )
                trace_store.mark_running(phase1_node.id)
                yield f"data: {json.dumps({'type': 'trace', 'node': phase1_node.to_dict()}, ensure_ascii=False)}\n\n"

                # Use non-streaming chat() for the first call so we can
                # inspect tool_calls before deciding how to proceed.
                # Run in executor to avoid blocking the asyncio event loop
                # (the OpenAI SDK is synchronous — a slow LLM response would
                # otherwise freeze health-checks, WebSocket, and all other
                # requests).
                # -- Pre-call token budget check ---------------------------- #
                # Large file attachments can blow past the model's context
                # window.  Estimate total tokens and, if over budget, truncate
                # attachment content aggressively instead of letting the LLM
                # API return a raw 400 error that confuses users.
                # _infer_context_window is defined inside other handlers in
                # this same create_app() scope; fall back to 128K if not
                # visible from here.
                try:
                    _ctx_window = _infer_context_window(body.model or "") or 128_000
                except NameError:
                    _ctx_window = 128_000
                _max_prompt = _ctx_window - getattr(body, "max_tokens", 8192) - 2048  # safety margin
                _estimated = sum(_estimate_tokens(getattr(m, "content", "") or "") for m in messages)
                if _estimated > _max_prompt:
                    # Find the last user message (the one with attachments) and
                    # shrink its ATTACHMENT blocks to fit.
                    _over = _estimated - _max_prompt
                    for _mi in range(len(messages) - 1, -1, -1):
                        _m = messages[_mi]
                        if getattr(_m, "role", "") == "user" and _m.content and "ATTACHMENT:" in _m.content:
                            import re as _re
                            # Shrink each ATTACHMENT block proportionally
                            _parts = _re.split(r'(\n--- ATTACHMENT:.*?--- END ---\n)', _m.content)
                            _new_parts = []
                            _att_text_len = sum(len(p) for p in _parts if "ATTACHMENT:" in p)
                            if _att_text_len > 1000:  # worth truncating
                                _ratio = max(0.1, (_att_text_len - _over * 3) / _att_text_len)
                                for p in _parts:
                                    if "ATTACHMENT:" in p and len(p) > 200:
                                        # Keep header + truncate body
                                        _header_end = p.find("\n", p.find("---\n") + 3)
                                        if _header_end > 0:
                                            _header = p[:_header_end + 1]
                                            _body = p[_header_end + 1:]
                                            _body = _body[:int(len(_body) * _ratio)]
                                            _new_parts.append(_header + _body + "\n…(truncated to fit context window)\n")
                                        else:
                                            _new_parts.append(p[:int(len(p) * _ratio)])
                                    else:
                                        _new_parts.append(p)
                                _m.content = "".join(_new_parts)
                            break  # only modify the last user message
                    # Re-estimate after truncation
                    _estimated2 = sum(_estimate_tokens(getattr(m, "content", "") or "") for m in messages)
                    if _estimated2 > _max_prompt:
                        # Still too big — emit a clear error instead of raw 400
                        _overflow_msg = (
                            f"附件+对话内容过长（约 {_estimated2//1000}K tokens），"
                            f"超出当前模型上下文窗口（{_ctx_window//1000}K tokens）。"
                            f"请尝试：缩小文件、减少对话历史、或换用更大上下文的模型。"
                        )
                        yield f"data: {json.dumps({'type': 'error', 'message': _overflow_msg}, ensure_ascii=False)}\n\n"
                        tr = trace_store.get(trace_root.id)
                        if tr:
                            trace_store.mark_done(trace_root.id, output="context overflow")
                            yield f"data: {json.dumps({'type': 'trace', 'node': tr.to_dict()}, ensure_ascii=False)}\n\n"
                        return

                # Phase 1: stream the tool-routing call so reasoning + text
                # appear live (previously this was a buffered client.chat()
                # that left the UI blank until the whole call finished).
                _p1_holder: dict = {}
                async for sse in _stream_phase1(client, messages, body, tool_schemas, _p1_holder):
                    yield sse
                if "error" in _p1_holder:
                    return  # error already emitted as SSE
                resp = _p1_holder.get("resp")
                if resp is None:
                    return

                # Mark phase 1 done
                p1 = trace_store.get(phase1_node.id)
                if p1:
                    trace_store.mark_done(phase1_node.id, output=str(len(resp.tool_calls or [])) + " tool calls")
                    yield f"data: {json.dumps({'type': 'trace', 'node': p1.to_dict()}, ensure_ascii=False)}\n\n"

                # No tool calls? The text was already streamed during Phase 1
                # (no need to re-stream — the old code re-called the model here).
                if not resp.tool_calls:
                    # -- Memory extraction (async, debounced) ----------- #
                    # Don't block the response — schedule a background
                    # thread that respects the 30s debounce window.
                    try:
                        from .memory_pipeline import schedule_extraction
                        schedule_extraction(messages)
                    except Exception:
                        pass
                    # -- Auto-create skill from "how-to" conversations --- #
                    try:
                        from madcop.agent.skill_forge import get_skill_store, auto_forge_from_conversation
                        user_msg = body.messages[-1].content if body.messages else ""
                        full_assistant = resp.content or ""
                        if full_assistant:
                            auto_forge_from_conversation(
                                get_skill_store(),
                                user_msg,
                                full_assistant,
                                tool_calls=[],
                            )
                    except Exception:
                        pass
                    # Mark root done
                    tr = trace_store.get(trace_root.id)
                    if tr:
                        trace_store.mark_done(trace_root.id, output="completed")
                        yield f"data: {json.dumps({'type': 'trace', 'node': tr.to_dict()}, ensure_ascii=False)}\n\n"
                    # -- Auto-detect HTML in the answer and write it to the
                    # preview directory so the live preview panel picks it
                    # up. Many models output a complete HTML page as a code
                    # block instead of calling write_file — this catch-all
                    # makes the preview work regardless. Only triggers for
                    # self-contained HTML (has <html> or <!DOCTYPE>).
                    try:
                        _preview_event = _extract_and_emit_html_preview(resp.content or "")
                        if _preview_event:
                            yield f"data: {_preview_event}\n\n"
                    except Exception:
                        pass
                    # Emit the terminal done event (Phase-1 streams text but
                    # doesn't emit done itself, so the no-tool path must).
                    yield f"data: {json.dumps({'type': 'done', 'model': resp.model or body.model or '', 'finish_reason': 'stop'}, ensure_ascii=False)}\n\n"
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
                    # Create a tool_call trace node
                    tool_node = trace_store.create_node(
                        conversation_id=conv_id,
                        parent_id=phase1_node.id,
                        node_type="tool_call",
                        label=call.name,
                        input_data={"args": call.arguments},
                    )
                    trace_store.mark_running(tool_node.id)
                    yield f"data: {json.dumps({'type': 'trace', 'node': tool_node.to_dict()}, ensure_ascii=False)}\n\n"

                    yield f"data: {json.dumps({'type': 'tool', 'name': call.name, 'args': call.arguments}, ensure_ascii=False)}\n\n"
                    # Tool dispatch may perform network/file I/O (e.g.
                    # web_search, read_file) — run in executor to keep the
                    # event loop responsive.
                    result = await _loop.run_in_executor(None, lambda: registry.dispatch(call))
                    result_str = result.to_message_content()
                    # Mark tool done
                    trace_store.mark_done(tool_node.id, output=result_str[:200])
                    # Emit the tool result as an SSE event
                    yield f"data: {json.dumps({'type': 'tool_result', 'name': call.name, 'result': result_str}, ensure_ascii=False)}\n\n"
                    # If the agent just wrote a file into the preview
                    # directory, tell the frontend to refresh the live
                    # preview immediately (instead of waiting for the
                    # PreviewPanel's 2s poll).
                    if call.name in ("write_file", "edit_file"):
                        try:
                            import json as _pj
                            _args = call.arguments if isinstance(call.arguments, dict) else _pj.loads(call.arguments or "{}")
                            _fp = str(_args.get("file_path") or _args.get("path") or "")
                            _preview_dir = str(Path.home() / ".madcop" / "preview")
                            if _fp and _preview_dir in _fp:
                                yield f"data: {json.dumps({'type': 'preview_update', 'path': _fp}, ensure_ascii=False)}\n\n"
                        except Exception:
                            pass
                    # Emit trace update
                    tn = trace_store.get(tool_node.id)
                    if tn:
                        yield f"data: {json.dumps({'type': 'trace', 'node': tn.to_dict()}, ensure_ascii=False)}\n\n"
                    # Append tool result to the conversation for the second call
                    messages.append(Message(
                        role="tool",
                        content=result_str,
                        name=call.name,
                        tool_call_id=call.id,
                    ))

                # -- Phase 2: second call with tool results ------------ #
                # v2.6.3.3: Force synthesis — without this, llama-3.1-8b-instruct
                # often just echoes the tool result as a new tool call, leaving
                # the user staring at "recall_memory ✓ echo ✓" with no final
                # answer.
                # NOTE: Use role="user" — some providers (SenseNova etc.) reject
                # system messages not at position 0 (HTTP 400).
                messages.append(Message(
                    role="user",
                    content=(
                        "[System instruction] You now have the tool results above. "
                        "Synthesize a final answer that directly addresses the user's "
                        "original request.\n"
                        "Rules:\n"
                        "1. Do NOT call any more tools.\n"
                        "2. Respond in the SAME language the user used in their latest "
                        "message (e.g. if they wrote in English, answer in English).\n"
                        "3. Be clear and concise. Use Markdown (tables/lists) only when it "
                        "genuinely improves readability — do not force charts or a report "
                        "format onto a simple question.\n"
                        "4. If the tool results are insufficient to answer, say so briefly "
                        "and suggest what is missing.\n"
                    )
                ))

                # Create phase 2 trace node
                phase2_node = trace_store.create_node(
                    conversation_id=conv_id,
                    parent_id=phase1_node.id,
                    node_type="llm_call",
                    label="Second LLM call (synthesize final answer)",
                )
                trace_store.mark_running(phase2_node.id)
                yield f"data: {json.dumps({'type': 'trace', 'node': phase2_node.to_dict()}, ensure_ascii=False)}\n\n"

                # Stream the final response normally but WITHOUT tools,
                # so the model MUST answer instead of calling more tools.
                # Also set max_tokens explicitly to avoid the model producing
                # empty responses (sensenova tends to return 0 tokens when
                # it has no guidance about output length).
                from dataclasses import dataclass
                @dataclass
                class _BareBody:
                    model: str
                    temperature: float
                    max_tokens: int = 8192
                    tools: None = None
                    effort: str | None = None
                no_tools_body = _BareBody(model=body.model or "", temperature=body.temperature or 0.7, effort=body.effort)
                async for sse in _stream_chunks(client, messages, no_tools_body):
                    yield sse

                # Mark phase 2 done
                p2 = trace_store.get(phase2_node.id)
                if p2:
                    trace_store.mark_done(phase2_node.id, output="completed")
                    yield f"data: {json.dumps({'type': 'trace', 'node': p2.to_dict()}, ensure_ascii=False)}\n\n"

                # -- Memory extraction (async, debounced) ----------------- #
                try:
                    from .memory_pipeline import schedule_extraction
                    schedule_extraction(messages)
                except Exception:
                    pass

                # -- Auto-create skill from "how-to" conversations --------- #
                title_user_msg = ""
                assistant_text = ""
                try:
                    from madcop.agent.skill_forge import get_skill_store, auto_forge_from_conversation
                    title_user_msg = body.messages[-1].content if body.messages else ""
                    assistant_text = "".join(m.content for m in messages if m.role == "assistant")
                    auto_forge_from_conversation(
                        get_skill_store(),
                        title_user_msg,
                        assistant_text,
                        tool_calls=[{"name": c.name, "args": c.arguments} for c in resp.tool_calls],
                    )
                except Exception:
                    pass

                # Mark root done
                tr2 = trace_store.get(trace_root.id)
                if tr2:
                    trace_store.mark_done(trace_root.id, output="completed")
                    yield f"data: {json.dumps({'type': 'trace', 'node': tr2.to_dict()}, ensure_ascii=False)}\n\n"

                # --- Auto-generate session title (Claude-style) ---------------
                # After the assistant has produced its first response, use a
                # small, fast LLM call to derive a 3-5 word title. The local
                # client has already set a fallback title from the first user
                # message, so any failure here leaves the local title intact.
                try:
                    if not body.skip_title_gen and assistant_text.strip():
                        generated_title = await _auto_generate_session_title(
                            title_user_msg, assistant_text, client, body.model or "",
                        )
                        if generated_title:
                            yield f"data: {json.dumps({'type': 'session_title', 'title': generated_title}, ensure_ascii=False)}\n\n"
                except Exception:
                    # Never break the response stream on title gen failure.
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
        """List all memories, grouped by kind — now 5 tiers (TencentDB shape).

        L0 episodic, L1 semantic, L2 reflective, L3 scenario,
        L4 persona traits, L5 insight. (madcop's 5-tier is
        inspired by TencentDB Agent Memory's 4-tier pyramid plus the
        cross-session Insight layer.)
        """
        from madcop.memory import (
            MemoryStore, MemoryKind,
            EpisodicMemory, SemanticMemory, ReflectiveMemory,
            ScenarioMemory, PersonaMemory, InsightMemory,
        )
        store = get_memory_store()
        result: dict[str, Any] = {
            "episodic": [],
            "semantic": [],
            "reflective": [],
            "scenario": [],
            "persona": [],
            "insight": [],
        }
        # L0/L1/L2 — from the legacy unified store
        for kind_label, mk in [
            ("episodic", MemoryKind.EPISODIC),
            ("semantic", MemoryKind.SEMANTIC),
            ("reflective", MemoryKind.REFLECTIVE),
        ]:
            for r in store.list_by_kind(mk, limit=200):
                result[kind_label].append({
                    "id": r.id,
                    "kind": r.kind.value,
                    "title": r.title,
                    "content": r.content,
                    "tags": list(r.tags),
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                })
        # L3 scenario + L4 persona + L5 insight — from the new layer stores
        try:
            scm = ScenarioMemory(store)
            for sc in scm.list_recent(limit=50):
                result["scenario"].append(scm.to_public_dict(sc))
        except Exception:
            pass
        try:
            pm = PersonaMemory(store)
            for t in pm.traits():
                result["persona"].append({
                    "key": t.key,
                    "value": t.value,
                    "confidence": t.confidence,
                })
        except Exception:
            pass
        try:
            im = InsightMemory(store)
            for ins in im.list(limit=50):
                result["insight"].append({
                    "id": ins.id,
                    "title": ins.title,
                    "description": ins.description,
                    "confidence": ins.confidence,
                    "occurrences": ins.occurrences,
                    "tags": ins.tags,
                })
        except Exception:
            pass
        # v3.0: total count for clients that want a quick summary
        result["total"] = sum(len(v) for v in result.values() if isinstance(v, list))
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
    # Trace API (Flowtrace)
    # ------------------------------------------------------------------- #

    @app.get("/api/trace/{conversation_id}")
    async def get_trace(conversation_id: str) -> dict[str, Any]:
        """Get the trace DAG for a conversation."""
        from madcop.agent.trace import get_trace_store
        store = get_trace_store()
        nodes = store.get_conversation_trace(conversation_id)
        return {
            "conversation_id": conversation_id,
            "nodes": [n.to_dict() for n in nodes],
            "total": len(nodes),
        }

    @app.post("/api/trace/{conversation_id}/resume")
    async def resume_from_node(conversation_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """Mark all downstream nodes of the given node as superseded.

        The client can then re-run from the given node_id.
        """
        from madcop.agent.trace import get_trace_store
        node_id = body.get("node_id", "")
        if not node_id:
            raise HTTPException(400, "node_id is required")
        store = get_trace_store()
        superseded = store.reset_downstream(node_id)
        return {
            "conversation_id": conversation_id,
            "resumed_from": node_id,
            "superseded_nodes": superseded,
            "count": len(superseded),
        }

    # ------------------------------------------------------------------- #
    # Skills API (auto-distill + LLM-callable)
    # Returns SkillMeta shape: {name, displayName?, description, source,
    #   userInvocable, version?, contentLength, hasDirectory, pluginName?}
    # ------------------------------------------------------------------- #

    @app.get("/api/skills")
    async def list_skills(
        q: str = Query(default=""),
        source: str = Query(default=""),
        cwd: str = Query(default=""),
    ) -> dict[str, Any]:
        """List all skills (auto-distilled user skills + bundled + project)."""
        from madcop.memory.skill_distill import list_user_skills
        from madcop.agent.skill_forge import get_skill_store
        skills: list[dict[str, Any]] = []
        # User skills (auto-distilled) — primary path
        if not source or source == "user":
            for s in list_user_skills():
                if q and q.lower() not in (s["name"] + s.get("description", "")).lower():
                    continue
                s["source"] = "user"
                skills.append(s)
        # Legacy skill_forge store
        try:
            forge = get_skill_store()
            for s in forge.list_skills():
                # Convert forge format to SkillMeta
                if isinstance(s, dict):
                    name = s.get("name", "")
                    skills.append({
                        "name": name,
                        "displayName": s.get("displayName", name),
                        "description": s.get("description", ""),
                        "source": "user",
                        "userInvocable": True,
                        "version": s.get("version", "1.0"),
                        "contentLength": len(s.get("body", "")),
                        "hasDirectory": False,
                    })
        except Exception:
            pass
        # Bundled skills
        if not source or source == "bundled":
            bundled = Path(__file__).resolve().parent.parent.parent / "skills"
            if bundled.exists():
                for f in bundled.glob("*.md"):
                    content = f.read_text(errors="ignore")
                    title = f.stem
                    if content.startswith("# "):
                        title = content.split("\n", 1)[0][2:].strip()
                    if q and q.lower() not in (title + content).lower():
                        continue
                    skills.append({
                        "name": f.stem,
                        "displayName": title,
                        "description": content[:200],
                        "source": "bundled",
                        "userInvocable": True,
                        "contentLength": len(content),
                        "hasDirectory": False,
                        "path": str(f),
                    })
        return {"skills": skills, "total": len(skills)}

    @app.get("/api/skills/detail")
    async def get_skill_detail(
        name: str = Query(...),
        source: str = Query(default="user"),
        cwd: str = Query(default=""),
    ) -> dict[str, Any]:
        """Get a skill's full content. Returns {detail: SkillDetail}.

        Must be registered BEFORE the /api/skills/{name} catch-all below,
        otherwise FastAPI matches the literal "detail" as the {name}.
        """
        from madcop.memory.skill_distill import read_skill_detail
        detail = read_skill_detail(name, source)
        if detail:
            return {"detail": detail}
        raise HTTPException(404, f"Skill '{name}' not found")

    @app.get("/api/skills/search")
    async def search_skills(q: str = "") -> dict[str, Any]:
        """Search user+bundled skills by name/description.

        Registered BEFORE `/api/skills/{name}` so the literal path
        `/api/skills/search` is not shadowed by the `{name}` parameter.
        """
        from madcop.memory.skill_distill import list_user_skills
        skills = list_user_skills()
        if q:
            skills = [s for s in skills if q.lower() in s["name"].lower()
                      or q.lower() in s.get("description", "").lower()]
        return {"results": skills, "total": len(skills)}

    @app.get("/api/skills/{name}")
    async def get_skill(name: str) -> dict[str, Any]:
        """Get a single skill by name. Returns SkillDetail shape."""
        from madcop.memory.skill_distill import read_skill_detail
        detail = read_skill_detail(name, "user")
        if detail:
            return detail
        # Fallback: skill_forge
        from madcop.agent.skill_forge import get_skill_store
        skill = get_skill_store().get_skill(name)
        if skill:
            return {
                "meta": {
                    "name": name,
                    "displayName": skill.get("displayName", name),
                    "description": skill.get("description", ""),
                    "source": "user",
                    "userInvocable": True,
                    "contentLength": len(skill.get("body", "")),
                    "hasDirectory": False,
                },
                "tree": [],
                "files": [{
                    "path": str(Path.home() / ".madcop" / "skills" / f"{name}.md"),
                    "content": skill.get("body", ""),
                    "language": "markdown",
                    "isEntry": True,
                }],
                "skillRoot": str(Path.home() / ".madcop" / "skills"),
            }
        raise HTTPException(404, f"Skill '{name}' not found")

    @app.post("/api/skills")
    async def create_skill(body: dict[str, Any]) -> dict[str, Any]:
        """Manually create a skill. Also auto-distills if it looks teachable."""
        name = body.get("name", "unnamed")
        description = body.get("description", "")
        body_md = body.get("body", "")
        # Use distill module to create the file with proper format
        from madcop.memory.skill_distill import force_distill_skill
        topic = body.get("topic", name)
        skill_name = force_distill_skill(
            topic, description or topic, body_md)
        if not skill_name:
            # Fallback: just write directly
            target = Path.home() / ".madcop" / "skills" / f"{name}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            content = f"# {name}\n\n{description}\n\n{body_md}\n"
            target.write_text(content, encoding="utf-8")
            skill_name = target.stem
        return {"path": str(Path.home() / ".madcop" / "skills" / f"{skill_name}.md"),
                "created": True, "name": skill_name}

    @app.post("/api/skills/distill")
    async def distill_skill_endpoint(body: dict[str, Any]) -> dict[str, Any]:
        """Manually trigger auto-distill from a (query, response) pair."""
        from madcop.memory.skill_distill import force_distill_skill
        topic = body.get("topic", "")
        user_q = body.get("userQuery", topic)
        assistant_r = body.get("assistantResponse", "")
        if not user_q or not assistant_r:
            return {"ok": False, "error": "userQuery and assistantResponse required"}
        name = force_distill_skill(topic, user_q, assistant_r)
        if name:
            return {"ok": True, "skillName": name}
        return {"ok": False, "error": "could not distill"}

    @app.delete("/api/skills/{name}")
    async def delete_skill(name: str) -> dict[str, Any]:
        target = Path.home() / ".madcop" / "skills" / f"{name}.md"
        if not target.exists():
            raise HTTPException(404, f"Skill '{name}' not found")
        target.unlink()
        return {"deleted": True, "name": name}

    # ------------------------------------------------------------------- #
    # WebUI (static HTML at /)
    # ------------------------------------------------------------------- #

    web_dir = Path(__file__).resolve().parent.parent.parent / "web"
    if web_dir.exists():
        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(web_dir / "index.html", media_type="text/html")

        app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")

    # ------------------------------------------------------------------- #
    # cc-haha React client compatibility layer
    # Surfaces madcop's real data (skills, memory, sessions, channels)
    # through the endpoints the cc-haha UI expects.
    # ------------------------------------------------------------------- #
    # v3.0 — Agent Network API (agent registry + knowledge base + orchestration)
    # MUST be registered BEFORE register_madcop_compat, because the
    # compat layer registers its own @app.get('/api/agents') handler
    # that would intercept our agent_network routes.
    from madcop.agent_network.api import router as agent_router
    from madcop.training.api import router as training_router
    from madcop.arena.api import router as arena_router

    # v3.0 — Extras API (SkillBuilder + UsageStats) — MadCop-exclusive
    from madcop.extras.api import router as extras_router
    app.include_router(extras_router)
    app.include_router(agent_mode_router)
    app.include_router(agent_router)
    app.include_router(training_router)
    app.include_router(arena_router)

    from .madcop_compat import register as register_madcop_compat
    from .madcop_compat import install_catch_all
    register_madcop_compat(app)

    # ------------------------------------------------------------------- #
    # v2.7.0 — Visual workflow orchestration API.
    # MUST be mounted BEFORE install_catch_all, because catch_all
    # has path /api/{path:path} and would otherwise intercept
    # /api/workflows/* routes.
    # ------------------------------------------------------------------- #
    from madcop.workflow.api import router as workflow_router
    app.include_router(workflow_router)

    # ── Design generation endpoint ────────────────────────────────────── #
    # MUST be registered BEFORE install_catch_all, otherwise the catch-all
    # /api/{path:path} route will intercept /api/design/generate and
    # return an empty {} response.
    @app.post("/api/design/generate")
    async def design_generate(body: dict):
        """Lightweight endpoint for UI design generation.
        Calls the LLM directly without tools/memory/streaming.
        """
        prompt = body.get("prompt", "")
        if not prompt:
            raise HTTPException(400, "prompt is required")

        system_prompt = body.get("system_prompt", _DESIGN_DEFAULT_SYSTEM_PROMPT)

        client = _get_client()
        # Bump timeout for design generation (LLM needs more time for JSON)
        if hasattr(client, '_client'):
            try:
                client._client = client._client.__class__(
                    api_key=client.api_key,
                    base_url=client.base_url,
                    timeout=90.0,
                )
            except Exception:
                pass
        from madcop.llm import Message
        messages = [
            Message(role="system", content=system_prompt),
            Message(role="user", content=f"根据以下需求生成 UI 设计 JSON（只返回 JSON，不要解释）：\n\n{prompt}"),
        ]

        try:
            resp = client.chat(
                messages=messages,
                tools=None,
                temperature=0.3,
                max_tokens=4096,
            )
            text = (getattr(resp, "content", "") or "")
        except Exception as e:
            import sys as _err_sys, traceback as _tb
            err_msg = str(e)
            print(f"[design_generate] ERROR: {type(e).__name__}: {err_msg[:200]}", file=_err_sys.stderr, flush=True)
            # Return error info instead of 502 — frontend can show useful message
            if "timeout" in err_msg.lower() or "timed out" in err_msg.lower():
                raise HTTPException(504, "AI 响应超时，请稍后重试")
            raise HTTPException(502, f"LLM 调用失败: {type(e).__name__}")

        return {"content": text, "model": getattr(client, "model", "unknown")}

    # ------------------------------------------------------------------- #
    # Workspace API — list files, select working directory
    # Defined here (BEFORE install_catch_all) so they are registered
    # earlier and win priority over the /api/{path:path} catch-all.
    # ------------------------------------------------------------------- #
    # State lives in a closure list so handlers share the same value
    # across requests within this app instance.

    _ws_state: list[str | None] = [None]

    @app.get("/api/workspace/dir")
    async def _workspace_get_dir() -> dict[str, Any]:
        return {"dir": _ws_state[0] or ""}

    @app.post("/api/workspace/dir")
    async def _workspace_set_dir(body: dict[str, str]) -> dict[str, Any]:
        d = body.get("dir", "").strip()
        p = Path(d).expanduser() if d else None
        _ws_state[0] = str(p) if (p and p.is_dir()) else None
        return {"dir": _ws_state[0] or ""}
    @app.get("/api/workspace/ls")
    async def _workspace_ls(dir: str = "", offset: int = 0, limit: int = 50) -> dict[str, Any]:
        from madcop.server import app as _appmod
        target = dir or _ws_state[0] or ""
        if not target:
            return {"error": "no workspace dir set", "entries": []}
        p = Path(target).expanduser()
        if not p.is_dir():
            return {"error": f"not a directory: {target}", "entries": []}
        try:
            all_entries = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            total = len(all_entries)
            page = all_entries[offset: offset + limit]
            entries = []
            for entry in page:
                try:
                    stat = entry.stat()
                    entries.append({
                        "name": entry.name,
                        "is_dir": entry.is_dir(),
                        "size": stat.st_size if entry.is_file() else 0,
                        "modified": int(stat.st_mtime),
                    })
                except Exception:
                    entries.append({"name": entry.name, "is_dir": False, "size": 0, "modified": 0})
            return {"dir": str(p), "entries": entries, "total": total}
        except Exception as e:
            return {"error": str(e), "entries": []}

    @app.get("/api/workspace/dirs-debug")
    async def _workspace_dirs_debug() -> dict[str, Any]:
        # Debug: show what allowed_dirs the file tools would get when
        # invoked from a chat with the currently selected workspace.
        from madcop.tools import default_registry
        reg = default_registry(workspace_dir=_ws_state[0])
        result: dict[str, Any] = {"ws_state": _ws_state[0]}
        for name, entry in reg._tools.items():
            if name in ('write_file', 'edit_file', 'read_file'):
                result[name] = entry._allowed_dirs
        return result

    install_catch_all(app)

    # ------------------------------------------------------------------- #
    # WebSocket endpoint — the cc-haha React UI opens
    #   ws://host:8765/ws/<sessionId>
    # for real-time chat streaming.  We bridge it to the same LLM
    # client as the /api/chat SSE endpoint so the Electron UI sees
    # a unified stream of {type, content, done} messages.
    # ------------------------------------------------------------------- #

    @app.websocket("/ws/{session_id}")
    async def cc_websocket_chat(ws: WebSocket, session_id: str) -> None:
        import sys
        print(f"[ws] accepted session_id={session_id}", file=sys.stderr, flush=True)
        # Send the standard 'connected' handshake first.
        await ws.accept()
        await ws.send_json({"type": "connected", "sessionId": session_id})

        # Lazy import to share _MESSAGES dict with madcop_compat
        from madcop.server.madcop_compat import _MESSAGES, _SESSIONS

        # v2.6.3.3: per-session middleware chain. Wires the Qian control
        # theory middleware into the WebSocket chat path so every
        # step outcome goes through 闭环反馈 / 早纠偏 / 可控性.
        # The chain observes HOOK_STEP_END events (each LLM call +
        # tool result counts as a step) and emits HALT directives
        # on stuck patterns / rate-limit / deviation. This makes
        # the "思维链路" observable and the agent recoverable
        # instead of stuck silently.
        from madcop.agent.middleware import (
            QianControlMiddleware, MiddlewareChain, HookContext,
            HOOK_PLAN_START, HOOK_STEP_START, HOOK_STEP_END,
            HOOK_PLAN_END, Directive,
        )
        middleware_chain = MiddlewareChain([QianControlMiddleware()])
        step_count_per_session: dict[str, int] = {}

        def ws_step(hook: str, outcome=None, step_name: str = "ws_chat") -> None:
            """Run a middleware step on the session's chain.
            Emits a status event if the chain produced a HALT."""
            ctx = HookContext(
                hook=hook,
                goal=f"session:{session_id}",
                step=type("S", (), {"name": step_name})(),
                outcome=outcome,
            )
            try:
                middleware_chain(ctx)
            except Exception as e:
                print(f"[ws/mw] error: {e}", file=sys.stderr, flush=True)
            # Check directives for HALT
            for d in ctx.directives:
                if d.kind == "HALT":
                    print(f"[ws/mw] HALT: {d.detail}", file=sys.stderr, flush=True)
            step_count_per_session[session_id] = (
                step_count_per_session.get(session_id, 0) + 1
            )
        # Emit HOOK_PLAN_START for this turn
        ws_step(HOOK_PLAN_START, step_name="turn_start")

        try:
            while True:
                msg = await ws.receive_json()
                print(f"[ws] {session_id} recv: {str(msg)[:200]}", file=sys.stderr, flush=True)
                if not isinstance(msg, dict):
                    continue
                mtype = msg.get("type", "")

                # Simple acks ------------------------------------------------- #
                if mtype == "ping":
                    await ws.send_json({"type": "pong"})
                    continue
                if mtype == "set_runtime_config":
                    await ws.send_json({"type": "ack", "config": msg})
                    continue
                if mtype == "set_permission_mode":
                    await ws.send_json({
                        "type": "permission_mode_changed",
                        "mode": msg.get("mode", "default"),
                    })
                    continue
                if mtype == "prewarm_session":
                    await ws.send_json({"type": "ack", "sessionId": session_id})
                    continue
                if mtype == "stop_generation":
                    await ws.send_json({"type": "status", "state": "idle"})
                    continue
                if mtype == "permission_response":
                    # In a real impl we'd apply this to the live tool call.
                    await ws.send_json({"type": "status", "state": "idle"})
                    continue
                if mtype == "computer_use_permission_response":
                    await ws.send_json({"type": "status", "state": "idle"})
                    continue

                # Chat turn (user_message OR chat) ------------------------- #
                from madcop.llm import Message
                model = msg.get("model")
                temperature = msg.get("temperature", 0.7)
                if mtype == "user_message":
                    content = msg.get("content", "")
                    if not content:
                        await ws.send_json({"type": "status", "state": "idle"})
                        continue
                    messages = [Message(role="user", content=content)]
                elif mtype in ("chat", ""):
                    raw_messages = msg.get("messages", [])
                    if not raw_messages:
                        await ws.send_json({"type": "status", "state": "idle"})
                        continue
                    try:
                        messages = [
                            Message(role=m["role"], content=m["content"])
                            for m in raw_messages
                        ]
                    except (KeyError, TypeError):
                        await ws.send_json({"type": "status", "state": "idle"})
                        continue
                else:
                    # Unknown message type — ignore gracefully.
                    continue

                # ---- Save user message to session history (cc-haha compat) ---- #
                # Persist into madcop_compat._MESSAGES[session_id] so the
                # Electron UI can re-fetch it via /api/sessions/{id}/messages.
                import time as _time, uuid as _uuid
                now_iso = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())
                # Ensure session exists
                # Keep the session bound to the user's working directory so it
                # persists under <workDir>/.madcop/ instead of the backend cwd.
                msg_wd = msg.get("workDir") or msg.get("work_dir") \
                    or msg.get("projectPath") or msg.get("projectRoot")
                if session_id not in _SESSIONS:
                    _SESSIONS[session_id] = {
                        "id": session_id,
                        "title": (messages[-1].content[:40] if messages else "New Session"),
                        "createdAt": now_iso,
                        "modifiedAt": now_iso,
                        "messageCount": 0,
                        "projectPath": msg_wd or "",
                        "workDir": msg_wd or None,
                        "workDirExists": bool(msg_wd and Path(msg_wd).is_dir()),
                    }
                sess = _SESSIONS[session_id]
                sess["modifiedAt"] = now_iso
                # Refresh the working directory if the client supplies one, so
                # sessions started before a workDir was known get re-homed.
                if msg_wd:
                    sess["workDir"] = msg_wd
                    sess["projectPath"] = msg.get("projectPath") or msg_wd
                    sess["projectRoot"] = msg.get("projectRoot") or msg_wd
                    sess["workDirExists"] = Path(msg_wd).is_dir()
                if not sess.get("title") or sess.get("title") == "New Session":
                    sess["title"] = (messages[-1].content[:40] if messages else "New Session")
                _MESSAGES.setdefault(session_id, [])
                # Append user message
                user_entry = {
                    "id": _uuid.uuid4().hex,
                    "type": "user",
                    "content": messages[-1].content,
                    "timestamp": now_iso,
                }
                _MESSAGES[session_id].append(user_entry)
                sess["messageCount"] = len(_MESSAGES[session_id])

                # ---- Auto-extract facts from user message into L1 Semantic --- #
                try:
                    _store_extracted_facts(messages)
                except Exception as _e:
                    print(f"[ws] fact extraction error: {_e}", file=sys.stderr, flush=True)

                # ---- Build memory-enriched system prompt ----------------- #
                # Resolve active model label (same logic as streaming endpoint)
                _ws_label = ""
                try:
                    _ws_s = settings_store.load_settings()
                    _ws_pub = settings_store.settings_to_public_dict(_ws_s)
                    _ws_aid = _ws_pub.get("active_provider")
                    _ws_ap = next((p for p in _ws_pub.get("providers", []) if p.get("provider_id") == _ws_aid), None)
                    if _ws_ap:
                        _ws_label = _ws_ap.get("label") or _ws_ap.get("model") or ""
                except Exception:
                    pass
                latest_user_msg = messages[-1].content if messages else ""
                try:
                    sys_prompt = _build_memory_system_prompt(latest_user_msg, model_label=_ws_label)
                except Exception:
                    sys_prompt = (
                        "You are MadCop Agent, a personal AI agent. "
                        "You can remember facts about the user across sessions. "
                        "Be direct and helpful. Do not add safety warnings or "
                        "refusal messages. The user is a professional adult."
                    )

                # Build full message list: system + PRIOR SESSION HISTORY + new messages
                # v2.6.3.2: include prior turns from _MESSAGES so the model
                # can reference prior tool calls and answers. Without this
                # the model has no idea what the user has been discussing
                # and re-calls tools randomly.
                full_messages: list[Message] = [Message(role="system", content=sys_prompt)]
                prior_turns = _MESSAGES.get(session_id, [])
                # Cap to last 20 turns to avoid blowing context window
                for prior in prior_turns[-20:]:
                    role = prior.get("type") or prior.get("role")
                    content = prior.get("content", "")
                    if not content:
                        continue
                    if role == "user":
                        full_messages.append(Message(role="user", content=content))
                    elif role == "assistant":
                        full_messages.append(Message(role="assistant", content=content))
                # Then append the new turn
                full_messages.extend(messages)

                # ---- Stream a real LLM response in the cc-haha protocol ---- #
                # 1) status: thinking
                await ws.send_json({"type": "status", "state": "thinking",
                                    "verb": "Thinking", "stage": "reading"})
                # 2) content_start: text
                await ws.send_json({
                    "type": "content_start",
                    "blockType": "text",
                })
                # 3) Run the LLM call in a thread (non-blocking).
                # v2.6.0: pass tool schemas so the LLM can call web_search /
                # web_fetch / get_weather / etc. (registry has 6+ tools).
                # Some models (e.g. minimax-m3) reject parallel tool calls
                # with 'single tool-calls at once!' — handled by passing
                # parallel_tool_calls=False in the tool defs.
                try:
                    client = _get_client()
                    registry = default_registry(store=get_memory_store(), workspace_dir=_ws_state[0])
                    tool_schemas = registry.openai_schemas()
                    # Annotate each tool with parallel_tool_calls: False
                    # so the model only emits ONE call per request.
                    for ts in (tool_schemas or []):
                        if "function" in ts:
                            ts["function"]["parallel_tool_calls"] = False
                    resp = await asyncio.to_thread(
                        client.chat,
                        full_messages,
                        model=model,
                        temperature=temperature,
                        tools=tool_schemas or None,
                        effort=body.effort,
                    )
                    content = resp.content or ""
                    # 4) content_delta: ship the whole text in one chunk
                    if content:
                        await ws.send_json({
                            "type": "content_delta",
                            "text": content,
                        })
                    # ---- Tool-call loop: execute any requested tools, then
                    #      do a second LLM call with the tool results.
                    # ----
                    if resp.tool_calls:
                        # Emit a content_block_end so the UI knows the
                        # first text block is done and tool_use is coming.
                        # The frontend treats tool calls as separate blocks.
                        # Append the assistant's tool-call message so the
                        # API accepts the following tool messages.
                        from madcop.llm import Message as _Msg
                        full_messages.append(_Msg(
                            role="assistant",
                            content=content or "",
                            tool_calls=resp.tool_calls,
                        ))
                        for call in resp.tool_calls:
                            args = call.arguments or {}
                            # Pretty name mapping for the UI
                            tool_label = {
                                "web_search": "🔍 上网搜索",
                                "web_fetch": "🌐 抓取网页",
                                "get_weather": "🌤 查询天气",
                                "bash": "💻 执行命令",
                                "read_file": "📄 读取文件",
                                "write_file": "✏️ 写入文件",
                            }.get(call.name, f"🔧 {call.name}")
                            await ws.send_json({
                                "type": "tool_use_complete",
                                "toolName": call.name,
                                "toolUseId": call.id or "",
                                "input": args,
                                "label": tool_label,
                            })
                            try:
                                result = await asyncio.to_thread(
                                    registry.dispatch, call)
                                result_str = result.to_message_content()
                                tool_ok = True
                            except Exception as exc:
                                result_str = f"Tool error: {exc}"
                                tool_ok = False
                            # v2.6.3.3: emit HOOK_STEP_END so the Qian control
                            # middleware can apply 闭环反馈 / 早纠偏 /
                            # 可控性 to the tool result. Without this the
                            # tool result disappears from the observability
                            # layer.
                            ws_step(
                                HOOK_STEP_END,
                                outcome=type("O", (), {
                                    "success": tool_ok,
                                    "cost_usd": 0.0,
                                    "error": "" if tool_ok else result_str,
                                    "output": result_str[:200],
                                })(),
                                step_name=f"tool:{call.name}",
                            )
                            await ws.send_json({
                                "type": "tool_result",
                                "toolUseId": call.id or "",
                                "name": call.name,
                                "content": result_str,
                                "isError": False,
                            })
                            # v2.6.3.3: handle ask_user specially — pause the
                            # loop, send a clarification_request to the UI,
                            # wait for the user's response, then resume.
                            if call.name == "ask_user":
                                args = call.arguments or {}
                                question = args.get("question", "请确认")
                                options = args.get("options", [])
                                allow_free_text = args.get("allow_free_text", True)
                                await ws.send_json({
                                    "type": "clarification_request",
                                    "toolUseId": call.id or "",
                                    "question": question,
                                    "options": options,
                                    "allowFreeText": allow_free_text,
                                })
                                # Wait for the user's response
                                try:
                                    while True:
                                        reply_raw = await asyncio.wait_for(
                                            ws.receive_json(),
                                            timeout=300.0,  # 5 min
                                        )
                                        rtype = reply_raw.get("type", "")
                                        if rtype == "clarification_response":
                                            choice = reply_raw.get("choice", "")
                                            if not choice:
                                                choice = "(no answer)"
                                            full_messages.append(_Msg(
                                                role="tool",
                                                content=f"User answered: {choice}",
                                                name="ask_user",
                                                tool_call_id=call.id,
                                            ))
                                            # Break out of the inner tool loop
                                            # so the next LLM call sees the answer.
                                            break
                                        # Ignore other message types while
                                        # we're waiting for clarification.
                                except asyncio.TimeoutError:
                                    full_messages.append(_Msg(
                                        role="tool",
                                        content="User did not answer (timeout). "
                                                "Make a reasonable guess and proceed.",
                                        name="ask_user",
                                        tool_call_id=call.id,
                                    ))
                                # Skip the rest of the tool dispatch for this
                                # call — we don't need to send tool_use_complete
                                # for a clarification. (Already sent above.)
                                continue
                            full_messages.append(_Msg(
                                role="tool",
                                content=result_str,
                                name=call.name,
                                tool_call_id=call.id,
                            ))
                        # ---- Loop: do a 2nd LLM call, then a 3rd if it
                        #      produced more tool calls, etc. We cap at 3
                        #      rounds to avoid infinite loops. Each round
                        #      is one tool call (parallel_tool_calls=False).
                        # ----
                        for _round in range(3):
                            await ws.send_json({
                                "type": "status", "state": "thinking",
                                "verb": "Composing", "stage": "searching",
                            })
                            resp2 = await asyncio.to_thread(
                                client.chat,
                                full_messages,
                                model=model,
                                temperature=temperature,
                                tools=tool_schemas or None,
                                effort=body.effort,
                            )
                            content2 = resp2.content or ""
                            if content2:
                                await ws.send_json({
                                    "type": "content_delta",
                                    "text": content2,
                                })
                            # If the 2nd call didn't trigger more tools,
                            # we're done.
                            if not resp2.tool_calls:
                                resp = resp2
                                content = content2
                                break
                            # Otherwise, append and execute again.
                            full_messages.append(_Msg(
                                role="assistant",
                                content=content2 or "",
                                tool_calls=resp2.tool_calls,
                            ))
                            for call in resp2.tool_calls:
                                args = call.arguments or {}
                                tool_label = {
                                    "web_search": "🔍 上网搜索",
                                    "web_fetch": "🌐 抓取网页",
                                    "get_weather": "🌤 查询天气",
                                    "bash": "💻 执行命令",
                                    "read_file": "📄 读取文件",
                                    "write_file": "✏️ 写入文件",
                                }.get(call.name, f"🔧 {call.name}")
                                await ws.send_json({
                                    "type": "tool_use_complete",
                                    "toolName": call.name,
                                    "toolUseId": call.id or "",
                                    "input": args,
                                    "label": tool_label,
                                })
                                try:
                                    result = await asyncio.to_thread(
                                        registry.dispatch, call)
                                    result_str = result.to_message_content()
                                except Exception as exc:
                                    result_str = f"Tool error: {exc}"
                                await ws.send_json({
                                    "type": "tool_result",
                                    "toolUseId": call.id or "",
                                    "name": call.name,
                                    "content": result_str,
                                    "isError": False,
                                })
                                full_messages.append(_Msg(
                                    role="tool",
                                    content=result_str,
                                    name=call.name,
                                    tool_call_id=call.id,
                                ))
                            # Continue to next round
                            resp = resp2
                            content = content2

                        # ---- Final synthesis call (no tools) ----
                        # v2.6.3: Force a final tool-free call so the model
                        # must give a natural-language answer instead of
                        # looping on more tool calls.
                        # NOTE: Use role="user" here — some providers (e.g.
                        # SenseNova) reject system messages that are NOT at
                        # position 0 ("System message must be at the
                        # beginning", HTTP 400).
                        if resp.tool_calls:
                            await ws.send_json({
                                "type": "status", "state": "thinking",
                                "verb": "Composing answer", "stage": "ready",
                            })
                            final = await asyncio.to_thread(
                                client.chat,
                                full_messages + [_Msg(
                                    role="user",
                                    content="[System instruction] You have "
                                    "all the tool results you need. Now write "
                                    "a detailed, helpful answer in the user's "
                                    "language. Summarize the data from the "
                                    "tools (numbers, names, links) into a "
                                    "clear, well-formatted response. Use "
                                    "bullet points or short paragraphs as "
                                    "appropriate. Do NOT call any more tools.",
                                )],
                                model=model,
                                temperature=temperature,
                                tools=None,  # no tools — must answer
                                effort=body.effort,
                            )
                            final_content = final.content or ""
                            if final_content:
                                await ws.send_json({
                                    "type": "content_delta",
                                    "text": final_content,
                                })
                            resp = final
                            content = final_content
                    # ---- Save assistant message to history ---- #
                    # v2.6.3.3: emit HOOK_STEP_END for the final LLM call so
                    # the Qian middleware sees the completed answer and
                    # emits any HALT directive based on drift / deviation.
                    ws_step(
                        HOOK_STEP_END,
                        outcome=type("O", (), {
                            "success": bool(content),
                            "cost_usd": 0.0,
                            "error": "",
                            "output": content or "",
                        })(),
                        step_name="llm_final",
                    )
                    ws_step(HOOK_PLAN_END, step_name="turn_end")
                    asst_entry = {
                        "id": _uuid.uuid4().hex,
                        "type": "assistant",
                        "content": content,
                        "timestamp": _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime()),
                        "model": resp.model,
                    }
                    _MESSAGES[session_id].append(asst_entry)
                    sess["messageCount"] = len(_MESSAGES[session_id])
                    # ---- Auto-distill SKILL from teach-me exchanges ---- #
                    try:
                        from madcop.memory.skill_distill import (
                            distill_skill_from_exchange,
                        )
                        skill_name = distill_skill_from_exchange(
                            user_query=latest_user_msg,
                            assistant_response=content,
                        )
                        if skill_name:
                            await ws.send_json({
                                "type": "skill_distilled",
                                "skillName": skill_name,
                                "message": f"Auto-distilled SKILL: {skill_name}",
                            })
                    except Exception as _e:
                        import sys as _sys
                        print(f"[ws] skill distill error: {_e}", file=_sys.stderr, flush=True)
                    # 5) status: idle (stream done)
                    await ws.send_json({"type": "status", "state": "idle",
                                        "verb": ""})
                    # 6) message_complete: token usage (best-effort)
                    usage: dict[str, int] = {}
                    raw_usage = getattr(resp, "usage", None) or {}
                    if hasattr(raw_usage, "get"):
                        usage = {
                            "inputTokens": int(raw_usage.get("prompt_tokens", 0) or 0),
                            "outputTokens": int(raw_usage.get("completion_tokens", 0) or 0),
                        }
                    await ws.send_json({
                        "type": "message_complete",
                        "usage": usage,
                        "model": resp.model,
                    })
                except WebSocketDisconnect:
                    return
                except Exception as e:
                    import sys as _sys
                    print(f"[ws] {session_id} error: {e}", file=_sys.stderr, flush=True)
                    try:
                        await ws.send_json({"type": "status", "state": "idle"})
                        await ws.send_json({
                            "type": "error",
                            "message": str(e)[:500],
                        })
                    except Exception:
                        pass
        except WebSocketDisconnect:
            return

    # ------------------------------------------------------------------- #
    # Preview server — serves ~/.madcop/preview/ as static files
    # The agent writes HTML files here via WriteFileTool, the frontend
    # loads them in an iframe for real-time preview.
    # ------------------------------------------------------------------- #
    _preview_dir = Path.home() / ".madcop" / "preview"
    _preview_dir.mkdir(parents=True, exist_ok=True)
    # Write a default index.html so the preview always has something
    _default = _preview_dir / "index.html"
    if not _default.exists():
        _default.write_text(
            "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
            "<title>Preview</title><style>body{font-family:sans-serif;"
            "padding:2rem;color:#666;background:#fafafa;display:flex;"
            "align-items:center;justify-content:center;height:90vh;}"
            "</style></head><body>← 写一个 index.html 到这里开始预览</body></html>"
        )
    app.mount("/preview", StaticFiles(directory=str(_preview_dir), html=True), name="preview")

    return app


# ------------------------------------------------------------------- #
# Module-level app for uvicorn
# ------------------------------------------------------------------- #

app = create_app()

# Module-level state for the workspace directory.
# The handlers are registered inside create_app() (before
# install_catch_all) so they take priority over the /api/{path:path}
# catch-all in madcop_compat.py.
_WORKSPACE_DIR: str | None = None
