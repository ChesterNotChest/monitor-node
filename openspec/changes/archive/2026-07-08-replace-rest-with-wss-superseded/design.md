## Context

当前架构存在三层通信通道，但其中两层在 Node 无公网 IP 的前提下实际无法被 Server 使用：

| 通道 | 状态 | 原因 |
|---|---|---|
| `POST /api/device/*` REST 端点 | 死通道 | Server 无法访问 Node 的私有 IP |
| `WS /api/ws` 本地 WebSocket | 死通道 | 同上，且 Swagger 无法测试 WS |
| `WssClient` 出站连接 | 空壳 | 能连上 Server，但收到命令后只打日志 |

需要收敛为单一通信通道：WSS（Node→Server 主动连接 + Server→Node 命令下发 + Node→Server 响应回传）。RTMP 推流链路保持不变。

## Goals / Non-Goals

**Goals:**
- WSS 成为 Server↔Node 的唯一指令通道
- 指令入口保持 `ServerCommand` 枚举风格，类似 API 路由的可读性
- Node 通过 WSS 回传设备列表、推流状态等响应给 Server
- 所有 docstring 使用中文
- 合并前必须通过 pytest 全量测试

**Non-Goals:**
- RTMP 推流链路不做任何改动
- 不改变 ffmpeg 子进程管理逻辑
- 不改变状态机（state machine）的协调逻辑
- 不引入新的外部依赖

## Decisions

### 1. 文件重组：`network/api.py` → `network/command_handler.py`

**决策**：将当前 `api.py` 中的 WS 命令处理逻辑抽取为 `CommandHandler` 类，放入新文件 `network/command_handler.py`。

**原因**：
- `api.py` 当前混杂了 FastAPI 路由定义和业务调度逻辑
- 拆出后 WSS 客户端只负责传输（连接/重连/心跳），CommandHandler 只负责分发
- 保持类似 API 路由的可读性：`ServerCommand` 枚举 → handler 函数的一一映射

**备选方案**：直接在 `wss_client.py` 里内联处理逻辑 → 拒绝，因为违反单一职责，且用户要求"API 式入口可读感"

### 2. 指令分发模式：字典派发表

**决策**：使用 `dict[ServerCommand, Callable]` 映射命令到 handler 方法，在 `dispatch()` 中查表调用。

```python
class CommandHandler:
    """WSS 指令分发器，根据 ServerCommand 分发到对应处理函数。"""

    def __init__(self, wss_client: WssClient) -> None:
        self._wss = wss_client
        self._dispatch: dict[str, Callable] = {
            ServerCommand.GET_DEVICES: self.handle_get_devices,
            ServerCommand.UPDATE_STREAM: self.handle_update_stream,
        }
```

**原因**：读起来像路由注册表，满足"API 入口式可读感"；新增命令只需加一行映射。与 `ServerCommand` 枚举形成编译时+运行时双重约束。

### 3. 移除 Swagger 但保留 Health

**决策**：移除 `docs_url="/docs"`、`redoc_url`、`/api/*` 路由；保留 `GET /` 和 `GET /health`。

**原因**：Swagger 展示的 REST/WS 端点已不存在，保留会误导；`/health` 是运维基本需求，与通信通道无关。

### 4. 响应协议：WSS JSON 回传

**决策**：Node 处理完 Server 命令后，通过同一 WSS 连接发回 JSON 响应，格式与当前 `api.py` 中 WS 端点的响应格式保持一致：

```json
{"type": "get_devices_response", "node_id": "...", "devices": [...], "total_count": N}
{"type": "update_stream_response", "node_id": "...", "device_id": "...", "enabled": true, "success": true, "message": "推流已启动"}
```

**原因**：响应格式已经定义好，不需要重新设计；直接复用减少变更半径。

### 5. 测试策略：用 Node.js 伪服务器验证 WSS

**决策**：提供一个轻量 Node.js 脚本（`tests/mock_server.js`），用 `ws` 库启动伪 WebSocket 服务器，用于手动验证 WSS 客户端的完整链路。

**原因**：pytest 的单元测试覆盖 handler 逻辑；伪服务器用于端到端验证 WSS 握手、心跳、命令收发。

## Risks / Trade-offs

- **[风险] 移除 REST 端点后本地调试不便** → 保留 `/health` 端点；WSS handler 逻辑可通过 pytest 单元测试覆盖，不依赖真实 Server
- **[风险] WSS 是单点故障** → 当前 WSS 客户端已有指数退避重连（1s→60s），重连后状态机自动协调，无数据丢失
- **[风险] 响应协议没有 Schema 校验** → 当前为轻量设计，暂不引入 Pydantic schema；后续如需可加

## Open Questions

- 是否需要在 `ServerCommand` 之外再定义一个 `NodeResponse` 枚举来约束响应 type？→ 当前保持字符串 type，后续按需引入

---

## 实现快查表

### 0. 新增常量 / 类型定义

**新增模块 `network/models.py`**（从 `api.py` 剥离，解决 3 个 service 的跨模块 import）：

| 类型 | 字段 | 说明 |
|---|---|---|
| `DeviceItem(BaseModel)` | `device_id: str`, `device_type: str`, `device_name: str`, `status: DeviceStatus` | 设备实体，已有，从 api.py 迁出 |
| `GetDeviceListInput(BaseModel)` | `node_id: str`, `device_type: Literal["video","audio"] \| None` | REST 时代的输入模型；WSS 模式下 handler 手动解包 dict，但保留作为类型参考 |
| `GetDeviceListOutput(BaseModel)` | `node_id: str`, `devices: list[DeviceItem]`, `total_count: int` | 同上 |
| `UpdateDeviceInput(BaseModel)` | `node_id: str`, `device_id: str`, `enabled: bool` | 同上 |
| `UpdateDeviceOutput(BaseModel)` | `node_id: str`, `device_id: str`, `enabled: bool`, `success: bool`, `message: str` | 同上 |
| `_cached_devices: list[DeviceItem]` | 模块级变量 | 启动时填充的设备缓存 |
| `set_cached_devices(devices) -> None` | — | 写入缓存 |
| `get_cached_devices() -> list[DeviceItem]` | — | 读取缓存 |

**`ServerCommand` 枚举** — 已有，不变。`constant.py:4-7`。

**`NodeResponse` 的 type 值不再新增枚举**，沿用字符串 `"get_devices_response"` / `"update_stream_response"` / `"heartbeat"` / `"error"`。

### 1. 影响的文件范围

| 文件 | 动作 | 变更量 | 风险 |
|---|---|---|---|
| `network/models.py` | **新建** — 从 api.py 迁出 Pydantic models + cache | ~60 行 | 低：纯搬迁 |
| `network/command_handler.py` | **新建** — CommandHandler 类 + 2 个 handler | ~100 行 | 中：核心新逻辑 |
| `network/api.py` | **删除** REST/WS 端点；models 迁至 models.py；废弃 router | 原 239 行 → 0 或仅保留注释 | 低：删代码 |
| `network/wss_client.py` | **微改** — `_default_handler` 日志升级 | ~5 行改动 | 低 |
| `app.py` | **删** Swagger/路由注册；**改** lifespan import 路径；**加** handler 注册 | ~10 行改动 | 中：启动链路 |
| `services/device_registry.py` | **改 import** `network.api` → `network.models` | 1 行 | 低 |
| `services/device_enumerator.py` | **改 import** 同上 | 1 行 | 低 |
| `services/ffmpeg_runner.py` | **改 import** 同上 | 1 行 | 低 |
| `network/__init__.py` | **删** `from network.api import router`，不再导出 api_router | 2 行 | 低 |
| `tests/test_device_registry.py` | **改 import** `network.api` → `network.models` | 1 行 | 低 |
| `tests/test_device_enumerator.py` | **改 import** 同上 | 1 行 | 低 |
| `tests/test_ffmpeg_runner.py` | **改 import** 同上 | 1 行 | 低 |
| `tests/test_state_machine.py` | **改 import** 同上 | 1 行 | 低 |
| `openspec/config.yaml` | **加** 编码规范规则 | ~10 行 | 低 |

**不变的文件**：`constant.py`、`services/state_machine.py`、`tests/conftest.py`、`tests/test_api_health.py`。

**删除的文件**：`tests/test_api_device_list.py`、`tests/test_api_device_update.py`、`tests/test_api_websocket.py`。

**新建的测试文件**：`tests/test_command_handler.py`、`tests/mock_server.js`。

### 2. 完整数据流（函数级收口）

```
┌──────────────────────────────────────────────────────────────────────┐
│                          启动阶段 (lifespan.startup)                    │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  app.py:lifespan()                                                   │
│    │                                                                 │
│    ├─[1]─► ffmpeg_runner.kill_zombies()                              │
│    │       清理上次崩溃残留的 ffmpeg 进程（RTMP 链路不受影响）           │
│    │                                                                 │
│    ├─[2]─► enumerate_devices() ─► set_cached_devices(devices)         │
│    │       枚举所有采集设备 → 写入模块级缓存 _cached_devices              │
│    │       import: from network.models import set_cached_devices       │
│    │                                                                 │
│    ├─[3]─► handler = CommandHandler(wss_client)                       │
│    │       wss_client.set_message_handler(handler.dispatch)            │
│    │       wss_client.start()                                         │
│    │         └─► _connect_loop()                                      │
│    │               └─► _connect() → WS 握手                            │
│    │               └─► _heartbeat_loop() (30s 间隔)                    │
│    │               └─► _receive_loop() ─► handler(data)               │
│    │                                                                 │
│    └─[4]─► state_machine.start()                                     │
│              └─► _loop() → 每 5s 执行 _tick()                          │
│                    ├─ registry.snapshot() vs runner.list_running()    │
│                    ├─ to_start → ffmpeg_runner.start_stream()         │
│                    └─ to_stop  → ffmpeg_runner.stop_stream()          │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                     WSS 运行时 — get_devices                           │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Server                                                              │
│    │ WSS 下发                                                         │
│    │ {"command":"get_devices", "node_id":"n1", "device_type":null}    │
│    ▼                                                                 │
│  WssClient._receive_loop()     ← transport/wss_client.py              │
│    │ json.loads(raw) → data                                          │
│    │                                                                 │
│    ▼                                                                 │
│  WssClient._handler(data)      ← 实际指向 CommandHandler.dispatch      │
│    │                                                                 │
│    ▼                                                                 │
│  CommandHandler.dispatch(data)  ← command_handler.py                  │
│    │ command = data.get("command")                                   │
│    │ handler = self._dispatch.get(command)  # 字典查表                 │
│    │                                                                 │
│    ▼                                                                 │
│  CommandHandler.handle_get_devices(data)                              │
│    │ 1. node_id = data.get("node_id", "")                            │
│    │ 2. device_type = data.get("device_type")                        │
│    │ 3. devices = get_cached_devices()                               │
│    │ 4. if device_type: devices = [d for d in devices if ...]        │
│    │ 5. self._wss.send({...})                                        │
│    │                                                                 │
│    ▼                                                                 │
│  WssClient.send(response_dict)  ← transport/wss_client.py             │
│    │ json.dumps(data) → self._ws.send(text)                          │
│    │                                                                 │
│    ▼                                                                 │
│  Server 收到                                                          │
│    {"type":"get_devices_response","node_id":"n1","devices":[...],     │
│     "total_count":2}                                                  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────────────┐
│                    WSS 运行时 — update_stream                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  Server                                                              │
│    │ WSS 下发                                                         │
│    │ {"command":"update_stream","node_id":"n1",                       │
│    │  "device_id":"cam-01","enabled":true}                            │
│    ▼                                                                 │
│  WssClient._receive_loop() → CommandHandler.dispatch(data)            │
│    │                                                                 │
│    ▼                                                                 │
│  CommandHandler.handle_update_stream(data)                            │
│    │ 1. device_id = data.get("device_id", "")                        │
│    │ 2. if not device_id → send({"error":"missing device_id"})       │
│    │ 3. enabled = data.get("enabled", False)                         │
│    │ 4. if enabled:                                                  │
│    │      device = lookup from cache; fallback DeviceItem(unknown)    │
│    │      await device_registry.add(device)                           │
│    │    else:                                                        │
│    │      await device_registry.remove(device_id)                    │
│    │ 5. self._wss.send({type:"update_stream_response", ...})         │
│    │                                                                 │
│    │ ★ handler 不直接启动 ffmpeg ★                                    │
│    │                                                                 │
│    ═══════ 最多 5s 后 ═══════                                        │
│    │                                                                 │
│    ▼                                                                 │
│  state_machine._tick()          ← services/state_machine.py           │
│    │ registry.snapshot() → {"cam-01": DeviceItem(...)}               │
│    │ runner.list_running() → set()                                    │
│    │ to_start = {"cam-01"} - {} = {"cam-01"}                         │
│    │                                                                 │
│    ▼                                                                 │
│  ffmpeg_runner.start_stream(device)                                   │
│    │ ffmpeg ... -f dshow -i "camera" ... rtmp://nginx/live/cam-01     │
│    │                                                                 │
│    ▼                                                                 │
│  RTMP 流推至 nginx，Server 从 nginx 拉流                               │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

### 3. 函数签名与内部逻辑

#### 3.1 `network/models.py` — 共享数据模型

```python
# === 从 api.py 迁出，字段不变 ===

class DeviceItem(BaseModel):
    """采集设备实体。"""
    device_id: str        # 唯一标识
    device_type: str      # "video" | "audio"
    device_name: str      # 系统上报的设备名
    status: DeviceStatus  # IDLE | STREAMING | ONLINE | OFFLINE

# 模块级缓存（原 api.py:66-77）
_cached_devices: list[DeviceItem] = []

def set_cached_devices(devices: list[DeviceItem]) -> None:
    """更新设备缓存（启动时和重枚举后调用）。"""
    global _cached_devices
    _cached_devices = devices

def get_cached_devices() -> list[DeviceItem]:
    """返回缓存的设备列表。"""
    return _cached_devices
```

#### 3.2 `network/command_handler.py` — 核心新模块

```python
class CommandHandler:
    """WSS 指令分发器，根据 ServerCommand 分发到对应处理函数。

    通过字典派发表 dict[ServerCommand, Callable] 将命令字符串映射到
    handler 方法，保持类似 REST API 路由的可读性。新增命令只需：
    1. constant.py 添加 ServerCommand 成员
    2. 在本类添加 handle_xxx 方法
    3. 在 _dispatch 字典中加一行映射
    """

    def __init__(self, wss_client: WssClient) -> None:
        """
        Args:
            wss_client: WSS 客户端实例，用于回传响应。
                        通过 wss_client.send() 将 handler 结果发回 Server。
        """
        self._wss: WssClient = wss_client
        self._dispatch: dict[str, Callable[[dict], Awaitable[None]]] = {
            ServerCommand.GET_DEVICES: self.handle_get_devices,
            ServerCommand.UPDATE_STREAM: self.handle_update_stream,
        }

    # ---------- 入口 ----------

    async def dispatch(self, data: dict[str, Any]) -> None:
        """WSS 消息入口。由 WssClient._handler 调用。

        内部逻辑:
          1. 提取 data["command"]
          2. 查表 self._dispatch.get(command)
          3. 命中 → await handler(data)
          4. 未命中 → self._wss.send({"error": f"unknown command: {command}"})

        Args:
            data: Server 发来的原始 JSON dict，必须包含 "command" 字段。
        """
        command = data.get("command", "")
        logger.debug("CommandHandler.dispatch: %s", command)

        handler = self._dispatch.get(command)
        if handler is not None:
            await handler(data)
        else:
            await self._wss.send({"error": f"unknown command: {command}"})

    # ---------- 指令处理函数 ----------

    async def handle_get_devices(self, data: dict[str, Any]) -> None:
        """获取设备列表 + 健康状态。

        输入: {"command": "get_devices", "node_id": str, "device_type"?: str}
        输出: WSS send {"type": "get_devices_response", "node_id": str,
                        "devices": [DeviceItem.model_dump(), ...], "total_count": int}

        内部逻辑:
          1. 提取 node_id (默认 "")
          2. 提取可选的 device_type 过滤条件
          3. 从 get_cached_devices() 获取缓存设备列表
          4. 如有 device_type，按类型过滤
          5. 将 DeviceItem 序列化为 dict（model_dump()）
          6. 通过 self._wss.send() 回传
          7. 不触发重枚举——缓存在启动时已填充，如需刷新由 Server 下发单独的
             re_enumerate 命令（后续扩展）
        """
        ...

    async def handle_update_stream(self, data: dict[str, Any]) -> None:
        """启用/禁用某个设备的 RTMP 推流。

        输入: {"command": "update_stream", "node_id": str,
               "device_id": str, "enabled": bool}
        输出: WSS send {"type": "update_stream_response", "node_id": str,
                        "device_id": str, "enabled": bool,
                        "success": bool, "message": str}

        内部逻辑:
          1. 提取并校验 device_id（空 → 回传 error）
          2. 提取 enabled (默认 False)、node_id (默认 "")
          3. 启用 (enabled=true):
             a. 从缓存查找 device
             b. 找到 → device_registry.add(device)
             c. 未找到 → 构造 DeviceItem(device_type="unknown",
                device_name=device_id) → device_registry.add()
          4. 停用 (enabled=false):
             a. device_registry.remove(device_id)
          5. 回传操作结果（success=True, message="推流已启动"/"推流已停止"）
          6. ★ 不在此处启动/停止 ffmpeg 子进程 ★
             state_machine._tick() 每 5s 检测 registry 变化后执行实际的进程启停
        """
        ...
```

#### 3.3 `network/wss_client.py` — 微改

```python
# 仅改动 _default_handler，其他全部不动

async def _default_handler(self, data: dict[str, Any]) -> None:
    """兜底消息处理器——未注册 handler 时记录 warning。"""
    command = data.get("command", "unknown")
    logger.warning("WSS received message but no handler registered (command=%s)", command)
```

#### 3.4 `app.py` — 改动 3 处

```python
# 行 52-53: import 路径变更
# OLD: from network.api import set_cached_devices
# NEW: from network.models import set_cached_devices

# 行 63-67: 新增 handler 注册（在 wss_client.start() 之前）
from network.command_handler import CommandHandler
if wss_enabled:
    handler = CommandHandler(wss_client)
    wss_client.set_message_handler(handler.dispatch)
    await wss_client.start()

# 行 93-98: FastAPI 初始化
# OLD: FastAPI(docs_url="/docs", redoc_url=None, ...)
# NEW: FastAPI(docs_url=None, redoc_url=None, ...)

# 行 120-124: 删除路由注册
# DELETE: from network.api import router
# DELETE: app.include_router(device_router, prefix="/api")
```

### 4. 测试用例构建

#### 4.0 测试基础设施

`CommandHandler` 的测试采用 **mock WssClient** 模式：构造一个记录 `send()` 调用的假 WSS 客户端，断言 handler 执行后回传的 JSON 内容。

```python
# conftest.py 或 test 文件内
class MockWssClient:
    """假 WSS 客户端，拦截 send() 调用到 self.sent_messages 列表。"""
    def __init__(self):
        self.sent_messages: list[dict] = []

    async def send(self, data: dict) -> bool:
        self.sent_messages.append(data)
        return True
```

#### 4.1 `tests/test_command_handler.py` — 指令分发

| 编号 | 测试用例 | GIVEN | WHEN | THEN |
|---|---|---|---|---|
| **TC-D01** | `dispatch` 命中 `get_devices` | `CommandHandler(mock_wss)`，缓存有 1 个设备 | `dispatch({"command":"get_devices","node_id":"n1"})` | `mock_wss.sent_messages[0]["type"] == "get_devices_response"`，`total_count == 1` |
| **TC-D02** | `dispatch` 命中 `update_stream` (启用) | `CommandHandler(mock_wss)`，缓存有 cam-01 | `dispatch({"command":"update_stream","device_id":"cam-01","enabled":true})` | `mock_wss.sent_messages[0]["type"] == "update_stream_response"`，`success == True`，`message == "推流已启动"` |
| **TC-D03** | `dispatch` 命中 `update_stream` (停用) | `CommandHandler(mock_wss)`，cam-01 在 registry 中 | `dispatch({"command":"update_stream","device_id":"cam-01","enabled":false})` | `mock_wss.sent_messages[0]["message"] == "推流已停止"` |
| **TC-D04** | `dispatch` 收到未知命令 | `CommandHandler(mock_wss)` | `dispatch({"command":"nonexistent"})` | `mock_wss.sent_messages[0] == {"error":"unknown command: nonexistent"}` |
| **TC-D05** | `dispatch` 收到空 command | `CommandHandler(mock_wss)` | `dispatch({"other_field":"x"})` | `mock_wss.sent_messages[0]["error"]` 包含 `"unknown command"` |

#### 4.2 `tests/test_command_handler.py` — get_devices 业务逻辑

| 编号 | 测试用例 | GIVEN | WHEN | THEN |
|---|---|---|---|---|
| **TC-GD01** | 缓存有设备 | `set_cached_devices([DeviceItem(id="cam-01",...), DeviceItem(id="mic-01",...)])` | `handle_get_devices({"node_id":"n1"})` | response 中 `devices` 长度 = 2，`total_count` = 2 |
| **TC-GD02** | 缓存为空 | `set_cached_devices([])` | `handle_get_devices({"node_id":"n1"})` | `total_count == 0`，`devices == []` |
| **TC-GD03** | 按 device_type 过滤 | 缓存有 1 video + 1 audio | `handle_get_devices({"device_type":"video"})` | `total_count == 1`，返回的设备 `device_type == "video"` |
| **TC-GD04** | 过滤类型无匹配 | 缓存有 1 video | `handle_get_devices({"device_type":"audio"})` | `total_count == 0` |
| **TC-GD05** | node_id 透传 | — | `handle_get_devices({"node_id":"node-xyz"})` | response 中 `node_id == "node-xyz"` |

#### 4.3 `tests/test_command_handler.py` — update_stream 业务逻辑

| 编号 | 测试用例 | GIVEN | WHEN | THEN |
|---|---|---|---|---|
| **TC-US01** | 启用，设备在缓存 | `set_cached_devices([DeviceItem(id="cam-01")])`，registry 空 | `handle_update_stream({"device_id":"cam-01","enabled":true})` | `registry.contains("cam-01") == True`；response `success==True`，`message=="推流已启动"` |
| **TC-US02** | 启用，设备不在缓存 | `set_cached_devices([])`，registry 空 | `handle_update_stream({"device_id":"cam-unknown","enabled":true})` | `registry.contains("cam-unknown") == True`，registry 中设备 `device_type=="unknown"` |
| **TC-US03** | 停用，设备在 registry | registry 有 cam-01 | `handle_update_stream({"device_id":"cam-01","enabled":false})` | `registry.contains("cam-01") == False`；response `message=="推流已停止"` |
| **TC-US04** | 缺少 device_id | — | `handle_update_stream({"enabled":true})` | response 为 `{"error":"missing device_id"}`；registry 不变 |
| **TC-US05** | device_id 为空字符串 | — | `handle_update_stream({"device_id":"","enabled":true})` | response 为 `{"error":"missing device_id"}` |
| **TC-US06** | node_id 透传 | — | `handle_update_stream({"device_id":"cam-01","enabled":true,"node_id":"node-abc"})` | response 中 `node_id=="node-abc"` |

#### 4.4 `tests/test_wss_client.py` — handler 注册/分发（更新已有）

| 编号 | 测试用例 | GIVEN | WHEN | THEN |
|---|---|---|---|---|
| **TC-WS01** | `set_message_handler` 生效 | `WssClient`，自定义 handler 记录调用 | `set_message_handler(custom)` → `_receive_loop` 收到 `{"command":"get_devices"}` | `custom` 被调用 1 次，参数为 `{"command":"get_devices"}` |
| **TC-WS02** | handler 抛异常不崩溃 | handler 抛出 `RuntimeError` | `_receive_loop` 收到消息 | WSS 连接不断开，异常被日志捕获，`logger.exception` 被调用 |
| **TC-WS03** | `_default_handler` 兜底 | 未注册任何 handler | `_receive_loop` 收到消息 | `logger.warning` 被调用，WSS 不崩溃 |

#### 4.5 `tests/test_wss_integration.py` — WSS 集成测试（CI 自动化）

采用 Python 内置的 `websockets.serve()` 在 pytest fixture 中启动假 WSS 服务器，
无需外部依赖，可直接在 CI 中运行。

```python
# 测试架构
┌──────────────── pytest 进程 ─────────────────┐
│                                               │
│  fixture: mock_wss_server                     │
│    websockets.serve(handler, host, port)       │
│    ┌─────────────────────────────┐            │
│    │ 假 Server                    │            │
│    │  - 接受 WssClient 连接        │            │
│    │  - 收到 heartbeat 不崩溃      │            │
│    │  - 发送 {"command":"get_devices",...}     │
│    │  - 等待响应，验证字段          │            │
│    │  - 发送 {"command":"update_stream",...}   │
│    │  - 等待响应，验证字段          │            │
│    └──────────┬──────────────────┘            │
│               │ ws://127.0.0.1:<random_port>  │
│    ┌──────────▼──────────────────┐            │
│    │ WssClient(url)              │            │
│    │   + CommandHandler          │            │
│    │   + 真实业务逻辑             │            │
│    └─────────────────────────────┘            │
│                                               │
└───────────────────────────────────────────────┘
```

| 编号 | 测试用例 | GIVEN | WHEN | THEN |
|---|---|---|---|---|
| **TC-IT01** | WSS 连接 + 心跳 | 假服务器启动，WssClient 连接 | 等待 35s（超过心跳间隔 30s） | 假服务器至少收到 1 条 `{"type":"heartbeat"}` |
| **TC-IT02** | get_devices 全链路 | 假服务器启动，缓存有设备 | 假服务器发送 `{"command":"get_devices","node_id":"n1"}` | 假服务器收到 `{"type":"get_devices_response","node_id":"n1","devices":[...],"total_count":N}` |
| **TC-IT03** | update_stream 启用全链路 | 假服务器启动 | 假服务器发送 `{"command":"update_stream","device_id":"cam-01","enabled":true}` | 假服务器收到 `{"type":"update_stream_response","success":true,"message":"推流已启动"}` |
| **TC-IT04** | update_stream 停用全链路 | registry 有 cam-01 | 假服务器发送 `{"command":"update_stream","device_id":"cam-01","enabled":false}` | 假服务器收到 `{"type":"update_stream_response","success":true,"message":"推流已停止"}` |
| **TC-IT05** | 未知命令处理 | 假服务器启动 | 假服务器发送 `{"command":"nonexistent"}` | 假服务器收到 `{"error":"unknown command: nonexistent"}` |

#### 4.6 `tests/mock_server.js` — WSS 手动验证工具（非 CI）

```
文件: tests/mock_server.js
依赖: npm install ws (一次性)
用途: 开发者本地手动调试，不纳入 CI

功能:
  1. 启动 WebSocket 服务端 ws://localhost:8443
  2. 接受 Node 的 WSS 连接请求
  3. 每 30s 收到 Node 发来的 heartbeat: {"type":"heartbeat"}
  4. 连接成功后自动发送一条 get_devices 命令
  5. 提供交互式 REPL，可手动输入命令:
     > get_devices n1
     > update_stream n1 cam-01 true
     > update_stream n1 cam-01 false
  6. 所有收到的 Node 响应打印到终端，带时间戳

验证全链路:
  Node(wss_client) → 连上 mock_server → 收到 get_devices 命令
  → Node 回传设备列表 → mock_server 终端打印响应
  → 手动发 update_stream → Node 启停推流 → mock_server 终端打印结果
```

测试用例与 spec scenario 的对应关系：
- TC-GD01–GD05 → `wss-command-channel` spec: Scenario "Server 下发 get_devices 指令"
- TC-US01–US06 → `wss-command-channel` spec: Scenario "Server 下发 update_stream 启用推流" / "停用推流"
- TC-D04 → spec: Scenario "收到未知命令"
- TC-US04 → spec: Scenario "update_stream 缺少必要字段"
- TC-IT01–IT05 → 覆盖 `wss-command-channel` spec 全部场景的 **WSS 全链路集成验证**，CI 可运行
