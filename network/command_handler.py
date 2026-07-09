"""WSS 指令分发器——根据 ServerCommand 将消息分发到对应的处理函数。

通过字典派发表 ``dict[ServerCommand, Callable]`` 将命令字符串映射到
handler 方法，保持类似 REST API 路由的可读性。新增命令只需：
1. constant.py 添加 ServerCommand 成员
2. 在本类添加 handle_xxx 方法
3. 在 _dispatch 字典中加一行映射
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from constant import NodeResponse, ServerCommand
from network.models import DeviceItem, get_cached_devices

logger = logging.getLogger(__name__)


class CommandHandler:
    """WSS 指令分发器，根据 ServerCommand 分发到对应处理函数。

    通过字典派发表 dict[ServerCommand, Callable] 将命令字符串映射到
    handler 方法，保持类似 REST API 路由的可读性。
    """

    def __init__(self, wss_client) -> None:
        """
        Args:
            wss_client: WSS 客户端实例，用于回传响应。
                        通过 wss_client.send() 将 handler 结果发回 Server。
                        通过 wss_client.node_id 获取当前会话的 NodeID。
        """
        self._wss = wss_client
        self._dispatch: dict[str, Callable[[dict[str, Any]], Awaitable[None]]] = {
            ServerCommand.GET_DEVICES: self.handle_get_devices,
            ServerCommand.UPDATE_STREAM: self.handle_update_stream,
        }

    # ---------- 入口 ----------

    async def dispatch(self, data: dict[str, Any]) -> None:
        """WSS 消息入口。由 WssClient._handler 调用。

        内部逻辑:
          1. 提取 data["command"]
          2. 查表 self._dispatch.get(command)
          3. 命中 → await handler(data)
          4. 未命中 → self._wss.send({"error": f"unknown command: {command}"})

        Args:
            data: Server 发来的原始 JSON dict，必须包含 "command" 字段。
        """
        command = data.get("command", "")
        logger.debug("CommandHandler.dispatch: %s", command)

        handler = self._dispatch.get(command)
        if handler is not None:
            await handler(data)
        else:
            await self._send_error(f"unknown command: {command}")

    # ---------- 指令处理函数 ----------

    async def handle_get_devices(self, data: dict[str, Any]) -> None:
        """获取设备列表 + 健康状态。

        输入: {"command": "get_devices", "node_id": str, "device_type"?: str}
        输出: WSS send {"type": "get_devices_response", "node_id": str,
                        "devices": [DeviceItem.model_dump(), ...], "total_count": int}

        内部逻辑:
          1. 提取 node_id (默认 "")
          2. 提取可选的 device_type 过滤条件
          3. 从 get_cached_devices() 获取缓存设备列表
          4. 如有 device_type，按类型过滤
          5. 将 DeviceItem 序列化为 dict（model_dump()）
          6. 通过 self._wss.send() 回传
        """
        node_id = data.get("node_id", self._wss.node_id or "")
        device_type = data.get("device_type")

        devices = get_cached_devices()
        if device_type:
            devices = [d for d in devices if d.device_type == device_type]

        await self._wss.send({
            "type": NodeResponse.GET_DEVICES_RESPONSE,
            "node_id": node_id,
            "devices": [d.model_dump() for d in devices],
            "total_count": len(devices),
        })

    async def handle_update_stream(self, data: dict[str, Any]) -> None:
        """启用/禁用某个设备的 RTMP 推流。

        输入: {"command": "update_stream", "node_id": str,
               "device_id": str, "enabled": bool}
        输出: WSS send {"type": "update_stream_response", "node_id": str,
                        "device_id": str, "enabled": bool,
                        "success": bool, "message": str}

        内部逻辑:
          1. 提取并校验 device_id（空 → 回传 error）
          2. 提取 enabled (默认 False)、node_id
          3. 启用 (enabled=true):
             a. 从缓存查找 device
             b. 找到 → device_registry.add(device)
             c. 未找到 → 构造 DeviceItem(device_type="unknown",
                device_name=device_id) → device_registry.add()
          4. 停用 (enabled=false):
             a. device_registry.remove(device_id)
          5. 回传操作结果
          6. ★ 不在此处启动/停止 ffmpeg 子进程 ★
             state_machine._tick() 每 5s 检测 registry 变化后执行实际的进程启停
        """
        from services.device_registry import device_registry

        node_id = data.get("node_id", self._wss.node_id or "")
        device_id = data.get("device_id", "")
        enabled = data.get("enabled", False)

        # 校验 device_id
        if not device_id:
            await self._send_error("missing device_id")
            return

        if enabled:
            # 从缓存查找设备
            device = next(
                (d for d in get_cached_devices() if d.device_id == device_id),
                None,
            )
            if device is None:
                # 设备不在本地缓存 — 构造占位条目（Server 可能知道更多）
                device = DeviceItem(
                    device_id=device_id,
                    device_type="unknown",
                    device_name=device_id,
                )
            await device_registry.add(device)
            message = "推流已启动"
        else:
            await device_registry.remove(device_id)
            message = "推流已停止"

        await self._wss.send({
            "type": NodeResponse.UPDATE_STREAM_RESPONSE,
            "node_id": node_id,
            "device_id": device_id,
            "enabled": enabled,
            "success": True,
            "message": message,
        })

    # ---------- 辅助方法 ----------

    async def _send_error(self, message: str) -> None:
        """发送通用错误响应。"""
        await self._wss.send({
            "type": NodeResponse.ERROR,
            "node_id": self._wss.node_id or "",
            "message": message,
        })
