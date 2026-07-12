# Dynamic Encoder Selection

## Purpose

Detect available ffmpeg video/audio encoders at runtime and select the best available codec for capture commands, prioritizing hardware acceleration.

## Requirements

### Requirement: Detect available encoders at startup
系统 SHALL 在首次构建采集命令时运行 `ffmpeg -encoders` 探测可用编码器，结果缓存供后续使用。

#### Scenario: Encoder detection succeeds
- **WHEN** ffmpeg 可用且 `-encoders` 输出正常
- **THEN** 系统返回按优先级排列的可用视频编码器和音频编码器名

#### Scenario: ffmpeg unavailable
- **WHEN** ffmpeg 二进制不可用
- **THEN** 系统回退到硬编码兜底编码器 `mpeg4`（视频）和内置 `aac`（音频）

### Requirement: Dynamic video encoder selection
采集命令中的视频编码器 SHALL 由运行时探测结果决定，不作为硬编码常量。

#### Scenario: MF hardware encoder available
- **WHEN** Windows 平台上 `h264_mf` 在 `ffmpeg -encoders` 输出中
- **THEN** `capture_command()` 使用 `-c:v h264_mf`

#### Scenario: MF unavailable, libopenh264 available
- **WHEN** `h264_mf` 不在列表中但 `libopenh264` 在
- **THEN** `capture_command()` 使用 `-c:v libopenh264 -allow_skip_frames 1`

### Requirement: Dynamic audio encoder selection
音频编码器 SHALL 按优先级 `aac` > `libmp3lame` 动态选择。

#### Scenario: AAC available
- **WHEN** `aac` 在编码器列表中
- **THEN** 使用 `-c:a aac -b:a 128k`
