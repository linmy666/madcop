"""Shell environment snapshot — codex parity (shell-command/src/shell_snapshot.rs).

Problem it solves: the bash tool runs commands in a bare non-interactive
shell, so the user's rc-file setup (nvm/sdkman paths, aliases, exported
vars, shell functions) is invisible — models keep hitting
"command not found" for things that work in the user's own terminal.

Fix (same shape as Codex): once per session, run a snapshot script
under the user's shell that sources the rc file and prints restorable
state (functions / aliases / exports) into a file under
~/.madcop/shell_snapshots/. Every bash command is then prefixed with
`. <snapshot>` so it starts from the user's real environment.

Best-effort: any failure (no shell, rc syntax error, timeout) returns
None and commands run exactly as before.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

SNAPSHOT_DIR = Path(os.environ.get(
    "MADCOP_SHELL_SNAPSHOT_DIR", str(Path.home() / ".madcop" / "shell_snapshots")))
SNAPSHOT_TIMEOUT_S = 10
SNAPSHOT_TTL_S = 24 * 3600
_MAX_SNAPSHOT_BYTES = 512_000  # a hostile rc can print megabytes

# Excluded from export capture (they'd break the next command's cwd).
_EXCLUDED_EXPORTS = ("PWD", "OLDPWD")

_BASH_SNAPSHOT_SCRIPT = r"""
rc="$HOME/.bashrc"
[ -r "$rc" ] && . "$rc"
declare -f 2>/dev/null
alias -p 2>/dev/null
export -p 2>/dev/null
"""

_ZSH_SNAPSHOT_SCRIPT = r"""
rc="$HOME/.zshrc"
if [ -n "$ZDOTDIR" ] && [ -r "$ZDOTDIR/.zshrc" ]; then rc="$ZDOTDIR/.zshrc"; fi
[ -r "$rc" ] && . "$rc"
unalias -a 2>/dev/null || true
functions 2>/dev/null
setopt 2>/dev/null | sed 's/^/setopt /'
alias -L 2>/dev/null
export -p 2>/dev/null
"""


def _filter_exports(snapshot_text: str) -> str:
    """Drop PWD/OLDPWD and unreadable-huge lines from captured exports."""
    lines = []
    pat = re.compile(
        r"^(export |declare -x )?(" + "|".join(_EXCLUDED_EXPORTS) + ")="
    )
    for ln in snapshot_text.splitlines():
        if pat.match(ln):
            continue
        lines.append(ln)
    return "\n".join(lines)


def _rc_path(shell: str) -> Path:
    home = Path.home()
    if shell.endswith("zsh"):
        zdot = os.environ.get("ZDOTDIR")
        return Path(zdot) / ".zshrc" if zdot else home / ".zshrc"
    if shell.endswith("bash"):
        return home / ".bashrc"
    return home / ".profile"


def _user_shell() -> str:
    return os.environ.get("SHELL") or shutil.which("bash") or ""


def ensure_snapshot(session_id: str, force: bool = False) -> str | None:
    """Return a shell-sourceable snapshot file path for this session,
    generating it when missing/stale (TTL or rc-file changed).
    None = snapshots unavailable (commands run bare, as before)."""
    shell = _user_shell()
    if not shell:
        return None
    try:
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", session_id or "default")[:80]
        snap = SNAPSHOT_DIR / f"{safe}.sh"
        rc = _rc_path(shell)
        rc_mtime = rc.stat().st_mtime if rc.exists() else 0.0
        if not force and snap.exists():
            age = time.time() - snap.stat().st_mtime
            if age < SNAPSHOT_TTL_S and snap.stat().st_mtime > rc_mtime:
                return str(snap)
        script = (_ZSH_SNAPSHOT_SCRIPT if shell.endswith("zsh")
                  else _BASH_SNAPSHOT_SCRIPT)
        proc = subprocess.run(
            [shell, "-c", script],
            capture_output=True, text=True, timeout=SNAPSHOT_TIMEOUT_S,
        )
        text = proc.stdout or ""
        if proc.returncode != 0 or len(text) > _MAX_SNAPSHOT_BYTES:
            logger.info("[shell_snapshot] capture failed (rc=%d, %d bytes)",
                        proc.returncode, len(text))
            return None
        snap.write_text(_filter_exports(text), encoding="utf-8")
        return str(snap)
    except Exception as e:  # noqa: BLE001
        logger.debug("[shell_snapshot] unavailable: %s", e)
        return None


def wrap_command(command: str, snapshot_path: str | None) -> str:
    """Prefix a shell command with snapshot sourcing (no-op when None)."""
    if not snapshot_path:
        return command
    return f". '{snapshot_path}' 2>/dev/null; ({command})"


__all__ = [
    "ensure_snapshot", "wrap_command", "SNAPSHOT_DIR",
    "SNAPSHOT_TIMEOUT_S", "SNAPSHOT_TTL_S",
]
