## ADDED Requirements

### Requirement: RTMP server address logged at startup
系统 SHALL 在 STREAM_DEBUG 模式下启动时将内嵌 RTMP 服务器的监听地址和每个设备的拉流地址打印到控制台。

#### Scenario: Print RTMP addresses
- **WHEN** `STREAM_DEBUG=true` 且 RTMP 服务器成功启动
- **THEN** 控制台输出 `[STREAM_DEBUG] RTMP 服务器已启动: rtmp://127.0.0.1:1935/live` 及每个设备的 `[STREAM_DEBUG] 拉流地址: rtmp://127.0.0.1:1935/live/<device_id>`
