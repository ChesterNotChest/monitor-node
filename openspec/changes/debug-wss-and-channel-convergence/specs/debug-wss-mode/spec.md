# DEBUG WSS Mode

## Purpose

定义 DEBUG_WSS 调试模式的行为规范。在 DEBUG_WSS 模式下，Node 使用固定 Token 连接本地伪 WSS 服务器，用于开发调试和验证身份标识功能。包含假 WSS 接收者脚本的规范。

## ADDED Requirements

### Requirement: DEBUG_WSS mode is enabled via environment variable
`DEBUG_WSS` 环境变量 SHALL 控制是否启用 WSS 调试模式。当值为 `"true"`、`"1"` 或 `"yes"` 时启用。

#### Scenario: DEBUG_WSS enabled
- **WHEN** `DEBUG_WSS=true`
- **THEN** Node 进入 WSS 调试模式：使用固定 Token、连接本地 WebSocket、跳过 SSL 证书验证

#### Scenario: DEBUG_WSS disabled
- **WHEN** `DEBUG_WSS=false` 或未设置
- **THEN** Node 使用生产模式：从 `SECRET_KEY` 读取 Token、通过 nginx WSS 连接

### Requirement: Fixed identity token in DEBUG_WSS mode
DEBUG_WSS 模式下，Node SHALL 使用固定 Token `"debug-token-fixed"` 进行身份认证。

#### Scenario: Authentication with fixed token
- **WHEN** `DEBUG_WSS=true` 且 WSS 连接建立
- **THEN** Node 发送 `{"type": "auth", "token": "debug-token-fixed"}`

### Requirement: DEBUG_WSS uses local non-encrypted WebSocket
DEBUG_WSS 模式下，Node SHALL 使用 `ws://`（非加密 WebSocket）连接 `127.0.0.1:{WSS_PORT}/ws`。

#### Scenario: Local WebSocket connection
- **WHEN** `DEBUG_WSS=true` 且 `WSS_PORT=8443`
- **THEN** Node 连接 `ws://127.0.0.1:8443/ws`

### Requirement: Mock WSS server recognizes debug token and assigns fixed NodeID
假 WSS 接收者（`tests/mock_server.js`）SHALL 识别 DEBUG_WSS 的固定 Token，分配固定 NodeID `"debug-node-001"`。

#### Scenario: Mock server authenticates debug token
- **WHEN** 假 WSS 服务器收到 `{"type": "auth", "token": "debug-token-fixed"}`
- **THEN** 假 WSS 服务器回传 `{"type": "auth_ack", "node_id": "debug-node-001"}`

#### Scenario: Mock server rejects unknown token
- **WHEN** 假 WSS 服务器收到 `{"type": "auth", "token": "unknown-token"}`
- **THEN** 假 WSS 服务器回传 `{"type": "auth_error", "message": "invalid token"}`
- **AND** 假 WSS 服务器关闭该连接

### Requirement: Mock WSS server supports get_devices command
假 WSS 接收者 SHALL 支持发送 `get_devices` 指令并接收 Node 的设备列表响应。

#### Scenario: Mock server sends get_devices
- **WHEN** 假 WSS 服务器发送 `{"command": "get_devices", "node_id": "debug-node-001"}`
- **THEN** 假 WSS 服务器收到 Node 回传的 `{"type": "get_devices_response", "node_id": "debug-node-001", "devices": [...], "total_count": N}`
- **AND** 假 WSS 服务器在终端打印收到的响应，带时间戳

### Requirement: Mock WSS server supports update_stream command
假 WSS 接收者 SHALL 支持发送 `update_stream` 指令并接收 Node 的操作结果响应。

#### Scenario: Mock server sends update_stream enable
- **WHEN** 假 WSS 服务器发送 `{"command": "update_stream", "node_id": "debug-node-001", "device_id": "cam-01", "enabled": true}`
- **THEN** 假 WSS 服务器收到 Node 回传的 `{"type": "update_stream_response", "node_id": "debug-node-001", "device_id": "cam-01", "enabled": true, "success": true, "message": "推流已启动"}`

#### Scenario: Mock server sends update_stream disable
- **WHEN** 假 WSS 服务器发送 `{"command": "update_stream", "node_id": "debug-node-001", "device_id": "cam-01", "enabled": false}`
- **THEN** 假 WSS 服务器收到 Node 回传的 `{"type": "update_stream_response", "node_id": "debug-node-001", "device_id": "cam-01", "enabled": false, "success": true, "message": "推流已停止"}`

### Requirement: Mock WSS server accepts heartbeat
假 WSS 接收者 SHALL 接受 Node 发送的心跳消息，不做响应。

#### Scenario: Mock server receives heartbeat
- **WHEN** 假 WSS 服务器收到 `{"type": "heartbeat"}`
- **THEN** 假 WSS 服务器不发送任何响应
- **AND** 假 WSS 服务器在终端打印心跳接收日志

### Requirement: Mock WSS server provides interactive REPL
假 WSS 接收者 SHALL 提供交互式命令行界面，支持手动输入指令。

#### Scenario: Interactive command input
- **WHEN** 开发者启动 `node tests/mock_server.js`
- **THEN** 假 WSS 服务器在终端显示交互提示符，接受以下命令格式：
  - `get_devices` — 发送 get_devices 指令
  - `update_stream <device_id> true` — 启用指定设备推流
  - `update_stream <device_id> false` — 停用指定设备推流
  - `help` — 显示帮助信息
  - `quit` — 关闭服务器
