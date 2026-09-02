"""Executable-command policy — Codex exec_policy, config-file form.

Codex gates shell commands through a compiled policy DSL (execpolicy
crate, .rules files). MadCop's equivalent is a user-editable JSON file:

    ~/.madcop/exec_policy.json
    {
      "rules": [
        {"id": "no-rm-rf", "pattern": "\\brm\\s+-rf?[\\s/]",
         "action": "deny", "reason": "rm -rf 不可逆"},
        {"id": "git-push", "pattern": "\\bgit\\s+push\\b",
         "action": "warn", "reason": "推送外部仓库前请确认"}
      ]
    }

Semantics (first matching rule wins, unmatched commands pass through —
HITL gating by danger_level still applies on top):

    deny  → the call is vetoed with a clear error (SafetyHook)
    warn  → the call runs, but a warning observation is appended so the
            model knows which rule it tripped
    allow → explicit no-op (documents intent)

The file is hot-reloaded on mtime change — users edit it while the
server runs and the next tool call sees the new rules, no restart.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

POLICY_FILE = Path(
    os.environ.get("MADCOP_EXEC_POLICY", str(Path.home() / ".madcop" / "exec_policy.json"))
)

# Seed rules — the exact patterns SafetyHook used to hardcode. Written
# to the policy file on first load so users can edit/extend from a
# working baseline instead of authoring regex from scratch.
DEFAULT_RULES: list[dict] = [
    {"id": "no-rm-rf", "pattern": r"\brm\s+-rf?[\s/]",
     "action": "deny", "reason": "rm -rf 递归删除不可逆"},
    {"id": "no-mkfs", "pattern": r"\bmkfs(\.[a-z0-9]+)?\b",
     "action": "deny", "reason": "格式化磁盘"},
    {"id": "no-dd-disk", "pattern": r"\bdd\s+if=.+of=/dev/(sd|nvme|hd)",
     "action": "deny", "reason": "裸写磁盘设备"},
    {"id": "no-shutdown", "pattern": r"\b(shutdown|reboot|halt)\b",
     "action": "deny", "reason": "关机/重启"},
    {"id": "no-curl-sh", "pattern": r"\bcurl[^|]*\|\s*(bash|sh|zsh)\b",
     "action": "deny", "reason": "下载即执行（pipe to shell）"},
    {"id": "no-fork-bomb", "pattern": r":\(\)\s*\{\s*:\|:&\s*\};:",
     "action": "deny", "reason": "fork bomb"},
    {"id": "warn-sudo", "pattern": r"\bsudo\b",
     "action": "warn", "reason": "sudo 提权命令，请确认必要性"},
    {"id": "warn-git-push", "pattern": r"\bgit\s+push\b",
     "action": "warn", "reason": "推送到远端仓库前请确认"},
]

_ACTIONS = {"allow", "warn", "deny"}


@dataclass
class PolicyDecision:
    action: str        # allow | warn | deny
    rule_id: str = ""
    reason: str = ""
    command: str = ""


class ExecPolicy:
    """Compiled rule list + matcher."""

    def __init__(self, rules: list[dict], source: str = "default"):
        self.source = source
        self.rules: list[dict] = []
        self._res: list[tuple[re.Pattern, dict]] = []
        for r in rules or []:
            try:
                pat = re.compile(str(r.get("pattern", "")), re.IGNORECASE)
                action = str(r.get("action", "warn")).lower()
                if action not in _ACTIONS:
                    action = "warn"
                rule = {"id": str(r.get("id", f"rule-{len(self.rules)}")),
                        "pattern": str(r.get("pattern", "")),
                        "action": action,
                        "reason": str(r.get("reason", ""))}
                self.rules.append(rule)
                self._res.append((pat, rule))
            except re.error as e:
                logger.warning("[exec_policy] bad pattern %r skipped: %s",
                               r.get("pattern"), e)

    def check(self, command: str) -> PolicyDecision:
        cmd = command or ""
        for pat, rule in self._res:
            if pat.search(cmd):
                return PolicyDecision(action=rule["action"], rule_id=rule["id"],
                                      reason=rule["reason"], command=cmd)
        return PolicyDecision(action="allow", command=cmd)


_lock = threading.Lock()
_policy: ExecPolicy | None = None
_policy_mtime: float = -1.0
_policy_path: Path | None = None


def _read_rules(path: Path) -> tuple[list[dict], bool]:
    """Read the policy file; seed it with defaults when missing.

    Returns (rules, seeded). A corrupt file falls back to the built-in
    defaults (never brick bash because of a typo'd regex)."""
    try:
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(
                {"_doc": "MadCop 命令策略。rules 按顺序匹配（先命中先生效）。"
                         "action: deny=拒绝 / warn=放行但警告 / allow=放行。"
                         "pattern 为不区分大小写的正则。",
                 "rules": DEFAULT_RULES},
                ensure_ascii=False, indent=2))
            return list(DEFAULT_RULES), True
        data = json.loads(path.read_text() or "{}")
        rules = data.get("rules")
        if not isinstance(rules, list):
            return list(DEFAULT_RULES), False
        return rules, False
    except Exception as e:  # noqa: BLE001
        logger.warning("[exec_policy] read failed (%s): using defaults", e)
        return list(DEFAULT_RULES), False


def get_policy(path: Path | None = None) -> ExecPolicy:
    """Process-wide policy with mtime hot-reload."""
    global _policy, _policy_mtime, _policy_path
    p = path or POLICY_FILE
    with _lock:
        try:
            mtime = p.stat().st_mtime if p.exists() else -1.0
        except OSError:
            mtime = -1.0
        if _policy is not None and p == _policy_path and mtime == _policy_mtime:
            return _policy
        rules, seeded = _read_rules(p)
        _policy = ExecPolicy(rules, source=str(p))
        _policy_mtime = mtime
        _policy_path = p
        if seeded:
            logger.info("[exec_policy] seeded %s with %d default rules",
                        p, len(DEFAULT_RULES))
        return _policy


def reset_policy_cache() -> None:
    """Test hook — drop the cached policy so a new file is read."""
    global _policy, _policy_mtime, _policy_path
    with _lock:
        _policy = None
        _policy_mtime = -1.0
        _policy_path = None


__all__ = ["ExecPolicy", "PolicyDecision", "get_policy", "reset_policy_cache",
           "POLICY_FILE", "DEFAULT_RULES"]
