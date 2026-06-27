"""Skill auto-sediment system — auto-create SKILL.md from conversations.

Inspired by Hermes Agent's skill system. After a conversation produces
a useful pattern (user asked X, assistant did Y, it worked), the system
automatically creates a SKILL.md file so future conversations can reuse
the pattern.

SKILL.md format (Hermes-compatible):
    ---
    name: skill-name
    description: One line description
    triggers:
      - keyword1
      - keyword2
    created_at: 2026-06-27T12:00:00
    source: auto  # auto | manual
    ---

    # Skill Title

    ## When to use
    ...

    ## Steps
    1. ...

    ## Pitfalls
    - ...
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_SKILLS_DIR = Path(
    os.environ.get("MADCOP_SKILLS_DIR", "~/.madcop/skills")
).expanduser()


@dataclass
class SkillMeta:
    """YAML frontmatter metadata for a SKILL.md."""
    name: str
    description: str = ""
    triggers: list[str] = field(default_factory=list)
    created_at: str = ""
    source: str = "auto"  # auto | manual
    version: str = "1.0"


def _slugify(name: str) -> str:
    """Convert a name to a filesystem-safe slug."""
    s = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-")[:60]


def _format_yaml(meta: SkillMeta) -> str:
    """Format SkillMeta as YAML frontmatter string."""
    triggers_yaml = "\n".join(f"      - {t}" for t in meta.triggers) if meta.triggers else "      []"
    return (
        "---\n"
        f"name: {meta.name}\n"
        f"description: {meta.description}\n"
        f"triggers:\n{triggers_yaml}\n"
        f"created_at: {meta.created_at}\n"
        f"source: {meta.source}\n"
        f"version: {meta.version}\n"
        "---\n\n"
    )


def _parse_yaml(text: str) -> tuple[SkillMeta, str]:
    """Parse YAML frontmatter from SKILL.md text."""
    if not text.startswith("---"):
        return SkillMeta(name="unknown"), text
    end = text.index("---", 3)
    yaml_block = text[3:end].strip()
    body = text[end + 3:].strip()

    meta = SkillMeta(name="unknown")
    for line in yaml_block.split("\n"):
        line = line.strip()
        if ":" in line and not line.startswith("-"):
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if key == "name":
                meta.name = val
            elif key == "description":
                meta.description = val
            elif key == "source":
                meta.source = val
            elif key == "version":
                meta.version = val
            elif key == "created_at":
                meta.created_at = val
        elif line.startswith("-"):
            meta.triggers.append(line.lstrip("- ").strip())

    return meta, body


class SkillStore:
    """File-based skill store. Each skill is a directory with SKILL.md."""

    def __init__(self, path: Path | str | None = None):
        self._path = Path(path) if path else DEFAULT_SKILLS_DIR
        self._path.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def list_skills(self) -> list[dict[str, Any]]:
        """List all skills as metadata dicts."""
        skills: list[dict[str, Any]] = []
        for skill_dir in sorted(self._path.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                continue
            try:
                text = skill_file.read_text(encoding="utf-8")
                meta, body = _parse_yaml(text)
                skills.append({
                    "name": meta.name,
                    "description": meta.description,
                    "triggers": meta.triggers,
                    "source": meta.source,
                    "created_at": meta.created_at,
                    "path": str(skill_dir),
                    "body_preview": body[:200],
                })
            except Exception:
                continue
        return skills

    def get_skill(self, name: str) -> dict[str, Any] | None:
        """Get a single skill by name."""
        slug = _slugify(name)
        skill_file = self._path / slug / "SKILL.md"
        if not skill_file.exists():
            # Try direct name match
            skill_file = self._path / name / "SKILL.md"
            if not skill_file.exists():
                return None
        text = skill_file.read_text(encoding="utf-8")
        meta, body = _parse_yaml(text)
        return {
            "name": meta.name,
            "description": meta.description,
            "triggers": meta.triggers,
            "source": meta.source,
            "created_at": meta.created_at,
            "body": body,
            "path": str(skill_file.parent),
        }

    def create_skill(
        self,
        name: str,
        description: str,
        body: str,
        triggers: list[str] | None = None,
        source: str = "auto",
    ) -> str:
        """Create or update a SKILL.md. Returns the skill path."""
        slug = _slugify(name)
        skill_dir = self._path / slug
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"

        meta = SkillMeta(
            name=slug,
            description=description,
            triggers=triggers or [],
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S"),
            source=source,
        )

        content = _format_yaml(meta) + body
        skill_file.write_text(content, encoding="utf-8")
        return str(skill_dir)

    def delete_skill(self, name: str) -> bool:
        """Delete a skill directory. Returns True if existed."""
        slug = _slugify(name)
        skill_dir = self._path / slug
        if not skill_dir.exists():
            return False
        import shutil
        shutil.rmtree(skill_dir)
        return True

    def search_skills(self, query: str) -> list[dict[str, Any]]:
        """Search skills by trigger keywords or description."""
        query_lower = query.lower()
        results: list[dict[str, Any]] = []
        for skill in self.list_skills():
            haystack = (
                skill.get("description", "").lower()
                + " "
                + " ".join(skill.get("triggers", []))
                + " "
                + skill.get("body_preview", "").lower()
            )
            if query_lower in haystack:
                results.append(skill)
        return results


def auto_create_skill_from_conversation(
    store: SkillStore,
    user_message: str,
    assistant_response: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> str | None:
    """Heuristic: detect if a conversation has a reusable pattern.

    Returns skill path if created, None if no pattern detected.
    Currently detects:
    - User asks a how-to question → assistant gives step-by-step answer
    - User asks for code → assistant writes code with explanation
    """
    # Heuristic 1: user asks "如何" / "怎么" / "how to" → step-by-step answer
    how_to_patterns = [
        r"如何.+",
        r"怎么.+",
        r"怎样.+",
        r"how\s+to\s+.+",
        r"how\s+do\s+i\s+.+",
    ]
    is_how_to = any(re.search(p, user_message, re.IGNORECASE) for p in how_to_patterns)

    # Heuristic 2: assistant answer has numbered steps or code blocks
    has_steps = bool(re.search(r"^\d+\.\s", assistant_response, re.MULTILINE))
    has_code = "```" in assistant_response

    if not (is_how_to and (has_steps or has_code)):
        return None

    # Don't duplicate if a similar skill already exists
    title = user_message[:40].strip()
    existing = store.search_skills(title)
    if existing:
        return None  # already have a similar skill

    # Build skill body
    triggers = []
    # Extract keywords from user message
    keywords = re.findall(r"[\w\u4e00-\u9fff]{2,}", user_message.lower())
    triggers = keywords[:5]

    # Build body
    body_parts = [
        f"# {title}\n",
        "## When to use",
        f"User asks: \"{user_message[:80]}\"\n",
        "## Solution",
    ]

    if tool_calls:
        body_parts.append("Tools used:")
        for tc in tool_calls:
            body_parts.append(f"- **{tc.get('name', 'unknown')}**: {json.dumps(tc.get('args', {}), ensure_ascii=False)[:100]}")
        body_parts.append("")

    # Take the first 500 chars of the response as the answer template
    body_parts.append("```")
    body_parts.append(assistant_response[:500])
    if len(assistant_response) > 500:
        body_parts.append("...")
    body_parts.append("```\n")

    body = "\n".join(body_parts)

    return store.create_skill(
        name=title,
        description=f"Auto-extracted from: {user_message[:60]}",
        body=body,
        triggers=triggers,
        source="auto",
    )


# Module-level singleton
_skill_store: SkillStore | None = None


def get_skill_store() -> SkillStore:
    global _skill_store
    if _skill_store is None:
        _skill_store = SkillStore()
    return _skill_store


def reset_skill_store(store: SkillStore | None) -> None:
    global _skill_store
    _skill_store = store


__all__ = [
    "SkillMeta",
    "SkillStore",
    "DEFAULT_SKILLS_DIR",
    "auto_create_skill_from_conversation",
    "get_skill_store",
    "reset_skill_store",
]
