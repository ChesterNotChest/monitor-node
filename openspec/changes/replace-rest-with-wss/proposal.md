## Why

当前 Node 没有公网 IP，Server 无法主动调用 Node 上暴露的 REST API 和本地 WebSocket 端点。实际的通信链路是 Node 通过 WSS 主动连接 Server 后由 Server 下发指令，但 WSS 客户端的消息处理目前是空壳——收到命令后只打日志，没有任何业务调度。需要去掉无法使用的 REST/本地 WS 通道，让 WSS 成为唯一的 Server→Node 指令通道，并补齐消息分发和响应回传逻辑。

## What Changes

- **BREAKING**: 移除 `POST /api/device/list` REST 端点
- **BREAKING**: 移除 `POST /api/device/update` REST 端点
- **BREAKING**: 移除 `WS /api/ws` 本地 WebSocket 端点
- **BREAKING**: 移除 Swagger UI (`/docs`) 和相关文档路由
- 为 WSS 客户端实现基于 `ServerCommand` 的指令分发处理器
- 补充 Node→Server 的 WSS 响应回传逻辑（设备列表、推流状态）
- RTMP 推流链路保持不变
- 新增编码规范：所有 docstring 使用中文
- 新增质量门禁：合并前必须通过 pytest

## Capabilities

### New Capabilities
- `wss-command-channel`: WSS 作为唯一的 Server→Node 指令通道，支持两个命令类型——`GET_DEVICES`（获取设备列表+健康状态）和 `UPDATE_STREAM`（启停推流），处理结果通过同一 WSS 连接回传。
- `coding-standards`: 编码规范——所有模块、类、函数的 docstring 必须使用中文；提交前必须通过 `pytest` 全量测试。

### Modified Capabilities
<!-- 无现有 specs 需修改 -->

## Impact

| 影响范围 | 说明 |
|---|---|
| `network/api.py` | 整体废弃或重写为纯 WSS 指令处理器 |
| `network/wss_client.py` | 新增 message handler 注册和 `ServerCommand` 分发 |
| `app.py` | 移除 REST/WS 路由注册，移除 `/docs`，恢复 `redoc_url=None`，启动时注册 WSS handler |
| `constant.py` | 可能补充 Node→Server 的响应类型常量 |
| `tests/` | 移除 REST/WS 相关测试，新增 WSS handler 测试 |
| `openspec/config.yaml` | 新增编码规范和测试门禁规则 |
