"""Windows DirectShow capture driver (ffmpeg backend)."""

from __future__ import annotations

import re

from network.api import DeviceItem
from services.capture.base import CaptureDriver

# Matches both ffmpeg 7.x format:  [dshow @ …] "name" (type)
#          and ffmpeg 8.x format:  [in#0 @ …] "name" (type)
_DEVICE_LINE = re.compile(r'\[(?:dshow|in#\d+)[^\]]*\]\s*"([^"]+)"\s*\((\w+)\)')


class FfmpegDshowDriver(CaptureDriver):
    """Windows DirectShow via ffmpeg."""

    def list_devices_command(self) -> list[str]:
        return ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"]

    def parse_device_list(self, stderr: str) -> list[DeviceItem]:
        devices: list[DeviceItem] = []
        seen: set[str] = set()
        for m in _DEVICE_LINE.finditer(stderr):
            name = m.group(1)
            dev_type = m.group(2)
            device_id = self._unique_id(
                f"{dev_type}-{self._slugify(name)}", seen,
            )
            seen.add(device_id)
            devices.append(DeviceItem(
                device_id=device_id, device_type=dev_type, device_name=name,
            ))
        return devices

    def capture_command(self, device: DeviceItem, rtmp_url: str) -> list[str]:
        # ffmpeg >= 8.x: video=<name> / audio=<name>
        # type "none" (virtual camera): bare name
        if device.device_type == "audio":
            input_name = f"audio={device.device_name}"
        elif device.device_type == "none":
            input_name = device.device_name
        else:
            input_name = f"video={device.device_name}"

        return [
            "ffmpeg",
            "-rtbufsize", "256M",
            "-f", "dshow",
            "-i", input_name,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-f", "flv",
            rtmp_url,
            "-y",
        ]
