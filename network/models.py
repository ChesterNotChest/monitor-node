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
