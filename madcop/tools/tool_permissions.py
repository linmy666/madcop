"""Tool permissions — opencode-style rule evaluation.

Pattern + action rules with wildcards, persisted to disk, default
action is 'ask' (mirrors opencode's permission/index.ts).

Sister to tools/permissions.py (which handles computer-use action
levels). This module covers all registered tools uniformly.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

# Permission verdicts — string union of opencode's three actions.
ALLOW = "allow"
DENY = "deny"
ASK = "ask"

_ALLOWED_ACTIONS = (ALLOW, DENY, ASK)


@dataclass(frozen=True)
class Rule:
    """A single permission rule.

    `pattern` is a shell-style glob matched against the tool name
    (e.g. 'write_file', 'bash', 'web_*'). '*' matches any string.
    Evaluation order: most-specific match wins; ties go to the later
    rule in the list (mirrors opencode's `findLast` behavior).
    """
    pattern: str
    action: str

    def __post_init__(self) -> None:
        if self.action not in _ALLOWED_ACTIONS:
            raise ValueError(
                f"action must be one of {_ALLOWED_ACTIONS}, got {self.action!r}"
            )


def _glob_to_re(pattern: str) -> re.Pattern[str]:
    """Convert a shell-style glob ('*', '?') to a compiled regex.

    We use the same simple conversion everywhere so wildcard semantics
    are consistent across the codebase. '**' is just a doubled '*' for
    compatibility with opencode's `Wildcard.match`.
    """
    out = []
    for ch in pattern:
        if ch == "*":
            out.append(".*")
        elif ch == "?":
            out.append(".")
        else:
            out.append(re.escape(ch))
    return re.compile(f"^{''.join(out)}$")


def evaluate(tools_pattern: str, rules: Iterable[Rule]) -> str:
    """Return the action for the given tool under the given rules.

    Mirrors opencode's `findLast` semantics: the LAST matching rule
    wins. Default if no rule matches is ASK (request permission from
    the user, like opencode's default).
    """
    last_match: str | None = None
    for rule in rules:
        if _glob_to_re(rule.pattern).match(tools_pattern):
            last_match = rule.action
    return last_match or ASK


# ── Persisted ruleset ─────────────────────────────────────────────── #

# One file per workspace-ish global. Tools don't usually have an
# installed state per workspace, so we use ~/.madcop directly.
_RULES_FILE = Path.home() / ".madcop" / "tool_permissions.json"

# Built-in defaults (mirrors opencode's `permission/index.ts`):
# 'bash' requires explicit ASK, 'read_*' / 'web_*' are allowed,
# write/edit/file are ASK unless an explicit allow rule exists.
DEFAULT_RULES: list[Rule] = [
    Rule("bash", ASK),
    Rule("write_*", ASK),
    Rule("edit_*", ASK),
    Rule("read_*", ALLOW),
    Rule("web_*", ASK),
]


def load_rules() -> list[Rule]:
    """Load rules from disk, falling back to DEFAULT_RULES.

    Persisted format is a JSON array of {pattern, action} dicts.
    On any parse error, log and use defaults — the user can
    re-customize via the settings UI without losing safety.
    """
    try:
        raw = json.loads(_RULES_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return list(DEFAULT_RULES)
    if not isinstance(raw, list):
        return list(DEFAULT_RULES)
    out: list[Rule] = []
    for item in raw:
        if not isinstance(item, dict) or "pattern" not in item or "action" not in item:
            continue
        try:
            out.append(Rule(pattern=item["pattern"], action=item["action"]))
        except ValueError:
            # Skip the bad rule but keep loading the rest.
            continue
    return out or list(DEFAULT_RULES)


def save_rules(rules: list[Rule]) -> None:
    _RULES_FILE.parent.mkdir(parents=True, exist_ok=True)
    payload = [{"pattern": r.pattern, "action": r.action} for r in rules]
    _RULES_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def check_tool(tool_name: str, rules: list[Rule] | None = None) -> str:
    """Decide whether `tool_name` is allowed/denied/asks-for-allow.

    Returns one of ALLOW / DENY / ASK. The caller is expected to
    short-circuit: DENY → raise a ToolPermissionError; ASK → surface
    an ask-permission event back to the user and wait; ALLOW → run.
    """
    return evaluate(tool_name, rules if rules is not None else load_rules())


# ── Tool-side guard ─────────────────────────────────────────────────── #

class ToolPermissionError(RuntimeError):
    """Raised when a tool is denied by the rule engine. The ReAct
    engine catches this and feeds it back to the LLM as the
    Observation so the model can pick a different tool."""

    def __init__(self, tool_name: str, pattern: str, action: str) -> None:
        super().__init__(
            f"Tool '{tool_name}' denied by permissions rule '{pattern}' "
            f"(action={action})"
        )
        self.tool_name = tool_name
        self.pattern = pattern
        self.action = action
