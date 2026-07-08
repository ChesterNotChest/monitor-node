## Context

ffmpeg 编码器可用性因编译选项而异。同一平台的不同发行版（conda vs 系统包 vs 自行编译）可能有完全不同的编码器集合。硬编码器名会导致某些环境直接无法推流。

## Goals / Non-Goals

**Goals:**
- 所有 `capture_command()` 动态选择视频/音频编码器
- MF 硬件编码器（`h264_mf`）最高优先级
- 启动时一次探测，结果缓存供后续使用
- 不增加外部依赖

**Non-Goals:**
- 不实现编码器参数调优
- 不处理 GPU 加速（NVENC、AMF 等）

## Decisions

### 1. 探测方式：`ffmpeg -encoders` 子进程

```python
@functools.lru_cache(maxsize=1)
def _detect_encoders() -> tuple[str, str]:
    """Returns (video_encoder, audio_encoder). Cached after first call."""
    output = subprocess.run(
        ["ffmpeg", "-encoders"], capture_output=True, text=True, timeout=5
    ).stdout

    video = _first_found(output, "h264_mf", "libopenh264", "libx264", "mpeg4")
    audio = _first_found(output, "aac", "libmp3lame")
    return video, audio
```

### 2. 优先级

视频：`h264_mf`（MF 硬件）→ `libopenh264`（BSD 软件）→ `libx264`（GPL 软件）→ `mpeg4`（兜底）

音频：`aac`（内置/FFmpeg AAC）→ `libmp3lame`（MP3，如果 AAC 不在）

### 3. 集成方式

放在 `services/capture/__init__.py` 或新建 `services/capture/encoder_resolver.py`。每个 driver 的 `capture_command()` 调用 `get_video_encoder()` / `get_audio_encoder()` 替代硬编码字符串。

## Risks / Trade-offs

- **[探测开销]** 每次进程启动额外 0.3-0.5s → 只执行一次，`lru_cache` 保证后续调用零开销
- **[mpeg4 兜底质量]** mpeg4 编码效率低于 H.264 → 仅当所有 H.264 编码器都不可用时启用，极少发生
