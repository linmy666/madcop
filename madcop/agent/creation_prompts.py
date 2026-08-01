"""Sprint 4 — Prompt templates for the Source-First CreationEngine.

Three prompts drive the search → fetch → outline → write pipeline.
Kept in a dedicated module so they can be tuned independently of the
engine orchestration code.
"""
from __future__ import annotations

# Used to turn a free-form user request into 2-3 search-engine queries.
# The engine asks the LLM for a compact JSON list; if parsing fails it
# falls back to the raw request itself.
SEARCH_QUERY_PROMPT = """\
你是一个研究助手。用户想就下面的主题写一篇详尽、有据可查的文章。

主题请求：
\"\"\"{request}\"\"\"

请把这个主题拆成 2 到 3 条最适合搜索引擎的检索词（中英文均可，优先用与主题最匹配的语言）。
只返回一个 JSON 数组，不要任何解释，例如：
["检索词一", "检索词二", "检索词 three"]

要求：
- 每条检索词 3-6 个词，聚焦、具体、命中核心概念。
- 覆盖主题的不同侧面（例如：概念定义、最新进展、实践方法）。
- 不要泛词（如 "介绍"、"大全"）。
"""


# Given the fetched source material, produce a structured outline.
# The engine parses the numbered list into list[str].
OUTLINE_PROMPT = """\
你是一位资深编辑。根据下面的检索素材，为用户的主题请求拟定一份清晰的文章大纲。

主题请求：
\"\"\"{request}\"\"\"

检索素材：
{sources}

要求：
- 输出一份 Markdown 有序列表（用 `1.` `2.` `3.` …），每项是一节的标题（不超过 20 字）。
- 5 到 8 节，包含：引言/背景 → 核心内容（2-4 节）→ 实践/案例 → 总结。
- 每节标题后可跟一句 ≤15 字的该节要点提示，用 ` — ` 分隔。
- 只输出大纲本身，不要前言、不要 ` ``` ` 围栏。

示例：
1. 什么是 RAG — 检索增强生成的定义与动机
2. 核心架构 — 索引、检索、生成的协作
"""


# Given the outline + sources, write the full article with [n] citations.
# Streamed token-by-token to the user.
WRITE_PROMPT = """\
你是一位严谨的技术作者。请根据大纲和检索素材，撰写一篇结构清晰、有引用的长文。

主题请求：
\"\"\"{request}\"\"\"

大纲：
{outline}

检索素材（编号即引用编号，正文用到对应素材时用 [n] 标注）：
{numbered_sources}

写作要求：
1. 严格按大纲顺序逐节撰写，每节用 `## 标题` 作为二级标题。
2. 语气专业、客观、信息密度高；避免空话套话。
3. 凡用到素材中的事实、数据、观点，在句末用 `[1]` `[2]` 这样的角标标注来源编号；多个来源用 `[1][3]`。
4. 不要逐字照抄素材——要改写、综合、提炼。
5. 全文 800-1500 字（中文计字数）。
6. 文末加一个 `## 参考` 章节，列出用到的引用：`- [n] 标题 — URL`。
7. 直接开始正文，不要写 "好的，我来…" 之类的开场白。
"""
