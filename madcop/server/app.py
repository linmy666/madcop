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


class ChatAttachment(BaseModel):
    id: str
    name: str
    type: str = "file"
    path: str | None = None
    dataUrl: str | None = None  # base64 data URL for inline previews


def _read_attachment_direct(att: ChatAttachment) -> str:
    """Extract attachment content as plain text — no tool call needed.

    Supports:
    - Text files (base64 dataUrl with text/* mime)
    - PDFs (via pypdf)
    - Anything else → short metadata description
    """
    name = att.name or "file"
    # Case A: real OS file path on the backend server
    if att.path:
        p = Path(att.path).expanduser()
        if p.exists() and p.is_file():
            if name.lower().endswith(".pdf"):
                try:
                    from pypdf import PdfReader as _PdfReader
                    pages = []
                    for pg in _PdfReader(str(p)).pages:
                        try:
                            pages.append(pg.extract_text() or "")
                        except Exception:
                            pages.append("")
                    t = "\n\n---\n\n".join(p.strip() for p in pages if p.strip())
                    if t:
                        return t[:60_000]
                except Exception:
                    pass
            try:
                return p.read_text("utf-8", errors="replace")[:60_000]
            except Exception:
                pass
        return f"[file not readable on server: {name}]"

    # Case B: base64 dataUrl from the chat composer
    if att.dataUrl and att.dataUrl.startswith("data:") and "," in att.dataUrl:
        _, body = att.dataUrl.split(",", 1)
        try:
            import base64 as _b64
            raw = _b64.b64decode(body)
        except Exception:
            return f"[failed to decode {name}]"

        # PDF via pypdf
        if name.lower().endswith(".pdf") or "application/pdf" in att.dataUrl[:100]:
            try:
                import io as _io
                from pypdf import PdfReader as _PdfReader
                pages = []
                for pg in _PdfReader(_io.BytesIO(raw)).pages:
                    try:
                        pages.append(pg.extract_text() or "")
                    except Exception:
                        pages.append("")
                t = "\n\n---\n\n".join(p.strip() for p in pages if p.strip())
                if t:
                    return t[:60_000]
                return "[PDF text extraction returned no content (scanned/image-only PDF?)]"
            except Exception as e:
                return f"[PDF parse error: {e}]"

        # Text files
        if att.dataUrl.startswith("data:text/") or att.dataUrl.startswith("data:application/json"):
            try:
                return raw.decode("utf-8", errors="replace")[:60_000]
            except Exception:
                pass

        # Binary/image files — not readable as text
        return f"[binary file: {name}, size: {len(body)} base64 chars]"

    # Case C: nothing usable
    return f"[no readable content for {name}]"


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float = 0.7
    conversation_id: str | None = None  # optional id for trace persistence
    skip_title_gen: bool = False  # set true to skip Claude-style auto title generation
    attachments: list[ChatAttachment] = []  # file/image attachments from the user
    plan_mode: bool = False  # enable Plan-and-Execute mode


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
    parts.append(
        "FILE ATTACHMENTS: When the user attaches files, you can:\n"
        "- For text-y files (.txt, .md, .json, .csv, source code): the file content is loaded into the conversation. You can read it directly.\n"
        "- For PDFs: text is extracted via pypdf and loaded into the conversation. You can read it directly.\n"
        "- For images (png, jpg, etc.): the current chat model (Sensenova GLM-5.2) does NOT support vision — you cannot see images. "
        "If the user asks you to analyze an image, respond honestly: 'I'm a text-only model and cannot view images. "
        "Please describe what's in the image, or enable a multimodal model like Qwen-VL or GPT-4o.'\n"
        "- For any file: the LLM can use the read_file tool with the path 'attachment://<id>' "
        "(e.g. attachment://att-1234-abc) to load the file's contents from the in-memory attachment store.\n"
        "Do NOT call read_file with a real OS path unless the user explicitly typed one — "
        "their file API path may not be readable on this machine."
    )

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
    "你是 MadCop 设计工具的前端组件生成器。"
    "你根据用户的需求生成符合 MadCop 编辑器格式的 JSON 数据。"
    "\n\n"
    "JSON 格式：\n"
    '{\n'
    '  "root": {\n'
    '    "props": {\n'
    '      "bgColor": "#FFFFFF",   // 背景色，十六进制\n'
    '      "padding": 40,          // 内边距，数字\n'
    '      "fontFamily": "sans-serif" // 全局字体\n'
    '    }\n'
    '  },\n'
    '  "content": [\n'
    '    { "type": "组件名", "props": { "属性名": "属性值" } }\n'
    '  ]\n'
    '}\n'
    "\n\n"
    "可用组件列表：\n"
    "1. Header — 标题：text(文字), level(1|2|3), color(颜色), fontSize(字号,数字)\n"
    "2. Paragraph — 段落：text(文字), color(颜色), fontSize(字号,数字), textAlign(left|center|right)\n"
    "3. Button — 按钮：text(文字), variant(primary|secondary), color(主色), width(宽度,数字)\n"
    "4. Image — 图片：src(图片地址), alt(替代文字), width(宽度), height(高度), borderRadius(圆角)\n"
    "5. Input — 输入框：placeholder(占位文字), width(宽度,数字), type(text|password|email)\n"
    "6. Card — 卡片容器：padding(内边距), bgColor(背景色), radius(圆角), shadow(sm|md|lg)\n"
    "7. Flex — 弹性布局容器：direction(row|column), gap(间距,数字), justify(center|between|around|start), align(center|start|stretch)\n"
    "8. Grid — 网格布局容器：columns(列数,数字), gap(间距,数字)\n"
    "9. Section — 全宽区块：bgColor(背景色), padding(内边距), maxWidth(最大宽度,数字)\n"
    "10. Divider — 分割线：color(颜色), thickness(粗细,数字), margin(外边距,数字)\n"
    "11. Space — 空白占位：height(高度,数字)\n"
    "\n\n"
    "【重要规则】\n"
    "1. 内容要真实，不要用\"标题\"\"段落\"这类占位词\n"
    "2. 颜色搭配要合理美观，善用品牌色\n"
    "3. 只返回 JSON，不要任何解释文字\n"
    "4. 善用容器组件（Flex/Grid/Card/Section）来组织布局\n"
    "5. Flex 的 direction=row 时内容水平排列，column 时垂直排列\n"
    "6. 复杂布局：外层用 Section → 内层用 Flex/Card → 最内层用文本/输入组件\n"
    "\n\n"
    "【FEW-SHOT 样例 — 登录页】\n"
    '{\n'
    '  "root": { "props": { "bgColor": "#FFFFFF", "padding": 40 } },\n'
    '  "content": [\n'
    '    { "type": "Header", "props": { "text": "欢迎回来", "level": "2", "fontSize": 28 } },\n'
    '    { "type": "Paragraph", "props": { "text": "请登录你的账号继续", "fontSize": 14, "color": "#6B7280" } },\n'
    '    { "type": "Space", "props": { "height": 24 } },\n'
    '    { "type": "Input", "props": { "placeholder": "邮箱地址", "width": 320, "type": "email" } },\n'
    '    { "type": "Space", "props": { "height": 12 } },\n'
    '    { "type": "Input", "props": { "placeholder": "密码", "width": 320, "type": "password" } },\n'
    '    { "type": "Space", "props": { "height": 24 } },\n'
    '    { "type": "Button", "props": { "text": "登录", "variant": "primary", "color": "#7C3AED", "width": 320 } }\n'
    '  ]\n'
    '}\n'
)


# --------------------------------------------------------------------------- #
# App factory
# --------------------------------------------------------------------------- #

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

    def _stream_chunks(client, messages, body):
        """Yield SSE formatted strings from a streaming LLM call."""
        max_tokens = getattr(body, "max_tokens", None)
        tools = getattr(body, "tools", None)
        for chunk in client.stream(
            messages,
            model=body.model,
            temperature=body.temperature,
            max_tokens=max_tokens,
            tools=tools,
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

        # Convert text-only messages. Attachments' content is EXTRACTED
        # and appended directly to the user message so the LLM can read
        # it without needing to call read_file (GLM-5.2 doesn't always
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
                        extra_parts.append(f"\n--- ATTACHMENT: {att.name} ---\n{content}\n--- END ---")
                messages.append(Message(role=m.role, content="\n".join(extra_parts)))
            else:
                messages.append(Message(role=m.role, content=m.content or ""))

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

            try:
                # -- Phase 0: Plan-and-Execute (if plan_mode) ---------- #
                if body.plan_mode:
                    from madcop.workflow.planner import generate_plan, verify_step
                    from madcop.workflow.planner import execute_step as _exec_step
                    _task = body.messages[-1].content if body.messages else ""
                    if _task:
                        def _plan_llm(msgs):
                            r = client.chat([Message(role=m.get("role","user"), content=m.get("content","")) for m in msgs], model=body.model, temperature=0.5)
                            return r.content or ""
                        _plan = generate_plan(_task, llm_complete=_plan_llm, max_steps=6)
                        _plan.status = "running"
                        yield f"data: {json.dumps({'type': 'plan', 'plan': _plan.to_dict()}, ensure_ascii=False)}\n\n"
                        for _step in _plan.steps:
                            _step.status = "in_progress"
                            _plan.current_step = _step.step
                            yield f"data: {json.dumps({'type': 'plan_step', 'step': _step.to_dict()}, ensure_ascii=False)}\n\n"
                            try:
                                _result = _exec_step(_step, _plan.goal, llm_complete=_plan_llm)
                                _step.result = _result
                                _passed, _reason = verify_step(_step, llm_complete=_plan_llm)
                                if _passed:
                                    _step.status = "completed"
                                else:
                                    _step.status = "failed"
                                    _step.error = f"验证失败: {_reason}"
                            except Exception as _e:
                                _step.status = "failed"
                                _step.error = f"异常: {_e}"
                            yield f"data: {json.dumps({'type': 'plan_step', 'step': _step.to_dict()}, ensure_ascii=False)}\n\n"
                            if _step.status == "failed":
                                _plan.status = "failed"
                                break
                        if _plan.failed_steps == 0:
                            _plan.status = "completed"
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
                resp = client.chat(
                    messages,
                    model=body.model,
                    temperature=body.temperature,
                    tools=tool_schemas,
                )

                # Mark phase 1 done
                p1 = trace_store.get(phase1_node.id)
                if p1:
                    trace_store.mark_done(phase1_node.id, output=str(len(resp.tool_calls or [])) + " tool calls")
                    yield f"data: {json.dumps({'type': 'trace', 'node': p1.to_dict()}, ensure_ascii=False)}\n\n"

                # No tool calls? Stream the text content normally.
                if not resp.tool_calls:
                    for sse in _stream_chunks(client, messages, body):
                        yield sse
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
                        # Reconstruct assistant text from SSE — easier: we don't have it here.
                        # We'll just call the heuristic with a partial signal.
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
                    result = registry.dispatch(call)
                    result_str = result.to_message_content()
                    # Mark tool done
                    trace_store.mark_done(tool_node.id, output=result_str[:200])
                    # Emit the tool result as an SSE event
                    yield f"data: {json.dumps({'type': 'tool_result', 'name': call.name, 'result': result_str}, ensure_ascii=False)}\n\n"
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
                # answer. v2.6.3.1: Tell the model to be DETAILED, not concise,
                # because users want the tool data summarized, not a one-liner.
                messages.append(Message(
                    role="system",
                    content=(
                        "你现在有了上面的搜索结果。请用中文写一份详细的BI分析报告。\n"
                        "要求：\n"
                        "1. 不要再调用任何工具\n"
                        "2. 用 Markdown 格式，包含表格和要点\n"
                        "3. 如果有数据适合可视化，用 Mermaid 图表语法（```mermaid 代码块）\n"
                        "   - 饼图: pie title 标题\\n\"A\" : 30\\n\"B\" : 70\n"
                        "   - 柱状图: xychart-beta\\ntitle \"标题\"\\nbar [100, 200, 300]\n"
                        "   - 流程图: flowchart LR\\nA --> B --> C\n"
                        "4. 报告 300-800 字\n"
                        "5. 直接开始写报告，不要说废话\n"
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
                no_tools_body = _BareBody(model=body.model or "", temperature=body.temperature or 0.7)
                for sse in _stream_chunks(client, messages, no_tools_body):
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

    @app.get("/api/skills/search")
    async def search_skills(q: str = "") -> dict[str, Any]:
        from madcop.memory.skill_distill import list_user_skills
        skills = list_user_skills()
        if q:
            skills = [s for s in skills if q.lower() in s["name"].lower()
                      or q.lower() in s.get("description", "").lower()]
        return {"results": skills, "total": len(skills)}

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
                max_tokens=2048,
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
                if session_id not in _SESSIONS:
                    _SESSIONS[session_id] = {
                        "id": session_id,
                        "title": (messages[-1].content[:40] if messages else "New Session"),
                        "createdAt": now_iso,
                        "modifiedAt": now_iso,
                        "messageCount": 0,
                        "projectPath": "",
                        "workDir": None,
                        "workDirExists": False,
                    }
                sess = _SESSIONS[session_id]
                sess["modifiedAt"] = now_iso
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
                latest_user_msg = messages[-1].content if messages else ""
                try:
                    sys_prompt = _build_memory_system_prompt(latest_user_msg)
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
                        # looping on more tool calls. Without this, llama-3.1
                        # often keeps calling tools and the user sees a
                        # session stuck on "recall_memory ✓" with no answer.
                        # v2.6.3.1: Tell it to be DETAILED so users see the
                        # tool data summarized, not a one-liner.
                        if resp.tool_calls:
                            await ws.send_json({
                                "type": "status", "state": "thinking",
                                "verb": "Composing answer", "stage": "ready",
                            })
                            final = await asyncio.to_thread(
                                client.chat,
                                full_messages + [_Msg(
                                    role="system",
                                    content="You have all the tool results you need. "
                                    "Now write a detailed, helpful answer in the "
                                    "user's language. Summarize the data from the "
                                    "tools (numbers, names, links) into a clear, "
                                    "well-formatted response. Use bullet points or "
                                    "short paragraphs as appropriate. Do NOT call "
                                    "any more tools. Aim for 3-6 sentences or a "
                                    "few bullet points.",
                                )],
                                model=model,
                                temperature=temperature,
                                tools=None,  # no tools — must answer
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
