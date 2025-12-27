"""
Website Browse Tool

A tool for browsing websites using the WebsiteBrowseService.
Designed for use with AI agents to fetch and extract web content.

Usage:
    from tools.tool_website_browse import WebsiteBrowseTool

    tool = WebsiteBrowseTool()

    # Get tool definition for OpenAI function calling
    definition = tool.get_tool_definition()

    # Run the tool (async)
    result = await tool.run_tool_async('{"url": "https://example.com"}')
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from tools.base_tool import AIToolBase
from utilities import logger


class WebsiteBrowseTool(AIToolBase):
    """
    Tool for browsing websites and extracting content.

    This tool wraps the WebsiteBrowseService to provide web browsing
    capabilities to AI agents. It supports multiple crawler backends
    (Crawl4AI, Selenium) with automatic retry and fallback.
    """

    name: str = "browse_website"
    description: str = """Browse a website and extract its content.

This tool fetches a webpage and returns its content in markdown format.
It uses advanced web crawling with stealth mode to avoid bot detection.

Use this tool when you need to:
- Fetch content from a webpage
- Extract text, links, or media from a website
- Research information from web sources

The tool automatically retries with different crawler backends if the initial attempt fails."""

    parameters: dict[str, Any] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL of the website to browse. Must be a valid HTTP/HTTPS URL.",
            },
            "crawler": {
                "type": "string",
                "enum": ["crawl4ai", "selenium"],
                "description": "The crawler backend to use. 'crawl4ai' (default) uses Playwright-based crawling, 'selenium' uses Selenium WebDriver.",
                "default": "crawl4ai",
            },
            "retry_times": {
                "type": "integer",
                "description": "Number of retry attempts if crawling fails. Default is 3.",
                "default": 3,
                "minimum": 0,
                "maximum": 10,
            },
            "retry_strategy": {
                "type": "string",
                "enum": ["same_crawler", "switch_crawler"],
                "description": "Strategy for retries. 'same_crawler' retries with the same backend, 'switch_crawler' (default) switches to the alternate crawler on failure.",
                "default": "switch_crawler",
            },
            "headless": {
                "type": "boolean",
                "description": "Run the browser in headless mode (no visible window). Default is true.",
                "default": True,
            },
            "use_stealth_mode": {
                "type": "boolean",
                "description": "Enable stealth mode to avoid bot detection. Default is true.",
                "default": True,
            },
            "timeout_ms": {
                "type": "integer",
                "description": "Page load timeout in milliseconds. Default is 90000 (90 seconds).",
                "default": 90000,
                "minimum": 5000,
                "maximum": 300000,
            },
            "include_screenshot": {
                "type": "boolean",
                "description": "Capture a screenshot of the page. Default is false.",
                "default": False,
            },
            "output_format": {
                "type": "string",
                "enum": ["markdown", "text", "html", "full"],
                "description": "Format of the returned content. 'markdown' (default) returns clean markdown, 'text' returns plain text, 'html' returns raw HTML, 'full' returns all available data as JSON.",
                "default": "markdown",
            },
        },
        "required": ["url"],
        "additionalProperties": False,
    }

    strict: bool = True

    def _run(self, params: str) -> str:
        """
        Synchronous execution - runs the async version in an event loop.

        Args:
            params: JSON string with tool parameters

        Returns:
            String result from browsing the website
        """
        return asyncio.run(self._run_async(params))

    async def _run_async(self, params: str) -> str:
        """
        Browse a website using the WebsiteBrowseService.

        Args:
            params: JSON string with tool parameters

        Returns:
            String result containing the website content
        """
        # Parse parameters
        try:
            args = json.loads(params)
        except json.JSONDecodeError as e:
            return f"Error: Invalid JSON parameters: {e}"

        url = args.get("url")
        if not url:
            return "Error: 'url' parameter is required"

        # Validate URL
        if not url.startswith(("http://", "https://")):
            return (
                f"Error: Invalid URL '{url}'. URL must start with http:// or https://"
            )

        # Extract parameters with defaults
        crawler = args.get("crawler", "crawl4ai")
        retry_times = args.get("retry_times", 3)
        retry_strategy = args.get("retry_strategy", "switch_crawler")
        headless = args.get("headless", True)
        use_stealth_mode = args.get("use_stealth_mode", True)
        timeout_ms = args.get("timeout_ms", 90000)
        include_screenshot = args.get("include_screenshot", False)
        output_format = args.get("output_format", "markdown")

        logger.info(
            f"[WebsiteBrowseTool] Browsing {url} with crawler={crawler}, "
            f"retries={retry_times}, strategy={retry_strategy}"
        )

        try:
            # Import service components
            from services.service_manager import ServiceManager
            from services.service_names import SERVICE_WEBSITE_BROWSE
            from services.website_browse_service import (
                CrawlerType,
                RetryStrategy,
                WebsiteBrowseTask,
                WebsiteBrowseTaskConfig,
            )

            # Map string parameters to enums
            crawler_type = CrawlerType(crawler)
            retry_strat = RetryStrategy(retry_strategy)

            # Create task configuration
            config = WebsiteBrowseTaskConfig(
                url=url,
                crawler_type=crawler_type,
                retry_times=retry_times,
                retry_strategy=retry_strat,
                headless=headless,
                use_stealth_mode=use_stealth_mode,
                page_timeout=timeout_ms,
                screenshot_enabled=include_screenshot,
            )

            # Get service and submit task
            manager = ServiceManager()
            manager.get_service(SERVICE_WEBSITE_BROWSE)

            task = WebsiteBrowseTask(
                service_name=SERVICE_WEBSITE_BROWSE,
                config=config,
            )

            # Submit and wait for completion
            task_id = await manager.submit_task(SERVICE_WEBSITE_BROWSE, task)

            # Wait with timeout slightly longer than page timeout
            wait_timeout = (timeout_ms / 1000) + 60
            await manager.wait_for_task(task_id, timeout=wait_timeout)

            # Get result from task
            if not task.browse_result:
                return "Error: No result returned from browse task"

            result = task.browse_result

            if not result.success:
                return f"Error: Failed to browse {url}. {result.error_message}"

            # Format output based on requested format
            return self._format_result(result, output_format)

        except asyncio.TimeoutError:
            return (
                f"Error: Timeout while browsing {url}. The page took too long to load."
            )
        except Exception as e:
            logger.error(f"[WebsiteBrowseTool] Error browsing {url}: {e}")
            return f"Error: Failed to browse {url}. {str(e)}"

    def _format_result(self, result, output_format: str) -> str:
        """
        Format the browse result based on the requested format.

        Args:
            result: WebsiteBrowseResult object
            output_format: Desired output format

        Returns:
            Formatted string
        """
        if not result.crawl_result:
            return f"Successfully browsed {result.url} but no content was extracted."

        crawl = result.crawl_result

        if output_format == "markdown":
            title = crawl.title or "Untitled"
            markdown = crawl.markdown or crawl.text or "No content extracted"
            return f"# {title}\n\nURL: {result.url}\n\n{markdown}"

        elif output_format == "text":
            return crawl.text or crawl.markdown or "No text content extracted"

        elif output_format == "html":
            return crawl.html or "No HTML content extracted"

        elif output_format == "full":
            # Return comprehensive JSON with all data
            data = {
                "success": result.success,
                "url": result.url,
                "crawler_used": result.crawler_used.value,
                "attempt_number": result.attempt_number,
                "title": crawl.title,
                "markdown": crawl.markdown,
                "text": crawl.text,
                "links": crawl.links,
                "media": crawl.media,
                "metadata": crawl.metadata,
            }
            return json.dumps(data, indent=2, default=str)

        else:
            # Default to markdown
            return crawl.markdown or crawl.text or "No content extracted"

    def use_cached_result(self) -> bool:
        """
        Whether to cache results for identical parameters.

        Returns False because web content may change between requests.
        """
        return False


# Convenience function to create the tool
def create_website_browse_tool() -> WebsiteBrowseTool:
    """Create and return a WebsiteBrowseTool instance."""
    return WebsiteBrowseTool()


__all__ = [
    "WebsiteBrowseTool",
    "create_website_browse_tool",
]
