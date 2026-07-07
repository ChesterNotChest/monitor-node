## Why

Node 处于内网环境（无公网 IP），无法被 Server 直接访问，因此需要 Node 主动向 Server 发起 WebSocket 连接以接收指令。同时，Node 需要能通过 RTMP 向 Server 推送设备视频流，整个推流过程由 ffmpeg 执行、Node 程序负责编排和生命周期管理。当前项目只有 API 骨架，缺少 WSS 客户端、设备发现、ffmpeg 推流调度等核心能力。

## What Changes

- **新增** WSS 客户端：Node 启动后主动向远端 Server 发起 WebSocket 连接，作为全双工指令通道
- **新增** 设备发现：基于 ffmpeg 枚举本机可用的视频/音频输入设备
- **新增** 启用设备表：Node 内存中维护一份"启用中"设备清单，由 Server 通过 API 控制增删
- **新增** RTMP 推流引擎：对启用设备表中的每一台设备，启动 ffmpeg 子进程向 Server 推 RTMP 流；设备被移出表时停止推流
- **新增** 流状态机：对比当前 ffmpeg 进程状态与启用设备表，决定启动/停止推流，处理异常退出重试

## Capabilities

### New Capabilities

- `wss-connection`: Node 启动后主动连接远端 Server 的 WSS 端点，维持长连接，收发 JSON 指令
- `device-enumeration`: 通过 ffmpeg 枚举本机可用的视频/音频设备，返回设备 ID、类型、名称
- `active-device-registry`: 维护"启用中"设备表（内存），提供 add/remove/list 操作，支持 Server 通过 API 远程修改
- `rtmp-streaming`: 管理 ffmpeg 子进程，按 RTMP 协议向 Server 推流，支持启动、停止、健康检查
- `stream-state-machine`: 定时比对启用设备表与当前 ffmpeg 进程状态，自动启动新设备推流、停止已移除设备推流、处理异常退出

### Modified Capabilities

<!-- 当前 openspec/specs/ 为空，无已存在的 spec 需修改 -->

## Impact

- **代码**: `app.py` 新增 WSS 客户端启动逻辑；`network/api.py` 的 POST 端点与 WebSocket 连接实际设备发现与推流控制；新增推流引擎模块
- **依赖**: `ffmpeg-python`（已有）用于设备枚举；`websockets`（uvicorn 已带）用于 WSS 客户端；ffmpeg 二进制（conda 已有）
- **配置**: `.env` 新增 `SERVER_WS_URL`、`SERVER_RTMP_URL` 等远端 Server 地址
