# Stream State Machine

## Purpose

Periodically reconcile the active device registry against running ffmpeg processes, starting and stopping streams to converge the actual state to the desired state.

## Requirements

### Requirement: State machine polls registry periodically
系统 SHALL 每 5 秒运行一次巡检 loop，对比启用设备表与当前运行的 ffmpeg 进程状态。

#### Scenario: New device detected
- **WHEN** 巡检发现启用设备表中有 `cam-01` 但没有对应的 ffmpeg 进程
- **THEN** 系统为该设备启动 ffmpeg RTMP 推流进程

#### Scenario: Removed device detected
- **WHEN** 巡检发现 ffmpeg 进程正在为 `cam-01` 推流，但 `cam-01` 已不在启用设备表中
- **THEN** 系统终止该 ffmpeg 进程

#### Scenario: No changes
- **WHEN** 巡检发现启用设备表与当前 ffmpeg 进程状态一致
- **THEN** 系统不做任何操作

### Requirement: Handle ffmpeg crash
当 ffmpeg 子进程异常退出时，系统 SHALL 检测并记录日志，最多重试 3 次。

#### Scenario: ffmpeg crashes during streaming
- **WHEN** `cam-01` 的 ffmpeg 进程异常退出且启用设备表中仍有该设备
- **THEN** 系统自动重启 ffmpeg 推流，并在日志中记录此次异常

#### Scenario: Retry limit exhausted
- **WHEN** 同一设备的 ffmpeg 连续异常退出 3 次
- **THEN** 系统停止重试，将设备状态标记为异常，通过 WSS 向 Server 发送警告

### Requirement: State machine started on boot
状态机 SHALL 在 Node 启动后作为后台 asyncio task 启动。

#### Scenario: State machine lifecycle
- **WHEN** Node 启动完成
- **THEN** 状态机 task 开始运行，直到 Node 进程退出

### Requirement: Cleanup on shutdown
Node 关闭时 SHALL 终止所有正在运行的 ffmpeg 子进程。

#### Scenario: Graceful shutdown
- **WHEN** Node 收到 SIGTERM 或 SIGINT
- **THEN** 系统遍历所有 ffmpeg 子进程执行 `terminate()`，等待完成后再退出
