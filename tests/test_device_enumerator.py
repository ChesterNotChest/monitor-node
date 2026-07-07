"""Unit tests for device_enumerator — mock ffmpeg subprocess, cross-platform parsing."""

from __future__ import annotations

import asyncio

import pytest

from network.api import DeviceItem
from services.device_enumerator import (
    _parse_linux,
    _parse_macos,
    _parse_windows,
    DeviceEnumerator,
    enumerate_devices,
)


# ---------------------------------------------------------------------------
# Windows dshow parsing
# ---------------------------------------------------------------------------

WINDOWS_STDERR = """
[dshow @ 000002a1c0b00400] DirectShow video devices (some may be both video and audio devices)
[dshow @ 000002a1c0b00400]  "Integrated Camera" (video)
[dshow @ 000002a1c0b00400]  "USB Video Device" (video)
[dshow @ 000002a1c0b00400] DirectShow audio devices
[dshow @ 000002a1c0b00400]  "Microphone Array" (audio)
[dshow @ 000002a1c0b00400]  "Line In" (audio)
"""


class TestWindowsParsing:
    def test_parses_all_devices(self):
        devices = _parse_windows(WINDOWS_STDERR)
        assert len(devices) == 4

    def test_device_types(self):
        devices = _parse_windows(WINDOWS_STDERR)
        video = [d for d in devices if d.device_type == "video"]
        audio = [d for d in devices if d.device_type == "audio"]
        assert len(video) == 2
        assert len(audio) == 2

    def test_device_names(self):
        devices = _parse_windows(WINDOWS_STDERR)
        names = {d.device_name for d in devices}
        assert "Integrated Camera" in names
        assert "Microphone Array" in names
        assert "USB Video Device" in names


class TestWindowsParsingEmpty:
    def test_empty_stderr(self):
        devices = _parse_windows("")
        assert devices == []

    def test_no_matching_lines(self):
        devices = _parse_windows("some random ffmpeg output")
        assert devices == []


# ---------------------------------------------------------------------------
# macOS avfoundation parsing
# ---------------------------------------------------------------------------

MACOS_STDERR = """
[AVFoundation input device @ 0x7f8e3a80a000] AVFoundation video devices:
[AVFoundation input device @ 0x7f8e3a80a000] [0] FaceTime HD Camera
[AVFoundation input device @ 0x7f8e3a80a000] [1] Capture screen 0
[AVFoundation input device @ 0x7f8e3a80a000] AVFoundation audio devices:
[AVFoundation input device @ 0x7f8e3a80a000] [2] Built-in Microphone
[AVFoundation input device @ 0x7f8e3a80a000] [3] External Microphone
"""


class TestMacOSParsing:
    def test_parses_all_devices(self):
        devices = _parse_macos(MACOS_STDERR)
        assert len(devices) == 4

    def test_camera_detected_as_video(self):
        devices = _parse_macos(MACOS_STDERR)
        camera = [d for d in devices if "FaceTime" in d.device_name]
        assert len(camera) == 1
        assert camera[0].device_type == "video"

    def test_microphone_detected_as_audio(self):
        devices = _parse_macos(MACOS_STDERR)
        mics = [d for d in devices if "Microphone" in d.device_name]
        assert len(mics) == 2
        assert all(m.device_type == "audio" for m in mics)


# ---------------------------------------------------------------------------
# Linux v4l2 parsing
# ---------------------------------------------------------------------------

LINUX_STDERR = """
[video4linux2,v4l2 @ 0x555abc] /dev/video0 : UVC Camera (046d:0825)
[video4linux2,v4l2 @ 0x555abc] /dev/video1 : Dummy video device
"""


class TestLinuxParsing:
    def test_parses_all_devices(self):
        devices = _parse_linux(LINUX_STDERR)
        assert len(devices) == 2

    def test_device_type_is_video(self):
        devices = _parse_linux(LINUX_STDERR)
        assert all(d.device_type == "video" for d in devices)

    def test_device_ids_use_path(self):
        devices = _parse_linux(LINUX_STDERR)
        ids = {d.device_id for d in devices}
        assert "video0" in ids
        assert "video1" in ids


# ---------------------------------------------------------------------------
# DeviceEnumerator (with mocked subprocess)
# ---------------------------------------------------------------------------


class TestEnumeratorWithMock:
    @pytest.mark.asyncio
    async def test_windows_enumeration(self, monkeypatch):
        """Simulate Windows ffmpeg output."""

        async def mock_subprocess(*args, **kwargs):
            return _MockProcess(stderr=WINDOWS_STDERR)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)
        monkeypatch.setattr("sys.platform", "win32")

        devices = await enumerate_devices()
        assert len(devices) == 4
        assert any(d.device_name == "Integrated Camera" for d in devices)

    @pytest.mark.asyncio
    async def test_macos_enumeration(self, monkeypatch):
        async def mock_subprocess(*args, **kwargs):
            return _MockProcess(stderr=MACOS_STDERR)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)
        monkeypatch.setattr("sys.platform", "darwin")

        devices = await enumerate_devices()
        assert len(devices) == 4

    @pytest.mark.asyncio
    async def test_linux_enumeration(self, monkeypatch):
        async def mock_subprocess(*args, **kwargs):
            return _MockProcess(stderr=LINUX_STDERR)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)
        monkeypatch.setattr("sys.platform", "linux")

        devices = await enumerate_devices()
        assert len(devices) == 2

    @pytest.mark.asyncio
    async def test_ffmpeg_not_found(self, monkeypatch):
        async def mock_subprocess(*args, **kwargs):
            raise FileNotFoundError("ffmpeg")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)

        devices = await enumerate_devices()
        assert devices == []

    @pytest.mark.asyncio
    async def test_no_devices(self, monkeypatch):
        async def mock_subprocess(*args, **kwargs):
            return _MockProcess(stderr="No devices found\n")

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)
        monkeypatch.setattr("sys.platform", "win32")

        devices = await enumerate_devices()
        assert devices == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _MockProcess:
    """Minimal mock of asyncio.subprocess.Process."""

    def __init__(self, stderr: str = "", returncode: int = 0):
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return (b"", self._stderr.encode("utf-8"))
