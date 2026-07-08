"""Platform-specific capture drivers.

Factory ``get_capture_driver()`` returns the right driver for the current OS.
"""

from __future__ import annotations

import sys

from services.capture.base import CaptureDriver
from services.capture.ffmpeg_dshow import FfmpegDshowDriver
from services.capture.ffmpeg_avfoundation import FfmpegAvfoundationDriver
from services.capture.ffmpeg_v4l2 import FfmpegV4l2Driver

_DRIVER_MAP = {
    "win32":  FfmpegDshowDriver,
    "darwin": FfmpegAvfoundationDriver,
    "linux":  FfmpegV4l2Driver,
}


def get_capture_driver() -> CaptureDriver:
    """Return the platform-appropriate capture driver."""
    cls = _DRIVER_MAP.get(sys.platform)
    if cls is None:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")
    return cls()


__all__ = ["CaptureDriver", "get_capture_driver"]
