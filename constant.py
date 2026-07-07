# enums.py
from enum import Enum

class ServerCommand(str, Enum):
    """Server -> Node 的指令入口"""
    GET_DEVICES = "get_devices"      # 获取所有设备列表 + 健康状态
    UPDATE_STREAM = "update_stream"  # 启用/禁用某个设备的推流

class DeviceStatus(str, Enum):
    """Node 维护的设备状态"""
    ONLINE = "online"
    OFFLINE = "offline"
    STREAMING = "streaming"   # 正在推流
    IDLE = "idle"             # 在线但未推流




