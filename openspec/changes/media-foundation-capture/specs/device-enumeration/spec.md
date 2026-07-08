## MODIFIED Requirements

### Requirement: Enumerate video and audio input devices via ffmpeg
系统 SHALL 使用 ffmpeg 的 `-list_devices` 参数枚举本机可用的视频和音频输入设备。在 Windows 平台上 SHALL 优先使用 Media Foundation API 进行枚举，MF 不可用时回退到 ffmpeg dshow。

#### Scenario: List devices on Windows (ffmpeg fallback)
- **WHEN** 运行在 Windows 平台且 MF 不可用
- **THEN** 系统执行 `ffmpeg -list_devices true -f dshow -i dummy`，从 stderr 输出中解析设备名和类型

#### Scenario: List devices on Windows (MF preferred)
- **WHEN** 运行在 Windows 平台且 MF API 可用
- **THEN** 系统使用 MF 枚举设备，返回 `list[DeviceItem]`

#### Scenario: List devices on macOS
- **WHEN** 运行在 macOS 平台
- **THEN** 系统执行 `ffmpeg -list_devices true -f avfoundation -i dummy`，从 stderr 输出中解析设备名和类型

#### Scenario: No devices found
- **WHEN** 本机无可用的视频或音频输入设备
- **THEN** 系统返回空设备列表，状态正常
