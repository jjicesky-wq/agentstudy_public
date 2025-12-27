"""
Task API Database Helper Functions

Provides database operation helpers for task tracking across all services.
All public helper functions start with db_helper_* prefix.

Architecture:
- BaseService/BaseTask: Orchestrates task execution, calls db_helper_* functions
- db_helper_* functions: Database operations only (no business logic)
- db_operations.py: Low-level database queries

Example:
    # Create task record when task starts
    from backend.apis.tasks import db_helper_create_task_record

    with get_db_session() as session:
        task_record = db_helper_create_task_record(
            session=session,
            task_id="task_123",
            task_name="Process URL",
            service_name="digest",
            user_id=1
        )

    # Update heartbeat during execution
    db_helper_update_task_heartbeat(
        task_id="task_123",
        progress=50,
        message="Processing audio..."
    )

    # Update state when complete
    db_helper_complete_task(
        task_id="task_123",
        success=True,
        final_message="Completed successfully"
    )
"""

from __future__ import annotations

import json
from typing import Optional

from sqlalchemy.orm import Session

from db import db_operations as db_ops
from db.constants import DatabaseEntryState
from db.database import get_db_session
from db.db_models import UserTask, get_utcnow
from utilities import logger

# =========================================================================
# Task State Constants
# =========================================================================

# Task states using DatabaseEntryState
TASK_STATE_PENDING = DatabaseEntryState.OK  # Task created but not started
TASK_STATE_RUNNING = DatabaseEntryState.PROCESSING  # Task is currently executing
TASK_STATE_TIME_OUT = DatabaseEntryState.TIMED_OUT  # Task timed out
TASK_STATE_COMPLETED = DatabaseEntryState.PROCESSED  # Task completed successfully
TASK_STATE_CANCELLED = DatabaseEntryState.CANCELLED  # Task cancelled
TASK_STATE_FAILED = DatabaseEntryState.ERROR  # Task failed

# =========================================================================
# Helper Functions (internal, start with _)
# =========================================================================


def _ensure_session(
    session: Optional[Session],
) -> tuple[Session, bool]:
    """
    Ensure we have a valid session, creating one if needed.

    Args:
        session: Optional session to use

    Returns:
        Tuple of (session, should_close) where should_close indicates if we created it
    """
    if session is not None:
        return session, False
    return next(get_db_session()), True


# =========================================================================
# Database Helper Functions (for BaseTask/BaseService to call)
# =========================================================================


def db_helper_create_task_record(
    task_id: str,
    task_name: str = "",
    service_name: str = "",
    user_id: int = -1,
    message: str = "",
    persistent_context: Optional[dict] = None,
    heartbeat_interval_seconds: int = 30,
    session: Optional[Session] = None,
    commit: bool = True,
) -> UserTask:
    """
    Create a task record in the database when a task is queued.

    Args:
        task_name: Human-readable task name
        service_name: Name of service running the task
        user_id: User ID if task is user-specific
        message: Initial status message
        persistent_context: Context data for task resumption (will be JSON serialized)
        heartbeat_interval_seconds: How often heartbeats are expected (default: 30s)
        session: Optional database session
        commit: Whether to commit immediately

    Returns:
        Created UserTask

    Example:
        task_record = db_helper_create_task_record(
            task_id="digest_123",
            task_name="Create audio digest",
            service_name="digest",
            user_id=1,
            message="Task queued",
            heartbeat_interval_seconds=30
        )
    """
    session, should_close = _ensure_session(session)

    try:
        # Serialize context if provided
        context_str = ""
        if persistent_context:
            context_str = json.dumps(persistent_context)

        task_model = UserTask(
            task_id=task_id,
            task_name=task_name,
            service_name=service_name,
            user_id=user_id,
            create_timestamp=get_utcnow(),
            last_heartbeat_timestamp=get_utcnow(),
            heartbeat_interval_seconds=heartbeat_interval_seconds,
            progress=0,
            message=message or "Task queued",
            persistent_context=context_str,
            state=TASK_STATE_PENDING,
        )

        created_task = db_ops.create_user_task(
            session=session, user_task=task_model, commit=commit
        )

        logger.info(
            f"Created task record: {created_task.task_id} "
            f"({service_name}/{task_name}) for user {user_id}, heartbeat every {heartbeat_interval_seconds}s"
        )

        return created_task

    finally:
        if should_close:
            session.close()


def db_helper_update_task_heartbeat(
    task_id: str,
    progress: Optional[int] = None,
    message: Optional[str] = None,
    persistent_context: Optional[dict] = None,
    task_stage: Optional[int] = None,
    session: Optional[Session] = None,
    commit: bool = True,
) -> Optional[UserTask]:
    """
    Update task heartbeat timestamp and optionally progress/message/context/stage.

    This should be called periodically during task execution to:
    - Show the task is still alive
    - Update progress percentage (0-100)
    - Update status message
    - Save context for resumption
    - Track task stage

    Args:
        task_id: Task ID
        progress: Progress percentage (0-100)
        message: Status message
        persistent_context: Context data for resumption (will be JSON serialized)
        task_stage: Integer representing the current stage of the task
        session: Optional database session
        commit: Whether to commit immediately

    Returns:
        Updated UserTask or None if task not found

    Example:
        db_helper_update_task_heartbeat(
            task_id=123,
            progress=50,
            message="Processing audio track 3/6...",
            task_stage=2
        )
    """
    session, should_close = _ensure_session(session)

    try:
        task = db_ops.get_user_task_by_id(session=session, task_id=task_id)
        if not task:
            logger.warning(f"Task {task_id} not found for heartbeat update")
            return None

        task.last_heartbeat_timestamp = get_utcnow()  # type: ignore

        if progress is not None:
            task.progress = max(0, min(100, progress))  # Clamp to 0-100  #type: ignore

        if message is not None:
            task.message = message  # type: ignore

        if persistent_context is not None:
            task.persistent_context = json.dumps(persistent_context)  # type: ignore

        if task_stage is not None:
            task.task_stage = task_stage  # type: ignore

        # Ensure task is marked as running if still pending
        if task.state == TASK_STATE_PENDING:  # type: ignore
            task.state = TASK_STATE_RUNNING  # type: ignore

        if commit:
            session.commit()
            session.refresh(task)

        return task

    finally:
        if should_close:
            session.close()


def db_helper_update_task_progress(
    task_id: str,
    progress: int,
    message: str,
    session: Optional[Session] = None,
    commit: bool = True,
) -> Optional[UserTask]:
    """
    Convenience method to update both progress and message.

    Args:
        task_id: Task ID
        progress: Progress percentage (0-100)
        message: Status message
        session: Optional database session
        commit: Whether to commit immediately

    Returns:
        Updated UserTask or None if task not found
    """
    return db_helper_update_task_heartbeat(
        task_id=task_id,
        progress=progress,
        message=message,
        session=session,
        commit=commit,
    )


def db_helper_save_task_context(
    task_id: str,
    context: dict,
    task_stage: int = 0,
    session: Optional[Session] = None,
    commit: bool = True,
) -> Optional[UserTask]:
    """
    Save task context for resumption after failure/restart.

    Args:
        task_id: Task ID
        context: Context dictionary to save
        task_stage: Integer representing the current stage of the task (default: 0)
        session: Optional database session
        commit: Whether to commit immediately

    Returns:
        Updated UserTask or None if task not found

    Example:
        db_helper_save_task_context(
            task_id=123,
            context={
                "processed_files": [1, 2, 3],
                "temp_data": {"url": "https://..."}
            },
            task_stage=1  # Stage 1: Processing files
        )
    """
    return db_helper_update_task_heartbeat(
        task_id=task_id,
        persistent_context=context,
        task_stage=task_stage,
        session=session,
        commit=commit,
    )


def db_helper_pending_task(
    task_id: str,
    message: str,
    session: Optional[Session] = None,
    commit: bool = True,
) -> None:
    session, should_close = _ensure_session(session)

    try:
        task = db_ops.get_user_task_by_id(session=session, task_id=task_id)
        if not task:
            logger.warning(f"Task {task_id} not found for update")
            return None

        task.state = TASK_STATE_PENDING  # type: ignore
        task.message = message  # type: ignore
        if commit:
            session.commit()
            session.refresh(task)

        return

    finally:
        if should_close:
            session.close()


def db_helper_complete_task(
    task_id: str,
    success: bool = True,
    final_message: Optional[str] = None,
    final_context: Optional[dict] = None,
    session: Optional[Session] = None,
    commit: bool = True,
) -> Optional[UserTask]:
    """
    Mark task as completed (success or failure).

    Args:
        task_id: Task ID
        success: Whether task completed successfully
        final_message: Final status message
        final_context: Final context state
        session: Optional database session
        commit: Whether to commit immediately

    Returns:
        Updated UserTask or None if task not found

    Example:
        # Success
        db_helper_complete_task(
            task_id=123,
            success=True,
            final_message="Digest created successfully"
        )

        # Failure
        db_helper_complete_task(
            task_id=123,
            success=False,
            final_message="Failed: Invalid URL"
        )
    """
    session, should_close = _ensure_session(session)

    try:
        task = db_ops.get_user_task_by_id(session=session, task_id=task_id)
        if not task:
            logger.warning(f"Task {task_id} not found for completion")
            return None

        task.last_heartbeat_timestamp = get_utcnow()  # type: ignore
        task.progress = 100  # type: ignore

        if final_message is not None:
            task.message = final_message  # type: ignore
        elif success:
            task.message = task.message or "Task completed successfully"  # type: ignore
        else:
            task.message = task.message or "Task failed"  # type: ignore

        if final_context is not None:
            task.persistent_context = json.dumps(final_context)  # type: ignore

        # Set final state
        task.state = TASK_STATE_COMPLETED if success else TASK_STATE_FAILED  # type: ignore

        if commit:
            session.commit()
            session.refresh(task)

        logger.info(f"Task {task_id} completed: {success} - {task.message}")

        return task

    finally:
        if should_close:
            session.close()


def db_helper_cancel_task(
    task_id: str,
    cancel_message: Optional[str] = None,
    session: Optional[Session] = None,
    commit: bool = True,
) -> Optional[UserTask]:
    """
    Mark task as cancelled.

    Args:
        task_id: Task ID
        cancel_message: Cancellation message
        session: Optional database session
        commit: Whether to commit immediately

    Returns:
        Updated UserTask or None if task not found
    """
    session, should_close = _ensure_session(session)

    try:
        task = db_ops.get_user_task_by_id(session=session, task_id=task_id)
        if not task:
            logger.warning(f"Task {task_id} not found for cancellation")
            return None

        task.last_heartbeat_timestamp = get_utcnow()  # type: ignore
        task.message = cancel_message or "Task cancelled"  # type: ignore
        task.state = TASK_STATE_CANCELLED  # type: ignore

        if commit:
            session.commit()
            session.refresh(task)

        logger.info(f"Task {task_id} cancelled: {task.message}")

        return task

    finally:
        if should_close:
            session.close()


def db_helper_get_task_by_id(
    task_id: str,
    user_id: int = -1,
    include_deleted: bool = False,
    session: Optional[Session] = None,
) -> Optional[UserTask]:
    """
    Get task by ID.

    Args:
        task_id: Task ID
        user_id: User ID for filtering (NONE means no filter)
        include_deleted: Whether to include deleted/failed/cancelled tasks
        session: Optional database session

    Returns:
        UserTask if found, None otherwise
    """
    session, should_close = _ensure_session(session)

    try:
        return db_ops.get_user_task_by_id(
            session=session,
            task_id=task_id,
            user_id=user_id,
            include_deleted=include_deleted,
        )
    finally:
        if should_close:
            session.close()


def db_helper_get_user_tasks(
    user_id: int,
    include_deleted: bool = False,
    session: Optional[Session] = None,
) -> list[UserTask]:
    """
    Get all tasks for a user.

    Args:
        user_id: User ID
        include_deleted: Whether to include deleted/failed/cancelled tasks
        session: Optional database session

    Returns:
        List of UserTask
    """
    session, should_close = _ensure_session(session)

    try:
        return db_ops.get_user_tasks(
            session=session,
            user_id=user_id,
            include_deleted=include_deleted,
        )
    finally:
        if should_close:
            session.close()


def db_helper_get_task_context(
    task_id: str,
    session: Optional[Session] = None,
) -> Optional[dict]:
    """
    Get task context for resumption.

    Args:
        task_id: Task ID
        session: Optional database session

    Returns:
        Context dictionary or None if task not found or no context saved
    """
    session, should_close = _ensure_session(session)

    try:
        task = db_ops.get_user_task_by_id(session=session, task_id=task_id)
        if not task or not task.persistent_context:  # type: ignore
            return None

        try:
            return json.loads(task.persistent_context)  # type: ignore
        except json.JSONDecodeError:
            logger.warning(f"Failed to decode context for task {task_id}")
            return None
    finally:
        if should_close:
            session.close()


def db_helper_query_task_info(
    task_id: Optional[str] = None,
    user_id: int = -1,
    session: Optional[Session] = None,
) -> Optional[dict]:
    """
    Query task information by either task_id (UUID string) or tracking_id (database ID).

    This helper consolidates the logic for:
    - Querying by tracking_id or task_id
    - Mapping database state to API-friendly state strings
    - Extracting context data including exam_id
    - Building result text from context

    Args:
        task_id: Task ID (UUID string, stored as task_name in database)
        tracking_id: Database tracking ID (task_id in database)
        user_id: User ID for security filtering
        session: Optional database session

    Returns:
        Dictionary with task information if found, None if not found:
        {
            "state": str,                  # "pending", "processing", "completed", "failed", "cancelled" (deprecated)
            "completed": bool,             # True if task completed successfully
            "failed": bool,                # True if task failed
            "cancelled": bool,             # True if task was cancelled
            "in_progress": bool,           # True if task is running
            "pending": bool,               # True if task is queued but not started
            "progress": Optional[float],   # Progress percentage (0-100)
            "message": str,                # Status message
            "context": Optional[dict],     # Persistent context data
            "exam_id": Optional[int],      # Exam ID (if completed and available)
            "result_text": Optional[str]   # Human-readable result text
        }

    Example:
        # Query by tracking_id
        info = db_helper_query_task_info(tracking_id=123, user_id=1, session=session)

        # Query by task_id (UUID)
        info = db_helper_query_task_info(task_id="uuid-string", user_id=1, session=session)
    """
    session, should_close = _ensure_session(session)

    try:
        db_task = None
        # Query by task_id (UUID stored as task_name)
        if task_id:
            try:
                db_task = db_ops.get_user_task_by_name(
                    session=session,
                    task_name=task_id,
                    user_id=user_id,
                )
            except Exception as e:
                logger.warning(f"Failed to query task by task_id {task_id}: {e}")

        # Task not found
        if not db_task:
            return None

        # Map database state to API-friendly state strings and boolean flags
        state_mapping = {
            TASK_STATE_PENDING: "pending",
            TASK_STATE_RUNNING: "processing",
            TASK_STATE_COMPLETED: "completed",
            TASK_STATE_FAILED: "failed",
            TASK_STATE_CANCELLED: "cancelled",
        }
        state = state_mapping.get(db_task.state, "unknown")  # type: ignore

        # Set boolean flags (mutually exclusive)
        completed = db_task.state == TASK_STATE_COMPLETED
        failed = db_task.state == TASK_STATE_FAILED
        cancelled = db_task.state == TASK_STATE_CANCELLED
        in_progress = db_task.state == TASK_STATE_RUNNING
        pending = db_task.state == TASK_STATE_PENDING

        # Get context data
        context_data = db_helper_get_task_context(task_id=task_id, session=session)  # type: ignore

        # Extract exam_id and build result text for completed tasks
        exam_id = None
        result_text = None
        if completed and context_data:  # type: ignore
            exam_id = context_data.get("exam_id")
            if exam_id:
                problems_count = context_data.get("problems_assembled", 0)
                result_text = (
                    f"Exam ingestion completed: {problems_count} problems extracted"
                )

        # Get progress and message from task record
        progress = float(db_task.progress) if db_task.progress else None  # type: ignore
        message = db_task.message or f"Task state: {state}"

        return {
            "state": state,  # Deprecated, but kept for backward compatibility
            "completed": completed,
            "failed": failed,
            "cancelled": cancelled,
            "in_progress": in_progress,
            "pending": pending,
            "progress": progress,
            "message": message,
            "context": context_data,
            "exam_id": exam_id,
            "result_text": result_text or message,
        }

    finally:
        if should_close:
            session.close()


# =========================================================================
# Cleanup Functions
# =========================================================================


def db_helper_delete_old_tasks(
    days_old: int = 30,
    session: Optional[Session] = None,
    commit: bool = True,
) -> int:
    """
    Soft delete tasks older than specified days.

    Args:
        days_old: Delete tasks older than this many days
        session: Optional database session
        commit: Whether to commit immediately

    Returns:
        Number of tasks deleted
    """
    from datetime import timedelta

    session, should_close = _ensure_session(session)

    try:
        cutoff_date = get_utcnow() - timedelta(days=days_old)

        # Get old completed/failed tasks
        old_tasks = (
            session.query(UserTask)
            .filter(UserTask.create_timestamp < cutoff_date)
            .filter(UserTask.state.in_([TASK_STATE_COMPLETED, TASK_STATE_FAILED]))
            .all()
        )

        count = 0
        for task in old_tasks:
            task.state = DatabaseEntryState.DELETED  # type: ignore
            count += 1

        if commit:
            session.commit()

        logger.info(f"Deleted {count} old tasks (older than {days_old} days)")
        return count

    finally:
        if should_close:
            session.close()
