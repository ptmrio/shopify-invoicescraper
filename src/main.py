"""Shopify VAT Invoice Scraper - FastAPI Application

This service provides HTTP endpoints for scraping VAT invoices from
Shopify admin UI using a persistent browser session.
"""
import os
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .models import (
    AdminScrapeRequest,
    ScrapeResult, 
    BatchScrapeRequest, 
    BatchScrapeResult, 
    HealthResponse,
    SessionStatus,
    SessionStatusResponse,
)
from .scraper import (
    scrape_admin_invoice,
    scrape_invoice_with_retry,
    cancel_scraping, 
    is_cancelled, 
    reset_cancel,
    get_session_status,
    set_session_status,
    ensure_logged_in,
    signal_login_complete,
    close_browser,
    close_all_pages,
    show_status_page,
    is_browser_running,
)
from .config import settings


# Configure logging
def setup_logging():
    """Configure application logging."""
    settings.ensure_directories()
    
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    log_file = os.path.join(settings.log_dir, 'scraper.log')
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
    
    # Reduce noise from external libraries
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)


setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    logger.info("="*60)
    logger.info("Shopify VAT Invoice Scraper v2.0 starting...")
    logger.info(f"Store: {settings.store_slug}")
    logger.info(f"Admin URL: {settings.admin_store_url}")
    logger.info(f"Download directory: {os.path.abspath(settings.download_dir)}")
    logger.info(f"Profile directory: {os.path.abspath(settings.profile_dir)}")
    logger.info(f"Headless mode: {settings.headless}")
    logger.info("="*60)
    yield
    logger.info("Shutting down - closing browser...")
    await close_browser()
    logger.info("Shopify VAT Invoice Scraper stopped.")


app = FastAPI(
    title="Shopify VAT Invoice Scraper",
    description="Scrapes VAT invoice PDFs from Shopify admin UI using persistent sessions",
    version="2.0.0",
    lifespan=lifespan
)

# Enable CORS for browser-based requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint including session and browser status."""
    return HealthResponse(
        status="healthy",
        headless_mode=settings.headless,
        download_dir=os.path.abspath(settings.download_dir),
        session_status=get_session_status(),
        browser_running=is_browser_running()
    )


@app.get("/session/status", response_model=SessionStatusResponse)
async def get_session_status_endpoint():
    """Get the current Shopify admin session status."""
    return SessionStatusResponse(
        status=get_session_status(),
        store_slug=settings.store_slug,
        message=_get_session_message(get_session_status())
    )


def _get_session_message(status: SessionStatus) -> str:
    """Get a human-readable message for session status."""
    messages = {
        SessionStatus.UNKNOWN: "Session status not yet checked",
        SessionStatus.LOGGED_IN: "Logged into Shopify admin",
        SessionStatus.LOGGED_OUT: "Not logged in",
        SessionStatus.LOGIN_REQUIRED: "Manual login required - browser window should be open",
        SessionStatus.CHECKING: "Checking session status...",
    }
    return messages.get(status, "Unknown status")


@app.post("/session/check", response_model=SessionStatusResponse)
async def check_session():
    """
    Check and ensure we're logged into Shopify admin.
    
    If not logged in, opens a browser window for manual login and waits.
    Returns when login is complete or times out.
    Browser shows status page when ready.
    """
    success, error = await ensure_logged_in()
    
    if not success:
        raise HTTPException(
            status_code=401,
            detail=error or "Login failed or timed out"
        )
    
    # Show status page to indicate browser is ready and waiting
    await show_status_page()
    
    return SessionStatusResponse(
        status=SessionStatus.LOGGED_IN,
        store_slug=settings.store_slug,
        message="Successfully logged into Shopify admin"
    )


@app.post("/session/login-complete")
async def notify_login_complete():
    """
    Signal that manual login has been completed.
    
    Call this endpoint after logging in manually to speed up the process.
    """
    signal_login_complete()
    return {"status": "ok", "message": "Login completion signaled"}


@app.post("/cancel")
async def cancel_current_run():
    """Cancel the current scraping operation."""
    cancel_scraping()
    logger.info("Cancellation requested")
    return {"status": "cancelled", "message": "Cancellation signal sent"}


@app.post("/reset")
async def reset_cancel_flag():
    """Reset the cancellation flag for a new run."""
    reset_cancel()
    logger.info("Cancel flag reset")
    return {"status": "ok", "message": "Ready for new run"}


@app.post("/browser/close")
async def close_browser_endpoint():
    """
    Close the browser instance to free resources.
    
    The browser will be re-launched on the next scrape or session check.
    """
    await close_browser()
    set_session_status(SessionStatus.UNKNOWN)
    logger.info("Browser closed via API")
    return {"status": "ok", "message": "Browser closed"}


@app.post("/browser/idle")
async def show_idle_status():
    """
    Show the status page in browser to indicate idle/ready state.
    
    Call this after a batch of operations completes to provide clear
    visual feedback that the browser is intentionally kept open.
    """
    await show_status_page()
    logger.info("Browser set to idle status page")
    return {"status": "ok", "message": "Browser showing idle status"}


@app.post("/scrape-invoice", response_model=ScrapeResult)
async def scrape_single_invoice(request: AdminScrapeRequest):
    """
    Scrape a single VAT invoice from Shopify admin.
    
    Requires order_id (legacyResourceId from Shopify GraphQL API).
    Uses persistent browser session - will indicate if login is required.
    """
    logger.info(f"Received scrape request for order: {request.order_name or request.order_id}")
    
    result = await scrape_invoice_with_retry(
        request.order_id, 
        request.order_name, 
        request.order_date
    )
    
    if result.success:
        logger.info(f"Successfully scraped invoice {result.invoice_number} for order {result.order_name}")
    elif result.needs_login:
        logger.warning(f"Login required for order {request.order_name or request.order_id}")
    else:
        logger.error(f"Failed to scrape invoice: {result.error}")
    
    return result


@app.post("/scrape-batch", response_model=BatchScrapeResult)
async def scrape_batch_invoices(request: BatchScrapeRequest):
    """
    Scrape multiple VAT invoices in sequence.
    
    Processes invoices one at a time. If login is required during processing,
    the batch will pause and return with needs_login=True.
    """
    logger.info(f"Received batch scrape request for {len(request.orders)} orders")
    
    # First ensure we're logged in
    logged_in, error = await ensure_logged_in()
    if not logged_in:
        return BatchScrapeResult(
            total=len(request.orders),
            successful=0,
            failed=len(request.orders),
            results=[],
            needs_login=True
        )
    
    results = []
    successful = 0
    failed = 0
    
    for i, order in enumerate(request.orders, 1):
        order_desc = order.order_name or f"order {i}/{len(request.orders)}"
        logger.info(f"Batch progress: Scraping {order_desc}...")
        
        result = await scrape_invoice_with_retry(
            order.order_id, 
            order.order_name, 
            order.order_date
        )
        results.append(result)
        
        if result.needs_login:
            # Session expired mid-batch
            logger.warning(f"Session expired at order {i}/{len(request.orders)}")
            return BatchScrapeResult(
                total=len(request.orders),
                successful=successful,
                failed=failed + (len(request.orders) - i),
                results=results,
                needs_login=True
            )
        
        if result.success:
            successful += 1
            logger.info(f"Batch: Successfully scraped {result.invoice_number}")
        else:
            failed += 1
            logger.error(f"Batch: Failed to scrape {order_desc}: {result.error}")
    
    logger.info(f"Batch complete: {successful} successful, {failed} failed")
    
    # Show status page to indicate browser is ready for next batch
    await show_status_page()
    
    return BatchScrapeResult(
        total=len(request.orders),
        successful=successful,
        failed=failed,
        results=results
    )


if __name__ == "__main__":
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=False
    )
