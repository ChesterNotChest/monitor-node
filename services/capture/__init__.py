"""Platform-specific capture drivers.

Factory ``get_capture_driver()`` returns the right driver for the current OS.
"""

from __future__ import annotations

import logging
import sys

from services.capture.base import CaptureDriver
from services.capture.ffmpeg_dshow import FfmpegDshowDriver
from services.capture.ffmpeg_avfoundation import FfmpegAvfoundationDriver
from services.capture.ffmpeg_v4l2 import FfmpegV4l2Driver
from services.capture.media_foundation import MediaFoundationDriver

logger = logging.getLogger(__name__)

# non-Windows: always use ffmpeg driver
_DRIVER_MAP = {
    "darwin": FfmpegAvfoundationDriver,
    "linux": FfmpegV4l2Driver,
}


def get_capture_driver() -> CaptureDriver:
    """Return the platform-appropriate capture driver.

    Windows: Media Foundation (preferred) with ffmpeg dshow fallback.
    macOS: ffmpeg avfoundation.
    Linux: ffmpeg v4l2.
    """
    if sys.platform == "win32":
        try:
            driver = MediaFoundationDriver()
            driver.check_available()  # raises if MF is not usable
            logger.info("Capture driver: Media Foundation")
            return driver
        except Exception:
            logger.info("Capture driver: ffmpeg dshow (MF unavailable)")
            return FfmpegDshowDriver()

    cls = _DRIVER_MAP.get(sys.platform)
    if cls is None:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")
    logger.info("Capture driver: %s", cls.__name__)
    return cls()


__all__ = ["CaptureDriver", "get_capture_driver"]
