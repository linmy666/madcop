"""v1.2.0 — minimal Markdown-with-frontmatter parser for PageDB rows.

The brain stores pages as slug + type + title + compiled_truth + timeline.
In practice the agent hands us a Markdown-ish blob with a YAML
frontmatter block, the body, and a chronological `## Timeline` section.
We parse that here into the page fields so `PageDB.save()` can store them
without forcing every caller to pre-extract.

Why our own parser (vs PyYAML)?
- Avoids a heavy dependency on a single field (frontmatter only).
- Frontmatter here is flat: title, type, tags, layers, sources. PyYAML
  loads lists fine but pulls `python-dateutil` and friends along.
- We only need `: ` key/value and a flat `[a, b]` list for `tags`. We
  intentionally don't try to be a complete YAML parser — if a user
  passes complex YAML, they should pre-load and pass us a dict via
  `PageDB.save(frontmatter={...})`.

Output shape
------------
  Page.parse(raw) -> ParseResult
  ParseResult fields:
    slug, title, type (str|None, must be in Page.TYPES),
    frontmatter (dict), compiled_truth (str), timeline (str).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# A declaration line `<!--- madcop: slug = NAME --->` allowed near the top.
# The value is a slug, which can include dashes.
# We match the *closing* `--->` first, then the body, then the opening `<!---`.
# That keeps us from getting confused by greedy `<!+` eating too few `<!`.
SLUG_COMMENT_RE = re.compile(
    r"<!--+\s*madcop\s*:\s*slug\s*=\s*([a-z0-9][a-z0-9_-]*)\s*--+>",
    re.IGNORECASE,
)

# `## Timeline` (heading level 2) splits body / timeline section.
TIMELINE_HDR_RE = re.compile(
    r"^#{2,}\s+timeline\s*$", re.IGNORECASE | re.MULTILINE
)

# Frontmatter fence: `---` on its own line, body, then closing `---`.
FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)

# Tag-like inline slug: `#person/alice` or `#alice`.
TAG_INLINE_RE = re.compile(r"#([a-z0-9][a-z0-9_-]{0,63})(?:/([a-z0-9][a-z0-9_-]{0,63}))?",
                          re.IGNORECASE)

# Page-level types.
VALID_TYPES = frozenset({"person", "project", "concept", "skill", "event"})

# Slug validity: lowercase alnum + dash/underscore, 1-128 chars.
# We disallow leading/trailing `-` to keep slugs friendly as filenames.
SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,126}[a-z0-9])?$")


@dataclass
class ParseResult:
    """The fields PageDB.save() needs extracted from raw Markdown."""
    slug: str = ""
    title: str = ""
    type: str | None = None
    frontmatter: dict[str, Any] = field(default_factory=dict)
    compiled_truth: str = ""
    timeline: str = ""

    def to_kwargs(self) -> dict[str, Any]:
        """Decompose into keyword args for PageDB.save."""
        return {
            "slug": self.slug,
            "title": self.title,
            "page_type": self.type,
            "frontmatter": self.frontmatter,
            "compiled_truth": self.compiled_truth,
            "timeline": self.timeline,
        }


def _parse_frontmatter(block: str) -> dict[str, Any]:
    """Parse a flat YAML-ish frontmatter into a dict.

    Supports:
      key: value
      key: "quoted value"
      key: [a, b, c]      # inline list
      key: [a, b, ]        # inline list, trailing comma ok
    """
    out: dict[str, Any] = {}
    for raw in block.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if not value:
            out[key] = True
            continue
        # Quoted string.
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            out[key] = value[1:-1]
            continue
        # Inline list `[a, b]`.
        if value.startswith("[") and value.endswith("]"):
            items = [it.strip() for it in value[1:-1].split(",")]
            items = [it for it in items if it]  # drop empties
            out[key] = items
            continue
        # Truthy/falsy literal.
        if value.lower() == "true":
            out[key] = True
            continue
        if value.lower() == "false":
            out[key] = False
            continue
        if value.lower() in ("null", "~"):
            out[key] = None
            continue
        if value.isdigit():
            out[key] = int(value)
            continue
        # Strip inline comment.
        if " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        out[key] = value
    return out


def _slug_declaration(raw: str) -> tuple[str, str]:
    """Return (slug_from_comment, raw_without_comment) if the optional
    `<!--- madcop: slug = NAME --->` declaration is present at the top."""
    m = SLUG_COMMENT_RE.search(raw[:256])
    if not m:
        return "", raw
    slug = m.group(1).strip().lower()
    return slug, raw.replace(m.group(0), "", 1).lstrip("\n")


def _split_body_timeline(body: str) -> tuple[str, str]:
    """Split body into (compiled_truth, timeline) at `## Timeline`.

    Returns the body unchanged if no Timeline heading found.
    """
    m = TIMELINE_HDR_RE.search(body)
    if not m:
        return body, ""
    head = body[: m.start()].rstrip()
    tail = body[m.end():].lstrip("\n")
    return head, tail


def _strip_slug_comments(text: str) -> str:
    """Remove leftover `<!--- madcop: slug = NAME --->` declarations.

    The comment is usually consumed by `_slug_declaration` but a user
    might typo a return value, leave the header in the body, or feed
    text we couldn't match. Keeping the declaration visible in
    compiled_truth is noise, so we strip the line entirely.
    """
    lines = []
    for line in text.splitlines():
        if SLUG_COMMENT_RE.search(line):
            continue
        lines.append(line)
    return "\n".join(lines).lstrip("\n")


def _fallback_title(compiled_truth: str) -> str:
    """Pick a fallback title: first H1/H2 line, else first non-empty line."""
    for line in compiled_truth.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            # Strip leading `#`s.
            return s.lstrip("#").strip()
        return s[:120]
    return ""


def _fallback_slug(compiled_truth: str, title: str, type_: str | None) -> str:
    """Generate a candidate slug from title/type if none was provided."""
    base = title.lower() if title else ""
    if base:
        base = re.sub(r"[^a-z0-9]+", "-", base).strip("-")
        if base and SLUG_RE.match(base):
            return base[:64]
    if type_ and SLUG_RE.match(type_):
        return type_
    return ""


def parse(raw: str) -> ParseResult:
    """Parse a raw markdown blob into a `ParseResult`.

    Field resolution order:
      - `slug`: comment-declaration → frontmatter.slug → derived from title.
      - `type`:  frontmatter.type → None.
      - `title`:  frontmatter.title → `# heading` in compiled_truth → empty.
    """
    if not isinstance(raw, str):
        raise TypeError("raw must be a str")

    slug_decl, text = _slug_declaration(raw)

    fm: dict[str, Any] = {}
    m = FRONTMATTER_RE.match(text)
    if m:
        fm = _parse_frontmatter(m.group(1))
        body = m.group(2)
    else:
        body = text

    body = body.lstrip("\n").rstrip()
    compiled, timeline = _split_body_timeline(_strip_slug_comments(body))

    # Resolve title before slug, so fallback-slug derivation uses it.
    title = str(fm.get("title") or "") or _fallback_title(compiled)
    type_ = fm.get("type")
    if type_ is not None:
        type_ = str(type_).lower()
        if type_ not in VALID_TYPES:
            # Don't raise: keep None so caller can fail noisily with type info.
            type_ = None

    # Resolve slug: explicit comment wins, then frontmatter.slug, then
    # fall back to (slugify(title) | type_). If none of them match, empty.
    candidates: list[str] = []
    if slug_decl:
        candidates.append(slug_decl.lower())
    if fm.get("slug"):
        candidates.append(str(fm.get("slug")).lower())
    derived = _fallback_slug(compiled, title, type_)
    if derived:
        candidates.append(derived)
    slug = ""
    for cand in candidates:
        if SLUG_RE.match(cand):
            slug = cand[:128]
            break

    return ParseResult(
        slug=slug,
        title=title,
        type=type_,
        frontmatter=fm,
        compiled_truth=compiled.strip(),
        timeline=timeline.strip(),
    )


def extract_inline_tags(raw: str) -> list[str]:
    """Walk the raw text and extract inline `#tag` / `#type/tag` markers.

    Useful when transitions happen informally inside a note — gives the
    caller a chance to chain them into `tags` after a parse.
    """
    seen: list[str] = []
    for m in TAG_INLINE_RE.finditer(raw):
        tag = m.group(2) or m.group(1)
        if tag.lower() not in (s.lower() for s in seen):
            seen.append(tag)
    return seen


__all__ = [
    "ParseResult",
    "VALID_TYPES",
    "parse",
    "extract_inline_tags",
]
