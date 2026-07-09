# Node Identity (Delta)

## MODIFIED Requirements

### Requirement: Node sends authentication message on WSS connect
WSS 连接建立后，Node SHALL 在发送任何其他消息之前，首先发送一条身份认证消息。认证消息格式 SHALL 为 `{"token": "<SECRET_KEY>"}`（不含 `type` 包装）。

#### Scenario: Successful authentication
- **WHEN** WSS 连接建立成功
- **THEN** Node 立即发送 `{"token": "<SECRET_KEY>"}` 消息
- **AND** Node 在 10 秒内等待 Server 的认证成功响应

#### Scenario: Authentication timeout
- **WHEN** Node 发送 token 消息后 10 秒内未收到有效响应
- **THEN** Node SHALL 断开当前 WSS 连接并进入重连流程

### Requirement: Server responds with session_token and device mapping
Server 收到 token 后 SHALL 回传认证成功响应，包含 `session_token`、`videos` 列表和 `audios` 列表。Node SHALL 存储 `session_token` 作为会话标识，存储设备列表作为本地映射表。

#### Scenario: Receive session_token and device lists
- **WHEN** Server 验证 Token 通过
- **THEN** Server 发送 `{"session_token": "<token>", "videos": [{"id": 1, "name": "cam0"}], "audios": [{"id": 2, "name": "mic0"}]}`
- **AND** Node SHALL 将 `session_token` 存储为本地会话标识（替代 `node_id`）
- **AND** Node SHALL 将 `videos` 和 `audios` 列表存储为 `{device_id: device_name}` 映射表

#### Scenario: Authentication rejected
- **WHEN** Server 验证 Token 失败
- **THEN** Server 关闭连接
- **AND** Node SHALL 检测到连接关闭，记录错误日志，进入重连流程（使用指数退避）

### Requirement: NodeID is included in all subsequent messages
此要求被移除。Server 协议使用 `session_token` 而非 `node_id`。后续命令中不包含 `node_id` 字段。

#### Scenario: Server command format
- **WHEN** Server 在认证成功后发送 `UPDATE_STREAM` 指令
- **THEN** 指令 JSON 格式为 `{"command": "UPDATE_STREAM", "device_type": "...", "device_id": N, "enable": true/false}`
- **AND** 不包含 `node_id` 字段

### Requirement: Session identifier persists across reconnections
Node SHALL 在 WSS 断开后清除本地 `session_token` 和设备映射表，重连成功后通过重新认证获取新的 `session_token` 和映射表。

#### Scenario: Session cleared on disconnect
- **WHEN** WSS 连接断开
- **THEN** Node 将本地 `_session_token` 设置为 `None`
- **AND** Node 清空 `_server_video_map` 和 `_server_audio_map`
- **AND** 在重新认证成功前，Node 不处理任何指令

#### Scenario: Session refreshed on reconnect
- **WHEN** Node 重新连接并完成认证
- **THEN** Node 使用新的 `session_token` 和映射表覆盖旧值
