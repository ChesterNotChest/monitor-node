## Context

`MediaFoundationDriver` 是 `CaptureDriver` 的子类，被 `get_capture_driver()` 在 Windows 上优先选择。其 `check_available()` 当前只验证 `comtypes` 是否可导入，不验证 MF 采集逻辑本身是否可实现。

## Goals / Non-Goals

**Goals:**
- MF 驱动在采集循环实现前自动让位给 `FfmpegDshowDriver`
- 全链路"枚举→推流→RTMP 服务器→终端打印 URL"恢复工作

**Non-Goals:**
- 不实现 MF 采集循环（那是另一项工作）
- 不删除 MF 驱动骨架

## Decisions

### 1. `check_available()` 自检

```python
def check_available(self) -> None:
    raise RuntimeError("MF capture loop not yet implemented")
```

工厂 `get_capture_driver()` 已处理此异常——捕获后回退到 `FfmpegDshowDriver`。

### 2. 恢复路径

```
get_capture_driver()
  → MediaFoundationDriver.check_available() → raise
  → except Exception → return FfmpegDshowDriver()
  → 全链路恢复
```

## Risks / Trade-offs

- **[MF 驱动暂时不可用]** → 仅影响 Windows 上想用 MF 采集的用户，不影响 ffmpeg dshow 用户
- **[MF 采集实现后需恢复]** → MF 采集循环写好之后删除 `check_available()` 中的 raise 行
