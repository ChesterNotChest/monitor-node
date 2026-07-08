"""Shared test fixtures for Monitor Node tests."""

from __future__ import annotations

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from app import app


@pytest.fixture
def client() -> TestClient:
    """Synchronous FastAPI TestClient."""
    return TestClient(app)


@pytest_asyncio.fixture
async def async_client() -> AsyncClient:
    """Async HTTP client for testing WebSocket and async endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
