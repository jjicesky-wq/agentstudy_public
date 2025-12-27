"""
Base Service and Task Framework

Provides abstract base classes for building threaded service architectures with task queues.

Key Components:
- BaseTaskConfig: Pydantic configuration class for task initialization
- BaseTask: Abstract base class for tasks
- AsyncBaseTask: Task base class for async operations
- BaseService: Abstract base class for services with task management

Example:
    class MyTaskConfig(BaseTaskConfig):
        custom_param: str

    class MyTask(BaseTask):
        def __init__(self, service_name: str, config: MyTaskConfig):
            super().__init__(service_name=service_name, config=config)
            self.custom_param = config.custom_param

        def _run(self):
            # Task logic here
            self.complete(result="Success")

    class MyService(BaseService):
        def __init__(self):
            super().__init__(service_name="MyService", passive_mode=True)

        def _query_tasks(self, max_count: int) -> list[BaseTask]:
            return []  # Passive mode - no automatic polling

        def _mark_task_as_not_processed(self, task: BaseTask):
            pass  # Handle task cleanup

        def _keep_task_alive_and_check_task_cancel(self, task: BaseTask) -> bool:
            return False  # Return True to cancel task

    # Usage
    service = MyService()
    service.start()
    config = MyTaskConfig(custom_param="value")
    task = MyTask(service_name="MyService", config=config)
    service.queue_task(task)
    service.wait_for_completion()
    service.request_shutdown()
"""

from __future__ import annotations

import asyncio
import threading
import time
import traceback
import uuid
from abc import abstractmethod
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel

from utilities import logger
from utilities.time import get_utcnow

# =============================================================================
# Task Configuration Classes
# =============================================================================


class BaseTaskConfig(BaseModel):
    """
    Configuration for BaseTask initialization.

    This Pydantic model contains all configuration parameters for creating a task.
    Subclasses can extend this to add custom configuration fields.

    Attributes:
        sync_run: If True, task runs synchronously (default: False)
        user_id: User ID if task is user-specific (default: -1 = NONE)
        enable_db_tracking: Enable automatic database tracking (default: False)
        heartbeat_interval_seconds: How often heartbeats are sent to DB (default: 30s)

    Example:
        class MyTaskConfig(BaseTaskConfig):
            url: str
            max_retries: int = 3

        config = MyTaskConfig(url="https://example.com")
        task = MyTask(service_name="crawler", config=config)
    """

    sync_run: bool = False
    user_id: int = -1
    enable_db_tracking: bool = False
    heartbeat_interval_seconds: int = 30


# =============================================================================
# Task Classes
# =============================================================================


class BaseTask:
    """
    Abstract base class for tasks that can be executed by a BaseService.

    Tasks represent units of work that can be queued, executed in threads,
    and monitored for completion. Each task has a unique ID, priority,
    and execution timeout.

    Attributes:
        config: BaseTaskConfig instance containing task configuration
        task_id: Unique identifier for the task (auto-generated)
        service_name: Name of the service managing this task
        thread: Thread object if running async (None if sync or not started)
        sync_run: If True, task runs synchronously in main thread
        task_max_execution_time_seconds: Maximum execution time before timeout
        task_start_time: When the task started executing
        completed: True if task completed successfully
        result: Result message/data from task execution
        follow_up_tasks: Optional list of tasks to queue after completion
        task_last_check_cancel_time: Last time cancel check was performed
        cancelled: True if task was cancelled
        terminate_event: Threading event set when task terminates
        priority: Task priority (higher = executed first)

    Example:
        class PrintTaskConfig(BaseTaskConfig):
            message: str

        class PrintTask(BaseTask):
            def __init__(self, service_name: str, config: PrintTaskConfig):
                super().__init__(service_name=service_name, config=config)
                self.message = config.message

            def _run(self):
                print(self.message)
                self.complete(result="Printed successfully")

        config = PrintTaskConfig(message="Hello")
        task = PrintTask(service_name="my_service", config=config)
        service.queue_task(task)
    """

    config: BaseTaskConfig
    task_id: str
    service_name: str
    thread: Optional[threading.Thread] = None
    sync_run: bool = False
    task_max_execution_time_seconds: int = 600
    task_start_time: Optional[datetime] = None
    completed: bool = False
    result: Optional[str] = ""
    follow_up_tasks: Optional[list[BaseTask]] = None
    task_last_check_cancel_time: Optional[datetime] = None
    cancelled: bool = False
    terminate_event: threading.Event = threading.Event()
    priority: int = 0

    # Database tracking fields
    user_id: int = -1  # User ID for user-specific tasks (-1 = -1)
    task_name: str = ""  # Human-readable task name
    enable_db_tracking: bool = False  # Enable automatic DB tracking
    last_heartbeat_time: Optional[datetime] = None  # Last heartbeat timestamp
    heartbeat_interval_seconds: int = 30  # DB heartbeat interval (default: 30s)
    _db_state_lock: Optional[
        threading.Lock
    ] = None  # Lock for thread-safe DB state access

    # Cached context and stage for fast retrieval
    _cached_context: Optional[dict] = None
    _cached_stage: int = 0
    _cached_progress: int = 0  # Cached progress percentage
    _cached_message: str = ""  # Cached status message

    def __init__(
        self,
        service_name: str,
        config: BaseTaskConfig,
        task_id: Optional[str] = None,
        task_name: Optional[str] = None,
    ):
        """
        Initialize a task.

        Args:
            service_name: Name of the service that will manage this task
            config: BaseTaskConfig instance containing task configuration
            task_name: Human-readable name for the task (optional, defaults to class name)
        """
        self.config = config
        self.task_id = task_id or str(uuid.uuid4())
        self.service_name = service_name
        self.sync_run = config.sync_run
        self.user_id = config.user_id
        self.task_name = task_name or self.__class__.__name__
        self.enable_db_tracking = config.enable_db_tracking
        self.heartbeat_interval_seconds = config.heartbeat_interval_seconds
        self.last_heartbeat_time = None

        # Create lock for DB state access (protects db_task_id and last_heartbeat_time)
        # This is needed because keep_alive() is called from service thread while
        # report_progress() etc. are called from task thread
        self._db_state_lock = threading.Lock() if config.enable_db_tracking else None

    def get_service_manager(self):
        """
        Get the singleton ServiceManager instance.

        This allows tasks to access other services without having a direct
        reference to their own service.

        Returns:
            ServiceManager instance

        Example:
            def _run(self):
                # Get the crawler service from within a task
                from services.service_names import SERVICE_CRAWLER
                manager = self.get_service_manager()
                crawler = manager.get_service(SERVICE_CRAWLER)
        """
        from services.service_manager import ServiceManager

        return ServiceManager()

    @abstractmethod
    def _run(self):
        """
        Abstract method containing the task logic to execute.

        Subclasses must implement this method with their task logic.
        Must call self.complete() or self.cancel() when done.

        Example:
            def _run(self):
                try:
                    # Do work here
                    result = self.do_something()
                    self.complete(result="Success")
                except Exception as e:
                    self.complete(result=f"Error: {e}")
        """
        raise NotImplementedError

    def _run_wrapper(self):
        """
        Internal wrapper that executes _run() with exception handling.

        This method is called by run() and handles exceptions that occur
        during task execution, logging them appropriately.
        """
        try:
            self.task_start_time = get_utcnow()
            self._run()
        except Exception as e:
            logger.info(f"!! Task {self.task_id} Exception !!\n{str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                logger.info(f"  {tb}")

    def run(self, sync_run: bool) -> threading.Thread | None:
        """
        Execute the task either synchronously or asynchronously.

        Args:
            sync_run: If True, run in current thread; if False, spawn new thread

        Returns:
            Thread object if async, None if sync
        """
        self.task_start_time = get_utcnow()
        if sync_run or self.sync_run:
            self._run_wrapper()
            return None
        else:
            self.thread = threading.Thread(target=self._run_wrapper, daemon=True)
            self.thread.start()
            return self.thread

    def cancel(self, result: Optional[str] = None):
        """
        Cancel the task.

        Marks the task as cancelled and terminated. The task thread may
        continue running but should check terminated() periodically.

        If DB tracking is enabled, updates the database record.
        """
        logger.info(f"Task {self.task_id} cancelled!")
        self.cancelled = True
        self.completed = True
        self.terminate_event.set()
        self.result = "Cancelled" if result is None else result

        # Update database state
        self.update_db_state_cancelled()

    def fail(self, result: Optional[str] = None):
        """
        Mark the task as failed.

        This should be called when the task encounters an error that prevents
        successful completion. Unlike cancel(), which indicates user-initiated
        cancellation, fail() indicates an error condition.

        Marks the task as completed but with failed state. The task thread may
        continue running but should check terminated() periodically.

        If DB tracking is enabled, updates the database record with failed state.

        Args:
            result: Error message or failure reason
        """
        logger.error(f"Task {self.task_id} failed!")
        self.completed = True
        self.terminate_event.set()
        self.result = "Failed" if result is None else result

        # Update database state with success=False to mark as failed
        self.update_db_state_completed(success=False, final_message=self.result)

    def get_final_artifact(self) -> Optional[dict]:
        """
        Get the final artifact/result data for saving to context.

        This method should be overridden by subclasses to return their
        final result as a dictionary for persistence. The artifact will
        be saved to the database context on successful completion.

        Returns:
            Dictionary containing the final artifact data, or None if no artifact

        Example:
            def get_final_artifact(self) -> Optional[dict]:
                return {
                    "audio_file_id": self.audio_file_id,
                    "duration_ms": self.duration_ms,
                    "codec": self.codec,
                }
        """
        return None  # Default: no artifact

    def complete(self, result: str, follow_up_tasks: Optional[list[BaseTask]] = None):
        """
        Mark the task as completed.

        Args:
            result: Result message/data from task execution
            follow_up_tasks: Optional list of tasks to queue after this one

        If DB tracking is enabled, updates the database record and saves the
        final artifact (from get_final_artifact()) to context.
        """
        logger.info(f"Task {self.task_id} completed!")
        self.completed = True
        self.terminate_event.set()
        self.result = result
        self.follow_up_tasks = follow_up_tasks

        # Update database state (success if not cancelled)
        if not self.cancelled:
            # Check if result indicates an error
            success = not (
                result and ("error" in result.lower() or "failed" in result.lower())
            )

            # Save final artifact to context if successful and DB tracking enabled
            if success and self.enable_db_tracking:
                final_artifact = self.get_final_artifact()
                if final_artifact:
                    # Save as final stage (use a high stage number to indicate completion)
                    self.save_context(final_artifact, task_stage=999)

            self.update_db_state_completed(success=success, final_message=result)

    def terminated(self) -> bool:
        """
        Check if task has terminated (either completed or cancelled).

        Returns:
            True if task is no longer running
        """
        return self.completed or self.cancelled

    def graceful_terminated(self) -> bool:
        """
        Check if task completed successfully (not cancelled).

        Returns:
            True if task completed without cancellation
        """
        return self.completed and (not self.cancelled)

    def task_running_time_seconds(self) -> float:
        """
        Get the number of seconds the task has been running.

        Returns:
            Seconds since task start, or 0 if not started
        """
        if not self.task_start_time:
            return 0
        return (get_utcnow() - self.task_start_time).total_seconds()

    def task_timed_out(self) -> bool:
        """
        Check if task has exceeded its maximum execution time.

        Returns:
            True if task has been running longer than task_max_execution_time_seconds
        """
        diff = self.task_running_time_seconds()
        if (
            self.task_max_execution_time_seconds > 0
            and diff >= self.task_max_execution_time_seconds
        ):
            return True
        else:
            return False

    # =========================================================================
    # Database Tracking Methods
    # =========================================================================

    def get_progress(self) -> int:
        """
        Get the current task progress percentage.

        Returns:
            Progress percentage (0-100)

        Example:
            progress = task.get_progress()
            print(f"Task is {progress}% complete")
        """
        return self._cached_progress

    def get_message(self) -> str:
        """
        Get the current task status message.

        Returns:
            Status message string

        Example:
            message = task.get_message()
            print(f"Task status: {message}")
        """
        return self._cached_message

    def report_progress(self, progress: int, message: str):
        """
        Report task progress (0-100) and status message.

        This method should be called periodically during task execution to update
        the progress bar and status message. If DB tracking is enabled, it will
        also update the database record.

        Subclasses can override this to add custom progress tracking logic.

        Thread-safe: Can be called from task thread while service thread calls keep_alive().

        Args:
            progress: Progress percentage (0-100)
            message: Current status message

        Example:
            def _run(self):
                self.report_progress(0, "Starting crawl...")
                result = self.crawl_url()
                self.report_progress(50, "Processing content...")
                processed = self.process(result)
                self.report_progress(100, "Complete!")
                self.complete(result="Success")
        """
        # Log progress
        logger.info(f"[{self.task_id}] Progress: {progress}% - {message}")

        # Cache progress and message for fast retrieval
        self._cached_progress = progress
        self._cached_message = message

        # Update database if tracking is enabled
        if self.enable_db_tracking:
            if self._db_state_lock is None:
                logger.warning(f"[{self.task_id}] DB state lock not initialized")
                return

            # Lock protects access to db_task_id (shared between task and service threads)
            with self._db_state_lock:
                from server.apis.tasks import db_helper_update_task_progress

                try:
                    db_helper_update_task_progress(
                        task_id=self.task_id,
                        progress=progress,
                        message=message,
                    )
                except Exception as e:
                    logger.warning(f"Failed to update task progress in DB: {e}")

    def save_context(self, context: dict, task_stage: int = 0):
        """
        Save task context for resumption after failure/restart.

        The context should contain all information needed to resume the task
        from its current state. This is stored in the database and can be
        retrieved to resume interrupted tasks.

        Subclasses can override this to add validation or transformation logic.

        Thread-safe: Can be called from task thread.

        Args:
            context: Context dictionary to save
            task_stage: Integer representing the current stage of the task (default: 0)

        Example:
            def _run(self):
                for i, file in enumerate(files):
                    self.process_file(file)
                    # Save progress so we can resume if interrupted
                    self.save_context(
                        context={
                            "processed_files": i + 1,
                            "last_file": file.name
                        },
                        task_stage=1  # Stage 1: Processing files
                    )
        """
        if not self.enable_db_tracking:
            return

        if self._db_state_lock is None:
            logger.warning(f"[{self.task_id}] DB state lock not initialized")
            return

        # Lock protects access to db_task_id
        with self._db_state_lock:
            from server.apis.tasks import db_helper_save_task_context

            try:
                db_helper_save_task_context(
                    task_id=self.task_id,
                    context=context,
                    task_stage=task_stage,
                )
                # Cache the context and stage for fast retrieval
                self._cached_context = context
                self._cached_stage = task_stage
                logger.info(
                    f"[{self.task_id}] Saved context (stage {task_stage}): {list(context.keys())}"
                )
            except Exception as e:
                logger.warning(f"Failed to save task context to DB: {e}")

    def load_context(self, no_lock: bool = False) -> tuple[Optional[dict], int]:
        """
        Load previously saved task context and stage for resumption.

        Returns the context dictionary and task_stage if one exists, or (None, 0)
        if no context was saved or DB tracking is disabled.

        Uses cached values if available, otherwise loads from database.

        Thread-safe: Can be called from task thread.

        Args:
            no_lock: If True, skip acquiring the lock (caller must hold lock). Default: False.
                     Use this when calling from within a locked section to avoid deadlock.

        Returns:
            Tuple of (context dictionary or None, task_stage int)

        Example:
            def _run(self):
                # Try to resume from previous run
                context, stage = self.load_context()
                if context:
                    start_index = context.get("processed_files", 0)
                    logger.info(f"Resuming from file {start_index}, stage {stage}")
                else:
                    start_index = 0
                    stage = 0
                    logger.info("Starting fresh")
                # Continue processing...
        """
        if not self.enable_db_tracking:
            return None, 0

        # Return cached values if available
        if self._cached_context is not None:
            return self._cached_context, self._cached_stage

        if self._db_state_lock is None:
            logger.warning(f"[{self.task_id}] DB state lock not initialized")
            return None, 0

        # Define the internal loading logic
        def _load_from_db():
            from server.apis.tasks import db_helper_get_task_by_id

            try:
                task_model = db_helper_get_task_by_id(task_id=self.task_id)
                if not task_model:
                    return None, 0

                # Load context from persistent_context field
                import json

                context = None
                if task_model.persistent_context:  # type: ignore
                    try:
                        context = json.loads(task_model.persistent_context)  # type: ignore
                    except json.JSONDecodeError:
                        logger.warning(
                            f"[{self.task_id}] Failed to decode context JSON"
                        )

                task_stage = task_model.task_stage

                # Cache the loaded values
                self._cached_context = context
                self._cached_stage = task_stage  # type: ignore

                if context:
                    logger.info(
                        f"[{self.task_id}] Loaded context (stage {task_stage}): {list(context.keys())}"
                    )
                else:
                    logger.info(f"[{self.task_id}] Loaded task_stage: {task_stage}")

                return context, task_stage
            except Exception as e:
                logger.warning(f"Failed to load task context from DB: {e}")
                return None, 0

        # Load with or without lock based on no_lock parameter
        if no_lock:
            return _load_from_db()  # type: ignore
        else:
            with self._db_state_lock:
                return _load_from_db()  # type: ignore

    def create_or_retrieve_db_record(self) -> bool:
        """
        Create a new database record or retrieve an existing one for task resumption.

        Returns:
            True if record was created/retrieved successfully and task can be processed,
            False if task should not be processed (e.g., already completed, deleted)
        """
        if not self.enable_db_tracking:
            return True  # No tracking, allow processing

        if self._db_state_lock is None:
            logger.warning(f"[{self.task_id}] DB state lock not initialized")
            return False

        with self._db_state_lock:
            # Try to load existing task by the id
            try:
                from server.apis.tasks import (
                    TASK_STATE_PENDING,
                    db_helper_get_task_by_id,
                    db_helper_pending_task,
                )

                task_model = db_helper_get_task_by_id(
                    task_id=self.task_id, include_deleted=True
                )
                if task_model:
                    # Check if task state allows processing
                    # Only PENDING tasks can be retried/resumed
                    if task_model.state != TASK_STATE_PENDING:  # type: ignore
                        logger.warning(
                            f"[{self.task_id}] Task state is {task_model.state}, only PENDING tasks can be retried, skipping"
                        )
                        return False

                    # Load and cache context and stage using load_context with no_lock
                    # Since we already hold the lock, pass no_lock=True to avoid deadlock
                    self.load_context(no_lock=True)

                    # Reset task state to PENDING for resumption
                    db_helper_pending_task(task_id=self.task_id, message="Queued")
                    return True
            except Exception as e:
                logger.error(f"[{self.task_id}] Failed to load DB record: {e}")
                return False

            # Create new record
            from server.apis.tasks import db_helper_create_task_record

            try:
                task_record = db_helper_create_task_record(
                    task_id=self.task_id,
                    task_name=self.task_name,
                    service_name=self.service_name,
                    user_id=self.user_id,
                    message="Task queued",
                    heartbeat_interval_seconds=self.heartbeat_interval_seconds,
                )
            except Exception as e:
                logger.error(
                    f"[{self.task_id}] Failed to create task record in DB: {e}"
                )
                return False

        return True  # Successfully created or retrieved record

    def update_db_state_completed(
        self, success: bool = True, final_message: Optional[str] = None
    ):
        """
        Update database record to mark task as completed.

        This is called automatically by complete() and cancel() if DB tracking
        is enabled.

        Thread-safe: Called from task thread at completion.

        Args:
            success: Whether task completed successfully
            final_message: Final status message
        """
        if not self.enable_db_tracking:
            return

        if self._db_state_lock is None:
            logger.warning(f"[{self.task_id}] DB state lock not initialized")
            return

        with self._db_state_lock:
            from server.apis.tasks import db_helper_complete_task

            try:
                db_helper_complete_task(
                    task_id=self.task_id,
                    success=success,
                    final_message=final_message or self.result or "Task completed",
                )
                logger.info(
                    f"[{self.task_id}] Updated DB state: {'completed' if success else 'failed'}"
                )
            except Exception as e:
                logger.warning(f"Failed to update task completion state in DB: {e}")

    def update_db_state_cancelled(self):
        """
        Update database record to mark task as cancelled.

        This is called automatically by cancel() if DB tracking is enabled.

        Thread-safe: Called from task thread at cancellation.
        """
        if not self.enable_db_tracking:
            return

        if self._db_state_lock is None:
            logger.warning(f"[{self.task_id}] DB state lock not initialized")
            return

        with self._db_state_lock:
            from server.apis.tasks import db_helper_cancel_task

            try:
                db_helper_cancel_task(
                    task_id=self.task_id,
                    cancel_message=self.result or "Task cancelled",
                )
                logger.info(f"[{self.task_id}] Updated DB state: cancelled")
            except Exception as e:
                logger.warning(f"Failed to update task cancellation state in DB: {e}")

    def mark_as_paused(self):
        """
        Mark this task as paused for future resumption.

        This method saves the current task state to the database, marking it
        as PENDING so it can be retried. Any context saved via save_context()
        is preserved. This is useful for tasks that are interrupted and need
        to be resumed later.

        If DB tracking is not enabled, this is a no-op.

        Thread-safe: Can be called from any thread.

        """
        if not self.enable_db_tracking:
            logger.info(
                f"[{self.task_id}] DB tracking not enabled, skipping mark_as_not_processed"
            )
            return

        if self._db_state_lock is None:
            logger.warning(f"[{self.task_id}] DB state lock not initialized")
            return

        with self._db_state_lock:
            try:
                from server.apis.tasks import db_helper_pending_task

                db_helper_pending_task(task_id=self.task_id, message="Paused")
                logger.info(
                    f"[{self.task_id}] Marked as paused (state reset to PENDING for retry)"
                )

            except Exception as e:
                logger.error(f"[{self.task_id}] Failed to mark as paused: {e}")

    # =========================================================================
    # Keep Alive - Called from Main Service Thread
    # =========================================================================

    def _send_heartbeat(self, force: bool = False) -> bool:
        """
        Send a heartbeat to indicate the task is still alive.

        This updates the last_heartbeat timestamp in the database. Called
        automatically by keep_alive() from the service thread.

        Heartbeats are sent at half the configured interval (e.g., if interval is 30s,
        heartbeats are sent every 15s) to ensure the DB record stays fresh.

        Thread-safe: Called from service thread via keep_alive().

        Args:
            force: If True, send heartbeat regardless of interval (default: False)

        Returns:
            True if sent heartbeat, False otherwise
        """
        if not self.enable_db_tracking:
            return False

        if self._db_state_lock is None:
            logger.warning(f"[{self.task_id}] DB state lock not initialized")
            return False

        # Check if enough time has passed since last heartbeat
        now = get_utcnow()
        if not force and self.last_heartbeat_time is not None:
            elapsed = (now - self.last_heartbeat_time).total_seconds()
            # Send heartbeat at half the interval to ensure DB record stays fresh
            if elapsed < (self.heartbeat_interval_seconds / 2.0):
                return False  # Too soon for another heartbeat

        with self._db_state_lock:
            self.last_heartbeat_time = now

            from server.apis.tasks import db_helper_update_task_heartbeat

            try:
                db_helper_update_task_heartbeat(
                    task_id=self.task_id,
                )
                return True
            except Exception as e:
                logger.warning(f"Failed to send task heartbeat to DB: {e}")

            return False

    def keep_alive(self) -> bool:
        """
        Keep task alive and check if it should be cancelled.

        Called periodically for running and queued tasks. This method:
        - Sends heartbeats to the database (if DB tracking enabled)
        - Checks database for external cancellation requests
        - Checks if task was marked as completed in DB

        Subclasses can override this to add custom heartbeat/cancellation logic,
        but should call super()._keep_task_alive_and_check_task_cancel(task) first.

        Args:
            task: The task to check

        Returns:
            True if task should be alive, False otherwise
        """
        # Only perform DB operations if tracking is enabled
        if not self.enable_db_tracking:
            return True

        if self._db_state_lock is None:
            logger.warning(f"[{self.task_id}] DB state lock not initialized")
            return True

        try:
            from server.apis.tasks import (
                TASK_STATE_CANCELLED,
                TASK_STATE_COMPLETED,
                db_helper_get_task_by_id,
            )

            # Send heartbeat
            if not self._send_heartbeat():
                return True

            with self._db_state_lock:
                # Check database for task state
                db_task = db_helper_get_task_by_id(
                    task_id=self.task_id,
                    include_deleted=True,  # Include cancelled/failed tasks
                )

                # Check if task was cancelled or completed externally
                if db_task.state == TASK_STATE_CANCELLED:  # type: ignore
                    logger.info(
                        f"[{self.service_name}] Task {self.task_id} was cancelled in database"
                    )
                    return False

                if db_task.state == TASK_STATE_COMPLETED:  # type: ignore
                    logger.info(
                        f"[{self.service_name}] Task {self.task_id} was marked complete in database"
                    )
                    return False

            return True

        except Exception as e:
            # Don't cancel task if DB check fails - log and continue
            logger.warning(
                f"[{self.service_name}] Failed to check task status in DB: {e}"
            )
            return True


class AsyncBaseTask(BaseTask):
    """
    Async version of BaseTask that runs async code in a thread with its own event loop.

    This class handles event loop management automatically, preventing
    "Semaphore bound to different event loop" errors when running async
    code in a threaded environment.

    Subclasses should implement _run_async() instead of _run().

    Example:
        class CrawlTaskConfig(BaseTaskConfig):
            url: str

        class CrawlTask(AsyncBaseTask):
            def __init__(self, service_name: str, config: CrawlTaskConfig):
                super().__init__(service_name=service_name, config=config)
                self.url = config.url

            async def _run_async(self):
                async with AsyncClient() as client:
                    result = await client.get(self.url)
                    self.complete(result=f"Downloaded {len(result)} bytes")

        config = CrawlTaskConfig(url="https://example.com")
        task = CrawlTask(service_name="crawler", config=config)

    See Also:
        ASYNC_TASKS.md for detailed documentation and migration guide
    """

    @abstractmethod
    async def _run_async(self):
        """
        Async implementation of the task logic.

        Subclasses must implement this method with their async task logic.
        Must call self.complete() or self.cancel() when done.

        Example:
            async def _run_async(self):
                try:
                    result = await self.fetch_data()
                    self.complete(result="Success")
                except Exception as e:
                    self.complete(result=f"Error: {e}")
        """
        raise NotImplementedError

    async def _cleanup_async(self):
        """
        Async cleanup hook called before the event loop closes.

        Override this method to close async resources like HTTP clients,
        database connections, etc. This is called after _run_async() completes
        but before the event loop is shut down.

        Example:
            async def _cleanup_async(self):
                if self._http_client:
                    await self._http_client.aclose()
        """

    def _run(self):
        """
        Synchronous wrapper that creates an event loop and runs the async task.

        This method is called by the base task framework and handles:
        - Creating a new event loop for this thread
        - Running the async task
        - Calling async cleanup
        - Cleaning up the event loop

        You should not override this method unless you need custom event loop
        configuration.
        """
        # Create a new event loop for this thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            # Run the async task
            loop.run_until_complete(self._run_async())
        finally:
            # Run async cleanup before shutting down the loop
            try:
                loop.run_until_complete(self._cleanup_async())
            except Exception as e:
                logger.debug(f"Async cleanup warning: {e}")

            # Properly shutdown async generators and pending tasks
            # This prevents "Event loop is closed" errors from httpx/aiohttp clients
            try:
                # Shutdown async generators first
                loop.run_until_complete(loop.shutdown_asyncgens())

                # Cancel all pending tasks
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()

                # Wait for tasks to be cancelled (with timeout)
                if pending:
                    loop.run_until_complete(asyncio.wait(pending, timeout=5.0))

                # Shutdown default executor
                loop.run_until_complete(loop.shutdown_default_executor())
            except Exception as e:
                # Log but don't raise - we're in cleanup
                logger.debug(f"Event loop cleanup warning: {e}")
            finally:
                # Clean up the event loop
                loop.close()
                asyncio.set_event_loop(None)


# =============================================================================
# Service Class
# =============================================================================


class BaseService:
    """
    Abstract base class for services that manage and execute tasks.

    BaseService provides a framework for:
    - Task queueing with priority support
    - Multi-threaded or single-threaded execution
    - Task lifecycle management (start, monitor, timeout, cancel)
    - Graceful shutdown
    - Optional automatic task polling or passive/manual mode

    Services can operate in two modes:
    - **Active mode** (passive_mode=False): Automatically polls for new tasks
      via _query_tasks(). Useful for polling databases or external queues.
    - **Passive mode** (passive_mode=True): Tasks must be manually queued via
      queue_task(). Useful for on-demand processing.

    Attributes:
        service_name: Name of the service for logging
        max_retries: Maximum retries for operations (currently unused)
        max_wait_seconds: Maximum wait time for operations (currently unused)
        single_thread_mode: If True, run all tasks synchronously
        max_thread_count: Maximum concurrent task threads (0 = unlimited)
        max_outstanding_tasks: Maximum tasks in queue + running (0 = unlimited)
        query_task_time_gap_second: Seconds between task polls in active mode
        current_tasks: Dictionary of currently executing tasks
        queued_tasks: List of tasks waiting to execute
        last_query_task_time: Last time tasks were polled
        task_contexts: Storage for task-specific context data
        lock: Threading lock for shared state
        query_thread: Thread for polling tasks in multi-threaded mode
        shutting_down: True if service is shutting down
        passive_mode: If True, don't poll for tasks automatically

    Example:
        class MyService(BaseService):
            def __init__(self):
                super().__init__(service_name="MyService", passive_mode=True)

            def _query_tasks(self, max_count: int) -> list[BaseTask]:
                # Return new tasks to process (empty in passive mode)
                return []

            def _mark_task_as_not_processed(self, task: BaseTask):
                # Mark task as failed/incomplete on shutdown
                pass

            def _keep_task_alive_and_check_task_cancel(self, task: BaseTask) -> bool:
                # Return True to cancel task
                return False

        # Usage
        service = MyService()
        service.start()  # Start in background

        # Queue tasks
        config = BaseTaskConfig()
        task = MyTask(service_name="MyService", config=config)
        service.queue_task(task)

        # Wait for completion
        service.wait_for_completion(timeout=30)

        # Shutdown
        service.request_shutdown()
    """

    # Note: Do not set mutable defaults (dict, list, Lock) at class level
    # They will be shared across all instances! Initialize in __init__ instead.
    service_name: str
    max_retries: int = 100
    max_wait_seconds: int = 5
    single_thread_mode: bool = False
    max_thread_count: int = 5
    max_outstanding_tasks: int = 10
    query_task_time_gap_second: int = 5
    query_task_time_gap_second_original: int = 5
    shutting_down: bool = False
    passive_mode: bool = False

    def __init__(
        self,
        service_name: str,
        single_thread_mode: bool = False,
        passive_mode: bool = False,
        max_thread_count: int = 5,
        max_outstanding_tasks: int = 10,
    ):
        """
        Initialize the service.

        Args:
            service_name: Name for logging and identification
            single_thread_mode: If True, execute tasks synchronously
            passive_mode: If True, don't poll for tasks automatically
            max_thread_count: Maximum concurrent task threads
            max_outstanding_tasks: Maximum tasks in queue + running
        """
        self.service_name = service_name
        self.single_thread_mode = single_thread_mode
        self.passive_mode = passive_mode
        self.max_thread_count = max_thread_count
        self.max_outstanding_tasks = max_outstanding_tasks
        self.query_task_time_gap_second_original = self.query_task_time_gap_second

        # Initialize ALL mutable attributes to avoid sharing between instances
        # CRITICAL: Never set these as class-level defaults!
        self.current_tasks: dict[str, BaseTask] = {}
        self.queued_tasks: list[BaseTask] = []
        self.task_contexts: dict[str, dict[Any, Any]] = {}
        self.lock: threading.Lock = threading.Lock()
        self.query_thread: Optional[threading.Thread] = None
        self.last_query_task_time: Optional[datetime] = None
        self._service_thread: Optional[threading.Thread] = None
        self._shutdown_event: threading.Event = threading.Event()

    # =========================================================================
    # Abstract Methods (Must be implemented by subclasses)
    # =========================================================================

    @abstractmethod
    def _query_tasks(self, max_count: int) -> list[BaseTask]:
        """
        Query for new tasks to process (active mode only).

        In active mode, this method is called periodically to poll for new
        tasks from an external source (database, queue, API, etc.).

        In passive mode, return an empty list.

        Args:
            max_count: Maximum number of tasks to return (-1 = unlimited)

        Returns:
            List of new tasks to queue

        Example:
            def _query_tasks(self, max_count: int) -> list[BaseTask]:
                # Query database for pending tasks
                pending = db.query(Task).filter(status="pending").limit(max_count).all()
                return [MyTask(task_id=t.id, service_name=self.service_name) for t in pending]
        """
        raise NotImplementedError

    # =========================================================================
    # Public API Methods
    # =========================================================================

    def start(self):
        """
        Start the service in a background thread.

        The service will begin processing queued tasks and (in active mode)
        polling for new tasks. This method returns immediately.

        The service runs as a daemon thread, so it will automatically stop
        when the main program exits. For graceful shutdown, call
        request_shutdown().

        Example:
            service = MyService()
            service.start()
            # Service is now running in background
            # Queue tasks, etc.
            service.request_shutdown()
        """
        if self._service_thread is None or not self._service_thread.is_alive():
            self.shutting_down = False
            self._shutdown_event.clear()
            self._service_thread = threading.Thread(target=self.run, daemon=True)
            self._service_thread.start()
            mode = "passive mode" if self.passive_mode else "active mode"
            logger.info(f"[{self.service_name}]: Started in background ({mode})")

    def queue_task(self, task: BaseTask) -> bool:
        """
        Queue a task for processing.

        The task will be inserted into the queue based on its priority
        (higher priority tasks are processed first). The task will be
        executed when a thread becomes available.

        Args:
            task: The task to queue

        Returns:
            True if task was queued successfully, False if service is shutting down

        Example:
            task = MyTask(task_id="task_1", service_name="my_service")
            task.priority = 10  # High priority
            service.queue_task(task)
        """
        if self.shutting_down:
            logger.warning(
                f"[{self.service_name}]: Cannot queue task {task.task_id} - service is shutting down"
            )
            return False

        with self.lock:
            return self._queue_task(task)

    def get_task_by_id(self, task_id: str) -> Optional[BaseTask]:
        """
        Get a task by its ID (from current or queued tasks).

        Args:
            task_id: The task ID to look up

        Returns:
            The task if found, None otherwise

        Example:
            task = service.get_task_by_id("task_123")
            if task:
                print(f"Task status: {'running' if not task.terminated() else 'done'}")
        """
        with self.lock:
            # Check current tasks
            if task_id in self.current_tasks:
                return self.current_tasks[task_id]

            # Check queued tasks
            for task in self.queued_tasks:
                if task.task_id == task_id:
                    return task

        return None

    def get_queue_status(self) -> dict[str, Any]:
        """
        Get the current queue status.

        Returns:
            Dictionary with queue statistics:
            - current_tasks: Number of tasks currently executing
            - queued_tasks: Number of tasks waiting in queue
            - max_thread_count: Maximum concurrent threads
            - max_outstanding_tasks: Maximum total tasks
            - current_task_ids: List of task IDs currently executing
            - queued_task_ids: List of task IDs in queue

        Example:
            status = service.get_queue_status()
            print(f"Running: {status['current_tasks']}, Queued: {status['queued_tasks']}")
        """
        with self.lock:
            return {
                "current_tasks": len(self.current_tasks),
                "queued_tasks": len(self.queued_tasks),
                "max_thread_count": self.max_thread_count,
                "max_outstanding_tasks": self.max_outstanding_tasks,
                "current_task_ids": list(self.current_tasks.keys()),
                "queued_task_ids": [t.task_id for t in self.queued_tasks],
            }

    def wait_for_completion(self, timeout: Optional[float] = None) -> bool:
        """
        Wait for all tasks to complete.

        Blocks until all currently running and queued tasks have finished,
        or until the timeout is reached.

        Args:
            timeout: Optional timeout in seconds (None = wait forever)

        Returns:
            True if all tasks completed, False if timeout occurred

        Example:
            service.queue_task(task1)
            service.queue_task(task2)
            if service.wait_for_completion(timeout=30):
                print("All tasks completed")
            else:
                print("Timeout - some tasks still running")
        """
        start_time = time.time()

        while True:
            status = self.get_queue_status()
            if status["current_tasks"] == 0 and status["queued_tasks"] == 0:
                return True

            if timeout is not None and (time.time() - start_time) >= timeout:
                return False

            time.sleep(0.1)

    def request_shutdown(self, wait: bool = True, timeout: float = 5.0):
        """
        Request the service to shut down gracefully.

        The service will:
        1. Stop accepting new tasks
        2. Cancel all running tasks
        3. Mark all tasks as paused (for retry)
        4. Clean up resources

        Args:
            wait: If True, wait for shutdown to complete (default: True)
            timeout: Maximum time to wait for shutdown in seconds (default: 5.0)

        Example:
            service.request_shutdown()
            # Service will shut down gracefully and wait for completion
        """
        logger.info(f"Service {self.service_name} requested to shutdown")
        self.shutting_down = True
        self._shutdown_event.set()

        if wait and self._service_thread and self._service_thread.is_alive():
            logger.info(
                f"Service {self.service_name} waiting for shutdown (timeout={timeout}s)"
            )
            self._service_thread.join(timeout=timeout)
            if self._service_thread.is_alive():
                logger.warning(
                    f"Service {self.service_name} did not shut down within {timeout}s"
                )

    # =========================================================================
    # Task Context Management
    # =========================================================================

    def save_task_context_by_task_id(self, task_id: str, key: Any, task_context: Any):
        """
        Save context data for a task (thread-safe).

        Task contexts allow storing arbitrary data associated with a task
        that can be retrieved later. Useful for passing state between
        task lifecycle callbacks.

        Args:
            task_id: The task ID
            key: Context key
            task_context: Context value to store

        Example:
            service.save_task_context_by_task_id("task_1", "user_id", 12345)
            # Later...
            user_id = service.get_task_context_by_task_id("task_1", "user_id")
        """
        with self.lock:
            self.save_task_context_by_task_id_no_lock(
                task_id=task_id, key=key, task_context=task_context
            )

    def save_task_context_by_task_id_no_lock(
        self, task_id: str, key: Any, task_context: Any
    ):
        """
        Save task context without acquiring lock (internal use).

        Args:
            task_id: The task ID
            key: Context key
            task_context: Context value
        """
        if not task_id or not task_context:
            return

        if task_id not in self.task_contexts.keys():
            self.task_contexts[task_id] = {}
        self.task_contexts[task_id][key] = task_context
        logger.info(
            f"[{self.service_name}]: save task {task_id} context: {key} = {task_context}"
        )

    def get_task_context_by_task_id(self, task_id: str, key: Any) -> Any | None:
        """
        Get context data for a task (thread-safe).

        Args:
            task_id: The task ID
            key: Context key

        Returns:
            Context value if found, None otherwise

        Example:
            user_id = service.get_task_context_by_task_id("task_1", "user_id")
            if user_id:
                print(f"Task belongs to user {user_id}")
        """
        with self.lock:
            return self.get_task_context_by_task_id_no_lock(task_id=task_id, key=key)

    def get_task_context_by_task_id_no_lock(self, task_id: str, key: Any) -> Any | None:
        """
        Get task context without acquiring lock (internal use).

        Args:
            task_id: The task ID
            key: Context key

        Returns:
            Context value if found, None otherwise
        """
        if task_id not in self.task_contexts.keys():
            return None

        if key not in self.task_contexts[task_id].keys():
            return None

        context = self.task_contexts[task_id][key]
        logger.info(
            f"[{self.service_name}]: found task {task_id} context: {key} = {context}"
        )
        return context

    # =========================================================================
    # Internal Methods
    # =========================================================================

    def _submit_task(self, task: BaseTask) -> bool:
        """
        Submit a task for immediate execution (internal use).

        This moves a task from the queue to execution. Called automatically
        by the service loop. Database record creation happens in _queue_task().

        Args:
            task: The task to submit

        Returns:
            True if task was submitted, False if already running or shutting down
        """
        if self.shutting_down:
            return False
        logger.info(f"[{self.service_name}]: submit task: {task.task_id}")
        if task.task_id in self.current_tasks.keys():
            return False

        # DB record was already created in _queue_task()
        self.current_tasks[task.task_id] = task
        task.run(sync_run=self.single_thread_mode)
        return True

    def _queue_task(self, task: BaseTask) -> bool:
        """
        Internal method to add task to queue (no lock).

        Tasks are inserted based on priority (higher priority first).
        Creates database record if tracking is enabled, or loads existing record
        if task is being resumed (has db_task_id set).

        Args:
            task: The task to queue

        Returns:
            True if queued successfully, False if task should not be processed
        """
        # Handle database record creation/retrieval
        if task.enable_db_tracking:
            if not task.create_or_retrieve_db_record():
                logger.warning(
                    f"[{self.service_name}]: Task {task.task_id} skipped (already completed, deleted, or cancelled)"
                )
                return False

        # Insert task into queue based on priority
        inserted = False
        for i in range(0, len(self.queued_tasks)):
            if self.queued_tasks[i].priority < task.priority:
                self.queued_tasks.insert(i, task)
                inserted = True
                break
        if not inserted:
            self.queued_tasks.append(task)
        logger.info(f"[{self.service_name}]: queued task: {task.task_id}!")
        return True

    def _dequeue_task(self) -> BaseTask | None:
        """
        Internal method to remove and return next task from queue (no lock).

        Returns:
            Next task to execute, or None if queue is empty
        """
        if len(self.queued_tasks) > 0:
            task = self.queued_tasks.pop(0)
            logger.info(f"[{self.service_name}]: dequeued task {task.task_id}")
            return task
        else:
            return None

    def _get_outstanding_task_count(self):
        """
        Get total number of tasks (running + queued).

        Returns:
            Total task count
        """
        with self.lock:
            return len(self.current_tasks) + len(self.queued_tasks)

    def _query_tasks_worker(self):
        """
        Worker method to query for new tasks (active mode only).

        Called periodically by the query thread. Checks if we have capacity
        for more tasks and calls _query_tasks() if so.
        """
        try:
            if self.shutting_down or self.passive_mode:
                return
            max_query_count = 0
            if self.max_outstanding_tasks <= 0:
                max_query_count = -1
            elif self._get_outstanding_task_count() < self.max_outstanding_tasks:
                max_query_count = (
                    self.max_outstanding_tasks - self._get_outstanding_task_count()
                )
            if max_query_count != 0:
                now = get_utcnow()
                if (
                    self.last_query_task_time is None
                    or (now - self.last_query_task_time).total_seconds()
                    >= self.query_task_time_gap_second
                ):
                    self.last_query_task_time = now
                    new_tasks = self._query_tasks(max_count=max_query_count)
                    if new_tasks:
                        with self.lock:
                            for new_task in new_tasks:
                                self._queue_task(new_task)

                    self.query_task_time_gap_second = (
                        self.query_task_time_gap_second_original
                    )
        except Exception as e:
            if self.query_task_time_gap_second <= 0:
                self.query_task_time_gap_second = 2
            if self.query_task_time_gap_second < 30:
                self.query_task_time_gap_second *= 2
                if self.query_task_time_gap_second > 30:
                    self.query_task_time_gap_second = 30
            logger.error(f"!! Service {self.service_name} Exception !!\n{str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                logger.error(f"  {tb}")

    def _query_tasks_thread(self):
        """
        Background thread for querying tasks (active mode only).

        Runs continuously until service shuts down, calling
        _query_tasks_worker() to poll for new tasks.
        """
        while not self._shutdown_event.is_set():
            try:
                if self.shutting_down:
                    return
                self._query_tasks_worker()
                # Sleep briefly to avoid tight loop and allow shutdown to proceed
                time.sleep(0.1)
            except Exception as e:
                logger.error(f"!! Service {self.service_name} Exception !!\n{str(e)}")
                tbs = traceback.format_exc().split("\n")
                for tb in tbs:
                    logger.error(f"  {tb}")
                # Sleep on error to avoid spinning
                time.sleep(1.0)

    def _run(self):
        """
        Main service loop.

        Handles:
        - Querying for new tasks (single-threaded mode)
        - Submitting queued tasks for execution
        - Monitoring task completion and timeouts
        - Handling task cancellation
        - Processing follow-up tasks
        - Graceful shutdown
        """
        while True:
            try:
                if self.shutting_down:
                    logger.info(f"Service {self.service_name} shuts down!")
                    self._handle_shutdown()
                    return

                # Query the work in single thread mode. In multi-thread mode, query work
                # is done by another thread.
                if self.single_thread_mode:
                    self._query_tasks_worker()

                # see if we can submit queued tasks for processing
                with self.lock:
                    requeue = []
                    while True:
                        if (
                            self.max_thread_count <= 0
                            or len(self.current_tasks) < self.max_thread_count
                        ):
                            task = self._dequeue_task()
                            if task:
                                if not self._submit_task(task):
                                    requeue += [task]
                            else:
                                break
                        else:
                            break

                    # Put back the ones that cannot be submitted right now.
                    if len(requeue) > 0:
                        for requeue_task in requeue:
                            self._queue_task(requeue_task)

                # Handle outstanding tasks
                outstanding_task_ids = [k for k in self.current_tasks.keys()]
                for task_id in outstanding_task_ids:
                    if task_id not in self.current_tasks.keys():
                        continue
                    task = self.current_tasks[task_id]
                    if task.terminated():
                        self.current_tasks.pop(task_id)
                        logger.info(
                            f"[{self.service_name}]: task {task_id} finished processing, current in-progress task count is {len(self.current_tasks)}"
                        )
                        if task.graceful_terminated() and task.follow_up_tasks:
                            logger.info(
                                f"{self.service_name} task {task_id} has follow up task(s)!"
                            )
                            for new_task in task.follow_up_tasks:
                                self._queue_task(new_task)
                    else:
                        if task.task_start_time and task.thread:
                            diff = task.task_running_time_seconds()
                            if task.task_timed_out() or not task.keep_alive():
                                self.current_tasks.pop(task_id)
                                logger.info(
                                    f"[{self.service_name}]: task {task_id} submitted at {task.task_start_time} cancelled after {diff} seconds!"
                                )
                                task.cancel()
                    if task.terminated():
                        task.thread = None

                # Keep alive queued tasks
                with self.lock:
                    queued_tasks_dup = [k for k in self.queued_tasks]
                    queued_tasks_valid = []
                    for task in queued_tasks_dup:
                        if not task.keep_alive():
                            logger.info(
                                f"[{self.service_name}]: task {task.task_id} cancelled while being queued!"
                            )
                            task.cancel()
                            continue
                        queued_tasks_valid += [task]
                    self.queued_tasks = queued_tasks_valid

                # Sleep briefly to avoid tight loop
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"!! Service {self.service_name} Exception !!\n{str(e)}")
                tbs = traceback.format_exc().split("\n")
                for tb in tbs:
                    logger.error(f"  {tb}")

                raise

    def run(self):
        """
        Main entry point of the service.

        Starts the service loop. In multi-threaded mode, also starts the
        query thread. This method blocks until the service shuts down.

        Usually you should call start() instead, which runs this in a
        background thread.
        """
        self.shutting_down = False
        if not self.single_thread_mode and not self.query_thread:
            self.query_thread = threading.Thread(
                target=self._query_tasks_thread, daemon=True
            )
            self.query_thread.start()

        self._run()

    def _handle_shutdown(self):
        """
        Handle graceful shutdown.

        Cancels all running tasks, marks all tasks as paused,
        and cleans up resources.
        """
        # Terminate the query task thread if present (don't join - it's daemon)
        if self.query_thread:
            self.query_thread = None

        # Get snapshots of tasks with lock, then process without holding lock
        with self.lock:
            current_task_list = list(self.current_tasks.values())
            queued_task_list = list(self.queued_tasks)

        # Cancel all active tasks and wait briefly for threads to finish
        task_threads = []
        for task in current_task_list:
            logger.info(
                f"[{self.service_name}]: shutting down with task {task.task_id} in progress, mark it as paused!"
            )
            task.cancel()
            if task.thread and task.thread.is_alive():
                task_threads.append(task.thread)
            task.mark_as_paused()

        # Wait briefly for task threads to finish (max 2 seconds total)
        if task_threads:
            logger.info(
                f"[{self.service_name}]: waiting for {len(task_threads)} task threads to finish"
            )
            for thread in task_threads:
                thread.join(timeout=0.5)

        # Mark all queued tasks as paused
        for task in queued_task_list:
            logger.info(
                f"[{self.service_name}]: shutting down with task {task.task_id} queued, mark it as paused!"
            )
            task.mark_as_paused()

        # Clear all tasks with lock
        with self.lock:
            self.current_tasks.clear()
            self.queued_tasks.clear()

        logger.info(f"Service {self.service_name} shutdown completed")
