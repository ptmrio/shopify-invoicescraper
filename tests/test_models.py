"""Tests for Pydantic models."""
import pytest
from datetime import datetime


class TestScrapeResult:
    """Test ScrapeResult model."""

    def test_success_result(self):
        """Test creating a successful scrape result."""
        from src.models import ScrapeResult
        
        result = ScrapeResult(
            success=True,
            order_name="#1234",
            shopify_order_id="12345678901234",
            invoice_number="INV-DE-001",
            invoice_uuid="abc-123-def",
            invoice_url="https://example.com/invoice.pdf",
            invoice_date="2026-01-22",
            filepath="/path/to/invoice.pdf",
        )
        
        assert result.success is True
        assert result.order_name == "#1234"
        assert result.invoice_number == "INV-DE-001"
        assert result.error is None
        assert result.needs_login is False

    def test_failure_result(self):
        """Test creating a failed scrape result."""
        from src.models import ScrapeResult
        
        result = ScrapeResult(
            success=False,
            error="Invoice not found",
        )
        
        assert result.success is False
        assert result.error == "Invoice not found"
        assert result.order_name is None

    def test_needs_login_result(self):
        """Test creating a needs_login result."""
        from src.models import ScrapeResult
        
        result = ScrapeResult(
            success=False,
            needs_login=True,
            error="Session expired",
        )
        
        assert result.success is False
        assert result.needs_login is True


class TestAdminScrapeRequest:
    """Test AdminScrapeRequest model."""

    def test_valid_request(self):
        """Test creating a valid admin scrape request."""
        from src.models import AdminScrapeRequest
        
        request = AdminScrapeRequest(
            order_id="12345678901234",
            order_name="#1234",
            order_date="2026-01-22",
        )
        
        assert request.order_id == "12345678901234"
        assert request.order_name == "#1234"
        assert request.order_date == "2026-01-22"

    def test_minimal_request(self):
        """Test request with only required fields."""
        from src.models import AdminScrapeRequest
        
        request = AdminScrapeRequest(order_id="12345678901234")
        
        assert request.order_id == "12345678901234"
        assert request.order_name is None
        assert request.order_date is None


class TestSessionStatus:
    """Test SessionStatus enum."""

    def test_status_values(self):
        """Test that all expected status values exist."""
        from src.models import SessionStatus
        
        assert SessionStatus.UNKNOWN.value == "unknown"
        assert SessionStatus.LOGGED_IN.value == "logged_in"
        assert SessionStatus.LOGGED_OUT.value == "logged_out"
        assert SessionStatus.LOGIN_REQUIRED.value == "login_required"


class TestSessionStatusResponse:
    """Test SessionStatusResponse model."""

    def test_logged_in_response(self):
        """Test logged in status response."""
        from src.models import SessionStatusResponse, SessionStatus
        
        response = SessionStatusResponse(
            status=SessionStatus.LOGGED_IN,
            store_slug="test-store",
            message="Session is valid",
        )
        
        assert response.status == SessionStatus.LOGGED_IN
        assert response.store_slug == "test-store"

    def test_login_required_response(self):
        """Test login required status response."""
        from src.models import SessionStatusResponse, SessionStatus
        
        response = SessionStatusResponse(
            status=SessionStatus.LOGIN_REQUIRED,
            store_slug="test-store",
            message="Please log in to Shopify admin",
        )
        
        assert response.status == SessionStatus.LOGIN_REQUIRED
        assert response.store_slug == "test-store"


class TestBatchScrapeRequest:
    """Test BatchScrapeRequest model."""

    def test_batch_request(self):
        """Test creating a batch scrape request."""
        from src.models import BatchScrapeRequest, AdminScrapeRequest
        
        request = BatchScrapeRequest(
            orders=[
                AdminScrapeRequest(order_id="111", order_name="#1"),
                AdminScrapeRequest(order_id="222", order_name="#2"),
            ]
        )
        
        assert len(request.orders) == 2
        assert request.orders[0].order_id == "111"


class TestBatchScrapeResult:
    """Test BatchScrapeResult model."""

    def test_batch_result(self):
        """Test creating a batch scrape result."""
        from src.models import BatchScrapeResult, ScrapeResult
        
        result = BatchScrapeResult(
            total=2,
            successful=1,
            failed=1,
            results=[
                ScrapeResult(success=True, order_name="#1"),
                ScrapeResult(success=False, error="Failed"),
            ]
        )
        
        assert result.total == 2
        assert result.successful == 1
        assert result.failed == 1
        assert result.needs_login is False
