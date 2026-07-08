## Context

当前 ffmpeg 同时承担设备采集（dshow）、编码（H.264）、推流（RTMP）三个角色。ffmpeg 8.x 的 dshow 模块存在设备兼容问题：MJPEG 像素格式检测失败、`none` 类型虚拟设备不支持、设备名格式随版本漂移（`[dshow @]` → `[in#0 @]`）。约束：Windows 平台须支持，非 Windows 平台保持现有路径不变。

## Goals / Non-Goals

**Goals:**
- Windows 上使用 Media Foundation 原生 API 采集音视频设备
- 采集原始帧通过 stdin pipe 传给 ffmpeg，ffmpeg 仅编码+推流
- STREAM_DEBUG 模式下自动启动 `node-media-server` RTMP 服务器并打印地址
- macOS/Linux 保持现有 ffmpeg 采集路径不受影响
- gitignore 覆盖 Node.js 依赖目录

**Non-Goals:**
- 不实现 ffplay 预览
- 不做视频录制/本地存储
- 不处理非 Windows 平台的 MF 等价方案（那些平台 ffmpeg 采集足够稳定）
- 不做 GPU 加速编码（后续可加，本次用软件 H.264）

## Decisions

### 1. 采集方案：Media Foundation via `pywinrt` 或 `comtypes`

通过 Windows Runtime API (`Windows.Media.Capture.MediaCapture`) 或 COM 接口调用 Media Foundation 枚举设备和采集帧。Python 侧使用 `comtypes` 或直接调用 Windows Runtime。

**替代方案 A — OpenCV `VideoCapture`**: OpenCV 的 dshow backend 同样依赖 ffmpeg/dshow 底层，没有解决兼容问题。
**替代方案 B — DirectShow COM**: 比 MF 更底层，API 更繁琐，MF 是 Windows 推荐的现代多媒体 API。
**替代方案 C — 纯 ffmpeg**: 已验证不可靠。

### 2. ffmpeg stdin pipe 模式

MF 采集帧后通过 subprocess stdin 传给 ffmpeg：

```
ffmpeg -f rawvideo -pix_fmt bgr24 -s 640x480 -r 30 -i - \
       -c:v libx264 -preset veryfast -tune zerolatency \
       -pix_fmt yuv420p -f flv rtmp://...
```

`-i -` 表示从 stdin 读取原始视频。MF 采集端负责：
- 打开设备、设置分辨率/帧率
- 循环读取帧、写入 ffmpeg stdin
- 检测 ffmpeg 退出并处理重连

音频同理：`-f s16le -ar 44100 -ac 2 -i -`

### 3. 驱动层架构

```
services/capture/
├── __init__.py          # get_capture_driver() 工厂
├── base.py              # CaptureDriver ABC
├── media_foundation.py  # Windows MF 实现
├── ffmpeg_dshow.py      # 回退：Windows ffmpeg dshow
├── ffmpeg_avfoundation.py  # macOS
└── ffmpeg_v4l2.py       # Linux
```

`get_capture_driver()` 选择逻辑：
- Windows → 尝试 MF，失败回退 ffmpeg dshow
- macOS → ffmpeg avfoundation
- Linux → ffmpeg v4l2

### 4. 内嵌 RTMP 服务器

STREAM_DEBUG 时 `app.py` 启动 `node rtmp_server/index.js`，`node-media-server` 监听 `rtmp://127.0.0.1:1935/live/<stream-key>`。启动后打印：

```
[STREAM_DEBUG] RTMP 服务器已启动: rtmp://127.0.0.1:1935/live
[STREAM_DEBUG] OBS 拉流地址: rtmp://127.0.0.1:1935/live/<device_id>
```

关闭时终止 Node.js 进程。

### 5. gitignore

```
rtmp_server/node_modules/
*.pyc 相关（已有）
```

## Risks / Trade-offs

- **[MF API 复杂度]** Media Foundation 比 ffmpeg dshow 参数多 → 封装成简洁的 `MediaFoundationDriver`，对外只暴露 `start/stop/read_frame`
- **[非 Windows 回退]** macOS/Linux 仍用 ffmpeg → `get_capture_driver()` 自动选择，调用方无感知
- **[ffmpeg stdin pipe 开销]** 原始视频数据量大（640x480 bgr24 @30fps ≈ 26 MB/s）→ 使用 `subprocess.PIPE` 的内存缓冲区，ffmpeg 侧用 `-rtbufsize` 控制
- **[node-media-server 端口冲突]** 1935 被占用时 server 退出 → 启动前检测端口，被占用时打印明确错误
