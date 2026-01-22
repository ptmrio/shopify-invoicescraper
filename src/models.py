"""Shopify VAT Invoice Scraper - Pydantic Models"""
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class SessionStatus(str, Enum):
    """Status of the Shopify admin session."""
    UNKNOWN = "unknown"
    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"
    LOGIN_REQUIRED = "login_required"
    CHECKING = "checking"


class AdminScrapeRequest(BaseModel):
    """Request to scrape a single invoice from admin UI."""
    order_id: str = Field(..., description="Shopify order ID (legacyResourceId)")
    order_name: Optional[str] = Field(None, description="Order name for logging (e.g., '#8512')")
    order_date: Optional[str] = Field(None, description="Order date for folder organization (ISO format)")


class ScrapeResult(BaseModel):
    """Result of scraping a single invoice."""
    success: bool
    shopify_order_id: Optional[str] = None
    order_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_uuid: Optional[str] = None
    invoice_url: Optional[str] = None
    invoice_date: Optional[str] = None  # ISO format: YYYY-MM-DD
    filepath: Optional[str] = None
    error: Optional[str] = None
    screenshot_path: Optional[str] = None
    needs_login: bool = False  # True if session expired and login is required


class BatchScrapeRequest(BaseModel):
    """Request to scrape multiple invoices."""
    orders: list[AdminScrapeRequest]


class BatchScrapeResult(BaseModel):
    """Result of scraping multiple invoices."""
    total: int
    successful: int
    failed: int
    results: list[ScrapeResult]
    needs_login: bool = False  # True if batch was interrupted due to login requirement


class SessionStatusResponse(BaseModel):
    """Session status response."""
    status: SessionStatus
    store_slug: str
    message: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str = "2.0.0"
    headless_mode: bool
    download_dir: str
    session_status: SessionStatus = SessionStatus.UNKNOWN
    browser_running: bool = False
