"""Tests for scraper utility functions."""
import pytest
from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch, MagicMock, AsyncMock


class TestParseGermanDate:
    """Test German date parsing function."""

    def test_standard_format_with_period(self):
        """Test standard German date format with period after month."""
        from src.scraper import parse_german_date
        
        assert parse_german_date("21. Jan. 2026") == "2026-01-21"
        assert parse_german_date("15. Dez. 2025") == "2025-12-15"
        assert parse_german_date("5. Mär. 2026") == "2026-03-05"

    def test_format_without_period(self):
        """Test German date format without period after month."""
        from src.scraper import parse_german_date
        
        assert parse_german_date("1. Mai 2026") == "2026-05-01"
        assert parse_german_date("21. Jan 2026") == "2026-01-21"

    def test_all_german_months(self):
        """Test all German month abbreviations."""
        from src.scraper import parse_german_date
        
        test_cases = [
            ("1. Jan. 2026", "2026-01-01"),
            ("1. Jän. 2026", "2026-01-01"),  # Austrian
            ("1. Feb. 2026", "2026-02-01"),
            ("1. Mär. 2026", "2026-03-01"),
            ("1. Mar. 2026", "2026-03-01"),  # Alternative
            ("1. Apr. 2026", "2026-04-01"),
            ("1. Mai 2026", "2026-05-01"),
            ("1. May 2026", "2026-05-01"),   # English
            ("1. Jun. 2026", "2026-06-01"),
            ("1. Jul. 2026", "2026-07-01"),
            ("1. Aug. 2026", "2026-08-01"),
            ("1. Sep. 2026", "2026-09-01"),
            ("1. Okt. 2026", "2026-10-01"),
            ("1. Oct. 2026", "2026-10-01"),  # English
            ("1. Nov. 2026", "2026-11-01"),
            ("1. Dez. 2026", "2026-12-01"),
            ("1. Dec. 2026", "2026-12-01"),  # English
        ]
        
        for input_date, expected in test_cases:
            assert parse_german_date(input_date) == expected, f"Failed for {input_date}"

    def test_single_digit_day(self):
        """Test single digit day numbers."""
        from src.scraper import parse_german_date
        
        assert parse_german_date("5. Jan. 2026") == "2026-01-05"
        assert parse_german_date("1. Mär 2026") == "2026-03-01"

    def test_double_digit_day(self):
        """Test double digit day numbers."""
        from src.scraper import parse_german_date
        
        assert parse_german_date("15. Jan. 2026") == "2026-01-15"
        assert parse_german_date("31. Dez. 2025") == "2025-12-31"

    def test_invalid_date_returns_none(self):
        """Test that invalid dates return None."""
        from src.scraper import parse_german_date
        
        assert parse_german_date("invalid") is None
        assert parse_german_date("") is None
        assert parse_german_date("2026-01-21") is None  # ISO format not supported
        assert parse_german_date("January 21, 2026") is None  # English format

    def test_case_insensitive(self):
        """Test that month matching is case insensitive."""
        from src.scraper import parse_german_date
        
        assert parse_german_date("21. JAN. 2026") == "2026-01-21"
        assert parse_german_date("21. jan. 2026") == "2026-01-21"
        assert parse_german_date("21. JaN. 2026") == "2026-01-21"

    def test_date_embedded_in_text(self):
        """Test extracting date from longer text."""
        from src.scraper import parse_german_date
        
        text = "Rechnungsdatum: 21. Jan. 2026 - Vielen Dank"
        assert parse_german_date(text) == "2026-01-21"


class TestGetOrderDateFolder:
    """Test order date folder generation."""

    def test_iso_date_string(self):
        """Test with ISO format date string."""
        from src.scraper import get_order_date_folder
        
        # UTC midnight -> Vienna is UTC+1 in winter
        result = get_order_date_folder("2026-01-22T00:00:00+00:00")
        assert result == "2026-01-22"

    def test_utc_z_suffix(self):
        """Test with Z suffix for UTC."""
        from src.scraper import get_order_date_folder
        
        result = get_order_date_folder("2026-01-22T10:30:00Z")
        assert result == "2026-01-22"

    def test_late_utc_stays_same_day_in_utc(self):
        """Test that late UTC times stay same day in UTC (default timezone)."""
        from src.scraper import get_order_date_folder
        
        # With default UTC timezone, 23:30 UTC on Jan 21 stays Jan 21
        result = get_order_date_folder("2026-01-21T23:30:00Z")
        assert result == "2026-01-21"

    def test_none_returns_today(self):
        """Test that None returns today's date."""
        from src.scraper import get_order_date_folder
        from src.config import settings
        
        result = get_order_date_folder(None)
        from src.scraper import _get_timezone
        tz = _get_timezone()
        expected = datetime.now(tz).strftime('%Y-%m-%d')
        assert result == expected

    def test_invalid_date_returns_today(self):
        """Test that invalid date returns today's date."""
        from src.scraper import get_order_date_folder
        
        result = get_order_date_folder("not-a-date")
        tz = ZoneInfo("Europe/Vienna")
        expected = datetime.now(tz).strftime('%Y-%m-%d')
        assert result == expected


class TestCancellationFlags:
    """Test scraping cancellation functions."""

    def test_cancel_and_check(self):
        """Test cancellation flag setting and checking."""
        from src.scraper import cancel_scraping, is_cancelled, reset_cancel
        
        reset_cancel()
        assert is_cancelled() is False
        
        cancel_scraping()
        assert is_cancelled() is True
        
        reset_cancel()
        assert is_cancelled() is False


class TestSessionStatus:
    """Test session status functions."""

    def test_get_and_set_session_status(self):
        """Test session status get/set functions."""
        from src.scraper import get_session_status, set_session_status
        from src.models import SessionStatus
        
        set_session_status(SessionStatus.LOGGED_IN)
        assert get_session_status() == SessionStatus.LOGGED_IN
        
        set_session_status(SessionStatus.LOGGED_OUT)
        assert get_session_status() == SessionStatus.LOGGED_OUT


class TestCheckLoginStatus:
    """Test login status detection."""

    @pytest.mark.asyncio
    async def test_login_page_detected(self):
        """Test detection of login page redirect."""
        from src.scraper import check_login_status
        
        mock_page = MagicMock()
        mock_page.url = "https://accounts.shopify.com/login"
        
        result = await check_login_status(mock_page)
        assert result is False

    @pytest.mark.asyncio
    async def test_oauth_redirect_detected(self):
        """Test detection of OAuth redirect."""
        from src.scraper import check_login_status
        
        mock_page = MagicMock()
        mock_page.url = "https://accounts.shopify.com/oauth/authorize?client_id=..."
        
        result = await check_login_status(mock_page)
        assert result is False

    @pytest.mark.asyncio
    async def test_identity_page_detected(self):
        """Test detection of identity page redirect."""
        from src.scraper import check_login_status
        
        mock_page = MagicMock()
        mock_page.url = "https://identity.shopify.com/..."
        
        result = await check_login_status(mock_page)
        assert result is False


class TestLoginCompleteSignal:
    """Test login complete signaling."""

    def test_signal_login_complete_exists(self):
        """Test that login complete signal function exists."""
        from src.scraper import signal_login_complete
        
        # Just verify the function exists and is callable
        assert callable(signal_login_complete)


class TestHumanDelay:
    """Test human-like delay functionality."""

    @pytest.mark.asyncio
    async def test_human_delay_exists(self):
        """Test that human_delay function exists and is async."""
        from src.scraper import human_delay
        import asyncio
        
        # Should complete without error
        await human_delay("test")

    def test_delay_config_values(self):
        """Test that delay config values are reasonable."""
        from src.config import settings
        
        assert settings.human_delay_min >= 0
        assert settings.human_delay_max > settings.human_delay_min
        assert settings.human_delay_max <= 10  # Sanity check - not too long
