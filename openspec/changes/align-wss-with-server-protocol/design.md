## Context

Node 当前的 WSS 协议是独立设计的，与 Server 侧 `build-core-monitoring-pipeline` 变更中定义的协议存在以下差异：

| 方面 | Node 当前 | Server 协议 |
|---|---|---|
| 认证消息 | `{"type":"auth","token":"xxx"}` | `{"token":"xxx"}` |
| 认证响应 | `{"type":"auth_ack","node_id":"n1"}` | `{"session_token":"sess_xxx","videos":[{id,name}],"audios":[{id,name}]}` |
| 设备查询 | `get_devices` 命令 | 设备列表在认证响应中下发 |
| 流控制命令 | `update_stream` (小写) | `UPDATE_STREAM` (大写) |
| device_id 类型 | string (本地设备ID) | int (Server 数据库 ID) |
| 响应格式 | `{"type":"update_stream_response",...}` | `{"success":true,"message":null}` |
| 会话标识 | `node_id` | `session_token` |

需要将 Node 侧协议全面对齐到 Server 规范。

## Goals / Non-Goals

**Goals:**
- WSS 认证消息格式对齐为 `{"token":"xxx"}`
- 认证响应处理 `session_token` + `videos`/`audios` 设备映射表
- 移除 `get_devices` 命令处理
- `UPDATE_STREAM` 命令字段对齐：`device_type`、`device_id`(int)、`enable`
- 响应格式对齐为 `{success, message}`
- RTMP URL 格式对齐为 `{device_name}_{device_type}_{device_id}`

**Non-Goals:**
- 修改 Server 侧代码
- 修改假 WSS 服务器的 REPL（单独跟进）
- 修改状态机逻辑
- 修改 RTMP 推流核心机制（仅改 URL 格式）
- 修改 `monitor-server` 仓库

## Decisions

### 1. 认证消息简化

**决策**：从 `{"type":"auth","token":"xxx"}` 简化为 `{"token":"xxx"}`。

**原因**：Server 协议规定 WSS 连接的首条消息即为 token，不需要 `type` 包装。Server 通过消息结构（仅含 `token` 字段）识别认证消息。

### 2. session_token 替代 node_id

**决策**：`WssClient._node_id` 改为 `WssClient._session_token`，由 `auth_ack` 中的 `node_id` 改为认证响应中的 `session_token`。

**原因**：Server 使用 `session_token` 作为会话标识，Node 需存储并在日志中使用。

### 3. 设备映射表

**决策**：在 `network/models.py` 中新增模块级 `_server_device_map: dict[int, str]` 和设备类型区分存储 `_server_video_map` / `_server_audio_map`。认证成功后由 `wss_client` 填充。

UPDATE_STREAM 处理流程：
```
Server → {"command":"UPDATE_STREAM","device_type":"video","device_id":1,"enable":true}
         ↓
command_handler 解析 device_type + device_id (int)
         ↓
从 _server_device_map 反查 device_name
         ↓
查找本地缓存中匹配 device_name 的 DeviceItem
         ↓
device_registry.add/remove → state_machine 处理实际 ffmpeg 启停
```

**原因**：Server 通过数据库 ID 引用设备，Node 通过设备名称匹配本地设备。映射表在认证时由 Server 下发，保证一致性。

### 4. 移除 get_devices

**决策**：完全移除 `handle_get_devices` handler 和 `ServerCommand.GET_DEVICES`。

**原因**：Server 从自己的数据库获取设备列表，不需要向 Node 查询。设备列表在认证握手时以映射表形式下发。

### 5. RTMP URL 格式

**决策**：从 `{nodeid}_{device_type}_{device_name_slug}` 变更为 `{device_name}_{device_type}_{device_id}`。

Server 期望的拉流路径为 `rtmp://srs:1935/live/{device_name}_video_{video_id}`，Node 推送路径需与之匹配。

**示例**：
- `rtmp://127.0.0.1:1935/live/Integrated Camera_video_1`
- `rtmp://127.0.0.1:1935/live/Microphone Array_audio_2`

**注意**：device_name 中的空格**保留原样**（不 slug 化），因为 Server 通过数据库中的原始名称匹配。Server 的 FFmpeg 命令会正确引用含空格的 URL。

### 6. 假 WSS 服务器不变

**决策**：`tests/mock_server/mock_server.js` 本次不同步修改（其 REPL 仍使用旧协议格式）。Node 侧变更完成后，DEBUG_WSS 模式下可通过手动注入的 `session_token` 和空映射表运行。

**原因**：假服务器更新属于后续工作，本次聚焦 Node 核心协议对齐。

## Risks / Trade-offs

- **[风险] device_name 匹配失败** → Server 下发的 device_name 与 Node 本地枚举的名称可能不完全一致（空格、编码、特殊字符）。Node 需做模糊匹配或记录未匹配警告。
- **[风险] 假 WSS 服务器不兼容** → DEBUG_WSS 模式下需手动启动旧版 mock_server.js 并注入符合新协议的响应。短期可通过硬编码 fallback 值绕过。
- **[风险] session_token 无实际用途** → 当前 Node 不主动使用 session_token（仅日志记录）。后续 Server 可能要求在后续命令中携带 session_token 做会话校验。

## Migration Plan

1. 更新 `constant.py`：移除 `GET_DEVICES`、修改 `UPDATE_STREAM` 值、移除 `NodeResponse`
2. 更新 `network/models.py`：新增 server 设备映射存储
3. 更新 `network/wss_client.py`：修改认证流程和 session_token 存储
4. 更新 `network/command_handler.py`：删除 `get_devices`、修改 `update_stream`
5. 更新 `services/ffmpeg_runner.py`：修改 RTMP URL 格式
6. 更新 `app.py`：适配新协议
7. 更新所有测试
8. 运行 pytest 验证
