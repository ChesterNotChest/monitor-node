## 1. 禁用 MF 驱动自检

- [ ] 1.1 `services/capture/media_foundation.py`：`check_available()` 抛出 `RuntimeError("MF capture loop not yet implemented")`

## 2. 验证全链路

- [ ] 2.1 启动程序，确认日志显示 `Capture driver: ffmpeg dshow (MF unavailable)`
- [ ] 2.2 确认设备枚举返回非零结果
- [ ] 2.3 确认 RTMP 服务器启动并打印 `rtmp://127.0.0.1:1935/live`
- [ ] 2.4 确认终端打印每个设备的拉流地址
- [ ] 2.5 运行 `pytest` 全部通过
