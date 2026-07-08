# Active Device Registry

## Purpose

Maintain an in-memory registry of "enabled" capture devices that should be actively streaming. The Server controls this registry via the REST API.

## Requirements

### Requirement: Maintain in-memory active device registry
Node SHALL 在内存中维护一份"启用中"设备表，结构为 `dict[str, DeviceItem]`，以 `device_id` 为键。

#### Scenario: Registry starts empty
- **WHEN** Node 启动
- **THEN** 启用设备表为空

### Requirement: Add device to registry via API
Server 通过 `POST /api/device/update` 且 `enabled=true` 时，系统 SHALL 将设备加入启用设备表。

#### Scenario: Enable a device
- **WHEN** 收到 `{"node_id": "n1", "device_id": "cam-01", "enabled": true}`
- **THEN** 设备 `cam-01` 出现在启用设备表中

#### Scenario: Enable already-enabled device
- **WHEN** 收到启用请求但设备已在表中
- **THEN** 系统返回 `success: true`，无重复添加

### Requirement: Remove device from registry via API
Server 通过 `POST /api/device/update` 且 `enabled=false` 时，系统 SHALL 将设备从启用设备表中移除。

#### Scenario: Disable a device
- **WHEN** 收到 `{"node_id": "n1", "device_id": "cam-01", "enabled": false}`
- **THEN** 设备 `cam-01` 从启用设备表中移除

#### Scenario: Disable non-enabled device
- **WHEN** 收到停用请求但设备不在表中
- **THEN** 系统返回 `success: true`，无错误

### Requirement: Registry is concurrency-safe
启用设备表的读写操作 SHALL 通过 `asyncio.Lock` 保护，保证协程安全。

#### Scenario: Concurrent add and remove
- **WHEN** 两个请求分别同时启用和停用同一设备
- **THEN** 最终状态一致，无数据竞争或死锁
