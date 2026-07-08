"""Device enumeration — delegates platform specifics to capture drivers."""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from typing import Optional

from network.api import DeviceItem
from services.capture import get_capture_driver

logger = logging.getLogger(__name__)

_ENUMERATION_TIMEOUT = 15.0


def _find_ffmpeg() -> Optional[str]:
    path = shutil.which("ffmpeg")
    if path:
        return path
    if sys.platform == "win32":
        for candidate in (
            r"C:\ffmpeg\bin\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        ):
            if os.path.isfile(candidate):
                return candidate
    return None


async def enumerate_devices() -> list[DeviceItem]:
    """Enumerate capture devices using the platform driver."""
    ffmpeg_path = _find_ffmpeg()
    if ffmpeg_path is None:
        logger.error("ffmpeg binary not found — device enumeration disabled")
        return []

    driver = get_capture_driver()
    cmd = [ffmpeg_path] + driver.list_devices_command()[1:]

    logger.info("Enumerating: %s", " ".join(cmd))

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            _, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=_ENUMERATION_TIMEOUT,
            )
        except asyncio.TimeoutError:
            logger.warning("Device enumeration timed out")
            proc.kill()
            _, stderr_bytes = await proc.communicate()
    except FileNotFoundError:
        logger.error("ffmpeg not found at '%s'", ffmpeg_path)
        return []
    except Exception:
        logger.exception("Device enumeration failed")
        return []

    stderr = stderr_bytes.decode("utf-8", errors="replace")
    devices = driver.parse_device_list(stderr)

    if devices:
        logger.info("Found %d device(s): %s", len(devices), [d.device_name for d in devices])
    else:
        logger.warning("No devices parsed (stderr: %s)", stderr[:200].replace("\n", "\\n"))

    return devices
