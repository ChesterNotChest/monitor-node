"""Tests for device enumeration via capture drivers."""

from __future__ import annotations

import asyncio

import pytest

from services.capture.ffmpeg_avfoundation import FfmpegAvfoundationDriver
from services.capture.ffmpeg_dshow import FfmpegDshowDriver
from services.capture.ffmpeg_v4l2 import FfmpegV4l2Driver
from services.device_enumerator import enumerate_devices

WINDOWS_STDERR = """
[dshow @ 000002a1c0b00400]  "Integrated Camera" (video)
[dshow @ 000002a1c0b00400]  "USB Video Device" (video)
[dshow @ 000002a1c0b00400]  "Microphone Array" (audio)
[dshow @ 000002a1c0b00400]  "Line In" (audio)
"""

WINDOWS_V8_STDERR = """
[in#0 @ 000002BB01A31980] "USB2.0 HD UVC WebCam" (video)
[in#0 @ 000002BB01A31980]   Alternative name "@device_pnp_..."
[in#0 @ 000002BB01A31980] "OBS Virtual Camera" (none)
[in#0 @ 000002BB01A31980] "麦克风阵列 (Realtek(R) Audio)" (audio)
"""

MACOS_STDERR = """
[AVFoundation input device @ 0x7f8e3a80a000] [0] FaceTime HD Camera
[AVFoundation input device @ 0x7f8e3a80a000] [1] Capture screen 0
[AVFoundation input device @ 0x7f8e3a80a000] [2] Built-in Microphone
"""

LINUX_STDERR = """
[video4linux2,v4l2 @ 0x555abc] /dev/video0 : UVC Camera
[video4linux2,v4l2 @ 0x555abc] /dev/video1 : Dummy video device
"""


class TestDshowParsing:
    def setup_method(self):
        self.driver = FfmpegDshowDriver()

    def test_v7_format(self):
        devices = self.driver.parse_device_list(WINDOWS_STDERR)
        assert len(devices) == 4

    def test_v8_format(self):
        devices = self.driver.parse_device_list(WINDOWS_V8_STDERR)
        assert len(devices) == 3

    def test_none_type_preserved(self):
        devices = self.driver.parse_device_list(WINDOWS_V8_STDERR)
        obs = [d for d in devices if d.device_name == "OBS Virtual Camera"]
        assert len(obs) == 1
        assert obs[0].device_type == "none"

    def test_alt_names_skipped(self):
        devices = self.driver.parse_device_list(WINDOWS_V8_STDERR)
        names = {d.device_name for d in devices}
        assert not any("Alternative" in n for n in names)

    def test_empty(self):
        assert self.driver.parse_device_list("") == []

    def test_dshow_command(self):
        cmd = self.driver.capture_command(
            _make_device("cam-01", "video", "Test Camera"),
            "rtmp://server/live/cam-01",
        )
        assert "video=Test Camera" in cmd
        assert "-c:v" in cmd  # video encoder flag present (encoder selected dynamically)
        assert "rtmp://server/live/cam-01" in cmd


class TestAvfoundationParsing:
    def setup_method(self):
        self.driver = FfmpegAvfoundationDriver()

    def test_parses_all(self):
        devices = self.driver.parse_device_list(MACOS_STDERR)
        assert len(devices) == 3

    def test_camera_is_video(self):
        devices = self.driver.parse_device_list(MACOS_STDERR)
        cam = [d for d in devices if "FaceTime" in d.device_name]
        assert cam[0].device_type == "video"


class TestV4l2Parsing:
    def setup_method(self):
        self.driver = FfmpegV4l2Driver()

    def test_parses_all(self):
        devices = self.driver.parse_device_list(LINUX_STDERR)
        assert len(devices) == 2

    def test_all_video(self):
        devices = self.driver.parse_device_list(LINUX_STDERR)
        assert all(d.device_type == "video" for d in devices)


# ---------------------------------------------------------------------------
# Enumerator integration
# ---------------------------------------------------------------------------

class TestEnumeratorWithMock:
    @pytest.mark.asyncio
    async def test_windows_enumeration(self, monkeypatch):
        async def mock_subprocess(*args, **kwargs):
            return _MockProcess(stderr=WINDOWS_STDERR)

        monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_subprocess)
        monkeypatch.setattr("sys.platform", "win32")
        monkeypatch.setattr("services.device_enumerator._find_ffmpeg", lambda: "/fake/ffmpeg")
        # Force ffmpeg dshow driver (MF requires comtypes, which would skip parsing)
        monkeypatch.setattr(
            "services.capture.MediaFoundationDriver.check_available",
            lambda self: (_ for _ in ()).throw(RuntimeError("test")),
        )

        devices = await enumerate_devices()
        assert len(devices) == 4

    @pytest.mark.asyncio
    async def test_ffmpeg_not_found(self, monkeypatch):
        monkeypatch.setattr("services.device_enumerator._find_ffmpeg", lambda: None)
        devices = await enumerate_devices()
        assert devices == []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_device(device_id, device_type, device_name):
    from network.models import DeviceItem
    return DeviceItem(device_id=device_id, device_type=device_type, device_name=device_name)


class _MockProcess:
    def __init__(self, stderr="", returncode=0):
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return (b"", self._stderr.encode("utf-8"))
