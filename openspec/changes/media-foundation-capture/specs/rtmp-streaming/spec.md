## MODIFIED Requirements

### Requirement: Start ffmpeg RTMP push for a device
当设备被标记为启用时，系统 SHALL 为该设备启动推流。Windows 平台上 SHALL 使用 Media Foundation 采集原始帧，通过 stdin pipe 传给 ffmpeg 编码后推流到 RTMP 端点。非 Windows 平台保持 ffmpeg 直接采集方式。

#### Scenario: Start streaming on Windows (MF + ffmpeg pipe)
- **WHEN** 设备 `cam-01`（视频输入）在 Windows 上被启用
- **THEN** 系统启动 MF 采集进程采集原始帧，同时启动 `ffmpeg -f rawvideo -pix_fmt bgr24 -s 640x480 -r 15 -i - -c:v libx264 -preset veryfast -tune zerolatency -pix_fmt yuv420p -f flv <rtmp_url>` 从 stdin 读取并编码推流

#### Scenario: Start streaming on macOS (ffmpeg direct)
- **WHEN** 运行在 macOS 且设备 `FaceTime HD Camera` 被启用
- **THEN** 系统执行 `ffmpeg -f avfoundation -i "FaceTime HD Camera" -c:v libx264 -f flv <rtmp_url>`（保持现有行为）

### Requirement: Each device gets a dedicated RTMP URL
每个设备的 RTMP 推流地址 SHALL 由配置的 `SERVER_RTMP_URL` 基础地址 + `/<device_id>` 拼接而成。`STREAM_DEBUG=true` 时 SHALL 强制使用 `rtmp://127.0.0.1:1935/live/<device_id>`。

#### Scenario: RTMP URL construction
- **WHEN** `SERVER_RTMP_URL` 配置为 `rtmp://server.example.com/live`
- **THEN** 设备 `cam-01` 的推流地址为 `rtmp://server.example.com/live/cam-01`

#### Scenario: STREAM_DEBUG URL override
- **WHEN** `STREAM_DEBUG=true`
- **THEN** 所有设备推流地址为 `rtmp://127.0.0.1:1935/live/<device_id>`，忽略 `SERVER_RTMP_URL` 配置
