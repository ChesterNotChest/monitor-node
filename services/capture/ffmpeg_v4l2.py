"""Linux V4L2 capture driver (ffmpeg backend)."""

from __future__ import annotations

import re

from network.models import DeviceItem
from services.capture.base import CaptureDriver

_DEVICE_LINE = re.compile(r'\[video4linux2[^\]]*\]\s*(/dev/\S+)\s*:\s*(.+)')


class FfmpegV4l2Driver(CaptureDriver):
    """Linux V4L2 via ffmpeg."""

    def list_devices_command(self) -> list[str]:
        return ["ffmpeg", "-list_devices", "true", "-f", "v4l2", "-i", "dummy"]

    def parse_device_list(self, stderr: str) -> list[DeviceItem]:
        devices: list[DeviceItem] = []
        seen: set[str] = set()
        for m in _DEVICE_LINE.finditer(stderr):
            path = m.group(1)
            name = m.group(2).strip() or path
            device_id = self._unique_id(
                path.replace("/dev/", "").replace("/", "_"), seen,
            )
            seen.add(device_id)
            devices.append(DeviceItem(
                device_id=device_id, device_type="video", device_name=name,
            ))
        return devices

    def capture_command(self, device: DeviceItem, rtmp_url: str) -> list[str]:
        return [
            "ffmpeg",
            "-f", "v4l2",
            "-i", device.device_name,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-f", "flv",
            rtmp_url,
            "-y",
        ]
