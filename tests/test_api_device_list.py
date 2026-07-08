"""Integration tests for POST /api/device/list."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from network.api import DeviceItem, set_cached_devices


class TestDeviceListEndpoint:
    """Tests for POST /api/device/list."""

    def test_returns_valid_format(self, client: TestClient, monkeypatch):
        """Response must match GetDeviceListOutput structure."""

        async def mock_enumerate():
            return [
                DeviceItem(device_id="cam-01", device_type="video", device_name="Camera"),
                DeviceItem(device_id="mic-01", device_type="audio", device_name="Mic"),
            ]

        monkeypatch.setattr(
            "services.device_enumerator.enumerate_devices",
            mock_enumerate,
        )

        resp = client.post("/api/device/list", json={
            "node_id": "test-node",
        })

        assert resp.status_code == 200
        data = resp.json()
        assert data["node_id"] == "test-node"
        assert "devices" in data
        assert "total_count" in data
        assert data["total_count"] == 2
        assert len(data["devices"]) == 2

    def test_filter_by_device_type(self, client: TestClient, monkeypatch):
        """Response filtered by device_type should only return matching devices."""

        async def mock_enumerate():
            return [
                DeviceItem(device_id="cam-01", device_type="video", device_name="Camera"),
                DeviceItem(device_id="mic-01", device_type="audio", device_name="Mic"),
            ]

        monkeypatch.setattr(
            "services.device_enumerator.enumerate_devices",
            mock_enumerate,
        )

        resp = client.post("/api/device/list", json={
            "node_id": "test-node",
            "device_type": "video",
        })

        data = resp.json()
        assert data["total_count"] == 1
        assert data["devices"][0]["device_id"] == "cam-01"

    def test_empty_devices(self, client: TestClient, monkeypatch):
        """When no devices exist, return empty list."""

        async def mock_enumerate():
            return []

        monkeypatch.setattr(
            "services.device_enumerator.enumerate_devices",
            mock_enumerate,
        )

        resp = client.post("/api/device/list", json={
            "node_id": "test-node",
        })

        data = resp.json()
        assert data["total_count"] == 0
        assert data["devices"] == []

    def test_device_item_fields(self, client: TestClient, monkeypatch):
        """Each device item must have device_id, device_type, device_name, status."""

        async def mock_enumerate():
            return [DeviceItem(
                device_id="cam-01",
                device_type="video",
                device_name="Test Camera",
            )]

        monkeypatch.setattr(
            "services.device_enumerator.enumerate_devices",
            mock_enumerate,
        )

        resp = client.post("/api/device/list", json={"node_id": "n1"})
        device = resp.json()["devices"][0]

        assert "device_id" in device
        assert "device_type" in device
        assert "device_name" in device
        assert "status" in device
