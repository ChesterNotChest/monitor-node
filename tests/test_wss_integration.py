"""WSS 全链路集成测试 — 使用 Python websockets.serve() 启动假 WSS 服务器 (Server-aligned protocol)."""

from __future__ import annotations

import asyncio
import json

import pytest
import websockets

from constant import AuthStatus, DeviceStatus
from network.command_handler import CommandHandler
from network.models import (
    DeviceItem,
    set_cached_devices,
    clear_server_device_maps,
)
from network.wss_client import WssClient

# ---------------------------------------------------------------------------
# Mock WSS Server (Server-aligned protocol)
# ---------------------------------------------------------------------------


class MockWssServer:
    """使用 websockets.serve() 的假 WSS 服务器，对齐 Server 协议。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self._server = None
        self.received_messages: list[dict] = []

    async def start(self):
        self._server = await websockets.serve(self._handler, self.host, self.port)
        for sock in self._server.sockets:
            addr = sock.getsockname()
            self.port = addr[1]
            break

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handler(self, ws):
        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                self.received_messages.append(data)

                # 认证：收到 {"token":"xxx"} → 回传 session_token + device maps
                if "token" in data:
                    resp = {
                        "session_token": "sess-test-001",
                        "videos": [{"id": 1, "name": "Integrated Camera"}],
                        "audios": [{"id": 2, "name": "Microphone Array"}],
                    }
                    await ws.send(json.dumps(resp))

                # 心跳
                elif data.get("type") == "heartbeat":
                    pass

        except websockets.exceptions.ConnectionClosed:
            pass


@pytest.fixture
async def mock_server():
    server = MockWssServer()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
def sample_devices():
    return [
        DeviceItem(
            device_id="video-Integrated Camera",
            device_type="video",
            device_name="Integrated Camera",
            status=DeviceStatus.IDLE,
        ),
    ]


# ---------------------------------------------------------------------------
# Integration tests
# ---------------------------------------------------------------------------


class TestWssIntegration:
    @pytest.mark.asyncio
    async def test_connection_and_auth(self, mock_server, monkeypatch):
        """WSS 连接 + 认证：发送 {"token":"xxx"}，接收 session_token + maps。"""
        monkeypatch.setenv("DEBUG_WSS", "true")
        monkeypatch.setenv("SECRET_KEY", "test-secret")

        client = WssClient(url=f"ws://127.0.0.1:{mock_server.port}/ws")
        handler = CommandHandler(client)
        client.set_message_handler(handler.dispatch)

        await client._connect()
        assert client._connected

        result = await client._authenticate()
        assert result is True
        assert client.session_token == "sess-test-001"
        assert client._auth_status == AuthStatus.AUTHENTICATED

        # 验证 mock server 收到了 token 消息
        token_msgs = [m for m in mock_server.received_messages if "token" in m]
        assert len(token_msgs) >= 1

        await client._disconnect()

    @pytest.mark.asyncio
    async def test_update_stream_full_chain(self, mock_server, sample_devices, monkeypatch):
        """UPDATE_STREAM 全链路：映射表已由认证填充，handler 反查 device_name。"""
        from services.device_registry import device_registry

        monkeypatch.setenv("DEBUG_WSS", "true")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        set_cached_devices(sample_devices)
        await device_registry.clear()

        client = WssClient(url=f"ws://127.0.0.1:{mock_server.port}/ws")
        handler = CommandHandler(client)
        client.set_message_handler(handler.dispatch)

        await client._connect()
        await client._authenticate()

        await handler.handle_update_stream({
            "command": "UPDATE_STREAM",
            "device_type": "video",
            "device_id": 1,
            "enable": True,
        })

        # 验证设备已加入 registry
        registry_snapshot = await device_registry.snapshot()
        found = any(
            d.device_name == "Integrated Camera" and d.device_type == "video"
            for d in registry_snapshot.values()
        )
        assert found is True

        await client._disconnect()

    @pytest.mark.asyncio
    async def test_unknown_command(self, mock_server, monkeypatch):
        """未知命令。"""
        monkeypatch.setenv("DEBUG_WSS", "true")
        monkeypatch.setenv("SECRET_KEY", "test-secret")

        client = WssClient(url=f"ws://127.0.0.1:{mock_server.port}/ws")
        handler = CommandHandler(client)
        client.set_message_handler(handler.dispatch)

        await client._connect()
        await client._authenticate()

        await handler.dispatch({"command": "get_devices"})

        await client._disconnect()
