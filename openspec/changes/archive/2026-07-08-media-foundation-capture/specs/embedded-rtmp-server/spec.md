## ADDED Requirements

### Requirement: STREAM_DEBUG launches embedded RTMP server
当 `STREAM_DEBUG=true` 时，系统 SHALL 在启动阶段自动拉起 `node-media-server` 作为本地 RTMP 服务器，监听 `rtmp://127.0.0.1:1935/live`。

#### Scenario: Server starts successfully
- **WHEN** `STREAM_DEBUG=true` 且 Node.js 可用且端口 1935 空闲
- **THEN** RTMP 服务器启动，控制台输出 `[STREAM_DEBUG] RTMP 服务器已启动: rtmp://127.0.0.1:1935/live`

#### Scenario: Port occupied
- **WHEN** `STREAM_DEBUG=true` 但端口 1935 已被其他进程占用
- **THEN** 系统输出明确错误信息，不启动推流

#### Scenario: Node.js not found
- **WHEN** `STREAM_DEBUG=true` 但系统未安装 Node.js
- **THEN** 系统输出 `[STREAM_DEBUG] Node.js 未找到，RTMP 服务器无法启动`，跳过推流

### Requirement: RTMP server stopped on shutdown
RTMP 服务器 SHALL 在程序关闭时被自动终止。

#### Scenario: Graceful shutdown
- **WHEN** 程序收到退出信号（Ctrl+C 或 SIGTERM）
- **THEN** 系统终止 Node.js RTMP 服务器进程

### Requirement: RTMP server URL logged at startup
RTMP 服务器启动后 SHALL 在控制台打印每个设备的完整拉流地址。

#### Scenario: Print stream URLs
- **WHEN** RTMP 服务器已启动且设备列表已知
- **THEN** 控制台输出每个设备的拉流地址，格式为 `rtmp://127.0.0.1:1935/live/<device_id>`
