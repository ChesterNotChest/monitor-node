# WSS Connection

## Purpose

Maintain the persistent WebSocket command channel from Node to Server.

## Requirements

### Requirement: Node connects to Server on startup

Node SHALL connect to the configured Server WebSocket endpoint during startup.
When the connection drops, Node SHALL retry with backoff until the connection is
restored.

#### Scenario: Successful connection

- **WHEN** Node starts and the Server WebSocket endpoint is reachable
- **THEN** Node completes the WebSocket handshake and enters the connected state

#### Scenario: Server unreachable

- **WHEN** Node starts and the Server WebSocket endpoint is unreachable
- **THEN** Node retries the connection instead of exiting permanently

### Requirement: Node authenticates and stores Server device mappings

Node SHALL authenticate on the WSS connection with its token. After Server
accepts the token, Node SHALL store returned device lists as
`server_device_id -> device_name` mappings, split by device type.

`server_device_id` SHALL mean the Server database id for the corresponding
`VideoDevice` or `AudioDevice`. This id is the same value Server later sends as
`device_id` in `UPDATE_STREAM` commands.

#### Scenario: Authentication returns mapped devices

- **WHEN** Server returns `videos: [{id: 1, name: "Integrated Camera"}]`
- **THEN** Node records `video 1 -> Integrated Camera`

#### Scenario: Authentication returns no mapped devices

- **WHEN** Server returns empty `videos` and `audios` lists
- **THEN** Node keeps empty mappings and may publish RTMP streams with `server_device_id` placeholder `0`

### Requirement: Node handles update stream commands by Server device id

Node SHALL treat `device_id` in `UPDATE_STREAM` as a Server database id, not as
a local device id. Node SHALL resolve `device_type + device_id` through the
stored mapping before matching a local physical device name.

#### Scenario: Start stream command resolves a mapped device

- **WHEN** Node receives `{"command":"UPDATE_STREAM","device_type":"video","device_id":1,"enable":true}`
- **AND** the mapping contains `video 1 -> Integrated Camera`
- **THEN** Node enables the local video device named `Integrated Camera`

#### Scenario: Command references an unknown Server device id

- **WHEN** Node receives `UPDATE_STREAM` for a `device_id` absent from the mapping
- **THEN** Node rejects the command with a failure response

### Requirement: Node sends heartbeat

Node SHALL periodically send heartbeat messages over the WSS connection while
connected.

#### Scenario: Heartbeat

- **WHEN** the WSS connection remains connected for the heartbeat interval
- **THEN** Node sends `{"type": "heartbeat"}`
