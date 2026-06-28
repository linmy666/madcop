"""MadCop Skill Forge — auto-forge + LLM-callable skill tools.

Two modes:
  1. Auto-forge (post-conversation): heuristic detection of reusable
     patterns → create SKILL.md.
  2. LLM-callable tools (`forge_skill`, `update_skill`, `list_skills`):
     the main agent can explicitly create / edit / query skills mid-task.

Inspired by Hermes Agent's progressive skill disclosure (SKILL.md
with YAML frontmatter + lazy body load) and the auto-forge pattern
from production agent memory systems.
"""

from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ───────────────────────────────────────────────────────────────────
# SKILL.md frontmatter (Hermes-compatible)
# ───────────────────────────────────────────────────────────────────

DEFAULT_SKILLS_DIR = Path(
    os.environ.get("MADCOP_SKILLS_DIR", "~/.madcop/skills")
).expanduser()

# ───────────────────────────────────────────────────────────────────
# SKILL.md frontmatter (Hermes-compatible)
# ───────────────────────────────────────────────────────────────────

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
    updated_at: str = ""
    source: str = "auto"  # auto | manual | agent
    version: str = "1.0"
    tags: list[str] = field(default_factory=list)


# ───────────────────────────────────────────────────────────────────
# Skill body template (Markdown)
# ───────────────────────────────────────────────────────────────────

SKILL_BODY_TEMPLATE = """# {title}

## When to use
{when}

## How
{how}

## Pitfalls
{pitfalls}

## Examples
{examples}
"""


def _slugify(name: str) -> str:
    """Convert a name to a filesystem-safe slug."""
    s = re.sub(r"[^\w\s-]", "", name.lower())
    return re.sub(r"[\s_-]+", "-", s).strip("-")[:60]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _format_yaml(meta: SkillMeta) -> str:
    triggers_yaml = "\n".join(f"      - {t}" for t in meta.triggers) if meta.triggers else "      []"
    tags_yaml = "\n".join(f"      - {t}" for t in meta.tags) if meta.tags else ""
    tag_block = f"tags:\n{tags_yaml}\n" if tags_yaml else ""
    return (
        "---\n"
        f"name: {meta.name}\n"
        f"description: {meta.description}\n"
        f"triggers:\n{triggers_yaml}\n"
        f"created_at: {meta.created_at}\n"
        f"updated_at: {meta.updated_at}\n"
        f"source: {meta.source}\n"
        f"version: {meta.version}\n"
        f"{tag_block}"
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
    current_list_key: str | None = None
    current_list: list[str] = []

    def flush_list() -> None:
        nonlocal current_list_key, current_list
        if current_list_key and current_list:
            setattr(meta, current_list_key, list(current_list))
        current_list_key = None
        current_list = []

    for raw in yaml_block.split("\n"):
        line = raw.rstrip()
        stripped = line.strip()
        if stripped.startswith("- ") and current_list_key:
            current_list.append(stripped[2:].strip().strip('"').strip("'"))
            continue
        flush_list()
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key in ("triggers", "tags"):
            current_list_key = key
            current_list = []
        elif key == "name":
            meta.name = val
        elif key == "description":
            meta.description = val
        elif key == "source":
            meta.source = val
        elif key == "version":
            meta.version = val
        elif key == "created_at":
            meta.created_at = val
        elif key == "updated_at":
            meta.updated_at = val
    flush_list()
    return meta, body


# ───────────────────────────────────────────────────────────────────
# SkillStore (filesystem)
# ───────────────────────────────────────────────────────────────────

class SkillStore:
    """File-based skill store. Each skill is a directory with SKILL.md."""

    def __init__(self, path: Path | str | None = None):
        self._path = Path(path) if path else DEFAULT_SKILLS_DIR
        self._path.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def list_skills(self) -> list[dict[str, Any]]:
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
                    "tags": meta.tags,
                    "source": meta.source,
                    "version": meta.version,
                    "created_at": meta.created_at,
                    "updated_at": meta.updated_at,
                    "path": str(skill_dir),
                    "body_preview": body[:200],
                })
            except Exception:
                continue
        return skills

    def get_skill(self, name: str) -> dict[str, Any] | None:
        slug = _slugify(name)
        skill_file = self._path / slug / "SKILL.md"
        if not skill_file.exists():
            skill_file = self._path / name / "SKILL.md"
            if not skill_file.exists():
                return None
        text = skill_file.read_text(encoding="utf-8")
        meta, body = _parse_yaml(text)
        return {
            "name": meta.name,
            "description": meta.description,
            "triggers": meta.triggers,
            "tags": meta.tags,
            "source": meta.source,
            "version": meta.version,
            "created_at": meta.created_at,
            "updated_at": meta.updated_at,
            "body": body,
            "path": str(skill_file.parent),
        }

    def create_skill(
        self,
        name: str,
        description: str,
        body: str = "",
        triggers: list[str] | None = None,
        tags: list[str] | None = None,
        source: str = "manual",
    ) -> str:
        slug = _slugify(name)
        skill_dir = self._path / slug
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"

        now = _now_iso()
        meta = SkillMeta(
            name=slug,
            description=description,
            triggers=triggers or [],
            tags=tags or [],
            created_at=now,
            updated_at=now,
            source=source,
        )
        if not body:
            body = SKILL_BODY_TEMPLATE.format(
                title=name,
                when=f"Use this skill when the user asks about {description}.",
                how="(Describe the steps here.)",
                pitfalls="(List common pitfalls.)",
                examples="(Provide usage examples.)",
            )

        content = _format_yaml(meta) + body
        skill_file.write_text(content, encoding="utf-8")
        return str(skill_dir)

    def update_skill(
        self,
        name: str,
        *,
        description: str | None = None,
        body: str | None = None,
        triggers: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> bool:
        """Update an existing skill. Returns True if existed."""
        slug = _slugify(name)
        skill_file = self._path / slug / "SKILL.md"
        if not skill_file.exists():
            skill_file = self._path / name / "SKILL.md"
            if not skill_file.exists():
                return False
        text = skill_file.read_text(encoding="utf-8")
        meta, old_body = _parse_yaml(text)

        if description is not None:
            meta.description = description
        if triggers is not None:
            meta.triggers = triggers
        if tags is not None:
            meta.tags = tags
        meta.updated_at = _now_iso()
        meta.version = f"{float(meta.version) + 0.1:.1f}"

        new_body = body if body is not None else old_body
        content = _format_yaml(meta) + new_body
        skill_file.write_text(content, encoding="utf-8")
        return True

    def delete_skill(self, name: str) -> bool:
        slug = _slugify(name)
        skill_dir = self._path / slug
        if not skill_dir.exists():
            return False
        import shutil
        shutil.rmtree(skill_dir)
        return True

    def search_skills(self, query: str) -> list[dict[str, Any]]:
        query_lower = query.lower()
        results: list[dict[str, Any]] = []
        for skill in self.list_skills():
            haystack = (
                skill.get("description", "").lower()
                + " "
                + " ".join(skill.get("triggers", []))
                + " "
                + " ".join(skill.get("tags", []))
                + " "
                + skill.get("body_preview", "").lower()
            )
            if query_lower in haystack:
                results.append(skill)
        return results


# ───────────────────────────────────────────────────────────────────
# Auto-forge (heuristic, no LLM)
# ───────────────────────────────────────────────────────────────────

def auto_forge_from_conversation(
    store: SkillStore,
    user_message: str,
    assistant_response: str,
    tool_calls: list[dict[str, Any]] | None = None,
) -> str | None:
    """Heuristic: detect 'how-to' patterns and forge a SKILL.md.

    Triggers when user_message matches a how-to pattern AND assistant
    response has numbered steps or a code block.
    """
    how_to_patterns = [
        r"如何.+",
        r"怎么.+",
        r"怎样.+",
        r"how\s+to\s+.+",
        r"how\s+do\s+i\s+.+",
    ]
    is_how_to = any(
        re.search(p, user_message, re.IGNORECASE) for p in how_to_patterns
    )
    has_steps = bool(re.search(r"^\d+\.\s", assistant_response, re.MULTILINE))
    has_code = "```" in assistant_response

    if not (is_how_to and (has_steps or has_code)):
        return None

    title = user_message[:40].strip()
    existing = store.search_skills(title)
    if existing:
        return None  # dedup

    triggers = re.findall(r"[\w\u4e00-\u9fff]{2,}", user_message.lower())[:5]

    # Build a body that captures what worked
    body_lines = [
        f"# {title}",
        "",
        f"## When to use",
        f"User asks: \"{user_message[:80]}\"",
        "",
        "## How",
        "",
    ]
    if tool_calls:
        body_lines.append("Tools used:")
        for tc in tool_calls:
            args = json.dumps(tc.get("args", {}), ensure_ascii=False)[:100]
            body_lines.append(f"- **{tc.get('name', '?')}**: `{args}`")
        body_lines.append("")
    body_lines.append("### Solution outline")
    body_lines.append("")
    body_lines.append("```")
    body_lines.append(assistant_response[:500])
    if len(assistant_response) > 500:
        body_lines.append("...")
    body_lines.append("```")
    body_lines.append("")

    return store.create_skill(
        name=title,
        description=f"Auto-forged from: {user_message[:60]}",
        body="\n".join(body_lines),
        triggers=triggers,
        source="auto",
    )


# ───────────────────────────────────────────────────────────────────
# Module-level singleton
# ───────────────────────────────────────────────────────────────────

_skill_store: SkillStore | None = None


def get_skill_store() -> SkillStore:
    global _skill_store
    if _skill_store is None:
        _skill_store = SkillStore()
    return _skill_store


def reset_skill_store(store: SkillStore | None) -> None:
    global _skill_store
    _skill_store = store


# ───────────────────────────────────────────────────────────────────
# LLM-callable tool definitions
#
# These are pure data (parameter schemas + handler functions). The
# server/registry layer wraps them into Tool instances — keeping
# skill_forge free of dependencies on madcop.tools.
# ───────────────────────────────────────────────────────────────────

FORGE_SKILL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Skill name (kebab-case recommended).",
        },
        "description": {
            "type": "string",
            "description": "One-line description of when to use this skill.",
        },
        "body": {
            "type": "string",
            "description": "Markdown body (steps, code, pitfalls).",
        },
        "triggers": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Optional list of trigger keywords for retrieval.",
        },
    },
    "required": ["name", "description", "body"],
}

LIST_SKILLS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "Optional search term to filter by trigger / description.",
        },
    },
}

READ_SKILL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {
            "type": "string",
            "description": "Skill name to load.",
        },
    },
    "required": ["name"],
}


def execute_forge_skill(
    name: str,
    description: str,
    body: str,
    triggers: list[str] | None = None,
    store: SkillStore | None = None,
) -> str:
    """Pure function: persist a new skill. Returns the new path
    or updates existing."""
    s = store or get_skill_store()
    if not name.strip() or not description.strip():
        return "Error: name and description are required."
    if s.get_skill(name):
        s.update_skill(name, description=description, body=body, triggers=triggers or [])
        return f"Updated existing skill: {name}"
    path = s.create_skill(name, description, body, triggers or [], source="agent")
    return f"Forged new skill '{name}' at {path}"


def execute_list_skills(
    query: str = "",
    store: SkillStore | None = None,
) -> str:
    s = store or get_skill_store()
    skills = s.search_skills(query) if query else s.list_skills()
    if not skills:
        return "No skills found."
    lines = [f"Found {len(skills)} skill(s):"]
    for sk in skills[:20]:
        lines.append(f"- [{sk.get('source', '?')}] {sk['name']}: {sk['description'][:60]}")
    return "\n".join(lines)


def execute_read_skill(
    name: str,
    store: SkillStore | None = None,
) -> str:
    s = store or get_skill_store()
    skill = s.get_skill(name)
    if not skill:
        return f"Error: skill '{name}' not found."
    return f"# {skill['name']}\n\n{skill['body']}"


__all__ = [
    "SkillMeta",
    "SkillStore",
    "auto_forge_from_conversation",
    "execute_forge_skill",
    "execute_list_skills",
    "execute_read_skill",
    "FORGE_SKILL_SCHEMA",
    "LIST_SKILLS_SCHEMA",
    "READ_SKILL_SCHEMA",
    "get_skill_store",
    "reset_skill_store",
    "DEFAULT_SKILLS_DIR",
    "SKILL_BODY_TEMPLATE",
]
