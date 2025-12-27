"""
Service Name Constants

Centralized constants for all service names used throughout the application.
This prevents magic strings and makes refactoring easier.

Usage:
    from services.service_names import SERVICE_TEXT_EMBED

    # Register service
    manager.register_service(SERVICE_TEXT_EMBED, TextEmbedService)

    # Get service
    crawler = manager.get_service(SERVICE_TEXT_EMBED)

    # Submit task
    task_id = await manager.submit_task(SERVICE_TEXT_EMBED, task)
"""

# Service name constants
SERVICE_WEBSITE_BROWSE = "website_browse"
"""Service for browsing the website"""

# Export all service names as a list for convenience
ALL_SERVICE_NAMES = [
    SERVICE_WEBSITE_BROWSE,
]

__all__ = [
    "SERVICE_WEBSITE_BROWSE",
    "ALL_SERVICE_NAMES",
]
