"""Unit tests for CommandHandler — dispatch and business logic."""

from __future__ import annotations

import pytest

from constant import AuthStatus, DeviceStatus, NodeResponse, ServerCommand
from network.command_handler import CommandHandler
from network.models import DeviceItem, set_cached_devices


# ---------------------------------------------------------------------------
# Mock WssClient
# ---------------------------------------------------------------------------


class MockWssClient:
    """假 WSS 客户端，拦截 send() 调用到 sent_messages 列表。"""

    def __init__(self, node_id: str = "test-node-001") -> None:
        self.sent_messages: list[dict] = []
        self._node_id = node_id
        self._auth_status = AuthStatus.AUTHENTICATED
        self._connected = True

    @property
    def node_id(self) -> str:
        return self._node_id

    @property
    def is_authenticated(self) -> bool:
        return True

    async def send(self, data: dict) -> bool:
        self.sent_messages.append(data)
        return True


@pytest.fixture
def mock_wss():
    return MockWssClient()


@pytest.fixture
def handler(mock_wss):
    return CommandHandler(mock_wss)


@pytest.fixture
def sample_devices():
    return [
        DeviceItem(
            device_id="cam-01",
            device_type="video",
            device_name="Integrated Camera",
            status=DeviceStatus.IDLE,
        ),
        DeviceItem(
            device_id="mic-01",
            device_type="audio",
            device_name="Microphone Array",
            status=DeviceStatus.IDLE,
        ),
    ]


# ---------------------------------------------------------------------------
# Dispatch tests (TC-D01 → TC-D05)
# ---------------------------------------------------------------------------


class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_get_devices(self, handler, mock_wss, sample_devices):
        """TC-D01: dispatch 命中 get_devices。"""
        set_cached_devices(sample_devices)

        await handler.dispatch({"command": "get_devices", "node_id": "n1"})

        assert len(mock_wss.sent_messages) == 1
        resp = mock_wss.sent_messages[0]
        assert resp["type"] == NodeResponse.GET_DEVICES_RESPONSE
        assert resp["total_count"] == 2

    @pytest.mark.asyncio
    async def test_dispatch_update_stream_enable(self, handler, mock_wss, sample_devices):
        """TC-D02: dispatch 命中 update_stream（启用）。"""
        set_cached_devices(sample_devices)

        await handler.dispatch({
            "command": "update_stream",
            "node_id": "n1",
            "device_id": "cam-01",
            "enabled": True,
        })

        assert len(mock_wss.sent_messages) == 1
        resp = mock_wss.sent_messages[0]
        assert resp["type"] == NodeResponse.UPDATE_STREAM_RESPONSE
        assert resp["success"] is True
        assert resp["message"] == "推流已启动"

    @pytest.mark.asyncio
    async def test_dispatch_update_stream_disable(self, handler, mock_wss):
        """TC-D03: dispatch 命中 update_stream（停用）。"""
        # 设备不在 registry 中也可以成功 disable
        await handler.dispatch({
            "command": "update_stream",
            "node_id": "n1",
            "device_id": "cam-01",
            "enabled": False,
        })

        assert len(mock_wss.sent_messages) == 1
        resp = mock_wss.sent_messages[0]
        assert resp["type"] == NodeResponse.UPDATE_STREAM_RESPONSE
        assert resp["message"] == "推流已停止"

    @pytest.mark.asyncio
    async def test_dispatch_unknown_command(self, handler, mock_wss):
        """TC-D04: dispatch 收到未知命令。"""
        await handler.dispatch({"command": "nonexistent"})

        assert len(mock_wss.sent_messages) == 1
        resp = mock_wss.sent_messages[0]
        assert resp["type"] == NodeResponse.ERROR
        assert "unknown command" in resp["message"]

    @pytest.mark.asyncio
    async def test_dispatch_missing_command(self, handler, mock_wss):
        """TC-D05: dispatch 收到无 command 字段的消息。"""
        await handler.dispatch({"other_field": "x"})

        assert len(mock_wss.sent_messages) == 1
        resp = mock_wss.sent_messages[0]
        assert resp["type"] == NodeResponse.ERROR
        assert "unknown command" in resp["message"]


# ---------------------------------------------------------------------------
# handle_get_devices tests (TC-GD01 → TC-GD05)
# ---------------------------------------------------------------------------


class TestHandleGetDevices:
    @pytest.mark.asyncio
    async def test_all_devices(self, handler, mock_wss, sample_devices):
        """TC-GD01: 缓存有设备时返回全部。"""
        set_cached_devices(sample_devices)

        await handler.handle_get_devices({"node_id": "n1"})

        resp = mock_wss.sent_messages[0]
        assert resp["total_count"] == 2
        assert len(resp["devices"]) == 2

    @pytest.mark.asyncio
    async def test_empty_cache(self, handler, mock_wss):
        """TC-GD02: 缓存为空。"""
        set_cached_devices([])

        await handler.handle_get_devices({"node_id": "n1"})

        resp = mock_wss.sent_messages[0]
        assert resp["total_count"] == 0
        assert resp["devices"] == []

    @pytest.mark.asyncio
    async def test_filter_by_video(self, handler, mock_wss, sample_devices):
        """TC-GD03: 按 device_type 过滤。"""
        set_cached_devices(sample_devices)

        await handler.handle_get_devices({"node_id": "n1", "device_type": "video"})

        resp = mock_wss.sent_messages[0]
        assert resp["total_count"] == 1
        assert resp["devices"][0]["device_type"] == "video"

    @pytest.mark.asyncio
    async def test_filter_no_match(self, handler, mock_wss, sample_devices):
        """TC-GD04: 过滤类型无匹配。"""
        set_cached_devices([sample_devices[0]])  # only video

        await handler.handle_get_devices({"node_id": "n1", "device_type": "audio"})

        resp = mock_wss.sent_messages[0]
        assert resp["total_count"] == 0
        assert resp["devices"] == []

    @pytest.mark.asyncio
    async def test_node_id_passthrough(self, handler, mock_wss):
        """TC-GD05: node_id 透传。"""
        set_cached_devices([])

        await handler.handle_get_devices({"node_id": "node-xyz"})

        resp = mock_wss.sent_messages[0]
        assert resp["node_id"] == "node-xyz"


# ---------------------------------------------------------------------------
# handle_update_stream tests (TC-US01 → TC-US06)
# ---------------------------------------------------------------------------


class TestHandleUpdateStream:
    @pytest.mark.asyncio
    async def test_enable_known_device(self, handler, mock_wss, sample_devices):
        """TC-US01: 启用，设备在缓存中。"""
        from services.device_registry import device_registry

        set_cached_devices(sample_devices)
        # 确保 registry 初始为空
        await device_registry.clear()

        await handler.handle_update_stream({
            "node_id": "n1",
            "device_id": "cam-01",
            "enabled": True,
        })

        assert await device_registry.contains("cam-01") is True
        resp = mock_wss.sent_messages[0]
        assert resp["type"] == NodeResponse.UPDATE_STREAM_RESPONSE
        assert resp["success"] is True
        assert resp["message"] == "推流已启动"

    @pytest.mark.asyncio
    async def test_enable_unknown_device(self, handler, mock_wss):
        """TC-US02: 启用，设备不在缓存中。"""
        from services.device_registry import device_registry

        set_cached_devices([])
        await device_registry.clear()

        await handler.handle_update_stream({
            "node_id": "n1",
            "device_id": "cam-unknown",
            "enabled": True,
        })

        assert await device_registry.contains("cam-unknown") is True
        device = await device_registry.get("cam-unknown")
        assert device.device_type == "unknown"

    @pytest.mark.asyncio
    async def test_disable_device(self, handler, mock_wss, sample_devices):
        """TC-US03: 停用，设备在 registry 中。"""
        from services.device_registry import device_registry

        set_cached_devices(sample_devices)
        await device_registry.clear()
        await device_registry.add(sample_devices[0])

        await handler.handle_update_stream({
            "node_id": "n1",
            "device_id": "cam-01",
            "enabled": False,
        })

        assert await device_registry.contains("cam-01") is False
        resp = mock_wss.sent_messages[0]
        assert resp["message"] == "推流已停止"

    @pytest.mark.asyncio
    async def test_missing_device_id(self, handler, mock_wss):
        """TC-US04: 缺少 device_id。"""
        await handler.handle_update_stream({
            "node_id": "n1",
            "enabled": True,
        })

        resp = mock_wss.sent_messages[0]
        assert resp["type"] == NodeResponse.ERROR
        assert "missing device_id" in resp["message"]

    @pytest.mark.asyncio
    async def test_empty_device_id(self, handler, mock_wss):
        """TC-US05: device_id 为空字符串。"""
        await handler.handle_update_stream({
            "node_id": "n1",
            "device_id": "",
            "enabled": True,
        })

        resp = mock_wss.sent_messages[0]
        assert resp["type"] == NodeResponse.ERROR
        assert "missing device_id" in resp["message"]

    @pytest.mark.asyncio
    async def test_node_id_passthrough(self, handler, mock_wss, sample_devices):
        """TC-US06: node_id 透传。"""
        set_cached_devices(sample_devices)

        await handler.handle_update_stream({
            "node_id": "node-abc",
            "device_id": "cam-01",
            "enabled": True,
        })

        resp = mock_wss.sent_messages[0]
        assert resp["node_id"] == "node-abc"
