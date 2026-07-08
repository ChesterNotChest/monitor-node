"""RTMP streaming engine — subprocess lifecycle for ffmpeg capture processes.

Platform-specific command building is delegated to ``services.capture`` drivers.
This module handles process start / stop / query / cleanup.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Optional

from network.api import DeviceItem
from services.capture import get_capture_driver

logger = logging.getLogger(__name__)

_STOP_TIMEOUT = 5  # seconds to wait after terminate()


def _build_rtmp_url(device_id: str) -> str:
    if _is_debug_mode():
        base = "rtmp://127.0.0.1:1935/live"
    else:
        base = os.getenv("SERVER_RTMP_URL", "rtmp://127.0.0.1:1935/live")
    return f"{base.rstrip('/')}/{device_id}"


def _is_debug_mode() -> bool:
    return os.getenv("STREAM_DEBUG", "false").lower() in ("true", "1", "yes")


class FfmpegRunner:
    """Manage ffmpeg subprocesses."""

    def __init__(self) -> None:
        self._processes: dict[str, asyncio.subprocess.Process] = {}

    # ------------------------------------------------------------------
    # Start / Stop
    # ------------------------------------------------------------------

    async def start_stream(self, device: DeviceItem) -> Optional[asyncio.subprocess.Process]:
        """Launch an ffmpeg subprocess to push RTMP for *device*."""
        if device.device_id in self._processes:
            return self._processes[device.device_id]

        rtmp_url = _build_rtmp_url(device.device_id)
        driver = get_capture_driver()
        cmd = driver.capture_command(device, rtmp_url)

        logger.info("Starting: %s → %s", device.device_name, rtmp_url)
        logger.debug("ffmpeg cmd: %s", " ".join(cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.error("ffmpeg binary not found — is it on PATH?")
            return None
        except Exception:
            logger.exception("Failed to spawn ffmpeg for %s", device.device_id)
            return None

        self._processes[device.device_id] = proc

        if _is_debug_mode():
            logger.info(
                "[STREAM_DEBUG] 推流地址: %s  ← OBS → 媒体源 → VLC 源",
                rtmp_url,
            )

        return proc

    async def stop_stream(self, device_id: str) -> bool:
        proc = self._processes.pop(device_id, None)
        if proc is None:
            return False
        try:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=_STOP_TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        except ProcessLookupError:
            pass
        return True

    async def stop_all(self) -> None:
        for did in list(self._processes.keys()):
            await self.stop_stream(did)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_running(self) -> set[str]:
        return set(self._processes.keys())

    def is_running(self, device_id: str) -> bool:
        return device_id in self._processes

    @property
    def running_count(self) -> int:
        return len(self._processes)

    # ------------------------------------------------------------------
    # Zombie cleanup
    # ------------------------------------------------------------------

    @staticmethod
    async def kill_zombies() -> None:
        exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        cmd = ["taskkill", "/F", "/IM", exe] if sys.platform == "win32" else ["pkill", "-9", exe]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
            )
            await proc.communicate()
        except Exception:
            pass


ffmpeg_runner = FfmpegRunner()
