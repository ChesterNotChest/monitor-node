"""Windows DirectShow capture driver (ffmpeg backend)."""

from __future__ import annotations

import re

from network.models import DeviceItem
from services.capture.base import CaptureDriver
from services.capture.encoder_resolver import get_audio_encoder, get_video_encoder

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
            return self._audio_command(device, rtmp_url)
        elif device.device_type == "none":
            return self._video_command(device.device_name, rtmp_url)
        else:
            return self._video_command(
                f"video={device.device_name}", rtmp_url,
            )

    def _video_command(self, input_name: str, rtmp_url: str) -> list[str]:
        """Build ffmpeg command for a video dshow device.

        Forces 640x480@15fps to avoid MJPEG decoder issues with some USB
        cameras on ffmpeg >= 8.x.  At this resolution the camera typically
        falls back to yuyv422 which decodes reliably.
        """
        return [
            "ffmpeg",
            "-rtbufsize", "256M",
            "-f", "dshow",
            "-video_size", "640x480",
            "-framerate", "15",
            "-i", input_name,
            "-c:v", get_video_encoder(),
            "-pix_fmt", "yuv420p",
            "-f", "flv",
            rtmp_url,
            "-y",
        ]

    def _audio_command(self, device: DeviceItem, rtmp_url: str) -> list[str]:
        """Build ffmpeg command for an audio dshow device."""
        return [
            "ffmpeg",
            "-rtbufsize", "256M",
            "-f", "dshow",
            "-i", f"audio={device.device_name}",
            "-c:a", get_audio_encoder(),
            "-b:a", "128k",
            "-f", "flv",
            rtmp_url,
            "-y",
        ]
