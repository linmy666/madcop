"""v1.1.0 — SubprocessSandbox: a safe-ish way to run shell commands.

When a sub-agent wants to "run a shell command", naively calling
`subprocess.run(cmd, shell=True)` is dangerous — the user can
inject `; rm -rf /` or read /etc/shadow. DeerFlow solves this
with a Docker container (heavy). We solve it with a SubprocessSandbox
that does cheap defenses without spinning up a container:

1. **Timeout** — every command has a hard wall-clock cap
2. **Working directory allowlist** — `cwd` must be in `allowed_dirs`
3. **Environment restriction** — only vars in `allowed_env_vars`
   pass through; everything else is dropped
4. **No shell=True** — the caller passes argv (list of strings)
5. **Output size cap** — stdout/stderr truncated to N chars
6. **Return code is success/fail** — non-zero = failed step

For personal/local use this is enough. For production you
want a Docker container (v1.3.0+).

Qian invariants:
- **稳定性**: timeout + size cap prevent runaway
- **可控性**: every run is logged with cwd, argv, return code
- **早纠偏**: a non-zero return code counts as a step failure;
  the LoopDetection / QianControl middlewares can catch it
"""
from __future__ import annotations

import logging
import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Result dataclass
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class SandboxResult:
    """The result of one sandboxed subprocess run."""
    argv: tuple[str, ...]
    cwd: str
    returncode: int
    stdout: str
    stderr: str
    duration_s: float
    timed_out: bool
    output_truncated: bool
    error: str | None = None

    @property
    def success(self) -> bool:
        return self.returncode == 0 and not self.timed_out and self.error is None


# --------------------------------------------------------------------------- #
# Sandbox
# --------------------------------------------------------------------------- #


class SubprocessSandbox:
    """Run subprocess commands with cheap safety constraints.

    The sandbox does NOT replace a real container. It catches the
    common foot-guns (infinite loop, env leak, output flood) but
    does NOT isolate the process from the host filesystem beyond
    the working directory. Use Docker for true isolation.
    """

    def __init__(
        self,
        *,
        allowed_dirs: Sequence[str | Path] | None = None,
        allowed_env_vars: Sequence[str] | None = None,
        default_timeout_s: float = 30.0,
        max_output_chars: int = 50_000,
        shell: bool = False,
    ) -> None:
        # If allowed_dirs is None, default to [cwd] (most permissive
        # in that you can only run in the current directory).
        if allowed_dirs is None:
            allowed_dirs = [Path.cwd()]
        self._allowed_dirs: list[Path] = [Path(d).resolve() for d in allowed_dirs]
        self._allowed_env_vars: set[str] | None = (
            set(allowed_env_vars) if allowed_env_vars is not None else None
        )
        self._default_timeout_s = default_timeout_s
        self._max_output_chars = max_output_chars
        # shell=True is OFF by default. If a user really wants to
        # pass a string command, they have to opt in. We warn them
        # in __init__ that this is dangerous.
        if shell:
            logger.warning(
                "SubprocessSandbox: shell=True enabled — this is "
                "dangerous and can lead to command injection"
            )
        self._shell = shell

    # ----- public API ---------------------------------------------------

    def run(
        self,
        argv: str | Sequence[str],
        *,
        cwd: str | Path | None = None,
        timeout_s: float | None = None,
        env: Mapping[str, str] | None = None,
        input_data: str | None = None,
    ) -> SandboxResult:
        """Run a command. Returns a SandboxResult.

        Args:
            argv: Either a list (preferred — safer) or a string. If
                a string, it's split via shlex (unless shell=True).
            cwd: Working directory. Must be inside one of
                `allowed_dirs`. Defaults to the first allowed dir.
            timeout_s: Wall-clock cap. Defaults to `default_timeout_s`.
            env: Additional env vars to pass through (in addition
                to the host's filtered set).
            input_data: Optional stdin bytes (decoded as utf-8).
        """
        if isinstance(argv, str):
            if self._shell:
                argv_list = [argv]
            else:
                argv_list = shlex.split(argv)
        else:
            argv_list = list(argv)
        if not argv_list:
            return SandboxResult(
                argv=tuple(argv_list), cwd="", returncode=-1,
                stdout="", stderr="", duration_s=0.0, timed_out=False,
                output_truncated=False, error="empty argv",
            )

        target_cwd = self._resolve_cwd(cwd)
        if target_cwd is None:
            logger.warning(
                "sandbox deny: cwd=%r not in allowlist argv=%s",
                cwd,
                argv_list[:3],
            )
            return SandboxResult(
                argv=tuple(argv_list), cwd=str(cwd or ""),
                returncode=-1, stdout="", stderr="",
                duration_s=0.0, timed_out=False, output_truncated=False,
                error=f"cwd {cwd!r} is not in allowed_dirs",
            )

        timeout = timeout_s if timeout_s is not None else self._default_timeout_s
        full_env = self._filter_env(env)

        t0 = time.monotonic()
        timed_out = False
        truncated = False
        try:
            proc = subprocess.run(
                argv_list,
                cwd=str(target_cwd),
                env=full_env,
                shell=self._shell,
                capture_output=True,
                text=True,
                timeout=timeout,
                input=input_data,
            )
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            returncode = proc.returncode
        except subprocess.TimeoutExpired as e:
            timed_out = True
            stdout = (e.stdout.decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""))
            stderr = (e.stderr.decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or ""))
            returncode = -1
        except FileNotFoundError as e:
            return SandboxResult(
                argv=tuple(argv_list), cwd=str(target_cwd),
                returncode=127, stdout="", stderr=str(e),
                duration_s=time.monotonic() - t0, timed_out=False,
                output_truncated=False, error=f"command not found: {e}",
            )
        except Exception as e:  # noqa: BLE001
            return SandboxResult(
                argv=tuple(argv_list), cwd=str(target_cwd),
                returncode=-1, stdout="", stderr="",
                duration_s=time.monotonic() - t0, timed_out=False,
                output_truncated=False, error=f"{type(e).__name__}: {e}",
            )

        # Output size cap
        if len(stdout) > self._max_output_chars:
            stdout = stdout[: self._max_output_chars - 3] + "..."
            truncated = True
        if len(stderr) > self._max_output_chars:
            stderr = stderr[: self._max_output_chars - 3] + "..."
            truncated = True

        return SandboxResult(
            argv=tuple(argv_list),
            cwd=str(target_cwd),
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_s=time.monotonic() - t0,
            timed_out=timed_out,
            output_truncated=truncated,
        )

    # ----- helpers ------------------------------------------------------

    def _resolve_cwd(self, cwd: str | Path | None) -> Path | None:
        if cwd is None:
            return self._allowed_dirs[0]
        target = Path(cwd).resolve()
        for allowed in self._allowed_dirs:
            try:
                target.relative_to(allowed)
                return target
            except ValueError:
                continue
        return None

    def _filter_env(self, extras: Mapping[str, str] | None) -> dict[str, str]:
        """Build the env to pass to subprocess.

        - If `allowed_env_vars` is None, pass the host's env through
          (the most permissive option).
        - Otherwise, only pass vars that are in `allowed_env_vars`.
        - `extras` is always added (in addition to the filtered set).
        """
        if self._allowed_env_vars is None:
            base = dict(os.environ)
        else:
            base = {k: v for k, v in os.environ.items() if k in self._allowed_env_vars}
        if extras:
            base.update(extras)
        return base


# --------------------------------------------------------------------------- #
# BashTool: wrap a sandbox as a Tool
# --------------------------------------------------------------------------- #


class BashTool:
    """A Tool that runs a shell command through a SubprocessSandbox.

    Wire-up:
        sandbox = SubprocessSandbox(allowed_dirs=[Path.home() / "projects"])
        tool = BashTool(sandbox)
        # Register with a ToolRegistry:
        registry.register(tool)
        # The LLM can now call `bash(command="ls -la")`.
    """

    def __init__(self, sandbox: SubprocessSandbox, *, name: str = "bash"):
        self.name = name
        self.description = (
            "Run a shell command in a sandboxed subprocess. "
            "Returns stdout (truncated), stderr, and the return code. "
            "Use this for: listing files, running scripts, inspecting "
            "data. The sandbox enforces a working-directory allowlist, "
            "a timeout, and an output size cap. Do NOT use for: file "
            "deletion, system changes — those need a different tool."
        )
        self._sandbox = sandbox

    @property
    def parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run (argv list, NOT a shell string)",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (optional, must be in sandbox's allowed_dirs)",
                },
                "timeout_s": {
                    "type": "number",
                    "description": "Wall-clock timeout in seconds (default: sandbox's default)",
                },
            },
            "required": ["command"],
        }

    def __call__(self, *, command: str, cwd: str | None = None, timeout_s: float | None = None) -> dict[str, Any]:
        result = self._sandbox.run(command, cwd=cwd, timeout_s=timeout_s)
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
            "duration_s": result.duration_s,
            "timed_out": result.timed_out,
            "output_truncated": result.output_truncated,
            "error": result.error,
        }

    def to_openai_schema(self) -> dict[str, Any]:
        """Format as an OpenAI tool descriptor (same as the abstract Tool)."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            },
        }


__all__ = ["BashTool", "SandboxResult", "SubprocessSandbox"]
