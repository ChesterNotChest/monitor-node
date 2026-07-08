# Device Enumeration

## Purpose

Discover available video and audio capture devices on the local machine using ffmpeg's device-listing capability.

## Requirements

### Requirement: Enumerate video and audio input devices via ffmpeg
系统 SHALL 使用 ffmpeg 的 `-list_devices` 参数枚举本机可用的视频和音频输入设备。

#### Scenario: List devices on Windows
- **WHEN** 运行在 Windows 平台
- **THEN** 系统执行 `ffmpeg -list_devices true -f dshow -i dummy`，从 stderr 输出中解析设备名和类型

#### Scenario: List devices on macOS
- **WHEN** 运行在 macOS 平台
- **THEN** 系统执行 `ffmpeg -list_devices true -f avfoundation -i dummy`，从 stderr 输出中解析设备名和类型

#### Scenario: No devices found
- **WHEN** 本机无可用的视频或音频输入设备
- **THEN** 系统返回空设备列表，状态正常

### Requirement: Return structured device list
枚举结果 SHALL 返回 `list[DeviceItem]` 格式，包含 `device_id`、`device_type`、`device_name` 字段。

#### Scenario: Parse ffmpeg output
- **WHEN** ffmpeg 输出包含设备名如 `"Integrated Camera" (video)` 和 `"Microphone Array" (audio)`
- **THEN** 系统返回 `[{"device_id": "...", "device_type": "video", "device_name": "Integrated Camera"}, {"device_id": "...", "device_type": "audio", "device_name": "Microphone Array"}]`
