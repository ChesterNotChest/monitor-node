"""macOS AVFoundation capture driver (ffmpeg backend)."""

from __future__ import annotations

import re

from network.api import DeviceItem
from services.capture.base import CaptureDriver

_DEVICE_LINE = re.compile(r'\[AVFoundation[^\]]*\]\s*\[(\d+)\]\s*(.+)')

_VIDEO_KW = ("camera", "facetime", "cam", "screen")
_AUDIO_KW = ("microphone", "mic", "audio", "sound")


class FfmpegAvfoundationDriver(CaptureDriver):
    """macOS AVFoundation via ffmpeg."""

    def list_devices_command(self) -> list[str]:
        return ["ffmpeg", "-list_devices", "true", "-f", "avfoundation", "-i", "dummy"]

    def parse_device_list(self, stderr: str) -> list[DeviceItem]:
        devices: list[DeviceItem] = []
        seen: set[str] = set()
        for m in _DEVICE_LINE.finditer(stderr):
            idx = m.group(1)
            name = m.group(2).strip()
            low = name.lower()
            if any(k in low for k in _VIDEO_KW):
                dev_type = "video"
            elif any(k in low for k in _AUDIO_KW):
                dev_type = "audio"
            else:
                dev_type = "video"
            device_id = self._unique_id(
                f"{dev_type}-{idx}-{self._slugify(name)}", seen,
            )
            seen.add(device_id)
            devices.append(DeviceItem(
                device_id=device_id, device_type=dev_type, device_name=name,
            ))
        return devices

    def capture_command(self, device: DeviceItem, rtmp_url: str) -> list[str]:
        return [
            "ffmpeg",
            "-f", "avfoundation",
            "-i", device.device_name,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-tune", "zerolatency",
            "-pix_fmt", "yuv420p",
            "-f", "flv",
            rtmp_url,
            "-y",
        ]
