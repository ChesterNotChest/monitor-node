"""共享数据模型——Pydantic 模型与设备缓存。

从 ``network/api.py`` 迁出，供 services 各模块和 command_handler 引用。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from constant import DeviceStatus


# ============================================================
# Pydantic models
# ============================================================


class DeviceItem(BaseModel):
    """采集设备实体。"""
    device_id: str
    device_type: str
    device_name: str
    status: DeviceStatus = DeviceStatus.IDLE


class GetDeviceListInput(BaseModel):
    """获取设备列表的请求参数（WSS 模式下 handler 手动解包 dict，保留作为类型参考）。"""
    node_id: str
    device_type: Literal["video", "audio"] | None = None


class GetDeviceListOutput(BaseModel):
    """获取设备列表的响应。"""
    node_id: str
    devices: list[DeviceItem]
    total_count: int


class UpdateDeviceInput(BaseModel):
    """更新设备推流状态的请求参数（WSS 模式下 handler 手动解包 dict，保留作为类型参考）。"""
    node_id: str
    device_id: str
    enabled: bool


class UpdateDeviceOutput(BaseModel):
    """更新设备推流状态的响应。"""
    node_id: str
    device_id: str
    enabled: bool
    success: bool
    message: str


# ============================================================
# 设备缓存（启动时填充，供 command_handler 查询）
# ============================================================

_cached_devices: list[DeviceItem] = []


def set_cached_devices(devices: list[DeviceItem]) -> None:
    """更新设备缓存（启动时和重枚举后调用）。"""
    global _cached_devices
    _cached_devices = devices


def get_cached_devices() -> list[DeviceItem]:
    """返回缓存的设备列表。"""
    return _cached_devices


# ============================================================
# Server 设备映射表（WSS 认证握手时由 Server 下发，供 UPDATE_STREAM 反查）
# ============================================================

_server_video_map: dict[int, str] = {}
_server_audio_map: dict[int, str] = {}


def set_server_device_maps(videos: list[dict], audios: list[dict]) -> None:
    """解析 Server 下发的 `{id, name}` 列表并写入映射表。

    Args:
        videos: [{"id": 1, "name": "Integrated Camera"}, ...]
        audios: [{"id": 2, "name": "Microphone Array"}, ...]
    """
    global _server_video_map, _server_audio_map
    _server_video_map = {item["id"]: item["name"] for item in videos}
    _server_audio_map = {item["id"]: item["name"] for item in audios}


def get_server_device_name(device_type: str, device_id: int) -> str | None:
    """从 Server 映射表反查 device_name。

    Args:
        device_type: ``"video"`` 或 ``"audio"``
        device_id: Server 侧数据库 ID

    Returns:
        设备名称，未找到返回 None
    """
    if device_type == "video":
        return _server_video_map.get(device_id)
    elif device_type == "audio":
        return _server_audio_map.get(device_id)
    return None


def get_server_device_id(device_type: str, device_name: str) -> int | None:
    """从 Server 映射表反查 device_id（按名称匹配）。

    用于 RTMP URL 构造：根据本地 device_name 查找 Server 侧 device_id。
    """
    target_map = _server_video_map if device_type == "video" else _server_audio_map
    for sid, sname in target_map.items():
        if sname == device_name:
            return sid
    return None


def clear_server_device_maps() -> None:
    """清空 Server 设备映射表。"""
    global _server_video_map, _server_audio_map
    _server_video_map = {}
    _server_audio_map = {}
