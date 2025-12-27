"""
Service Configuration API Database Helper Functions

Provides database operation helpers for service configuration management.
All public helper functions start with db_helper_* prefix.

Architecture:
- db_helper_* functions: Database operations only (no business logic)
- db_operations.py: Low-level database queries
- api_* functions: Thin wrappers for API endpoints

Example:
    from backend.apis.service_config import db_helper_upsert_config
    from db.database import get_db_session

    with get_db_session() as session:
        response = db_helper_upsert_config(
            session=session,
            user_id=1,
            service_name="digest",
            config_key="default_voice",
            config_value="alloy",
            config_type="string"
        )
"""

from __future__ import annotations

import traceback
from typing import Optional

from sqlalchemy.orm import Session

from db import db_operations as db_ops
from db.database import get_db_session
from server.schemas.service_config import (
    ServiceConfigDeleteResponse,
    ServiceConfigInfo,
    ServiceConfigListResponse,
    ServiceConfigResponse,
)
from utilities import logger
from utilities.convert import pyd_from_obj

# =========================================================================
# Helper Functions (internal, start with _)
# =========================================================================


def _create_error_response(message: str) -> ServiceConfigResponse:
    """Create error response for config operations"""
    return ServiceConfigResponse(
        success=False,
        message=message,
        config=None,
    )


def _create_error_list_response(message: str) -> ServiceConfigListResponse:
    """Create error response for config listing"""
    return ServiceConfigListResponse(
        success=False,
        message=message,
        configs=[],
        total_count=0,
    )


def _create_error_delete_response(message: str) -> ServiceConfigDeleteResponse:
    """Create error response for config deletion"""
    return ServiceConfigDeleteResponse(
        success=False,
        message=message,
        config_id=None,
    )


# =========================================================================
# Database Helper Functions (public, start with db_helper_*)
# =========================================================================


def db_helper_upsert_config(
    session: Session,
    user_id: int,
    service_name: str,
    config_key: str,
    config_value: str,
    config_type: str = "string",
    description: Optional[str] = None,
    is_secret: bool = False,
) -> ServiceConfigResponse:
    """
    Create or update a service configuration

    Args:
        session: Database session
        user_id: User ID
        service_name: Name of the service
        config_key: Configuration key
        config_value: Configuration value (stored as string)
        config_type: Type of value (string, int, float, bool, json)
        description: Optional description
        is_secret: Whether this is a secret value

    Returns:
        ServiceConfigResponse with created/updated config
    """
    try:
        config = db_ops.upsert_service_config(
            session=session,
            user_id=user_id,
            service_name=service_name,
            config_key=config_key,
            config_value=config_value,
            config_type=config_type,
            description=description,
            is_secret=is_secret,
            commit=True,
        )

        config_info = pyd_from_obj(ServiceConfigInfo, config)

        return ServiceConfigResponse(
            success=True,
            message=f"Configuration '{config_key}' saved successfully",
            config=config_info,
        )

    except Exception as e:
        logger.error(f"Error upserting service config: {e}\n{traceback.format_exc()}")
        return _create_error_response(f"Failed to save configuration: {str(e)}")


def db_helper_get_config(
    session: Session,
    user_id: int,
    service_name: str,
    config_key: str,
) -> ServiceConfigResponse:
    """
    Get a specific service configuration

    Args:
        session: Database session
        user_id: User ID
        service_name: Name of the service
        config_key: Configuration key

    Returns:
        ServiceConfigResponse with config data
    """
    try:
        config = db_ops.get_service_config_by_key(
            session=session,
            user_id=user_id,
            service_name=service_name,
            config_key=config_key,
        )

        if not config:
            return _create_error_response(
                f"Configuration '{config_key}' not found for service '{service_name}'"
            )

        config_info = pyd_from_obj(ServiceConfigInfo, config)

        return ServiceConfigResponse(
            success=True,
            message="Configuration retrieved successfully",
            config=config_info,
        )

    except Exception as e:
        logger.error(f"Error getting service config: {e}\n{traceback.format_exc()}")
        return _create_error_response(f"Failed to get configuration: {str(e)}")


def db_helper_get_configs_by_service(
    session: Session,
    user_id: int,
    service_name: str,
) -> ServiceConfigListResponse:
    """
    Get all configurations for a specific service

    Args:
        session: Database session
        user_id: User ID
        service_name: Name of the service

    Returns:
        ServiceConfigListResponse with list of configs
    """
    try:
        configs = db_ops.get_service_configs_by_service(
            session=session,
            user_id=user_id,
            service_name=service_name,
        )

        config_infos = [pyd_from_obj(ServiceConfigInfo, c) for c in configs]

        return ServiceConfigListResponse(
            success=True,
            message=f"Found {len(configs)} configurations for service '{service_name}'",
            configs=config_infos,
            total_count=len(configs),
        )

    except Exception as e:
        logger.error(
            f"Error getting service configs by service: {e}\n{traceback.format_exc()}"
        )
        return _create_error_list_response(f"Failed to get configurations: {str(e)}")


def db_helper_get_configs_by_user(
    session: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
) -> ServiceConfigListResponse:
    """
    Get all configurations for a user

    Args:
        session: Database session
        user_id: User ID
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        ServiceConfigListResponse with list of configs
    """
    try:
        configs = db_ops.get_service_configs_by_user(
            session=session,
            user_id=user_id,
            skip=skip,
            limit=limit,
        )

        config_infos = [pyd_from_obj(ServiceConfigInfo, c) for c in configs]

        return ServiceConfigListResponse(
            success=True,
            message=f"Found {len(configs)} configurations",
            configs=config_infos,
            total_count=len(configs),
        )

    except Exception as e:
        logger.error(
            f"Error getting service configs by user: {e}\n{traceback.format_exc()}"
        )
        return _create_error_list_response(f"Failed to get configurations: {str(e)}")


def db_helper_delete_config(
    session: Session,
    user_id: int,
    service_name: str,
    config_key: str,
) -> ServiceConfigDeleteResponse:
    """
    Delete a service configuration

    Args:
        session: Database session
        user_id: User ID
        service_name: Name of the service
        config_key: Configuration key

    Returns:
        ServiceConfigDeleteResponse
    """
    try:
        # Get the config first to get its ID
        config = db_ops.get_service_config_by_key(
            session=session,
            user_id=user_id,
            service_name=service_name,
            config_key=config_key,
        )

        if not config:
            return _create_error_delete_response(
                f"Configuration '{config_key}' not found for service '{service_name}'"
            )

        config_id = config.config_id

        # Delete it
        db_ops.delete_service_config_by_key(
            session=session,
            user_id=user_id,
            service_name=service_name,
            config_key=config_key,
            commit=True,
        )

        return ServiceConfigDeleteResponse(
            success=True,
            message=f"Configuration '{config_key}' deleted successfully",
            config_id=config_id,  # type: ignore
        )

    except Exception as e:
        logger.error(f"Error deleting service config: {e}\n{traceback.format_exc()}")
        return _create_error_delete_response(
            f"Failed to delete configuration: {str(e)}"
        )


def db_helper_get_config_value(
    session: Session,
    user_id: int,
    service_name: str,
    config_key: str,
    default: Optional[str] = None,
) -> Optional[str]:
    """
    Get a configuration value directly (convenience function)

    Args:
        session: Database session
        user_id: User ID
        service_name: Name of the service
        config_key: Configuration key
        default: Default value if config not found

    Returns:
        Configuration value as string, or default if not found
    """
    try:
        config = db_ops.get_service_config_by_key(
            session=session,
            user_id=user_id,
            service_name=service_name,
            config_key=config_key,
        )

        if not config:
            return default

        return config.config_value  # type: ignore

    except Exception as e:
        logger.error(f"Error getting config value: {e}\n{traceback.format_exc()}")
        return default


# =========================================================================
# API Endpoint Functions (start with api_*)
# =========================================================================


def api_upsert_config(
    user_id: int,
    service_name: str,
    config_key: str,
    config_value: str,
    config_type: str = "string",
    description: Optional[str] = None,
    is_secret: bool = False,
) -> ServiceConfigResponse:
    """
    API endpoint for creating/updating a service configuration

    Args:
        user_id: User ID
        service_name: Name of the service
        config_key: Configuration key
        config_value: Configuration value
        config_type: Type of value (string, int, float, bool, json)
        description: Optional description
        is_secret: Whether this is a secret value

    Returns:
        ServiceConfigResponse
    """
    session_gen = get_db_session()
    session = next(session_gen)
    try:
        return db_helper_upsert_config(
            session=session,
            user_id=user_id,
            service_name=service_name,
            config_key=config_key,
            config_value=config_value,
            config_type=config_type,
            description=description,
            is_secret=is_secret,
        )
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


def api_get_config(
    user_id: int,
    service_name: str,
    config_key: str,
) -> ServiceConfigResponse:
    """
    API endpoint for getting a service configuration

    Args:
        user_id: User ID
        service_name: Name of the service
        config_key: Configuration key

    Returns:
        ServiceConfigResponse
    """
    session_gen = get_db_session()
    session = next(session_gen)
    try:
        return db_helper_get_config(
            session=session,
            user_id=user_id,
            service_name=service_name,
            config_key=config_key,
        )
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


def api_get_configs_by_service(
    user_id: int,
    service_name: str,
) -> ServiceConfigListResponse:
    """
    API endpoint for getting all configs for a service

    Args:
        user_id: User ID
        service_name: Name of the service

    Returns:
        ServiceConfigListResponse
    """
    session_gen = get_db_session()
    session = next(session_gen)
    try:
        return db_helper_get_configs_by_service(
            session=session,
            user_id=user_id,
            service_name=service_name,
        )
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


def api_get_configs_by_user(
    user_id: int,
    skip: int = 0,
    limit: int = 100,
) -> ServiceConfigListResponse:
    """
    API endpoint for getting all configs for a user

    Args:
        user_id: User ID
        skip: Number of records to skip
        limit: Maximum number of records to return

    Returns:
        ServiceConfigListResponse
    """
    session_gen = get_db_session()
    session = next(session_gen)
    try:
        return db_helper_get_configs_by_user(
            session=session,
            user_id=user_id,
            skip=skip,
            limit=limit,
        )
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass


def api_delete_config(
    user_id: int,
    service_name: str,
    config_key: str,
) -> ServiceConfigDeleteResponse:
    """
    API endpoint for deleting a service configuration

    Args:
        user_id: User ID
        service_name: Name of the service
        config_key: Configuration key

    Returns:
        ServiceConfigDeleteResponse
    """
    session_gen = get_db_session()
    session = next(session_gen)
    try:
        return db_helper_delete_config(
            session=session,
            user_id=user_id,
            service_name=service_name,
            config_key=config_key,
        )
    finally:
        try:
            next(session_gen)
        except StopIteration:
            pass
