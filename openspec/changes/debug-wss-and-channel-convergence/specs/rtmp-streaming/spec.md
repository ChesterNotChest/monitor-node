# RTMP Streaming (Delta)

## MODIFIED Requirements

### Requirement: Each device gets a dedicated RTMP URL
每个设备的 RTMP 推流地址 SHALL 由 `rtmp://{SERVER_BASE_URL}:{RTMP_PORT}/live/{nodeid}_{device_type}_{device_name}` 格式拼接而成。

其中：
- `{SERVER_BASE_URL}` 为配置的基础地址（如 `127.0.0.1` 或 `nginx.example.com`）
- `{RTMP_PORT}` 为配置的 RTMP 端口（如 `1935`）
- `{nodeid}` 为认证后 Server 分配的 NodeID
- `{device_type}` 为设备类型（`video` 或 `audio`）
- `{device_name}` 为经过 slug 化处理的设备名称（空格转连字符、仅保留字母数字和连字符）

`RTMP_DEBUG=true` 时，`SERVER_BASE_URL` SHALL 强制为 `127.0.0.1`。

#### Scenario: RTMP URL construction in production
- **WHEN** `SERVER_BASE_URL` 为 `192.168.1.100`，`RTMP_PORT` 为 `1935`，NodeID 为 `node-abc123`，设备为 video 类型 `Integrated Camera`
- **THEN** 推流地址为 `rtmp://192.168.1.100:1935/live/node-abc123_video_integrated-camera`

#### Scenario: RTMP URL construction in DEBUG mode
- **WHEN** `RTMP_DEBUG=true`，`RTMP_PORT` 为 `1935`，NodeID 为 `debug-node-001`，设备为 audio 类型 `Microphone Array`
- **THEN** `SERVER_BASE_URL` 强制为 `127.0.0.1`
- **AND** 推流地址为 `rtmp://127.0.0.1:1935/live/debug-node-001_audio_microphone-array`

#### Scenario: RTMP URL with special characters in device name
- **WHEN** 设备名称为 `USB2.0 HD UVC WebCam (04f2:b6fb)`
- **THEN** slug 化后为 `usb2-0-hd-uvc-webcam-04f2-b6fb`
- **AND** 推流地址包含 slug 化后的名称

### Requirement: Start ffmpeg RTMP push for a device
当设备被标记为启用时，系统 SHALL 为该设备启动一个 ffmpeg 子进程，将设备捕获的视频/音频推流到 Server 的 RTMP 端点。RTMP URL 按上述格式构造。

#### Scenario: Start streaming a video device
- **WHEN** 设备 `cam-01`（视频输入）被启用，NodeID 为 `debug-node-001`
- **THEN** 系统执行 `ffmpeg -f dshow -i "cam-01" ... -f flv rtmp://127.0.0.1:1935/live/debug-node-001_video_cam-01`（Windows），子进程进入运行态

#### Scenario: Start streaming with platform-specific input format
- **WHEN** 运行在 macOS 且设备 `FaceTime HD Camera` 被启用，NodeID 为 `node-xyz`
- **THEN** 系统执行 `ffmpeg -f avfoundation -i "FaceTime HD Camera" -c:v libx264 -f flv rtmp://server.example.com:1935/live/node-xyz_video_facetime-hd-camera`

### Requirement: Windows dshow uses device-supported capture options
When starting a Windows DirectShow video device, Node SHALL query the device's
ffmpeg dshow options and select a capture mode that the device advertises.
The generated ffmpeg command SHALL use the selected `-video_size` and
`-framerate`, and SHALL include an input `-pixel_format` when the selected
mode advertises one.

If option probing fails or returns no usable video modes, Node SHALL fall back
to `640x480@30` instead of `640x480@15`.

#### Scenario: Select a supported dshow mode
- **WHEN** dshow option probing for `Integrated Camera` advertises
  `640x480@30` with `pixel_format=yuyv422`
- **THEN** Node builds the ffmpeg command with `-video_size 640x480`,
  `-framerate 30`, and `-pixel_format yuyv422`

#### Scenario: Fall back when dshow option probing is unavailable
- **WHEN** dshow option probing fails or produces no parseable modes
- **THEN** Node builds the ffmpeg command with `-video_size 640x480` and
  `-framerate 30`
