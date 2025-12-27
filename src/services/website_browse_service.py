"""
Website Browse Service

A service for browsing websites using various crawler backends (Crawl4AI, Selenium).
Supports configurable retry strategies with automatic fallback between crawlers.

Usage:
    from services.service_names import SERVICE_WEBSITE_BROWSE
    from services.website_browse_service import (
        WebsiteBrowseService,
        WebsiteBrowseTask,
        WebsiteBrowseTaskConfig,
    )

    # Create and register service
    manager = ServiceManager()
    service = manager.get_service(SERVICE_WEBSITE_BROWSE)

    # Submit a browse task
    config = WebsiteBrowseTaskConfig(
        url="https://example.com",
        crawler_type="crawl4ai",
        retry_times=3,
        retry_strategy="switch_crawler",
    )
    task = WebsiteBrowseTask(service_name=SERVICE_WEBSITE_BROWSE, config=config)
    task_id = await manager.submit_task(SERVICE_WEBSITE_BROWSE, task)
    result = await manager.wait_for_task(task_id)
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field

from crawler.base_crawler import BaseCrawler, CrawlResultBase
from services.base_service import AsyncBaseTask, BaseService, BaseTask, BaseTaskConfig
from services.service_names import SERVICE_WEBSITE_BROWSE
from utilities import logger

# =============================================================================
# Enums
# =============================================================================


class CrawlerType(str, Enum):
    """Supported crawler types."""

    CRAWL4AI = "crawl4ai"
    SELENIUM = "selenium"


class RetryStrategy(str, Enum):
    """Retry strategies for failed crawls."""

    SAME_CRAWLER = "same_crawler"
    """Retry with the same crawler."""

    SWITCH_CRAWLER = "switch_crawler"
    """Switch to the other crawler on retry."""


# =============================================================================
# Task Configuration
# =============================================================================


class WebsiteBrowseTaskConfig(BaseTaskConfig):
    """
    Configuration for WebsiteBrowseTask.

    Attributes:
        url: The URL to browse/crawl.
        crawler_type: Which crawler to use (crawl4ai or selenium).
        retry_times: Number of retry attempts on failure.
        retry_strategy: Strategy for retries (same_crawler or switch_crawler).
        headless: Run browser in headless mode.
        use_stealth_mode: Enable stealth mode to avoid bot detection.
        page_timeout: Page load timeout in milliseconds.
        screenshot_enabled: Capture a screenshot of the page.
    """

    url: str = Field(..., description="The URL to browse/crawl")
    crawler_type: CrawlerType = Field(
        default=CrawlerType.CRAWL4AI, description="Which crawler to use"
    )
    retry_times: int = Field(default=3, ge=0, description="Number of retry attempts")
    retry_strategy: RetryStrategy = Field(
        default=RetryStrategy.SWITCH_CRAWLER,
        description="Strategy for retries",
    )
    headless: bool = Field(default=True, description="Run browser in headless mode")
    use_stealth_mode: bool = Field(
        default=True, description="Enable stealth mode to avoid bot detection"
    )
    page_timeout: int = Field(
        default=90000, description="Page load timeout in milliseconds"
    )
    screenshot_enabled: bool = Field(
        default=False, description="Capture a screenshot of the page"
    )


# =============================================================================
# Task Result
# =============================================================================


class WebsiteBrowseResult:
    """
    Result of a website browse task.

    Contains the crawl result along with metadata about the crawl attempt.
    """

    def __init__(
        self,
        success: bool,
        url: str,
        crawler_used: CrawlerType,
        attempt_number: int,
        crawl_result: Optional[CrawlResultBase] = None,
        error_message: Optional[str] = None,
    ):
        self.success = success
        self.url = url
        self.crawler_used = crawler_used
        self.attempt_number = attempt_number
        self.crawl_result = crawl_result
        self.error_message = error_message

    def to_dict(self) -> dict:
        """Convert result to dictionary for serialization."""
        result = {
            "success": self.success,
            "url": self.url,
            "crawler_used": self.crawler_used.value,
            "attempt_number": self.attempt_number,
            "error_message": self.error_message,
        }
        if self.crawl_result:
            result["content"] = {
                "html": self.crawl_result.html,
                "markdown": self.crawl_result.markdown,
                "text": self.crawl_result.text,
                "title": self.crawl_result.title,
                "links": self.crawl_result.links,
                "media": self.crawl_result.media,
                "metadata": self.crawl_result.metadata,
            }
        return result


# =============================================================================
# Task Implementation
# =============================================================================


class WebsiteBrowseTask(AsyncBaseTask):
    """
    Async task for browsing a website using configurable crawlers.

    Supports automatic retry with fallback between different crawler backends.
    """

    browse_result: Optional[WebsiteBrowseResult] = None

    def __init__(
        self,
        service_name: str,
        config: WebsiteBrowseTaskConfig,
        task_id: Optional[str] = None,
        task_name: Optional[str] = None,
    ):
        super().__init__(
            service_name=service_name,
            config=config,
            task_id=task_id,
            task_name=task_name or "WebsiteBrowseTask",
        )
        self.url = config.url
        self.crawler_type = config.crawler_type
        self.retry_times = config.retry_times
        self.retry_strategy = config.retry_strategy
        self.headless = config.headless
        self.use_stealth_mode = config.use_stealth_mode
        self.page_timeout = config.page_timeout
        self.screenshot_enabled = config.screenshot_enabled

    def _get_alternate_crawler(self, current: CrawlerType) -> CrawlerType:
        """Get the alternate crawler type for retry strategy."""
        if current == CrawlerType.CRAWL4AI:
            return CrawlerType.SELENIUM
        return CrawlerType.CRAWL4AI

    async def _create_crawler(self, crawler_type: CrawlerType) -> BaseCrawler:
        """Create a crawler instance based on type."""
        if crawler_type == CrawlerType.CRAWL4AI:
            from crawler.crawl4ai_crawler import Crawl4AICrawler, Crawl4AICrawlerConfig

            config = Crawl4AICrawlerConfig(
                headless=self.headless,
                use_stealth_mode=self.use_stealth_mode,
                page_timeout=self.page_timeout,
                screenshot_enabled=self.screenshot_enabled,
            )
            return Crawl4AICrawler(config=config)
        else:
            from crawler.selenium_crawler import SeleniumCrawler, SeleniumCrawlerConfig

            config = SeleniumCrawlerConfig(
                headless=self.headless,
                use_stealth_mode=self.use_stealth_mode,
                page_timeout=self.page_timeout,
                screenshot_enabled=self.screenshot_enabled,
            )
            return SeleniumCrawler(config=config)

    async def _crawl_with_retry(self) -> WebsiteBrowseResult:
        """Execute crawl with retry logic."""
        current_crawler_type = self.crawler_type
        last_error: Optional[str] = None

        for attempt in range(self.retry_times + 1):
            if self.terminated():
                return WebsiteBrowseResult(
                    success=False,
                    url=self.url,
                    crawler_used=current_crawler_type,
                    attempt_number=attempt + 1,
                    error_message="Task was cancelled",
                )

            self.report_progress(
                int((attempt / (self.retry_times + 1)) * 80),
                f"Attempt {attempt + 1}/{self.retry_times + 1} with {current_crawler_type.value}",
            )

            logger.info(
                f"[{self.task_id}] Crawl attempt {attempt + 1}/{self.retry_times + 1} "
                f"using {current_crawler_type.value} for {self.url}"
            )

            crawler: Optional[BaseCrawler] = None
            try:
                crawler = await self._create_crawler(current_crawler_type)
                await crawler.start()

                result = await crawler.crawl(
                    self.url,
                    screenshot=self.screenshot_enabled,
                )

                if result.success:
                    logger.info(
                        f"[{self.task_id}] Successfully crawled {self.url} "
                        f"on attempt {attempt + 1} using {current_crawler_type.value}"
                    )
                    return WebsiteBrowseResult(
                        success=True,
                        url=self.url,
                        crawler_used=current_crawler_type,
                        attempt_number=attempt + 1,
                        crawl_result=result,
                    )
                else:
                    last_error = result.error_message or "Unknown crawl error"
                    logger.warning(
                        f"[{self.task_id}] Crawl failed on attempt {attempt + 1}: {last_error}"
                    )

            except Exception as e:
                last_error = str(e)
                logger.error(
                    f"[{self.task_id}] Exception on attempt {attempt + 1}: {last_error}"
                )
            finally:
                if crawler:
                    try:
                        await crawler.stop()
                    except Exception as e:
                        logger.warning(f"[{self.task_id}] Error stopping crawler: {e}")

            # Apply retry strategy for next attempt
            if attempt < self.retry_times:
                if self.retry_strategy == RetryStrategy.SWITCH_CRAWLER:
                    current_crawler_type = self._get_alternate_crawler(
                        current_crawler_type
                    )
                    logger.info(
                        f"[{self.task_id}] Switching to {current_crawler_type.value} for next attempt"
                    )

        # All attempts failed
        return WebsiteBrowseResult(
            success=False,
            url=self.url,
            crawler_used=current_crawler_type,
            attempt_number=self.retry_times + 1,
            error_message=f"All {self.retry_times + 1} attempts failed. Last error: {last_error}",
        )

    async def _run_async(self):
        """Execute the browse task."""
        logger.info(f"[{self.task_id}] Starting browse task for {self.url}")
        self.report_progress(0, f"Starting crawl of {self.url}")

        try:
            self.browse_result = await self._crawl_with_retry()

            self.report_progress(100, "Crawl complete")

            if self.browse_result.success:
                self.complete(
                    result=f"Successfully crawled {self.url} using {self.browse_result.crawler_used.value}"
                )
            else:
                self.fail(result=self.browse_result.error_message or "Crawl failed")

        except Exception as e:
            logger.error(f"[{self.task_id}] Browse task failed with exception: {e}")
            self.browse_result = WebsiteBrowseResult(
                success=False,
                url=self.url,
                crawler_used=self.crawler_type,
                attempt_number=0,
                error_message=str(e),
            )
            self.fail(result=str(e))

    def get_final_artifact(self) -> Optional[dict]:
        """Return the browse result as the final artifact."""
        if self.browse_result:
            return self.browse_result.to_dict()
        return None


# =============================================================================
# Service Implementation
# =============================================================================


class WebsiteBrowseService(BaseService):
    """
    Service for browsing websites using various crawler backends.

    This service runs in passive mode - tasks are manually queued via queue_task().
    It manages the execution of WebsiteBrowseTask instances.
    """

    def __init__(
        self,
        service_name: str = SERVICE_WEBSITE_BROWSE,
        max_thread_count: int = 3,
    ):
        """
        Initialize the WebsiteBrowseService.

        Args:
            service_name: Name of the service (defaults to SERVICE_WEBSITE_BROWSE)
            max_thread_count: Maximum concurrent browse tasks
        """
        super().__init__(
            service_name=service_name,
            single_thread_mode=False,
            passive_mode=True,  # Tasks are manually queued
            max_thread_count=max_thread_count,
            max_outstanding_tasks=max_thread_count * 2,
        )
        logger.info(
            f"WebsiteBrowseService initialized with max_thread_count={max_thread_count}"
        )

    def _query_tasks(self, max_count: int) -> list[BaseTask]:
        """
        Query for new tasks (not used in passive mode).

        Returns:
            Empty list (passive mode - tasks are manually queued)
        """
        return []


# =============================================================================
# Service Registration Helper
# =============================================================================


def register_website_browse_service():
    """
    Register the WebsiteBrowseService with the ServiceManager.

    This function is called during auto-registration to make the service
    available throughout the application.
    """
    from services.service_manager import ServiceManager

    manager = ServiceManager()

    # Use a factory function to enable lazy loading
    def create_website_browse_service() -> WebsiteBrowseService:
        return WebsiteBrowseService()

    try:
        manager.register_service(
            name=SERVICE_WEBSITE_BROWSE,
            factory=create_website_browse_service,
        )
        logger.info(f"Registered service: {SERVICE_WEBSITE_BROWSE}")
    except ValueError:
        # Service already registered
        pass


# Export all public classes and functions
__all__ = [
    "CrawlerType",
    "RetryStrategy",
    "WebsiteBrowseTaskConfig",
    "WebsiteBrowseResult",
    "WebsiteBrowseTask",
    "WebsiteBrowseService",
    "register_website_browse_service",
]
