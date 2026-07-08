# WSS Connection (Delta)

## MODIFIED Requirements

### Requirement: Node connects to Server on startup
Node 启动后 SHALL 在 10 秒内主动向 Server 发起 WebSocket 连接。

连接建立后，Node SHALL 首先完成身份认证握手（发送 Token → 接收 NodeID），认证成功后方可进入心跳和指令收发。

在 DEBUG_WSS 模式下，Node SHALL 使用 `ws://` 连接 `127.0.0.1:{WSS_PORT}/ws` 并使用固定 Token `"debug-token-fixed"`。

WSS 连接地址 SHALL 由 `{SERVER_BASE_URL}:{WSS_PORT}/ws` 拼接而成。

#### Scenario: Successful connection with authentication
- **WHEN** Node 启动且 Server WSS 端点可达
- **THEN** Node 完成 WSS 握手
- **AND** Node 发送 `{"type": "auth", "token": "<token>"}` 进行身份认证
- **AND** Node 收到 `{"type": "auth_ack", "node_id": "<node_id>"}` 后连接状态变为 `connected`
- **AND** Node 存储 `node_id` 为本地会话标识

#### Scenario: DEBUG_WSS connection
- **WHEN** `DEBUG_WSS=true` 且 Node 启动
- **THEN** Node 连接 `ws://127.0.0.1:{WSS_PORT}/ws`
- **AND** Node 使用固定 Token `"debug-token-fixed"` 进行认证
- **AND** 假 WSS 服务器回传 `{"type": "auth_ack", "node_id": "debug-node-001"}`

#### Scenario: Server unreachable on startup
- **WHEN** Node 启动但 Server WSS 端点不可达
- **THEN** Node SHALL 进入指数退避重连模式，首期间隔 1s，上限 60s，无限重试

### Requirement: Node maintains persistent connection
WSS 连接 SHALL 保持长连接，Node 通过此连接接收 Server 指令。

连接断开时，Node SHALL 清除本地存储的 `node_id`，重连后重新认证获取新的 NodeID。

#### Scenario: Connection dropped mid-session
- **WHEN** 已建立的 WSS 连接意外断开（网络波动 / Server 重启）
- **THEN** Node SHALL 检测断连事件
- **AND** 清除本地 `node_id`
- **AND** 立即进入重连流程，重连后重新认证

### Requirement: Node sends heartbeat
Node SHALL 每 30 秒向 Server 发送心跳消息。心跳仅在认证成功（收到 `auth_ack`）后进行。

#### Scenario: Heartbeat after authentication
- **WHEN** 认证成功且连接处于 `connected` 状态超过 30 秒
- **THEN** Node 发送 `{"type": "heartbeat"}` 消息

#### Scenario: No heartbeat before authentication
- **WHEN** WSS 握手完成但认证尚未完成
- **THEN** Node SHALL NOT 发送心跳消息
