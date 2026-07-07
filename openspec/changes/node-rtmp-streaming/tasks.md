## 1. Configuration & Module Structure

- [ ] 1.1 更新 `.env.example`，新增 `SERVER_WS_URL`、`SERVER_RTMP_URL`
- [ ] 1.2 新建 `network/wss_client.py`（WSS 客户端模块）
- [ ] 1.3 新建 `services/` 包（`__init__.py`、`device_registry.py`、`ffmpeg_runner.py`、`state_machine.py`）
- [ ] 1.4 安装 pytest 测试框架：`pip install pytest pytest-asyncio pytest-cov`
- [ ] 1.5 新建 `tests/` 目录与 `tests/conftest.py`（FastAPI `TestClient` + `AsyncClient` fixture）

## 2. Device Enumeration (device-enumeration)

- [ ] 2.1 实现 `services/device_enumerator.py`：调用 ffmpeg `-list_devices` 枚举设备
- [ ] 2.2 实现跨平台适配（Windows `dshow` / macOS `avfoundation`）
- [ ] 2.3 解析 ffmpeg stderr 输出为 `list[DeviceItem]` 格式
- [ ] 2.4 在 `POST /api/device/list` 端点挂接真实枚举逻辑
- [ ] 2.5 编写 device_enumerator 的单元测试（mock ffmpeg subprocess，覆盖 Windows/macOS/Linux 解析）

## 3. Active Device Registry (active-device-registry)

- [ ] 3.1 实现 `services/device_registry.py`：`dict[device_id, DeviceItem]` + `asyncio.Lock`
- [ ] 3.2 实现 `add`/`remove`/`list`/`contains` 操作
- [ ] 3.3 在 `POST /api/device/update` 端点挂接 registry 操作（enabled=true → add, false → remove）
- [ ] 3.4 编写 registry 的单元测试（并发 add/remove、空表操作）

## 4. RTMP Streaming Engine (rtmp-streaming)

- [ ] 4.1 实现 `services/ffmpeg_runner.py`：`start_stream(device) -> asyncio.Process`
- [ ] 4.2 构建 ffmpeg 命令行（平台感知的输入格式、H.264 编码、RTMP 输出）
- [ ] 4.3 实现 `stop_stream(process)`：`terminate()` + 5s 超时 → `kill()`
- [ ] 4.4 实现 RTMP URL 拼接逻辑（`SERVER_RTMP_URL + "/" + device_id`）
- [ ] 4.5 编写 ffmpeg_runner 的单元测试（mock subprocess）
- [ ] 4.6 实现 `STREAM_DEBUG` 模式：env 开启后忽略启用设备表，推所有设备到 `rtmp://127.0.0.1:1935/live/<device_id>`

## 5. Stream State Machine (stream-state-machine)

- [ ] 5.1 实现 `services/state_machine.py`：5s 间隔定时巡检 task
- [ ] 5.2 实现 diff 逻辑：registry vs 当前 ffmpeg 进程 dict → 启动/停止
- [ ] 5.3 实现异常退出重试逻辑（最多 3 次，超限后标记异常并通过 WSS 上报）
- [ ] 5.4 实现优雅关闭：SIGTERM/SIGINT 时遍历终止所有 ffmpeg 子进程
- [ ] 5.5 启动时清理残留 ffmpeg 僵尸进程
- [ ] 5.6 编写状态机的单元测试（mock registry + mock ffmpeg_runner）

## 6. WSS Client (wss-connection)

- [ ] 6.1 实现 `network/wss_client.py`：使用 `websockets` 库建立 WSS 连接
- [ ] 6.2 实现指数退避重连（1s / 2s / 4s / ... 上限 60s）
- [ ] 6.3 实现心跳：每 30s 发送 `{"type": "heartbeat"}`
- [ ] 6.4 实现消息接收与分发（解析 `command` 字段 → 调用对应 handler）
- [ ] 6.5 向 `constant.py` 的 `ServerCommand` 枚举对齐消息类型
- [ ] 6.6 编写 WSS 客户端的单元测试（mock WebSocket server）

## 7. Startup Orchestration

- [ ] 7.1 在 `app.py` 的 startup event 中启动 WSS 客户端 task
- [ ] 7.2 在 `app.py` 的 startup event 中启动状态机 task
- [ ] 7.3 在 `app.py` 的 shutdown event 中优雅关闭所有后台 task
- [ ] 7.4 启动时执行一次设备枚举，将结果缓存供 API 使用
- [ ] 7.5 端到端验证：启动 Node → WSS 连接成功 → 设备枚举 → API 返回正确数据

## 8. API Integration Tests

- [ ] 8.1 编写 `tests/test_api_device_list.py`：TestClient 调用 `POST /api/device/list`，验证返回格式匹配 `GetDeviceListOutput`
- [ ] 8.2 编写 `tests/test_api_device_update.py`：TestClient 调用 `POST /api/device/update`，验证 registry 状态变更
- [ ] 8.3 编写 `tests/test_api_websocket.py`：AsyncClient 测试 `/api/ws` WebSocket 连接与消息收发
- [ ] 8.4 编写 `tests/test_api_health.py`：TestClient 验证 `GET /` 和 `GET /health` 返回 200

## 9. Integration & Polish

- [ ] 9.1 更新 `README.md` 补充新增的 `.env` 配置项和架构说明
- [ ] 9.2 运行 `pytest --cov` 确保核心模块覆盖率 ≥ 80%
- [ ] 9.3 `network/api.py` 中 WebSocket `/ws` 端点与 WSS 客户端的 Server 指令处理对齐
- [ ] 9.4 端到端验证：启动 Node → WSS 连接成功 → 设备枚举 → API 返回正确数据
