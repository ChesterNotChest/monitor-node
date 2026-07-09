## 1. 常量与枚举对齐

- [ ] 1.1 更新 `constant.py`：删除 `ServerCommand.GET_DEVICES`，将 `UPDATE_STREAM` 值改为 `"UPDATE_STREAM"`
- [ ] 1.2 删除 `constant.py` 中的 `NodeResponse` 枚举（响应改为简单 dict `{success, message}`）
- [ ] 1.3 保留 `AuthStatus` 枚举不变

## 2. Server 设备映射

- [ ] 2.1 在 `network/models.py` 中新增 `_server_video_map: dict[int, str]` 和 `_server_audio_map: dict[int, str]`
- [ ] 2.2 新增 `set_server_device_maps(videos: list[dict], audios: list[dict])` 函数：解析 `{id, name}` 列表并写入映射表
- [ ] 2.3 新增 `get_server_device_name(device_type: str, device_id: int) -> Optional[str]` 函数：从对应映射表反查 device_name
- [ ] 2.4 新增 `clear_server_device_maps()` 函数：清空两个映射表

## 3. WSS 客户端认证协议对齐

- [ ] 3.1 修改 `_authenticate()` 的认证消息格式：从 `{"type":"auth","token":"xxx"}` 改为 `{"token":"xxx"}`
- [ ] 3.2 修改 `_authenticate()` 的响应解析：期望 `{"session_token":"...","videos":[...],"audios":[...]}` 格式
- [ ] 3.3 将 `_node_id` 重命名为 `_session_token`，`node_id` 属性改为 `session_token`
- [ ] 3.4 认证成功后调用 `set_server_device_maps(videos, audios)` 填充映射表
- [ ] 3.5 断连时调用 `clear_server_device_maps()` 清除映射表
- [ ] 3.6 移除 `set_on_auth_complete` 回调（将在 app.py 中直接调用 `_on_auth_restart_streams` 同步修改）

## 4. 指令处理器对齐

- [ ] 4.1 删除 `handle_get_devices` 方法和对应的 `_dispatch` 条目
- [ ] 4.2 修改 `handle_update_stream` 签名：解析 `device_type`（str）、`device_id`（int）、`enable`（bool）
- [ ] 4.3 通过 `get_server_device_name(device_type, device_id)` 反查 device_name
- [ ] 4.4 在本地设备缓存中匹配 device_name + device_type，找到则操作 registry
- [ ] 4.5 响应格式改为 `{"success": true/false, "message": "..."}`
- [ ] 4.6 移除响应中的 `node_id` 字段

## 5. RTMP URL 格式对齐

- [ ] 5.1 修改 `_build_rtmp_url` 签名：从 `(device: DeviceItem)` 改为 `(device: DeviceItem, server_device_id: int = 0)`
- [ ] 5.2 RTMP URL 格式改为 `rtmp://{host}:{port}/live/{device_name}_{device_type}_{device_id}`
- [ ] 5.3 `device_name` 使用原始名称（不 slug 化），空格保留
- [ ] 5.4 `device_id` 从 server 映射表获取；未映射时使用 `0` 作为占位
- [ ] 5.5 移除 `_slugify` 的调用（不再需要 slug 化）

## 6. 应用入口适配

- [ ] 6.1 更新 `app.py` 中 `on_auth_restart_streams` 回调：使用 `session_token` 替代 `node_id`
- [ ] 6.2 更新相关日志中的 `node_id` 引用为 `session_token`

## 7. 测试更新

- [ ] 7.1 更新 `tests/test_command_handler.py`：删除 get_devices 相关测试，更新 update_stream 测试适配新字段格式
- [ ] 7.2 更新 `tests/test_wss_auth.py`：认证消息格式改为 `{"token":"xxx"}`，响应格式改为 `{session_token, videos, audios}`
- [ ] 7.3 更新 `tests/test_wss_client.py`：适配 `session_token` 属性
- [ ] 7.4 更新 `tests/test_ffmpeg_runner.py`：适配新 RTMP URL 格式（`device_name` 不 slug 化、`device_id` 为 int）
- [ ] 7.5 更新 `tests/test_wss_integration.py`：适配新协议格式

## 8. 验证

- [ ] 8.1 运行全量 `pytest` 确保所有测试通过
- [ ] 8.2 DEBUG_WSS 模式手动验证：启动假 WSS 服务器 + Node，确认认证和 UPDATE_STREAM 流程正确
