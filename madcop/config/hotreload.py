"""v1.8.0 — Config hot-reload.

Watches the user's config file (~/.madcop/config.yaml) for changes
and re-parses it on the fly. A registered callback is invoked
when the config changes, so the agent can pick up new model
settings, providers, etc. without a restart.

Why hot-reload?
  - Personal use: edit config, see effect immediately.
  - No need to restart long-running daemons (e.g. the channel
    listener) when you switch models.
  - Matches OpenClaw's hot-reload pattern (Hybrid mode).

Implementation: ``os.stat()`` mtime polling every 2s.
For v1.8 we don't need fancier (no inotify cross-platform);
mtime polling works everywhere and is cheap.

Usage:
  watcher = ConfigWatcher("~/.madcop/config.yaml", on_change=reload)
  watcher.start()  # background thread
  watcher.stop()
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Watch a config file for changes via mtime polling.

    Args:
        path: Path to the config file.
        on_change: Callback called with the new file contents (str)
            when the file changes.
        check_interval: Seconds between mtime checks (default 2).
    """

    def __init__(
        self,
        path: str | Path,
        on_change: Callable[[str], None],
        *,
        check_interval: float = 2.0,
    ) -> None:
        self._path = Path(path).expanduser()
        self._on_change = on_change
        self._interval = check_interval
        self._last_mtime: float | None = None
        self._last_content: str | None = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        # Prime last_mtime to current state — first check won't fire
        self._read_state()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True,
            name=f"madcop-config-watcher",
        )
        self._thread.start()
        logger.info("ConfigWatcher started for %s", self._path)

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        logger.info("ConfigWatcher stopped")

    def check_once(self) -> bool:
        """Check for changes right now. Returns True if changed."""
        if not self._path.exists():
            return False
        try:
            mtime = self._path.stat().st_mtime
        except OSError:
            return False

        if self._last_mtime is None:
            self._last_mtime = mtime
            self._last_content = self._safe_read()
            return False

        if mtime == self._last_mtime:
            return False

        # File changed — read new content
        old_content = self._last_content
        new_content = self._safe_read()
        if new_content is None:
            return False

        # Update state
        self._last_mtime = mtime
        self._last_content = new_content

        # Fire callback only if content actually changed (mtime can
        # change without content changing on some systems)
        if new_content == old_content:
            return False

        try:
            self._on_change(new_content)
        except Exception as e:
            logger.warning("ConfigWatcher on_change callback failed: %s", e)
        return True

    # ---- internals ----

    def _read_state(self) -> None:
        if self._path.exists():
            try:
                self._last_mtime = self._path.stat().st_mtime
                self._last_content = self._safe_read()
            except OSError:
                pass

    def _safe_read(self) -> str | None:
        try:
            return self._path.read_text(encoding="utf-8")
        except OSError as e:
            logger.warning("ConfigWatcher: failed to read %s: %s", self._path, e)
            return None

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.check_once()
            self._stop_event.wait(self._interval)


__all__ = ["ConfigWatcher"]


# --------------------------------------------------------------------------- #
# Convenience: a Config class that knows how to reload itself
# --------------------------------------------------------------------------- #


class HotConfig:
    """A config wrapper that re-parses on file change.

    Example:
        cfg = HotConfig("~/.madcop/config.yaml", ConfigClass)
        cfg.start()
        # cfg.config is always up-to-date
        cfg.config.providers.primary.model
    """

    def __init__(self, path: str | Path, config_class: type) -> None:
        self._path = Path(path).expanduser()
        self._cls = config_class
        self._config: Any = None
        self._lock = threading.Lock()
        self._watcher = ConfigWatcher(self._path, on_change=self._on_file_changed)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def config(self) -> Any:
        """Returns the current config (thread-safe)."""
        with self._lock:
            if self._config is None:
                self._load()
            return self._config

    def start(self) -> None:
        # Initial load
        self._load()
        # Start watching
        self._watcher.start()

    def stop(self) -> None:
        self._watcher.stop()

    def _on_file_changed(self, new_content: str) -> None:
        """Called by ConfigWatcher when the file changes on disk."""
        logger.info("HotConfig: config file changed, reloading")
        with self._lock:
            try:
                self._config = self._cls.from_yaml(self._path)
                logger.info("HotConfig: reload successful")
            except Exception as e:
                logger.warning("HotConfig: reload failed: %s", e)

    def _load(self) -> None:
        try:
            self._config = self._cls.from_yaml(self._path)
        except Exception as e:
            logger.warning("HotConfig: initial load failed: %s", e)
            self._config = None


__all__ += ["HotConfig"]
