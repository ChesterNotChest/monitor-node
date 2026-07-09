# RTMP Streaming

## Purpose

Manage ffmpeg subprocesses that capture local devices and publish raw audio or
video streams to the RTMP server.

## Requirements

### Requirement: Raw stream names use the shared Server/Node convention

Node SHALL construct raw RTMP stream names with the same normalization rule
used by Server when it builds pull URLs:

```text
stream_name = device_name.replace(" ", "_") + "_" + device_type + "_" + server_device_id
```

`device_type` SHALL be `video` or `audio`. `server_device_id` SHALL be the
Server database id for the selected `VideoDevice` or `AudioDevice`.

#### Scenario: Known Server device id

- **WHEN** the local device name is `Integrated Camera`, `device_type` is `video`, and the Server mapping resolves to id `1`
- **THEN** Node publishes to `rtmp://{SERVER_BASE_URL}:{RTMP_PORT}/live/Integrated_Camera_video_1`

#### Scenario: Unknown Server device id

- **WHEN** Node starts a stream before the Server mapping is available
- **THEN** Node SHALL use `0` as the `server_device_id` placeholder
- **AND** the stream name SHALL still follow the same normalized format

### Requirement: Node maintains Server device mappings after authentication

After WSS authentication succeeds, Node SHALL store the device lists returned by
Server as `server_device_id -> device_name` mappings, split by `device_type`.
The mapping SHALL be used to resolve both incoming `UPDATE_STREAM` commands and
outgoing RTMP stream names.

#### Scenario: WSS authentication returns device mappings

- **WHEN** Server returns `videos: [{id: 1, name: "Integrated Camera"}]` and `audios: [{id: 2, name: "Microphone Array"}]`
- **THEN** Node records `video 1 -> Integrated Camera`
- **AND** Node records `audio 2 -> Microphone Array`

### Requirement: Start ffmpeg RTMP push for a device

When a device is enabled, Node SHALL start one ffmpeg subprocess for that
device and publish the captured raw audio or video to the normalized RTMP URL.

#### Scenario: Start streaming a video device

- **WHEN** the video device `Integrated Camera` is enabled and maps to Server id `1`
- **THEN** Node starts an ffmpeg process whose output URL ends with `/live/Integrated_Camera_video_1`

### Requirement: Stop ffmpeg RTMP push for a device

When a device is removed from the active registry, Node SHALL terminate the
corresponding ffmpeg subprocess.

#### Scenario: Stop an active stream

- **WHEN** a streaming device is disabled
- **THEN** Node terminates the corresponding ffmpeg process and removes it from the running process table
