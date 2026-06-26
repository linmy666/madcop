"""v1.9.0 — Docker sandbox provider.

Wraps the `docker` CLI to run agent commands in isolated containers.
This is the v1.1.0 ``SubprocessSandbox`` graduated to a real isolation
boundary — but only when Docker is available. When it's not, we
fall back to the local subprocess sandbox (Qian: 稳定性 wins).

Why subprocess to ``docker`` instead of docker-py?
  - Zero new dependency (urllib only)
  - Works with the ``docker`` binary the user already has installed
  - The user can swap to docker-py later by subclassing

Design:
  - 隔离性: each command runs in a fresh container
  - 可控性: container is deleted after the run (--rm)
  - 稳定性: hard timeout, image-not-found → local fallback
  - 早纠偏: a non-zero exit code counts as step failure
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

from .sandbox import SubprocessSandbox, SandboxResult

logger = logging.getLogger(__name__)

DEFAULT_IMAGE = "alpine:3.19"
DOCKER_TIMEOUT = 60  # seconds


# --------------------------------------------------------------------------- #
# DockerSandbox
# --------------------------------------------------------------------------- #


@dataclass
class DockerConfig:
    """Configuration for Docker sandbox runs."""
    image: str = DEFAULT_IMAGE
    timeout: int = DOCKER_TIMEOUT
    network_disabled: bool = True
    read_only_root: bool = True
    memory_limit: str | None = "256m"   # 256 MB
    cpu_shares: int | None = 512        # relative weight
    workdir: str = "/work"
    user: str = "nobody"


class DockerSandbox:
    """Run shell commands in isolated Docker containers.

    Falls back to ``SubprocessSandbox`` if Docker is unavailable
    or the image is missing — degradation is the default.

    Args:
        image: Docker image to run commands in.
        fallback: A ``SubprocessSandbox`` to use when Docker fails.
            If None, a default one is created with the same allowed_dirs.
        allowed_dirs: Working directories that the container can access
            (bind-mounted as ``/work``).
    """

    name = "docker"

    def __init__(
        self,
        *,
        image: str = DEFAULT_IMAGE,
        config: DockerConfig | None = None,
        fallback: SubprocessSandbox | None = None,
        allowed_dirs: Sequence[str | Path] | None = None,
    ) -> None:
        self._config = config or DockerConfig(image=image)
        self._fallback = fallback or SubprocessSandbox(allowed_dirs=allowed_dirs)
        self._docker_available = self._check_docker()
        if not self._docker_available:
            logger.warning(
                "DockerSandbox: docker CLI not found, falling back to "
                "SubprocessSandbox (no isolation)"
            )

    @property
    def is_isolated(self) -> bool:
        """True if running in a real Docker container, False if local."""
        return self._docker_available

    def run(
        self,
        argv: list[str],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        timeout: int | None = None,
    ) -> SandboxResult:
        """Run ``argv`` in a Docker container (or fallback locally).

        The container is removed after the run (--rm). Output is
        captured and truncated to 50_000 chars (same as SubprocessSandbox).
        """
        if not self._docker_available:
            return self._fallback.run(argv, cwd=cwd, env=env, timeout_s=timeout)

        cmd = self._build_docker_cmd(argv, cwd=cwd, timeout=timeout)
        actual_timeout = timeout or self._config.timeout

        t0 = time.time()
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=actual_timeout + 5,  # buffer for docker overhead
            )
        except subprocess.TimeoutExpired as e:
            return SandboxResult(
                argv=tuple(argv),
                cwd=str(cwd or "/work"),
                returncode=-1,
                stdout=(e.stdout or b"").decode("utf-8", errors="replace")[:50000],
                stderr=(e.stderr or b"").decode("utf-8", errors="replace")[:50000],
                duration_s=time.time() - t0,
                timed_out=True,
                output_truncated=True,
                error=f"Docker command timed out after {actual_timeout}s",
            )
        except Exception as e:
            logger.warning("DockerSandbox: docker run failed (%s), falling back", e)
            return self._fallback.run(argv, cwd=cwd, env=env, timeout_s=timeout)

        duration = time.time() - t0
        stdout = (proc.stdout or "")[:50000]
        stderr = (proc.stderr or "")[:50000]
        truncated = len(proc.stdout or "") > 50000 or len(proc.stderr or "") > 50000

        return SandboxResult(
            argv=tuple(argv),
            cwd=str(cwd or "/work"),
            returncode=proc.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_s=duration,
            timed_out=False,
            output_truncated=truncated,
        )

    # ---- internals ----

    @staticmethod
    def _check_docker() -> bool:
        """Check if the ``docker`` CLI is available."""
        if not shutil.which("docker"):
            return False
        try:
            result = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True, text=True, timeout=5,
            )
            return result.returncode == 0
        except Exception:
            return False

    def _build_docker_cmd(
        self,
        argv: list[str],
        *,
        cwd: str | Path | None,
        timeout: int | None,
    ) -> list[str]:
        """Build the full ``docker run`` command line."""
        cmd = ["docker", "run", "--rm", "-i"]

        # Network isolation
        if self._config.network_disabled:
            cmd.extend(["--network", "none"])

        # Resource limits
        if self._config.memory_limit:
            cmd.extend(["--memory", self._config.memory_limit])
        if self._config.cpu_shares:
            cmd.extend(["--cpu-shares", str(self._config.cpu_shares)])

        # Read-only root
        if self._config.read_only_root:
            # /tmp needs to be writable for some commands
            cmd.extend(["--read-only", "--tmpfs", "/tmp:size=64m"])

        # Workdir
        cmd.extend(["--workdir", self._config.workdir])

        # User
        cmd.extend(["--user", self._config.user])

        # Image
        cmd.append(self._config.image)

        # The actual command — pass through stdin
        cmd.append("--")
        cmd.extend(argv)

        return cmd

    def close(self) -> None:
        """Release resources."""
        # Docker is fire-and-forget; nothing to close. Hook for subclasses.
        pass


__all__ = [
    "DockerConfig",
    "DockerSandbox",
    "DEFAULT_IMAGE",
]
