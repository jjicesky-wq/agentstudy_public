"""
Abstract Base Crawler Module

Defines the interface for all crawler implementations (Crawl4AI, Selenium, Playwright, etc.)
This allows for easy swapping of crawler backends while maintaining a consistent API.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel

from utilities import logger


@dataclass
class CrawlResultBase:
    """
    Base class for crawl results - framework-agnostic

    This represents the common data structure returned by all crawler implementations.
    """

    url: str
    """The URL that was crawled"""

    success: bool
    """Whether the crawl was successful"""

    html: Optional[str] = None
    """Raw HTML content"""

    markdown: Optional[str] = None
    """Markdown-formatted content"""

    cleaned_html: Optional[str] = None
    """Cleaned HTML content (ads, scripts removed)"""

    text: Optional[str] = None
    """Plain text content"""

    title: Optional[str] = None
    """Page title"""

    description: Optional[str] = None
    """Page meta description"""

    keywords: Optional[str] = None
    """Page meta keywords"""

    status_code: Optional[int] = None
    """HTTP status code"""

    error_message: Optional[str] = None
    """Error message if crawl failed"""

    screenshot: Optional[bytes] = None
    """Screenshot data (if enabled)"""

    media: Optional[dict[str, Any]] = None
    """Extracted media information (images, videos)"""

    links: Optional[dict[str, Any]] = None
    """Extracted links"""

    metadata: Optional[dict[str, Any]] = None
    """Additional metadata"""

    extracted_content: Optional[str] = None
    """LLM-extracted content (if LLM enabled)"""

    response_headers: Optional[dict[str, str]] = None
    """HTTP response headers"""


class BaseCrawlerConfig(BaseModel):
    """
    Base configuration for all crawler implementations

    Each implementation can extend this with its own specific settings.
    """

    # Stealth mode settings
    use_stealth_mode: bool = True
    """Enable stealth mode to avoid bot detection"""

    headless: bool = True
    """Run browser in headless mode"""

    user_agent: Optional[str] = None
    """Custom user agent string"""

    # Browser settings
    browser_type: str = "chromium"
    """Browser type: chromium, firefox, or webkit"""

    viewport_width: int = 1920
    """Browser viewport width"""

    viewport_height: int = 1080
    """Browser viewport height"""

    # Network settings
    page_timeout: int = 90000
    """Page load timeout in milliseconds"""

    wait_until: str = "domcontentloaded"
    """Wait until: commit, domcontentloaded, load, networkidle"""

    ignore_https_errors: bool = True
    """Ignore HTTPS certificate errors"""

    # Content extraction settings
    word_count_threshold: int = 10
    """Minimum word count for content blocks"""

    exclude_external_links: bool = False
    """Exclude external links from extraction"""

    exclude_external_images: bool = False
    """Exclude external images from extraction"""

    # Screenshot settings
    screenshot_enabled: bool = False
    """Enable page screenshots"""

    # LLM settings
    use_llm: bool = False
    """Enable LLM-based content extraction"""

    llm_provider: Optional[str] = None
    """LLM provider and model (e.g., 'openai/gpt-4o-mini')"""

    llm_api_token: Optional[str] = None
    """API token for LLM"""

    llm_extraction_prompt: Optional[str] = None
    """Custom prompt for LLM extraction"""

    # Cache settings
    cache_mode: str = "enabled"
    """Cache mode: enabled, disabled, bypass, read_only, write_only"""

    # Extra settings (implementation-specific)
    extra_args: Optional[list[str]] = None
    """Extra browser launch arguments"""


class BaseCrawler(ABC):
    """
    Abstract base class for web crawlers

    All crawler implementations (Crawl4AI, Selenium, Playwright, etc.)
    must implement this interface to ensure compatibility with the rest
    of the system (CrawlerService, etc.).

    Usage:
        class MyCrawler(BaseCrawler):
            async def crawl(self, url: str, **kwargs) -> CrawlResultBase:
                # Implementation here
                pass

            # Implement other abstract methods...
    """

    def __init__(self, config: Optional[BaseCrawlerConfig] = None):
        """
        Initialize the crawler

        Args:
            config: Crawler configuration (uses defaults if not provided)
        """
        self.config = config or BaseCrawlerConfig()

    @abstractmethod
    async def start(self):
        """
        Initialize and start the crawler

        This should set up the browser instance, load any necessary
        resources (like stealth scripts), and prepare for crawling.
        """

    @abstractmethod
    async def stop(self):
        """
        Stop and cleanup the crawler

        This should close the browser, release resources, and perform
        any necessary cleanup.
        """

    @abstractmethod
    async def crawl(self, url: str, **kwargs) -> CrawlResultBase:
        """
        Crawl a single URL and extract content

        Args:
            url: The URL to crawl
            **kwargs: Additional parameters to override config

        Returns:
            CrawlResultBase with extracted content

        Raises:
            RuntimeError: If crawler is not started
        """

    @abstractmethod
    async def crawl_multiple(
        self, urls: list[str], max_concurrent: int = 5
    ) -> list[CrawlResultBase]:
        """
        Crawl multiple URLs concurrently

        Args:
            urls: List of URLs to crawl
            max_concurrent: Maximum number of concurrent crawls

        Returns:
            List of CrawlResultBase objects
        """

    # Optional methods with default implementations

    async def __aenter__(self):
        """Async context manager entry"""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.stop()

    async def extract_with_llm(
        self,
        content: str,
        prompt: str,
        model: Optional[str] = None,
    ) -> str:
        """
        Extract or process content using LLM (separate from crawling)

        Default implementation - can be overridden by implementations.

        Args:
            content: The content to process
            prompt: The extraction/processing prompt
            model: Optional model override

        Returns:
            Processed content from LLM
        """
        # Default implementation using OpenAI
        from model_management import WEB_CONTENT_EXTRACTION, ModelManager

        from utilities import logger

        logger.info("Processing content with LLM")

        try:
            # Use ModelManager for web content extraction
            manager = ModelManager()
            llm = manager.get_model_by_scenario(WEB_CONTENT_EXTRACTION)
            conversation = llm.create_conversation(
                system_prompt="You are a helpful assistant that extracts and processes web content."
            )

            full_prompt = f"{prompt}\n\nContent:\n{content}"
            response = await conversation.run_chat_completion_async(
                user_prompt=full_prompt
            )

            logger.info("LLM processing completed successfully")
            return response

        except Exception as e:
            logger.error(f"LLM processing failed: {str(e)}")
            raise

    # Advanced interaction methods (optional - not all implementations may support these)

    async def navigate_and_get_page(self, url: str, wait_until: str = "networkidle"):
        """
        Navigate to a URL and return a page object for advanced interactions

        This is optional and may not be supported by all implementations.
        Implementations that don't support this should raise NotImplementedError.

        Args:
            url: URL to navigate to
            wait_until: Wait until condition

        Returns:
            Page object (implementation-specific)

        Raises:
            NotImplementedError: If not supported by this implementation
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support interactive page navigation"
        )

    async def find_element(self, page, selectors: list[str], timeout: int = 5000):
        """
        Find an element using multiple selector strategies

        This is optional and may not be supported by all implementations.

        Args:
            page: Page object (implementation-specific)
            selectors: List of CSS selectors to try
            timeout: Timeout in milliseconds

        Returns:
            Element locator if found, None otherwise

        Raises:
            NotImplementedError: If not supported by this implementation
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support element finding"
        )

    async def type_text(
        self, element, text: str, delay: int = 100, clear_first: bool = False
    ):
        """
        Type text into an element

        This is optional and may not be supported by all implementations.

        Args:
            element: Element to type into
            text: Text to type
            delay: Delay between keystrokes in milliseconds
            clear_first: Clear the element first

        Raises:
            NotImplementedError: If not supported by this implementation
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support text typing"
        )

    async def click_element(
        self, element, delay_before: float = 0, delay_after: float = 0
    ):
        """
        Click an element

        This is optional and may not be supported by all implementations.

        Args:
            element: Element to click
            delay_before: Delay before clicking (seconds)
            delay_after: Delay after clicking (seconds)

        Raises:
            NotImplementedError: If not supported by this implementation
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support element clicking"
        )

    async def press_key(self, element, key: str, delay_after: float = 0):
        """
        Press a key on an element

        This is optional and may not be supported by all implementations.

        Args:
            element: Element to press key on
            key: Key to press
            delay_after: Delay after pressing (seconds)

        Raises:
            NotImplementedError: If not supported by this implementation
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support key pressing"
        )

    async def scroll_page(self, page, direction: str = "down", amount: int = 500):
        """
        Scroll the page

        This is optional and may not be supported by all implementations.

        Args:
            page: Page object
            direction: Scroll direction
            amount: Amount to scroll in pixels

        Raises:
            NotImplementedError: If not supported by this implementation
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support page scrolling"
        )

    async def wait_for_load(
        self, page, state: str = "networkidle", timeout: int = 30000
    ):
        """
        Wait for page to reach a certain load state

        This is optional and may not be supported by all implementations.

        Args:
            page: Page object
            state: Load state to wait for
            timeout: Timeout in milliseconds

        Raises:
            NotImplementedError: If not supported by this implementation
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support wait for load"
        )

    async def get_page_content(self, page) -> str:
        """
        Get the HTML content of the page

        This is optional and may not be supported by all implementations.

        Args:
            page: Page object

        Returns:
            HTML content as string

        Raises:
            NotImplementedError: If not supported by this implementation
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support getting page content"
        )

    async def execute_js(self, page, js_code: str):
        """
        Execute JavaScript code in the page context

        This is optional and may not be supported by all implementations.

        Args:
            page: Page object
            js_code: JavaScript code to execute

        Returns:
            Result of the JavaScript execution

        Raises:
            NotImplementedError: If not supported by this implementation
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support JavaScript execution"
        )

    async def _inject_stealth_scripts(self):
        """Load stealth.min.js for later injection per-page"""
        if not self.config.use_stealth_mode:
            logger.debug("Stealth mode disabled, skipping script loading")
            return

        try:
            if self._stealth_js is None:
                stealth_js_path = os.path.join(
                    os.path.dirname(__file__), "stealth.min.js"
                )

                if not os.path.exists(stealth_js_path):
                    logger.warning(
                        f"stealth.min.js not found at {stealth_js_path}. "
                        "Run update_stealth_js.py to download it."
                    )
                    return

                with open(stealth_js_path, encoding="utf-8") as f:
                    self._stealth_js = f.read()
                    logger.info(
                        f"✅ Loaded stealth.min.js ({len(self._stealth_js)} bytes)"
                    )

        except Exception as e:
            logger.warning(f"Failed to load stealth scripts: {str(e)}")


# Type alias for backward compatibility
CrawlResult = CrawlResultBase
