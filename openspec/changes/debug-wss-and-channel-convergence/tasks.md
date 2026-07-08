## 1. 配置与常量对齐

- [ ] 1.1 更新 `.env.example`：替换旧字段为 `SERVER_BASE_URL`、`RTMP_PORT`、`RTMP_DEBUG`、`WSS_PORT`、`DEBUG_WSS`，新增 `SECRET_KEY`
- [ ] 1.2 更新 `.env`：同步字段变更，设置 `DEBUG_WSS=true` 为本地开发默认值
- [ ] 1.3 更新 `constant.py`：新增 `NodeResponse` 枚举（`AUTH`、`AUTH_ACK`、`AUTH_ERROR`、`GET_DEVICES_RESPONSE`、`UPDATE_STREAM_RESPONSE`、`HEARTBEAT`、`ERROR`），新增 `AuthStatus` 枚举（`PENDING`、`AUTHENTICATED`、`REJECTED`）

## 2. 数据模型提取

- [ ] 2.1 创建 `network/models.py`：从 `network/api.py` 迁出 `DeviceItem`、`GetDeviceListInput`、`GetDeviceListOutput`、`UpdateDeviceInput`、`UpdateDeviceOutput` Pydantic 模型
- [ ] 2.2 迁移 `_cached_devices`、`set_cached_devices()`、`get_cached_devices()` 到 `network/models.py`
- [ ] 2.3 更新 `services/device_registry.py`：import `DeviceItem` 从 `network.models` 而非 `network.api`
- [ ] 2.4 更新 `services/device_enumerator.py`：import `DeviceItem` 从 `network.models`
- [ ] 2.5 更新 `services/ffmpeg_runner.py`：import `DeviceItem` 从 `network.models`
- [ ] 2.6 更新 `services/state_machine.py`：import `DeviceItem` 从 `network.models`
- [ ] 2.7 更新 `tests/` 中所有测试文件：import 路径从 `network.api` 改为 `network.models`

## 3. WSS 客户端身份认证

- [ ] 3.1 在 `WssClient` 中新增 `_node_id: Optional[str]` 字段和 `node_id` 只读属性
- [ ] 3.2 新增 `_auth_status` 状态管理（`PENDING` / `AUTHENTICATED` / `REJECTED`）
- [ ] 3.3 实现 `_authenticate()` 方法：连接建立后立即发送 `{"type":"auth","token":"..."}`，等待 `auth_ack`
- [ ] 3.4 实现 10s 认证超时：超时断开并进入重连
- [ ] 3.5 实现 `auth_ack` / `auth_error` 消息处理：设置 `_node_id` 和 `_auth_status`
- [ ] 3.6 心跳仅在 `AUTHENTICATED` 状态后启动
- [ ] 3.7 `_receive_loop` 在认证完成前仅处理认证相关消息，忽略其他指令
- [ ] 3.8 连接断开时清除 `_node_id` 和重置 `_auth_status`
- [ ] 3.9 实现 `_build_ws_url()` 方法：从 `SERVER_BASE_URL` + `WSS_PORT` 拼接 WSS 地址，DEBUG_WSS 时强制 `ws://127.0.0.1:{WSS_PORT}/ws`
- [ ] 3.10 实现 Token 解析：DEBUG_WSS 时使用固定 `"debug-token-fixed"`，否则从 `SECRET_KEY` 环境变量读取

## 4. 指令分发处理器

- [ ] 4.1 创建 `network/command_handler.py`：`CommandHandler` 类，构造函数接收 `WssClient` 实例
- [ ] 4.2 实现字典派发表：`dict[str, Callable]` 映射 `ServerCommand.GET_DEVICES` → `handle_get_devices`、`ServerCommand.UPDATE_STREAM` → `handle_update_stream`
- [ ] 4.3 实现 `dispatch(data)` 入口方法：提取 `command` 字段，查表调用；未知命令回传 error；校验 `node_id` 存在性
- [ ] 4.4 实现 `handle_get_devices(data)`：从 `network.models` 获取缓存设备列表，支持 `device_type` 过滤，回传 `get_devices_response` 格式的 JSON
- [ ] 4.5 实现 `handle_update_stream(data)`：校验 `device_id`，操作 `device_registry`（添加/移除），回传 `update_stream_response` 格式的 JSON；不直接操作 ffmpeg
- [ ] 4.6 所有 handler 的响应 JSON 必须包含 `node_id` 字段

## 5. 应用入口重构

- [ ] 5.1 更新 `app.py` 的配置读取：从 `SERVER_BASE_URL`、`WSS_PORT` 等新字段读取
- [ ] 5.2 移除 `docs_url="/docs"`、`redoc_url`，设置 `docs_url=None`
- [ ] 5.3 移除 `from network.api import router` 和 `app.include_router(device_router, prefix="/api")`
- [ ] 5.4 在 lifespan 启动阶段：创建 `CommandHandler(wss_client)`，通过 `wss_client.set_message_handler(handler.dispatch)` 注册
- [ ] 5.5 更新设备缓存 import：`from network.models import set_cached_devices`
- [ ] 5.6 更新 `RTMP_DEBUG` 逻辑：替代旧 `STREAM_DEBUG` 变量名

## 6. RTMP URL 格式对齐

- [ ] 6.1 在 `ffmpeg_runner.py` 中新增 `_slugify(name: str) -> str` 静态方法：空格转连字符，保留字母数字和中文
- [ ] 6.2 重写 `_build_rtmp_url(device: DeviceItem) -> str`：格式为 `rtmp://{SERVER_BASE_URL}:{RTMP_PORT}/live/{nodeid}_{device_type}_{device_name_slug}`
- [ ] 6.3 `nodeid` 从 `wss_client.node_id` 获取；若尚未认证（node_id 为 None），使用 `"unauthenticated"` 作为占位符并记录 warning
- [ ] 6.4 `RTMP_DEBUG=true` 时 `SERVER_BASE_URL` 强制为 `127.0.0.1`

## 7. 旧代码清理

- [ ] 7.1 删除 `network/api.py`（所有 REST + WS 端点代码）
- [ ] 7.2 更新 `network/__init__.py`：移除 `from network.api import router`，不再导出 `api_router`
- [ ] 7.3 删除 `tests/test_api_device_list.py`
- [ ] 7.4 删除 `tests/test_api_device_update.py`
- [ ] 7.5 删除 `tests/test_api_websocket.py`

## 8. 假 WSS 接收者脚本

- [ ] 8.1 创建 `tests/mock_server.js`：使用 Node.js `ws` 库实现 WebSocket 服务器
- [ ] 8.2 实现身份识别逻辑：接收 `auth` 消息，识别 `"debug-token-fixed"` → 回传 `auth_ack`（`node_id: "debug-node-001"`），未知 token → 回传 `auth_error` 并关闭连接
- [ ] 8.3 实现 `get_devices` 命令发送功能：认证后自动发送一条 get_devices 指令，打印响应
- [ ] 8.4 实现 `update_stream` 命令发送功能
- [ ] 8.5 实现交互式 REPL：支持 `get_devices`、`update_stream <device_id> true/false`、`help`、`quit` 命令
- [ ] 8.6 实现心跳日志：收到 `{"type":"heartbeat"}` 时打印时间戳日志，不做响应
- [ ] 8.7 添加 `tests/mock_server/package.json`：依赖 `ws` 库

## 9. 测试

- [ ] 9.1 创建 `tests/test_command_handler.py`：覆盖所有 dispatch、handle_get_devices、handle_update_stream 场景（参考 spec 中的 Scenario）
- [ ] 9.2 新增 `MockWssClient` 测试辅助类：拦截 `send()` 调用到 `sent_messages` 列表
- [ ] 9.3 创建 `tests/test_wss_auth.py`：测试认证消息发送、auth_ack 处理、auth_error 处理、认证超时、重连后重新认证
- [ ] 9.4 更新 `tests/test_wss_client.py`：适配新的认证流程
- [ ] 9.5 更新 `tests/conftest.py`：适配新配置字段（如需要）
- [ ] 9.6 创建 `tests/test_wss_integration.py`：使用 Python `websockets.serve()` 启动假 WSS 服务器，测试 get_devices 和 update_stream 全链路

## 10. 验证与文档

- [ ] 10.1 运行全量 `pytest` 确保所有测试通过
- [ ] 10.2 手动验证：启动 `node tests/mock_server.js`，启动 Node（`DEBUG_WSS=true`），验证认证→心跳→指令收发的完整链路
- [ ] 10.3 手动验证：在 DEBUG_WSS + RTMP_DEBUG 模式下确认 RTMP URL 格式正确
- [ ] 10.4 更新 `README.md`：反映新的配置字段和启动方式
- [ ] 10.5 归档或删除 `openspec/changes/replace-rest-with-wss/`（被本变更完全取代）
