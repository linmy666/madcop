"""v1.8.0 — Tests for config hot-reload."""
from __future__ import annotations

import time
import threading
import pytest
from pathlib import Path

from madcop.config.hotreload import ConfigWatcher, HotConfig


# --------------------------------------------------------------------------- #
# ConfigWatcher
# --------------------------------------------------------------------------- #


class TestConfigWatcher:
    def test_detects_file_change(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("initial: 1\n")
        changes = []
        watcher = ConfigWatcher(cfg_path, on_change=lambda c: changes.append(c))
        watcher.start()
        time.sleep(0.2)

        # Modify the file
        cfg_path.write_text("initial: 2\n")
        time.sleep(3.0)  # > check_interval (2s)
        watcher.stop()

        assert len(changes) >= 1
        assert "initial: 2" in changes[-1]

    def test_no_change_no_callback(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("stable\n")
        changes = []
        watcher = ConfigWatcher(cfg_path, on_change=lambda c: changes.append(c))
        # check_once without modification
        assert watcher.check_once() is False
        assert changes == []

    def test_check_once_returns_true_on_change(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("v1\n")
        changes = []
        watcher = ConfigWatcher(cfg_path, on_change=lambda c: changes.append(c))
        # First call: primes state
        watcher.check_once()
        # Modify
        cfg_path.write_text("v2\n")
        # Next call should detect
        assert watcher.check_once() is True
        assert changes == ["v2\n"]

    def test_missing_file_doesnt_crash(self, tmp_path):
        cfg_path = tmp_path / "nonexistent.yaml"
        watcher = ConfigWatcher(cfg_path, on_change=lambda c: None)
        # Should not raise
        assert watcher.check_once() is False

    def test_callback_error_logged(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("v1\n")
        def bad_callback(c):
            raise RuntimeError("boom")
        watcher = ConfigWatcher(cfg_path, on_change=bad_callback)
        watcher.check_once()  # primes
        cfg_path.write_text("v2\n")
        # Should not raise
        result = watcher.check_once()
        assert result is True  # still detects the change

    def test_mtime_only_change_no_callback(self, tmp_path):
        """If mtime changes but content doesn't, don't fire."""
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("same content\n")
        changes = []
        watcher = ConfigWatcher(cfg_path, on_change=lambda c: changes.append(c))
        watcher.check_once()
        # Touch (change mtime but not content)
        time.sleep(1.1)  # ensure mtime resolution
        import os
        os.utime(cfg_path, (time.time(), time.time() + 100))
        result = watcher.check_once()
        assert result is False
        assert changes == []


# --------------------------------------------------------------------------- #
# HotConfig
# --------------------------------------------------------------------------- #


# A simple test config class
class SimpleConfig:
    def __init__(self, model: str = "default"):
        self.model = model

    @classmethod
    def from_yaml(cls, path):
        import yaml
        data = yaml.safe_load(Path(path).read_text())
        return cls(model=data.get("model", "default"))


class TestHotConfig:
    def test_initial_load(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("model: gpt-4\n")
        hot = HotConfig(cfg_path, SimpleConfig)
        hot.start()
        try:
            assert hot.config.model == "gpt-4"
        finally:
            hot.stop()

    def test_reload_on_change(self, tmp_path):
        cfg_path = tmp_path / "config.yaml"
        cfg_path.write_text("model: gpt-4\n")
        hot = HotConfig(cfg_path, SimpleConfig)
        hot.start()
        try:
            assert hot.config.model == "gpt-4"
            # Change the file
            time.sleep(1.1)  # mtime resolution
            cfg_path.write_text("model: claude-3\n")
            time.sleep(3.0)  # wait for watcher to pick up
            # Manually trigger a check to be sure
            hot._watcher.check_once()
            assert hot.config.model == "claude-3"
        finally:
            hot.stop()

    def test_missing_file_returns_none(self, tmp_path):
        hot = HotConfig(tmp_path / "nope.yaml", SimpleConfig)
        # Don't call start — config is None
        assert hot.config is None

    def test_load_failure_doesnt_crash(self, tmp_path):
        cfg_path = tmp_path / "bad.yaml"
        cfg_path.write_text("model: gpt-4\n")
        class BadConfig:
            @classmethod
            def from_yaml(cls, path):
                raise ValueError("bad config")
        hot = HotConfig(cfg_path, BadConfig)
        hot.start()  # should not raise
        time.sleep(0.5)
        hot.stop()
        # No exception means the test passes
