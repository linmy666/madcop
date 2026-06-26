"""v0.8.0 — `madcop doctor` self-check.

A single command that answers the question "is my madcop
installation actually working?" with a clear pass/fail per check.

What it checks (in order):

1. **Python + madcop version** — is the import path healthy?
2. **Env vars** — does the user have `MADCOP_OPENAI_*` set if they
   want a real LLM? (Soft warning if not, hard fail only if
   explicitly asked.)
3. **LLM endpoint reachable** — if env vars are set, does a one-shot
   `chat()` to the endpoint succeed? (Times out after 5s so doctor
   doesn't hang on a dead proxy.)
4. **Scratchpad directory writable** — can madcop create
   `~/.madcop/runs/` and write a tiny JSON file? (This is the same
   path real runs use, so a failure here is real.)
5. **Sub-agent pool + async loop** — can the executor spin up a
   trivial sub-agent and have it complete?

Each check returns a `DoctorCheck` with:
- `name`: short id like "env" or "llm_endpoint"
- `status`: "ok" | "warn" | "fail" | "skip"
- `detail`: human-readable explanation
- `fix`: optional actionable hint (printed when status != "ok")

Exit code:
- 0 if all checks are "ok" or "warn"
- 1 if any check is "fail"
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import socket
import tempfile
import time
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

logger = logging.getLogger(__name__)


# Status values
OK = "ok"
WARN = "warn"
FAIL = "fail"
SKIP = "skip"

_STATUS_GLYPH = {OK: "[OK]", WARN: "[WARN]", FAIL: "[FAIL]", SKIP: "[SKIP]"}


@dataclass(frozen=True)
class DoctorCheck:
    """One self-check result."""
    name: str
    status: str
    detail: str
    fix: str | None = None


@dataclass
class DoctorReport:
    """The full set of checks + the final verdict."""
    checks: list[DoctorCheck]

    @property
    def passed(self) -> bool:
        return all(c.status != FAIL for c in self.checks)

    @property
    def failure_count(self) -> int:
        return sum(1 for c in self.checks if c.status == FAIL)

    @property
    def warn_count(self) -> int:
        return sum(1 for c in self.checks if c.status == WARN)

    def to_text(self) -> str:
        lines = ["madcop doctor — self-check report", ""]
        for c in self.checks:
            glyph = _STATUS_GLYPH.get(c.status, "[????]")
            lines.append(f"  {glyph:<6} {c.name}: {c.detail}")
            if c.fix and c.status in (FAIL, WARN):
                lines.append(f"          fix: {c.fix}")
        lines.append("")
        verdict = "PASS" if self.passed else "FAIL"
        lines.append(
            f"verdict: {verdict}  "
            f"({self.failure_count} failure(s), {self.warn_count} warning(s))"
        )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Individual checks
# --------------------------------------------------------------------------- #


def check_python_and_version() -> DoctorCheck:
    """1. madcop importable, version resolvable."""
    import madcop
    return DoctorCheck(
        name="python_version",
        status=OK,
        detail=f"madcop {madcop.__version__} on Python {__import__('sys').version.split()[0]}",
    )


def check_env_vars(strict: bool = False) -> DoctorCheck:
    """2. Are MADCOP_OPENAI_* env vars set?

    With `strict=False` (the default), missing vars are a WARN: the
    user can still run with `MockClient`. With `strict=True`, missing
    vars are a FAIL.
    """
    base = os.environ.get("MADCOP_OPENAI_BASE_URL", "")
    key = os.environ.get("MADCOP_OPENAI_API_KEY", "")
    model = os.environ.get("MADCOP_OPENAI_MODEL", "")

    if base and key and model:
        return DoctorCheck(
            name="env",
            status=OK,
            detail=f"MADCOP_OPENAI_* all set (model={model})",
        )

    missing = []
    if not base: missing.append("MADCOP_OPENAI_BASE_URL")
    if not key: missing.append("MADCOP_OPENAI_API_KEY")
    if not model: missing.append("MADCOP_OPENAI_MODEL")
    status = FAIL if strict else WARN
    return DoctorCheck(
        name="env",
        status=status,
        detail=f"missing env vars: {', '.join(missing)}",
        fix=(
            "export MADCOP_OPENAI_BASE_URL=https://api.example.com/v1 "
            "MADCOP_OPENAI_API_KEY=sk-... "
            "MADCOP_OPENAI_MODEL=your-model"
        ),
    )


def check_llm_endpoint(timeout_s: float = 5.0) -> DoctorCheck:
    """3. If env vars are set, can we hit the LLM endpoint?

    We do a TCP-level reachability check on the host:port extracted
    from the base URL. A real chat() call is too expensive (and too
    flakey on slow networks) for a quick self-check.
    """
    base = os.environ.get("MADCOP_OPENAI_BASE_URL", "")
    if not base:
        return DoctorCheck(
            name="llm_endpoint",
            status=SKIP,
            detail="no MADCOP_OPENAI_BASE_URL — skipped",
        )

    try:
        parsed = urllib.parse.urlparse(base)
    except Exception as e:  # noqa: BLE001
        return DoctorCheck(
            name="llm_endpoint",
            status=FAIL,
            detail=f"could not parse MADCOP_OPENAI_BASE_URL: {e}",
            fix="set MADCOP_OPENAI_BASE_URL to a valid http(s) URL",
        )

    host = parsed.hostname
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not host:
        return DoctorCheck(
            name="llm_endpoint",
            status=FAIL,
            detail=f"MADCOP_OPENAI_BASE_URL has no host: {base!r}",
        )

    try:
        with socket.create_connection((host, port), timeout=timeout_s):
            pass
    except (socket.timeout, OSError) as e:
        return DoctorCheck(
            name="llm_endpoint",
            status=FAIL,
            detail=f"could not reach {host}:{port} within {timeout_s}s ({type(e).__name__})",
            fix="check your network, VPN, or proxy settings",
        )
    return DoctorCheck(
        name="llm_endpoint",
        status=OK,
        detail=f"{host}:{port} reachable",
    )


def check_scratchpad_dir() -> DoctorCheck:
    """4. Can we write to ~/.madcop/runs/ ?"""
    runs_dir = Path.home() / ".madcop" / "runs"
    try:
        runs_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as e:
        return DoctorCheck(
            name="scratchpad_dir",
            status=FAIL,
            detail=f"cannot create {runs_dir}: {type(e).__name__}: {e}",
            fix=f"check write permissions on {Path.home()}",
        )

    # Try writing a tiny file
    probe = runs_dir / ".doctor-probe.json"
    try:
        probe.write_text('{"probe": true}')
        probe.unlink()
    except (PermissionError, OSError) as e:
        return DoctorCheck(
            name="scratchpad_dir",
            status=FAIL,
            detail=f"cannot write to {runs_dir}: {type(e).__name__}: {e}",
            fix=f"check write permissions on {runs_dir}",
        )

    return DoctorCheck(
        name="scratchpad_dir",
        status=OK,
        detail=f"{runs_dir} is writable",
    )


def check_subagent_pool() -> DoctorCheck:
    """5. Can the SubagentExecutor spin up + complete a trivial sub-agent?

    We use a sync executor + FnRunner so this check doesn't need an
    event loop. If anything goes wrong (spec lookup, threading, status
    machine), it surfaces here.
    """
    try:
        from madcop.agent.subagent import (
            ExecutorConfig,
            FnRunner,
            GENERAL_PURPOSE,
            SubagentExecutor,
        )
        from madcop.agent.subagent.status import SubagentStatus
    except ImportError as e:
        return DoctorCheck(
            name="subagent_pool",
            status=FAIL,
            detail=f"could not import sub-agent modules: {e}",
        )

    def run(*, agent, prompt, context, result_holder):  # type: ignore[no-untyped-def]
        return f"ok: {prompt}"

    executor = SubagentExecutor(
        runner=FnRunner(run),
        config=ExecutorConfig(max_concurrent=1),
    )
    try:
        result = executor.run_one(GENERAL_PURPOSE.name, "ping", {})
    except Exception as e:  # noqa: BLE001
        return DoctorCheck(
            name="subagent_pool",
            status=FAIL,
            detail=f"sub-agent run crashed: {type(e).__name__}: {e}",
        )
    finally:
        executor.shutdown(wait=False)

    if result.status != SubagentStatus.COMPLETED:
        return DoctorCheck(
            name="subagent_pool",
            status=FAIL,
            detail=f"sub-agent did not complete (status={result.status.name}, "
                   f"error={result.error!r})",
        )
    return DoctorCheck(
        name="subagent_pool",
        status=OK,
        detail="sub-agent ran + completed in a real SubagentExecutor",
    )


def check_async_loop() -> DoctorCheck:
    """6. Can asyncio actually drive a coroutine?

    This catches the "we're in a sync context but the user tried to
    use async stuff" failure mode. Doctor should always run sync
    (we drive the async check via asyncio.run()).
    """
    async def ping() -> str:
        await asyncio.sleep(0)
        return "pong"

    try:
        got = asyncio.run(ping())
    except Exception as e:  # noqa: BLE001
        return DoctorCheck(
            name="async_loop",
            status=FAIL,
            detail=f"asyncio.run() crashed: {type(e).__name__}: {e}",
        )
    if got != "pong":
        return DoctorCheck(
            name="async_loop",
            status=FAIL,
            detail=f"async coroutine returned {got!r}, expected 'pong'",
        )
    return DoctorCheck(
        name="async_loop",
        status=OK,
        detail="asyncio.run() can drive a coroutine end-to-end",
    )


# --------------------------------------------------------------------------- #
# Run the full check suite
# --------------------------------------------------------------------------- #


def run_all_checks(strict: bool = False) -> DoctorReport:
    """Run every check, in order, and return the full report.

    A check that raises is treated as a FAIL (we catch the exception
    and record its name + type).
    """
    checks: list[DoctorCheck] = []
    check_fns: Sequence[Callable[[], DoctorCheck]] = (
        check_python_and_version,
        lambda: check_env_vars(strict=strict),
        check_llm_endpoint,
        check_scratchpad_dir,
        check_subagent_pool,
        check_async_loop,
    )
    for fn in check_fns:
        t0 = time.monotonic()
        try:
            c = fn()
        except Exception as e:  # noqa: BLE001
            c = DoctorCheck(
                name=fn.__name__,
                status=FAIL,
                detail=f"check itself crashed: {type(e).__name__}: {e}",
            )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        logger.debug("doctor check %s: %s in %dms", c.name, c.status, elapsed_ms)
        checks.append(c)
    return DoctorReport(checks=checks)


__all__ = [
    "DoctorCheck",
    "DoctorReport",
    "run_all_checks",
    "OK", "WARN", "FAIL", "SKIP",
]
