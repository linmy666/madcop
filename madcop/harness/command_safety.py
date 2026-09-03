"""Command safety net — codex parity (shell-command/src/command_safety).

Second layer below the regex exec_policy: tokenize the command and
classify it, unwrapping common wrapper executables (sudo / env / nohup
/ nice / xargs / timeout / command / stdbuf, up to 8 layers) so
`sudo rm -rf /` and `env rm -rf /` can't dodge pattern rules by
prefixing a benign executable.

Faithful to the two-rule shape of codex's DangerousCommandMatch:
  FORCED_RM  — an rm invocation carrying -f/--force
  OTHER      — any other dangerous command

This is a heuristic net, not a sandbox: unknown shapes pass through
(HITL and the Guardian layer sit behind it).
"""
from __future__ import annotations

import shlex
from enum import Enum
from typing import Sequence

# Wrappers whose only effect is to run their argument; unwrap up to
# this many layers before classifying (codex: MAX_..._WRAPPER_DEPTH).
WRAPPER_EXECUTABLES = {
    "sudo", "doas", "env", "nohup", "nice", "stdbuf", "timeout",
    "command", "exec", "time", "xargs", "ionice", "setsid",
    "busybox", "strace", "ltrace", "envy", "script",
}
MAX_WRAPPER_DEPTH = 8

_RM_FLAGS_FORCE = {"-f", "--force"}


class DangerousMatch(str, Enum):
    FORCED_RM = "forced_rm"
    OTHER = "other"


def tokenize(command: str) -> list[str]:
    """Best-effort shell tokenization (quotes respected)."""
    try:
        return shlex.split(command or "")
    except ValueError:
        return (command or "").split()


def _is_rm_forced(tokens: Sequence[str]) -> bool:
    """`rm` with a force flag, incl. bundled short flags (-rf, -fr)."""
    if not tokens:
        return False
    exe = tokens[0].rsplit("/", 1)[-1]
    if exe != "rm":
        return False
    for arg in tokens[1:]:
        if arg == "--":
            break
        if arg in _RM_FLAGS_FORCE:
            return True
        if arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
            if "f" in arg[1:]:
                return True
    return False


def dangerous_command_match(
    command: str | Sequence[str], wrapper_depth: int = 0,
) -> DangerousMatch | None:
    """Classify a command (string or pre-tokenized argv). None = pass."""
    if isinstance(command, str):
        tokens = tokenize(command)
    else:
        tokens = list(command)
    if not tokens:
        return None

    exe = tokens[0].rsplit("/", 1)[-1]

    # Unwrap wrapper executables: classify the wrapped command.
    if exe in WRAPPER_EXECUTABLES and wrapper_depth < MAX_WRAPPER_DEPTH:
        # `sudo rm -rf /` → tokens[1:]; `env VAR=1 rm -rf /` skips
        # leading VAR=... assignments; `timeout 10 rm ...` skips the
        # duration; `sudo -u root ...` skips flags + their values;
        # `xargs rm` classifies as rm itself.
        rest = tokens[1:]
        if exe in ("env",):
            while rest and "=" in rest[0] and not rest[0].startswith("-"):
                rest = rest[1:]
        elif exe in ("timeout", "nice", "ionice", "stdbuf"):
            while rest and (rest[0].startswith("-") or _looks_numeric(rest[0])
                            or "=" in rest[0]):
                rest = rest[1:]
        elif exe in ("sudo", "doas"):
            # Skip flags; short value-taking flags (-u/-g/-p/-C…) also
            # consume the following token.
            _VALUE_FLAGS = {"-u", "-g", "-p", "-C", "-D", "-t", "-l"}
            while rest and rest[0].startswith("-") and rest[0] != "--":
                flag = rest[0]
                rest = rest[1:]
                if flag in _VALUE_FLAGS and rest:
                    rest = rest[1:]
            if rest and rest[0] == "--":
                rest = rest[1:]
        elif exe == "xargs":
            rest = [t for t in rest if not t.startswith("-")]
        if not rest:
            return None
        return dangerous_command_match(rest, wrapper_depth + 1)
    if exe in WRAPPER_EXECUTABLES:
        # Depth exhausted — treat as unsafe rather than pass blindly.
        return DangerousMatch.OTHER

    if _is_rm_forced(tokens):
        return DangerousMatch.FORCED_RM

    # A small vetted set of always-dangerous executables (the rest of
    # the old regex net lives in exec_policy.json).
    if exe in ("mkfs", "mkfs.ext4", "mkfs.apfs", "dd", "fdisk",
               "diskutil", "shutdown", "reboot", "halt", "launchctl"):
        if exe == "dd":
            joined = " ".join(tokens)
            if "of=/dev/" in joined:
                return DangerousMatch.OTHER
            return None
        if exe == "diskutil":
            joined = " ".join(tokens)
            if "eraseDisk" in joined or "eraseVolume" in joined:
                return DangerousMatch.OTHER
            return None
        if exe == "launchctl":
            return DangerousMatch.OTHER
        return DangerousMatch.OTHER

    # Chained commands: check each segment (a ; b && c | d).
    if any(ch in (command if isinstance(command, str) else " ")
           for ch in (";", "&&", "||")):
        if isinstance(command, str):
            import re
            segments = re.split(r";|&&|\|\|", command)
            for seg in segments:
                seg = seg.strip()
                if seg and dangerous_command_match(seg, 0):
                    return DangerousMatch.OTHER
    return None


def _looks_numeric(s: str) -> bool:
    try:
        float(s.rstrip("smhd"))
        return True
    except ValueError:
        return False


__all__ = ["DangerousMatch", "dangerous_command_match", "tokenize",
           "WRAPPER_EXECUTABLES", "MAX_WRAPPER_DEPTH"]
