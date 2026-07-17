"""Filesystem allowlist for /api/filesystem/* endpoints."""
from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

# Entire ~/.madcop blocked (keys, settings, history). Preview uses /preview.
FS_SENSITIVE_PATHS = (
    Path.home() / ".ssh",
    Path.home() / ".madcop",
    Path.home() / ".aws",
    Path.home() / ".gnupg",
    Path.home() / ".kube",
    Path.home() / ".docker",
    Path.home() / ".netrc",
    Path.home() / ".git-credentials",
    Path.home() / ".npmrc",
    Path.home() / ".config" / "gh",
    Path.home() / ".config" / "gcloud",
)


def check_path_allowed(path: Path) -> Path:
    """Resolve and validate a path for filesystem endpoints.

    Allowed: user home, cwd, /tmp (and /private/tmp on macOS).
    """
    p = path.expanduser().resolve()
    for sensitive in FS_SENSITIVE_PATHS:
        try:
            s = sensitive.expanduser().resolve()
        except OSError:
            continue
        if p == s:
            raise HTTPException(403, "access denied: sensitive path")
        try:
            p.relative_to(s)
            raise HTTPException(403, "access denied: sensitive path")
        except ValueError:
            pass
    allowed_roots = [
        Path.home().resolve(),
        Path.cwd().resolve(),
        Path("/tmp").resolve(),
    ]
    if Path("/private/tmp").exists():
        allowed_roots.append(Path("/private/tmp").resolve())
    seen: set[Path] = set()
    uniq: list[Path] = []
    for r in allowed_roots:
        if r not in seen:
            seen.add(r)
            uniq.append(r)
    for root in uniq:
        try:
            p.relative_to(root)
            return p
        except ValueError:
            continue
    raise HTTPException(403, f"access denied: '{p}' is outside allowed directories")
