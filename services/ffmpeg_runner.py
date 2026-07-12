"""RTMP streaming engine — subprocess lifecycle for ffmpeg capture processes.

Platform-specific command building is delegated to ``services.capture`` drivers.
This module handles process start / stop / query / cleanup.

RTMP URL format: rtmp://{SERVER_BASE_URL}:{RTMP_PORT}/live/{device_name}_{device_type}_{device_id}
（对齐 Server 侧的拉流路径格式）
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from typing import Optional

from network.models import DeviceItem, get_server_device_id
from services.capture import get_capture_driver


def _sanitize_stream_name(name: str) -> str:
    """去除 device name 中的非 ASCII 字符，压缩空白为下划线。

    RTMP URL 中的中文设备名会导致 ffmpeg 拉流阻塞。
    此函数确保 stream key 仅含 ASCII 安全字符。
    """
    name = re.sub(r'[^\x20-\x7E]', '', name)       # 去除非 ASCII
    name = re.sub(r'\s+', '_', name.strip())        # 空白 → _
    name = re.sub(r'[^a-zA-Z0-9_.-]', '_', name)    # 特殊字符 → _
    name = re.sub(r'_+', '_', name)                  # 合并连续下划线
    return name.strip('_')

logger = logging.getLogger(__name__)

_STOP_TIMEOUT = 5  # seconds to wait after terminate()


def _is_debug_mode() -> bool:
    """检查是否启用 RTMP 调试模式。"""
    return os.getenv("RTMP_DEBUG", "false").lower() in ("true", "1", "yes")


def _resolve_rtmp_host() -> str:
    """解析 RTMP 主机地址。

    RTMP_DEBUG=true → 强制 127.0.0.1
    否则           → 从 SERVER_BASE_URL 读取
    """
    if _is_debug_mode():
        return "127.0.0.1"
    return os.getenv("SERVER_BASE_URL", "127.0.0.1")


def _build_rtmp_url(device: DeviceItem, server_device_id: int = 0) -> str:
    """按 Server 协议构造 RTMP 推流地址。

    格式: rtmp://{host}:{port}/live/{device_name}_{device_type}_{device_id}

    - device_name 中的空格替换为下划线，避免 RTMP URL 解析问题
    - device_id 优先从 Server 映射表查，未映射时使用 0 占位
    """
    host = _resolve_rtmp_host()
    port = os.getenv("RTMP_PORT", "1935")
    device_type = device.device_type or "unknown"
    # ASCII sanitize: 去除非 ASCII 字符，确保 RTMP URL 安全
    url_name = _sanitize_stream_name(device.device_name)

    # 优先从 Server 映射表获取 device_id
    if server_device_id == 0:
        mapped_id = get_server_device_id(device_type, device.device_name)
        if mapped_id is not None:
            server_device_id = mapped_id

    if server_device_id == 0:
        logger.warning(
            "RTMP URL 使用 device_id=0（占位）— Server 映射表中未找到设备 %s (%s)",
            device.device_name, device_type,
        )

    return f"rtmp://{host}:{port}/live/{url_name}_{device_type}_{server_device_id}"


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

        rtmp_url = _build_rtmp_url(device)
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
                "[RTMP_DEBUG] 推流地址: %s  ← OBS → 媒体源 → VLC 源",
                rtmp_url,
            )

        return proc

    async def stop_stream(self, device_id: str) -> bool:
        """Terminate the ffmpeg subprocess for *device_id*."""
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
        """Terminate all running ffmpeg subprocesses."""
        for did in list(self._processes.keys()):
            await self.stop_stream(did)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def list_running(self) -> set[str]:
        """Return the set of device_ids currently streaming."""
        return set(self._processes.keys())

    def is_running(self, device_id: str) -> bool:
        """Return True if *device_id* is currently streaming."""
        return device_id in self._processes

    @property
    def running_count(self) -> int:
        """Number of currently running ffmpeg subprocesses."""
        return len(self._processes)

    # ------------------------------------------------------------------
    # Zombie cleanup
    # ------------------------------------------------------------------

    @staticmethod
    async def kill_zombies() -> None:
        """Kill leftover ffmpeg processes from a previous crash."""
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
