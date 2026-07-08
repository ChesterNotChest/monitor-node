## ADDED Requirements

### Requirement: Start ffmpeg RTMP push for a device
当设备被标记为启用时，系统 SHALL 为该设备启动一个 ffmpeg 子进程，将设备捕获的视频/音频推流到 Server 的 RTMP 端点。

#### Scenario: Start streaming a video device
- **WHEN** 设备 `cam-01`（视频输入）被启用
- **THEN** 系统执行 `ffmpeg -f dshow -i "cam-01" -c:v libx264 -preset veryfast -tune zerolatency -f flv <rtmp_url>`（Windows），子进程进入运行态

#### Scenario: Start streaming with platform-specific input format
- **WHEN** 运行在 macOS 且设备 `FaceTime HD Camera` 被启用
- **THEN** 系统执行 `ffmpeg -f avfoundation -i "FaceTime HD Camera" -c:v libx264 -f flv <rtmp_url>`

### Requirement: Stop ffmpeg RTMP push for a device
当设备从启用表中移除时，系统 SHALL 终止对应的 ffmpeg 子进程。

#### Scenario: Stop an active stream
- **WHEN** 设备 `cam-01` 被停用且对应 ffmpeg 进程正在运行
- **THEN** 系统调用 `process.terminate()`，等待最多 5 秒后 `process.wait()`，成功停止

#### Scenario: Force kill stuck ffmpeg
- **WHEN** ffmpeg 进程在 5 秒内未响应 `terminate()`
- **THEN** 系统调用 `process.kill()` 强制结束

### Requirement: Each device gets a dedicated RTMP URL
每个设备的 RTMP 推流地址 SHALL 由配置的 `SERVER_RTMP_URL` 基础地址 + `/<device_id>` 拼接而成。

#### Scenario: RTMP URL construction
- **WHEN** `SERVER_RTMP_URL` 配置为 `rtmp://server.example.com/live`
- **THEN** 设备 `cam-01` 的推流地址为 `rtmp://server.example.com/live/cam-01`
