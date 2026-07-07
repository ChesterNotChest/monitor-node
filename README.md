# Monitor Node

> 设备监控节点服务 — 通过 FastAPI + WebSocket 向上游 Server 报告设备状态并接收指令。

## 环境准备

前置条件：已安装 **Miniconda**（`conda --version` 能正常输出版本号）。

### 1. 创建环境

```bash
conda env create -f environment.yml
```

### 2. 激活环境

```bash
conda activate monitor-node
```

### 3. 配置

```bash
cp .env.example .env
```

按需修改 `.env` 中的密钥和调试开关。

### 4. 启动

```bash
python run.py
```

服务运行在 `http://localhost:5000`。

## 快速验证

| 端点 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 服务状态 |
| `/health` | GET | 健康检查 |
| `/api/device/list` | POST | 获取设备列表 |
| `/api/device/update` | POST | 更新设备推流状态 |
| `/api/ws` | WebSocket | 实时推送通道 |
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

## 依赖

| 包 | 用途 |
|---|---|
| `fastapi` | Web 框架 |
| `uvicorn` | ASGI 服务器 |
| `ffmpeg-python` | FFmpeg Python 绑定 |
| `python-dotenv` | `.env` 配置加载 |
| `ffmpeg` (conda) | 系统级 FFmpeg 二进制 |

## 更新环境

当 `environment.yml` 有变化时：

```bash
conda env update -f environment.yml
```
