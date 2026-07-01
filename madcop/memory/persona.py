"""L3 — Persona memory layer.

The persona is a long-form Markdown document that aggregates every
distilled user preference, habit, and communication style observation.
It is stored as ``~/.madcop/memory/persona.md`` so that a human (or
another Agent) can open it in any text editor and immediately see the
full picture of how to communicate with this user.

Persona is built up over time by the :class:`PersonaBuilder`, which
diffs new L1 (semantic) entries against the existing persona and
appends only meaningful additions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .store import MemoryStore


@dataclass
class PersonaTrait:
    """A single observed user trait with provenance."""

    key: str  # stable identifier (e.g. "communication.tone", "tools.prefer_minimax")
    value: str
    confidence: float = 1.0
    source_atom_ids: list[str] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)


class PersonaMemory:
    """L3 persona layer — a single Markdown file aggregating user traits."""

    def __init__(self, store: MemoryStore) -> None:
        self.store = store
        self.persona_path = store.path.parent / "memory" / "persona.md"
        self.persona_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.persona_path.exists():
            self.persona_path.write_text(
                "# User Persona\n\n"
                "_Generated automatically by the PersonaBuilder._\n\n"
                "## Communication Style\n\n"
                "## Tooling Preferences\n\n"
                "## Project Conventions\n\n"
                "## Recurring Goals\n",
                encoding="utf-8",
            )

    def read(self) -> str:
        return self.persona_path.read_text(encoding="utf-8")

    def traits(self) -> list[PersonaTrait]:
        """Parse the current persona.md into structured traits."""
        text = self.read()
        traits: list[PersonaTrait] = []
        current_section = ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                current_section = stripped[3:].strip().lower()
                continue
            if not stripped or stripped.startswith("#") or stripped.startswith(">_"):
                continue
            # "Key: value" or "**Key**: value"
            key_part = stripped
            value_part = ""
            if "**" in stripped:
                # "**Key**: value"
                try:
                    k, v = stripped.split(":", 1)
                    key_part = k.replace("**", "").strip()
                    value_part = v.strip()
                except ValueError:
                    pass
            elif ":" in stripped:
                try:
                    k, v = stripped.split(":", 1)
                    key_part = k.strip()
                    value_part = v.strip()
                except ValueError:
                    pass
            if key_part and value_part:
                traits.append(PersonaTrait(
                    key=f"{current_section}.{key_part}" if current_section else key_part,
                    value=value_part,
                ))
        return traits

    def upsert_trait(self, key: str, value: str,
                      source_atom_ids: Iterable[str] | None = None) -> None:
        """Insert or update a single trait and rewrite persona.md."""
        section, _, item_key = key.rpartition(".")
        if not section:
            section = "General"
            item_key = key

        text = self.read()
        lines = text.splitlines()
        out: list[str] = []
        in_target = False
        replaced = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## "):
                # New section encountered — flush
                if in_target and not replaced:
                    out.append(f"- **{item_key}**: {value}")
                    if source_atom_ids:
                        out.append(f"  _Sources: {', '.join(source_atom_ids)}_")
                    replaced = True
                in_target = (stripped[3:].strip().lower() == section.lower())
                out.append(line)
                continue
            if in_target and not replaced and (
                stripped.startswith(f"**{item_key}**:")
                or stripped.startswith(f"- **{item_key}**:")
                or stripped.startswith(f"{item_key}:")
            ):
                # Replace this line
                out.append(f"- **{item_key}**: {value}")
                if source_atom_ids:
                    out.append(f"  _Sources: {', '.join(source_atom_ids)}_")
                replaced = True
                continue
            out.append(line)
        if in_target and not replaced:
            out.append(f"- **{item_key}**: {value}")
            if source_atom_ids:
                out.append(f"  _Sources: {', '.join(source_atom_ids)}_")
            replaced = True
        if not in_target:
            out.append("")
            out.append(f"## {section}")
            out.append(f"- **{item_key}**: {value}")
            if source_atom_ids:
                out.append(f"  _Sources: {', '.join(source_atom_ids)}_")
        self.persona_path.write_text("\n".join(out) + "\n", encoding="utf-8")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "path": str(self.persona_path),
            "traits": [
                {
                    "key": t.key,
                    "value": t.value,
                    "confidence": t.confidence,
                    "last_updated": t.last_updated,
                }
                for t in self.traits()
            ],
            "raw": self.read(),
        }
