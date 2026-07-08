"""Unit tests for stream state machine."""

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
    return DeviceItem(device_id="cam-01", device_type="video", device_name="Test Camera")


class TestDiffLogic:
    @pytest.mark.asyncio
    async def test_starts_stream_for_new_device(self, registry, runner, cam_device):
        await registry.add(cam_device)
        sm = StreamStateMachine(registry=registry, runner=runner, poll_interval=0.01)

        async def mock_start(device):
            proc = AsyncMock(returncode=None)
            runner._processes[device.device_id] = proc
            return proc

        with patch.object(runner, "start_stream", side_effect=mock_start):
            await sm._tick()

        assert "cam-01" in runner._processes
        assert sm._conn_state["cam-01"] == "connected"

    @pytest.mark.asyncio
    async def test_stops_stream_for_removed_device(self, registry, runner, cam_device):
        sm = StreamStateMachine(registry=registry, runner=runner, poll_interval=0.01)
        mock_proc = MagicMock(returncode=None)
        runner._processes["cam-01"] = mock_proc

        with patch.object(runner, "stop_stream", new_callable=AsyncMock) as mock_stop:
            mock_stop.return_value = True
            await sm._tick()

        mock_stop.assert_called_once_with("cam-01")

    @pytest.mark.asyncio
    async def test_noop_when_in_sync(self, registry, runner, cam_device):
        await registry.add(cam_device)
        mock_proc = MagicMock(returncode=None)
        runner._processes["cam-01"] = mock_proc
        sm = StreamStateMachine(registry=registry, runner=runner, poll_interval=0.01)
        sm._conn_state["cam-01"] = "connected"

        with (
            patch.object(runner, "start_stream", new_callable=AsyncMock) as mock_start,
            patch.object(runner, "stop_stream", new_callable=AsyncMock) as mock_stop,
        ):
            await sm._tick()
        mock_start.assert_not_called()
        mock_stop.assert_not_called()


class TestCrashRetry:
    @pytest.mark.asyncio
    async def test_crash_resets_state(self, registry, runner, cam_device):
        """Crash → state resets to None → restarted next tick."""
        await registry.add(cam_device)
        mock_proc = MagicMock(returncode=1)
        runner._processes["cam-01"] = mock_proc
        sm = StreamStateMachine(registry=registry, runner=runner, poll_interval=0.01)
        sm._conn_state["cam-01"] = "connected"

        await sm._tick()
        assert sm._conn_state["cam-01"] is None
        assert "cam-01" not in runner._processes

    @pytest.mark.asyncio
    async def test_always_retries_crashed_device(self, registry, runner, cam_device):
        """Even after many crashes, device keeps being restarted (no dead list)."""
        await registry.add(cam_device)
        sm = StreamStateMachine(registry=registry, runner=runner, poll_interval=0.01)

        for _ in range(10):
            mock_proc = MagicMock(returncode=1)
            runner._processes["cam-01"] = mock_proc
            async def mock_start(device):
                proc = AsyncMock(returncode=1)  # immediately dead
                return proc
            with patch.object(runner, "start_stream", side_effect=mock_start):
                await sm._tick()

        assert sm._conn_state.get("cam-01") is None  # crashed → None, retried next tick


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop(self, registry, runner):
        sm = StreamStateMachine(registry=registry, runner=runner, poll_interval=0.1)
        await sm.start()
        assert sm._running is True
        await sm.stop()
        assert sm._running is False

    @pytest.mark.asyncio
    async def test_shutdown_stops_all(self, registry, runner):
        for did in ("a", "b"):
            p = MagicMock(returncode=None)
            p.terminate = MagicMock()
            p.kill = MagicMock()
            p.wait = AsyncMock(return_value=0)
            runner._processes[did] = p

        sm = StreamStateMachine(registry=registry, runner=runner)
        await sm.start()
        await sm.shutdown()
        assert runner.running_count == 0
