# Node Identity

## Purpose

定义 Node 与 Server 之间通过 WSS 连接进行身份认证的协议。Node 在 WSS 连接建立后立即发送 Token 进行认证，Server 回传 NodeID。认证完成后，所有后续指令均携带 NodeID。

## ADDED Requirements

### Requirement: Node sends authentication message on WSS connect
WSS 连接建立后，Node SHALL 在发送任何其他消息之前，首先发送一条身份认证消息。

#### Scenario: Successful authentication
- **WHEN** WSS 连接建立成功
- **THEN** Node 立即发送 `{"type": "auth", "token": "<SECRET_KEY>"}` 消息
- **AND** Node 在 10 秒内等待 Server 的 `auth_ack` 响应

#### Scenario: Authentication timeout
- **WHEN** Node 发送 auth 消息后 10 秒内未收到 `auth_ack` 响应
- **THEN** Node SHALL 断开当前 WSS 连接并进入重连流程

### Requirement: Server responds with NodeID
Server 收到认证消息后 SHALL 回传 `auth_ack` 消息，包含分配的 NodeID。

#### Scenario: Receive NodeID
- **WHEN** Server 验证 Token 通过
- **THEN** Server 发送 `{"type": "auth_ack", "node_id": "<assigned_node_id>"}`
- **AND** Node SHALL 将 `node_id` 存储为本地会话标识

#### Scenario: Authentication rejected
- **WHEN** Server 验证 Token 失败
- **THEN** Server 发送 `{"type": "auth_error", "message": "<reason>"}`
- **AND** Node SHALL 断开连接，记录错误日志，进入重连流程（使用指数退避）

### Requirement: NodeID is included in all subsequent messages
认证成功后，Server 发送的每一条指令 SHALL 包含 `node_id` 字段；Node 发送的每一条响应 SHALL 包含 `node_id` 字段。

#### Scenario: Server command includes node_id
- **WHEN** Server 在认证成功后发送 `get_devices` 或 `update_stream` 指令
- **THEN** 指令 JSON 中 MUST 包含 `"node_id": "<assigned_node_id>"` 字段
- **AND** Node 处理指令前 SHALL 校验 `node_id` 与本地存储的 NodeID 一致

#### Scenario: Node response includes node_id
- **WHEN** Node 处理完指令并回传响应
- **THEN** 响应 JSON 中 MUST 包含 `"node_id": "<local_node_id>"` 字段

### Requirement: NodeID persists across reconnections
Node SHALL 在 WSS 断开后清除本地 NodeID，重连成功后通过重新认证获取新的 NodeID。

#### Scenario: NodeID cleared on disconnect
- **WHEN** WSS 连接断开
- **THEN** Node 将本地 `_node_id` 设置为 `None`
- **AND** 在重新认证成功前，Node 不处理任何指令

#### Scenario: NodeID refreshed on reconnect
- **WHEN** Node 重新连接并完成认证
- **THEN** Node 使用新的 `auth_ack` 中的 NodeID 覆盖旧值
