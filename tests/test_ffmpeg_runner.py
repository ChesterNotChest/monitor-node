"""Unit tests for ffmpeg_runner — mock asyncio subprocess."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from network.models import DeviceItem
from services.ffmpeg_runner import FfmpegRunner, _build_rtmp_url, _is_debug_mode


@pytest.fixture
def runner():
    """Fresh FfmpegRunner instance."""
    return FfmpegRunner()


@pytest.fixture
def cam_device():
    return DeviceItem(
        device_id="cam-01",
        device_type="video",
        device_name="Integrated Camera",
    )


@pytest.fixture
def audio_device():
    return DeviceItem(
        device_id="mic-01",
        device_type="audio",
        device_name="Microphone Array",
    )


# ---------------------------------------------------------------------------
# RTMP URL construction
# ---------------------------------------------------------------------------


class TestRtmpUrl:
    def test_url_format_with_server_mapping(self, monkeypatch, cam_device):
        """RTMP URL 使用 {device_name}_{device_type}_{device_id} 格式，空格→下划线。"""
        monkeypatch.setenv("RTMP_DEBUG", "false")
        monkeypatch.setenv("SERVER_BASE_URL", "192.168.1.100")
        monkeypatch.setenv("RTMP_PORT", "1935")

        url = _build_rtmp_url(cam_device, server_device_id=1)
        assert url == "rtmp://192.168.1.100:1935/live/Integrated_Camera_video_1"

    def test_url_debug_mode(self, monkeypatch, cam_device):
        """RTMP_DEBUG 时强制 127.0.0.1。"""
        monkeypatch.setenv("RTMP_DEBUG", "true")
        monkeypatch.setenv("RTMP_PORT", "1935")

        url = _build_rtmp_url(cam_device, server_device_id=1)
        assert url.startswith("rtmp://127.0.0.1:1935/live/Integrated_Camera_video_")

    def test_url_audio_device(self, monkeypatch, audio_device):
        """音频设备 URL 包含 audio 类型，空格→下划线。"""
        monkeypatch.setenv("RTMP_DEBUG", "false")
        monkeypatch.setenv("SERVER_BASE_URL", "server.local")
        monkeypatch.setenv("RTMP_PORT", "1935")

        url = _build_rtmp_url(audio_device, server_device_id=2)
        assert "Microphone_Array_audio_2" in url

    def test_url_zero_device_id(self, monkeypatch, cam_device):
        """未映射时使用 device_id=0 占位。"""
        monkeypatch.setenv("RTMP_DEBUG", "false")
        monkeypatch.setenv("SERVER_BASE_URL", "192.168.1.100")
        monkeypatch.setenv("RTMP_PORT", "1935")

        url = _build_rtmp_url(cam_device)
        assert "_video_0" in url


# ---------------------------------------------------------------------------
# Debug mode
# ---------------------------------------------------------------------------


class TestDebugMode:
    def test_debug_off_by_default(self, monkeypatch):
        monkeypatch.delenv("RTMP_DEBUG", raising=False)
        assert _is_debug_mode() is False

    def test_debug_true(self, monkeypatch):
        monkeypatch.setenv("RTMP_DEBUG", "true")
        assert _is_debug_mode() is True

    def test_debug_1(self, monkeypatch):
        monkeypatch.setenv("RTMP_DEBUG", "1")
        assert _is_debug_mode() is True

    def test_debug_false(self, monkeypatch):
        monkeypatch.setenv("RTMP_DEBUG", "false")
        assert _is_debug_mode() is False


# ---------------------------------------------------------------------------
# Start / Stop lifecycle
# ---------------------------------------------------------------------------


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_stream_creates_subprocess(self, runner, cam_device, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setenv("RTMP_DEBUG", "false")
        monkeypatch.setenv("SERVER_BASE_URL", "127.0.0.1")
        monkeypatch.setenv("RTMP_PORT", "1935")

        mock_proc = AsyncMock()
        mock_proc.returncode = None

        with patch.object(asyncio, "create_subprocess_exec", return_value=mock_proc) as mock_exec:
            proc = await runner.start_stream(cam_device)

        mock_exec.assert_called_once()
        assert proc is mock_proc
        assert runner.is_running("cam-01") is True

    @pytest.mark.asyncio
    async def test_stop_stream_terminates(self, runner, cam_device, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")

        mock_proc = AsyncMock()
        mock_proc.returncode = None
        mock_proc.wait = AsyncMock(return_value=0)

        runner._processes["cam-01"] = mock_proc

        result = await runner.stop_stream("cam-01")
        assert result is True
        mock_proc.terminate.assert_called_once()
        assert runner.is_running("cam-01") is False

    @pytest.mark.asyncio
    async def test_stop_nonexistent(self, runner):
        result = await runner.stop_stream("no-such-device")
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_stream_timeout_then_kill(self, runner, cam_device, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")

        mock_proc = MagicMock()
        mock_proc.returncode = None
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock(side_effect=[asyncio.TimeoutError(), None])

        runner._processes["cam-01"] = mock_proc

        with patch("services.ffmpeg_runner._STOP_TIMEOUT", 0.01):
            result = await runner.stop_stream("cam-01")

        assert result is True
        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_all(self, runner, cam_device, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")

        mock1 = AsyncMock()
        mock1.returncode = None
        mock1.wait = AsyncMock(return_value=0)
        mock2 = AsyncMock()
        mock2.returncode = None
        mock2.wait = AsyncMock(return_value=0)

        runner._processes["a"] = mock1
        runner._processes["b"] = mock2

        await runner.stop_all()

        assert runner.running_count == 0
        mock1.terminate.assert_called_once()
        mock2.terminate.assert_called_once()


# ---------------------------------------------------------------------------
# List running
# ---------------------------------------------------------------------------


class TestListRunning:
    def test_empty(self, runner):
        assert runner.list_running() == set()
        assert runner.running_count == 0

    def test_with_processes(self, runner):
        runner._processes["a"] = MagicMock()
        runner._processes["b"] = MagicMock()
        assert runner.list_running() == {"a", "b"}
        assert runner.running_count == 2


# ---------------------------------------------------------------------------
# Zombie cleanup
# ---------------------------------------------------------------------------


class TestZombieCleanup:
    @pytest.mark.asyncio
    async def test_kill_zombies_windows(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "win32")

        with patch.object(asyncio, "create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_proc

            await FfmpegRunner.kill_zombies()

            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert "taskkill" in args
            assert "ffmpeg.exe" in args

    @pytest.mark.asyncio
    async def test_kill_zombies_linux(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "linux")

        with patch.object(asyncio, "create_subprocess_exec") as mock_exec:
            mock_proc = AsyncMock()
            mock_proc.returncode = 0
            mock_proc.communicate = AsyncMock(return_value=(b"", b""))
            mock_exec.return_value = mock_proc

            await FfmpegRunner.kill_zombies()

            args = mock_exec.call_args[0]
            assert "pkill" in args
            assert "ffmpeg" in args
