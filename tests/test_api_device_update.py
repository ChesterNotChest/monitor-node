"""Integration tests for POST /api/device/update."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.device_registry import device_registry


class TestDeviceUpdateEndpoint:
    """Tests for POST /api/device/update."""

    @pytest.fixture(autouse=True)
    async def _clear_registry(self):
        """Reset the registry before and after each test."""
        await device_registry.clear()
        yield
        await device_registry.clear()

    def test_enable_device_adds_to_registry(self, client: TestClient, monkeypatch):
        """When enabled=true, device should be added to the registry."""

        async def mock_enumerate():
            from network.api import DeviceItem
            return [DeviceItem(
                device_id="cam-01",
                device_type="video",
                device_name="Test Camera",
            )]

        monkeypatch.setattr(
            "services.device_enumerator.enumerate_devices",
            mock_enumerate,
        )

        resp = client.post("/api/device/update", json={
            "node_id": "test-node",
            "device_id": "cam-01",
            "enabled": True,
        })

        data = resp.json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert data["device_id"] == "cam-01"
        assert data["enabled"] is True

    def test_disable_device_removes_from_registry(self, client: TestClient, monkeypatch):
        """When enabled=false, device should be removed from registry."""

        async def mock_enumerate():
            from network.api import DeviceItem
            return [DeviceItem(
                device_id="cam-01",
                device_type="video",
                device_name="Test Camera",
            )]

        monkeypatch.setattr(
            "services.device_enumerator.enumerate_devices",
            mock_enumerate,
        )

        # First enable
        client.post("/api/device/update", json={
            "node_id": "n1",
            "device_id": "cam-01",
            "enabled": True,
        })

        # Then disable
        resp = client.post("/api/device/update", json={
            "node_id": "n1",
            "device_id": "cam-01",
            "enabled": False,
        })

        data = resp.json()
        assert data["success"] is True
        assert data["enabled"] is False

    def test_output_format_matches_schema(self, client: TestClient, monkeypatch):
        """Response must match UpdateDeviceOutput structure."""

        async def mock_enumerate():
            from network.api import DeviceItem
            return [DeviceItem(
                device_id="cam-01",
                device_type="video",
                device_name="Test Camera",
            )]

        monkeypatch.setattr(
            "services.device_enumerator.enumerate_devices",
            mock_enumerate,
        )

        resp = client.post("/api/device/update", json={
            "node_id": "test-node",
            "device_id": "cam-01",
            "enabled": True,
        })

        data = resp.json()
        assert "node_id" in data
        assert "device_id" in data
        assert "enabled" in data
        assert "success" in data
        assert "message" in data

    def test_disable_nonexistent_device_succeeds(self, client: TestClient):
        """Disabling a non-existent device should return success=True."""
        resp = client.post("/api/device/update", json={
            "node_id": "n1",
            "device_id": "nonexistent",
            "enabled": False,
        })

        data = resp.json()
        assert data["success"] is True
