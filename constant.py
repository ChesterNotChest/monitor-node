# enums.py
from enum import Enum


class ServerCommand(str, Enum):
    """Server -> Node 的指令入口"""
    GET_DEVICES = "get_devices"      # 获取所有设备列表 + 健康状态
    UPDATE_STREAM = "update_stream"  # 启用/禁用某个设备的推流


class NodeResponse(str, Enum):
    """Node -> Server 的响应类型"""
    AUTH = "auth"                                # Node 发送身份认证
    AUTH_ACK = "auth_ack"                        # Server 回传认证成功 + NodeID
    AUTH_ERROR = "auth_error"                    # Server 回传认证失败
    GET_DEVICES_RESPONSE = "get_devices_response"      # 设备列表响应
    UPDATE_STREAM_RESPONSE = "update_stream_response"  # 推流状态变更响应
    HEARTBEAT = "heartbeat"                      # 心跳
    ERROR = "error"                              # 通用错误响应


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
