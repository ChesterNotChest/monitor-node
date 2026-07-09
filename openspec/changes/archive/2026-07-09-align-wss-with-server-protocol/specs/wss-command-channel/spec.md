# WSS Command Channel (Delta)

## MODIFIED Requirements

### Requirement: CommandHandler dispatches commands by ServerCommand enum
`CommandHandler` SHALL 使用 `dict[ServerCommand, Callable]` 字典派发表。仅支持 `UPDATE_STREAM` 命令。命令字符串值 SHALL 为 `"UPDATE_STREAM"`（大写）。

#### Scenario: Dispatch to update_stream handler
- **WHEN** `CommandHandler.dispatch()` 收到 `{"command": "UPDATE_STREAM", "device_type": "video", "device_id": 1, "enable": true}`
- **THEN** 查表命中 `ServerCommand.UPDATE_STREAM`，调用 `handle_update_stream(data)`

#### Scenario: Unknown command
- **WHEN** `CommandHandler.dispatch()` 收到 `{"command": "get_devices"}`
- **THEN** 通过 `self._wss.send()` 回传 `{"success": false, "message": "unknown command: get_devices"}`

### Requirement: handle_update_stream controls device streaming by server device ID
`handle_update_stream` SHALL 解析 `device_type`（`"video"`/`"audio"`）、`device_id`（int）和 `enable`（bool）。SHALL 通过映射表反查 `device_name` 后匹配本地设备。SHALL 返回 `{"success": true/false, "message": "..."}` 格式。

#### Scenario: Enable streaming for known device
- **WHEN** 收到 `{"command": "UPDATE_STREAM", "device_type": "video", "device_id": 1, "enable": true}` 且映射表命中、本地设备存在
- **THEN** `device_registry` 中新增该设备
- **AND** 回传 `{"success": true, "message": "推流已启动"}`

#### Scenario: Disable streaming
- **WHEN** 收到 `{"command": "UPDATE_STREAM", "device_type": "audio", "device_id": 2, "enable": false}` 且设备在 registry 中
- **THEN** `device_registry` 中移除该设备
- **AND** 回传 `{"success": true, "message": "推流已停止"}`

#### Scenario: Unknown device_id
- **WHEN** 收到 `{"command": "UPDATE_STREAM", "device_type": "video", "device_id": 99, "enable": true}` 且映射表中无此 ID
- **THEN** 回传 `{"success": false, "message": "unknown device_id: 99"}`

## REMOVED Requirements

### Requirement: handle_get_devices returns device list with health status
**Reason**: Server 从数据库获取设备列表，通过认证响应下发映射表，不再需要 `get_devices` 命令向 Node 查询设备。
**Migration**: 设备发现改为认证握手时 Server 主动下发 `{videos, audios}` 映射表。

### Requirement: REST endpoint POST /api/device/list
**Reason**: 已在之前变更中移除。

### Requirement: REST endpoint POST /api/device/update
**Reason**: 已在之前变更中移除。

### Requirement: Local WebSocket endpoint WS /api/ws
**Reason**: 已在之前变更中移除。
