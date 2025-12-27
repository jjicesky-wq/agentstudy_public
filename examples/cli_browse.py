#!/usr/bin/env python
"""
CLI tool for browsing websites using the WebsiteBrowseService.

Usage:
    python cli_browse.py <url> [options]

Examples:
    # Basic usage with default settings (crawl4ai)
    python cli_browse.py https://example.com

    # Use selenium crawler
    python cli_browse.py https://example.com --crawler selenium

    # Custom retry settings
    python cli_browse.py https://example.com --retries 5 --strategy switch_crawler

    # Non-headless mode (show browser)
    python cli_browse.py https://example.com --no-headless

    # Save output to file
    python cli_browse.py https://example.com --output result.json

    # Get markdown content
    python cli_browse.py https://example.com --format markdown
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from services.service_manager import ServiceManager
from services.service_names import SERVICE_WEBSITE_BROWSE
from services.website_browse_service import (
    CrawlerType,
    RetryStrategy,
    WebsiteBrowseTask,
    WebsiteBrowseTaskConfig,
)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Browse websites using Crawl4AI or Selenium crawlers",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s https://example.com
  %(prog)s https://example.com --crawler selenium
  %(prog)s https://example.com --retries 5 --strategy switch_crawler
  %(prog)s https://example.com --output result.json
  %(prog)s https://example.com --format markdown
        """,
    )

    parser.add_argument(
        "url",
        help="URL to browse/crawl",
    )

    parser.add_argument(
        "-c",
        "--crawler",
        choices=["crawl4ai", "selenium"],
        default="crawl4ai",
        help="Crawler to use (default: crawl4ai)",
    )

    parser.add_argument(
        "-r",
        "--retries",
        type=int,
        default=3,
        help="Number of retry attempts (default: 3)",
    )

    parser.add_argument(
        "-s",
        "--strategy",
        choices=["same_crawler", "switch_crawler"],
        default="switch_crawler",
        help="Retry strategy (default: switch_crawler)",
    )

    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in non-headless mode (show browser window)",
    )

    parser.add_argument(
        "--no-stealth",
        action="store_true",
        help="Disable stealth mode",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=90000,
        help="Page load timeout in milliseconds (default: 90000)",
    )

    parser.add_argument(
        "--screenshot",
        action="store_true",
        help="Capture a screenshot of the page",
    )

    parser.add_argument(
        "-o",
        "--output",
        type=str,
        help="Save result to JSON file",
    )

    parser.add_argument(
        "-f",
        "--format",
        choices=["json", "markdown", "text", "html"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    return parser.parse_args()


async def browse_website(args: argparse.Namespace) -> dict:
    """
    Browse a website using the WebsiteBrowseService.

    Args:
        args: Parsed command line arguments

    Returns:
        Dictionary with browse result
    """
    # Map string arguments to enums
    crawler_type = CrawlerType(args.crawler)
    retry_strategy = RetryStrategy(args.strategy)

    # Create task configuration
    config = WebsiteBrowseTaskConfig(
        url=args.url,
        crawler_type=crawler_type,
        retry_times=args.retries,
        retry_strategy=retry_strategy,
        headless=not args.no_headless,
        use_stealth_mode=not args.no_stealth,
        page_timeout=args.timeout,
        screenshot_enabled=args.screenshot,
    )

    if args.verbose:
        print(f"Configuration:")
        print(f"  URL: {args.url}")
        print(f"  Crawler: {crawler_type.value}")
        print(f"  Retries: {args.retries}")
        print(f"  Strategy: {retry_strategy.value}")
        print(f"  Headless: {not args.no_headless}")
        print(f"  Stealth: {not args.no_stealth}")
        print(f"  Timeout: {args.timeout}ms")
        print()

    # Get the service manager
    manager = ServiceManager()

    # Create and submit task
    task = WebsiteBrowseTask(
        service_name=SERVICE_WEBSITE_BROWSE,
        config=config,
    )

    if args.verbose:
        print(f"Starting browse task: {task.task_id}")

    # Submit task and wait for completion
    task_id = await manager.submit_task(SERVICE_WEBSITE_BROWSE, task)
    result = await manager.wait_for_task(task_id, timeout=args.timeout / 1000 + 60)

    # Get the browse result from the task
    if task.browse_result:
        return task.browse_result.to_dict()
    else:
        return {
            "success": False,
            "url": args.url,
            "error_message": result if isinstance(result, str) else "Unknown error",
        }


def format_output(result: dict, output_format: str) -> str:
    """
    Format the result based on the requested output format.

    Args:
        result: Browse result dictionary
        output_format: Desired output format

    Returns:
        Formatted string
    """
    if output_format == "json":
        # Remove binary screenshot data for JSON output
        result_copy = result.copy()
        if "content" in result_copy and result_copy["content"]:
            content = result_copy["content"].copy()
            if "screenshot" in content:
                content["screenshot"] = (
                    "<binary data>" if content["screenshot"] else None
                )
            result_copy["content"] = content
        return json.dumps(result_copy, indent=2, default=str)

    elif output_format == "markdown":
        if not result.get("success"):
            return f"# Error\n\n{result.get('error_message', 'Unknown error')}"

        content = result.get("content", {})
        markdown = content.get("markdown", "")
        title = content.get("title", "Untitled")

        return f"# {title}\n\n{markdown}"

    elif output_format == "text":
        if not result.get("success"):
            return f"Error: {result.get('error_message', 'Unknown error')}"

        content = result.get("content", {})
        return content.get("text", "")

    elif output_format == "html":
        if not result.get("success"):
            return f"<html><body><h1>Error</h1><p>{result.get('error_message', 'Unknown error')}</p></body></html>"

        content = result.get("content", {})
        return content.get("html", "")

    return str(result)


def main():
    """Main entry point for the CLI."""
    args = parse_args()

    print(f"Browsing: {args.url}")
    print(f"Using {args.crawler} crawler with {args.retries} retries ({args.strategy})")
    print()

    try:
        # Run the async browse function
        result = asyncio.run(browse_website(args))

        # Format output
        output = format_output(result, args.format)

        # Save to file or print
        if args.output:
            output_path = Path(args.output)
            output_path.write_text(output, encoding="utf-8")
            print(f"Result saved to: {args.output}")
        else:
            print(output)

        # Print summary
        if result.get("success"):
            print()
            print(
                f"Success! Crawled with {result.get('crawler_used')} on attempt {result.get('attempt_number')}"
            )
            if "content" in result and result["content"]:
                content = result["content"]
                print(f"  Title: {content.get('title', 'N/A')}")
                print(f"  HTML length: {len(content.get('html', '') or '')} chars")
                print(
                    f"  Markdown length: {len(content.get('markdown', '') or '')} chars"
                )
        else:
            print()
            print(f"Failed: {result.get('error_message', 'Unknown error')}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nOperation cancelled by user")
        sys.exit(130)
    except Exception as e:
        print(f"Error: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup: stop all services
        try:
            manager = ServiceManager()
            manager.stop_all_services()
        except Exception:
            pass


if __name__ == "__main__":
    main()
