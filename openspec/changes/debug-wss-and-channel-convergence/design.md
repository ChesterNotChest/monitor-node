## Context

当前 Node 有三套通信通道：

| 通道 | 状态 | 原因 |
|---|---|---|
| `POST /api/device/*` REST 端点 | 死通道 | Server 无法访问 Node 的私有 IP |
| `WS /api/ws` 本地 WebSocket | 死通道 | 同上 |
| `WssClient` 出站 WSS 连接 | 功能完整但缺身份认证 | 能连上 Server，但无 Token 认证和 NodeID 分配 |

需要收敛为 WSS 单一通道 + RTMP 推流。同时补齐 Node 身份标识协议和 DEBUG_WSS 调试模式。

## Goals / Non-Goals

**Goals:**
- WSS 成为 Server↔Node 的唯一指令通道
- 实现 Node 身份标识协议：Token 认证 → NodeID 分配
- 实现 DEBUG_WSS 模式：固定 Token + 本地伪 WSS 服务器
- 对齐所有配置字段：`SERVER_BASE_URL`、`RTMP_PORT`、`RTMP_DEBUG`、`WSS_PORT`
- RTMP URL 格式对齐为 `rtmp://{ip}:{port}/live/{nodeid}_{device_type}_{device_name}`
- 所有 docstring 使用中文
- 合并前通过 pytest 全量测试

**Non-Goals:**
- RTMP 推流核心逻辑（ffmpeg 子进程管理、状态机协调）不做改动
- 设备枚举逻辑不做改动
- 跨平台采集驱动不做改动
- Server 侧实现不做改动（仅规约对齐）
- nginx 配置不做改动

## Decisions

### 1. 文件重组：`network/api.py` → `network/command_handler.py` + `network/models.py`

**决策**：删除 `api.py`，将其 Pydantic 模型和缓存函数迁至 `network/models.py`，将命令处理逻辑重构为 `network/command_handler.py` 中的 `CommandHandler` 类。

**原因**：
- `api.py` 混杂了 FastAPI 路由定义和业务调度逻辑，且 REST/WS 端点为死通道
- 拆出后 WSS 客户端只负责传输（连接/重连/心跳/认证），CommandHandler 只负责分发
- 保持类似 API 路由的可读性：`ServerCommand` 枚举 → handler 函数字典映射

### 2. 指令分发模式：字典派发表

**决策**：使用 `dict[ServerCommand, Callable]` 映射命令到 handler 方法。

```python
class CommandHandler:
    def __init__(self, wss_client: WssClient) -> None:
        self._wss = wss_client
        self._dispatch: dict[str, Callable] = {
            ServerCommand.GET_DEVICES: self.handle_get_devices,
            ServerCommand.UPDATE_STREAM: self.handle_update_stream,
        }
```

**原因**：读起来像路由注册表；新增命令只需加一行映射；与 `ServerCommand` 枚举形成双重约束。

### 3. Node 身份标识协议：Token → NodeID

**决策**：WSS 连接建立后，Node 立即发送认证消息，Server 回传 NodeID。认证完成后才进入心跳和指令收发。

```
Node                                    Server
  |                                        |
  |--- WSS 握手 ------------------------->|
  |                                        |
  |--- {"type":"auth","token":"xxx"} ----->|
  |                                        |
  |<-- {"type":"auth_ack","node_id":"n1"} -|
  |                                        |
  |--- {"type":"heartbeat"} -------------->|  (认证后开始)
  |                                        |
  |<-- {"command":"get_devices","node_id":"n1"} -|
  |                                        |
  |--- {"type":"get_devices_response",     |
  |      "node_id":"n1", ...} ------------>|
```

**原因**：
- Node 表由 Server 侧维护，NodeID 由 Server 分配
- Token 用于 Server 识别和授权 Node
- 后续所有指令携带 `node_id` 以关联到具体 Node
- 认证在心跳之前进行，确保未认证连接不消耗资源

**备选方案**：在 WSS URL 查询参数中传递 Token → 拒绝，因为查询参数在 WSS 握手时明文传输，不如在连接建立后通过加密通道发送安全。

### 4. DEBUG_WSS 模式设计

**决策**：新增 `DEBUG_WSS` 环境变量。开启后：
- Node 使用固定 Token `"debug-token-fixed"` 发起认证
- Node 连接地址强制为 `ws://127.0.0.1:{WSS_PORT}/ws`（非加密 WebSocket）
- 假 WSS 服务器（`tests/mock_server.js`）识别 DEBUG_WSS 的固定 Token，分配固定 NodeID `"debug-node-001"`
- 假 WSS 服务器支持完整的身份认证 + 两种命令收发

**原因**：
- 固定 Token 和 NodeID 用于验证"身份标识验证"功能是否正常工作
- 本地 WebSocket（非加密）方便调试，无需证书配置
- mock_server.js 作为独立脚本，可用于手动端到端验证

### 5. 配置字段对齐

**决策**：从旧有的零散配置迁移到以下规范化字段：

| 旧字段 | 新字段 | 说明 |
|---|---|---|
| `SERVER_WS_URL` | `SERVER_BASE_URL` + `WSS_PORT` | WSS 连接地址由 base + port 拼接 |
| `SERVER_RTMP_URL` | `SERVER_BASE_URL` + `RTMP_PORT` | RTMP 地址由 base + port 拼接 |
| `STREAM_DEBUG` | `RTMP_DEBUG` | 本地 RTMP 调试模式 |
| — | `DEBUG_WSS` | **新增** — WSS 调试模式 |
| `WSS_ENABLED` | — | **移除** — 始终启用 WSS |
| `SECRET_KEY` | `SECRET_KEY` | 保留，作为 Node Token |
| `DEBUG_INFO` | `DEBUG_INFO` | 保留 |

WSS URL 构造：`ws://{SERVER_BASE_URL}:{WSS_PORT}/ws`（DEBUG_WSS 时强制 `ws://`，生产环境通过 nginx 升级为 `wss://`）

RTMP URL 构造：`rtmp://{SERVER_BASE_URL}:{RTMP_PORT}/live/{nodeid}_{device_type}_{device_name}`

**原因**：设计与实现对齐，字段语义清晰，避免完整 URL 中协议和端口的冗余配置。

### 6. RTMP URL 格式变更

**决策**：RTMP 推流地址从 `rtmp://{url}/live/{device_id}` 变更为 `rtmp://{ip}:{port}/live/{nodeid}_{device_type}_{device_name}`。

**原因**：
- 包含 `nodeid` 使 Server 能按 Node 区分流来源
- 包含 `device_type` 使 Server 能区分音频流和视频流
- 包含 `device_name` 保持人类可读性
- 与总设计方案中的 RTMP 格式规约完全对齐

**示例**：
- `rtmp://127.0.0.1:1935/live/debug-node-001_video_Integrated Camera`
- `rtmp://192.168.1.100:1935/live/node-abc123_audio_Microphone Array`

**注意事项**：`device_name` 中的空格和特殊字符需要处理。采用 URL-safe slug 化（小写 + 空格转连字符）。

### 7. NodeID 本地存储

**决策**：在 `WssClient` 中新增 `_node_id: Optional[str]` 字段，认证成功后由 `auth_ack` 消息设置。`CommandHandler` 和 `ffmpeg_runner` 通过 `wss_client.node_id` 属性获取。

**原因**：
- NodeID 是 Server 分配的，Node 侧只读不写
- 作为 WSS 会话的核心标识，存储在 WSS 客户端中语义正确
- RTMP URL 构造和命令响应都需要 NodeID

### 8. 移除 Swagger 但保留 Health

**决策**：移除 `docs_url="/docs"`、`redoc_url`、`/api/*` 路由；保留 `GET /` 和 `GET /health`。

**原因**：Swagger 展示的 REST/WS 端点已不存在，保留会误导；`/health` 是运维基本需求。

## Risks / Trade-offs

- **[风险] WSS 是单点故障** → 当前 WSS 客户端已有指数退避重连（1s→60s），重连后自动重新认证，状态机继续协调
- **[风险] 认证超时阻塞** → 设置 10s 认证超时，超时自动断开并重连
- **[风险] NodeID 在重连后变化** → Server 可能在每次认证时分配不同 NodeID，Node 侧应以最新 auth_ack 为准，更新本地存储
- **[风险] RTMP URL 中 device_name 含特殊字符** → slug 化处理：只保留字母数字和连字符，空格转连字符，中文保留（FFmpeg 支持 UTF-8 URL）

## Migration Plan

1. 更新 `.env` 配置文件，替换旧字段
2. 删除 `network/api.py`，创建 `network/models.py` 和 `network/command_handler.py`
3. 修改 `network/wss_client.py` 增加认证流程
4. 修改 `services/ffmpeg_runner.py` 更新 RTMP URL 构造
5. 更新 `app.py` 启动流程
6. 新增 `tests/mock_server.js` 假 WSS 服务器
7. 新增/更新测试文件
8. 运行全量 pytest 验证
9. 删除 `openspec/changes/replace-rest-with-wss/`（被本变更取代）

## Open Questions

- `SECRET_KEY` 作为 Token 是否足够？后续是否需要独立的 `NODE_TOKEN` 环境变量？
- RTMP URL 中 `device_name` 的 slug 化策略是否需要 md5/sha256 哈希以避免超长文件名？
