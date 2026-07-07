"""Device enumeration via ffmpeg -list_devices.

Cross-platform: Windows (dshow), macOS (avfoundation), Linux (v4l2).
Parses ffmpeg stderr output into ``list[DeviceItem]``.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from typing import Optional

from network.api import DeviceItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform detection
# ---------------------------------------------------------------------------

_PLATFORM_CONFIG = {
    "win32":  {"format": "dshow",       "desc": "Windows"},
    "darwin": {"format": "avfoundation", "desc": "macOS"},
    "linux":  {"format": "v4l2",        "desc": "Linux"},
}


def _get_input_format() -> str:
    """Return the ffmpeg input format string for the current platform."""
    cfg = _PLATFORM_CONFIG.get(sys.platform)
    if cfg is None:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")
    return cfg["format"]


# ---------------------------------------------------------------------------
# ffmpeg stderr parsing
# ---------------------------------------------------------------------------

# Patterns for different platforms' device listing output
# Windows dshow example:
#   [dshow @ 000002...]  "Integrated Camera" (video)
#   [dshow @ 000002...]  "Microphone Array" (audio)
_WIN_LINE_RE = re.compile(
    r'\[dshow[^\]]*\]\s*"([^"]+)"\s*\((video|audio)\)'
)

# macOS avfoundation example:
#   [AVFoundation input device @ 0x...] [0] FaceTime HD Camera
#   [AVFoundation input device @ 0x...] [1] Built-in Microphone
_MAC_LINE_RE = re.compile(
    r'\[AVFoundation[^\]]*\]\s*\[(\d+)\]\s*(.+)'
)

# Linux v4l2 example:
#   [video4linux2,v4l2 @ 0x...] /dev/video0 : UVC Camera
_LINUX_LINE_RE = re.compile(
    r'\[video4linux2[^\]]*\]\s*(/dev/\S+)\s*:\s*(.+)'
)


def _parse_windows(stderr: str) -> list[DeviceItem]:
    """Parse Windows dshow device listing."""
    devices: list[DeviceItem] = []
    seen_ids: set[str] = set()
    for match in _WIN_LINE_RE.finditer(stderr):
        name = match.group(1)
        dev_type = match.group(2)
        device_id = _make_device_id(name, dev_type, seen_ids)
        seen_ids.add(device_id)
        devices.append(
            DeviceItem(
                device_id=device_id,
                device_type=dev_type,
                device_name=name,
            )
        )
    return devices


def _parse_macos(stderr: str) -> list[DeviceItem]:
    """Parse macOS avfoundation device listing."""
    devices: list[DeviceItem] = []
    seen_ids: set[str] = set()
    for match in _MAC_LINE_RE.finditer(stderr):
        index = match.group(1)
        name = match.group(2).strip()
        # Guess type from name heuristics
        lowered = name.lower()
        if any(kw in lowered for kw in ("camera", "facetime", "cam")):
            dev_type = "video"
        elif any(kw in lowered for kw in ("microphone", "mic", "audio", "sound")):
            dev_type = "audio"
        else:
            dev_type = "video"  # default
        device_id = f"{dev_type}-{index}-{_slugify(name)}"
        if device_id in seen_ids:
            device_id = f"{device_id}-{len(seen_ids)}"
        seen_ids.add(device_id)
        devices.append(
            DeviceItem(
                device_id=device_id,
                device_type=dev_type,
                device_name=name,
            )
        )
    return devices


def _parse_linux(stderr: str) -> list[DeviceItem]:
    """Parse Linux v4l2 device listing."""
    devices: list[DeviceItem] = []
    seen_ids: set[str] = set()
    for match in _LINUX_LINE_RE.finditer(stderr):
        path = match.group(1)
        name = match.group(2).strip()
        device_id = path.replace("/dev/", "").replace("/", "_")
        if device_id in seen_ids:
            device_id = f"{device_id}-{len(seen_ids)}"
        seen_ids.add(device_id)
        devices.append(
            DeviceItem(
                device_id=device_id,
                device_type="video",
                device_name=name or path,
            )
        )
    return devices


_PARSERS = {
    "win32":  _parse_windows,
    "darwin": _parse_macos,
    "linux":  _parse_linux,
}


def _slugify(name: str) -> str:
    """Simple slug for device-id generation."""
    return re.sub(r"[^a-zA-Z0-9_-]", "_", name).strip("_").lower() or "unknown"


def _make_device_id(name: str, dev_type: str, seen_ids: set[str]) -> str:
    """Generate a unique device_id from name and type."""
    base = f"{dev_type}-{_slugify(name)}"
    device_id = base
    counter = 1
    while device_id in seen_ids:
        device_id = f"{base}-{counter}"
        counter += 1
    return device_id


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class DeviceEnumerator:
    """Enumerate video/audio input devices via ffmpeg."""

    @staticmethod
    def _build_command() -> list[str]:
        """Build the ffmpeg list-devices command for the current platform."""
        fmt = _get_input_format()
        if sys.platform == "win32":
            return [
                "ffmpeg", "-list_devices", "true",
                "-f", fmt, "-i", "dummy",
            ]
        else:
            return [
                "ffmpeg", "-list_devices", "true",
                "-f", fmt, "-i", "dummy",
            ]

    async def enumerate(self) -> list[DeviceItem]:
        """Run ffmpeg -list_devices and return parsed device list.

        Returns an empty list when no devices are found or ffmpeg is unavailable.
        """
        cmd = self._build_command()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr_bytes = await proc.communicate()
            stderr = stderr_bytes.decode("utf-8", errors="replace")
        except FileNotFoundError:
            logger.warning("ffmpeg binary not found; returning empty device list")
            return []
        except Exception:
            logger.exception("Failed to enumerate devices via ffmpeg")
            return []

        parser = _PARSERS.get(sys.platform)
        if parser is None:
            logger.error("No parser for platform %s", sys.platform)
            return []

        devices = parser(stderr)
        logger.info("Enumerated %d device(s) on %s", len(devices), sys.platform)
        return devices


# Convenience singleton / function
_enumerator: Optional[DeviceEnumerator] = None


def get_device_enumerator() -> DeviceEnumerator:
    """Return a shared DeviceEnumerator instance."""
    global _enumerator
    if _enumerator is None:
        _enumerator = DeviceEnumerator()
    return _enumerator


async def enumerate_devices() -> list[DeviceItem]:
    """Convenience: enumerate all devices."""
    return await get_device_enumerator().enumerate()
