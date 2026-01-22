"""Shopify VAT Invoice Scraper - Core scraping logic (Async)

This module provides admin UI-based scraping for Shopify VAT invoices.
It uses a persistent browser profile to maintain login sessions.
"""
import re
import os
import asyncio
import logging
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo
from pathlib import Path

from camoufox.async_api import AsyncCamoufox

from .config import settings
from .models import ScrapeResult, SessionStatus

logger = logging.getLogger(__name__)

# Global state
_cancel_requested = False
_browser_instance = None
_browser_context = None
_current_session_status = SessionStatus.UNKNOWN
_login_event = None  # Event to signal login completion


def cancel_scraping():
    """Set the cancellation flag."""
    global _cancel_requested
    _cancel_requested = True


def is_cancelled() -> bool:
    """Check if cancellation was requested."""
    return _cancel_requested


def reset_cancel():
    """Reset the cancellation flag."""
    global _cancel_requested
    _cancel_requested = False


def get_session_status() -> SessionStatus:
    """Get the current session status."""
    return _current_session_status


def set_session_status(status: SessionStatus):
    """Set the session status."""
    global _current_session_status
    _current_session_status = status


def is_browser_running() -> bool:
    """Check if browser instance is currently running."""
    return _browser_context is not None


import random

async def human_delay(action_name: str = "action"):
    """Add a random human-like delay between actions."""
    delay = random.uniform(settings.human_delay_min, settings.human_delay_max)
    logger.debug(f"Human delay before {action_name}: {delay:.2f}s")
    await asyncio.sleep(delay)


# German month mapping for date parsing
GERMAN_MONTHS = {
    'Jan': '01', 'Jän': '01', 'Feb': '02', 'Mär': '03', 'Mar': '03', 'Apr': '04',
    'Mai': '05', 'May': '05', 'Jun': '06', 'Jul': '07', 'Aug': '08',
    'Sep': '09', 'Okt': '10', 'Oct': '10', 'Nov': '11', 'Dez': '12', 'Dec': '12'
}


def parse_german_date(date_str: str) -> Optional[str]:
    """Convert German date format to ISO format."""
    pattern = r'(\d{1,2})\.\s*(Jan|Jän|Feb|Mär|Mar|Apr|Mai|May|Jun|Jul|Aug|Sep|Okt|Oct|Nov|Dez|Dec)\.?\s*(\d{4})'
    match = re.search(pattern, date_str, re.IGNORECASE)
    if match:
        day, month, year = match.groups()
        month_num = GERMAN_MONTHS.get(month.capitalize(), '01')
        return f"{year}-{month_num}-{day.zfill(2)}"
    return None


def _get_timezone():
    """Get timezone, with fallback for Windows systems without tzdata."""
    try:
        return ZoneInfo(settings.timezone)
    except Exception:
        # Fallback: use UTC offset for Europe/Vienna (CET/CEST)
        # This is a simplified fallback - won't handle DST perfectly
        from datetime import timezone, timedelta
        logger.warning(f"ZoneInfo not available for {settings.timezone}, using UTC+1 fallback. Install 'tzdata' package for proper timezone support.")
        return timezone(timedelta(hours=1))


def get_order_date_folder(order_date_str: Optional[str]) -> str:
    """
    Determine the folder date for an order.
    
    Uses the order creation date (in Vienna timezone) to organize files.
    """
    tz = _get_timezone()
    
    if order_date_str:
        try:
            if order_date_str.endswith('Z'):
                order_date_str = order_date_str[:-1] + '+00:00'
            dt = datetime.fromisoformat(order_date_str)
            dt_local = dt.astimezone(tz)
            return dt_local.strftime('%Y-%m-%d')
        except Exception as e:
            logger.warning(f"Could not parse order date '{order_date_str}': {e}")
    
    return datetime.now(tz).strftime('%Y-%m-%d')


async def _save_screenshot(page, prefix: str) -> str:
    """Save debug screenshot and return the filepath."""
    settings.ensure_directories()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{timestamp}.png"
    filepath = os.path.join(settings.screenshot_dir, filename)
    try:
        await page.screenshot(path=filepath, full_page=True)
        logger.info(f"Screenshot saved: {filepath}")
    except Exception as e:
        logger.warning(f"Failed to save screenshot: {e}")
        return ""
    return filepath


async def get_browser_context():
    """
    Get or create a persistent browser context.
    
    Uses a persistent profile directory to maintain login sessions across restarts.
    Spoofs Firefox version to avoid Shopify browser compatibility warnings.
    """
    global _browser_instance, _browser_context
    
    if _browser_context is not None:
        return _browser_context
    
    settings.ensure_directories()
    profile_path = Path(settings.profile_dir).absolute()
    
    logger.info(f"Launching browser with persistent profile at: {profile_path}")
    
    # Spoof Firefox version to avoid Shopify's "Update your browser" warning
    # Camoufox is based on Firefox 135, but Shopify requires 136+
    # We spoof a newer version in the user agent
    spoofed_config = {
        "navigator.userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
    }
    
    # Launch Camoufox with persistent context
    # When persistent_context=True, this returns a BrowserContext directly
    # See: https://github.com/daijro/camoufox/blob/main/pythonlib/camoufox/async_api.py
    _browser_instance = await AsyncCamoufox(
        headless=settings.headless,
        persistent_context=True,
        user_data_dir=str(profile_path),
        humanize=True,  # Humanize cursor movement for more realistic behavior
        config=spoofed_config,
        i_know_what_im_doing=True,  # Suppress warning about manual navigator properties
    ).__aenter__()
    
    # With persistent_context=True, _browser_instance IS the context
    _browser_context = _browser_instance
    
    return _browser_context


async def close_browser():
    """Close the browser instance."""
    global _browser_instance, _browser_context
    
    if _browser_instance is not None:
        try:
            await _browser_instance.__aexit__(None, None, None)
        except Exception as e:
            logger.warning(f"Error closing browser: {e}")
        _browser_instance = None
        _browser_context = None


async def close_all_pages():
    """Close all open pages but keep the browser context alive for session persistence."""
    global _browser_context
    
    if _browser_context is None:
        return
    
    try:
        pages = _browser_context.pages
        for page in pages:
            try:
                await page.close()
            except Exception as e:
                logger.debug(f"Error closing page: {e}")
        logger.debug(f"Closed {len(pages)} browser pages")
    except Exception as e:
        logger.warning(f"Error closing pages: {e}")


async def show_status_page():
    """
    Navigate browser to status page showing it's ready and waiting.
    
    This provides clear visual feedback that the browser is intentionally
    kept open for session persistence, not a bug or oversight.
    """
    global _browser_context
    
    if _browser_context is None:
        return
    
    try:
        pages = _browser_context.pages
        
        # Close all pages except one, reuse the last one for status
        if len(pages) > 1:
            for page in pages[:-1]:
                try:
                    await page.close()
                except Exception:
                    pass
        
        # Get or create a page for status display
        if pages:
            page = pages[-1] if len(pages) > 0 else None
            # Check if page is still usable
            try:
                _ = page.url  # Test if page is accessible
            except Exception:
                page = None
        else:
            page = None
        
        # If no usable page, create one
        if page is None:
            try:
                page = await _browser_context.new_page()
            except Exception as e:
                logger.warning(f"Could not create new page for status: {e}")
                return
        
        # Get the status page path
        status_file = Path(__file__).parent / "static" / "status.html"
        if status_file.exists():
            # Use proper file:// URL format (works on both Windows and Unix)
            file_url = status_file.absolute().as_uri()
            await page.goto(file_url)
            logger.info("Browser showing status page - ready for tasks")
        else:
            # Fallback: simple about:blank with title
            await page.goto("about:blank")
            await page.evaluate("""() => {
                document.title = 'Invoice Scraper - Bereit';
                document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;font-family:sans-serif;background:#1a1a2e;color:#fff;"><div style="text-align:center"><h1>✓ Scraper bereit</h1><p style="color:#888">Warte auf Aufgaben...</p></div></div>';
            }""")
            logger.info("Browser showing fallback status page")
    except Exception as e:
        logger.warning(f"Error showing status page: {e}")


async def check_login_status(page) -> bool:
    """
    Check if we're logged into Shopify admin.
    
    Returns True if logged in, False if login is required.
    """
    current_url = page.url
    
    # Check for login redirect indicators
    login_indicators = [
        "accounts.shopify.com",
        "/login",
        "/auth/login",
        "identity.shopify.com"
    ]
    
    for indicator in login_indicators:
        if indicator in current_url:
            logger.info(f"Login required - detected redirect to: {current_url}")
            return False
    
    # Check for admin UI elements (Polaris components)
    try:
        # Wait briefly for Polaris page structure
        await page.wait_for_selector('[class*="Polaris-Page"], [class*="Polaris-Frame"]', timeout=5000)
        return True
    except Exception:
        # May still be loading or on a non-admin page
        pass
    
    # Additional check: look for specific admin elements
    try:
        html = await page.content()
        if 'Polaris-Page' in html or 'admin.shopify.com/store' in current_url:
            return True
    except Exception:
        pass
    
    return False


async def ensure_logged_in() -> tuple[bool, Optional[str]]:
    """
    Ensure we're logged into Shopify admin.
    
    If not logged in, opens admin page and waits for manual login.
    Returns (success, error_message).
    """
    global _login_event
    
    set_session_status(SessionStatus.CHECKING)
    
    try:
        context = await get_browser_context()
        page = await context.new_page()
        page.set_default_timeout(settings.timeout_page_load)
        
        # Navigate to admin
        logger.info(f"Navigating to: {settings.admin_store_url}")
        await page.goto(settings.admin_store_url, wait_until='domcontentloaded')
        
        # Wait for network to settle
        try:
            await page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass
        
        # Check if logged in
        if await check_login_status(page):
            logger.info("Already logged into Shopify admin")
            set_session_status(SessionStatus.LOGGED_IN)
            await page.close()
            return True, None
        
        # Not logged in - need manual login
        logger.warning("Not logged in - manual login required")
        set_session_status(SessionStatus.LOGIN_REQUIRED)
        
        # Create an event for signaling login completion
        _login_event = asyncio.Event()
        
        # Keep page open and wait for login (with timeout)
        logger.info(f"Waiting up to {settings.timeout_login_wait/1000}s for manual login...")
        
        start_time = asyncio.get_event_loop().time()
        timeout_seconds = settings.timeout_login_wait / 1000
        
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_seconds:
                logger.error("Login timeout - user did not log in within time limit")
                await page.close()
                return False, "Login timeout - please try again"
            
            # Check for cancellation
            if is_cancelled():
                await page.close()
                return False, "Cancelled by user"
            
            # Check if external signal received
            if _login_event and _login_event.is_set():
                break
            
            # Check if now logged in
            current_url = page.url
            if "admin.shopify.com/store" in current_url and "/login" not in current_url:
                # Verify with element check
                if await check_login_status(page):
                    break
            
            await asyncio.sleep(2)  # Check every 2 seconds
        
        logger.info("Login successful!")
        set_session_status(SessionStatus.LOGGED_IN)
        await page.close()
        return True, None
        
    except Exception as e:
        logger.error(f"Error during login check: {e}")
        set_session_status(SessionStatus.UNKNOWN)
        return False, str(e)


def signal_login_complete():
    """Signal that login has been completed (called from external trigger)."""
    global _login_event
    if _login_event:
        _login_event.set()


async def scrape_admin_invoice(
    order_id: str,
    order_name: Optional[str] = None,
    order_date: Optional[str] = None
) -> ScrapeResult:
    """
    Scrape VAT invoice from Shopify admin order page.
    
    Args:
        order_id: Shopify order ID (legacyResourceId)
        order_name: Order name for logging (e.g., '#8512')
        order_date: Order date for folder organization (ISO format)
    
    Returns:
        ScrapeResult with invoice data or error information
    """
    if is_cancelled():
        logger.info("Scraping cancelled before start")
        return ScrapeResult(success=False, error="Cancelled by user")
    
    settings.ensure_directories()
    order_desc = order_name or f"Order {order_id}"
    
    try:
        context = await get_browser_context()
        page = await context.new_page()
        page.set_default_timeout(settings.timeout_page_load)
        
        # Human-like delay before navigation
        await human_delay("navigation")
        
        # Navigate to order page
        order_url = settings.get_admin_order_url(order_id)
        logger.info(f"Navigating to order page: {order_url}")
        
        response = await page.goto(order_url, wait_until='domcontentloaded')
        
        # Wait for page to load
        try:
            await page.wait_for_load_state('networkidle', timeout=15000)
        except Exception:
            pass
        
        # Human-like delay after page load
        await human_delay("page_loaded")
        
        # Check if logged in
        if not await check_login_status(page):
            logger.warning("Session expired - login required")
            await page.close()
            set_session_status(SessionStatus.LOGIN_REQUIRED)
            return ScrapeResult(
                success=False,
                shopify_order_id=order_id,
                order_name=order_name,
                error="Session expired - login required",
                needs_login=True
            )
        
        # Wait for order page content to load
        try:
            await page.wait_for_selector('[class*="Polaris-Page"]', timeout=settings.timeout_selector)
        except Exception:
            screenshot_path = await _save_screenshot(page, f"order_load_failed_{order_id}")
            await page.close()
            return ScrapeResult(
                success=False,
                shopify_order_id=order_id,
                order_name=order_name,
                error="Failed to load order page",
                screenshot_path=screenshot_path
            )
        
        # Look for invoice link in the page
        html = await page.content()
        
        # Extract invoice URL from the page
        # Pattern from admin UI: href="https://admin.shopify.com/store/{slug}/orders/{order_id}/tax_invoices/{uuid}/download/vat_invoice_{invoice_number}.pdf"
        invoice_patterns = [
            # Full admin URL pattern
            r'href="(https://admin\.shopify\.com/store/[^"]+/orders/\d+/tax_invoices/[^"]+/download/[^"]+\.pdf)"',
            # Relative admin URL pattern
            r'href="(/store/[^"]+/orders/\d+/tax_invoices/[^"]+/download/[^"]+\.pdf)"',
            # Any tax_invoices download link
            r'href="([^"]+/tax_invoices/[^"]+/download/[^"]+\.pdf)"',
            # Legacy pattern
            r'href="([^"]+/tax_invoices/[^"]+)"',
        ]
        
        invoice_url = None
        for pattern in invoice_patterns:
            match = re.search(pattern, html)
            if match:
                invoice_url = match.group(1)
                # Make relative URLs absolute
                if invoice_url.startswith('/'):
                    invoice_url = f"{settings.admin_base_url}{invoice_url}"
                logger.info(f"Found invoice URL: {invoice_url[:80]}...")
                break
        
        if not invoice_url:
            # Check if order page loaded but no invoice section exists
            # Support both German ("MwSt.-Rechnungen") and English ("VAT invoices") UI
            has_invoice_section = any(term in html for term in [
                'MwSt.-Rechnungen',  # German
                'VAT invoices',       # English
                'VAT invoice',        # English singular
                'tax_invoices',       # URL pattern (always present if invoice exists)
            ])
            
            if not has_invoice_section:
                screenshot_path = await _save_screenshot(page, f"no_invoice_section_{order_id}")
                await page.close()
                return ScrapeResult(
                    success=False,
                    shopify_order_id=order_id,
                    order_name=order_name,
                    error="No VAT invoice section found - invoice may not be generated yet",
                    screenshot_path=screenshot_path
                )
            
            screenshot_path = await _save_screenshot(page, f"invoice_link_not_found_{order_id}")
            await page.close()
            return ScrapeResult(
                success=False,
                shopify_order_id=order_id,
                order_name=order_name,
                error="Could not find invoice download link on page",
                screenshot_path=screenshot_path
            )
        
        # Extract metadata from URL
        uuid_match = re.search(r'/tax_invoices/([a-f0-9-]+)/', invoice_url)
        inv_num_match = re.search(r'vat_invoice_([A-Z0-9-]+)\.pdf', invoice_url)
        
        invoice_uuid = uuid_match.group(1) if uuid_match else None
        invoice_number = inv_num_match.group(1) if inv_num_match else None
        
        # If invoice number not in URL, try to extract from page
        if not invoice_number:
            inv_text_match = re.search(r'(INV-[A-Z]{2}-\d+)', html)
            if inv_text_match:
                invoice_number = inv_text_match.group(1)
        
        if not invoice_number:
            invoice_number = f"unknown_{order_id}"
        
        logger.info(f"Extracted: invoice_number={invoice_number}, uuid={invoice_uuid}")
        
        # Extract invoice date from page (German format in timeline)
        invoice_date = None
        # Look for date near invoice mention
        date_patterns = [
            r'(\d{1,2})\.\s*(Jän|Jan|Feb|Mär|Mar|Apr|Mai|May|Jun|Jul|Aug|Sep|Okt|Oct|Nov|Dez|Dec)\.?\s*(\d{4})',
        ]
        for pattern in date_patterns:
            date_match = re.search(pattern, html, re.IGNORECASE)
            if date_match:
                day, month, year = date_match.groups()
                month_num = GERMAN_MONTHS.get(month.capitalize(), '01')
                invoice_date = f"{year}-{month_num}-{day.zfill(2)}"
                break
        
        # Determine folder based on order date
        folder_date = get_order_date_folder(order_date)
        date_folder = settings.get_date_folder(folder_date)
        
        # Download PDF
        filename = f"{invoice_number}.pdf"
        filepath = str(date_folder / filename)
        
        logger.info(f"Downloading PDF to: {filepath}")
        
        # Human-like delay before downloading
        await human_delay("download")
        
        # Use response interception - don't rely on page load events for PDFs
        # PDFs are binary data, not pages, so 'load' events are unreliable
        pdf_content = None
        pdf_status = None
        
        async def handle_response(response):
            nonlocal pdf_content, pdf_status
            if invoice_uuid in response.url and response.status == 200:
                content_type = response.headers.get('content-type', '')
                if 'pdf' in content_type or response.url.endswith('.pdf'):
                    try:
                        pdf_content = await response.body()
                        pdf_status = response.status
                    except Exception as e:
                        logger.warning(f"Failed to read response body: {e}")
        
        # Listen for the PDF response
        page.on('response', handle_response)
        
        try:
            # Navigate with 'commit' - fires when response headers received
            # We don't wait for 'load' since PDFs don't have DOM
            await page.goto(invoice_url, wait_until='commit', timeout=settings.timeout_download)
            
            # Give a moment for response body to be captured if not already
            if pdf_content is None:
                await page.wait_for_timeout(2000)
            
        except Exception as e:
            error_msg = str(e)
            # Timeout on 'commit' usually means network issue, not PDF handling
            if 'Timeout' in error_msg:
                logger.warning(f"PDF navigation timeout for {invoice_number}: {error_msg}")
                screenshot_path = await _save_screenshot(page, f"pdf_timeout_{order_id}")
                page.remove_listener('response', handle_response)
                await page.close()
                return ScrapeResult(
                    success=False,
                    shopify_order_id=order_id,
                    order_name=order_name,
                    error=f"PDF download timeout: {error_msg}",
                    screenshot_path=screenshot_path
                )
            else:
                page.remove_listener('response', handle_response)
                raise
        
        page.remove_listener('response', handle_response)
        
        # If interception didn't capture it, try reading from current response
        if pdf_content is None:
            try:
                # Fallback: try to get response directly from page
                response = await page.context.request.get(invoice_url, timeout=settings.timeout_download)
                if response.status == 200:
                    pdf_content = await response.body()
                    pdf_status = response.status
            except Exception as e:
                logger.warning(f"Fallback PDF fetch failed: {e}")
        
        if pdf_content and pdf_status == 200:
            # Verify it's a PDF
            if not pdf_content.startswith(b'%PDF'):
                # Might have hit a redirect or error page
                screenshot_path = await _save_screenshot(page, f"pdf_invalid_{order_id}")
                await page.close()
                return ScrapeResult(
                    success=False,
                    shopify_order_id=order_id,
                    order_name=order_name,
                    error="Downloaded content is not a valid PDF",
                    screenshot_path=screenshot_path
                )
            
            with open(filepath, 'wb') as f:
                f.write(pdf_content)
            
            logger.info(f"PDF saved successfully: {filepath}")
        else:
            status = pdf_status if pdf_status else 'No response captured'
            screenshot_path = await _save_screenshot(page, f"pdf_download_failed_{order_id}")
            await page.close()
            return ScrapeResult(
                success=False,
                shopify_order_id=order_id,
                order_name=order_name,
                error=f"Failed to download PDF: {status}",
                screenshot_path=screenshot_path
            )
        
        await page.close()
        
        return ScrapeResult(
            success=True,
            shopify_order_id=order_id,
            order_name=order_name,
            invoice_number=invoice_number,
            invoice_uuid=invoice_uuid,
            invoice_url=invoice_url,
            invoice_date=invoice_date,
            filepath=filepath
        )
        
    except Exception as e:
        logger.error(f"Error scraping invoice for {order_desc}: {e}")
        # Ensure page is closed even on error
        try:
            if 'page' in locals() and page:
                await page.close()
        except Exception:
            pass
        return ScrapeResult(
            success=False,
            shopify_order_id=order_id,
            order_name=order_name,
            error=str(e)
        )


async def scrape_invoice_with_retry(
    order_id: str,
    order_name: Optional[str] = None,
    order_date: Optional[str] = None
) -> ScrapeResult:
    """
    Scrape invoice with retry logic.
    """
    if is_cancelled():
        return ScrapeResult(success=False, error="Cancelled by user")
    
    last_error = None
    
    for attempt in range(settings.retry_attempts):
        if is_cancelled():
            return ScrapeResult(success=False, error="Cancelled by user")
        
        try:
            logger.info(f"Attempt {attempt + 1}/{settings.retry_attempts} for order {order_name or order_id}")
            result = await scrape_admin_invoice(order_id, order_name, order_date)
            
            # If login required, don't retry - bubble up immediately
            if result.needs_login:
                return result
            
            # If successful or definitive failure, return
            if result.success or "not be generated yet" in (result.error or ""):
                return result
            
            last_error = result.error
            
        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed: {e}")
            last_error = str(e)
        
        if attempt < settings.retry_attempts - 1:
            await asyncio.sleep(settings.retry_delay)
    
    return ScrapeResult(
        success=False,
        shopify_order_id=order_id,
        order_name=order_name,
        error=last_error or "Unknown error after all retries"
    )
