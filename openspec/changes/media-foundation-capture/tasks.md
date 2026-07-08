## 1. Embedded RTMP Server

- [ ] 1.1 创建 `rtmp_server/` 目录：`package.json`、`index.js`（使用 `node-media-server`）
- [ ] 1.2 `rtmp_server/index.js`：监听 `rtmp://127.0.0.1:1935/live`，启动时 console.log 地址
- [ ] 1.3 `npm install` 安装 `node-media-server` 依赖
- [ ] 1.4 `app.py`：STREAM_DEBUG 时 `_start_rtmp_server()` 启动 Node.js 子进程
- [ ] 1.5 `app.py`：STREAM_DEBUG 时打印 `RTMP 服务器已启动: rtmp://127.0.0.1:1935/live` 和各设备拉流地址
- [ ] 1.6 `app.py` shutdown 时 `_stop_rtmp_server()` 终止 Node.js 进程
- [ ] 1.7 gitignore：添加 `rtmp_server/node_modules/`

## 2. Capture Driver Layer

- [ ] 2.1 创建 `services/capture/__init__.py`：`get_capture_driver()` 工厂（Windows → MF，fallback → ffmpeg，macOS/Linux → ffmpeg）
- [ ] 2.2 创建 `services/capture/base.py`：`CaptureDriver` ABC（`list_devices_command` / `capture_command` / `parse_device_list`）
- [ ] 2.3 创建 `services/capture/media_foundation.py`：实现 `MediaFoundationDriver`
- [ ] 2.4 创建 `services/capture/ffmpeg_dshow.py`：将原有 dshow 逻辑迁移到此
- [ ] 2.5 创建 `services/capture/ffmpeg_avfoundation.py`：将原有 avfoundation 逻辑迁移到此
- [ ] 2.6 创建 `services/capture/ffmpeg_v4l2.py`：将原有 v4l2 逻辑迁移到此

## 3. Media Foundation Capture Implementation

- [ ] 3.1 MF 设备枚举：调用 Windows Runtime `MediaCapture` API 列出视频/音频设备
- [ ] 3.2 MF 视频采集：打开指定摄像头，设置 640x480@15fps BGR24 格式
- [ ] 3.3 MF 音频采集：打开指定麦克风，设置 PCM 44100Hz 格式
- [ ] 3.4 MF 采集循环：读取帧 → 写入 stdout（作为 pipe 给 ffmpeg）
- [ ] 3.5 MF 错误处理：设备断开/占用时返回清晰错误

## 4. Refactor ffmpeg_runner for Pipe Mode

- [ ] 4.1 `ffmpeg_runner.start_stream()`：Windows 时启动两个子进程（MF 采集 + ffmpeg），通过 `subprocess.PIPE` 连接
- [ ] 4.2 ffmpeg 命令使用 `-f rawvideo -pix_fmt bgr24 -s 640x480 -r 15 -i -` stdin 模式
- [ ] 4.3 `ffmpeg_runner.stop_stream()`：同时终止 MF 采集进程和 ffmpeg 进程
- [ ] 4.4 非 Windows 平台保持原有 `list[str]` 命令 + 直接 spawn 方式不变

## 5. Refactor device_enumerator

- [ ] 5.1 `device_enumerator.py` 委托给 `get_capture_driver().list_devices_command()` 和 `.parse_device_list()`
- [ ] 5.2 Windows: 调用 MF 枚举，失败时 fallback 到 ffmpeg dshow 枚举

## 6. State Machine Retry Limit

- [ ] 6.1 每个设备连续失败超过 5 次后停止重试，打印一次 warning
- [ ] 6.2 `_dead` 集合中的设备不再启动推流

## 7. Remove ffmpeg-python Dependency

- [ ] 7.1 `requirements.txt`：移除 `ffmpeg-python`
- [ ] 7.2 `ffmpeg_runner.py`：移除 `import ffmpeg`，命令构建改用驱动层的 `capture_command()` 返回的 `list[str]`

## 8. Tests

- [ ] 8.1 `tests/test_capture_drivers.py`：测试 MF driver 枚举和命令构建（mock Windows Runtime）
- [ ] 8.2 `tests/test_ffmpeg_runner.py`：适配新的 stdin pipe 模式
- [ ] 8.3 `tests/test_state_machine.py`：测试 retry limit 和 dead device 行为
- [ ] 8.4 `tests/test_device_enumerator.py`：适配驱动层委托

## 9. Gitignore & Polish

- [ ] 9.1 `.gitignore`：添加 `rtmp_server/node_modules/`、`*.pyc` 构建产物
- [ ] 9.2 `README.md`：更新 STREAM_DEBUG 使用说明
- [ ] 9.3 运行 `pytest` 确保所有测试通过
