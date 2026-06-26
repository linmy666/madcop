"""v1.8.0 — Tests for channel abstraction and Telegram/Discord channels."""
from __future__ import annotations

import time
import threading
import pytest
from unittest.mock import MagicMock, patch

from madcop.channels.base import ChannelBase, IncomingMessage


# --------------------------------------------------------------------------- #
# Test channel implementation
# --------------------------------------------------------------------------- #


class FakeChannel(ChannelBase):
    """A test channel that uses in-memory message lists."""

    name = "fake"

    def __init__(self, messages: list[IncomingMessage] | None = None, **kwargs):
        kwargs.setdefault("rate_limit_seconds", 0)
        super().__init__(**kwargs)
        self._messages = list(messages or [])
        self._send_calls: list[tuple[str, str]] = []
        self._lock = threading.Lock()

    def add_message(self, msg: IncomingMessage) -> None:
        with self._lock:
            self._messages.append(msg)

    def _poll(self) -> list[IncomingMessage]:
        with self._lock:
            out = list(self._messages)
            self._messages.clear()
        return out

    def _send_impl(self, user_id: str, text: str) -> None:
        self._send_calls.append((user_id, text))


# --------------------------------------------------------------------------- #
# ChannelBase basics
# --------------------------------------------------------------------------- #


class TestChannelBase:
    def test_send_message(self):
        ch = FakeChannel()
        assert ch.send_message("u1", "hello") is True
        assert ch._send_calls == [("u1", "hello")]

    def test_send_message_failure(self):
        class BadChannel(FakeChannel):
            def _send_impl(self, user_id, text):
                raise RuntimeError("network down")
        ch = BadChannel()
        assert ch.send_message("u1", "x") is False

    def test_rate_limiting(self):
        ch = FakeChannel(rate_limit_seconds=0.5)
        start = time.time()
        ch.send_message("u1", "a")
        ch.send_message("u1", "b")
        elapsed = time.time() - start
        # Second call should have been delayed
        assert elapsed >= 0.4  # slightly under 0.5 due to timestamp

    def test_on_message_handler(self):
        received = []
        def handler(channel, msg):
            received.append(msg.text)
        ch = FakeChannel(on_message=handler)
        ch.add_message(IncomingMessage(user_id="u1", user_name="alice", text="hi"))
        ch._dispatch(IncomingMessage(user_id="u1", user_name="alice", text="hi"))
        assert received == ["hi"]

    def test_handler_error_doesnt_crash(self):
        def bad_handler(channel, msg):
            raise RuntimeError("boom")
        ch = FakeChannel(on_message=bad_handler)
        # Should not raise
        ch._dispatch(IncomingMessage(user_id="u1", user_name="alice", text="hi"))

    def test_start_and_stop(self):
        ch = FakeChannel()
        ch.start()
        time.sleep(0.1)
        assert ch._thread is not None
        ch.stop()
        assert ch._thread is None or not ch._thread.is_alive()

    def test_run_loop_polls_messages(self):
        received = []
        ch = FakeChannel(on_message=lambda c, m: received.append(m.text))
        ch.add_message(IncomingMessage(user_id="u1", user_name="a", text="hello"))
        ch.start()
        time.sleep(1.5)  # let the polling loop run
        ch.stop()
        assert "hello" in received


# --------------------------------------------------------------------------- #
# TelegramChannel
# --------------------------------------------------------------------------- #


class TestTelegramChannel:
    def test_requires_token(self):
        from madcop.channels.telegram import TelegramChannel
        with patch.dict("os.environ", {}, clear=True):
            with pytest.raises(ValueError, match="token"):
                TelegramChannel()

    def test_token_from_env(self, monkeypatch):
        monkeypatch.setenv("MADCOP_TELEGRAM_BOT_TOKEN", "test-token")
        from madcop.channels.telegram import TelegramChannel
        ch = TelegramChannel()
        assert ch._token == "test-token"

    def test_poll_parses_updates(self, monkeypatch):
        monkeypatch.setenv("MADCOP_TELEGRAM_BOT_TOKEN", "test-token")
        from madcop.channels.telegram import TelegramChannel
        ch = TelegramChannel()

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 100,
                    "message": {
                        "text": "hello bot",
                        "from": {"id": 42, "first_name": "Alice"},
                    },
                },
                {
                    "update_id": 101,
                    "message": {
                        "text": "another msg",
                        "from": {"id": 43, "username": "bob"},
                    },
                },
            ],
        }

        with patch.object(ch._client, "get", return_value=mock_response):
            messages = ch._poll()

        assert len(messages) == 2
        assert messages[0].text == "hello bot"
        assert messages[0].user_id == "42"
        assert messages[0].user_name == "Alice"
        assert messages[1].user_name == "bob"
        # Offset should be advanced
        assert ch._offset == 102

    def test_poll_filters_non_allowed_users(self, monkeypatch):
        monkeypatch.setenv("MADCOP_TELEGRAM_BOT_TOKEN", "test-token")
        from madcop.channels.telegram import TelegramChannel
        ch = TelegramChannel(allowed_user_ids={42})

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": [
                {
                    "update_id": 100,
                    "message": {
                        "text": "allowed",
                        "from": {"id": 42, "first_name": "A"},
                    },
                },
                {
                    "update_id": 101,
                    "message": {
                        "text": "not allowed",
                        "from": {"id": 99, "first_name": "B"},
                    },
                },
            ],
        }

        with patch.object(ch._client, "get", return_value=mock_response):
            messages = ch._poll()
        assert len(messages) == 1
        assert messages[0].text == "allowed"

    def test_poll_handles_timeout(self, monkeypatch):
        monkeypatch.setenv("MADCOP_TELEGRAM_BOT_TOKEN", "test-token")
        from madcop.channels.telegram import TelegramChannel
        import httpx
        ch = TelegramChannel()

        with patch.object(ch._client, "get", side_effect=httpx.TimeoutException("timeout")):
            messages = ch._poll()
        assert messages == []

    def test_poll_handles_api_error(self, monkeypatch):
        monkeypatch.setenv("MADCOP_TELEGRAM_BOT_TOKEN", "test-token")
        from madcop.channels.telegram import TelegramChannel
        ch = TelegramChannel()

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        with patch.object(ch._client, "get", return_value=mock_response):
            messages = ch._poll()
        assert messages == []

    def test_send_truncates_long_messages(self, monkeypatch):
        monkeypatch.setenv("MADCOP_TELEGRAM_BOT_TOKEN", "test-token")
        from madcop.channels.telegram import TelegramChannel
        ch = TelegramChannel()
        long = "x" * 5000

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch.object(ch._client, "post", return_value=mock_response) as mock_post:
            ch._send_impl("42", long)
            # Verify the text was truncated
            call_args = mock_post.call_args
            sent_text = call_args.kwargs["json"]["text"]
            assert len(sent_text) <= 4000
            assert sent_text.endswith("...")


# --------------------------------------------------------------------------- #
# DiscordChannel
# --------------------------------------------------------------------------- #


class TestDiscordChannel:
    def test_requires_token_for_send(self, monkeypatch):
        monkeypatch.delenv("MADCOP_DISCORD_BOT_TOKEN", raising=False)
        from madcop.channels.discord import DiscordChannel
        ch = DiscordChannel()
        with pytest.raises(RuntimeError, match="bot_token"):
            ch._send_impl("123", "hello")

    def test_handle_webhook_post(self, monkeypatch):
        monkeypatch.delenv("MADCOP_DISCORD_BOT_TOKEN", raising=False)
        from madcop.channels.discord import DiscordChannel
        ch = DiscordChannel()
        ch.handle_webhook_post({
            "content": "hi from discord",
            "user_id": "u1",
            "username": "alice",
            "channel_id": "c1",
        })
        msgs = ch._poll()
        assert len(msgs) == 1
        assert msgs[0].text == "hi from discord"
        assert msgs[0].user_name == "alice"

    def test_webhook_filters_channels(self, monkeypatch):
        monkeypatch.delenv("MADCOP_DISCORD_BOT_TOKEN", raising=False)
        from madcop.channels.discord import DiscordChannel
        ch = DiscordChannel(allowed_channel_ids={"allowed"})
        ch.handle_webhook_post({
            "content": "hi",
            "channel_id": "not-allowed",
        })
        ch.handle_webhook_post({
            "content": "hi",
            "channel_id": "allowed",
        })
        msgs = ch._poll()
        assert len(msgs) == 1

    def test_send_via_bot_api(self, monkeypatch):
        monkeypatch.setenv("MADCOP_DISCORD_BOT_TOKEN", "test-discord-token")
        from madcop.channels.discord import DiscordChannel
        ch = DiscordChannel()

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = mock_response
            ch._send_impl("channel123", "hello discord")

            call_args = mock_client.post.call_args
            assert "channels/channel123/messages" in call_args.args[0]
            assert "Bot test-discord-token" in call_args.kwargs["headers"]["Authorization"]
            assert call_args.kwargs["json"]["content"] == "hello discord"

    def test_send_failure_raises(self, monkeypatch):
        monkeypatch.setenv("MADCOP_DISCORD_BOT_TOKEN", "test-token")
        from madcop.channels.discord import DiscordChannel
        ch = DiscordChannel()

        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"

        with patch("httpx.Client") as mock_client_cls:
            mock_client = mock_client_cls.return_value.__enter__.return_value
            mock_client.post.return_value = mock_response
            with pytest.raises(RuntimeError):
                ch._send_impl("ch1", "x")

    def test_empty_webhook_post_ignored(self, monkeypatch):
        monkeypatch.delenv("MADCOP_DISCORD_BOT_TOKEN", raising=False)
        from madcop.channels.discord import DiscordChannel
        ch = DiscordChannel()
        ch.handle_webhook_post({"content": ""})  # empty
        ch.handle_webhook_post({})  # no content
        msgs = ch._poll()
        assert msgs == []
