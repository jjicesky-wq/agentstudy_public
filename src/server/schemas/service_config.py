"""
Service Configuration Management Schemas

Schemas for managing user and service-specific configurations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from db.constants import DatabaseEntryState


class ServiceConfigInfo(BaseModel):
    """Internal representation of a service configuration"""

    config_id: Optional[int] = Field(None, description="Database ID")
    user_id: int = Field(-1, description="User ID (or -1 for global config)")
    service_name: str = Field(..., description="Name of the service")
    config_key: str = Field(..., description="Configuration key")
    config_value: str = Field(..., description="Configuration value (stored as string)")
    config_type: str = Field(
        "string", description="Type: string, int, float, bool, json"
    )
    description: Optional[str] = Field(None, description="Description of this config")
    is_secret: bool = Field(False, description="Whether this is a secret value")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")
    state: int = Field(DatabaseEntryState.OK, description="Entry state")

    class Config:
        from_attributes = True


class ServiceConfigCreateRequest(BaseModel):
    """Request for creating/updating a service configuration"""

    user_id: int = Field(..., description="User ID")
    service_name: str = Field(..., description="Service name")
    config_key: str = Field(..., description="Configuration key")
    config_value: str = Field(..., description="Configuration value")
    config_type: str = Field(
        "string", description="Type: string, int, float, bool, json"
    )
    description: Optional[str] = Field(None, description="Description")
    is_secret: bool = Field(False, description="Is this a secret value?")


class ServiceConfigUpdateRequest(BaseModel):
    """Request for updating a service configuration"""

    config_value: str = Field(..., description="New configuration value")
    config_type: Optional[str] = Field(
        None, description="Type: string, int, float, bool, json"
    )
    description: Optional[str] = Field(None, description="Description")
    is_secret: Optional[bool] = Field(None, description="Is this a secret value?")


class ServiceConfigGetRequest(BaseModel):
    """Request for getting a service configuration"""

    user_id: int = Field(..., description="User ID")
    service_name: str = Field(..., description="Service name")
    config_key: str = Field(..., description="Configuration key")


class ServiceConfigListRequest(BaseModel):
    """Request for listing service configurations"""

    user_id: int = Field(..., description="User ID")
    service_name: Optional[str] = Field(
        None, description="Service name (if None, get all services)"
    )
    skip: int = Field(0, description="Number of records to skip")
    limit: int = Field(100, description="Maximum number of records to return")


class ServiceConfigDeleteRequest(BaseModel):
    """Request for deleting a service configuration"""

    user_id: int = Field(..., description="User ID")
    service_name: str = Field(..., description="Service name")
    config_key: str = Field(..., description="Configuration key")


class ServiceConfigResponse(BaseModel):
    """Response for service configuration operations"""

    success: bool = Field(..., description="Whether operation succeeded")
    message: str = Field(..., description="Response message")
    config: Optional[ServiceConfigInfo] = Field(None, description="Configuration data")


class ServiceConfigListResponse(BaseModel):
    """Response for listing service configurations"""

    success: bool = Field(..., description="Whether operation succeeded")
    message: str = Field(..., description="Response message")
    configs: list[ServiceConfigInfo] = Field(
        default_factory=list, description="List of configurations"
    )
    total_count: int = Field(0, description="Total number of configurations")


class ServiceConfigDeleteResponse(BaseModel):
    """Response for deleting a service configuration"""

    success: bool = Field(..., description="Whether deletion succeeded")
    message: str = Field(..., description="Response message")
    config_id: Optional[int] = Field(None, description="ID of deleted configuration")
