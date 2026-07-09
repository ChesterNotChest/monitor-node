# Server Device Mapping

## Purpose

Node 在 WSS 认证握手后从 Server 获取 `(device_id → device_name)` 映射表，供后续 `UPDATE_STREAM` 命令通过 Server 侧数据库 ID 反查本地物理设备。

## ADDED Requirements

### Requirement: Node receives device mapping in auth response
Server 认证成功响应 SHALL 包含 `videos` 和 `audios` 列表，每项含 `id`（int）和 `name`（str）。Node SHALL 将列表存储为本地映射表。

#### Scenario: Receive populated device lists
- **WHEN** Server 返回 `{"session_token":"sess_xxx","videos":[{"id":1,"name":"Integrated Camera"}],"audios":[{"id":2,"name":"Microphone Array"}]}`
- **THEN** Node 存储 `_server_video_map = {1: "Integrated Camera"}` 和 `_server_audio_map = {2: "Microphone Array"}`

#### Scenario: Receive empty device lists
- **WHEN** Server 返回 `{"session_token":"sess_xxx","videos":[],"audios":[]}`
- **THEN** Node 存储空映射表 `_server_video_map = {}`、`_server_audio_map = {}`

### Requirement: UPDATE_STREAM resolves device via mapping
收到 `UPDATE_STREAM` 命令时，Node SHALL 通过 `device_type` 和 `device_id` 反查映射表获取 `device_name`，再用 `device_name` 匹配本地缓存的 `DeviceItem`。

#### Scenario: Resolve video device by mapping
- **WHEN** 收到 `{"command":"UPDATE_STREAM","device_type":"video","device_id":1,"enable":true}` 且 `_server_video_map[1] = "Integrated Camera"`
- **THEN** Node 在本地设备缓存中查找 `device_name == "Integrated Camera"` 且 `device_type == "video"` 的 `DeviceItem`
- **AND** 将该设备加入 `device_registry`

#### Scenario: Device not in mapping
- **WHEN** 收到 `{"command":"UPDATE_STREAM","device_type":"video","device_id":99,"enable":true}` 且映射表中无 `99`
- **THEN** Node 返回 `{"success":false,"message":"unknown device_id: 99"}`
- **AND** 不修改 `device_registry`

#### Scenario: Device in mapping but not found locally
- **WHEN** 收到 `{"command":"UPDATE_STREAM","device_type":"audio","device_id":2,"enable":true}` 且映射表中 `2 → "Microphone Array"` 但本地缓存中无此设备
- **THEN** Node 创建占位 `DeviceItem(device_type="audio", device_name="Microphone Array")` 并加入 registry
- **AND** 返回 `{"success":true,"message":"推流已启动"}`

### Requirement: Device mapping is cleared on disconnect
WSS 连接断开时，Node SHALL 清除本地设备映射表。

#### Scenario: Mapping cleared on disconnect
- **WHEN** WSS 连接断开
- **THEN** `_server_video_map` 和 `_server_audio_map` 清空为 `{}`
