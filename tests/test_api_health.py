"""Integration tests for health-check endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """GET / and GET /health."""

    def test_root_returns_200(self, client: TestClient):
        """GET / should return 200 with service info."""
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["service"] == "monitor-node"
        assert data["status"] == "running"

    def test_health_returns_200(self, client: TestClient):
        """GET /health should return 200 with ok status."""
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"

    def test_docs_not_accessible(self, client: TestClient):
        """GET /docs should return 404 (Swagger UI removed — WSS-only architecture)."""
        resp = client.get("/docs")
        assert resp.status_code == 404
