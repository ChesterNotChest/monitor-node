## ADDED Requirements

### Requirement: Enumerate devices via Media Foundation on Windows
在 Windows 平台，系统 SHALL 优先使用 Media Foundation API 枚举本机可用的视频和音频输入设备。

#### Scenario: Enumerate via MF
- **WHEN** 运行在 Windows 平台且 MF API 可用
- **THEN** 系统调用 MF 枚举接口，返回 `list[DeviceItem]`，包含设备名、类型、唯一 ID

#### Scenario: MF unavailable falls back to ffmpeg
- **WHEN** Windows 平台上 MF API 初始化失败（如缺少运行时组件）
- **THEN** 系统回退到 ffmpeg `-list_devices true -f dshow -i dummy` 方式

### Requirement: Capture raw video frames via Media Foundation
系统 SHALL 使用 MF 打开指定设备，按配置的分辨率和帧率采集原始视频帧。

#### Scenario: Successful capture
- **WHEN** 设备 `USB2.0 HD UVC WebCam` 被启用且 MF 成功打开该设备
- **THEN** 系统进入采集循环，以 640x480@15fps BGR24 格式持续输出帧到 stdout pipe

#### Scenario: Device open failure
- **WHEN** MF 无法打开指定设备（设备被占用或断开）
- **THEN** 系统返回错误，由状态机处理重试逻辑

### Requirement: Pipe raw frames to ffmpeg via stdin
MF 采集到的原始帧 SHALL 通过 subprocess stdin 管道传输给 ffmpeg 进程，ffmpeg 从 `-i -` 读取。

#### Scenario: Pipe setup
- **WHEN** 启动一个设备推流
- **THEN** 系统创建两个子进程：MF 采集进程（输出到 stdout）和 ffmpeg 进程（从 stdin 读取），通过管道连接
