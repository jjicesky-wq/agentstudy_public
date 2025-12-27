"""
Base API Server class for creating FastAPI applications with common functionality.

This base class provides:
- CORS middleware configuration
- Health check endpoints
- Authentication endpoints (login/register)
- Client IP extraction utilities
- Lifespan management
- Service configuration reload
"""

import asyncio
from contextlib import asynccontextmanager
from fnmatch import fnmatch
from typing import Annotated, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from db.database import get_db_session
from server.apis.authentication import (
    api_login_user,
    api_register_user,
    api_revalidate_token,
    db_helper_validate_and_use_invite_code,
    get_token_from_header,
)
from server.apis.service_config import db_helper_get_configs_by_service
from server.schemas.authentication import InviteRegistrationRequest, TokenResponse
from server.schemas.service_config import ServiceConfigInfo
from utilities import logger


def get_service_configs(
    user_id: int, service_name: str
) -> dict[str, ServiceConfigInfo]:
    """
    Utility routine to retrieve service configurations by service name.

    This is a convenience function that fetches all configurations for a given
    service and returns them as a dictionary keyed by config_key for easy access.

    Args:
        user_id: User ID who owns the configurations
        service_name: Name of the service (e.g., "digest", "crawler", "content")

    Returns:
        Dictionary mapping config_key to ServiceConfigInfo
        Empty dict if no configurations found or error occurs

    Example:
        configs = get_service_configs(user_id=1, service_name="digest")
        default_voice = configs.get("default_voice")
        if default_voice:
            print(f"Voice: {default_voice.config_value}")
    """
    try:
        session_gen = get_db_session()
        session = next(session_gen)
        try:
            response = db_helper_get_configs_by_service(
                session=session,
                user_id=user_id,
                service_name=service_name,
            )

            if response.success:
                # Convert list to dict keyed by config_key
                return {config.config_key: config for config in response.configs}
            else:
                logger.warning(
                    f"Failed to get configs for service '{service_name}': {response.message}"
                )
                return {}

        finally:
            try:
                next(session_gen)
            except StopIteration:
                pass

    except Exception as e:
        logger.error(f"Error getting service configs: {e}")
        import traceback

        logger.error(traceback.format_exc())
        return {}


def get_service_config_value(
    user_id: int, service_name: str, config_key: str, default: str = ""
) -> str:
    """
    Utility routine to retrieve a single service configuration value.

    Convenience function to get just the value of a specific configuration.
    Returns the default if the configuration is not found.

    Args:
        user_id: User ID who owns the configuration
        service_name: Name of the service (e.g., "digest", "crawler", "content")
        config_key: Configuration key to retrieve
        default: Default value to return if config not found

    Returns:
        Configuration value as string, or default if not found

    Example:
        voice = get_service_config_value(
            user_id=1,
            service_name="digest",
            config_key="default_voice",
            default="alloy"
        )
        print(f"Using voice: {voice}")
    """
    configs = get_service_configs(user_id=user_id, service_name=service_name)
    config = configs.get(config_key)
    return config.config_value if config else default


class BaseAPIServer:
    """
    Base class for FastAPI servers with common endpoints and middleware.

    This class provides standard endpoints like health checks, authentication,
    and common middleware setup. Inherit from this class to create custom servers
    with additional endpoints.

    Attributes:
        app: The FastAPI application instance
        title: Application title for API docs
        docs_url: URL path for Swagger docs
        allowed_origins: List of allowed CORS origins

    Example:
        ```python
        class MyCustomServer(BaseAPIServer):
            def __init__(self):
                super().__init__(
                    title="My Custom API",
                    docs_url="/api/docs"
                )
                # Add custom routes
                self.add_custom_routes()

            def add_custom_routes(self):
                @self.app.get("/custom")
                def custom_endpoint():
                    return {"message": "custom"}

        # Use the server
        server = MyCustomServer()
        app = server.app
        ```
    """

    def __init__(
        self,
        title: str = "API Server",
        docs_url: str = "/docs",
        allowed_origins: Optional[list[str]] = None,
        enable_auth: bool = True,
    ):
        """
        Initialize the base API server.

        Args:
            title: Application title for API documentation
            docs_url: URL path for Swagger documentation
            allowed_origins: List of allowed CORS origins (default: ["*"])
            enable_auth: Whether to enable authentication endpoints (default: True)
            enable_files: Whether to enable file endpoints (default: True)
        """
        self.title = title
        self.docs_url = docs_url
        self.allowed_origins = allowed_origins or ["*"]
        self.enable_auth = enable_auth

        # Service manager instance (will be initialized on startup)
        self.service_manager = None

        # Config reload task management
        self._config_reload_task = None
        self._shutdown_event = None
        self._service_lock_file = None

        # Create FastAPI app with lifespan
        self.app = FastAPI(
            docs_url=self.docs_url, lifespan=self._lifespan, title=self.title
        )

        # Setup middleware
        self._setup_middleware()

        # Add common routes
        self._add_common_routes()

        # Add authentication routes if enabled
        if self.enable_auth:
            self._add_auth_routes()

    @asynccontextmanager
    async def _lifespan(self, app: FastAPI):
        """
        Lifespan context manager for startup/shutdown events.

        Override this in subclasses to add custom startup/shutdown logic:

        Example:
            ```python
            @asynccontextmanager
            async def _lifespan(self, app: FastAPI):
                # Startup
                print("Starting up...")
                await self.initialize_services()

                yield

                # Shutdown
                await self.cleanup_services()
                print("Shutting down...")
            ```
        """
        # Startup
        await self.on_startup()

        yield

        # Shutdown
        await self.on_shutdown()

    def get_service_lock_name(self) -> Optional[str]:
        """
        Get the name for service lock file.

        Override this in subclasses to enable single-instance service initialization.
        Returns None by default (no locking).

        Returns:
            Lock file name (e.g., "content_service.lock") or None

        Example:
            ```python
            class MyServer(BaseAPIServer):
                def get_service_lock_name(self) -> Optional[str]:
                    return "my_service.lock"
            ```
        """
        return None

    def get_service_configs(self) -> dict:
        """
        Get service configurations to load on startup.

        Override this in subclasses to return service-specific configurations.
        Returns empty dict by default.

        Returns:
            Dictionary of configurations keyed by config name

        Example:
            ```python
            class ContentServer(BaseAPIServer):
                def get_service_configs(self) -> dict:
                    return get_default_content_configs()
            ```
        """
        return {}

    def apply_service_configs(self, configs: dict):
        """
        Apply loaded configurations to services.

        Override this in subclasses to apply configs to specific services.
        Does nothing by default.

        Args:
            configs: Dictionary of configurations from get_service_configs()

        Example:
            ```python
            class ContentServer(BaseAPIServer):
                def apply_service_configs(self, configs: dict):
                    content_service = self.service_manager.get_service(SERVICE_CONTENT)
                    for config in configs.values():
                        content_service.add_content_config(config)
            ```
        """

    def get_config_reload_interval(self) -> Optional[int]:
        """
        Get interval (in seconds) for periodic config reload.

        Override this in subclasses to enable automatic config reloading.
        Returns None by default (no automatic reload).

        Returns:
            Reload interval in seconds or None

        Example:
            ```python
            class ContentServer(BaseAPIServer):
                def get_config_reload_interval(self) -> Optional[int]:
                    return 30 * 60  # 30 minutes
            ```
        """
        return None

    async def _reload_configs_periodically(self):
        """
        Background task to reload configurations periodically.

        This is a generic implementation that:
        1. Waits for the configured reload interval
        2. Calls get_service_configs() to fetch new configs
        3. Calls apply_service_configs() to apply them
        4. Repeats until shutdown
        """
        if self._shutdown_event is None:
            logger.error("Shutdown event not initialized, cannot run reload task")
            return

        reload_interval = self.get_config_reload_interval()
        if reload_interval is None:
            logger.warning("Config reload interval not set, reload task will not run")
            return

        logger.info(f"Starting config reload task (interval: {reload_interval}s)")

        while not self._shutdown_event.is_set():
            try:
                # Wait for reload interval or until shutdown
                await asyncio.wait_for(
                    self._shutdown_event.wait(), timeout=reload_interval
                )
                # If we get here, shutdown was triggered
                break
            except asyncio.TimeoutError:
                # Timeout means it's time to reload
                pass

            try:
                logger.info("Reloading service configurations from database...")

                # Get updated configs from child class
                new_configs = self.get_service_configs()

                # Apply configs via child class
                self.apply_service_configs(new_configs)

                logger.info(
                    f"✅ Config reload complete: {len(new_configs)} config(s) loaded"
                )

            except Exception as e:
                logger.error(f"Error reloading configs: {e}")
                import traceback

                logger.error(traceback.format_exc())

        logger.info("Config reload task stopped")

    async def on_startup(self):
        """
        Hook called during application startup.

        This method:
        1. Initializes ServiceManager
        2. Acquires service lock if get_service_lock_name() returns a name
        3. Loads configs via get_service_configs()
        4. Applies configs via apply_service_configs()
        5. Starts config reload task if get_config_reload_interval() is set

        Override get_service_lock_name(), get_service_configs(), apply_service_configs(),
        and get_config_reload_interval() instead of overriding this method.
        """
        logger.info(f"Starting {self.title}...")

        # Check if file lock is required
        lock_name = self.get_service_lock_name()

        # Determine if we should proceed with service initialization
        should_initialize_services = False

        if lock_name is None:
            # No lock required - always initialize services
            should_initialize_services = True
            logger.info("No service lock configured - proceeding with initialization")
        else:
            # Lock required - try to acquire it
            import os
            import time

            # Place lock file in data directory
            import data

            data_dir = os.path.dirname(data.__file__)
            os.makedirs(data_dir, exist_ok=True)
            lock_file_path = os.path.join(data_dir, lock_name)

            lock_file = None
            try:
                # Try to acquire exclusive lock (non-blocking)
                lock_file = open(lock_file_path, "w")

                # Platform-specific file locking
                if os.name == "nt":  # Windows
                    import msvcrt

                    try:
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore
                    except OSError:
                        raise BlockingIOError("Service lock already held")
                else:  # POSIX (Linux, macOS, Docker)
                    import fcntl

                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore

                # Write PID and timestamp for debugging
                lock_file.write(f"PID: {os.getpid()}\nTime: {time.time()}\n")
                lock_file.flush()

                logger.info(f"✅ Acquired service lock: {lock_name} (PID {os.getpid()})")

                # Store lock file reference
                self._service_lock_file = lock_file

                # Lock acquired - proceed with initialization
                should_initialize_services = True

            except BlockingIOError:
                logger.info(
                    f"⏭️  Service already running in another worker (PID {os.getpid()})"
                )
                if lock_file:
                    lock_file.close()
                # Don't initialize services - another worker has the lock
                should_initialize_services = False
            except Exception as e:
                logger.error(f"Error acquiring service lock: {e}")
                if lock_file:
                    lock_file.close()
                raise

        # Initialize ServiceManager and services only if we should (no lock required OR lock acquired)
        if should_initialize_services:
            # Get ServiceManager singleton
            from services.service_manager import ServiceManager

            self.service_manager = ServiceManager()
            logger.info("ServiceManager initialized")
            # Load and apply configs
            configs = self.get_service_configs()
            if configs:
                self.apply_service_configs(configs)
                logger.info(f"Applied {len(configs)} service configuration(s)")

            # Start config reload task if interval is configured
            reload_interval = self.get_config_reload_interval()
            if reload_interval:
                self._shutdown_event = asyncio.Event()
                self._config_reload_task = asyncio.create_task(
                    self._reload_configs_periodically()
                )
                logger.info(
                    f"Started config reload task (interval: {reload_interval}s)"
                )

        logger.info(f"{self.title} startup complete")

    async def on_shutdown(self):
        """
        Hook called during application shutdown.

        This method:
        1. Stops config reload task if running
        2. Releases service lock if held
        3. Stops all services via ServiceManager

        Generally you don't need to override this method.
        """
        logger.info(f"Shutting down {self.title}...")

        # Stop config reload task
        if self._shutdown_event is not None:
            self._shutdown_event.set()
            logger.info("Signaled config reload task to stop")

        if self._config_reload_task is not None:
            try:
                await self._config_reload_task
                logger.info("Config reload task stopped")
            except Exception as e:
                logger.error(f"Error stopping config reload task: {e}")

        # Release service lock if held
        if self._service_lock_file is not None:
            try:
                import os

                # Platform-specific lock release
                if os.name == "nt":  # Windows
                    import msvcrt

                    try:
                        msvcrt.locking(self._service_lock_file.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore
                    except:
                        pass  # Lock may already be released
                else:  # POSIX (Linux, macOS, Docker)
                    import fcntl

                    fcntl.flock(self._service_lock_file.fileno(), fcntl.LOCK_UN)  # type: ignore

                self._service_lock_file.close()
                logger.info("Released service lock")
            except Exception as e:
                logger.error(f"Error releasing service lock: {e}")

        # Stop all services
        if self.service_manager:
            self.service_manager.stop_all_services()
            logger.info("All services stopped")

        logger.info(f"{self.title} shutdown complete")

    def get_default_user_role(self) -> Optional[str]:
        """
        Get the default role for newly registered users.

        Override this in subclasses to set a default role for the server.
        Returns None by default, which means no role is assigned.

        Returns:
            Default role string or None

        Example:
            ```python
            class MyCustomServer(BaseAPIServer):
                def get_default_user_role(self) -> Optional[str]:
                    return "user"  # All registered users get "user" role
            ```
        """
        return None

    def get_expected_user_role(self) -> Optional[list[str]]:
        """
        Get the expected roles for users logging in to this server.

        Override this in subclasses to restrict server access to specific roles.
        Returns None by default, which means any role is allowed.

        Returns:
            List of allowed role strings or None (allow any)

        Example:
            ```python
            class AdminServer(BaseAPIServer):
                def get_expected_user_role(self) -> Optional[list[str]]:
                    return ["admin", "superuser"]  # Only admins can login
            ```
        """
        return None

    def get_elevated_user_role(self) -> Optional[str]:
        """
        Get the elevated/privileged role for this server.

        This role typically represents users with elevated privileges like
        content creators, moderators, teachers, or administrators.
        Returns None by default, indicating no special elevated role is defined.

        This can be used for features like:
        - Granting content creation permissions
        - Enabling moderation capabilities
        - Unlocking advanced features
        - Bypassing certain restrictions

        Returns:
            Elevated role string or None

        Example:
            ```python
            class EduServer(BaseAPIServer):
                def get_elevated_user_role(self) -> Optional[str]:
                    return "teacher"  # Teachers have elevated privileges

            class CommunityServer(BaseAPIServer):
                def get_elevated_user_role(self) -> Optional[str]:
                    return "moderator"  # Moderators have elevated privileges
            ```
        """
        return None

    def get_excluded_endpoints(self) -> set[str]:
        """
        Get the set of endpoints to exclude/disable for this server.

        Override this in subclasses to selectively disable endpoints.
        By default, no endpoints are excluded (all are enabled).

        Supports wildcard patterns:
        - "*" or "auth/*": Exclude all auth endpoints
        - "auth/register": Exclude specific endpoint
        - Exact matches: "token", "register", "invite", "revalidate"

        Returns:
            Set of endpoint patterns to exclude. Available options:
            - "token" or "auth/token": POST /api/v1/auth/token - OAuth2 password login
            - "register" or "auth/register": POST /api/v1/auth/register - User registration
            - "invite" or "auth/invite": POST /api/v1/auth/invite - Invite-based registration
            - "revalidate" or "auth/revalidate": POST /api/v1/auth/revalidate - Token revalidation
            - "*" or "auth/*": All authentication endpoints
            - "/api/v1/auth/*": All v1 auth endpoints (full path)

        Example:
            ```python
            class ReadOnlyServer(BaseAPIServer):
                def get_excluded_endpoints(self) -> set[str]:
                    # Exclude registration endpoints, allow login and revalidation
                    return {"register", "invite"}

            class InviteOnlyServer(BaseAPIServer):
                def get_excluded_endpoints(self) -> set[str]:
                    # Exclude public registration, allow invite-based
                    return {"register"}

            class NoAuthServer(BaseAPIServer):
                def get_excluded_endpoints(self) -> set[str]:
                    # Exclude all auth endpoints
                    return {"auth/*"}  # or {"*"}
            ```
        """
        return set()  # By default, exclude nothing (enable all)

    def _is_endpoint_enabled(
        self,
        endpoint_name: str,
        excluded_patterns: set[str],
        full_path: str | None = None,
        api_group: str = "auth",
    ) -> bool:
        """
        Check if an endpoint is enabled (NOT excluded) based on wildcard patterns.

        This method checks if the endpoint matches any exclusion pattern.
        If it matches, the endpoint is disabled. Otherwise, it's enabled.

        Supports multiple matching strategies:
        1. Short name: "token" matches pattern "token"
        2. Namespaced: "auth/token" matches pattern "auth/token"
        3. Full path: "/api/v1/auth/token" matches pattern "/api/v1/auth/token"
        4. Wildcards: "*", "auth/*", "/api/v1/auth/*", etc.

        Args:
            endpoint_name: Short name of the endpoint (e.g., "token", "register")
            excluded_patterns: Set of patterns from get_excluded_endpoints()
            full_path: Full API path (e.g., "/api/v1/auth/token"), optional
            api_group: API group name (e.g., "auth", "files", "digest")

        Returns:
            True if endpoint is NOT excluded (enabled), False if excluded

        Examples:
            _is_endpoint_enabled("token", set()) -> True (nothing excluded)
            _is_endpoint_enabled("token", {"*"}) -> False (all excluded)
            _is_endpoint_enabled("token", {"register"}) -> True (token not excluded)
            _is_endpoint_enabled("register", {"register"}) -> False (register excluded)
            _is_endpoint_enabled("token", {"auth/*"}) -> False (all auth excluded)
        """
        # Build all possible matching names
        matching_names = [
            endpoint_name,  # Short name: "token"
            f"{api_group}/{endpoint_name}",  # Namespaced: "auth/token"
        ]

        if full_path:
            matching_names.append(full_path)  # Full path: "/api/v1/auth/token"

        # Check for exact matches in exclusion list
        for name in matching_names:
            if name in excluded_patterns:
                return False  # Excluded = disabled

        # Check wildcard patterns
        for pattern in excluded_patterns:
            # Universal wildcard
            if pattern == "*":
                return False  # Exclude all

            # Wildcard patterns using fnmatch
            if "*" in pattern or "?" in pattern:
                # Try matching against all possible names
                for name in matching_names:
                    if fnmatch(name, pattern):
                        return False  # Matched exclusion = disabled

        return True  # Not excluded = enabled

    def validate_invite_code(
        self, invite_code: str, session: Optional[Session] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Validate an invite code for elevated user registration.

        Uses db_helper_validate_and_use_invite_code to check that the code:
        1. Exists in the database
        2. Is not deleted
        3. Has not expired
        4. Has uses remaining (count_left > 0)
        5. Role matches expected roles for this server

        If all validations pass, decrements the usage count.

        Override this in subclasses for custom validation logic.

        Args:
            invite_code: The invite code string to validate
            session: Database session (optional, will create one if not provided)

        Returns:
            Tuple of (is_valid: bool, role: str | None)
            - If valid: (True, role_from_invite_code)
            - If invalid: (False, None)

        Example:
            ```python
            class MyServer(BaseAPIServer):
                def validate_invite_code(self, invite_code: str, session=None) -> tuple[bool, Optional[str]]:
                    valid, role = super().validate_invite_code(invite_code, session)
                    if valid:
                        # Additional custom validation
                        return is_premium_code(invite_code), role
                    return False, None
            ```
        """
        # Get expected roles for this server
        expected_roles = self.get_expected_user_role()

        # Use the db helper to validate and use the invite code
        is_valid, message, role = db_helper_validate_and_use_invite_code(
            invite_code=invite_code, expected_roles=expected_roles, session=session
        )

        return is_valid, role

    def _setup_middleware(self):
        """Setup CORS middleware with configured origins."""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=self.allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _add_common_routes(self):
        """Add common routes (root, health check)."""

        @self.app.get("/")
        async def root():
            """Root endpoint returning server status."""
            return {"message": "running", "server": self.title}

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint."""
            return "ok"

    def _add_auth_routes(self):
        """Add authentication routes (login, register) based on excluded endpoints."""
        # Get which endpoints should be excluded
        excluded_patterns = self.get_excluded_endpoints()

        if self._is_endpoint_enabled(
            "token", excluded_patterns, "/api/v1/auth/token", "auth"
        ):

            @self.app.post(
                "/api/v1/auth/token",
                response_model=TokenResponse,
                response_model_exclude_none=True,
            )
            def login_for_access_token(
                form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                request: Request,
                session: Session = Depends(get_db_session),
            ):
                """
                OAuth2 compatible token login endpoint.

                Get access token by providing username and password.
                """
                client_ip = self._get_client_ip(request)

                # Get expected roles for this server
                expected_role = self.get_expected_user_role()

                # Attempt to authenticate user
                token_response = api_login_user(
                    username=form_data.username,
                    password=form_data.password,
                    ip=client_ip,
                    expected_role=expected_role,
                    session=session,
                )

                if not token_response.success:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=token_response.message,
                        headers={"WWW-Authenticate": "Bearer"},
                    )

                return token_response

        if self._is_endpoint_enabled(
            "register", excluded_patterns, "/api/v1/auth/register", "auth"
        ):

            @self.app.post(
                "/api/v1/auth/register",
                response_model=TokenResponse,
                response_model_exclude_none=True,
            )
            def register_user(
                form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
                request: Request,
                session: Session = Depends(get_db_session),
            ):
                """
                User registration endpoint.

                Register a new user and return access token.
                """
                client_ip = self._get_client_ip(request)

                # Get default role for this server
                default_role = self.get_default_user_role()

                # Attempt to register user
                register_response = api_register_user(
                    username=form_data.username,
                    password=form_data.password,
                    ip=client_ip,
                    role=default_role,
                    session=session,
                )

                if not register_response.success:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=register_response.message,
                    )

                return register_response

        if self._is_endpoint_enabled(
            "invite", excluded_patterns, "/api/v1/auth/invite", "auth"
        ):

            @self.app.post(
                "/api/v1/auth/invite",
                response_model=TokenResponse,
                response_model_exclude_none=True,
            )
            def invite_user(
                registration_data: InviteRegistrationRequest,
                request: Request,
                session: Session = Depends(get_db_session),
            ):
                """
                Invite-based user registration endpoint.

                Register a new user using an invite code.
                The user will be assigned the role specified in the invite code.

                Requires:
                - username: Desired username
                - password: User password
                - invite_code: Valid invite code for registration

                Returns access token upon successful registration.
                """
                client_ip = self._get_client_ip(request)

                # Validate and use invite code (validates and decrements in one operation)
                expected_roles = self.get_expected_user_role()
                is_valid, _, invite_role = db_helper_validate_and_use_invite_code(
                    invite_code=registration_data.invite_code,
                    expected_roles=expected_roles,
                    session=session,
                )

                if not is_valid or invite_role is None:
                    # Normalize all validation errors to "Invalid invite code" for security
                    # (don't leak information about whether codes exist, are expired, etc.)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Invalid invite code",
                    )

                # Attempt to register user with role from invite code
                register_response = api_register_user(
                    username=registration_data.username,
                    password=registration_data.password,
                    ip=client_ip,
                    role=invite_role,
                    invite_code=registration_data.invite_code,
                    session=session,
                )

                if not register_response.success:
                    # Registration failed - invite code was already consumed
                    # This is acceptable since invalid codes won't be retried
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=register_response.message,
                    )

                return register_response

        if self._is_endpoint_enabled(
            "revalidate", excluded_patterns, "/api/v1/auth/revalidate", "auth"
        ):

            @self.app.post(
                "/api/v1/auth/revalidate",
                response_model=TokenResponse,
                response_model_exclude_none=True,
            )
            def revalidate_token(
                request: Request,
                token: Annotated[str, Depends(get_token_from_header)],
                session: Session = Depends(get_db_session),
            ):
                """
                Token revalidation endpoint.

                Validates an existing JWT token from Authorization header without updating login information.
                Returns TokenResponse with same token if valid.
                """
                client_ip = self._get_client_ip(request)

                # Get expected roles for this server
                expected_role = self.get_expected_user_role()

                # Revalidate the token
                validation_response = api_revalidate_token(
                    token=token,
                    ip=client_ip,
                    expected_role=expected_role,
                    session=session,
                )

                return validation_response

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """
        Extract client IP address from request, handling proxy/load balancer cases.

        Checks headers in this order:
        1. X-Forwarded-For (proxy/load balancer)
        2. X-Real-IP
        3. Direct connection IP

        Args:
            request: FastAPI request object

        Returns:
            Client IP address as string
        """
        client_ip = ""

        # Check X-Forwarded-For header first (proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs, take the first one (original client)
            client_ip = forwarded_for.split(",")[0].strip()
        # Fallback to X-Real-IP header
        elif request.headers.get("X-Real-IP"):
            client_ip = request.headers.get("X-Real-IP", "").strip()
        # Final fallback to direct connection IP
        elif request.client:
            client_ip = request.client.host

        return client_ip

    def add_route(self, path: str, **kwargs):
        """
        Decorator for adding routes to the app.

        Example:
            ```python
            @server.add_route("/custom", methods=["GET"])
            def custom_endpoint():
                return {"message": "custom"}
            ```
        """
        return self.app.api_route(path, **kwargs)

    def include_router(self, router, **kwargs):
        """
        Include an APIRouter in the application.

        Args:
            router: FastAPI APIRouter instance
            **kwargs: Additional arguments for router inclusion (prefix, tags, etc.)

        Example:
            ```python
            from fastapi import APIRouter

            router = APIRouter()

            @router.get("/items")
            def list_items():
                return []

            server.include_router(router, prefix="/api", tags=["items"])
            ```
        """
        self.app.include_router(router, **kwargs)
