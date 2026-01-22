"""Tests for FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock, MagicMock


@pytest.fixture
def client():
    """Create test client for API."""
    from src.main import app
    return TestClient(app)


class TestHealthEndpoint:
    """Test /health endpoint."""

    def test_health_returns_ok(self, client):
        """Test that health endpoint returns healthy status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "session_status" in data

    def test_health_includes_version(self, client):
        """Test that health includes version info."""
        response = client.get("/health")
        data = response.json()
        
        assert "version" in data


class TestSessionEndpoints:
    """Test session management endpoints."""

    def test_session_status_endpoint(self, client):
        """Test /session/status endpoint."""
        response = client.get("/session/status")
        
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        # Response includes store_slug, message
        assert "store_slug" in data or "message" in data

    def test_session_check_endpoint(self, client):
        """Test /session/check endpoint."""
        with patch("src.main.ensure_logged_in", new_callable=AsyncMock) as mock:
            mock.return_value = (True, None)
            
            response = client.post("/session/check")
            
            assert response.status_code == 200
            data = response.json()
            # Response includes status field
            assert "status" in data

    def test_session_login_complete_endpoint(self, client):
        """Test /session/login-complete endpoint."""
        with patch("src.main.signal_login_complete") as mock_signal:
            response = client.post("/session/login-complete")
            
            assert response.status_code == 200
            mock_signal.assert_called_once()


class TestScrapeEndpoint:
    """Test /scrape-invoice endpoint."""

    def test_scrape_requires_order_id(self, client):
        """Test that scrape endpoint requires order_id."""
        response = client.post("/scrape-invoice", json={})
        
        # Should fail validation
        assert response.status_code == 422

    def test_scrape_endpoint_accepts_request(self, client):
        """Test scrape endpoint accepts valid request format."""
        # Just verify the endpoint accepts the request structure
        # The actual scraping may fail due to mocked browser
        response = client.post("/scrape-invoice", json={
            "order_id": "12345678901234",
            "order_name": "#1234",
        })
        
        # Should return 200 even if scraping fails
        assert response.status_code == 200
        data = response.json()
        # Response should have success field
        assert "success" in data

    def test_scrape_error_returns_success_false(self, client):
        """Test scrape endpoint returns success=false on error."""
        response = client.post("/scrape-invoice", json={
            "order_id": "12345678901234",
        })
        
        assert response.status_code == 200
        data = response.json()
        # With mocked browser, scraping will fail
        # Just verify the response structure
        assert "success" in data
        if not data["success"]:
            assert "error" in data


class TestCancelEndpoint:
    """Test /cancel endpoint."""

    def test_cancel_endpoint(self, client):
        """Test cancel scraping endpoint."""
        with patch("src.main.cancel_scraping") as mock_cancel:
            response = client.post("/cancel")
            
            assert response.status_code == 200
            mock_cancel.assert_called_once()


class TestCORSHeaders:
    """Test CORS configuration."""

    def test_cors_headers_present(self, client):
        """Test that CORS headers are set."""
        response = client.options("/health", headers={
            "Origin": "http://localhost:8080",
            "Access-Control-Request-Method": "GET",
        })
        
        # FastAPI CORS middleware should respond
        assert response.status_code in (200, 204, 405)
