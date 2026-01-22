"""Tests for the config module."""
import os
import pytest
from unittest.mock import patch


class TestSettings:
    """Test Settings configuration class."""

    def test_store_slug_from_env(self):
        """Test that store_slug is loaded from environment."""
        from src.config import settings
        
        # Set by conftest.py
        assert settings.store_slug == "test-store"

    def test_timeout_defaults(self):
        """Test that timeout values are reasonable."""
        from src.config import settings
        
        assert settings.timeout_page_load >= 30000
        assert settings.timeout_selector >= 10000
        assert settings.timeout_login_wait >= 60000

    def test_browser_profile_configured(self):
        """Test that browser profile directory is configured."""
        from src.config import settings
        
        assert settings.profile_dir is not None
        assert len(settings.profile_dir) > 0

    def test_admin_store_url_property(self):
        """Test admin_store_url property generation."""
        from src.config import settings
        
        url = settings.admin_store_url
        assert "admin.shopify.com/store/" in url
        assert settings.store_slug in url

    def test_get_admin_order_url(self):
        """Test order URL generation."""
        from src.config import settings
        
        order_id = "12345678901234"
        url = settings.get_admin_order_url(order_id)
        
        assert order_id in url
        assert settings.store_slug in url
        assert url.endswith(f"/orders/{order_id}")


class TestOutputDirectory:
    """Test output directory configuration."""

    def test_download_dir_configured(self):
        """Test that download directory is configured."""
        from src.config import settings
        
        assert settings.download_dir is not None
        assert len(settings.download_dir) > 0

    def test_screenshot_dir_configured(self):
        """Test screenshot directory is configured."""
        from src.config import settings
        
        assert settings.screenshot_dir is not None

    def test_ensure_directories_creates_folders(self):
        """Test that ensure_directories creates required folders."""
        from src.config import settings
        import tempfile
        import shutil
        
        # Use temp directory for test
        with tempfile.TemporaryDirectory() as tmpdir:
            original_download = settings.download_dir
            settings.download_dir = f"{tmpdir}/downloads"
            
            settings.ensure_directories()
            
            assert os.path.isdir(settings.download_dir)
            
            # Restore
            settings.download_dir = original_download
