"""Unit tests for CommandHandler — dispatch and business logic (Server-aligned protocol)."""

from __future__ import annotations

import pytest

from constant import AuthStatus, DeviceStatus, ServerCommand
from network.command_handler import CommandHandler
from network.models import (
    DeviceItem,
    set_cached_devices,
    set_server_device_maps,
    clear_server_device_maps,
)


# ---------------------------------------------------------------------------
# Mock WssClient
# ---------------------------------------------------------------------------


class MockWssClient:
    """假 WSS 客户端，拦截 send() 调用到 sent_messages 列表。"""

    def __init__(self) -> None:
        self.sent_messages: list[dict] = []
        self._session_token = "sess-test-001"
        self._auth_status = AuthStatus.AUTHENTICATED
        self._connected = True

    @property
    def session_token(self) -> str:
        return self._session_token

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
            device_id="video-Integrated Camera",
            device_type="video",
            device_name="Integrated Camera",
            status=DeviceStatus.IDLE,
        ),
        DeviceItem(
            device_id="audio-Microphone Array",
            device_type="audio",
            device_name="Microphone Array",
            status=DeviceStatus.IDLE,
        ),
    ]


@pytest.fixture(autouse=True)
def setup_device_maps(sample_devices):
    """每个测试前设置 Server 设备映射表。"""
    set_server_device_maps(
        videos=[{"id": 1, "name": "Integrated Camera"}],
        audios=[{"id": 2, "name": "Microphone Array"}],
    )
    set_cached_devices(sample_devices)
    yield
    clear_server_device_maps()


# ---------------------------------------------------------------------------
# Dispatch tests
# ---------------------------------------------------------------------------


class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_update_stream_enable(self, handler, mock_wss):
        """dispatch 命中 UPDATE_STREAM（启用视频设备）。"""
        await handler.dispatch({
            "command": "UPDATE_STREAM",
            "device_type": "video",
            "device_id": 1,
            "enable": True,
        })

        assert len(mock_wss.sent_messages) == 1
        resp = mock_wss.sent_messages[0]
        assert resp["type"] == "update_stream_response"
        assert resp["success"] is True
        assert "推流已启动" in resp["message"]

    @pytest.mark.asyncio
    async def test_dispatch_update_stream_disable(self, handler, mock_wss):
        """dispatch 命中 UPDATE_STREAM（停用）。"""
        await handler.dispatch({
            "command": "UPDATE_STREAM",
            "device_type": "audio",
            "device_id": 2,
            "enable": False,
        })

        assert len(mock_wss.sent_messages) == 1
        resp = mock_wss.sent_messages[0]
        assert resp["type"] == "update_stream_response"
        assert resp["success"] is True
        assert resp["message"] == "推流已停止"

    @pytest.mark.asyncio
    async def test_dispatch_unknown_command(self, handler, mock_wss):
        """dispatch 收到未知命令。"""
        await handler.dispatch({"command": "get_devices"})

        assert len(mock_wss.sent_messages) == 1
        resp = mock_wss.sent_messages[0]
        assert resp["type"] == "update_stream_response"
        assert resp["success"] is False
        assert "unknown command" in resp["message"]


# ---------------------------------------------------------------------------
# handle_update_stream tests
# ---------------------------------------------------------------------------


class TestHandleUpdateStream:
    @pytest.mark.asyncio
    async def test_enable_known_video_device(self, handler, mock_wss):
        """启用设备：映射表命中 + 本地缓存存在。"""
        from services.device_registry import device_registry

        await handler.handle_update_stream({
            "command": "UPDATE_STREAM",
            "device_type": "video",
            "device_id": 1,
            "enable": True,
        })

        resp = mock_wss.sent_messages[0]
        assert resp["type"] == "update_stream_response"
        assert resp["success"] is True
        assert resp["message"] == "推流已启动"

    @pytest.mark.asyncio
    async def test_enable_audio_device(self, handler, mock_wss):
        """启用音频设备：映射表命中 + 本地缓存存在。"""
        await handler.handle_update_stream({
            "command": "UPDATE_STREAM",
            "device_type": "audio",
            "device_id": 2,
            "enable": True,
        })

        resp = mock_wss.sent_messages[0]
        assert resp["type"] == "update_stream_response"
        assert resp["success"] is True

    @pytest.mark.asyncio
    async def test_unknown_device_id(self, handler, mock_wss):
        """映射表中无此 device_id。"""
        await handler.handle_update_stream({
            "command": "UPDATE_STREAM",
            "device_type": "video",
            "device_id": 99,
            "enable": True,
        })

        resp = mock_wss.sent_messages[0]
        assert resp["type"] == "update_stream_response"
        assert resp["success"] is False
        assert "unknown device_id" in resp["message"]

    @pytest.mark.asyncio
    async def test_invalid_device_type(self, handler, mock_wss):
        """无效的 device_type。"""
        await handler.handle_update_stream({
            "command": "UPDATE_STREAM",
            "device_type": "camera",
            "device_id": 1,
            "enable": True,
        })

        resp = mock_wss.sent_messages[0]
        assert resp["type"] == "update_stream_response"
        assert resp["success"] is False
        assert "invalid device_type" in resp["message"]

    @pytest.mark.asyncio
    async def test_device_not_in_local_cache(self, handler, mock_wss):
        """映射表命中但本地缓存无此设备 → 创建占位条目。"""
        from services.device_registry import device_registry

        # 设置映射表包含一个本地没有的设备
        set_server_device_maps(
            videos=[{"id": 3, "name": "Unknown Camera"}],
            audios=[],
        )

        await handler.handle_update_stream({
            "command": "UPDATE_STREAM",
            "device_type": "video",
            "device_id": 3,
            "enable": True,
        })

        resp = mock_wss.sent_messages[0]
        assert resp["type"] == "update_stream_response"
        assert resp["success"] is True
