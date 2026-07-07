## Context

Monitor Node 运行在内网，无公网 IP，需主动向外连接。当前项目已完成 FastAPI 骨架（`app.py`、`network/api.py`），包含设备列表查询和推流状态更新的 REST 端点及 WebSocket 入口。本次设计将在此基础上补齐 WSS 客户端、设备枚举、RTMP 推流调度能力。

约束：
- RTMP 推流由 ffmpeg 子进程执行
- 设备信息由 ffmpeg 的 `-list_devices` 枚举
- Node 启动后第一件事是向 Server 建立 WSS 连接
- 推流触发条件：设备存在于"启用中"设备表内

## Goals / Non-Goals

**Goals:**
- Node 启动时自动注册到 Server（WSS），并保持连接
- 能通过 ffmpeg 枚举本机可用的音视频输入设备
- 维护"启用中"设备表，Server 通过 API 远程增删
- 对启用中的设备，自动启动/停止 ffmpeg RTMP 推流子进程
- 推流状态机定时巡检，处理进程异常退出

**Non-Goals:**
- 不实现 RTMP 协议本身（由 ffmpeg 承担）
- 不处理视频编码参数调优（使用合理默认值，后续可配）
- 不实现 Server 侧逻辑
- 不做视频录制/本地存储

## Decisions

### 1. WSS 客户端：使用 `websockets` 库（uvicorn 自带）

uvicorn 的 `websockets` 依赖同时支持服务端和客户端，无需新增包。
Node 启动后在后台 `asyncio.create_task` 中运行 WSS 客户端，与 FastAPI 主 loop 共存。

**替代方案**：`aiohttp` — 功能更全但多余，且需要额外安装。

### 2. 设备枚举：`ffmpeg-python` 调用底层二进制

使用 `ffmpeg-python`（`requirements.txt` 已有）的 `ffmpeg.probe()` 或直接 `subprocess.run` 调用：
- Windows：`ffmpeg -list_devices true -f dshow -i dummy`
- macOS：`ffmpeg -list_devices true -f avfoundation -i dummy`
- Linux：`ffmpeg -list_devices true -f v4l2 -i dummy`

从 stderr 解析设备名，通过 `constant.py` 中的 `DeviceStatus` 枚举管理设备状态。

**替代方案**：系统原生 API（DirectShow / AVFoundation / v4l2）— 更精确但平台强绑定，ffmpeg 跨平台且已依赖。

### 3. 启用设备表：内存 `dict[str, DeviceItem]` + asyncio 锁

简单 dict 加 `asyncio.Lock` 保证协程安全。Server 通过 `/api/device/update` 修改表后，状态机在下一轮巡检中感知变更。

**替代方案**：SQLite — 太重，设备表生命周期与进程一致。

### 4. ffmpeg 子进程管理：`ffmpeg-python` 链式 API

使用 `ffmpeg-python`（`requirements.txt` 已有）的链式 API 构造命令，避免手拼容易出错的裸字符串：

```python
import ffmpeg

process = (
    ffmpeg
    .input(device_name, format=input_format)      # dshow / avfoundation / v4l2
    .output(
        rtmp_url,
        format="flv",
        vcodec="libx264",
        preset="veryfast",
        tune="zerolatency",
    )
    .overwrite_output()
    .run_async(asyncio=True)                      # 返回 asyncio subprocess
)
```

停止：`process.terminate()` + 5s 超时后 `process.kill()`。

**替代方案**：手拼命令行 `"ffmpeg -f dshow -i ..."` — 参数一多就容易引号/转义出错，`ffmpeg-python` 参数化构造更稳健。

### 5. 状态机：定时巡检 loop（默认 5s 间隔）

一个后台 asyncio task，循环执行：
1. 取启用设备表快照
2. 对比当前运行的 ffmpeg 进程 dict
3. 新设备 → `create_subprocess_exec` 启动推流
4. 已移除设备 → `terminate()` 停止推流
5. 异常退出的进程 → 记录日志，可选重试

### 6. 本地验证模式：`STREAM_DEBUG` 环境变量

当 `.env` 中 `STREAM_DEBUG=true` 时：
- 忽略启用设备表，推流**所有**枚举到的输入设备
- RTMP 目标重定向到 `rtmp://127.0.0.1:1935/live/<device_id>`
- 操作员在本地启动 RTMP 服务器（如 OBS → 媒体源 → VLC 源），拉 `rtmp://127.0.0.1:1935/live/<device_id>` 即可验证
- 启动时将全部已启动的 RTMP 推流地址输出到控制台日志，方便操作员直接复制到 OBS

此模式仅在 Node 启动时根据 env 切换，不影响正常生产路径。

## Risks / Trade-offs

- **[ffmpeg 进程泄漏]** 如果 Node 异常退出，子进程可能残留 → 启动时先 `taskkill` / `pkill` 清理僵尸 ffmpeg
- **[WSS 断连]** Server 重启或网络波动导致 WSS 断开 → 指数退避重连，重连后重新上报设备状态
- **[推流资源占用]** 多设备同时推流可能占满 CPU/带宽 → 先不做限制，后续可加并发推流上限
- **[跨平台设备枚举]** ffmpeg 的 list_devices 参数在 Windows (`dshow`) 和 Linux (`v4l2`) / macOS (`avfoundation`) 不同 → 通过 `sys.platform` 检测 + 配置覆盖

## Open Questions

- RTMP 推流地址格式：`rtmp://<server>/live/<device_id>` 还是由 Server 在 update 请求中下发？
- 推流异常退出后重试次数上限？
- 是否需要心跳机制定期向 Server 报告设备状态（不仅仅是 WebSocket 响应）？
