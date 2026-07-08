"""Unit tests for stream state machine — mock registry + mock ffmpeg_runner."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from network.api import DeviceItem
from services.device_registry import DeviceRegistry
from services.ffmpeg_runner import FfmpegRunner
from services.state_machine import StreamStateMachine


@pytest.fixture
async def registry():
    reg = DeviceRegistry()
    yield reg
    await reg.clear()


@pytest.fixture
def runner():
    return FfmpegRunner()


@pytest.fixture
def cam_device():
    return DeviceItem(
        device_id="cam-01",
        device_type="video",
        device_name="Test Camera",
    )


@pytest.fixture
def mic_device():
    return DeviceItem(
        device_id="mic-01",
        device_type="audio",
        device_name="Test Microphone",
    )


# ---------------------------------------------------------------------------
# Diff logic: start / stop
# ---------------------------------------------------------------------------


class TestDiffLogic:
    @pytest.mark.asyncio
    async def test_starts_stream_for_new_device(self, registry, runner, cam_device):
        """When a device is in the registry but not running, it should be started."""
        await registry.add(cam_device)
        sm = StreamStateMachine(registry=registry, runner=runner, poll_interval=0.01)

        with patch.object(runner, "start_stream", new_callable=AsyncMock) as mock_start:
            mock_start.return_value = AsyncMock(returncode=None)
            await sm._tick()

            mock_start.assert_called_once()
            args = mock_start.call_args[0]
            assert args[0].device_id == "cam-01"

    @pytest.mark.asyncio
    async def test_stops_stream_for_removed_device(self, registry, runner, cam_device):
        """When a process is running but the device is not in the registry, stop it."""
        sm = StreamStateMachine(registry=registry, runner=runner, poll_interval=0.01)

        # Simulate: device is running but removed from registry
        mock_proc = MagicMock()
        mock_proc.returncode = None
        runner._processes["cam-01"] = mock_proc

        with patch.object(runner, "stop_stream", new_callable=AsyncMock) as mock_stop:
            mock_stop.return_value = True
            await sm._tick()

            mock_stop.assert_called_once_with("cam-01")

    @pytest.mark.asyncio
    async def test_noop_when_in_sync(self, registry, runner, cam_device):
        """When registry and processes are in sync, nothing happens."""
        await registry.add(cam_device)

        mock_proc = MagicMock()
        mock_proc.returncode = None
        runner._processes["cam-01"] = mock_proc

        sm = StreamStateMachine(registry=registry, runner=runner, poll_interval=0.01)

        with (
            patch.object(runner, "start_stream", new_callable=AsyncMock) as mock_start,
            patch.object(runner, "stop_stream", new_callable=AsyncMock) as mock_stop,
        ):
            await sm._tick()

            mock_start.assert_not_called()
            mock_stop.assert_not_called()


# ---------------------------------------------------------------------------
# Crash detection
# ---------------------------------------------------------------------------


class TestCrashDetection:
    @pytest.mark.asyncio
    async def test_detects_crashed_process(self, registry, runner, cam_device):
        """A process with a non-None returncode is detected as crashed."""
        await registry.add(cam_device)

        # Simulate crashed process
        mock_proc = MagicMock()
        mock_proc.returncode = 1  # exited with error
        runner._processes["cam-01"] = mock_proc

        sm = StreamStateMachine(registry=registry, runner=runner, poll_interval=0.01)

        await sm._tick()

        # After tick, dead process should be removed
        assert "cam-01" not in runner._processes
        # And a failure should be recorded
        assert sm._consecutive_failures["cam-01"] == 1


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------


class TestRetryLimit:
    @pytest.mark.asyncio
    async def test_records_consecutive_failures(self, registry, runner, cam_device):
        sm = StreamStateMachine(registry=registry, runner=runner, max_retries=3)

        for _ in range(3):
            sm._record_failure("cam-01")

        assert sm._consecutive_failures["cam-01"] == 3

    @pytest.mark.asyncio
    async def test_device_marked_dead_after_max_failures(self, registry, runner, cam_device):
        sm = StreamStateMachine(registry=registry, runner=runner, max_retries=3)

        # Simulate 6 consecutive failures (exceeds _MAX_FAILURES=5)
        for _ in range(6):
            sm._record_failure("cam-01")

        assert "cam-01" in sm._dead

    @pytest.mark.asyncio
    async def test_dead_device_not_restarted(self, registry, runner, cam_device):
        await registry.add(cam_device)
        sm = StreamStateMachine(registry=registry, runner=runner, max_retries=3)
        sm._dead.add("cam-01")

        with patch("services.ffmpeg_runner.FfmpegRunner.start_stream", new_callable=AsyncMock) as mock_start:
            await sm._tick()
        mock_start.assert_not_called()


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop(self, registry, runner):
        sm = StreamStateMachine(registry=registry, runner=runner, poll_interval=0.1)
        await sm.start()
        assert sm._running is True
        assert sm._task is not None

        await sm.stop()
        assert sm._running is False

    @pytest.mark.asyncio
    async def test_shutdown_stops_all_streams(self, registry, runner):
        mock_proc_a = MagicMock()
        mock_proc_a.returncode = None
        mock_proc_a.terminate = MagicMock()
        mock_proc_a.kill = MagicMock()
        mock_proc_a.wait = AsyncMock(return_value=0)

        mock_proc_b = MagicMock()
        mock_proc_b.returncode = None
        mock_proc_b.terminate = MagicMock()
        mock_proc_b.kill = MagicMock()
        mock_proc_b.wait = AsyncMock(return_value=0)

        runner._processes["a"] = mock_proc_a
        runner._processes["b"] = mock_proc_b

        sm = StreamStateMachine(registry=registry, runner=runner)
        await sm.start()
        await sm.shutdown()

        assert sm._running is False
        assert runner.running_count == 0
