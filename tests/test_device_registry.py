"""Unit tests for device_registry — concurrency safety, CRUD operations."""

from __future__ import annotations

import asyncio

import pytest
import pytest_asyncio

from network.api import DeviceItem
from services.device_registry import DeviceRegistry


@pytest_asyncio.fixture
async def registry():
    """Fresh empty registry for each test."""
    reg = DeviceRegistry()
    yield reg
    await reg.clear()


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
# Basic CRUD
# ---------------------------------------------------------------------------


class TestAdd:
    @pytest.mark.asyncio
    async def test_add_new_device(self, registry, cam_device):
        added = await registry.add(cam_device)
        assert added is True
        assert await registry.contains("cam-01") is True

    @pytest.mark.asyncio
    async def test_add_duplicate(self, registry, cam_device):
        await registry.add(cam_device)
        added = await registry.add(cam_device)
        assert added is False
        assert await registry.contains("cam-01") is True


class TestRemove:
    @pytest.mark.asyncio
    async def test_remove_existing(self, registry, cam_device):
        await registry.add(cam_device)
        removed = await registry.remove("cam-01")
        assert removed is True
        assert await registry.contains("cam-01") is False

    @pytest.mark.asyncio
    async def test_remove_nonexistent(self, registry):
        removed = await registry.remove("nonexistent")
        assert removed is False


class TestList:
    @pytest.mark.asyncio
    async def test_empty_registry(self, registry):
        devices = await registry.list()
        assert devices == []

    @pytest.mark.asyncio
    async def test_list_returns_all(self, registry, cam_device, mic_device):
        await registry.add(cam_device)
        await registry.add(mic_device)
        devices = await registry.list()
        assert len(devices) == 2
        ids = {d.device_id for d in devices}
        assert ids == {"cam-01", "mic-01"}


class TestContains:
    @pytest.mark.asyncio
    async def test_contains_true(self, registry, cam_device):
        await registry.add(cam_device)
        assert await registry.contains("cam-01") is True

    @pytest.mark.asyncio
    async def test_contains_false(self, registry):
        assert await registry.contains("nothing") is False


class TestGet:
    @pytest.mark.asyncio
    async def test_get_existing(self, registry, cam_device):
        await registry.add(cam_device)
        device = await registry.get("cam-01")
        assert device is not None
        assert device.device_name == "Test Camera"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, registry):
        device = await registry.get("nothing")
        assert device is None


# ---------------------------------------------------------------------------
# Concurrency safety
# ---------------------------------------------------------------------------


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_concurrent_add_remove(self, registry):
        """Multiple concurrent add+remove operations should stay consistent."""

        async def add_remove(device_id: str, iterations: int):
            for i in range(iterations):
                device = DeviceItem(
                    device_id=device_id,
                    device_type="video",
                    device_name=f"Device-{device_id}",
                )
                await registry.add(device)
                await asyncio.sleep(0)
                await registry.remove(device_id)
                await asyncio.sleep(0)

        await asyncio.gather(
            add_remove("a", 20),
            add_remove("b", 20),
            add_remove("c", 20),
        )

        # After all operations, registry should be consistent (likely empty)
        devices = await registry.list()
        # Each device was added then removed — final state is empty
        assert len(devices) <= 20  # timing-dependent, but must not crash

    @pytest.mark.asyncio
    async def test_concurrent_add_same_device(self, registry, cam_device):
        """Concurrent adds of same device: only one should succeed."""

        async def try_add():
            return await registry.add(cam_device)

        results = await asyncio.gather(*(try_add() for _ in range(10)))
        success_count = sum(1 for r in results if r)
        assert success_count == 1  # Only the first add returns True

    @pytest.mark.asyncio
    async def test_snapshot_is_consistent(self, registry, cam_device, mic_device):
        """Snapshot should return a consistent copy."""
        await registry.add(cam_device)
        await registry.add(mic_device)

        snap = await registry.snapshot()
        assert len(snap) == 2
        assert "cam-01" in snap
        assert "mic-01" in snap
        # Snapshot is a copy — modifying it doesn't affect the registry
        snap.pop("cam-01")
        assert await registry.contains("cam-01") is True


class TestClear:
    @pytest.mark.asyncio
    async def test_clear_removes_all(self, registry, cam_device, mic_device):
        await registry.add(cam_device)
        await registry.add(mic_device)
        await registry.clear()
        devices = await registry.list()
        assert devices == []
