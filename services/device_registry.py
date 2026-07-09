"""Active device registry — in-memory dict with asyncio.Lock.

Maintains the set of "enabled" devices that should be streaming.
Thread-safe for asyncio concurrent access.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from network.models import DeviceItem


class DeviceRegistry:
    """In-memory registry of enabled devices, concurrency-safe via asyncio.Lock."""

    def __init__(self) -> None:
        self._devices: dict[str, DeviceItem] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    async def add(self, device: DeviceItem) -> bool:
        """Add a device to the registry.

        Returns True if the device was newly added, False if already present.
        """
        async with self._lock:
            if device.device_id in self._devices:
                return False
            self._devices[device.device_id] = device
            return True

    async def remove(self, device_id: str) -> bool:
        """Remove a device by id.

        Returns True if the device was present and removed, False otherwise.
        """
        async with self._lock:
            if device_id not in self._devices:
                return False
            del self._devices[device_id]
            return True

    async def list(self) -> list[DeviceItem]:
        """Return a snapshot of all enabled devices."""
        async with self._lock:
            return list(self._devices.values())

    async def contains(self, device_id: str) -> bool:
        """Check whether a device is enabled."""
        async with self._lock:
            return device_id in self._devices

    async def get(self, device_id: str) -> Optional[DeviceItem]:
        """Get a device by id, or None."""
        async with self._lock:
            return self._devices.get(device_id)

    async def clear(self) -> None:
        """Remove all devices (useful for testing / shutdown)."""
        async with self._lock:
            self._devices.clear()

    async def snapshot(self) -> dict[str, DeviceItem]:
        """Return a copy of the internal dict under lock."""
        async with self._lock:
            return dict(self._devices)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    async def count(self) -> int:
        """Number of enabled devices."""
        async with self._lock:
            return len(self._devices)


# Global singleton
device_registry = DeviceRegistry()
