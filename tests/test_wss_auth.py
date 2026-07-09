"""Unit tests for WSS client authentication flow (Server-aligned protocol)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, patch

import pytest
import websockets

from constant import AuthStatus
from network.models import clear_server_device_maps
from network.wss_client import WssClient


@pytest.fixture
def wss_client():
    """Fresh WSS client with a test URL, not started."""
    return WssClient(url="ws://test.local:8080/ws")


# ---------------------------------------------------------------------------
# Token resolution
# ---------------------------------------------------------------------------


class TestTokenResolution:
    def test_debug_wss_uses_fixed_token(self, wss_client, monkeypatch):
        """DEBUG_WSS=true 时使用固定 Token。"""
        monkeypatch.setenv("DEBUG_WSS", "true")
        assert wss_client._resolve_token() == "debug-token-fixed"

    def test_production_uses_secret_key(self, wss_client, monkeypatch):
        """非 DEBUG_WSS 时使用 SECRET_KEY。"""
        monkeypatch.setenv("DEBUG_WSS", "false")
        monkeypatch.setenv("SECRET_KEY", "my-secret-token")
        assert wss_client._resolve_token() == "my-secret-token"


# ---------------------------------------------------------------------------
# URL resolution
# ---------------------------------------------------------------------------


class TestUrlResolution:
    def test_debug_wss_url(self, monkeypatch):
        """DEBUG_WSS 时使用 ws://127.0.0.1:{WSS_PORT}/ws。"""
        monkeypatch.setenv("DEBUG_WSS", "true")
        monkeypatch.setenv("WSS_PORT", "9443")
        client = WssClient()
        url = client._resolve_url()
        assert url == "ws://127.0.0.1:9443/ws"

    def test_production_url(self, monkeypatch):
        """非 DEBUG_WSS 时使用 wss://{SERVER_BASE_URL}:{WSS_PORT}/ws。"""
        monkeypatch.setenv("DEBUG_WSS", "false")
        monkeypatch.setenv("SERVER_BASE_URL", "my-server.example.com")
        monkeypatch.setenv("WSS_PORT", "8443")
        client = WssClient()
        url = client._resolve_url()
        assert url == "wss://my-server.example.com:8443/ws"


# ---------------------------------------------------------------------------
# Authenticate flow
# ---------------------------------------------------------------------------


class TestAuthenticate:
    @pytest.mark.asyncio
    async def test_sends_token_and_receives_session(self, wss_client, monkeypatch):
        """_authenticate 发送 {"token":"xxx"}，接收 session_token + device maps。"""
        monkeypatch.setenv("DEBUG_WSS", "true")

        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({
                "session_token": "sess-test-123",
                "videos": [{"id": 1, "name": "Integrated Camera"}],
                "audios": [{"id": 2, "name": "Microphone Array"}],
            }),
            websockets.exceptions.ConnectionClosed(None, None),
        ])
        wss_client._ws = mock_ws
        wss_client._connected = True

        result = await wss_client._authenticate()

        assert result is True
        assert wss_client._session_token == "sess-test-123"
        assert wss_client._auth_status == AuthStatus.AUTHENTICATED
        # 验证发送了 token 消息（无 type 包装）
        assert mock_ws.send.called
        sent = json.loads(mock_ws.send.call_args[0][0])
        assert sent == {"token": "debug-token-fixed"}

    @pytest.mark.asyncio
    async def test_authenticate_timeout(self, wss_client, monkeypatch):
        """recv 持续超时 → 认证超时返回 False。"""
        monkeypatch.setenv("DEBUG_WSS", "true")

        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=asyncio.TimeoutError())
        wss_client._ws = mock_ws
        wss_client._connected = True

        with patch("network.wss_client._AUTH_TIMEOUT", 0.01):
            result = await wss_client._authenticate()

        assert result is False
        assert wss_client._auth_status == AuthStatus.REJECTED

    @pytest.mark.asyncio
    async def test_authenticate_buffers_non_auth(self, wss_client, monkeypatch):
        """认证期间收到的非 session_token 消息被缓冲，认证后交给 handler。"""
        monkeypatch.setenv("DEBUG_WSS", "true")

        received = []

        async def handler(data):
            received.append(data)

        wss_client.set_message_handler(handler)

        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        mock_ws.recv = AsyncMock(side_effect=[
            json.dumps({"command": "UPDATE_STREAM", "device_type": "video", "device_id": 1, "enable": True}),
            json.dumps({"session_token": "sess-test", "videos": [], "audios": []}),
            websockets.exceptions.ConnectionClosed(None, None),
        ])
        wss_client._ws = mock_ws
        wss_client._connected = True

        result = await wss_client._authenticate()

        assert result is True
        assert len(received) == 1
        assert received[0]["command"] == "UPDATE_STREAM"


# ---------------------------------------------------------------------------
# Disconnect clears auth state
# ---------------------------------------------------------------------------


class TestDisconnectClearsAuth:
    @pytest.mark.asyncio
    async def test_disconnect_resets_auth(self, wss_client):
        """断连时清除 session_token 和 auth_status。"""
        wss_client._session_token = "some-session"
        wss_client._auth_status = AuthStatus.AUTHENTICATED
        wss_client._connected = True
        wss_client._ws = AsyncMock()
        wss_client._ws.close = AsyncMock()

        await wss_client._disconnect()

        assert wss_client._session_token is None
        assert wss_client._auth_status == AuthStatus.PENDING
        assert wss_client._connected is False


# ---------------------------------------------------------------------------
# Send blocked before auth
# ---------------------------------------------------------------------------


class TestSendBlocked:
    @pytest.mark.asyncio
    async def test_send_blocked_when_pending(self, wss_client):
        """认证前 send 被阻止。"""
        mock_ws = AsyncMock()
        wss_client._ws = mock_ws
        wss_client._connected = True
        wss_client._auth_status = AuthStatus.PENDING

        result = await wss_client.send({"type": "test"})
        assert result is False

    @pytest.mark.asyncio
    async def test_send_allowed_when_authenticated(self, wss_client):
        """认证后 send 正常发送。"""
        mock_ws = AsyncMock()
        mock_ws.send = AsyncMock()
        wss_client._ws = mock_ws
        wss_client._connected = True
        wss_client._auth_status = AuthStatus.AUTHENTICATED

        result = await wss_client.send({"type": "test"})
        assert result is True
        mock_ws.send.assert_called_once()
