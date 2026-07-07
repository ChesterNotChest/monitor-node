"""Integration tests for WebSocket /api/ws endpoint — mock-based."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


class TestWebSocketMocked:
    """Test WebSocket endpoint behaviour using mocked dependencies."""

    def test_websocket_endpoint_exists(self, client: TestClient):
        """The /api/ws route should be defined (though TestClient can't test WS natively)."""
        # Just verify the app starts and routes are registered
        resp = client.get("/docs")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_ws_command_routing(self, monkeypatch):
        """Simulate WebSocket message handling logic."""
        from network.api import websocket_endpoint
        from services.device_registry import device_registry

        # Create a mock WebSocket
        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=[
            json.dumps({"command": "get_devices", "node_id": "test-node"}),
            json.dumps({"command": "update_stream", "node_id": "n1", "device_id": "cam-01", "enabled": True}),
            __import__("starlette").websockets.WebSocketDisconnect(),
        ])
        mock_ws.send_json = AsyncMock()

        # Mock cached devices
        monkeypatch.setattr("network.api.get_cached_devices", lambda: [])

        try:
            await websocket_endpoint(mock_ws)
        except Exception:
            pass  # Expected — disconnect will propagate

        # Verify the mock received calls
        mock_ws.accept.assert_called_once()
        assert mock_ws.send_json.call_count >= 2

    @pytest.mark.asyncio
    async def test_ws_unknown_command(self, monkeypatch):
        """Unknown command should return error JSON."""
        from network.api import websocket_endpoint

        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=[
            json.dumps({"command": "bogus_command"}),
            __import__("starlette").websockets.WebSocketDisconnect(),
        ])
        mock_ws.send_json = AsyncMock()

        monkeypatch.setattr("network.api.get_cached_devices", lambda: [])

        try:
            await websocket_endpoint(mock_ws)
        except Exception:
            pass

        # First send_json should be the error for unknown command
        error_call = mock_ws.send_json.call_args_list[0]
        error_data = error_call[0][0]
        assert "error" in error_data

    @pytest.mark.asyncio
    async def test_ws_invalid_json(self, monkeypatch):
        """Invalid JSON should receive an error response."""
        from network.api import websocket_endpoint

        mock_ws = AsyncMock()
        mock_ws.receive_text = AsyncMock(side_effect=[
            "not-valid-json{{{",
            __import__("starlette").websockets.WebSocketDisconnect(),
        ])
        mock_ws.send_json = AsyncMock()

        monkeypatch.setattr("network.api.get_cached_devices", lambda: [])

        try:
            await websocket_endpoint(mock_ws)
        except Exception:
            pass

        error_call = mock_ws.send_json.call_args_list[0]
        error_data = error_call[0][0]
        assert error_data == {"error": "invalid json"}
