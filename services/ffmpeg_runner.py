"""RTMP streaming engine — subprocess lifecycle for ffmpeg capture processes.

Platform-specific command building is delegated to ``services.capture`` drivers.
This module handles process start / stop / query / cleanup.

RTMP URL format: rtmp://{SERVER_BASE_URL}:{RTMP_PORT}/live/{nodeid}_{device_type}_{device_name_slug}
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from typing import Optional

from network.models import DeviceItem
from services.capture import get_capture_driver

logger = logging.getLogger(__name__)

_STOP_TIMEOUT = 5  # seconds to wait after terminate()


def _slugify(name: str) -> str:
    """将设备名称转为 URL-safe slug。

    规则:
      - 空格转连字符
      - 仅保留字母、数字、连字符、下划线
      - 保留中文字符（FFmpeg 支持 UTF-8 URL）
      - 连续连字符合并为一个

    >>> _slugify("Integrated Camera")
    'integrated-camera'
    >>> _slugify("USB2.0 HD UVC WebCam (04f2:b6fb)")
    'usb2-0-hd-uvc-webcam-04f2-b6fb'
    """
    # 转小写
    slug = name.lower()
    # 括号/空格/特殊分隔符 → 连字符
    slug = re.sub(r'[\s()（）\[\]{}:]+', '-', slug)
    # 移除其余非允许字符（保留字母、数字、连字符、下划线、中文）
    slug = re.sub(r'[^\w\-一-鿿]', '', slug)
    # 合并连续连字符
    slug = re.sub(r'-{2,}', '-', slug)
    # 去除首尾连字符
    slug = slug.strip('-')
    return slug or "unknown"


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


def _build_rtmp_url(device: DeviceItem) -> str:
    """按规范格式构造 RTMP 推流地址。

    格式: rtmp://{host}:{port}/live/{nodeid}_{device_type}_{device_name_slug}

    若 node_id 尚未分配（WSS 未认证），使用 "unauthenticated" 占位。
    """
    from network.wss_client import wss_client

    host = _resolve_rtmp_host()
    port = os.getenv("RTMP_PORT", "1935")
    node_id = wss_client.node_id or "unauthenticated"
    device_type = device.device_type or "unknown"
    name_slug = _slugify(device.device_name)

    if node_id == "unauthenticated":
        logger.warning(
            "RTMP URL 使用未认证 NodeID — WSS 认证尚未完成，流可能无法被 Server 识别"
        )

    return f"rtmp://{host}:{port}/live/{node_id}_{device_type}_{name_slug}"


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
