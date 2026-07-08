## Why

当前视频编码器硬编码为 `libopenh264`，音频编码器仅支持 `aac`。在不同 ffmpeg 发行版下——尤其是关闭 GPL 的 conda 包——`libx264` 不可用，`libopenh264` 也可能缺失或被替代。需要在运行时动态检测可用编码器，自动选择最优方案，优先利用 Media Foundation 硬件加速。

## What Changes

- **新增** 编码器探测模块：启动时运行 `ffmpeg -encoders`，缓存可用的视频/音频编码器列表
- **修改** 所有 `capture_command()`：视频编码器从硬编码 `libopenh264` 改为 `_pick_video_encoder()` 动态选择
- **修改** 音频编码器同理：`_pick_audio_encoder()`，优先级 `aac` → `libmp3lame` → 内置 `aac`
- **优先级**：视频 `h264_mf` > `libopenh264` > `libx264` > `mpeg4`；音频 `aac` > `libmp3lame`

## Capabilities

### New Capabilities

- `dynamic-encoder-selection`: 系统在启动时探测 ffmpeg 可用编码器，构建采集命令时自动选择最优编码器

## Impact

- **代码**: `services/capture/ffmpeg_dshow.py`、`media_foundation.py`（也可能新增一个 shared encoder resolver）
- **运行时**: 启动时额外一次 `ffmpeg -encoders` 子进程调用（<0.5s，只执行一次并缓存）
- **依赖**: 无新增
