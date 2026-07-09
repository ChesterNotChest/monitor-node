## 1. 编码规范与质量门禁

- [ ] 1.1 更新 `openspec/config.yaml`，添加 docstring 中文规范和 pytest 门禁规则

## 2. 提取共享数据模型

- [ ] 2.1 创建 `network/models.py`，从 `network/api.py` 迁出 `DeviceItem`、Pydantic 模型和 `set_cached_devices` / `get_cached_devices` 缓存函数
- [ ] 2.2 更新 `services/device_registry.py` 的 import：`from network.api import DeviceItem` → `from network.models import DeviceItem`
- [ ] 2.3 更新 `services/device_enumerator.py` 的 import 同上
- [ ] 2.4 更新 `services/ffmpeg_runner.py` 的 import 同上
- [ ] 2.5 更新 `tests/test_device_registry.py` 的 import 同上
- [ ] 2.6 更新 `tests/test_device_enumerator.py` 的 import 同上
- [ ] 2.7 更新 `tests/test_ffmpeg_runner.py` 的 import 同上
- [ ] 2.8 更新 `tests/test_state_machine.py` 的 import 同上
- [ ] 2.9 更新 `network/__init__.py`：移除 `from network.api import router`，不再导出 api_router

## 3. 新建 WSS 指令分发器

- [ ] 3.1 创建 `network/command_handler.py`，实现 `CommandHandler` 类（`__init__` 构建 `dict[ServerCommand, Callable]` 派发表，`dispatch` 入口查表分发）
- [ ] 3.2 实现 `handle_get_devices` — 从缓存读取设备列表，可选 device_type 过滤，通过 `wss_client.send()` 回传 `get_devices_response`
- [ ] 3.3 实现 `handle_update_stream` — 校验 device_id，操作 `DeviceRegistry` 启停设备，通过 `wss_client.send()` 回传 `update_stream_response`；不直接操作 ffmpeg 子进程

## 4. 改造 WSS 客户端

- [ ] 4.1 `wss_client.py` 的 `_default_handler` 从 "info log" 升级为 "warning log"，明确标记未注册 handler 的异常路径

## 5. 清理 app.py

- [ ] 5.1 移除 `docs_url="/docs"` 和 `redoc_url`，禁掉 Swagger
- [ ] 5.2 移除 `from network.api import router` 和 `app.include_router(device_router)`
- [ ] 5.3 将 `from network.api import set_cached_devices` 改为 `from network.models import set_cached_devices`
- [ ] 5.4 在 `wss_client.start()` 之前创建 `CommandHandler(wss_client)` 并通过 `wss_client.set_message_handler(handler.dispatch)` 注册

## 6. 清理 network/api.py

- [ ] 6.1 从 api.py 删除所有 FastAPI router / endpoint 代码（`router = APIRouter(...)`、`@router.websocket`、`@router.post`）
- [ ] 6.2 确认 models 和缓存函数已迁至 `network/models.py` 后，删除 api.py 中的对应定义
- [ ] 6.3 **删除 `network/api.py`**——所有内容已迁出至 `models.py` 和 `command_handler.py`，不再有残留

## 7. 测试重构

- [ ] 7.1 删除 `tests/test_api_device_list.py`、`tests/test_api_device_update.py`、`tests/test_api_websocket.py`
- [ ] 7.2 新增 `tests/test_command_handler.py`，包含：
  - `TestCommandHandlerDispatch`：TC-D01~D05（5 条 dispatch 分发测试）
  - `TestHandleGetDevices`：TC-GD01~GD05（5 条设备列表业务测试）
  - `TestHandleUpdateStream`：TC-US01~US06（6 条推流启停业务测试）
- [ ] 7.3 更新 `tests/test_wss_client.py`：TC-WS01（handler 注册生效）、TC-WS02（handler 异常不崩溃）、TC-WS03（_default_handler 兜底）
- [ ] 7.4 更新 `tests/conftest.py`，新增 `MockWssClient` fixture（拦截 `send()` 到 `sent_messages` 列表）
- [ ] 7.5 新增 `tests/test_wss_integration.py`：TC-IT01~IT05（5 条 WSS 全链路集成测试），用 `websockets.serve()` 在 fixture 中启动假服务器，覆盖连接→心跳→命令→响应完整链路
- [ ] 7.6 运行 `pytest`，确认全量通过（含未改动的 test_device_enumerator、test_device_registry、test_ffmpeg_runner、test_state_machine、test_api_health）

## 8. 手动验证用伪服务器（非 CI）

- [ ] 8.1 创建 `tests/mock_server.js`：基于 `ws` 库的 WebSocket 服务端（监听 8443），连接后自动发送 `get_devices`，提供 REPL 输入 `update_stream` 命令，打印所有收到的 Node 响应
- [ ] 8.2 编写 mock_server 顶部注释（中文使用说明），用于开发者本地手动调试 WSS 全链路
