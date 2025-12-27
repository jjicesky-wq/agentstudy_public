from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from db.constants import DatabaseEntryState
from db.database import clone_model_into
from db.db_models import (
    ServiceConfigurationModel,
    User,
    UserConversation,
    UserConversationThread,
    UserInviteModel,
    UserTask,
)

# Users


def get_user_by_id(
    session: Session, user_id: int, include_deleted: bool = False
) -> User | None:
    query = session.query(User).filter(User.id == user_id)
    if not include_deleted:
        query = query.filter(User.state < DatabaseEntryState.DELETED)
    return query.first()


def get_user_by_username(
    session: Session, username: str, include_deleted: bool = False
) -> User | None:
    query = session.query(User).filter(User.username == username)
    if not include_deleted:
        query = query.filter(User.state < DatabaseEntryState.DELETED)
    return query.first()


def get_users(
    session: Session, skip: int = 0, limit: int = 100, include_deleted: bool = False
) -> list[User]:
    query = session.query(User)
    if not include_deleted:
        query = query.filter(User.state < DatabaseEntryState.DELETED)
    query = query.offset(skip).limit(limit=limit)
    return query.all()


def create_user(session: Session, user: User) -> User:
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def update_user(session: Session, user: User) -> User | None:
    user_to_update = get_user_by_id(session=session, user_id=user.id)  # type: ignore
    if not user_to_update:
        return
    clone_model_into(dst=user_to_update, src=user)
    session.commit()
    session.refresh(user_to_update)
    return user_to_update


def delete_user_by_id(session: Session, user_id: int):
    user = get_user_by_id(session=session, user_id=user_id)
    if not user:
        return
    user.state = DatabaseEntryState.DELETED  # type: ignore
    session.commit()


def delete_user_by_username(session: Session, username: str):
    user = get_user_by_username(session=session, username=username)
    if not user:
        return
    user.state = DatabaseEntryState.DELETED  # type: ignore
    session.commit()


# User Invites


def get_user_invite_by_code(
    session: Session, invite_code: str, include_deleted: bool = False
) -> UserInviteModel | None:
    """Get user invite by invite code."""
    query = session.query(UserInviteModel).filter(
        UserInviteModel.invite_code == invite_code
    )
    if not include_deleted:
        query = query.filter(UserInviteModel.state < DatabaseEntryState.DELETED)
    return query.first()


def get_user_invites_by_creator(
    session: Session,
    created_by_user_id: int,
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = False,
) -> list[UserInviteModel]:
    """Get all invites created by a specific user."""
    query = session.query(UserInviteModel).filter(
        UserInviteModel.created_by_user_id == created_by_user_id
    )
    if not include_deleted:
        query = query.filter(UserInviteModel.state < DatabaseEntryState.DELETED)
    query = query.offset(skip).limit(limit=limit)
    return query.all()


def get_user_invites(
    session: Session, skip: int = 0, limit: int = 100, include_deleted: bool = False
) -> list[UserInviteModel]:
    """Get all user invites."""
    query = session.query(UserInviteModel)
    if not include_deleted:
        query = query.filter(UserInviteModel.state < DatabaseEntryState.DELETED)
    query = query.offset(skip).limit(limit=limit)
    return query.all()


def create_user_invite(
    session: Session, invite: UserInviteModel, commit: bool = True
) -> UserInviteModel:
    """Create a new user invite."""
    session.add(invite)
    if commit:
        session.commit()
        session.refresh(invite)
    return invite


def update_user_invite(
    session: Session,
    invite: UserInviteModel,
    inplace: bool = False,
    commit: bool = True,
) -> UserInviteModel | None:
    """Update an existing user invite."""
    if inplace:
        invite_to_update = invite
    else:
        invite_to_update = get_user_invite_by_code(
            session=session, invite_code=invite.invite_code  # type: ignore
        )
        if not invite_to_update:
            return None
        clone_model_into(dst=invite_to_update, src=invite)
    if commit:
        session.commit()
        session.refresh(invite_to_update)
    return invite_to_update


def delete_user_invite(session: Session, invite: UserInviteModel, commit: bool = True):
    """Soft delete a user invite."""
    invite.state = DatabaseEntryState.DELETED  # type: ignore
    if commit:
        session.commit()


def delete_user_invite_by_code(session: Session, invite_code: str, commit: bool = True):
    """Soft delete a user invite by code."""
    invite = get_user_invite_by_code(session=session, invite_code=invite_code)
    if not invite:
        return
    delete_user_invite(session=session, invite=invite, commit=commit)


def decrement_invite_count(
    session: Session, invite_code: str, commit: bool = True
) -> UserInviteModel | None:
    """
    Decrement the count_left for an invite code.

    Returns the updated invite or None if not found or count is already 0.
    """
    invite = get_user_invite_by_code(session=session, invite_code=invite_code)
    if not invite or invite.count_left <= 0:  # type: ignore
        return None

    invite.count_left -= 1  # type: ignore
    if commit:
        session.commit()
        session.refresh(invite)
    return invite


# Conversations


def create_conversation(
    session: Session, conversation: UserConversation
) -> UserConversation:
    session.add(conversation)
    session.commit()
    session.refresh(conversation)
    return conversation


def get_conversation_by_id(
    session: Session, conversation_id: int, include_deleted: bool = False
) -> UserConversation | None:
    query = session.query(UserConversation).filter(
        UserConversation.conversation_id == conversation_id
    )
    if not include_deleted:
        query = query.filter(UserConversation.state < DatabaseEntryState.DELETED)
    return query.first()


def delete_conversation_by_id(session: Session, conversation_id: int):
    conversation = get_conversation_by_id(
        session=session, conversation_id=conversation_id
    )
    if not conversation:
        return
    conversation.state = DatabaseEntryState.DELETED  # type: ignore
    session.commit()


def update_conversation(
    session: Session, conversation: UserConversation
) -> UserConversation | None:
    conversation_to_update = get_conversation_by_id(
        session=session, conversation_id=conversation.conversation_id  # type: ignore
    )
    if not conversation_to_update:
        return
    clone_model_into(dst=conversation_to_update, src=conversation)
    session.commit()
    session.refresh(conversation_to_update)
    return conversation_to_update


def get_responses_to_conversation(
    session: Session, conversation_id: int, newer_than: Optional[datetime] = None
) -> list[UserConversation]:
    query = (
        session.query(UserConversation)
        .filter(UserConversation.response_to == conversation_id)
        .filter(UserConversation.state < DatabaseEntryState.DELETED)
    )

    if newer_than:
        query = query.filter(UserConversation.timestamp > newer_than)
    return query.order_by(UserConversation.timestamp).all()


# Conversation threads


def create_conversation_thread(
    session: Session, thread: UserConversationThread
) -> UserConversationThread:
    session.add(thread)
    session.commit()
    session.refresh(thread)
    return thread


def get_conversation_thread_by_id(
    session: Session, thread_id: int, include_deleted: bool = False
) -> UserConversationThread | None:
    query = session.query(UserConversationThread).filter(
        UserConversationThread.thread_id == thread_id
    )
    if not include_deleted:
        query = query.filter(UserConversationThread.state < DatabaseEntryState.DELETED)
    return query.first()


def get_conversations_of_thread_by_id(
    session: Session,
    thread_id: int,
    include_deleted: bool = False,
    newer_than: Optional[datetime] = None,
) -> list[UserConversation]:
    query = session.query(UserConversation).filter(
        UserConversation.thread_id == thread_id
    )
    if not include_deleted:
        query = query.filter(UserConversation.state < DatabaseEntryState.DELETED)
    if newer_than:
        query = query.filter(UserConversation.timestamp > newer_than)
    return query.order_by(UserConversation.timestamp).all()


def get_conversation_threads_by_user_id(
    session: Session, user_id: int, include_deleted: bool = False
) -> list[UserConversationThread]:
    query = session.query(UserConversationThread).filter(
        UserConversationThread.user_id == user_id
    )
    if not include_deleted:
        query = query.filter(UserConversationThread.state < DatabaseEntryState.DELETED)
    return query.all()


def delete_conversation_thread_by_id(session: Session, thread_id: int):
    thread = get_conversation_thread_by_id(session=session, thread_id=thread_id)
    if not thread:
        return
    thread.state = DatabaseEntryState.DELETED  # type: ignore
    session.commit()


def update_conversation_thread(
    session: Session, thread: UserConversationThread
) -> Optional[UserConversationThread]:
    thread_to_update = get_conversation_by_id(
        session=session, conversation_id=thread.thread_id  # type: ignore
    )
    if not thread_to_update:
        return None
    clone_model_into(dst=thread_to_update, src=thread)
    session.commit()
    session.refresh(thread_to_update)
    return thread_to_update


# User tasks


def create_user_task(
    session: Session, user_task: UserTask, commit: bool = True
) -> UserTask:
    """Create a new user task"""
    session.add(user_task)
    if commit:
        session.commit()
        session.refresh(user_task)
    return user_task


def get_user_task_by_id(
    session: Session,
    task_id: str,
    user_id: int = -1,
    include_deleted: bool = False,
) -> UserTask | None:
    """Get a user task by ID, optionally filtered by user_id"""
    query = session.query(UserTask).filter(UserTask.task_id == task_id)
    if not include_deleted:
        query = query.filter(UserTask.state < DatabaseEntryState.DELETED)
    if user_id != -1:
        query = query.filter(UserTask.user_id == user_id)
    return query.first()


def get_user_tasks(
    session: Session, user_id: int, include_deleted: bool = False
) -> list[UserTask]:
    """Get all tasks for a specific user"""
    query = session.query(UserTask).filter(UserTask.user_id == user_id)
    if not include_deleted:
        query = query.filter(UserTask.state < DatabaseEntryState.DELETED)
    return query.order_by(UserTask.create_timestamp.desc()).all()


def get_user_tasks_by_service(
    session: Session,
    user_id: int,
    service_name: str,
    include_deleted: bool = False,
) -> list[UserTask]:
    """Get all tasks for a specific user and service"""
    query = (
        session.query(UserTask)
        .filter(UserTask.user_id == user_id)
        .filter(UserTask.service_name == service_name)
    )
    if not include_deleted:
        query = query.filter(UserTask.state < DatabaseEntryState.DELETED)
    return query.order_by(UserTask.create_timestamp.desc()).all()


def get_user_tasks_paginated(
    session: Session,
    user_id: int,
    limit: Optional[int] = None,
    offset: int = 0,
    include_deleted: bool = False,
) -> list[UserTask]:
    """Get user tasks with pagination support"""
    query = (
        session.query(UserTask)
        .filter(UserTask.user_id == user_id)
        .order_by(UserTask.create_timestamp.desc())
    )
    if not include_deleted:
        query = query.filter(UserTask.state < DatabaseEntryState.DELETED)
    if offset:
        query = query.offset(offset)
    if limit:
        query = query.limit(limit)
    return query.all()


def get_user_tasks_by_state(
    session: Session,
    user_id: int,
    state: int,
    include_deleted: bool = False,
) -> list[UserTask]:
    """Get all tasks for a specific user with a specific state"""
    query = (
        session.query(UserTask)
        .filter(UserTask.user_id == user_id)
        .filter(UserTask.state == state)
    )
    if not include_deleted and state != DatabaseEntryState.DELETED:
        query = query.filter(UserTask.state < DatabaseEntryState.DELETED)
    return query.order_by(UserTask.create_timestamp.desc()).all()


def get_user_task_by_name(
    session: Session,
    user_id: int,
    task_name: str,
    include_deleted: bool = False,
) -> UserTask | None:
    """Get a user task by name for a specific user"""
    query = (
        session.query(UserTask)
        .filter(UserTask.user_id == user_id)
        .filter(UserTask.task_name == task_name)
    )
    if not include_deleted:
        query = query.filter(UserTask.state < DatabaseEntryState.DELETED)
    return query.first()


def update_user_task(
    session: Session,
    user_task: UserTask,
    inplace: bool = False,
    commit: bool = True,
) -> UserTask | None:
    """Update a user task"""
    if inplace:
        user_task_to_update = user_task
    else:
        user_task_to_update = get_user_task_by_id(
            session=session, task_id=user_task.task_id  # type: ignore
        )
        if not user_task_to_update:
            return None
        clone_model_into(dst=user_task_to_update, src=user_task)
    if commit:
        session.commit()
        session.refresh(user_task_to_update)
    return user_task_to_update


def update_user_task_heartbeat(
    session: Session,
    task_id: str,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    commit: bool = True,
) -> UserTask | None:
    """Update a user task's heartbeat timestamp and optionally progress/message"""
    user_task = get_user_task_by_id(session=session, task_id=task_id)
    if not user_task:
        return None

    from db.db_models import get_utcnow

    user_task.last_heartbeat_timestamp = get_utcnow()  # type: ignore
    if progress is not None:
        user_task.progress = progress  # type: ignore
    if message is not None:
        user_task.message = message  # type: ignore

    if commit:
        session.commit()
        session.refresh(user_task)
    return user_task


def delete_user_task(session: Session, user_task: UserTask, commit: bool = True):
    """Soft delete a user task"""
    user_task.state = DatabaseEntryState.DELETED  # type: ignore
    if commit:
        session.commit()


def delete_user_task_by_id(session: Session, task_id: str, commit: bool = True):
    """Soft delete a user task by ID"""
    user_task = get_user_task_by_id(session=session, task_id=task_id)
    if not user_task:
        return
    delete_user_task(session=session, user_task=user_task, commit=commit)


# Service Configuration


def get_service_config_by_id(
    session: Session, config_id: int, include_deleted: bool = False
) -> ServiceConfigurationModel | None:
    """Get service configuration by ID"""
    query = session.query(ServiceConfigurationModel).filter(
        ServiceConfigurationModel.config_id == config_id
    )
    if not include_deleted:
        query = query.filter(
            ServiceConfigurationModel.state < DatabaseEntryState.DELETED
        )
    return query.first()


def get_service_config_by_key(
    session: Session,
    user_id: int,
    service_name: str,
    config_key: str,
    include_deleted: bool = False,
) -> ServiceConfigurationModel | None:
    """Get service configuration by user_id, service_name, and config_key"""
    query = session.query(ServiceConfigurationModel).filter(
        ServiceConfigurationModel.user_id == user_id,
        ServiceConfigurationModel.service_name == service_name,
        ServiceConfigurationModel.config_key == config_key,
    )
    if not include_deleted:
        query = query.filter(
            ServiceConfigurationModel.state < DatabaseEntryState.DELETED
        )
    return query.first()


def get_service_configs_by_service(
    session: Session,
    user_id: int,
    service_name: str,
    include_deleted: bool = False,
) -> list[ServiceConfigurationModel]:
    """Get all configurations for a specific service and user"""
    query = session.query(ServiceConfigurationModel).filter(
        ServiceConfigurationModel.user_id == user_id,
        ServiceConfigurationModel.service_name == service_name,
    )
    if not include_deleted:
        query = query.filter(
            ServiceConfigurationModel.state < DatabaseEntryState.DELETED
        )
    return query.all()


def get_service_configs_by_user(
    session: Session,
    user_id: int,
    skip: int = 0,
    limit: int = 100,
    include_deleted: bool = False,
) -> list[ServiceConfigurationModel]:
    """Get all configurations for a specific user"""
    query = session.query(ServiceConfigurationModel).filter(
        ServiceConfigurationModel.user_id == user_id
    )
    if not include_deleted:
        query = query.filter(
            ServiceConfigurationModel.state < DatabaseEntryState.DELETED
        )
    query = query.offset(skip).limit(limit)
    return query.all()


def create_service_config(
    session: Session, config: ServiceConfigurationModel, commit: bool = True
) -> ServiceConfigurationModel:
    """Create a new service configuration"""
    session.add(config)
    if commit:
        session.commit()
        session.refresh(config)
    return config


def update_service_config(
    session: Session,
    config: ServiceConfigurationModel,
    inplace: bool = False,
    commit: bool = True,
) -> ServiceConfigurationModel | None:
    """Update an existing service configuration"""
    if inplace:
        config_to_update = config
    else:
        config_to_update = get_service_config_by_id(
            session=session, config_id=config.config_id  # type: ignore
        )
        if not config_to_update:
            return None
        clone_model_into(dst=config_to_update, src=config)

    # Update the updated_at timestamp
    from db.db_models import get_utcnow

    config_to_update.updated_at = get_utcnow()  # type: ignore

    if commit:
        session.commit()
        session.refresh(config_to_update)
    return config_to_update


def upsert_service_config(
    session: Session,
    user_id: int,
    service_name: str,
    config_key: str,
    config_value: str,
    config_type: str = "string",
    description: Optional[str] = None,
    is_secret: bool = False,
    commit: bool = True,
) -> ServiceConfigurationModel:
    """Create or update a service configuration by key"""
    existing_config = get_service_config_by_key(
        session=session,
        user_id=user_id,
        service_name=service_name,
        config_key=config_key,
    )

    if existing_config:
        # Update existing
        existing_config.config_value = config_value  # type: ignore
        existing_config.config_type = config_type  # type: ignore
        if description is not None:
            existing_config.description = description  # type: ignore
        existing_config.is_secret = is_secret  # type: ignore
        return update_service_config(
            session=session, config=existing_config, inplace=True, commit=commit
        )
    else:
        # Create new
        new_config = ServiceConfigurationModel(
            user_id=user_id,
            service_name=service_name,
            config_key=config_key,
            config_value=config_value,
            config_type=config_type,
            description=description,
            is_secret=is_secret,
        )
        return create_service_config(session=session, config=new_config, commit=commit)


def delete_service_config(
    session: Session, config: ServiceConfigurationModel, commit: bool = True
):
    """Soft delete a service configuration"""
    config.state = DatabaseEntryState.DELETED  # type: ignore
    if commit:
        session.commit()


def delete_service_config_by_id(session: Session, config_id: int, commit: bool = True):
    """Soft delete a service configuration by ID"""
    config = get_service_config_by_id(session=session, config_id=config_id)
    if not config:
        return
    delete_service_config(session=session, config=config, commit=commit)


def delete_service_config_by_key(
    session: Session,
    user_id: int,
    service_name: str,
    config_key: str,
    commit: bool = True,
):
    """Soft delete a service configuration by key"""
    config = get_service_config_by_key(
        session=session,
        user_id=user_id,
        service_name=service_name,
        config_key=config_key,
    )
    if not config:
        return
    delete_service_config(session=session, config=config, commit=commit)
