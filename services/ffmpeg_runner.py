"""RTMP streaming engine — manage ffmpeg subprocess lifecycle.

Uses ``ffmpeg-python`` for command construction and ``asyncio`` subprocess for
non-blocking process management.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from typing import Optional

import ffmpeg  # type: ignore

from network.api import DeviceItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Platform → ffmpeg input format
# ---------------------------------------------------------------------------

_INPUT_FORMAT_MAP = {
    "win32":  "dshow",
    "darwin": "avfoundation",
    "linux":  "v4l2",
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_PRESET = "veryfast"
_DEFAULT_TUNE = "zerolatency"
_STOP_TIMEOUT = 5  # seconds to wait after terminate()


def _get_input_format() -> str:
    fmt = _INPUT_FORMAT_MAP.get(sys.platform)
    if fmt is None:
        raise RuntimeError(f"Unsupported platform for streaming: {sys.platform}")
    return fmt


def _build_rtmp_url(device_id: str) -> str:
    """Build the RTMP push URL for a device."""
    base = os.getenv("SERVER_RTMP_URL", "rtmp://127.0.0.1:1935/live")
    return f"{base.rstrip('/')}/{device_id}"


def _is_debug_mode() -> bool:
    """Check whether STREAM_DEBUG env flag is set."""
    return os.getenv("STREAM_DEBUG", "false").lower() in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class FfmpegRunner:
    """Manage ffmpeg subprocesses for RTMP streaming."""

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    async def start_stream(self, device: DeviceItem) -> Optional[asyncio.subprocess.Process]:
        """Launch an ffmpeg subprocess to push RTMP for *device*.

        Returns the asyncio Process handle, or None on failure.
        """
        if device.device_id in self._processes:
            logger.warning("Stream already running for %s", device.device_id)
            return self._processes[device.device_id]

        rtmp_url = _build_rtmp_url(device.device_id)
        input_format = _get_input_format()

        try:
            stream = (
                ffmpeg
                .input(device.device_name, format=input_format)
                .output(
                    rtmp_url,
                    format="flv",
                    vcodec="libx264",
                    preset=_DEFAULT_PRESET,
                    tune=_DEFAULT_TUNE,
                )
                .overwrite_output()
            )
            # Build the argument list
            args = stream.compile()
        except Exception:
            logger.exception("Failed to compile ffmpeg command for %s", device.device_id)
            return None

        logger.info("Starting ffmpeg for %s → %s", device.device_id, rtmp_url)
        logger.debug("ffmpeg args: %s", " ".join(args))

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except Exception:
            logger.exception("Failed to spawn ffmpeg for %s", device.device_id)
            return None

        self._processes[device.device_id] = proc

        # Log the RTMP URL prominently for STREAM_DEBUG mode
        if _is_debug_mode():
            logger.info(
                "[STREAM_DEBUG] RTMP push: %s  ← copy this into OBS → Media Source → VLC Source",
                rtmp_url,
            )

        return proc

    async def stop_stream(self, device_id: str) -> bool:
        """Stop the ffmpeg process for *device_id*.

        Tries ``terminate()`` first, then ``kill()`` after a 5-second grace period.
        Returns True if a process was stopped, False if no process was found.
        """
        proc = self._processes.pop(device_id, None)
        if proc is None:
            return False

        logger.info("Stopping ffmpeg for %s", device_id)
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=_STOP_TIMEOUT)
            except asyncio.TimeoutError:
                logger.warning("ffmpeg %s did not terminate in %ds, killing", device_id, _STOP_TIMEOUT)
                proc.kill()
                await proc.wait()
        except ProcessLookupError:
            # Already exited
            pass

        return True

    async def stop_all(self) -> None:
        """Stop all running ffmpeg processes (used during shutdown)."""
        device_ids = list(self._processes.keys())
        logger.info("Stopping all ffmpeg processes (%d total)", len(device_ids))
        for device_id in device_ids:
            await self.stop_stream(device_id)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_running(self) -> set[str]:
        """Return the set of device_ids that currently have a running process."""
        return set(self._processes.keys())

    def is_running(self, device_id: str) -> bool:
        """Check if a stream is active for *device_id*."""
        return device_id in self._processes

    @property
    def running_count(self) -> int:
        """Number of currently active ffmpeg subprocesses."""
        return len(self._processes)

    # ------------------------------------------------------------------
    # Zombie cleanup
    # ------------------------------------------------------------------

    @staticmethod
    async def kill_zombies() -> None:
        """Best-effort cleanup of leftover ffmpeg processes on startup."""
        if sys.platform == "win32":
            cmd = ["taskkill", "/F", "/IM", "ffmpeg.exe"]
        else:
            cmd = ["pkill", "-9", "ffmpeg"]

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
        except Exception:
            logger.debug("Zombie cleanup skipped (ffmpeg may not be running)")
        else:
            if proc.returncode == 0:
                logger.info("Cleaned up leftover ffmpeg processes")


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

ffmpeg_runner = FfmpegRunner()
