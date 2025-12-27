"""
Service Manager - Singleton for managing service lifecycle and task distribution

This module provides a centralized singleton manager for:
1. Service registration and instantiation
2. Service lifecycle management (start, stop, restart)
3. Task submission and forwarding to local/remote services
4. Async task completion waiting
5. Dependency cycle detection

Example:
    # Register a service
    from service_management.service_manager import ServiceManager
    from services import SERVICE_CRAWLER
    from services.crawler_service import CrawlerService

    manager = ServiceManager()
    manager.register_service(SERVICE_CRAWLER, CrawlerService)

    # Get and start service
    crawler = manager.get_service(SERVICE_CRAWLER)

    # Submit task
    task_id = await manager.submit_task(SERVICE_CRAWLER, my_task)

    # Wait for completion
    result = await manager.wait_for_task(task_id)
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, Optional

from services.base_service import BaseService, BaseTask
from utilities import logger


class ServiceManager:
    """
    Singleton manager for service lifecycle and task distribution.

    The ServiceManager maintains a registry of service classes, manages
    their instantiation and lifecycle, and handles task submission with
    support for both local and remote service execution.

    Features:
    - Singleton pattern ensures single manager instance
    - Service registration with dependency tracking
    - Lazy service instantiation
    - Lifecycle management (start/stop/restart)
    - Task submission with local/remote routing
    - Async task result waiting
    - Dependency cycle detection

    Thread Safety:
    - All operations are thread-safe using internal locking
    - Can be safely called from multiple threads
    """

    _instance: Optional[ServiceManager] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls):
        """
        Implement singleton pattern with thread-safe instance creation.
        """
        if cls._instance is None:
            with cls._lock:
                # Double-check locking pattern
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        """
        Initialize the service manager (only runs once due to singleton).
        """
        # Only initialize once
        if self._initialized:
            return

        self._initialized = True

        # Service registry: name -> service class
        self._service_registry: dict[str, type[BaseService]] = {}

        # Service factory functions: name -> factory callable
        self._service_factories: dict[str, Callable[[], BaseService]] = {}

        # Running service instances: name -> service instance
        self._services: dict[str, BaseService] = {}

        # Service dependencies: name -> set of dependency names
        self._dependencies: dict[str, set[str]] = {}

        # Task tracking: task_id -> (service_name, task, future)
        self._tasks: dict[str, tuple[str, BaseTask, asyncio.Future]] = {}

        # Completed task retention: task_id -> (task, completion_time)
        # Keep completed tasks for polling/retrieval
        self._completed_tasks: dict[str, tuple[BaseTask, float]] = {}
        self._completed_task_retention_seconds = 300  # 5 minutes

        # Remote service configuration: name -> remote endpoint
        self._remote_services: dict[str, str] = {}

        # Thread lock for state management
        self._state_lock = threading.Lock()

        # Task monitoring thread
        self._monitor_thread: Optional[threading.Thread] = None
        self._monitor_running = False
        self._monitor_event = threading.Event()  # Reusable event for sleep

        # Auto-register all existing services
        self._auto_register_services()

        logger.info("ServiceManager initialized")

    def _auto_register_services(self):
        """
        Automatically discover and register all existing services.

        Uses lazy factory functions to avoid circular imports.
        Services are only imported when they are first accessed.
        """

    # =========================================================================
    # Service Registration
    # =========================================================================

    def register_service(
        self,
        name: str,
        service_class: Optional[type[BaseService]] = None,
        factory: Optional[Callable[[], BaseService]] = None,
        dependencies: Optional[list[str]] = None,
    ) -> ServiceManager:
        """
        Register a service class or factory function.

        Services can be registered either by providing the service class
        directly or by providing a factory function that creates the service.

        Args:
            name: Unique name for the service
            service_class: Service class to instantiate (mutually exclusive with factory)
            factory: Factory function that returns service instance
            dependencies: List of service names this service depends on

        Returns:
            Self for method chaining

        Raises:
            ValueError: If service already registered, no class/factory provided,
                       or both class and factory provided

        Example:
            from services import SERVICE_CRAWLER

            manager.register_service(SERVICE_CRAWLER, CrawlerService)

            # Or with factory
            def create_crawler():
                return CrawlerService(custom_config)
            manager.register_service(SERVICE_CRAWLER, factory=create_crawler)

            # With dependencies
            manager.register_service("analyzer", AnalyzerService, dependencies=[SERVICE_CRAWLER])
        """
        with self._state_lock:
            # Validation
            if name in self._service_registry or name in self._service_factories:
                raise ValueError(f"Service '{name}' is already registered")

            if service_class is None and factory is None:
                raise ValueError("Must provide either service_class or factory")

            if service_class is not None and factory is not None:
                raise ValueError("Cannot provide both service_class and factory")

            # Register service
            if service_class is not None:
                self._service_registry[name] = service_class
                logger.info(f"Registered service '{name}': {service_class.__name__}")
            else:
                self._service_factories[name] = factory  # type: ignore
                logger.info(f"Registered service '{name}' with factory")

            # Register dependencies
            if dependencies:
                self._dependencies[name] = set(dependencies)
                logger.info(f"Service '{name}' depends on: {dependencies}")

                # Check for dependency cycles
                self._check_dependency_cycles(name)
            else:
                self._dependencies[name] = set()

        return self

    def _check_dependency_cycles(self, service_name: str):
        """
        Check for circular dependencies starting from given service.

        Uses depth-first search to detect cycles in the dependency graph.

        Args:
            service_name: Service to start checking from

        Raises:
            ValueError: If a dependency cycle is detected
        """
        visited: set[str] = set()
        path: list[str] = []

        def dfs(name: str) -> bool:
            """
            Depth-first search for cycle detection.

            Returns:
                True if cycle detected, False otherwise
            """
            if name in path:
                # Found a cycle
                cycle_start = path.index(name)
                cycle = path[cycle_start:] + [name]
                raise ValueError(f"Dependency cycle detected: {' -> '.join(cycle)}")

            if name in visited:
                return False

            visited.add(name)
            path.append(name)

            # Check dependencies
            if name in self._dependencies:
                for dep in self._dependencies[name]:
                    dfs(dep)

            path.pop()
            return False

        dfs(service_name)

    def register_remote_service(self, name: str, endpoint: str) -> ServiceManager:
        """
        Register a remote service endpoint.

        Remote services are not instantiated locally. Tasks submitted to
        remote services will be forwarded to the remote endpoint.

        Args:
            name: Service name
            endpoint: Remote endpoint URL

        Returns:
            Self for method chaining

        Example:
            manager.register_remote_service("gpu_service", "http://gpu-server:8080")
        """
        with self._state_lock:
            self._remote_services[name] = endpoint
            logger.info(f"Registered remote service '{name}' at {endpoint}")

        return self

    # =========================================================================
    # Service Lifecycle Management
    # =========================================================================

    def get_service(self, name: str, auto_start: bool = True) -> BaseService:
        """
        Get a service instance by name, creating and starting it if needed.

        Services are instantiated lazily on first access. Dependencies are
        automatically started before the requested service.

        Args:
            name: Service name
            auto_start: If True, automatically start the service

        Returns:
            Service instance

        Raises:
            ValueError: If service not registered or is remote

        Example:
            from services import SERVICE_CRAWLER

            crawler = manager.get_service(SERVICE_CRAWLER)
            # Service is now running and ready to accept tasks
        """
        # Check if service already exists (fast path with lock)
        with self._state_lock:
            # Check if it's a remote service
            if name in self._remote_services:
                raise ValueError(
                    f"Service '{name}' is remote (at {self._remote_services[name]}). "
                    "Use submit_task() to forward tasks to remote services."
                )

            # Return existing instance if already created
            if name in self._services:
                return self._services[name]

            # Check if service is registered
            if (
                name not in self._service_registry
                and name not in self._service_factories
            ):
                raise ValueError(f"Service '{name}' is not registered")

            # Get dependencies list while holding lock
            dependencies = list(self._dependencies.get(name, []))

        # Start dependencies WITHOUT holding lock (prevents deadlock)
        for dep in dependencies:
            logger.info(f"Starting dependency '{dep}' for service '{name}'")
            self.get_service(dep, auto_start=True)

        # Now create and register the service
        with self._state_lock:
            # Double-check service wasn't created by another thread
            if name in self._services:
                return self._services[name]

            # Create service instance
            if name in self._service_factories:
                service = self._service_factories[name]()
                logger.info(f"Created service '{name}' via factory")
            else:
                # Try to instantiate with service_name parameter if supported
                try:
                    service = self._service_registry[name](service_name=name)
                except TypeError:
                    # Fallback to no-arg constructor if service_name not accepted
                    service = self._service_registry[name]()  # type: ignore[call-arg]
                logger.info(f"Created service '{name}': {service.__class__.__name__}")

            self._services[name] = service

        # Start service OUTSIDE of lock to avoid blocking
        if auto_start:
            service.start()
            logger.info(f"Started service '{name}'")

        return service

    def start_service(self, name: str) -> BaseService:
        """
        Start a service by name.

        Args:
            name: Service name

        Returns:
            Started service instance

        Example:
            from services import SERVICE_CRAWLER

            manager.start_service(SERVICE_CRAWLER)
        """
        service = self.get_service(name, auto_start=False)
        service.start()
        logger.info(f"Started service '{name}'")
        return service

    def stop_service(self, name: str):
        """
        Stop a running service.

        Args:
            name: Service name

        Example:
            from services import SERVICE_CRAWLER

            manager.stop_service(SERVICE_CRAWLER)
        """
        # Get service reference without holding lock
        service = None
        with self._state_lock:
            if name in self._services:
                service = self._services[name]

        # Stop service outside of lock to avoid deadlock
        if service is not None:
            # Request shutdown with longer timeout to allow background threads to finish
            service.request_shutdown(wait=True, timeout=10.0)

            # Wait briefly for service to acknowledge shutdown
            import time

            time.sleep(0.5)

            logger.info(f"Stopped service '{name}'")

    def restart_service(self, name: str) -> BaseService:
        """
        Restart a service (stop and start).

        Args:
            name: Service name

        Returns:
            Restarted service instance

        Example:
            from services import SERVICE_CRAWLER

            manager.restart_service(SERVICE_CRAWLER)
        """
        self.stop_service(name)

        # Wait for service to shut down
        with self._state_lock:
            if name in self._services:
                self._services[name]
                # Remove from services dict so get_service will create new instance
                del self._services[name]

        return self.start_service(name)

    def stop_all_services(self):
        """
        Stop all running services.

        Services are stopped in reverse dependency order (dependents before dependencies).

        Example:
            manager.stop_all_services()
        """
        # Get service names while holding lock
        with self._state_lock:
            service_names = list(self._services.keys())
            # Sort so services with no dependents come first
            service_names.sort(
                key=lambda name: len(
                    [s for s in self._dependencies.values() if name in s]
                )
            )

        # Stop services WITHOUT holding lock to avoid deadlock
        for name in service_names:
            self.stop_service(name)

        logger.info("Stopped all services")

    def get_service_status(self, name: str) -> dict[str, Any]:
        """
        Get status information for a service.

        Args:
            name: Service name

        Returns:
            Dictionary with status information:
            - registered: True if service is registered
            - running: True if service is running
            - remote: True if service is remote
            - endpoint: Remote endpoint if remote
            - queue_status: Queue status if running locally
            - dependencies: List of dependency names

        Example:
            from services import SERVICE_CRAWLER

            status = manager.get_service_status(SERVICE_CRAWLER)
            if status["running"]:
                print(f"Queue: {status['queue_status']}")
        """
        # Get service reference while holding lock
        service = None
        with self._state_lock:
            status: dict[str, Any] = {
                "registered": False,
                "running": False,
                "remote": False,
                "dependencies": [],
            }

            # Check if registered
            if name in self._service_registry or name in self._service_factories:
                status["registered"] = True

            # Check if remote
            if name in self._remote_services:
                status["remote"] = True
                status["endpoint"] = self._remote_services[name]

            # Check if running
            if name in self._services:
                status["running"] = True
                service = self._services[name]

            # Get dependencies
            if name in self._dependencies:
                status["dependencies"] = list(self._dependencies[name])

        # Call service methods outside of lock to avoid nested locking
        if service is not None:
            status["queue_status"] = service.get_queue_status()

        return status

    # =========================================================================
    # Task Submission and Tracking
    # =========================================================================

    async def submit_task(
        self,
        service_name: str,
        task: BaseTask,
        timeout: Optional[float] = None,
    ) -> str:
        """
        Submit a task to a service (local or remote).

        For local services, the task is queued directly. For remote services,
        the task is forwarded to the remote endpoint (placeholder for now).

        Args:
            service_name: Name of service to handle the task
            task: Task to submit
            timeout: Optional timeout in seconds for remote submission

        Returns:
            Task ID

        Raises:
            ValueError: If service not registered

        Example:
            from services import SERVICE_CRAWLER

            task = CrawlTask(task_id="task_1", url="https://example.com", service_name=SERVICE_CRAWLER)
            task_id = await manager.submit_task(SERVICE_CRAWLER, task)
            result = await manager.wait_for_task(task_id)
        """
        # Check if service is registered (with lock)
        with self._state_lock:
            is_local = (
                service_name in self._service_registry
                or service_name in self._service_factories
            )
            is_remote = service_name in self._remote_services

            if not is_local and not is_remote:
                raise ValueError(f"Service '{service_name}' is not registered")

        # Handle local service
        if is_local:
            # Get service WITHOUT holding lock (prevents deadlock)
            service = self.get_service(service_name)

            # Queue the task
            service.queue_task(task)
            logger.info(
                f"Submitted task '{task.task_id}' to local service '{service_name}'"
            )

            # Create future and register task with lock
            with self._state_lock:
                loop = asyncio.get_event_loop()
                future: asyncio.Future = loop.create_future()
                self._tasks[task.task_id] = (service_name, task, future)

                # Start monitoring thread if not running
                if not self._monitor_running:
                    self._start_task_monitor()

            return task.task_id

        # Handle remote service
        else:
            with self._state_lock:
                endpoint = self._remote_services[service_name]

            logger.info(
                f"Forwarding task '{task.task_id}' to remote service "
                f"'{service_name}' at {endpoint}"
            )

            # TODO: Implement remote task forwarding
            # This is a placeholder for future implementation
            # In a real implementation, you would:
            # 1. Serialize the task
            # 2. Send HTTP/gRPC request to remote endpoint
            # 3. Track remote task ID for result retrieval

            raise NotImplementedError(
                f"Remote task forwarding to {endpoint} is not yet implemented. "
                "This is a placeholder for future implementation."
            )

    def get_task_by_id(self, task_id: str) -> Optional[BaseTask]:
        """
        Get a task by its task ID.

        Checks both active tasks and recently completed tasks (retained for 5 minutes).

        Args:
            task_id: Task ID to look up

        Returns:
            Task object if found, None otherwise

        Example:
            task = manager.get_task_by_id("my-task-uuid")
            if task:
                print(f"Task state: completed={task.completed}, cancelled={task.cancelled}")
        """
        with self._state_lock:
            # Check active tasks first
            if task_id in self._tasks:
                _, task, _ = self._tasks[task_id]
                return task

            # Check completed tasks cache
            if task_id in self._completed_tasks:
                task, _ = self._completed_tasks[task_id]
                return task

            return None

    async def wait_for_task(
        self,
        task_id: str,
        timeout: Optional[float] = None,
    ) -> Any:
        """
        Wait for a task to complete and return its result.

        Args:
            task_id: Task ID returned from submit_task()
            timeout: Optional timeout in seconds

        Returns:
            Task result

        Raises:
            asyncio.TimeoutError: If timeout is exceeded
            KeyError: If task ID was never submitted
            RuntimeError: If task was already completed and cleaned up

        Example:
            from services import SERVICE_CRAWLER

            task_id = await manager.submit_task(SERVICE_CRAWLER, task)
            result = await manager.wait_for_task(task_id, timeout=60)
            print(f"Task result: {result}")
        """
        with self._state_lock:
            if task_id not in self._tasks:
                raise KeyError(
                    f"Task '{task_id}' not found. It may have already completed "
                    "and been cleaned up, or was never submitted."
                )

            _, _, future = self._tasks[task_id]

        if timeout is not None:
            result = await asyncio.wait_for(future, timeout=timeout)
        else:
            result = await future

        return result

    def _start_task_monitor(self):
        """
        Start background thread to monitor task completion.

        This thread polls tracked tasks and resolves their futures when complete.
        """
        if self._monitor_running:
            return

        self._monitor_running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_tasks, daemon=True, name="ServiceManager-TaskMonitor"
        )
        self._monitor_thread.start()
        logger.info("Started task monitoring thread")

    def _monitor_tasks(self):
        """
        Background thread that monitors task completion.

        Polls all tracked tasks and resolves their futures when they complete.
        """
        while self._monitor_running:
            try:
                completed_tasks: list[str] = []

                # Copy tasks dict to avoid holding lock during iteration
                with self._state_lock:
                    tasks_snapshot = list(self._tasks.items())

                # Check each task without holding the lock
                for task_id, (service_name, task, future) in tasks_snapshot:
                    try:
                        if task.terminated():
                            # Task completed - resolve future
                            if not future.done():
                                try:
                                    loop = future.get_loop()

                                    if task.cancelled:
                                        loop.call_soon_threadsafe(
                                            future.set_exception,
                                            asyncio.CancelledError(
                                                f"Task {task_id} was cancelled"
                                            ),
                                        )
                                    else:
                                        loop.call_soon_threadsafe(
                                            future.set_result, task.result
                                        )

                                    logger.info(
                                        f"Task '{task_id}' completed with result: {task.result}"
                                    )
                                except RuntimeError as e:
                                    # Event loop may be closed
                                    logger.warning(
                                        f"Failed to resolve future for task '{task_id}': {e}"
                                    )

                            completed_tasks.append(task_id)
                    except Exception as e:
                        logger.error(f"Error processing task '{task_id}': {e}")

                # Move completed tasks to retention cache
                if completed_tasks:
                    import time

                    current_time = time.time()
                    with self._state_lock:
                        for task_id in completed_tasks:
                            if task_id in self._tasks:
                                _, task, _ = self._tasks[task_id]
                                # Move to completed tasks cache for retention
                                self._completed_tasks[task_id] = (task, current_time)
                                del self._tasks[task_id]

                        # Clean up expired completed tasks
                        expired_tasks = [
                            tid
                            for tid, (
                                _,
                                completion_time,
                            ) in self._completed_tasks.items()
                            if current_time - completion_time
                            > self._completed_task_retention_seconds
                        ]
                        for tid in expired_tasks:
                            del self._completed_tasks[tid]

                # Sleep briefly before next check using reusable event
                self._monitor_event.wait(0.1)

            except Exception as e:
                logger.error(f"Error in task monitor: {e}")
                import traceback

                traceback.print_exc()

    def stop_task_monitor(self):
        """
        Stop the task monitoring thread.

        Example:
            manager.stop_task_monitor()
        """
        self._monitor_running = False
        # Wake up the monitor thread if it's sleeping
        self._monitor_event.set()
        # Don't join daemon threads - they'll stop on their own
        # Joining can cause deadlocks if thread is waiting for locks
        logger.info("Stopped task monitoring thread")

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def list_services(self) -> dict[str, dict[str, Any]]:
        """
        List all registered services with their status.

        Returns:
            Dictionary mapping service names to status info

        Example:
            services = manager.list_services()
            for name, info in services.items():
                print(f"{name}: {'running' if info['running'] else 'stopped'}")
        """
        # Get service names while holding lock
        with self._state_lock:
            all_service_names = set()
            all_service_names.update(self._service_registry.keys())
            all_service_names.update(self._service_factories.keys())
            all_service_names.update(self._remote_services.keys())

        # Call get_service_status outside of lock to avoid deadlock
        # (get_service_status acquires _state_lock internally)
        result = {}
        for name in all_service_names:
            result[name] = self.get_service_status(name)

        return result

    @classmethod
    def reset(cls):
        """
        Reset the singleton instance (for testing only).

        WARNING: This should only be used in test teardown.

        Example:
            def teardown():
                ServiceManager.reset()
        """
        instance = None
        with cls._lock:
            if cls._instance is not None:
                # Release lock before stopping to avoid deadlock
                instance = cls._instance
                cls._instance = None

        # Stop services outside the lock
        if instance is not None:
            instance.stop_task_monitor()
            instance.stop_all_services()

            # Give threads time to fully clean up before Python teardown
            import time

            time.sleep(0.5)

            # Clear services dict after stopping
            with cls._lock:
                instance._services.clear()
                instance._service_registry.clear()
                instance._service_factories.clear()
                instance._dependencies.clear()
                instance._remote_services.clear()
                instance._tasks.clear()

            logger.info("ServiceManager reset")
