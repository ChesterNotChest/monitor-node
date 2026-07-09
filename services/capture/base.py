"""Abstract base for platform capture drivers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from network.models import DeviceItem


class CaptureDriver(ABC):
    """Platform-specific ffmpeg capture driver.

    Each driver knows how to:
    - List devices via ffmpeg (or native API)
    - Parse device listing output
    - Build a capture command
    """

    @abstractmethod
    def list_devices_command(self) -> list[str]:
        """The ffmpeg command (as a list) to enumerate input devices."""
        ...

    @abstractmethod
    def capture_command(self, device: DeviceItem, rtmp_url: str) -> list[str]:
        """The ffmpeg command (as a list) to push *device* → *rtmp_url*.

        For pipe-based drivers, return a single command that reads from stdin.
        For direct drivers, return the full ffmpeg capture command.
        """
        ...

    @abstractmethod
    def parse_device_list(self, stderr: str) -> list[DeviceItem]:
        """Parse the stderr output of ``list_devices_command()``."""
        ...

    def check_available(self) -> None:
        """Raise an exception if this driver cannot be used.

        The default implementation always succeeds. Override for drivers
        that depend on optional platform features (e.g. Media Foundation).
        """
        return

    @staticmethod
    def _slugify(name: str) -> str:
        import re
        return re.sub(r"[^a-zA-Z0-9_-]", "_", name).strip("_").lower() or "unknown"

    @staticmethod
    def _unique_id(base: str, seen: set[str]) -> str:
        if base not in seen:
            return base
        i = 1
        while f"{base}-{i}" in seen:
            i += 1
        return f"{base}-{i}"
