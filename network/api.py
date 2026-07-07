"""
通过 WSS 接收请求。
此处定义具体每种事件的处置入口。
"""

from typing import Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from constant import DeviceStatus, ServerCommand 

router = APIRouter(tags=["Device"])


# ============================================================
# Pydantic models
# ============================================================


class GetDeviceListInput(BaseModel):
    node_id: str
    device_type: Literal["video", "audio"] | None = None


class DeviceItem(BaseModel):
    device_id: str
    device_type: str
    device_name: str
    status: DeviceStatus


class GetDeviceListOutput(BaseModel):
    node_id: str
    devices: list[DeviceItem]
    total_count: int


class UpdateDeviceInput(BaseModel):
    node_id: str
    device_id: str
    enabled: bool


class UpdateDeviceOutput(BaseModel):
    node_id: str
    device_id: str
    enabled: bool
    success: bool
    message: str



# ============================================================
# WebSocket 入口
# ============================================================


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 推送通道。"""
    await ws.accept()
    try:
        while True:
            data = await ws.receive_text()
            # 路由分发由调用方处理
            # 你可以在这里根据 data 中的 "command" 字段
            # 调用 get_device_list 或 update_device_usage 的处理逻辑
    except WebSocketDisconnect:
        pass


#################
# 接收输入设备列表请求
@router.post("/device/list", response_model=GetDeviceListOutput)
async def get_device_list(input: GetDeviceListInput) -> GetDeviceListOutput:
    """获取节点下的设备列表。

    输入格式:
        {
            "node_id": "string", 
            "device_type": "video"
        }
    输出格式:
        {
            "node_id": "string", 
            "devices": [...], 
            "total_count": 0
        }
    """
    return GetDeviceListOutput(
        node_id=input.node_id,
        devices=[],
        total_count=0,
    )
#################


#################
# 接收变动设备情况请求（流传输启用与否）
@router.post("/device/update", response_model=UpdateDeviceOutput)
async def update_device_usage(input: UpdateDeviceInput) -> UpdateDeviceOutput:
    """更新设备流传输状态。

    输入格式:
        {
            "node_id": "string", 
            "device_id": "string", 
            "enabled": true
        }
    输出格式:
        {
            "node_id": "string",
            "device_id": "string", 
            "enabled": true, 
            "success": true, 
            "message": "推流已启动"
        }
    """
    return UpdateDeviceOutput(
        node_id=input.node_id,
        device_id=input.device_id,
        enabled=input.enabled,
        success=True,
        message="处理成功（占位）",
    )
#################