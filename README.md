# Monitor Node

> 设备监控节点服务 — 通过 WSS 与上游 Server 建立双向指令通道，通过 ffmpeg 向 Server 推送 RTMP 视频流。WSS 是 Server↔Node 的唯一指令通道。

## 架构

```text
monitor-node/
├── app.py                         # FastAPI 应用入口 + 生命周期管理
├── constant.py                    # 枚举定义（ServerCommand, NodeResponse, AuthStatus, DeviceStatus）
├── run.py                         # uvicorn 启动入口
├── network/
│   ├── models.py                  # 共享 Pydantic 数据模型 + 设备缓存
│   ├── wss_client.py              # WSS 客户端（连接 + Token 认证 + 心跳 + 指令收发）
│   └── command_handler.py         # WSS 指令分发器（字典派发 get_devices / update_stream）
├── services/
│   ├── capture/                   # 平台采集驱动层
│   │   ├── base.py                # CaptureDriver 抽象接口
│   │   ├── ffmpeg_dshow.py        # Windows dshow 驱动
│   │   ├── ffmpeg_avfoundation.py # macOS avfoundation 驱动
│   │   ├── ffmpeg_v4l2.py         # Linux v4l2 驱动
│   │   ├── media_foundation.py    # Windows MF 驱动（规划中）
│   │   └── encoder_resolver.py    # 编码器动态探测 + 缓存
│   ├── device_enumerator.py       # 设备枚举（委托给驱动层）
│   ├── device_registry.py         # 启用设备表（内存 + asyncio 锁）
│   ├── ffmpeg_runner.py           # ffmpeg 子进程生命周期管理
│   └── state_machine.py           # 流状态机（定时巡检 + 重试上限）
├── rtmp_server/                   # RTMP_DEBUG 内嵌 RTMP 服务器
│   ├── package.json
│   ├── index.js                   # node-media-server，监听 :1935
│   └── node_modules/              # npm 依赖（gitignore）
└── tests/
    ├── conftest.py
    ├── mock_server/               # 假 WSS 服务器（DEBUG_WSS 调试用）
    │   ├── package.json
    │   └── mock_server.js         # 身份识别 + 指令收发 + 交互式 REPL
    ├── test_command_handler.py    # 指令分发器测试
    ├── test_wss_auth.py           # WSS 认证流程测试
    ├── test_wss_client.py         # WSS 客户端测试
    ├── test_wss_integration.py    # WSS 全链路集成测试
    ├── test_device_*.py           # 设备枚举 + 注册表测试
    ├── test_ffmpeg_runner.py      # 推流引擎测试
    └── test_state_machine.py      # 状态机测试
```

### 启动流程

1. 清理残留 ffmpeg 僵尸进程
2. 枚举本机音视频输入设备（缓存供 CommandHandler 使用）
3. RTMP_DEBUG=true → 启动内嵌 RTMP 服务器 + 所有设备入 registry
4. 启动 WSS 客户端 + 注册 CommandHandler（Token 认证 → NodeID 分配 → 指令就绪）
5. 启动流状态机（每 5s 巡检，对比启用表 vs 运行中进程）

### WSS 认证流程

```
Node                                    Server
  |                                        |
  |--- WSS 握手 ------------------------->|
  |--- {"type":"auth","token":"xxx"} ----->|
  |<-- {"type":"auth_ack","node_id":"n1"} -|  认证成功
  |--- {"type":"heartbeat"} -------------->|  每 30s
  |<-- {"command":"get_devices",          |  指令（两种）
  |     "node_id":"n1"} ------------------|
```

### RTMP URL 格式

```
rtmp://{SERVER_BASE_URL}:{RTMP_PORT}/live/{nodeid}_{device_type}_{device_name_slug}
```

示例: `rtmp://192.168.1.100:1935/live/node-abc123_video_integrated-camera`

### 编码器选择

启动时自动运行 `ffmpeg -encoders` 探测可用编码器，结果缓存。优先级：

| 类型 | 优先级 | 说明 |
|---|---|---|
| 视频 | `h264_mf` > `libopenh264` > `libx264` > `mpeg4` | MF 硬件优先 |
| 音频 | `aac` > `libmp3lame` | AAC 优先 |

## 环境准备

前置条件：已安装 **Miniconda** 和 **Node.js**。

### 1. 创建环境

```bash
conda env create -f environment.yml
```

### 2. 激活环境

```bash
conda activate monitor-node
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 安装 Node.js 依赖（开发调试用）

RTMP 服务器和假 WSS 服务器都依赖 Node.js，一键安装：

```bash
cd rtmp_server && npm install && cd ..
cd tests/mock_server && npm install && cd ../..
```

或分开安装：

```bash
# RTMP 服务器（RTMP_DEBUG 模式需要）
cd rtmp_server && npm install && cd ..

# 假 WSS 服务器（DEBUG_WSS 模式需要，程序会自动启动）
cd tests/mock_server && npm install && cd ../..
```

> **提示**：`DEBUG_WSS=true` 时程序会**自动启动**假 WSS 服务器，无需手动开终端。`RTMP_DEBUG=true` 同理。

### 6. 配置

```bash
cp .env.example .env
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `SERVER_BASE_URL` | Server 主机地址（IP 或域名） | `127.0.0.1` |
| `WSS_SCHEME` | Server WebSocket 协议，本地 FastAPI 用 `ws`，TLS/nginx 前置时用 `wss` | `ws` |
| `WSS_PORT` | WSS 连接端口 | `8443` |
| `RTMP_PORT` | RTMP 推流端口 | `1935` |
| `DEBUG_WSS` | WSS 调试模式：固定 Token + 本地 ws:// 连接 | `false` |
| `RTMP_DEBUG` | RTMP 调试模式：启动本地 RTMP 服务器 + 推所有设备 | `false` |
| `SECRET_KEY` | Node 身份 Token（DEBUG_WSS=true 时使用固定值） | — |
| `DEBUG_INFO` | 调试信息开关 | `false` |

### DEBUG_WSS 模式

当 `DEBUG_WSS=true` 时：
- 使用固定 Token `"debug-token-fixed"` 进行身份认证
- 连接 `ws://127.0.0.1:{WSS_PORT}/ws`（非加密 WebSocket）
- 配合假 WSS 服务器 `tests/mock_server/mock_server.js` 使用

### RTMP_DEBUG 模式

当 `RTMP_DEBUG=true` 时：
- 自动启动内嵌 `node-media-server` RTMP 服务器，监听 `rtmp://127.0.0.1:1935/live`
- 所有枚举到的设备自动入 registry 并开始推流
- 控制台打印每个设备的拉流地址

### 7. 启动

```bash
# 本地开发（DEBUG_WSS + RTMP_DEBUG）
python run.py

# 配合假 WSS 服务器调试
# 终端 1: cd tests/mock_server && node mock_server.js
# 终端 2: python run.py
```

服务运行在 `http://localhost:5000`。

## 快速验证

| 端点 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 服务状态 |
| `/health` | GET | 健康检查 |

REST 和本地 WebSocket 端点已移除。所有指令通过 WSS 通道（Node 主动连接 Server）下发的两种命令完成：

| 命令 | 说明 |
|---|---|
| `get_devices` | 获取设备列表 + 健康状态 |
| `update_stream` | 启用/停用指定设备推流 |

```bash
# 健康检查
curl http://localhost:5000/health
```

### 假 WSS 服务器 REPL

```bash
cd tests/mock_server && node mock_server.js

> get_devices                    # 发送 get_devices 指令
> update_stream cam-01 true      # 启用设备推流
> update_stream cam-01 false     # 停用设备推流
> list                           # 列出已连接客户端
> help                           # 帮助
> quit                           # 退出
```

## 运行测试

```bash
pytest tests/ -v
pytest tests/ --cov=. --cov-report=term
```

## 依赖

| 包 | 用途 |
|---|---|
| `fastapi` | Web 框架 |
| `uvicorn[standard]` | ASGI 服务器（含 websockets） |
| `python-dotenv` | `.env` 配置加载 |
| `websockets` | WSS 客户端 + 测试用假服务器 |
| `httpx` | 异步测试客户端 |
| `comtypes` | Windows MF 采集（可选） |
| `pytest` / `pytest-asyncio` / `pytest-cov` | 测试框架 |
| `ffmpeg` (conda) | 系统级 FFmpeg 二进制 |
| `nodejs` (conda) | Node.js 运行时（RTMP 服务器 + 假 WSS 服务器） |
