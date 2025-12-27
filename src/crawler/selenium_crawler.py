"""
Selenium-based Crawler Implementation

This module provides a Selenium implementation of BaseCrawler with support for
multiple browsers (Chrome, Edge) and advanced bot detection bypass capabilities.

Features:
- Multi-browser support (Chrome with undetected-chromedriver, Microsoft Edge)
- Stealth.min.js injection for enhanced anti-detection
- User agent spoofing and webdriver property masking
- Screenshot capture support
- Configurable timeouts and options

Usage:
    from crawler.selenium_crawler import SeleniumCrawler, SeleniumCrawlerConfig

    # Chrome (default)
    config = SeleniumCrawlerConfig(
        browser_type="chrome",
        use_stealth_mode=True,
        use_undetected_mode=True,
        headless=True
    )

    # Microsoft Edge
    config = SeleniumCrawlerConfig(
        browser_type="edge",
        use_stealth_mode=True,
        headless=True
    )

    async with SeleniumCrawler(config=config) as crawler:
        result = await crawler.crawl("https://example.com")
        print(result.markdown)
"""

from __future__ import annotations

import asyncio
import os
import random
import tempfile
import time
from typing import Any, Optional, Union

import undetected_chromedriver as uc
from bs4 import BeautifulSoup
from markdownify import markdownify as md
from pydantic import Field
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.common.by import By
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from crawler.base_crawler import BaseCrawler, BaseCrawlerConfig, CrawlResultBase
from crawler.enhanced_stealth import (
    ULTRA_STEALTH_ARGS,
    ULTRA_STEALTH_PREFS,
    apply_ultra_stealth,
)
from utilities import logger

# Default User Agents
DEFAULT_CHROME_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
DEFAULT_EDGE_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36 Edg/140.0.0.0"


class SeleniumCrawlerConfig(BaseCrawlerConfig):
    """
    Configuration for Selenium-based crawler.

    Extends BaseCrawlerConfig with Selenium-specific options.
    Supports both Chrome and Microsoft Edge browsers.
    """

    # Browser selection
    selenium_browser: str = Field(
        default="chrome",
        description="Browser to use: 'chrome' or 'edge'",
    )

    # Selenium-specific options
    use_undetected_mode: bool = Field(
        default=True,
        description="Use undetected-chromedriver for maximum bot detection bypass (Chrome only)",
    )
    chrome_driver_path: Optional[str] = Field(
        default=None,
        description="Path to ChromeDriver executable (auto-download if None)",
    )
    edge_driver_path: Optional[str] = Field(
        default=None,
        description="Path to EdgeDriver executable (auto-download if None)",
    )
    chrome_binary_location: Optional[str] = Field(
        default=None, description="Path to Chrome browser binary"
    )
    edge_binary_location: Optional[str] = Field(
        default=None, description="Path to Edge browser binary"
    )
    user_data_dir: Optional[str] = Field(
        default=None, description="Browser user data directory for persistent sessions"
    )
    disable_dev_shm: bool = Field(
        default=True, description="Disable /dev/shm usage (useful for Docker)"
    )
    disable_gpu: bool = Field(default=False, description="Disable GPU acceleration")
    no_sandbox: bool = Field(
        default=True, description="Run Chrome without sandbox (required for Docker)"
    )
    disable_extensions: bool = Field(
        default=True, description="Disable Chrome extensions"
    )
    load_timeout_seconds: int = Field(
        default=90, description="Page load timeout in seconds (0 = no timeout)"
    )
    element_wait_timeout: int = Field(
        default=10, description="Element wait timeout in seconds"
    )
    stealth_js_path: Optional[str] = Field(
        default=None, description="Path to stealth.min.js file"
    )
    screenshot_on_error: bool = Field(
        default=False, description="Take screenshot on crawl errors"
    )
    extract_links: bool = Field(default=True, description="Extract links from page")
    extract_images: bool = Field(default=True, description="Extract images from page")
    use_ultra_stealth: bool = Field(
        default=False,
        description="Enable ultra stealth mode with advanced anti-detection patches (experimental)",
    )


class SeleniumCrawler(BaseCrawler):
    """
    Selenium-based implementation of BaseCrawler.

    Supports multiple browsers (Chrome, Edge) with advanced bot detection
    bypass capabilities. Chrome can use undetected-chromedriver for
    maximum stealth.
    """

    def __init__(self, config: Optional[SeleniumCrawlerConfig] = None) -> None:
        """
        Initialize Selenium crawler.

        Args:
            config: Selenium crawler configuration (uses defaults if None)
        """
        super().__init__(config or SeleniumCrawlerConfig())
        self.config: SeleniumCrawlerConfig = self.config  # type: ignore[assignment]
        self._driver: Optional[Union[webdriver.Chrome, webdriver.Edge]] = None
        self._stealth_js: Optional[str] = None
        self._temp_profile: Optional[str] = None
        self._browser_type: str = self.config.selenium_browser.lower()

    async def start(self) -> None:
        """Initialize and start the Selenium WebDriver."""
        logger.info(
            f"SeleniumCrawler initializing with browser={self._browser_type}, "
            f"stealth_mode={self.config.use_stealth_mode}, "
            f"undetected_mode={self.config.use_undetected_mode}"
        )

        # Load stealth.min.js if stealth mode is enabled
        if self.config.use_stealth_mode:
            await self._inject_stealth_scripts()

        # Initialize the appropriate driver based on browser type
        if self._browser_type == "edge":
            self._init_edge_driver()
        elif self._browser_type == "chrome":
            if self.config.use_undetected_mode:
                self._init_undetected_driver()
            else:
                self._init_standard_driver()
        else:
            raise ValueError(
                f"Unsupported browser: {self._browser_type}. Use 'chrome' or 'edge'."
            )

        logger.info(f"SeleniumCrawler started successfully with {self._browser_type}")

    async def stop(self) -> None:
        """Stop and cleanup the Selenium WebDriver."""
        if self._driver:
            try:
                self._driver.quit()
                logger.info("SeleniumCrawler driver quit successfully")
            except Exception as e:
                logger.warning(f"Error quitting driver: {e}")
            finally:
                self._driver = None

        # Cleanup temp profile if created
        if self._temp_profile and os.path.exists(self._temp_profile):
            try:
                import shutil

                shutil.rmtree(self._temp_profile)
                logger.debug(f"Cleaned up temp profile: {self._temp_profile}")
            except Exception as e:
                logger.warning(f"Error cleaning up temp profile: {e}")

        logger.info("SeleniumCrawler stopped successfully")

    def _init_undetected_driver(self) -> None:
        """Initialize undetected-chromedriver for maximum bot detection bypass."""
        logger.info("Initializing undetected-chromedriver")

        chrome_options = uc.ChromeOptions()

        # Apply base options
        self._apply_base_options(chrome_options)

        # Apply ultra stealth arguments if enabled
        if self.config.use_ultra_stealth:
            logger.info("Applying ultra stealth configuration...")
            for arg in ULTRA_STEALTH_ARGS:
                chrome_options.add_argument(arg)

            # Apply preferences (nested under "prefs")
            chrome_options.add_experimental_option("prefs", ULTRA_STEALTH_PREFS)

            # Note: excludeSwitches and useAutomationExtension not compatible with uc.ChromeOptions
            # They're handled by undetected-chromedriver itself
        else:
            # Standard stealth options
            if self.config.disable_dev_shm:
                chrome_options.add_argument("--disable-dev-shm-usage")
            if self.config.no_sandbox:
                chrome_options.add_argument("--no-sandbox")
            if self.config.disable_extensions:
                chrome_options.add_argument("--disable-extensions")
            if self.config.disable_gpu:
                chrome_options.add_argument("--disable-gpu")

        # Additional stealth options
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        # Note: excludeSwitches and useAutomationExtension are not compatible with uc.ChromeOptions
        # They're handled internally by undetected-chromedriver

        # User data directory
        if self.config.user_data_dir:
            chrome_options.add_argument(f"--user-data-dir={self.config.user_data_dir}")
        elif not self.config.headless:
            # Create temp profile for non-headless mode
            self._temp_profile = tempfile.mkdtemp(prefix="selenium_profile_")
            chrome_options.add_argument(f"--user-data-dir={self._temp_profile}")
            logger.info(f"Using temp profile: {self._temp_profile}")

        # Initialize undetected Chrome
        # Note: undetected-chromedriver handles driver management internally
        # We let it auto-download and manage the driver unless a path is specified
        try:
            if self.config.chrome_driver_path:
                # Use manually specified ChromeDriver path
                service = ChromeService(executable_path=self.config.chrome_driver_path)
                self._driver = uc.Chrome(options=chrome_options, service=service)
                logger.info(f"Using ChromeDriver at: {self.config.chrome_driver_path}")
            else:
                # Let undetected-chromedriver handle driver management automatically
                self._driver = uc.Chrome(options=chrome_options)
                logger.info("[OK] Undetected Chrome initialized (driver auto-managed)")
        except Exception as e:
            logger.error(f"Failed to initialize undetected Chrome: {e}")
            raise

        # Apply stealth enhancements
        self._apply_stealth_enhancements()

        # Set timeouts
        if self.config.load_timeout_seconds > 0:
            self._driver.set_page_load_timeout(self.config.load_timeout_seconds)

    def _init_standard_driver(self) -> None:
        """Initialize standard Selenium WebDriver."""
        logger.info("Initializing standard Selenium WebDriver")

        chrome_options = Options()

        # Apply base options
        self._apply_base_options(chrome_options)

        # Apply ultra stealth arguments if enabled
        if self.config.use_ultra_stealth:
            logger.info("Applying ultra stealth configuration...")
            for arg in ULTRA_STEALTH_ARGS:
                chrome_options.add_argument(arg)

            # Apply preferences (nested under "prefs")
            chrome_options.add_experimental_option("prefs", ULTRA_STEALTH_PREFS)

            # Apply other experimental options
            from crawler.enhanced_stealth import ULTRA_STEALTH_EXPERIMENTAL_OPTIONS

            for key, value in ULTRA_STEALTH_EXPERIMENTAL_OPTIONS.items():
                chrome_options.add_experimental_option(key, value)
        else:
            # Standard stealth options
            if self.config.disable_dev_shm:
                chrome_options.add_argument("--disable-dev-shm-usage")
            if self.config.no_sandbox:
                chrome_options.add_argument("--no-sandbox")
            if self.config.disable_extensions:
                chrome_options.add_argument("--disable-extensions")
            if self.config.disable_gpu:
                chrome_options.add_argument("--disable-gpu")

            # Stealth options
            if self.config.use_stealth_mode:
                chrome_options.add_argument(
                    "--disable-blink-features=AutomationControlled"
                )
                chrome_options.add_experimental_option(
                    "excludeSwitches", ["enable-automation"]
                )
                chrome_options.add_experimental_option("useAutomationExtension", False)

        # User data directory
        if self.config.user_data_dir:
            chrome_options.add_argument(f"--user-data-dir={self.config.user_data_dir}")
        elif not self.config.headless:
            self._temp_profile = tempfile.mkdtemp(prefix="selenium_profile_")
            chrome_options.add_argument(f"--user-data-dir={self._temp_profile}")
            logger.info(f"Using temp profile: {self._temp_profile}")

        # Chrome binary location
        if self.config.chrome_binary_location:
            chrome_options.binary_location = self.config.chrome_binary_location

        # Initialize Chrome
        try:
            if self.config.chrome_driver_path:
                # Use manually specified ChromeDriver path
                service = ChromeService(executable_path=self.config.chrome_driver_path)
                self._driver = webdriver.Chrome(options=chrome_options, service=service)
                logger.info(f"Using ChromeDriver at: {self.config.chrome_driver_path}")
            else:
                # Use Selenium Manager (recommended, auto-downloads matching driver)
                self._driver = webdriver.Chrome(options=chrome_options)
                logger.info("[OK] Standard Chrome initialized with Selenium Manager")
        except Exception as e:
            logger.error(f"Failed to initialize Chrome: {e}")
            raise

        # Apply stealth enhancements
        if self.config.use_stealth_mode:
            self._apply_stealth_enhancements()

        # Set timeouts
        if self.config.load_timeout_seconds > 0:
            self._driver.set_page_load_timeout(self.config.load_timeout_seconds)

    def _init_edge_driver(self) -> None:
        """Initialize Microsoft Edge WebDriver."""
        logger.info("Initializing Microsoft Edge WebDriver")

        edge_options = EdgeOptions()

        # Apply base options
        self._apply_base_options(edge_options)

        # Apply ultra stealth arguments if enabled
        if self.config.use_ultra_stealth:
            logger.info("Applying ultra stealth configuration...")
            for arg in ULTRA_STEALTH_ARGS:
                edge_options.add_argument(arg)

            # Apply preferences (nested under "prefs")
            edge_options.add_experimental_option("prefs", ULTRA_STEALTH_PREFS)

            # Apply other experimental options
            from crawler.enhanced_stealth import ULTRA_STEALTH_EXPERIMENTAL_OPTIONS

            for key, value in ULTRA_STEALTH_EXPERIMENTAL_OPTIONS.items():
                edge_options.add_experimental_option(key, value)
        else:
            # Standard stealth options
            if self.config.disable_dev_shm:
                edge_options.add_argument("--disable-dev-shm-usage")
            if self.config.no_sandbox:
                edge_options.add_argument("--no-sandbox")
            if self.config.disable_extensions:
                edge_options.add_argument("--disable-extensions")
            if self.config.disable_gpu:
                edge_options.add_argument("--disable-gpu")

            # Stealth options
            if self.config.use_stealth_mode:
                edge_options.add_argument(
                    "--disable-blink-features=AutomationControlled"
                )
                edge_options.add_experimental_option(
                    "excludeSwitches", ["enable-automation"]
                )
                edge_options.add_experimental_option("useAutomationExtension", False)

        # User data directory
        if self.config.user_data_dir:
            edge_options.add_argument(f"--user-data-dir={self.config.user_data_dir}")
        elif not self.config.headless:
            self._temp_profile = tempfile.mkdtemp(prefix="edge_profile_")
            edge_options.add_argument(f"--user-data-dir={self._temp_profile}")
            logger.info(f"Using temp profile: {self._temp_profile}")

        # Edge binary location
        if self.config.edge_binary_location:
            edge_options.binary_location = self.config.edge_binary_location

        # Initialize Edge
        try:
            if self.config.edge_driver_path:
                # Use manually specified EdgeDriver path
                service = EdgeService(executable_path=self.config.edge_driver_path)
                self._driver = webdriver.Edge(options=edge_options, service=service)
                logger.info(f"Using EdgeDriver at: {self.config.edge_driver_path}")
            else:
                # Use Selenium Manager (recommended, auto-downloads matching driver)
                self._driver = webdriver.Edge(options=edge_options)
                logger.info("[OK] Microsoft Edge initialized with Selenium Manager")
        except Exception as e:
            logger.error(f"Failed to initialize Microsoft Edge WebDriver: {e}")
            logger.error("")
            logger.error("Common causes:")
            logger.error("  1. Microsoft Edge browser is not installed")
            logger.error("  2. EdgeDriver version doesn't match Edge browser version")
            logger.error("  3. Edge browser is installed in non-standard location")
            logger.error("")
            logger.error("Solutions:")
            logger.error("  - Install Microsoft Edge: https://www.microsoft.com/edge")
            logger.error(
                "  - Specify Edge location: SeleniumCrawlerConfig(edge_binary_location='path/to/msedge.exe')"
            )
            logger.error(
                "  - Use Chrome instead: SeleniumCrawlerConfig(selenium_browser='chrome')"
            )
            logger.error("")
            raise RuntimeError(
                f"Failed to initialize Microsoft Edge: {e}. "
                "Make sure Microsoft Edge browser is installed. "
                "Alternatively, use Chrome with selenium_browser='chrome'"
            ) from e

        # Apply stealth enhancements
        if self.config.use_stealth_mode:
            self._apply_stealth_enhancements()

        # Set timeouts
        if self.config.load_timeout_seconds > 0:
            self._driver.set_page_load_timeout(self.config.load_timeout_seconds)

    def _apply_base_options(
        self, options: Union[uc.ChromeOptions, Options, EdgeOptions]
    ) -> None:
        """Apply base configuration options to browser options (Chrome/Edge)."""
        # Headless mode
        if self.config.headless:
            options.add_argument("--headless=new")

        # Viewport size
        options.add_argument(
            f"--window-size={self.config.viewport_width}x{self.config.viewport_height}"
        )

        # User agent
        if self.config.user_agent:
            options.add_argument(f"--user-agent={self.config.user_agent}")

        # Log level
        options.add_argument("log-level=3")

        # Start maximized
        options.add_argument("--start-maximized")

    def _apply_stealth_enhancements(self) -> None:
        """Apply stealth enhancements to bypass bot detection."""
        if not self._driver:
            return

        try:
            # Use ultra stealth mode if enabled
            if self.config.use_ultra_stealth:
                logger.info(
                    "[ULTRA STEALTH] Applying advanced anti-detection patches..."
                )
                success = apply_ultra_stealth(self._driver, self._browser_type)
                if success:
                    logger.info("[OK] Ultra stealth patches applied successfully")
                else:
                    logger.warning(
                        "[WARNING] Ultra stealth patches failed, falling back to standard stealth"
                    )
                    self._apply_standard_stealth()
            else:
                self._apply_standard_stealth()

        except Exception as e:
            logger.warning(f"Error applying stealth enhancements: {e}")

    def _apply_standard_stealth(self) -> None:
        """Apply standard stealth enhancements."""
        if not self._driver:
            return

        # Inject stealth.min.js via CDP
        if self._stealth_js:
            self._driver.execute_cdp_cmd(
                "Page.addScriptToEvaluateOnNewDocument",
                {"source": self._stealth_js},
            )
            logger.info("[OK] Injected stealth.min.js via CDP")

        # Get current user agent
        current_ua = self._driver.execute_script("return navigator.userAgent;")

        # Set new user agent (browser-specific default)
        if self.config.user_agent:
            new_ua = self.config.user_agent
        elif self._browser_type == "edge":
            new_ua = DEFAULT_EDGE_USER_AGENT
        else:
            new_ua = DEFAULT_CHROME_USER_AGENT

        if "HeadlessChrome" in current_ua:
            new_ua = current_ua.replace("HeadlessChrome", "Chrome")

        logger.info(f"User agent: {current_ua[:50]}... -> {new_ua[:50]}...")

        # Override user agent via CDP
        self._driver.execute_cdp_cmd(
            "Network.setUserAgentOverride",
            {"userAgent": new_ua},
        )

        # Hide webdriver property
        self._driver.execute_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        # Verify
        final_ua = self._driver.execute_script("return navigator.userAgent;")
        logger.info(f"Final user agent: {final_ua[:80]}...")

    async def crawl(self, url: str, **kwargs) -> CrawlResultBase:
        """
        Crawl a single URL using Selenium.

        Args:
            url: URL to crawl
            **kwargs: Additional crawl options

        Returns:
            CrawlResultBase with crawl results
        """
        if not self._driver:
            raise RuntimeError("Crawler not started. Call start() first.")

        logger.info(f"Crawling URL: {url}")
        start_time = time.time()

        try:
            # Navigate to URL
            self._driver.get(url)

            # Wait for page load (optional wait for specific element)
            wait_for_selector = kwargs.get("wait_for_selector")
            if wait_for_selector:
                await self._wait_for_element(wait_for_selector)

            # Small delay to ensure JavaScript execution
            await asyncio.sleep(kwargs.get("wait_after_load", 1.0))

            # Get page source
            html = self._driver.page_source
            current_url = self._driver.current_url

            # Extract metadata
            title = self._driver.title
            status_code = 200  # Selenium doesn't provide status codes directly

            # Process HTML
            soup = BeautifulSoup(html, "html.parser")

            # Extract text
            text = soup.get_text(separator=" ", strip=True)

            # Convert to markdown
            markdown = md(str(soup), heading_style="ATX")

            # Extract links
            links = None
            if self.config.extract_links:
                links = self._extract_links(soup, current_url)

            # Extract media
            media = None
            if self.config.extract_images:
                media = self._extract_media(soup, current_url)

            # Take screenshot if requested
            screenshot = None
            if kwargs.get("screenshot", False):
                screenshot = self._driver.get_screenshot_as_png()

            # Build metadata
            metadata = {
                "crawl_time_seconds": time.time() - start_time,
                "final_url": current_url,
                "page_title": title,
                "html_length": len(html),
                "text_length": len(text),
                "markdown_length": len(markdown),
            }

            logger.info(
                f"Successfully crawled {url} in {metadata['crawl_time_seconds']:.2f}s "
                f"(HTML: {len(html)} chars, Markdown: {len(markdown)} chars)"
            )

            return CrawlResultBase(
                url=url,
                success=True,
                html=html,
                markdown=markdown,
                text=text,
                title=title,
                status_code=status_code,
                screenshot=screenshot,
                media=media,
                links=links,
                metadata=metadata,
            )

        except TimeoutException as e:
            error_msg = f"Timeout while crawling {url}: {str(e)}"
            logger.error(error_msg)

            # Take screenshot on error if configured
            screenshot = None
            if self.config.screenshot_on_error:
                try:
                    screenshot = self._driver.get_screenshot_as_png()
                except Exception:
                    pass

            return CrawlResultBase(
                url=url,
                success=False,
                error_message=error_msg,
                screenshot=screenshot,
                metadata={
                    "error_type": "timeout",
                    "crawl_time_seconds": time.time() - start_time,
                },
            )

        except WebDriverException as e:
            error_msg = f"WebDriver error while crawling {url}: {str(e)}"
            logger.error(error_msg)

            return CrawlResultBase(
                url=url,
                success=False,
                error_message=error_msg,
                metadata={
                    "error_type": "webdriver_error",
                    "crawl_time_seconds": time.time() - start_time,
                },
            )

        except Exception as e:
            error_msg = f"Error crawling {url}: {str(e)}"
            logger.error(error_msg)

            return CrawlResultBase(
                url=url,
                success=False,
                error_message=error_msg,
                metadata={
                    "error_type": "unknown",
                    "crawl_time_seconds": time.time() - start_time,
                },
            )

    async def crawl_multiple(
        self, urls: list[str], max_concurrent: int = 5
    ) -> list[CrawlResultBase]:
        """
        Crawl multiple URLs sequentially (Selenium doesn't support true concurrency).

        Args:
            urls: List of URLs to crawl
            max_concurrent: Ignored for Selenium (always sequential)

        Returns:
            List of CrawlResultBase objects
        """
        logger.info(f"Crawling {len(urls)} URLs sequentially with Selenium")

        results = []
        for i, url in enumerate(urls, 1):
            logger.info(f"Crawling {i}/{len(urls)}: {url}")
            result = await self.crawl(url)
            results.append(result)

            # Small delay between requests
            if i < len(urls):
                await asyncio.sleep(random.uniform(0.5, 1.5))

        return results

    async def _wait_for_element(
        self, selector: str, timeout: Optional[int] = None
    ) -> WebElement:
        """Wait for element to appear using CSS selector."""
        if not self._driver:
            raise RuntimeError("Driver not initialized")

        wait_timeout = timeout or self.config.element_wait_timeout

        try:
            element = WebDriverWait(self._driver, wait_timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, selector))
            )
            logger.debug(f"Element found: {selector}")
            return element
        except TimeoutException:
            logger.warning(f"Timeout waiting for element: {selector}")
            raise

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> dict[str, Any]:
        """Extract all links from the page."""
        from urllib.parse import urljoin

        internal_links = []
        external_links = []

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]  # type: ignore
            # Convert href to string (BeautifulSoup returns _AttributeValue type)
            href_str = str(href) if href else ""
            if not href_str:
                continue

            absolute_url = urljoin(base_url, href_str)

            link_data = {"url": absolute_url, "text": a_tag.get_text(strip=True)}

            if absolute_url.startswith(base_url):
                internal_links.append(link_data)
            else:
                external_links.append(link_data)

        return {
            "internal": internal_links[:100],  # Limit to avoid huge payloads
            "external": external_links[:100],
        }

    def _extract_media(self, soup: BeautifulSoup, base_url: str) -> dict[str, Any]:
        """Extract media (images, videos) from the page."""
        from urllib.parse import urljoin

        images = []
        for img_tag in soup.find_all("img", src=True):
            src = img_tag["src"]  # type: ignore
            # Convert src to string (BeautifulSoup returns _AttributeValue type)
            src_str = str(src) if src else ""
            if src_str:
                images.append(
                    {
                        "url": urljoin(base_url, src_str),
                        "alt": str(img_tag.get("alt", "")),  # type: ignore
                    }
                )

        videos = []
        for video_tag in soup.find_all("video", src=True):
            src = video_tag["src"]  # type: ignore
            # Convert src to string (BeautifulSoup returns _AttributeValue type)
            src_str = str(src) if src else ""
            if src_str:
                videos.append({"url": urljoin(base_url, src_str)})

        return {
            "images": images[:50],  # Limit to avoid huge payloads
            "videos": videos[:20],
        }

    # Context manager support
    async def __aenter__(self) -> "SeleniumCrawler":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.stop()
