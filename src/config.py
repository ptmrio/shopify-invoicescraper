"""Shopify VAT Invoice Scraper - Configuration"""
from pydantic_settings import BaseSettings
from pydantic import field_validator
from pathlib import Path


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Shopify Admin settings
    store_slug: str = ""  # Required: Your Shopify store identifier (e.g., "my-store")
    admin_base_url: str = "https://admin.shopify.com"
    
    # Browser profile for persistent login
    profile_dir: str = "./.browser-profile"
    
    # Directories
    download_dir: str = "./downloads"
    screenshot_dir: str = "./screenshots"
    log_dir: str = "./logs"
    
    # Timezone for date folder organization
    timezone: str = "UTC"
    
    # Browser settings
    headless: bool = False  # Headed mode required for login and reliability
    
    # Timeouts (milliseconds)
    timeout_page_load: int = 60000  # 60 seconds for initial page load
    timeout_selector: int = 30000   # 30 seconds to wait for invoice link
    timeout_download: int = 30000   # 30 seconds for PDF download
    timeout_login_wait: int = 300000  # 5 minutes to wait for manual login
    
    # Retry logic
    retry_attempts: int = 3
    retry_delay: float = 2.0  # seconds between retries
    
    # Human-like delay settings (seconds)
    human_delay_min: float = 0.5  # Minimum delay between actions
    human_delay_max: float = 2.0  # Maximum delay between actions
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8000
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
    
    @field_validator('store_slug')
    @classmethod
    def store_slug_required(cls, v: str) -> str:
        if not v or v.strip() == "":
            raise ValueError(
                "STORE_SLUG is required. Set it in your .env file.\n"
                "Example: STORE_SLUG=my-store-name\n"
                "Find it in your Shopify admin URL: https://admin.shopify.com/store/YOUR-STORE-SLUG"
            )
        return v.strip()
    
    def ensure_directories(self) -> None:
        """Create required directories if they don't exist."""
        for dir_path in [self.download_dir, self.screenshot_dir, self.log_dir, self.profile_dir]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    @property
    def admin_store_url(self) -> str:
        """Get the full admin URL for the store."""
        return f"{self.admin_base_url}/store/{self.store_slug}"
    
    def get_admin_order_url(self, order_id: str) -> str:
        """Get the admin URL for a specific order."""
        return f"{self.admin_store_url}/orders/{order_id}"
    
    def get_date_folder(self, date_str: str) -> Path:
        """Get the download folder for a specific date (YYYY-MM-DD format)."""
        folder = Path(self.download_dir) / date_str
        folder.mkdir(parents=True, exist_ok=True)
        return folder


settings = Settings()
