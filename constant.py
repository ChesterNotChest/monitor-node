# enums.py
from enum import Enum


class ServerCommand(str, Enum):
    """Server -> Node 的指令入口"""
    UPDATE_STREAM = "UPDATE_STREAM"  # 启用/禁用某个设备的推流


class AuthStatus(str, Enum):
    """WSS 认证状态"""
    PENDING = "pending"            # 已连接，等待认证
    AUTHENTICATED = "authenticated"  # 认证成功
    REJECTED = "rejected"          # 认证被拒绝


class DeviceStatus(str, Enum):
    """Node 维护的设备状态"""
    ONLINE = "online"
    OFFLINE = "offline"
    STREAMING = "streaming"   # 正在推流
    IDLE = "idle"             # 在线但未推流
