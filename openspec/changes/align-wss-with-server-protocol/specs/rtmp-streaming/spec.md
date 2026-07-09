# RTMP Streaming (Delta)

## MODIFIED Requirements

### Requirement: Each device gets a dedicated RTMP URL
每个设备的 RTMP 推流地址 SHALL 由 `rtmp://{SERVER_BASE_URL}:{RTMP_PORT}/live/{device_name}_{device_type}_{device_id}` 格式拼接而成。

其中：
- `{SERVER_BASE_URL}` 为配置的基础地址
- `{RTMP_PORT}` 为配置的 RTMP 端口
- `{device_name}` 为 Server 在认证握手时下发的设备原始名称（**保留空格和原始大小写，不做 slug 化**）
- `{device_type}` 为 `"video"` 或 `"audio"`
- `{device_id}` 为 Server 侧数据库中的设备 ID（整数）

`RTMP_DEBUG=true` 时，`SERVER_BASE_URL` SHALL 强制为 `127.0.0.1`。

#### Scenario: RTMP URL construction
- **WHEN** `SERVER_BASE_URL` 为 `192.168.1.100`，`RTMP_PORT` 为 `1935`，设备映射为 `video_id=1 → "Integrated Camera"`
- **THEN** 推流地址为 `rtmp://192.168.1.100:1935/live/Integrated Camera_video_1`

#### Scenario: RTMP URL construction in DEBUG mode
- **WHEN** `RTMP_DEBUG=true`，`RTMP_PORT` 为 `1935`，设备映射为 `audio_id=2 → "Microphone Array"`
- **THEN** `SERVER_BASE_URL` 强制为 `127.0.0.1`
- **AND** 推流地址为 `rtmp://127.0.0.1:1935/live/Microphone Array_audio_2`

#### Scenario: No server device mapping available (pre-auth)
- **WHEN** 设备在 WSS 认证完成前被推流（RTMP_DEBUG 模式）
- **THEN** `device_name` 使用本地枚举的名称，`device_id` 使用 `"0"` 作为占位符
- **AND** 推流地址形如 `rtmp://127.0.0.1:1935/live/Integrated Camera_video_0`

### Requirement: Start ffmpeg RTMP push for a device
当设备被标记为启用时，系统 SHALL 为该设备启动一个 ffmpeg 子进程，将设备捕获的视频/音频推流到 Server 的 RTMP 端点。RTMP URL 按上述格式构造。

#### Scenario: Start streaming a video device with server mapping
- **WHEN** 设备 `Integrated Camera`（视频输入）被启用，且 server 映射为 `video_id=1`
- **THEN** 系统执行 ffmpeg 推流到 `rtmp://127.0.0.1:1935/live/Integrated Camera_video_1`
