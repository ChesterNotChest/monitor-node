## Why

当前 Node 存在三套通信通道（REST `/api/device/*`、本地 WS `/api/ws`、WSS `wss_client`），其中 REST 和本地 WS 因 Node 无公网 IP 而无法被 Server 使用，属于死通道。需要将指令通道收敛为 WSS 单一通道，同时补齐 DEBUG_WSS 调试模式、Node 身份标识协议和配置字段对齐，使 Node 侧与 Server 侧的规约完全一致。

## What Changes

- **BREAKING**: 移除 `POST /api/device/list` REST 端点
- **BREAKING**: 移除 `POST /api/device/update` REST 端点
- **BREAKING**: 移除 `WS /api/ws` 本地 WebSocket 端点
- **BREAKING**: 移除 Swagger UI (`/docs`)，仅保留 `GET /` 和 `GET /health`
- 将 WSS 收敛为 Server↔Node 的唯一指令通道，实现 `CommandHandler` 指令分发器
- 新增 Node 身份标识协议：WSS 连接建立后 Node 发送 Token，Server 回传 NodeID；后续所有 WSS 请求均携带 NodeID
- 新增 DEBUG_WSS 模式：使用固定 Token 连接本地伪 WSS 服务器，用于验证身份标识功能
- 新增假 WSS 接收者脚本（`tests/mock_server.js`），具备身份标识识别能力
- 对齐配置字段：`SERVER_BASE_URL`、`RTMP_PORT`、`RTMP_DEBUG`、`WSS_PORT` 替代旧有零散配置
- RTMP URL 格式对齐为 `rtmp://{ip}:{port}/live/{nodeid}_{device_type}_{device_name}`
- RTMP 推流链路保持不变

## Capabilities

### New Capabilities
- `debug-wss-mode`: DEBUG_WSS 调试模式——使用固定 Token 连接本地伪 WSS 服务器，用于开发调试和验证身份标识功能。包含假 WSS 接收者脚本，具备身份标识识别和两种命令（get_devices / update_stream）的收发能力。
- `wss-command-channel`: WSS 作为唯一的 Server→Node 指令通道，通过 `CommandHandler` 类基于 `ServerCommand` 枚举进行字典派发。移除所有 REST 和本地 WS 端点。新增 `NodeResponse` 响应类型枚举。
- `node-identity`: Node 身份标识协议——WSS 连接建立后 Node 立即发送 `{"type":"auth","token":"..."}` 进行身份认证，Server 回传 `{"type":"auth_ack","node_id":"..."}` 分配 NodeID。后续所有 WSS 指令均包含 `node_id` 字段。

### Modified Capabilities
- `wss-connection`: 新增身份认证握手环节（Token → NodeID），连接建立后的第一条消息为 auth 消息，收到 auth_ack 后连接才算就绪。心跳和指令收发仅在认证通过后进行。
- `rtmp-streaming`: RTMP 推流 URL 格式从 `rtmp://{url}/live/{device_id}` 变更为 `rtmp://{ip}:{port}/live/{nodeid}_{device_type}_{device_name}`，以支持 Server 侧按 Node 和设备类型区分流。

## Impact

| 影响范围 | 说明 |
|---|---|
| `network/api.py` | 整体删除（REST + WS 端点） |
| `network/wss_client.py` | 新增认证握手逻辑、NodeID 本地存储、`send()` 自动附带 node_id |
| `network/command_handler.py` | **新建** — WSS 指令分发器，字典派发 `GET_DEVICES` / `UPDATE_STREAM` |
| `network/models.py` | **新建** — 从 `api.py` 迁出 Pydantic 模型 + 设备缓存 |
| `network/__init__.py` | 移除 `api_router` 导出 |
| `constant.py` | 新增 `NodeResponse` 枚举、`AuthStatus` 枚举 |
| `app.py` | 移除 Swagger/路由注册、新增 CommandHandler 注册、更新配置读取 |
| `services/ffmpeg_runner.py` | RTMP URL 格式变更（含 `nodeid`、`device_type`、`device_name`） |
| `services/device_registry.py` | import 路径从 `network.api` 改为 `network.models` |
| `services/device_enumerator.py` | import 路径变更 |
| `services/state_machine.py` | import 路径变更 |
| `tests/` | 删除 REST/WS 测试；新增 `test_command_handler.py`、`test_wss_integration.py`、`mock_server.js` |
| `.env` / `.env.example` | 配置字段对齐为 `SERVER_BASE_URL`、`RTMP_PORT`、`RTMP_DEBUG`、`WSS_PORT` |

## Addendum: Dynamic dshow capture options

Windows dshow video capture SHALL no longer hardcode one capture mode for
every camera. Before starting a video push, Node SHALL probe the selected
device with ffmpeg dshow `-list_options true`, parse advertised video modes,
and build the capture command from a compatible size/fps/pixel_format.

This keeps Node as the source of truth for raw device capture while allowing
different cameras to use their actual supported modes. If probing fails or no
usable mode is returned, Node SHALL use a conservative fallback of
`640x480@30`.
