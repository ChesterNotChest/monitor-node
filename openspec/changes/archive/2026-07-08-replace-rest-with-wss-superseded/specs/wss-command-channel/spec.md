## ADDED Requirements

### Requirement: WSS 作为唯一指令通道

Node 与 Server 之间的所有指令通信 SHALL 通过 WSS（WebSocket Secure）连接完成。Node SHALL 主动向 Server 发起 WSS 连接，Server 通过该连接向 Node 下发指令，Node 通过该连接向 Server 回传响应。Node SHALL NOT 暴露任何 REST API 或本地 WebSocket 服务端端口用于指令通信。

#### Scenario: Server 下发 get_devices 指令
- **WHEN** Server 通过 WSS 发送 `{"command": "get_devices", "node_id": "n1"}`
- **THEN** Node 执行设备枚举，并通过同一 WSS 连接返回 `{"type": "get_devices_response", "node_id": "n1", "devices": [...], "total_count": N}`

#### Scenario: Server 下发 update_stream 启用推流
- **WHEN** Server 通过 WSS 发送 `{"command": "update_stream", "node_id": "n1", "device_id": "cam-01", "enabled": true}`
- **THEN** Node 将对应设备加入活跃注册表，并通过同一 WSS 连接返回 `{"type": "update_stream_response", "node_id": "n1", "device_id": "cam-01", "enabled": true, "success": true, "message": "推流已启动"}`

#### Scenario: Server 下发 update_stream 停用推流
- **WHEN** Server 通过 WSS 发送 `{"command": "update_stream", "node_id": "n1", "device_id": "cam-01", "enabled": false}`
- **THEN** Node 将对应设备从活跃注册表中移除，停止 ffmpeg 推流，并通过同一 WSS 连接返回 `{"type": "update_stream_response", "node_id": "n1", "device_id": "cam-01", "enabled": false, "success": true, "message": "推流已停止"}`

### Requirement: ServerCommand 枚举作为指令入口

Node SHALL 使用 `ServerCommand` 枚举定义所有支持的指令类型。当前支持两个指令：`GET_DEVICES`（获取设备列表及健康状态）和 `UPDATE_STREAM`（启用或禁用设备推流）。指令分发 SHALL 使用字典映射（`dict[str, Callable]`）将 `ServerCommand` 值映射到对应的处理函数，新增指令类型时只需在枚举中添加成员并在映射表中添加一行。

#### Scenario: 收到未知命令
- **WHEN** Server 通过 WSS 发送 `{"command": "unknown_cmd"}`
- **THEN** Node SHALL 返回 `{"error": "unknown command: unknown_cmd"}`

#### Scenario: 收到无效 JSON
- **WHEN** Server 通过 WSS 发送无法解析为 JSON 的数据
- **THEN** Node SHALL 返回 `{"error": "invalid json"}`

### Requirement: 指令处理结果回传

Node 处理完 Server 指令后 SHALL 通过同一 WSS 连接将结果（成功或失败）回传给 Server。响应消息 SHALL 包含 `type` 字段标明响应类型，以及相关业务数据。

#### Scenario: update_stream 缺少必要字段
- **WHEN** Server 通过 WSS 发送 `{"command": "update_stream", "enabled": true}`（缺少 `device_id`）
- **THEN** Node SHALL 返回 `{"error": "missing device_id"}`

### Requirement: 健康检查端点保留

Node SHALL 保留 `GET /` 和 `GET /health` 两个 HTTP 端点用于基本健康检查和运维探活。Node SHALL NOT 保留任何其他 HTTP REST 端点或本地 WebSocket 服务端端点。

#### Scenario: 健康检查探活
- **WHEN** 运维系统或负载均衡器访问 `GET /health`
- **THEN** Node SHALL 返回 `{"status": "ok"}` 且 HTTP 状态码为 200

#### Scenario: 根路径访问
- **WHEN** 访问 `GET /`
- **THEN** Node SHALL 返回 `{"service": "monitor-node", "status": "running"}`

### Requirement: Swagger 文档移除

Node SHALL NOT 暴露 Swagger UI（`/docs`）或 ReDoc 文档端点，因为所有指令通信已通过 WSS 完成，无可供文档化的 REST 端点。

#### Scenario: 访问已移除的 Swagger 路径
- **WHEN** 访问 `GET /docs`
- **THEN** Node SHALL 返回 404
