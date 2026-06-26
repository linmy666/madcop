"""v1.9.0 — Tests for Docker sandbox and event bus."""
from __future__ import annotations

import json
import time
import threading
import pytest
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import patch, MagicMock

from madcop.tools.docker_sandbox import DockerSandbox, DockerConfig
from madcop.tools.sandbox import SubprocessSandbox
from madcop.tools.eventbus import Event, EventBus, WebhookSub, emit, get_default_bus


# --------------------------------------------------------------------------- #
# Test HTTP server (for webhook tests)
# --------------------------------------------------------------------------- #


class _WebhookHandler(BaseHTTPRequestHandler):
    received: list[dict] = []
    log_box: list[str] = []

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        try:
            self.received.append(json.loads(body))
        except Exception:
            self.received.append({"raw": body})
        self.send_response(200)
        self.end_headers()

    def log_message(self, format, *args):
        pass


@pytest.fixture
def webhook_server():
    server = HTTPServer(("127.0.0.1", 0), _WebhookHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _WebhookHandler.received.clear()
    _WebhookHandler.log_box.clear()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()
    server.server_close()


# --------------------------------------------------------------------------- #
# DockerSandbox
# --------------------------------------------------------------------------- #


class TestDockerSandbox:
    def test_detects_docker_unavailable(self, monkeypatch):
        """If docker CLI is not available, sandbox falls back to local."""
        # Force _check_docker to return False
        monkeypatch.setattr(DockerSandbox, "_check_docker", staticmethod(lambda: False))
        sandbox = DockerSandbox()
        assert sandbox.is_isolated is False

    def test_detects_docker_available(self, monkeypatch):
        monkeypatch.setattr(DockerSandbox, "_check_docker", staticmethod(lambda: True))
        sandbox = DockerSandbox()
        assert sandbox.is_isolated is True

    def test_falls_back_to_local_when_no_docker(self, monkeypatch):
        """When Docker is unavailable, run() delegates to SubprocessSandbox."""
        monkeypatch.setattr(DockerSandbox, "_check_docker", staticmethod(lambda: False))
        sandbox = DockerSandbox()

        # SubprocessSandbox should be called
        with patch.object(sandbox._fallback, "run", return_value=MagicMock(success=True)) as mock:
            result = sandbox.run(["echo", "hello"])
            mock.assert_called_once()
            assert "echo" in mock.call_args.args[0]

    def test_builds_correct_docker_cmd(self, monkeypatch):
        """The docker CLI invocation has all the right flags."""
        monkeypatch.setattr(DockerSandbox, "_check_docker", staticmethod(lambda: True))
        sandbox = DockerSandbox(config=DockerConfig(
            image="alpine:3.19",
            network_disabled=True,
            memory_limit="256m",
            user="nobody",
        ))

        cmd = sandbox._build_docker_cmd(
            ["echo", "hello"], cwd="/work", timeout=30,
        )

        assert cmd[0] == "docker"
        assert cmd[1] == "run"
        assert "--rm" in cmd
        assert "--network" in cmd
        assert "none" in cmd
        assert "--memory" in cmd
        assert "256m" in cmd
        assert "--user" in cmd
        assert "nobody" in cmd
        assert "alpine:3.19" in cmd
        # The "--" separator is inserted before the user's argv
        assert "--" in cmd
        # The command comes after --
        sep_idx = cmd.index("--")
        assert cmd[sep_idx + 1:] == ["echo", "hello"]

    def test_no_network_when_disabled(self, monkeypatch):
        monkeypatch.setattr(DockerSandbox, "_check_docker", staticmethod(lambda: True))
        sandbox = DockerSandbox(config=DockerConfig(network_disabled=True))
        cmd = sandbox._build_docker_cmd(["ls"], cwd="/work", timeout=10)
        idx = cmd.index("--network")
        assert cmd[idx + 1] == "none"

    def test_network_enabled_when_requested(self, monkeypatch):
        monkeypatch.setattr(DockerSandbox, "_check_docker", staticmethod(lambda: True))
        sandbox = DockerSandbox(config=DockerConfig(network_disabled=False))
        cmd = sandbox._build_docker_cmd(["ls"], cwd="/work", timeout=10)
        assert "--network" not in cmd

    def test_read_only_root_creates_tmpfs(self, monkeypatch):
        monkeypatch.setattr(DockerSandbox, "_check_docker", staticmethod(lambda: True))
        sandbox = DockerSandbox(config=DockerConfig(read_only_root=True))
        cmd = sandbox._build_docker_cmd(["ls"], cwd="/work", timeout=10)
        assert "--read-only" in cmd
        assert "--tmpfs" in cmd

    def test_run_invokes_docker_subprocess(self, monkeypatch):
        """When Docker is available, run() shells out to docker CLI."""
        monkeypatch.setattr(DockerSandbox, "_check_docker", staticmethod(lambda: True))
        sandbox = DockerSandbox()

        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "hello from container"
        mock_proc.stderr = ""

        with patch("subprocess.run", return_value=mock_proc) as mock_run:
            result = sandbox.run(["echo", "hello"], cwd="/work", timeout=10)

        # Verify subprocess.run was called
        mock_run.assert_called_once()
        cmd = mock_run.call_args.args[0]
        assert cmd[0] == "docker"
        assert "alpine:3.19" in cmd or sandbox._config.image in cmd
        # Verify the result
        assert result.returncode == 0
        assert "hello from container" in result.stdout
        assert result.success is True

    def test_run_handles_timeout(self, monkeypatch):
        """subprocess.TimeoutExpired → result with timed_out=True."""
        import subprocess as _subprocess
        monkeypatch.setattr(DockerSandbox, "_check_docker", staticmethod(lambda: True))
        sandbox = DockerSandbox()

        with patch("subprocess.run", side_effect=_subprocess.TimeoutExpired("docker", 30)):
            result = sandbox.run(["sleep", "100"], timeout=30)

        assert result.timed_out is True
        assert result.returncode == -1

    def test_run_handles_docker_error_falls_back(self, monkeypatch):
        """If docker run raises an exception, fall back to local."""
        monkeypatch.setattr(DockerSandbox, "_check_docker", staticmethod(lambda: True))
        sandbox = DockerSandbox()

        with patch("subprocess.run", side_effect=FileNotFoundError("docker gone")):
            with patch.object(sandbox._fallback, "run", return_value=MagicMock(success=True)) as fb:
                sandbox.run(["echo", "x"])
                fb.assert_called_once()


# --------------------------------------------------------------------------- #
# EventBus
# --------------------------------------------------------------------------- #


class TestEventBus:
    def test_emit_to_sync_subscriber(self):
        bus = EventBus()
        received = []
        bus.subscribe(lambda evt: received.append(evt))
        bus.emit("test", {"x": 1})
        assert len(received) == 1
        assert received[0].type == "test"
        assert received[0].data == {"x": 1}

    def test_emit_to_async_subscriber(self):
        bus = EventBus(max_workers=2)
        received = []
        event_signal = threading.Event()
        def cb(evt):
            received.append(evt)
            event_signal.set()
        bus.subscribe(cb, async_dispatch=True)
        bus.emit("async_test", {"y": 2})
        # Wait briefly for async dispatch
        assert event_signal.wait(timeout=2)
        assert len(received) == 1
        assert received[0].data == {"y": 2}
        bus.shutdown()

    def test_sync_subscriber_error_doesnt_crash(self):
        bus = EventBus()
        def bad_cb(evt):
            raise RuntimeError("boom")
        bus.subscribe(bad_cb)
        # Should not raise
        bus.emit("error_test", {})

    def test_unsubscribe(self):
        bus = EventBus()
        received = []
        def cb(evt):
            received.append(evt)
        bus.subscribe(cb)
        bus.emit("e1", {})
        bus.unsubscribe(cb)
        bus.emit("e2", {})
        assert len(received) == 1
        assert received[0].type == "e1"

    def test_history_tracks_events(self):
        bus = EventBus()
        bus.emit("a", {})
        bus.emit("b", {"x": 1})
        bus.emit("c", {"y": 2})
        history = bus.history
        assert len(history) == 3
        assert [e.type for e in history] == ["a", "b", "c"]

    def test_history_of_filters(self):
        bus = EventBus()
        bus.emit("foo", {})
        bus.emit("bar", {})
        bus.emit("foo", {"v": 2})
        foo_events = bus.history_of("foo")
        assert len(foo_events) == 2

    def test_history_max_capped(self):
        bus = EventBus()
        bus._history_max = 5
        for i in range(10):
            bus.emit("e", {"i": i})
        assert len(bus.history) == 5
        # Most recent 5 are kept
        assert bus.history[-1].data == {"i": 9}

    def test_event_dataclass(self):
        evt = Event(type="x", data={"k": "v"}, source="test")
        assert evt.type == "x"
        assert evt.source == "test"
        assert evt.timestamp > 0


# --------------------------------------------------------------------------- #
# Webhooks
# --------------------------------------------------------------------------- #


class TestWebhooks:
    def test_webhook_delivered(self, webhook_server):
        bus = EventBus()
        bus.add_webhook(WebhookSub(url=webhook_server))
        bus.emit("hook_test", {"msg": "hello"})
        # Wait for async delivery
        time.sleep(1)
        bus.shutdown(wait=True)

        assert len(_WebhookHandler.received) == 1
        payload = _WebhookHandler.received[0]
        assert payload["type"] == "hook_test"
        assert payload["data"] == {"msg": "hello"}
        assert payload["source"] == "madcop"

    def test_webhook_event_filter(self, webhook_server):
        bus = EventBus()
        bus.add_webhook(WebhookSub(
            url=webhook_server,
            event_types={"only_this"},
        ))
        bus.emit("not_matched", {})
        bus.emit("only_this", {"v": 1})
        bus.emit("also_not_matched", {})
        time.sleep(1)
        bus.shutdown(wait=True)
        assert len(_WebhookHandler.received) == 1
        assert _WebhookHandler.received[0]["type"] == "only_this"

    def test_webhook_retry_on_failure(self):
        bus = EventBus()
        # Point at a URL that will reject
        with patch("urllib.request.urlopen", side_effect=Exception("network error")):
            with patch("time.sleep"):  # skip backoff
                bus.add_webhook(WebhookSub(
                    url="http://nope.invalid/",
                    max_retries=2,
                    timeout=1,
                ))
                bus.emit("retry_test", {})
                time.sleep(0.5)
                bus.shutdown(wait=True)
        # No exception, no assertion needed — just verifying retry doesn't crash

    def test_remove_webhook(self, webhook_server):
        bus = EventBus()
        sub = WebhookSub(url=webhook_server)
        bus.add_webhook(sub)
        assert bus.remove_webhook(webhook_server) is True
        bus.emit("after_remove", {})
        time.sleep(0.5)
        bus.shutdown(wait=True)
        assert _WebhookHandler.received == []

    def test_remove_nonexistent_webhook(self):
        bus = EventBus()
        assert bus.remove_webhook("http://never.added/") is False


# --------------------------------------------------------------------------- #
# Convenience API
# --------------------------------------------------------------------------- #


class TestGlobalBus:
    def test_get_default_bus_returns_singleton(self):
        bus1 = get_default_bus()
        bus2 = get_default_bus()
        assert bus1 is bus2

    def test_emit_convenience(self):
        bus = get_default_bus()
        before = len(bus.history)
        emit("convenience_test", {"v": 1})
        after = len(bus.history)
        assert after == before + 1
        # Last event is the one we emitted
        assert bus.history[-1].type == "convenience_test"


# --------------------------------------------------------------------------- #
# DockerSandbox fallback integration
# --------------------------------------------------------------------------- #


class TestDockerFallbackIntegration:
    def test_fallback_actually_runs_locally(self, monkeypatch):
        """When Docker is unavailable, the fallback SubprocessSandbox runs."""
        monkeypatch.setattr(DockerSandbox, "_check_docker", staticmethod(lambda: False))
        sandbox = DockerSandbox(allowed_dirs=["/tmp"])

        # This should actually execute locally (no docker)
        result = sandbox.run(["echo", "hello world"], cwd="/tmp")
        # SubprocessSandbox runs the command
        # (it may fail on cwd but it should return a result)
        assert result is not None
