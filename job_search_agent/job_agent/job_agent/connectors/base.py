"""
BaseConnector
=============
All platform connectors inherit from this class.
"""

from abc import ABC, abstractmethod
from typing import Optional
from core.logger import get_logger


class BaseConnector(ABC):
    """Abstract base for job platform connectors."""

    platform_name: str = "base"

    def __init__(self, config: dict):
        self.config = config
        self.logger = get_logger(self.platform_name)

    @abstractmethod
    def search(
        self,
        keywords: str,
        location: Optional[str],
        remote: bool,
        limit: int,
    ) -> list[dict]:
        """
        Search for jobs. Returns list of job dicts:
        {
            id, platform, title, company, location,
            url, description, posted_date, easy_apply (bool)
        }
        """
        ...

    @abstractmethod
    def apply(self, job: dict) -> tuple[bool, str]:
        """
        Apply to a job. Returns (success: bool, message: str).
        job dict includes cover_letter key injected by orchestrator.
        """
        ...

    def _new_browser(self, headless: bool = True):
        """Launch a Playwright browser instance."""
        from playwright.sync_api import sync_playwright
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=headless)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        )
        return pw, browser, context

    def _job_dict(self, **kwargs) -> dict:
        """Helper to create a standardised job dict."""
        return {
            "id": kwargs.get("id", ""),
            "platform": self.platform_name,
            "title": kwargs.get("title", ""),
            "company": kwargs.get("company", ""),
            "location": kwargs.get("location", ""),
            "url": kwargs.get("url", ""),
            "description": kwargs.get("description", ""),
            "posted_date": kwargs.get("posted_date", ""),
            "easy_apply": kwargs.get("easy_apply", False),
        }
