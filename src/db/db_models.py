from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.types import DateTime

from db.constants import DatabaseEntryState
from db.database import Base
from utilities.time import get_utcnow

# User


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False)
    password_hashed = Column(String, default=None)
    create_timestamp = Column(DateTime(timezone=True), default=get_utcnow)
    multi_session_ok = Column(Boolean, default=True)
    is_active = Column(Boolean, default=True)
    register_ip_hashed = Column(String, default=None)
    last_login_ip_hashed = Column(String, default=None)
    last_login_timestamp = Column(DateTime(timezone=True), default=None)
    last_login_session = Column(Integer, default=0)
    role = Column(String, default="")
    invite_code = Column(String, default=None)
    organization_id = Column(Integer, default=-1)
    state = Column(Integer, default=DatabaseEntryState.OK)


class UserInviteModel(Base):
    """
    Model for invite codes used for elevated user registration.

    Stores invite codes with usage limits, expiration, and role assignment.
    """

    __tablename__ = "user_invites"
    invite_code = Column(String, primary_key=True)
    count_left = Column(Integer, default=1)
    create_time = Column(DateTime(timezone=True), default=get_utcnow)
    expire_time = Column(DateTime(timezone=True), default=None)
    created_by_user_id = Column(Integer, default=-1)
    role = Column(String, default="")
    organization_id = Column(Integer, default=-1)
    state = Column(Integer, default=DatabaseEntryState.OK)


# Conversation


class UserConversation(Base):
    __tablename__ = "user_conversations"
    conversation_id = Column(Integer, primary_key=True)
    thread_id = Column(Integer, default=-1)
    user_id = Column(Integer, default=-1)
    timestamp = Column(DateTime(timezone=True), default=get_utcnow)
    name = Column(String, default="")
    message = Column(String, default="")
    response_to = Column(Integer, default=-1)
    last_operator = Column(String, default="")
    last_heartbeat = Column(DateTime(timezone=True), default=get_utcnow)
    heartbeat_rate = Column(Integer, default=10)
    state = Column(Integer, default=DatabaseEntryState.OK)


class UserConversationThread(Base):
    __tablename__ = "user_conversation_threads"
    thread_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, default=-1)
    timestamp = Column(DateTime(timezone=True), default=get_utcnow)
    name = Column(String, default="")
    state = Column(Integer, default=DatabaseEntryState.OK)


# Task


class UserTask(Base):
    __tablename__ = "user_tasks"
    task_id = Column(String, primary_key=True)
    task_name = Column(String, default="")
    service_name = Column(String, default="")
    user_id = Column(Integer, default=-1)
    create_timestamp = Column(DateTime(timezone=True), default=get_utcnow)
    last_heartbeat_timestamp = Column(DateTime(timezone=True), default=get_utcnow)
    heartbeat_interval_seconds = Column(Integer, default=30)
    progress = Column(Integer, default=0)
    message = Column(String, default="")
    task_stage = Column(Integer, default=0)
    persistent_context = Column(String, default="")
    state = Column(Integer, default=DatabaseEntryState.OK)


# Service Configuration


class ServiceConfigurationModel(Base):
    __tablename__ = "service_configurations"
    config_id = Column(Integer, primary_key=True)
    user_id = Column(Integer, default=-1)
    service_name = Column(String, default="")
    config_key = Column(String, default="")
    config_value = Column(String, default="")
    config_type = Column(String, default="string")  # string, int, float, bool, json
    description = Column(String, default=None)
    is_secret = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=get_utcnow)
    updated_at = Column(DateTime(timezone=True), default=get_utcnow)
    state = Column(Integer, default=DatabaseEntryState.OK)


# Log


class LogEntry(Base):
    __tablename__ = "log_entries"
    id = Column(Integer, primary_key=True, index=True)
    level = Column(String)
    message = Column(String)
    logger_name = Column(String)
    created_at = Column(DateTime, default=get_utcnow)
