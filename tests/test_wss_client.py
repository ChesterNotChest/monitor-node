"""Unit tests for WSS client — mock WebSocket server."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import websockets

from network.wss_client import WssClient


@pytest.fixture
def wss_client():
    """Fresh WSS client instance (not started)."""
    return WssClient(url="ws://test.local:8080/ws")


# ---------------------------------------------------------------------------
# Connection lifecycle
# ---------------------------------------------------------------------------


class TestConnectionLifecycle:
    @pytest.mark.asyncio
    async def test_start_sets_running(self, wss_client):
        """Start should set _running True."""
        # We need to prevent actual connection attempt
        with patch.object(wss_client, "_connect_loop", new_callable=AsyncMock):
            await wss_client.start()
            assert wss_client._running is True

    @pytest.mark.asyncio
    async def test_stop_cleans_up(self, wss_client):
        with patch.object(wss_client, "_connect_loop", new_callable=AsyncMock):
            await wss_client.start()

        await wss_client.stop()
        assert wss_client._running is False
        assert wss_client._connected is False

    @pytest.mark.asyncio
    async def test_double_start_is_noop(self, wss_client):
        with patch.object(wss_client, "_connect_loop", new_callable=AsyncMock) as mock_loop:
            await wss_client.start()
            await wss_client.start()
            mock_loop.assert_called_once()


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


class TestHeartbeat:
    @pytest.mark.asyncio
    async def test_sends_heartbeat_message(self, wss_client):
        """Heartbeat should send {"type": "heartbeat"} periodically."""
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()

        wss_client._ws = mock_ws
        wss_client._connected = True
        wss_client._running = True

        # Run two heartbeat cycles with a short interval
        beat_count = 0
        original_sleep = asyncio.sleep

        async def fast_sleep(duration):
            nonlocal beat_count
            beat_count += 1
            if beat_count > 2:
                # Stop after 2 heartbeats
                wss_client._connected = False
            await original_sleep(0)  # yield to event loop

        with patch("network.wss_client._HEARTBEAT_INTERVAL", 0.01):
            with patch("asyncio.sleep", side_effect=fast_sleep):
                await wss_client._heartbeat_loop()

        assert mock_ws.send.call_count >= 1
        # Verify format
        for call in mock_ws.send.call_args_list:
            data = json.loads(call[0][0])
            assert data["type"] == "heartbeat"


# ---------------------------------------------------------------------------
# Message dispatch
# ---------------------------------------------------------------------------


class TestMessageDispatch:
    @pytest.mark.asyncio
    async def test_dispatches_to_handler(self, wss_client):
        received = []

        async def handler(data):
            received.append(data)

        wss_client.set_message_handler(handler)

        mock_ws = AsyncMock()
        messages = [
            json.dumps({"command": "get_devices", "node_id": "n1"}),
            json.dumps({"command": "update_stream", "device_id": "cam-01", "enabled": True}),
        ]
        mock_ws.recv = AsyncMock(side_effect=messages + [websockets.exceptions.ConnectionClosed(None, None)])

        wss_client._ws = mock_ws
        wss_client._connected = True
        wss_client._running = True

        await wss_client._receive_loop()

        assert len(received) == 2
        assert received[0]["command"] == "get_devices"
        assert received[1]["command"] == "update_stream"

    @pytest.mark.asyncio
    async def test_handles_invalid_json(self, wss_client):
        received = []

        async def handler(data):
            received.append(data)

        wss_client.set_message_handler(handler)

        mock_ws = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            "not valid json{{{",
            json.dumps({"command": "get_devices"}),
            websockets.exceptions.ConnectionClosed(None, None),
        ])

        wss_client._ws = mock_ws
        wss_client._connected = True
        wss_client._running = True

        await wss_client._receive_loop()

        # Only the valid JSON message should be dispatched
        assert len(received) == 1
        assert received[0]["command"] == "get_devices"


# ---------------------------------------------------------------------------
# Send
# ---------------------------------------------------------------------------


class TestSend:
    @pytest.mark.asyncio
    async def test_send_when_connected(self, wss_client):
        mock_ws = AsyncMock()
        wss_client._ws = mock_ws
        wss_client._connected = True

        result = await wss_client.send({"type": "test", "payload": "hello"})
        assert result is True
        mock_ws.send.assert_called_once()
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent["type"] == "test"

    @pytest.mark.asyncio
    async def test_send_when_disconnected(self, wss_client):
        wss_client._connected = False
        result = await wss_client.send({"type": "test"})
        assert result is False


# ---------------------------------------------------------------------------
# Backoff
# ---------------------------------------------------------------------------


class TestBackoff:
    def test_initial_backoff(self, wss_client):
        assert wss_client._backoff == 1.0

    def test_backoff_doubles(self, wss_client):
        backoffs = []
        for _ in range(5):
            backoffs.append(wss_client._backoff)
            wss_client._backoff = min(wss_client._backoff * 2, 60.0)
        assert backoffs == [1.0, 2.0, 4.0, 8.0, 16.0]

    def test_backoff_capped_at_60(self, wss_client):
        wss_client._backoff = 32.0
        wss_client._backoff = min(wss_client._backoff * 2, 60.0)
        assert wss_client._backoff == 60.0
        # Should stay at 60
        wss_client._backoff = min(wss_client._backoff * 2, 60.0)
        assert wss_client._backoff == 60.0


# ---------------------------------------------------------------------------
# Default handler
# ---------------------------------------------------------------------------


class TestDefaultHandler:
    @pytest.mark.asyncio
    async def test_default_handler_does_not_crash(self, wss_client):
        """Default handler should process messages without errors."""
        await wss_client._default_handler({"command": "unknown", "data": "test"})
        # No exception = pass
