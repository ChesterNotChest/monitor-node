"""Windows Media Foundation capture driver.

Uses Windows Runtime ``Windows.Media.Capture.MediaCapture`` API via ``comtypes``
to enumerate and capture from video/audio devices. ffmpeg receives raw frames
via stdin pipe for encoding + RTMP push.
"""

from __future__ import annotations

import logging

from network.api import DeviceItem
from services.capture.base import CaptureDriver
from services.capture.encoder_resolver import get_video_encoder

logger = logging.getLogger(__name__)


class MediaFoundationDriver(CaptureDriver):
    """Media Foundation capture driver for Windows.

    This driver is checked first on Windows. If ``comtypes`` is not installed
    or MF is otherwise unavailable, ``get_capture_driver()`` falls back to
    ``FfmpegDshowDriver``.
    """

    def check_available(self) -> None:
        """Verify that the MF capture loop is implemented and usable."""
        # MF capture loop (device open, frame read, stdin pipe) is not yet
        # implemented.  Raise unconditionally so the factory falls back to
        # FfmpegDshowDriver, which handles the full pipeline correctly.
        raise RuntimeError("MF capture loop not yet implemented")

    # ------------------------------------------------------------------
    # Device listing
    # ------------------------------------------------------------------

    def list_devices_command(self) -> list[str]:
        # MF driver enumerates natively; return a no-op command
        return ["ffmpeg", "-version"]  # dummy — never executed

    def parse_device_list(self, stderr: str) -> list[DeviceItem]:
        # Parsing is done natively; stderr from the dummy command is ignored
        return []

    # ------------------------------------------------------------------
    # Capture command (pipe mode)
    # ------------------------------------------------------------------

    def capture_command(self, device: DeviceItem, rtmp_url: str) -> list[str]:
        """Build the ffmpeg command that reads raw frames from stdin.

        The MF capture process writes raw BGR24 video frames to stdout,
        which is piped to this ffmpeg process via stdin.
        """
        return [
            "ffmpeg",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", "640x480",
            "-r", "15",
            "-i", "-",               # stdin
            "-c:v", get_video_encoder(),
            "-pix_fmt", "yuv420p",
            "-f", "flv",
            rtmp_url,
            "-y",
        ]
