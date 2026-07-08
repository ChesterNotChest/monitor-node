# Monitor Node

> 设备监控节点服务 — 通过 FastAPI + WebSocket 向上游 Server 报告设备状态并接收指令，通过 ffmpeg 向 Server 推送 RTMP 视频流。

## 架构

```text
monitor-node/
├── app.py                         # FastAPI 应用入口 + 生命周期管理
├── constant.py                    # 枚举定义（ServerCommand, DeviceStatus）
├── run.py                         # uvicorn 启动入口
├── network/
│   ├── api.py                     # REST + WebSocket 端点
│   └── wss_client.py              # WSS 客户端（连接远端 Server）
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
├── rtmp_server/                   # STREAM_DEBUG 内嵌 RTMP 服务器
│   ├── package.json
│   ├── index.js                   # node-media-server，监听 :1935
│   └── node_modules/              # npm 依赖（gitignore）
└── tests/
    ├── conftest.py
    ├── test_api_*.py              # API 集成测试
    ├── test_device_*.py           # 设备枚举 + 注册表测试
    ├── test_ffmpeg_runner.py      # 推流引擎测试
    ├── test_state_machine.py      # 状态机测试
    └── test_wss_client.py         # WSS 客户端测试
```

### 启动流程

1. 清理残留 ffmpeg 僵尸进程
2. 枚举本机音视频输入设备（缓存供 API 使用）
3. STREAM_DEBUG=true → 启动内嵌 RTMP 服务器 + 所有设备入 registry
4. 启动 WSS 客户端（连接远端 Server）
5. 启动流状态机（每 5s 巡检，对比启用表 vs 运行中进程）

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

### 4. 安装 RTMP 服务器依赖（开发调试用）

```bash
cd rtmp_server && npm install && cd ..
```

### 5. 配置

```bash
cp .env.example .env
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `SERVER_WS_URL` | 远端 Server WSS 地址 | `wss://<server-ip>:8443/ws` |
| `SERVER_RTMP_URL` | RTMP 推流目标基础地址 | `rtmp://<server-ip>:1935/live` |
| `STREAM_DEBUG` | 调试模式：启动本地 RTMP 服务器 + 推所有设备 | `false` |
| `WSS_ENABLED` | WSS 客户端开关 | `true` |
| `SECRET_KEY` | 应用密钥 | — |
| `DEBUG_INFO` | 调试信息开关 | `false` |

### STREAM_DEBUG 模式

当 `STREAM_DEBUG=true` 时：
- 自动启动内嵌 `node-media-server` RTMP 服务器，监听 `rtmp://127.0.0.1:1935/live`
- 所有枚举到的设备自动入 registry 并开始推流
- 控制台打印每个设备的拉流地址，可直接复制到 OBS → 媒体源 → VLC 源

### 6. 启动

```bash
python run.py
```

服务运行在 `http://localhost:5000`。

## 快速验证

| 端点 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 服务状态 |
| `/health` | GET | 健康检查 |
| `/api/device/list` | POST | 获取设备列表（实时枚举） |
| `/api/device/update` | POST | 启用/停用设备推流 |
| `/api/ws` | WebSocket | Server 指令通道 |
| `/docs` | GET | Swagger UI |

```bash
# 健康检查
curl http://localhost:5000/health

# 获取设备列表
curl -X POST http://localhost:5000/api/device/list \
  -H "Content-Type: application/json" \
  -d '{"node_id":"node-01"}'

# 启用设备推流
curl -X POST http://localhost:5000/api/device/update \
  -H "Content-Type: application/json" \
  -d '{"node_id":"node-01","device_id":"cam-01","enabled":true}'
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
| `websockets` | WSS 客户端 |
| `httpx` | 异步测试客户端 |
| `comtypes` | Windows MF 采集（可选） |
| `pytest` / `pytest-asyncio` / `pytest-cov` | 测试框架 |
| `ffmpeg` (conda) | 系统级 FFmpeg 二进制 |
| `nodejs` (conda) | Node.js 运行时（STREAM_DEBUG RTMP 服务器） |
