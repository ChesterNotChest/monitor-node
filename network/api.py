"""
REST API and WebSocket endpoints for device management.

POST /api/device/list   — enumerate and return devices
POST /api/device/update — enable/disable device streaming
WS   /api/ws            — WebSocket command channel from Server
"""

from __future__ import annotations

import json
import logging
from typing import Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from constant import DeviceStatus, ServerCommand

logger = logging.getLogger(__name__)

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
    status: DeviceStatus = DeviceStatus.IDLE


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
# In-memory device cache (populated at startup)
# ============================================================

_cached_devices: list[DeviceItem] = []


def set_cached_devices(devices: list[DeviceItem]) -> None:
    """Update the in-memory device cache (called at startup and on re-enumeration)."""
    global _cached_devices
    _cached_devices = devices


def get_cached_devices() -> list[DeviceItem]:
    """Return the cached device list."""
    return _cached_devices


# ============================================================
# WebSocket endpoint
# ============================================================


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket channel for Server → Node commands.

    Accepts JSON messages with a ``command`` field matching ``ServerCommand``::

        {"command": "get_devices", "node_id": "n1"}
        {"command": "update_stream", "node_id": "n1", "device_id": "cam-01", "enabled": true}
    """
    await ws.accept()
    # Lazy import to avoid circular dependency at module level
    from services.device_enumerator import enumerate_devices
    from services.device_registry import device_registry

    try:
        while True:
            raw = await ws.receive_text()
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"error": "invalid json"})
                continue

            command = data.get("command", "")
            logger.debug("WS received command: %s", command)

            if command == ServerCommand.GET_DEVICES:
                node_id = data.get("node_id", "")
                device_type = data.get("device_type")
                devices = get_cached_devices()
                if device_type:
                    devices = [d for d in devices if d.device_type == device_type]
                await ws.send_json({
                    "type": "get_devices_response",
                    "node_id": node_id,
                    "devices": [d.model_dump() for d in devices],
                    "total_count": len(devices),
                })

            elif command == ServerCommand.UPDATE_STREAM:
                device_id = data.get("device_id", "")
                enabled = data.get("enabled", False)
                node_id = data.get("node_id", "")
                if not device_id:
                    await ws.send_json({"error": "missing device_id"})
                    continue

                if enabled:
                    # Find the device in cache
                    device = next(
                        (d for d in get_cached_devices() if d.device_id == device_id),
                        None,
                    )
                    if device:
                        await device_registry.add(device)
                    else:
                        # Create a synthetic entry from what we know
                        await device_registry.add(DeviceItem(
                            device_id=device_id,
                            device_type="unknown",
                            device_name=device_id,
                        ))
                else:
                    await device_registry.remove(device_id)

                await ws.send_json({
                    "type": "update_stream_response",
                    "node_id": node_id,
                    "device_id": device_id,
                    "enabled": enabled,
                    "success": True,
                    "message": "推流已启动" if enabled else "推流已停止",
                })

            else:
                await ws.send_json({"error": f"unknown command: {command}"})

    except WebSocketDisconnect:
        logger.info("WS client disconnected")
    except Exception:
        logger.exception("WS endpoint error")


# ============================================================
# REST: Device list
# ============================================================


@router.post("/device/list", response_model=GetDeviceListOutput)
async def get_device_list(input: GetDeviceListInput) -> GetDeviceListOutput:
    """Return the list of devices on this node.

    Optionally filtered by ``device_type`` (``"video"`` or ``"audio"``).
    """
    from services.device_enumerator import enumerate_devices

    # Re-enumerate on each call to get live data
    devices = await enumerate_devices()

    # Apply optional type filter
    if input.device_type:
        devices = [d for d in devices if d.device_type == input.device_type]

    # Update cache
    set_cached_devices(devices)

    return GetDeviceListOutput(
        node_id=input.node_id,
        devices=devices,
        total_count=len(devices),
    )


# ============================================================
# REST: Device update (enable / disable streaming)
# ============================================================


@router.post("/device/update", response_model=UpdateDeviceOutput)
async def update_device_usage(input: UpdateDeviceInput) -> UpdateDeviceOutput:
    """Enable or disable RTMP streaming for a device.

    - ``enabled=true`` → add device to the active registry
    - ``enabled=false`` → remove device from the active registry
    """
    from services.device_enumerator import enumerate_devices
    from services.device_registry import device_registry

    if input.enabled:
        # Look up the device from current enumeration
        devices = await enumerate_devices()
        device = next(
            (d for d in devices if d.device_id == input.device_id),
            None,
        )
        if device is None:
            # Device not found locally — still allow (Server may know better)
            device = DeviceItem(
                device_id=input.device_id,
                device_type="unknown",
                device_name=input.device_id,
            )
        await device_registry.add(device)
        message = "推流已启动"
    else:
        await device_registry.remove(input.device_id)
        message = "推流已停止"

    return UpdateDeviceOutput(
        node_id=input.node_id,
        device_id=input.device_id,
        enabled=input.enabled,
        success=True,
        message=message,
    )