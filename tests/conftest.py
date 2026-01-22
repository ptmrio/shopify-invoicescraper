"""Pytest configuration and shared fixtures."""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch

# Ensure src is in path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Set required environment variables for tests BEFORE importing config
os.environ.setdefault('STORE_SLUG', 'test-store')

# Mock camoufox before any imports that need it
sys.modules['camoufox'] = MagicMock()
sys.modules['camoufox.async_api'] = MagicMock()


@pytest.fixture(autouse=True)
def reset_scraper_state():
    """Reset scraper state before each test."""
    # Import after mocking
    from src.scraper import reset_cancel, set_session_status
    from src.models import SessionStatus
    
    reset_cancel()
    set_session_status(SessionStatus.UNKNOWN)
    yield


@pytest.fixture
def mock_browser_context():
    """Mock browser context for testing."""
    from unittest.mock import AsyncMock
    
    mock_page = MagicMock()
    mock_page.url = "https://admin.shopify.com/store/test-store/orders"
    mock_page.goto = AsyncMock()
    mock_page.wait_for_load_state = AsyncMock()
    mock_page.locator = MagicMock()
    mock_page.screenshot = AsyncMock()
    
    mock_context = MagicMock()
    mock_context.new_page = MagicMock(return_value=mock_page)
    mock_context.close = MagicMock()
    
    return mock_context, mock_page
