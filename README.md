# Monitor Node

> 设备监控节点服务 — 通过 FastAPI + WebSocket 向上游 Server 报告设备状态并接收指令，通过 ffmpeg 向 Server 推送 RTMP 视频流。

## 架构

```text
monitor-node/
├── app.py                    # FastAPI 应用入口 + 生命周期管理
├── constant.py               # 枚举定义（ServerCommand, DeviceStatus）
├── run.py                    # uvicorn 启动入口
├── network/
│   ├── api.py                # REST + WebSocket 端点
│   ├── wss_client.py         # WSS 客户端（连接远端 Server）
│   └── stream.py             # （遗留）流辅助函数
├── services/
│   ├── device_enumerator.py  # ffmpeg 设备枚举（跨平台）
│   ├── device_registry.py    # 启用设备表（内存 + asyncio 锁）
│   ├── ffmpeg_runner.py      # ffmpeg RTMP 推流子进程管理
│   └── state_machine.py      # 流状态机（定时巡检 + 重试）
└── tests/
    ├── conftest.py
    ├── test_api_*.py         # API 集成测试
    ├── test_device_*.py      # 设备枚举 + 注册表测试
    ├── test_ffmpeg_runner.py # 推流引擎测试
    ├── test_state_machine.py # 状态机测试
    └── test_wss_client.py    # WSS 客户端测试
```

### 启动流程

1. 清理残留 ffmpeg 僵尸进程
2. 枚举本机音视频输入设备（缓存供 API 使用）
3. 启动 WSS 客户端（连接远端 Server）
4. 启动流状态机（每 5s 巡检，对比启用表 vs 运行中进程）

### 关闭流程

1. 停止状态机 → 终止所有 ffmpeg 子进程
2. 断开 WSS 连接

## 环境准备

前置条件：已安装 **Miniconda**（`conda --version` 能正常输出版本号）和系统级 **ffmpeg** 二进制。

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

### 4. 配置

```bash
cp .env.example .env
```

按需修改 `.env` 中的配置项。

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `SERVER_WS_URL` | 远端 Server WSS 地址 | `wss://<server-ip>:8443/ws` |
| `SERVER_RTMP_URL` | RTMP 推流目标基础地址 | `rtmp://<server-ip>:1935/live` |
| `STREAM_DEBUG` | 调试模式：推所有设备到本地 RTMP | `false` |
| `SECRET_KEY` | 应用密钥 | — |
| `DEBUG_INFO` | 调试信息开关 | `false` |

### STREAM_DEBUG 模式

当 `STREAM_DEBUG=true` 时：
- 忽略启用设备表，推流**所有**枚举到的输入设备
- RTMP 目标重定向到 `rtmp://127.0.0.1:1935/live/<device_id>`
- 启动时将所有 RTMP 推流地址输出到控制台日志，可直接复制到 OBS → 媒体源 → VLC 源验证

### 5. 启动

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

# 停用设备推流
curl -X POST http://localhost:5000/api/device/update \
  -H "Content-Type: application/json" \
  -d '{"node_id":"node-01","device_id":"cam-01","enabled":false}'
```

## 运行测试

```bash
# 运行全部测试
pytest tests/ -v

# 含覆盖率报告
pytest tests/ --cov=. --cov-report=term
```

## 依赖

| 包 | 用途 |
|---|---|
| `fastapi` | Web 框架 |
| `uvicorn` | ASGI 服务器 |
| `ffmpeg-python` | FFmpeg Python 绑定 |
| `websockets` | WSS 客户端 |
| `python-dotenv` | `.env` 配置加载 |
| `pytest` / `pytest-asyncio` / `pytest-cov` | 测试框架 |
| `ffmpeg` (系统) | 系统级 FFmpeg 二进制 |

## 更新环境

当 `environment.yml` 有变化时：

```bash
conda env update -f environment.yml
```
