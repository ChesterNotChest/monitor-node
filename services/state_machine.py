"""Stream state machine — periodic reconciliation loop.

Every 5 seconds, compares the active device registry against running ffmpeg
processes and starts/stops streams to converge.

Logging is intentional: one line per device state transition.
Devices that fail are silently retried indefinitely.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from services.device_registry import DeviceRegistry, device_registry
from services.ffmpeg_runner import FfmpegRunner, ffmpeg_runner

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 5  # seconds between reconciliation ticks


class StreamStateMachine:
    """Periodically reconcile enabled devices ↔ running streams."""

    def __init__(
        self,
        registry: Optional[DeviceRegistry] = None,
        runner: Optional[FfmpegRunner] = None,
        poll_interval: float = _POLL_INTERVAL,
    ) -> None:
        self._registry = registry or device_registry
        self._runner = runner or ffmpeg_runner
        self._poll_interval = poll_interval

        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Per-device connection state: None | "connecting" | "connected"
        self._conn_state: dict[str, Optional[str]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def shutdown(self) -> None:
        await self.stop()
        await self._runner.stop_all()

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("State machine tick failed")
            await asyncio.sleep(self._poll_interval)

    async def _tick(self) -> None:
        enabled_snapshot = await self._registry.snapshot()
        running_set = self._runner.list_running()
        enabled_ids = set(enabled_snapshot.keys())

        # 1. Start streams for new devices (infinite retry — no dead set)
        to_start = enabled_ids - running_set
        for device_id in to_start:
            device = enabled_snapshot[device_id]
            prev = self._conn_state.get(device_id)
            if prev != "connecting":
                logger.info("[%s] 正在连接中", device.device_name)
                self._conn_state[device_id] = "connecting"
            await self._runner.start_stream(device)

        # 2. Stop streams for removed devices
        to_stop = running_set - enabled_ids
        for device_id in to_stop:
            await self._runner.stop_stream(device_id)
            self._conn_state.pop(device_id, None)

        # 3. Detect crashed processes
        for device_id in enabled_ids & running_set:
            proc = self._runner._processes.get(device_id)
            if proc is not None and proc.returncode is not None:
                self._runner._processes.pop(device_id, None)
                # Mark as needing reconnection; log on next tick only if
                # it was previously connected (avoids stutter)
                self._conn_state[device_id] = None

        # 4. Mark running devices as connected (state transition only)
        running_set = self._runner.list_running()
        for device_id in enabled_ids & running_set:
            proc = self._runner._processes.get(device_id)
            if proc is not None and proc.returncode is None:
                if self._conn_state.get(device_id) != "connected":
                    device = enabled_snapshot.get(device_id)
                    name = device.device_name if device else device_id
                    logger.info("[%s] 已连接", name)
                    self._conn_state[device_id] = "connected"


state_machine = StreamStateMachine()
