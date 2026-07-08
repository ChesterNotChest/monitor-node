# WSS Command Channel

## Purpose

WSS 作为 Server 与 Node 之间的唯一指令通道。Node 通过 `CommandHandler` 类基于 `ServerCommand` 枚举进行字典派发，处理 `get_devices` 和 `update_stream` 两种指令。所有 REST 和本地 WebSocket 端点被移除。

## ADDED Requirements

### Requirement: CommandHandler dispatches commands by ServerCommand enum
`CommandHandler` SHALL 使用 `dict[ServerCommand, Callable]` 字典派发表，根据消息中的 `command` 字段查表调用对应的 handler 方法。

#### Scenario: Dispatch to get_devices handler
- **WHEN** `CommandHandler.dispatch()` 收到 `{"command": "get_devices", "node_id": "n1"}`
- **THEN** 查表命中 `ServerCommand.GET_DEVICES`，调用 `handle_get_devices(data)`

#### Scenario: Dispatch to update_stream handler
- **WHEN** `CommandHandler.dispatch()` 收到 `{"command": "update_stream", "node_id": "n1", "device_id": "cam-01", "enabled": true}`
- **THEN** 查表命中 `ServerCommand.UPDATE_STREAM`，调用 `handle_update_stream(data)`

#### Scenario: Unknown command
- **WHEN** `CommandHandler.dispatch()` 收到 `{"command": "nonexistent"}`
- **THEN** 通过 `self._wss.send()` 回传 `{"type": "error", "message": "unknown command: nonexistent"}`

#### Scenario: Missing command field
- **WHEN** `CommandHandler.dispatch()` 收到 `{"other_field": "x"}`（无 `command` 字段）
- **THEN** 通过 `self._wss.send()` 回传 `{"type": "error", "message": "unknown command: "}`

### Requirement: handle_get_devices returns device list with health status
`handle_get_devices` SHALL 从设备缓存中获取设备列表，支持按 `device_type` 过滤，并回传包含健康状态的设备列表。

#### Scenario: Return all devices
- **WHEN** 收到 `{"command": "get_devices", "node_id": "n1"}` 且缓存有 2 个设备
- **THEN** 回传 `{"type": "get_devices_response", "node_id": "n1", "devices": [...], "total_count": 2}`

#### Scenario: Return empty device list
- **WHEN** 收到 `{"command": "get_devices", "node_id": "n1"}` 且缓存为空
- **THEN** 回传 `{"type": "get_devices_response", "node_id": "n1", "devices": [], "total_count": 0}`

#### Scenario: Filter by device_type
- **WHEN** 收到 `{"command": "get_devices", "node_id": "n1", "device_type": "video"}` 且缓存有 1 video + 1 audio
- **THEN** 回传 `total_count == 1`，返回的设备全部 `device_type == "video"`

#### Scenario: No device matches filter
- **WHEN** 收到 `{"command": "get_devices", "node_id": "n1", "device_type": "audio"}` 且缓存只有 video 设备
- **THEN** 回传 `total_count == 0`，`devices == []`

### Requirement: handle_update_stream enables or disables device streaming
`handle_update_stream` SHALL 修改设备注册表（添加/移除设备），由状态机在下一个巡检周期（最多 5 秒）执行实际的 ffmpeg 进程启停。

#### Scenario: Enable streaming for known device
- **WHEN** 收到 `{"command": "update_stream", "node_id": "n1", "device_id": "cam-01", "enabled": true}` 且设备在缓存中
- **THEN** `device_registry` 中新增 `cam-01`
- **AND** 回传 `{"type": "update_stream_response", "node_id": "n1", "device_id": "cam-01", "enabled": true, "success": true, "message": "推流已启动"}`

#### Scenario: Enable streaming for unknown device
- **WHEN** 收到 `{"command": "update_stream", "node_id": "n1", "device_id": "unknown-dev", "enabled": true}` 且设备不在缓存中
- **THEN** `device_registry` 中新增 `unknown-dev`，其 `device_type` 为 `"unknown"`
- **AND** 回传 `success: true`

#### Scenario: Disable streaming
- **WHEN** 收到 `{"command": "update_stream", "node_id": "n1", "device_id": "cam-01", "enabled": false}` 且设备在 registry 中
- **THEN** `device_registry` 中移除 `cam-01`
- **AND** 回传 `{"type": "update_stream_response", "node_id": "n1", "device_id": "cam-01", "enabled": false, "success": true, "message": "推流已停止"}`

#### Scenario: Missing device_id
- **WHEN** 收到 `{"command": "update_stream", "node_id": "n1", "enabled": true}`（无 `device_id`）
- **THEN** 回传 `{"type": "error", "message": "missing device_id"}`

#### Scenario: Empty device_id
- **WHEN** 收到 `{"command": "update_stream", "node_id": "n1", "device_id": "", "enabled": true}`
- **THEN** 回传 `{"type": "error", "message": "missing device_id"}`

### Requirement: CommandHandler does not directly start or stop ffmpeg processes
`handle_update_stream` SHALL NOT 直接启动或停止 ffmpeg 子进程。实际的进程管理由 `StreamStateMachine._tick()` 在每 5 秒的巡检周期中执行。

#### Scenario: Registry change triggers state machine convergence
- **WHEN** `handle_update_stream` 将设备添加到 `device_registry` 后
- **THEN** 最多 5 秒后 `StreamStateMachine._tick()` 检测到 registry 与 running 进程的差异并启动 ffmpeg

#### Scenario: Registry removal triggers state machine convergence
- **WHEN** `handle_update_stream` 将设备从 `device_registry` 移除后
- **THEN** 最多 5 秒后 `StreamStateMachine._tick()` 检测到差异并停止对应的 ffmpeg 进程

## REMOVED Requirements

### Requirement: REST endpoint POST /api/device/list
**Reason**: Node 无公网 IP，Server 无法主动调用 REST API。已被 WSS `get_devices` 指令替代。
**Migration**: Server 通过 WSS 发送 `{"command": "get_devices", "node_id": "..."}` 获取设备列表。

### Requirement: REST endpoint POST /api/device/update
**Reason**: Node 无公网 IP，Server 无法主动调用 REST API。已被 WSS `update_stream` 指令替代。
**Migration**: Server 通过 WSS 发送 `{"command": "update_stream", "node_id": "...", "device_id": "...", "enabled": true/false}` 控制推流。

### Requirement: Local WebSocket endpoint WS /api/ws
**Reason**: 与 REST 端点相同的问题——Server 无法访问 Node 的私有 IP。已被 WSS 指令通道替代。
**Migration**: 所有指令通过 WSS 客户端（Node 主动连接 Server）下发和响应。
