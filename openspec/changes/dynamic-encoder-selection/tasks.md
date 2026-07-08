## 1. 编码器探测模块

- [ ] 1.1 新建 `services/capture/encoder_resolver.py`：`_detect_encoders()` + `get_video_encoder()` + `get_audio_encoder()`
- [ ] 1.2 实现 `ffmpeg -encoders` 子进程调用，解析 stdout，按优先级匹配

## 2. 集成到 driver

- [ ] 2.1 `ffmpeg_dshow.py`：`_video_command` 和 `_audio_command` 改用 `get_video_encoder()` / `get_audio_encoder()`
- [ ] 2.2 `media_foundation.py`：`capture_command` 视频编码器改用 `get_video_encoder()`

## 3. 验证

- [ ] 3.1 运行 `pytest` 全部通过
- [ ] 3.2 启动程序，确认日志中编码器选择正确（当前环境应为 `h264_mf`）
