## Why

`comtypes` 安装后 `MediaFoundationDriver.check_available()` 通过，工厂选它作为采集驱动。但 MF 驱动的采集循环未实现——`list_devices_command()` 返回假命令、`parse_device_list()` 返回空列表、采集帧的 pipe 循环不存在。结果：设备枚举返回 0、推流无法启动、全链路断裂。必须立即把控制权交还给已验证可工作的 `FfmpegDshowDriver`。

## What Changes

- **修改** `MediaFoundationDriver.check_available()`：MF 采集循环未实现前始终抛出异常，让工厂回退到 `FfmpegDshowDriver`
- **不影响**：全链路枚举→推流→RTMP 服务器→终端打印 URL 在 dshow 驱动下已验证能跑通

## Capabilities

### Modified Capabilities

- `media-foundation-capture`: MF 驱动的 `check_available()` 语义从"comtypes 可导入即为可用"改为"采集循环实现完毕始为可用"

## Impact

- **代码**: `services/capture/media_foundation.py` 单文件、`check_available()` 单方法修改
- **风险**: 无——dshow 驱动已处理 ffmpeg 7.x/8.x 兼容、设备名格式、`none` 类型
- **回退**: MF 采集循环真正实现后删除 raise 行即可恢复
