"""
Crawl4AI Crawler Implementation

Implementation of BaseCrawler using the Crawl4AI library.
This is the default crawler implementation with full stealth mode support.
"""

from __future__ import annotations

# Windows encoding fix - must be at module import time to handle crawl4ai/Rich Unicode output
import os
import sys

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass

import asyncio
import json
from typing import Optional

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
from crawl4ai import CrawlResult as Crawl4AICrawlResult
from crawl4ai import LLMConfig, UndetectedAdapter
from crawl4ai.async_crawler_strategy import AsyncPlaywrightCrawlerStrategy
from crawl4ai.extraction_strategy import LLMExtractionStrategy, NoExtractionStrategy

from crawler.base_crawler import BaseCrawler, BaseCrawlerConfig, CrawlResultBase
from env_vars import OPENAI_API_KEY, OPENAI_MODEL
from utilities import logger


class Crawl4AICrawlerConfig(BaseCrawlerConfig):
    """
    Configuration for Crawl4AI crawler implementation

    Extends BaseCrawlerConfig with Crawl4AI-specific settings.
    """

    # Crawl4AI-specific settings
    browser_mode: str = "dedicated"
    """Browser mode: dedicated, shared, or persistent"""

    use_persistent_context: bool = False
    """Use persistent context for undetected browsing"""

    user_data_dir: Optional[str] = None
    """Directory for persistent browser data"""

    accept_downloads: bool = False
    """Whether to accept downloads"""

    java_script_enabled: bool = True
    """Enable JavaScript execution"""

    use_undetected_mode: bool = False
    """Use UndetectedAdapter for maximum bot detection bypass"""

    use_magic_mode: bool = False
    """Enable magic mode for aggressive bot detection bypass (experimental)"""

    custom_headers: Optional[dict] = None
    """Custom HTTP headers to use for requests"""

    def __init__(self, **data):
        super().__init__(**data)
        # Set default LLM API token from environment
        if self.use_llm and not self.llm_api_token:
            self.llm_api_token = OPENAI_API_KEY
            if not self.llm_provider:
                self.llm_provider = f"openai/{OPENAI_MODEL or 'gpt-4o-mini'}"


class Crawl4AICrawler(BaseCrawler):
    """
    Crawl4AI implementation of BaseCrawler

    Provides full implementation using the Crawl4AI library with:
    - Advanced stealth mode (stealth.min.js injection)
    - Undetected mode (patchright adapter)
    - LLM-based content extraction
    - Interactive browsing capabilities
    """

    def __init__(self, config: Optional[Crawl4AICrawlerConfig] = None):
        """
        Initialize the Crawl4AI crawler

        Args:
            config: Crawl4AI crawler configuration
        """
        super().__init__(config or Crawl4AICrawlerConfig())
        self.config: Crawl4AICrawlerConfig = self.config  # Type hint for IDE
        self._crawler: Optional[AsyncWebCrawler] = None
        self._stealth_js: Optional[str] = None
        logger.info(
            f"Crawl4AICrawler initialized with stealth_mode={self.config.use_stealth_mode}, "
            f"llm_enabled={self.config.use_llm}"
        )

    def _get_browser_config(self) -> BrowserConfig:
        """Create browser configuration with stealth mode support"""
        import os

        browser_kwargs = {
            "browser_type": self.config.browser_type,
            "headless": self.config.headless,
            "browser_mode": self.config.browser_mode,
            "use_persistent_context": self.config.use_persistent_context,
            "viewport_width": self.config.viewport_width,
            "viewport_height": self.config.viewport_height,
            "accept_downloads": self.config.accept_downloads,
            "java_script_enabled": self.config.java_script_enabled,
            "ignore_https_errors": self.config.ignore_https_errors,
            "enable_stealth": self.config.use_stealth_mode,
        }

        if self.config.user_agent:
            browser_kwargs["user_agent"] = self.config.user_agent

        if self.config.user_data_dir:
            browser_kwargs["user_data_dir"] = self.config.user_data_dir

        # Auto-add Docker/AWS args if running in containerized environment
        extra_args = list(self.config.extra_args) if self.config.extra_args else []

        # Check environment variable for Docker detection
        is_docker = os.environ.get("RUNNING_IN_DOCKER", "").lower() in (
            "true",
            "1",
            "yes",
        )

        # Add container-required args
        if is_docker:
            container_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ]
            for arg in container_args:
                if arg not in extra_args:
                    extra_args.append(arg)
            logger.info(f"🐳 Docker/container detected - added sandbox disable args")

        if extra_args:
            browser_kwargs["extra_args"] = extra_args

        # Add custom headers if provided
        if self.config.custom_headers:
            browser_kwargs["headers"] = self.config.custom_headers
            logger.info(
                f"📋 Using custom headers: {list(self.config.custom_headers.keys())}"
            )

        browser_config = BrowserConfig(**browser_kwargs)

        logger.debug(
            f"Browser config: {self.config.browser_type}, mode={self.config.browser_mode}, "
            f"headless={self.config.headless}, stealth={self.config.use_stealth_mode}"
        )
        return browser_config

    def _get_extraction_strategy(self):
        """Get the appropriate extraction strategy"""
        if not self.config.use_llm:
            return NoExtractionStrategy()

        if not self.config.llm_api_token:
            logger.warning(
                "LLM enabled but no API token provided, falling back to no extraction"
            )
            return NoExtractionStrategy()

        default_prompt = """Extract and summarize the main content from this webpage.
Focus on the key information, facts, and insights.
Organize the content in a clear and structured way."""

        extraction_prompt = self.config.llm_extraction_prompt or default_prompt

        logger.info(f"Using LLM extraction with provider: {self.config.llm_provider}")

        llm_config = LLMConfig(
            provider=self.config.llm_provider or "openai/gpt-4o-mini",
            api_token=self.config.llm_api_token,
        )

        return LLMExtractionStrategy(
            llm_config=llm_config,
            instruction=extraction_prompt,
        )

    def _get_crawler_config(self) -> CrawlerRunConfig:
        """Create crawler run configuration"""
        cache_mode_map = {
            "enabled": CacheMode.ENABLED,
            "disabled": CacheMode.DISABLED,
            "bypass": CacheMode.BYPASS,
            "read_only": CacheMode.READ_ONLY,
            "write_only": CacheMode.WRITE_ONLY,
        }

        config_kwargs = {
            "cache_mode": cache_mode_map.get(self.config.cache_mode, CacheMode.ENABLED),
            "word_count_threshold": self.config.word_count_threshold,
            "exclude_external_links": self.config.exclude_external_links,
            "exclude_external_images": self.config.exclude_external_images,
            "extraction_strategy": self._get_extraction_strategy(),
            "wait_until": self.config.wait_until,
            "page_timeout": self.config.page_timeout,
            "screenshot": self.config.screenshot_enabled,
        }

        # Enable magic mode if configured
        if self.config.use_magic_mode:
            config_kwargs["magic"] = True
            logger.info("🪄 Magic mode enabled for aggressive bot detection bypass")

        # Inject stealth scripts if enabled and loaded
        if self.config.use_stealth_mode and self._stealth_js:
            extra_stealth_js = """
// Override navigator.webdriver to be undefined
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// Replace HeadlessChrome in user agent
const originalUserAgent = navigator.userAgent;
if (originalUserAgent.includes('HeadlessChrome')) {
    Object.defineProperty(navigator, 'userAgent', {
        get: () => originalUserAgent.replace('HeadlessChrome', 'Chrome')
    });
}

// Fix navigator.plugins for headless detection
if (navigator.plugins.length === 0) {
    Object.defineProperty(navigator, 'plugins', {
        get: () => [
            {
                0: {type: "application/pdf", suffixes: "pdf", description: "Portable Document Format"},
                description: "Portable Document Format",
                filename: "internal-pdf-viewer",
                length: 1,
                name: "Chrome PDF Plugin"
            },
            {
                0: {type: "application/x-google-chrome-pdf", suffixes: "pdf", description: "Portable Document Format"},
                description: "Portable Document Format",
                filename: "internal-pdf-viewer",
                length: 1,
                name: "Chrome PDF Viewer"
            },
            {
                0: {type: "application/x-nacl", suffixes: "", description: "Native Client Executable"},
                1: {type: "application/x-pnacl", suffixes: "", description: "Portable Native Client Executable"},
                description: "Native Client",
                filename: "internal-nacl-plugin",
                length: 2,
                name: "Native Client"
            }
        ]
    });
}
"""
            js_commands = [self._stealth_js, extra_stealth_js]
            config_kwargs["js_code"] = js_commands
            logger.info("✅ Stealth scripts will be injected via js_code parameter")

        return CrawlerRunConfig(**config_kwargs)

    async def start(self):
        """Initialize and start the crawler"""
        if self._crawler is not None:
            logger.warning("Crawler already started")
            return

        browser_config = self._get_browser_config()

        # Use UndetectedAdapter if configured
        if self.config.use_undetected_mode:
            logger.info("Using UndetectedAdapter for maximum bot detection bypass")
            undetected_adapter = UndetectedAdapter()
            crawler_strategy = AsyncPlaywrightCrawlerStrategy(
                browser_config=browser_config, browser_adapter=undetected_adapter
            )
            self._crawler = AsyncWebCrawler(
                crawler_strategy=crawler_strategy, config=browser_config
            )
        else:
            self._crawler = AsyncWebCrawler(config=browser_config)

        await self._crawler.__aenter__()

        # Inject stealth.min.js if stealth mode is enabled
        await self._inject_stealth_scripts()

        logger.info("Crawl4AICrawler started successfully")

    async def stop(self):
        """Stop and cleanup the crawler"""
        if self._crawler is None:
            logger.warning("Crawler not started")
            return

        await self._crawler.__aexit__(None, None, None)
        self._crawler = None
        logger.info("Crawl4AICrawler stopped successfully")

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

    def _convert_crawl4ai_result(self, result: Crawl4AICrawlResult) -> CrawlResultBase:
        """Convert Crawl4AI result to base result format"""
        # Parse media information
        media = {}
        if result.media:
            try:
                media = (
                    json.loads(result.media)
                    if isinstance(result.media, str)
                    else result.media
                )
            except json.JSONDecodeError:
                logger.warning("Failed to parse media JSON")

        # Parse links information
        links = {}
        if result.links:
            try:
                links = (
                    json.loads(result.links)
                    if isinstance(result.links, str)
                    else result.links
                )
            except json.JSONDecodeError:
                logger.warning("Failed to parse links JSON")

        # Build metadata
        metadata = {
            "title": getattr(result, "title", None),
            "description": getattr(result, "description", None),
            "keywords": getattr(result, "keywords", None),
            "status_code": getattr(result, "status_code", None),
            "response_headers": getattr(result, "response_headers", None),
        }

        # Get extracted content from LLM if enabled
        extracted_content = None
        if self.config.use_llm and hasattr(result, "extracted_content"):
            extracted_content = result.extracted_content

        # Get screenshot if enabled
        screenshot_data: Optional[bytes] = None
        if self.config.screenshot_enabled and hasattr(result, "screenshot"):
            # Crawl4AI returns screenshot as base64 string or path, convert to bytes if needed
            screenshot = result.screenshot
            if isinstance(screenshot, str):
                # If it's a base64 string, decode it
                import base64

                try:
                    screenshot_data = base64.b64decode(screenshot)
                except Exception:
                    # If not base64, it might be a file path - log warning
                    logger.warning(
                        f"Screenshot is string but not base64: {screenshot[:50]}..."
                    )
                    screenshot_data = None
            elif isinstance(screenshot, bytes):
                screenshot_data = screenshot
            else:
                screenshot_data = None

        return CrawlResultBase(
            url=result.url,
            success=result.success,
            html=result.html,
            markdown=result.markdown,
            cleaned_html=result.cleaned_html,
            title=getattr(result, "title", None),
            description=getattr(result, "description", None),
            keywords=getattr(result, "keywords", None),
            status_code=getattr(result, "status_code", None),
            error_message=result.error_message if not result.success else None,
            screenshot=screenshot_data,
            media=media,
            links=links,
            metadata=metadata,
            extracted_content=extracted_content,
            response_headers=getattr(result, "response_headers", None),
        )

    async def crawl(self, url: str, **kwargs) -> CrawlResultBase:
        """Crawl a single URL and extract content"""
        if self._crawler is None:
            raise RuntimeError(
                "Crawler not started. Use 'async with Crawl4AICrawler()' or call start() first"
            )

        logger.info(f"Crawling URL: {url}")

        try:
            crawler_config = self._get_crawler_config()

            # Apply runtime overrides
            if "word_count_threshold" in kwargs:
                crawler_config.word_count_threshold = kwargs["word_count_threshold"]
            if "screenshot" in kwargs:
                crawler_config.screenshot = kwargs["screenshot"]

            # Execute the crawl
            result: Crawl4AICrawlResult = await self._crawler.arun(url=url, config=crawler_config)  # type: ignore

            if not result.success:
                logger.error(f"Crawl failed for {url}: {result.error_message}")
                return CrawlResultBase(
                    url=url,
                    success=False,
                    error_message=result.error_message,
                )

            logger.info(
                f"Successfully crawled {url} (length: {len(result.html or '')} chars)"
            )

            return self._convert_crawl4ai_result(result)

        except Exception as e:
            logger.error(f"Exception during crawl of {url}: {str(e)}")
            import traceback

            traceback.print_exc()
            return CrawlResultBase(
                url=url,
                success=False,
                error_message=str(e),
            )

    async def crawl_multiple(
        self, urls: list[str], max_concurrent: int = 5
    ) -> list[CrawlResultBase]:
        """Crawl multiple URLs concurrently"""
        if self._crawler is None:
            raise RuntimeError("Crawler not started")

        logger.info(f"Crawling {len(urls)} URLs with max_concurrent={max_concurrent}")

        semaphore = asyncio.Semaphore(max_concurrent)

        async def crawl_with_semaphore(url: str) -> CrawlResultBase:
            async with semaphore:
                return await self.crawl(url)

        results = await asyncio.gather(*[crawl_with_semaphore(url) for url in urls])

        successful = sum(1 for r in results if r.success)
        logger.info(
            f"Completed: {successful} successful, {len(urls) - successful} failed"
        )

        return results

    # Interactive browsing methods (Crawl4AI supports these)

    async def navigate_and_get_page(self, url: str, wait_until: str = "networkidle"):
        """Navigate to a URL and return page object for interactions"""
        if self._crawler is None:
            raise RuntimeError("Crawler not started")

        logger.info(f"Navigating to: {url}")

        config = CrawlerRunConfig(
            cache_mode=CacheMode.BYPASS,
            wait_until=wait_until,
            page_timeout=self.config.page_timeout,
        )

        await self._crawler.arun(url=url, config=config)

        # Get the page from the session
        strategy = self._crawler.crawler_strategy
        if not strategy:
            raise RuntimeError("Crawler strategy not available")

        if not hasattr(strategy, "sessions") or not strategy.sessions:  # type: ignore
            raise RuntimeError("No active session found after navigation")

        sessions = strategy.sessions  # type: ignore
        if not sessions:
            raise RuntimeError("No sessions available")

        session_id = list(sessions.keys())[-1]
        session = sessions[session_id]
        page = session["page"]

        logger.info(f"Successfully navigated to: {url}")
        return page

    async def find_element(self, page, selectors: list[str], timeout: int = 5000):
        """Find an element using multiple selector strategies"""
        for selector in selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=timeout)
                if element:
                    logger.info(f"Found element with selector: {selector}")
                    return element
            except Exception:
                continue

        logger.warning(f"Could not find element with selectors: {selectors}")
        return None

    async def type_text(
        self, element, text: str, delay: int = 100, clear_first: bool = False
    ):
        """Type text into an element with human-like delays"""
        if clear_first:
            await element.fill("")

        logger.info(f"Typing text (length: {len(text)}, delay: {delay}ms)")
        for char in text:
            await element.type(char, delay=delay)

    async def click_element(
        self, element, delay_before: float = 0, delay_after: float = 0
    ):
        """Click an element with optional delays"""
        if delay_before > 0:
            await asyncio.sleep(delay_before)

        logger.info("Clicking element")
        await element.click()

        if delay_after > 0:
            await asyncio.sleep(delay_after)

    async def press_key(self, element, key: str, delay_after: float = 0):
        """Press a key on an element"""
        logger.info(f"Pressing key: {key}")
        await element.press(key)

        if delay_after > 0:
            await asyncio.sleep(delay_after)

    async def scroll_page(self, page, direction: str = "down", amount: int = 500):
        """Scroll the page"""
        scroll_script = {
            "down": f"window.scrollBy(0, {amount})",
            "up": f"window.scrollBy(0, -{amount})",
            "left": f"window.scrollBy(-{amount}, 0)",
            "right": f"window.scrollBy({amount}, 0)",
        }

        if direction not in scroll_script:
            raise ValueError(f"Invalid direction: {direction}")

        logger.info(f"Scrolling {direction} by {amount}px")
        await page.evaluate(scroll_script[direction])

    async def wait_for_load(
        self, page, state: str = "networkidle", timeout: int = 30000
    ):
        """Wait for page to reach a certain load state"""
        logger.info(f"Waiting for load state: {state}")
        await page.wait_for_load_state(state, timeout=timeout)

    async def get_page_content(self, page) -> str:
        """Get the HTML content of the page"""
        logger.info("Getting page content")
        return await page.content()

    async def execute_js(self, page, js_code: str):
        """Execute JavaScript code in the page context"""
        logger.info("Executing JavaScript")
        return await page.evaluate(js_code)
