# WSS Connection

## Purpose

Maintain a persistent WebSocket Secure connection from the Node to the Server for receiving commands and reporting status.

## Requirements

### Requirement: Node connects to Server on startup
Node 启动后 SHALL 在 10 秒内主动向 Server 发起 WebSocket Secure (WSS) 连接。

#### Scenario: Successful connection
- **WHEN** Node 启动且 Server WSS 端点可达
- **THEN** Node 完成 WSS 握手，连接状态变为 `connected`

#### Scenario: Server unreachable on startup
- **WHEN** Node 启动但 Server WSS 端点不可达
- **THEN** Node SHALL 进入指数退避重连模式，首期间隔 1s，上限 60s，无限重试

### Requirement: Node maintains persistent connection
WSS 连接 SHALL 保持长连接，Node 通过此连接接收 Server 指令。

#### Scenario: Connection dropped mid-session
- **WHEN** 已建立的 WSS 连接意外断开（网络波动 / Server 重启）
- **THEN** Node SHALL 检测断连事件，立即进入重连流程

### Requirement: Node sends heartbeat
Node SHALL 每 30 秒向 Server 发送心跳消息。

#### Scenario: Heartbeat
- **WHEN** 连接处于 `connected` 状态超过 30 秒
- **THEN** Node 发送 `{"type": "heartbeat"}` 消息
