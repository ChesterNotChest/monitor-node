"""Stream state machine — periodic reconciliation loop.

Every 5 seconds, compares the active device registry against running ffmpeg
processes and starts/stops streams to converge.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from typing import Optional

from services.device_registry import DeviceRegistry, device_registry
from services.ffmpeg_runner import FfmpegRunner, ffmpeg_runner

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_POLL_INTERVAL = 5          # seconds between reconciliation ticks
_MAX_RETRIES = 3            # max restart attempts per device before giving up
_RETRY_WINDOW = 30          # seconds — sliding window for retry counting
_MAX_FAILURES = 5           # consecutive failures before marking device dead

# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------


class StreamStateMachine:
    """Periodically reconcile enabled devices ↔ running streams."""

    def __init__(
        self,
        registry: Optional[DeviceRegistry] = None,
        runner: Optional[FfmpegRunner] = None,
        poll_interval: float = _POLL_INTERVAL,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self._registry = registry or device_registry
        self._runner = runner or ffmpeg_runner
        self._poll_interval = poll_interval
        self._max_retries = max_retries

        self._task: Optional[asyncio.Task] = None
        self._running = False

        # Retry tracking: device_id → list of failure timestamps
        self._failures: dict[str, list[float]] = {}
        # Consecutive failure counter (separate from sliding-window retries)
        self._consecutive_failures: dict[str, int] = {}
        # Devices that exceeded _MAX_FAILURES and should not be restarted
        self._dead: set[str] = set()

        # Callback for notifying external systems about events
        self._on_alert: Optional[callable] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Begin the reconciliation loop as a background task."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("State machine started (interval=%ss)", self._poll_interval)

    async def stop(self) -> None:
        """Signal the reconciliation loop to stop and wait for it."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("State machine stopped")

    def set_alert_callback(self, cb: callable) -> None:
        """Register an async callback(device_id: str, reason: str) for alerts."""
        self._on_alert = cb

    # ------------------------------------------------------------------
    # Loop
    # ------------------------------------------------------------------

    async def _loop(self) -> None:
        """Main reconciliation loop."""
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("State machine tick failed")
            await asyncio.sleep(self._poll_interval)

    async def _tick(self) -> None:
        """Single reconciliation tick."""
        # 1. Snapshot current state
        enabled_snapshot = await self._registry.snapshot()
        running_set = self._runner.list_running()

        enabled_ids = set(enabled_snapshot.keys())

        # 2. Start streams for new devices (skip dead ones)
        to_start = enabled_ids - running_set - self._dead
        for device_id in to_start:
            device = enabled_snapshot[device_id]
            logger.info("State machine: starting stream for %s", device_id)
            proc = await self._runner.start_stream(device)
            if proc is None:
                self._record_failure(device_id)

        # 3. Stop streams for removed devices
        to_stop = running_set - enabled_ids
        for device_id in to_stop:
            logger.info("State machine: stopping stream for %s", device_id)
            await self._runner.stop_stream(device_id)
            # Clean up failure records for stopped devices
            self._failures.pop(device_id, None)

        # 4. Check for crashed processes (process exited but still enabled)
        for device_id in enabled_ids & running_set:
            proc_handle = self._runner._processes.get(device_id)
            if proc_handle is not None and proc_handle.returncode is not None:
                # Process exited
                self._runner._processes.pop(device_id, None)
                self._record_failure(device_id)
            elif proc_handle is not None and proc_handle.returncode is None:
                # Process is healthy — reset consecutive failure counter
                if device_id in self._consecutive_failures:
                    self._consecutive_failures[device_id] = 0

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------

    def _record_failure(self, device_id: str) -> None:
        """Record a failure. Mark device dead after _MAX_FAILURES consecutive failures."""
        now = asyncio.get_event_loop().time()
        if device_id not in self._failures:
            self._failures[device_id] = []
        self._failures[device_id] = [
            ts for ts in self._failures[device_id]
            if now - ts < _RETRY_WINDOW
        ]
        self._failures[device_id].append(now)

        # Consecutive failure tracking (reset on success via _tick)
        self._consecutive_failures[device_id] = self._consecutive_failures.get(device_id, 0) + 1
        n = self._consecutive_failures[device_id]

        if n > _MAX_FAILURES:
            if device_id not in self._dead:
                self._dead.add(device_id)
                logger.warning(
                    "[%s] 连续失败 %d 次，已停止重试（可能是设备或驱动不兼容）",
                    device_id, _MAX_FAILURES,
                )

    # ------------------------------------------------------------------
    # Cleanup on shutdown
    # ------------------------------------------------------------------

    @staticmethod
    def _install_signal_handlers() -> None:
        """No-op: graceful shutdown is handled via app.py lifecycle events."""

    async def shutdown(self) -> None:
        """Stop the state machine and terminate all ffmpeg processes."""
        await self.stop()
        await self._runner.stop_all()


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

state_machine = StreamStateMachine()
