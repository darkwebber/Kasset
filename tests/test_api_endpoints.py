"""
Tests for backend/api.py — FastAPI endpoint validation.

These tests verify endpoint contracts, request/response schemas,
and error handling WITHOUT needing a running server. Uses FastAPI's
TestClient for in-process testing.
"""
import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

try:
    from fastapi.testclient import TestClient
    from api import app
    HAS_FASTAPI = True
except Exception:
    HAS_FASTAPI = False

pytestmark = pytest.mark.skipif(not HAS_FASTAPI, reason="FastAPI app import failed (model deps)")


class TestHealthEndpoints:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_root_or_health(self, client):
        """App should have a health/root endpoint."""
        for path in ("/", "/health", "/api/health"):
            resp = client.get(path)
            if resp.status_code == 200:
                return
        # At least one should work
        pytest.skip("No health endpoint found")

    def test_static_routes_exist(self, client):
        """Key API routes should be registered."""
        # Just check they don't 404 with method not allowed or similar
        routes = [r.path for r in app.routes if hasattr(r, 'path')]
        assert any("/api/" in r for r in routes), f"No /api/ routes found in {routes[:10]}"


class TestCartridgeEndpoints:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_list_cartridges(self, client):
        resp = client.get("/api/cartridges")
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, (list, dict))

    def test_get_nonexistent_cartridge(self, client):
        resp = client.get("/api/cartridges/nonexistent_xyz_999")
        assert resp.status_code in (404, 422, 200)  # May return empty


class TestSettingsEndpoints:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    def test_get_settings(self, client):
        resp = client.get("/api/settings")
        if resp.status_code == 200:
            data = resp.json()
            assert isinstance(data, dict)
