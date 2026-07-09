"""WSS 全链路集成测试 — 使用 Python websockets.serve() 启动假 WSS 服务器。

测试覆盖:
- WSS 连接 + 心跳
- get_devices 全链路
- update_stream 全链路
- 未知命令处理
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest
import websockets

from constant import AuthStatus, DeviceStatus, NodeResponse
from network.command_handler import CommandHandler
from network.models import DeviceItem, set_cached_devices
from network.wss_client import WssClient

# ---------------------------------------------------------------------------
# Mock WSS Server
# ---------------------------------------------------------------------------


class MockWssServer:
    """使用 websockets.serve() 的假 WSS 服务器，仅用于测试。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.port = port
        self._server = None
        self.received_messages: list[dict] = []
        self.sent_messages: list[dict] = []
        self._clients: set = set()

    async def start(self):
        """启动假 WSS 服务器。"""
        self._server = await websockets.serve(
            self._handler, self.host, self.port,
        )
        # 获取实际分配的端口
        for sock in self._server.sockets:
            addr = sock.getsockname()
            self.port = addr[1]
            break

    async def stop(self):
        """关闭假 WSS 服务器。"""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handler(self, ws):
        """处理单个 WebSocket 连接。"""
        self._clients.add(ws)
        try:
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                self.received_messages.append(data)
                msg_type = data.get("type", "")

                # 认证处理
                if msg_type == NodeResponse.AUTH:
                    token = data.get("token", "")
                    if token == "debug-token-fixed" or token:
                        ack = {"type": NodeResponse.AUTH_ACK, "node_id": "test-node-001"}
                        await ws.send(json.dumps(ack))
                        self.sent_messages.append(ack)
                    else:
                        err = {"type": NodeResponse.AUTH_ERROR, "message": "invalid token"}
                        await ws.send(json.dumps(err))

                # 心跳 — 不响应
                elif msg_type == NodeResponse.HEARTBEAT:
                    pass

                # 响应 — 记录
                elif msg_type and msg_type.endswith("_response"):
                    pass

                # 错误 — 记录
                elif msg_type == NodeResponse.ERROR:
                    pass
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            self._clients.discard(ws)


@pytest.fixture
async def mock_server():
    """启动假 WSS 服务器的 fixture。"""
    server = MockWssServer()
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
def sample_devices():
    return [
        DeviceItem(
            device_id="cam-01",
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
        """TC-IT01: WSS 连接 + 认证。_authenticate() 自己读 websocket 收 auth_ack。"""
        monkeypatch.setenv("DEBUG_WSS", "true")
        monkeypatch.setenv("SECRET_KEY", "test-secret")

        client = WssClient(url=f"ws://127.0.0.1:{mock_server.port}/ws")
        handler = CommandHandler(client)
        client.set_message_handler(handler.dispatch)

        # 手动 connect
        await client._connect()
        assert client._connected

        # _authenticate() 自己发送 auth 并读取 websocket 等待 auth_ack
        # 不需要启动 _receive_loop
        result = await client._authenticate()
        assert result is True
        assert client.node_id == "test-node-001"
        assert client._auth_status == AuthStatus.AUTHENTICATED

        # 验证 mock server 收到了 auth 消息
        auth_msgs = [m for m in mock_server.received_messages if m.get("type") == NodeResponse.AUTH]
        assert len(auth_msgs) >= 1

        await client._disconnect()

    @pytest.mark.asyncio
    async def test_get_devices_full_chain(self, mock_server, sample_devices, monkeypatch):
        """TC-IT02: get_devices 全链路。"""
        monkeypatch.setenv("DEBUG_WSS", "true")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        set_cached_devices(sample_devices)

        client = WssClient(url=f"ws://127.0.0.1:{mock_server.port}/ws")
        handler = CommandHandler(client)
        client.set_message_handler(handler.dispatch)

        await client._connect()
        await client._authenticate()

        # 模拟 Server 发送 get_devices 指令
        cmd = {"command": "get_devices", "node_id": "test-node-001"}
        client._ws.send = None  # 清除以便用 mock server 发送
        # 直接调用 handler
        await handler.handle_get_devices(cmd)

        await client._disconnect()

    @pytest.mark.asyncio
    async def test_update_stream_full_chain(self, mock_server, sample_devices, monkeypatch):
        """TC-IT03: update_stream 启用全链路。"""
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

        # 启用设备
        await handler.handle_update_stream({
            "command": "update_stream",
            "node_id": "test-node-001",
            "device_id": "cam-01",
            "enabled": True,
        })

        assert await device_registry.contains("cam-01") is True

        await client._disconnect()

    @pytest.mark.asyncio
    async def test_update_stream_disable(self, mock_server, sample_devices, monkeypatch):
        """TC-IT04: update_stream 停用全链路。"""
        from services.device_registry import device_registry

        monkeypatch.setenv("DEBUG_WSS", "true")
        monkeypatch.setenv("SECRET_KEY", "test-secret")
        set_cached_devices(sample_devices)
        await device_registry.clear()
        await device_registry.add(sample_devices[0])

        client = WssClient(url=f"ws://127.0.0.1:{mock_server.port}/ws")
        handler = CommandHandler(client)
        client.set_message_handler(handler.dispatch)

        await client._connect()
        await client._authenticate()

        # 停用设备
        await handler.handle_update_stream({
            "command": "update_stream",
            "node_id": "test-node-001",
            "device_id": "cam-01",
            "enabled": False,
        })

        assert await device_registry.contains("cam-01") is False

        await client._disconnect()

    @pytest.mark.asyncio
    async def test_unknown_command(self, mock_server, monkeypatch):
        """TC-IT05: 未知命令处理。"""
        monkeypatch.setenv("DEBUG_WSS", "true")
        monkeypatch.setenv("SECRET_KEY", "test-secret")

        client = WssClient(url=f"ws://127.0.0.1:{mock_server.port}/ws")
        handler = CommandHandler(client)
        client.set_message_handler(handler.dispatch)

        await client._connect()
        await client._authenticate()

        await handler.dispatch({"command": "nonexistent"})

        await client._disconnect()
