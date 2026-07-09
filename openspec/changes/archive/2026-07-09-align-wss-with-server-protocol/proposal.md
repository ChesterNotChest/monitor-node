## Why

当前 Node 的 WSS 协议是独立设计的（`{"type":"auth","token":"xxx"}` → `{"type":"auth_ack","node_id":"..."}`、`get_devices` 命令、小写 `update_stream`），与 Server 侧 [node-wss-connection spec](D:\aboutCoding\IDE\python\PlaceHolder\monitor-server\openspec\changes\build-core-monitoring-pipeline\specs\node-wss-connection\spec.md) 定义的协议不一致。Server 已明确了协议规范，Node 需要对齐以完成端到端对接。

## What Changes

- **BREAKING**: 认证消息格式从 `{"type":"auth","token":"xxx"}` 改为 `{"token":"xxx"}`
- **BREAKING**: 认证响应从 `{"type":"auth_ack","node_id":"..."}` 改为 `{"session_token":"sess_xxx","videos":[{id,name}],"audios":[{id,name}]}`
- **BREAKING**: 移除 `get_devices` 命令——Server 从数据库获取设备列表，通过认证响应下发映射表
- **BREAKING**: `UPDATE_STREAM` 命令字段变更：`device_id` 从 string 改为 int（Server 侧数据库 ID），新增 `device_type` 字段（`"video"`/`"audio"`），`enabled` 改为 `enable`
- **BREAKING**: 命令响应格式从 `{"type":"update_stream_response",...}` 改为 `{"success":true,"message":null}`
- **BREAKING**: 移除 `NodeResponse` 枚举（响应改为简单 dict）
- 移除 `ServerCommand.GET_DEVICES` 枚举值
- 新增本地 `{device_id (int) → device_name (str)}` 映射表，在认证握手时由 Server 下发
- RTMP URL 格式对齐为 `{device_name}_{device_type}_{device_id}`（与 Server 拉流路径一致）
- `session_token` 替代 `node_id` 作为会话标识
- 心跳保持不变

## Capabilities

### New Capabilities
- `server-device-mapping`: Node 在 WSS 认证握手后从 Server 获取 `(device_id → device_name)` 映射表，供后续 `UPDATE_STREAM` 命令反查本地设备

### Modified Capabilities
- `wss-command-channel`: 移除 `get_devices` 指令；`UPDATE_STREAM` 字段变更为 `{command, device_type, device_id (int), enable}`；响应格式变更为 `{success, message}`
- `node-identity`: 认证消息格式从 `{type:"auth", token}` 简化为 `{token}`；认证成功响应从 `{type:"auth_ack", node_id}` 变更为 `{session_token, videos, audios}`
- `rtmp-streaming`: RTMP URL 格式从 `{nodeid}_{device_type}_{device_name_slug}` 变更为 `{device_name}_{device_type}_{device_id}`

## Impact

| 影响范围 | 说明 |
|---|---|
| `constant.py` | 删除 `GET_DEVICES`，`UPDATE_STREAM` 值改为 `"UPDATE_STREAM"`；删除 `NodeResponse` 枚举；保留 `AuthStatus` |
| `network/wss_client.py` | 认证消息格式变更：`{"token":"xxx"}`；解析 `session_token` + `videos`/`audios` 映射；`session_token` 替代 `node_id` |
| `network/command_handler.py` | 删除 `handle_get_devices`；`handle_update_stream` 解析 `device_type`、`device_id`(int)、`enable`；通过映射表反查本地设备；响应格式 `{success, message}` |
| `network/models.py` | 新增 Server 设备映射缓存 `_server_device_map` |
| `services/ffmpeg_runner.py` | RTMP URL 格式变更为 `{device_name}_{device_type}_{device_id}` |
| `app.py` | 移除 `on_auth_restart_streams` 中对 `node_id` 的引用（改为 `session_token`） |
| `tests/` | 更新所有相关测试 |
