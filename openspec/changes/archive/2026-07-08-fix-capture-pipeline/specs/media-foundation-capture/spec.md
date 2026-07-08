## MODIFIED Requirements

### Requirement: Enumerate devices via Media Foundation on Windows
在 Windows 平台，系统 SHALL 优先使用 Media Foundation API 枚举本机可用的视频和音频输入设备。MF 驱动 SHALL 通过 `check_available()` 自检——当采集循环未实现时，SHALL 主动报告不可用，让工厂回退到 ffmpeg dshow 驱动。

#### Scenario: MF self-check fails
- **WHEN** MF 驱动的采集循环尚未实现
- **THEN** `check_available()` 抛出异常，工厂回退到 `FfmpegDshowDriver`

#### Scenario: MF unavailable falls back to ffmpeg
- **WHEN** Windows 平台上 MF API 初始化失败（如缺少运行时组件或采集循环未实现）
- **THEN** 系统回退到 ffmpeg `-list_devices true -f dshow -i dummy` 方式
