"""WSS 指令分发器——根据 ServerCommand 将消息分发到对应的处理函数。

通过字典派发表 ``dict[ServerCommand, Callable]`` 将命令字符串映射到
handler 方法。当前仅支持 ``UPDATE_STREAM`` 命令。

协议（对齐 Server 的 node-wss-connection spec）：
  Server → Node: {"command": "UPDATE_STREAM", "device_type": "video", "device_id": 1, "enable": true}
  Node → Server: {"success": true, "message": null}
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from constant import ServerCommand
from network.models import (
    DeviceItem,
    get_cached_devices,
    get_server_device_name,
)

logger = logging.getLogger(__name__)


class CommandHandler:
    """WSS 指令分发器，根据 ServerCommand 分发到对应处理函数。"""

    def __init__(self, wss_client) -> None:
        """
        Args:
            wss_client: WSS 客户端实例，用于回传响应。
        """
        self._wss = wss_client
        self._dispatch: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {
            ServerCommand.UPDATE_STREAM: self.handle_update_stream,
        }

    # ---------- 入口 ----------

    async def dispatch(self, data: dict[str, Any]) -> None:
        """WSS 消息入口。由 WssClient._handler 调用。

        Args:
            data: Server 发来的原始 JSON dict，必须包含 "command" 字段。
        """
        command = data.get("command", "")
        logger.debug("CommandHandler.dispatch: %s", command)

        handler = self._dispatch.get(command)
        if handler is not None:
            await handler(data)
        else:
            await self._send_response(False, f"unknown command: {command}")

    # ---------- 指令处理函数 ----------

    async def handle_update_stream(self, data: dict[str, Any]) -> None:
        """启用/禁用某个设备的 RTMP 推流。

        输入（对齐 Server 协议）:
          {"command": "UPDATE_STREAM", "device_type": "video", "device_id": 1, "enable": true}

        输出:
          {"success": true, "message": "推流已启动"}

        内部逻辑:
          1. 解析 device_type（"video"/"audio"）、device_id（int）、enable（bool）
          2. 通过 get_server_device_name() 反查映射表获取 device_name
          3. 在本地设备缓存中按 device_name + device_type 匹配 DeviceItem
          4. 操作 device_registry（添加/移除）
          5. ★ 不在此处启动/停止 ffmpeg 子进程 ★
             state_machine._tick() 每 5s 检测 registry 变化后执行实际的进程启停
        """
        from services.device_registry import device_registry

        device_type = data.get("device_type", "")
        device_id = data.get("device_id")
        enable = data.get("enable", False)

        # 校验 device_type
        if device_type not in ("video", "audio"):
            await self._send_response(False, f"invalid device_type: {device_type}")
            return

        # 校验 device_id
        if not isinstance(device_id, int) and not (isinstance(device_id, str) and device_id.isdigit()):
            await self._send_response(False, f"invalid device_id: {device_id}")
            return
        device_id = int(device_id)

        # 通过 Server 映射表反查 device_name
        device_name = get_server_device_name(device_type, device_id)
        if device_name is None:
            await self._send_response(False, f"unknown device_id: {device_id}")
            return

        if enable:
            # 在本地设备缓存中匹配 device_name + device_type
            cached = get_cached_devices()
            device = next(
                (d for d in cached if d.device_name == device_name and d.device_type == device_type),
                None,
            )
            if device is None:
                # 设备不在本地缓存 — 构造占位条目
                local_device_id = f"{device_type}-{device_name}"
                device = DeviceItem(
                    device_id=local_device_id,
                    device_type=device_type,
                    device_name=device_name,
                )
            await device_registry.add(device)
            await self._send_response(True, "推流已启动")
        else:
            # 停用：在 registry 中按 device_name 匹配查找并移除
            registry_snapshot = await device_registry.snapshot()
            target_device_id = None
            for did, item in registry_snapshot.items():
                if item.device_name == device_name and item.device_type == device_type:
                    target_device_id = did
                    break

            if target_device_id:
                await device_registry.remove(target_device_id)

            await self._send_response(True, "推流已停止")

    # ---------- 辅助方法 ----------

    async def _send_response(self, success: bool, message: str | None) -> None:
        """发送对齐 Server 协议的响应。"""
        await self._wss.send({
            "type": "update_stream_response",
            "success": success,
            "message": message,
        })
