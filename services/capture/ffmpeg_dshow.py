"""Windows DirectShow capture driver (ffmpeg backend)."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass

from network.models import DeviceItem
from services.capture.base import CaptureDriver
from services.capture.encoder_resolver import get_audio_encoder, get_video_encoder

# Matches both ffmpeg 7.x format:  [dshow @ …] "name" (type)
#          and ffmpeg 8.x format:  [in#0 @ …] "name" (type)
_DEVICE_LINE = re.compile(r'\[(?:dshow|in#\d+)[^\]]*\]\s*"([^"]+)"\s*\((\w+)\)')
_VIDEO_OPTION_LINE = re.compile(
    r"(?P<kind>pixel_format|vcodec)=(?P<format>\S+)\s+"
    r"min s=(?P<size>\d+x\d+)\s+fps=(?P<fps>\d+(?:\.\d+)?)"
)

_FALLBACK_VIDEO_SIZE = "640x480"
_FALLBACK_FRAMERATE = "30"
_PREFERRED_SIZES = ("640x480", "848x480", "960x540", "1280x720")
_PREFERRED_FPS = ("20", "15", "25", "10", "30")
_PREFERRED_PIXEL_FORMATS = ("yuyv422", "nv12", "uyvy422", "rgb24")


@dataclass(frozen=True)
class DshowVideoOption:
    size: str
    framerate: str
    pixel_format: str | None = None


class FfmpegDshowDriver(CaptureDriver):
    """Windows DirectShow via ffmpeg."""

    def __init__(self) -> None:
        self._video_options_cache: dict[str, list[DshowVideoOption]] = {}

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

        Selects a mode advertised by the device when dshow exposes options.
        Falls back to 640x480@30 if probing is unavailable.
        """
        option = self._select_video_option(self._device_name_from_input(input_name))
        cmd = [
            "ffmpeg",
            "-fflags", "nobuffer",
            "-rtbufsize", "4M",
            "-f", "dshow",
            "-video_size", option.size,
            "-framerate", option.framerate,
        ]
        if option.pixel_format:
            cmd.extend(["-pixel_format", option.pixel_format])
        cmd.extend([
            "-i", input_name,
            "-vf", "drawtext=text='%{localtime}':fontsize=14:fontcolor=white:x=W-tw-10:y=H-th-10",
            "-c:v", get_video_encoder(),
            "-b:v", "1M",
            "-pix_fmt", "yuv420p",
            "-f", "flv",
            rtmp_url,
            "-y",
        ])
        return cmd

    def _audio_command(self, device: DeviceItem, rtmp_url: str) -> list[str]:
        """Build ffmpeg command for an audio dshow device."""
        return [
            "ffmpeg",
            "-rtbufsize", "8M",
            "-f", "dshow",
            "-i", f"audio={device.device_name}",
            "-c:a", get_audio_encoder(),
            "-b:a", "128k",
            "-f", "flv",
            rtmp_url,
            "-y",
        ]

    def _select_video_option(self, device_name: str) -> DshowVideoOption:
        options = self._list_video_options(device_name)
        if not options:
            return DshowVideoOption(_FALLBACK_VIDEO_SIZE, _FALLBACK_FRAMERATE)

        def score(option: DshowVideoOption) -> tuple[int, int, int, float]:
            size_score = _rank(option.size, _PREFERRED_SIZES)
            fps_score = _rank(option.framerate, _PREFERRED_FPS)
            fmt_score = _rank(option.pixel_format or "", _PREFERRED_PIXEL_FORMATS)
            return (size_score, fps_score, fmt_score, -float(option.framerate))

        return min(options, key=score)

    def _list_video_options(self, device_name: str) -> list[DshowVideoOption]:
        if device_name not in self._video_options_cache:
            self._video_options_cache[device_name] = self._probe_video_options(device_name)
        return self._video_options_cache[device_name]

    def _probe_video_options(self, device_name: str) -> list[DshowVideoOption]:
        try:
            result = subprocess.run(
                [
                    "ffmpeg",
                    "-hide_banner",
                    "-f", "dshow",
                    "-list_options", "true",
                    "-i", f"video={device_name}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        return parse_dshow_video_options(result.stderr or "")

    @staticmethod
    def _device_name_from_input(input_name: str) -> str:
        if input_name.startswith("video="):
            return input_name[len("video="):]
        return input_name


def parse_dshow_video_options(stderr: str) -> list[DshowVideoOption]:
    """Parse ffmpeg dshow video option lines."""
    options: list[DshowVideoOption] = []
    seen: set[tuple[str, str, str | None]] = set()
    for match in _VIDEO_OPTION_LINE.finditer(stderr):
        pixel_format = match.group("format") if match.group("kind") == "pixel_format" else None
        option = DshowVideoOption(
            size=match.group("size"),
            framerate=_normalize_fps(match.group("fps")),
            pixel_format=pixel_format,
        )
        key = (option.size, option.framerate, option.pixel_format)
        if key not in seen:
            options.append(option)
            seen.add(key)
    return options


def _normalize_fps(value: str) -> str:
    fps = float(value)
    if fps.is_integer():
        return str(int(fps))
    return value


def _rank(value: str, preferred: tuple[str, ...]) -> int:
    try:
        return preferred.index(value)
    except ValueError:
        return len(preferred)
