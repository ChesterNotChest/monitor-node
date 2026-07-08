## Why

ffmpeg dshow 采集在 ffmpeg 8.x 上有严重的设备兼容问题（MJPEG 解码失败、虚拟摄像头不支持、设备名格式版本漂移），导致多台设备无法正常推流。将采集层从 ffmpeg 迁移到 Windows Media Foundation 可从驱动层面保证设备兼容性，ffmpeg 仅负责编码和 RTMP 推流。

## What Changes

- **新增** 内嵌 RTMP 服务器：STREAM_DEBUG 时自动启动 `node-media-server`，监听本地 IP，在控制台打印服务器地址
- **新增** Windows Media Foundation 采集模块：使用原生 Windows API 打开摄像头/麦克风，输出原始视频帧
- **重构** ffmpeg 角色：从"采集+编码+推流"变为"编码+推流"，采集帧通过 stdin pipe 传入
- **新增** gitignore 条目：覆盖 Node.js 依赖和 Media Foundation 构建产物
- **移除** ffmpeg-python 依赖：命令构建不再需要黑盒封装，改用显式 `list[str]` 命令

## Capabilities

### New Capabilities

- `media-foundation-capture`: 使用 Windows Media Foundation API 枚举和采集音视频设备，输出原始帧到管道
- `embedded-rtmp-server`: STREAM_DEBUG 模式下自动启动 `node-media-server` 作为本地 RTMP 服务器，监听 `rtmp://127.0.0.1:1935/live`

### Modified Capabilities

- `device-enumeration`: 枚举逻辑新增 Media Foundation 路径（Windows 优先），ffmpeg 路径作为非 Windows 平台回退
- `rtmp-streaming`: ffmpeg 不再负责设备采集，仅从 stdin 接收原始数据后编码推流
- `wss-connection`: 无需求变更，但 RTMP 服务器地址需在启动日志中打印

## Impact

- **代码**: 新增 `services/capture/` 包（MF 采集模块）；重构 `services/ffmpeg_runner.py`（stdin pipe 模式）；`app.py` 新增 RTMP 服务器启动逻辑
- **依赖**: 移除 `ffmpeg-python`；新增 `node-media-server`（开发依赖，已有 `rtmp_server/` 目录）
- **平台**: Media Foundation 仅 Windows 可用，macOS/Linux 保持 ffmpeg 采集路径不变
- **gitignore**: 新增 `rtmp_server/node_modules/`、构建产物
