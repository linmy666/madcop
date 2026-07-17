"""SKILL auto-distillation — detect teach-me / how-to patterns in chat and
persist the assistant's response as a SKILL.md file under ~/.madcop/skills/.

The system also indexes existing skills and exposes them in the system prompt,
so the next time a similar question comes in, the LLM can leverage the
learned skill.

This is the MadCop Agent equivalent of Hermes's auto-SKILL-distill.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

# Where user skills live
USER_SKILLS_DIR = Path.home() / ".madcop" / "skills"

# Patterns that signal "the user is teaching me / asking for reusable knowledge"
_TEACH_PATTERNS_ZH = [
    # 教我怎么部署 X / 教我如何写 X
    re.compile(r"教我(?:怎么|如何)(.+?)(?:[?？。!！]|$)", re.UNICODE),
    # 教我 X 怎么做
    re.compile(r"教我(.{2,40}?)(?:怎么|如何|方法|步骤|做法)", re.UNICODE),
    # 怎么部署 X / 如何实现 X
    re.compile(
        r"(?:怎么|如何)(?:做|写|实现|处理|使用|部署|配置|搭建|开发)(.+?)(?:[?？。!！]|$)",
        re.UNICODE,
    ),
    re.compile(r"我想(?:学|了解|知道)(.+?)(?:[?？。!！]|$)", re.UNICODE),
    re.compile(r"(.+?)的(?:最佳实践|方法|步骤|流程|模板|教程|示例)是什么", re.UNICODE),
]
_TEACH_PATTERNS_EN = [
    re.compile(r"teach me (?:how to )?(.+)", re.IGNORECASE),
    re.compile(
        r"how (?:do|should) (?:I |we )?(?:do|use|implement|deploy|configure|set up)\s+(.+)",
        re.IGNORECASE,
    ),
    re.compile(r"best (?:practice|way) (?:for|to) (.+)", re.IGNORECASE),
    re.compile(r"(.+?) tutorial", re.IGNORECASE),
]


def _slugify_topic(topic: str, max_len: int = 60) -> str:
    """Turn a free-form topic into a filesystem-safe skill name."""
    # Remove punctuation, keep CJK + ASCII alphanumerics + hyphens
    s = re.sub(r"[^\w\u4e00-\u9fff\-]+", "-", topic.strip().lower())
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:max_len] or "untitled-skill"


def _looks_like_teaching_request(text: str) -> str | None:
    """Return the detected topic if the message looks like a teaching request."""
    text = text.strip()
    for pat in _TEACH_PATTERNS_ZH + _TEACH_PATTERNS_EN:
        m = pat.search(text)
        if not m:
            continue
        try:
            topic = (m.group(1) or "").strip()
        except IndexError:
            topic = text[:60].strip()
        # Drop trailing punctuation / whitespace
        topic = re.sub(r"[?？。!！\s]+$", "", topic).strip(" .,;:：")
        if 2 <= len(topic) <= 80:
            return topic
    return None


def _build_skill_markdown(topic: str, user_query: str, assistant_response: str) -> str:
    """Format a SKILL.md from a teach-me exchange."""
    safe_topic = topic.strip() or "Skill"
    return f"""# {safe_topic}

> Auto-distilled from chat on {time.strftime('%Y-%m-%d', time.gmtime())}.
> This SKILL.md was created automatically by MadCop Agent when the user asked
> for guidance on this topic. Edit freely.

## When to use

Use this skill when the user asks about: **{safe_topic}**.

## Question that triggered this

> {user_query[:300]}

## Approach

{assistant_response.strip()[:3000]}

## Notes

- Source: MadCop Agent auto-distill
- ID: {uuid.uuid4().hex[:12]}
- Created: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
"""


def distill_skill_from_exchange(
    user_query: str,
    assistant_response: str,
) -> str | None:
    """If the user query looks like a teach-me request, persist the
    assistant's response as a SKILL.md and return its name. Otherwise None.

    The skill is also added to the L1 Semantic memory index so the retriever
    can find it on the next turn.
    """
    topic = _looks_like_teaching_request(user_query)
    if not topic:
        return None
    if not assistant_response or len(assistant_response.strip()) < 50:
        return None

    USER_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    skill_name = _slugify_topic(topic)
    # If a skill with this name already exists, append a numeric suffix
    target = USER_SKILLS_DIR / f"{skill_name}.md"
    counter = 2
    while target.exists():
        target = USER_SKILLS_DIR / f"{skill_name}-{counter}.md"
        counter += 1
    skill_name = target.stem

    content = _build_skill_markdown(topic, user_query, assistant_response)
    target.write_text(content, encoding="utf-8")

    # Also register in L1 Semantic memory so retriever can find it
    try:
        from madcop.server.app import get_memory_store
        from madcop.memory import SemanticMemory
        store = get_memory_store()
        sem = SemanticMemory(store)
        sem.add(
            subject="skill",
            predicate="teaches",
            object=topic,
            tags=("auto-distilled", "skill", "user-taught"),
        )
    except Exception:
        pass

    return skill_name


def list_user_skills() -> list[dict[str, Any]]:
    """List all user-created skills (SKILL.md files in ~/.madcop/skills/)."""
    if not USER_SKILLS_DIR.exists():
        return []
    skills: list[dict[str, Any]] = []
    for f in sorted(USER_SKILLS_DIR.glob("*.md")):
        content = f.read_text(errors="ignore")
        # Extract title from first `# heading`
        title = f.stem
        if content.startswith("# "):
            title = content.split("\n", 1)[0][2:].strip()
        # First non-empty paragraph as description
        description = ""
        in_body = False
        for line in content.splitlines():
            if line.startswith("## "):
                break
            if in_body and line.strip():
                description = line.strip()
                break
            if line.strip() and not line.startswith("#"):
                in_body = True
        skills.append({
            "name": f.stem,
            "displayName": title,
            "description": description or f"Auto-distilled skill for: {title}",
            "source": "user",
            "userInvocable": True,
            "contentLength": len(content),
            "hasDirectory": False,
            "path": str(f),
        })
    return skills


def read_skill_detail(name: str, source: str = "user") -> dict[str, Any] | None:
    """Read a skill's full content + meta."""
    # User skills
    if source in ("user", "project"):
        target = USER_SKILLS_DIR / f"{name}.md"
        if target.exists():
            content = target.read_text(errors="ignore")
            title = name
            if content.startswith("# "):
                title = content.split("\n", 1)[0][2:].strip()
            return {
                "meta": {
                    "name": name,
                    "displayName": title,
                    "description": content[:200],
                    "source": source,
                    "userInvocable": True,
                    "contentLength": len(content),
                    "hasDirectory": False,
                },
                "tree": [{
                    "name": f"{name}.md",
                    "path": str(target),
                    "type": "file",
                }],
                "files": [{
                    "path": str(target),
                    "content": content,
                    "language": "markdown",
                    "isEntry": True,
                }],
                "skillRoot": str(USER_SKILLS_DIR),
            }
    return None


def force_distill_skill(topic: str, user_query: str,
                         assistant_response: str) -> str | None:
    """Bypass the teach-me pattern detector and explicitly persist
    a SKILL.md from a (user_query, assistant_response) pair.
    Returns the skill name on success, None on failure.

    Public API for the rest of the app.
    """
    if not user_query or not assistant_response:
        return None
    base = _slugify_topic(topic or user_query)
    USER_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    target = USER_SKILLS_DIR / f"{base}.md"
    counter = 2
    while target.exists():
        target = USER_SKILLS_DIR / f"{base}-{counter}.md"
        counter += 1
    content = _build_skill_markdown(topic or user_query, user_query,
                                     assistant_response)
    target.write_text(content, encoding="utf-8")
    # Register in memory index (deferred import to avoid circular deps)
    try:
        from madcop.server.app import get_memory_store
        from madcop.memory import SemanticMemory
        store = get_memory_store()
        sem = SemanticMemory(store)
        sem.add(
            subject="skill",
            predicate="teaches",
            object=topic or user_query,
            tags=("auto-distilled", "skill", "user-taught"),
        )
    except Exception:
        pass
    return target.stem
