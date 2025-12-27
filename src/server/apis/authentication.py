from __future__ import annotations

import traceback
from datetime import datetime, timedelta
from typing import Annotated, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from db.database import get_db_session
from db.db_models import User, UserInviteModel
from db.db_operations import (
    create_user,
    create_user_invite,
    decrement_invite_count,
    delete_user_invite,
    get_user_by_username,
    get_user_invite_by_code,
    get_user_invites_by_creator,
    update_user,
)
from env_vars import ACCESS_TOKEN_EXPIRE_MINUTES
from server.schemas.authentication import TokenResponse, UserAuthToken
from utilities import logger
from utilities.time import get_utcnow

# To get a secret key:
#   openssl rand -hex 32
# or:
#   import secrets
#   token = secrets.token_hex(32)
#   print(token)


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# Helper functions


def _verify_plain_text_with_hashed_text(plain_text: str, hashed_text: str) -> bool:
    return pwd_context.verify(plain_text, hashed_text)


def _get_plain_text_hash(plain_text: str) -> str | None:
    if not plain_text:
        return None
    return pwd_context.hash(plain_text)


def _authenticate_user(
    username: str,
    ip: str = "",
    password: str = "",
    revalidate: bool = False,
    validate_only: bool = False,
    session: Optional[Session] = None,
) -> User | None:
    close_session = False
    try:
        if not session:
            session = next(get_db_session())
            close_session = True
        user = get_user_by_username(session=session, username=username)
        if not user:
            logger.warning(f"user {username} failed authentication, not found")
            return None
        if not user.is_active:  # type: ignore
            logger.warning(f"user {username} failed authentication, not active")
            return None
        if (
            not revalidate  # type: ignore
            and user.password_hashed  # type: ignore
            and not _verify_plain_text_with_hashed_text(
                plain_text=password, hashed_text=user.password_hashed  # type: ignore
            )
        ):
            logger.warning(f"user {username} failed authentication, incorrect password")
            return None
        if not validate_only:
            if (
                ip  # type: ignore
                and user.last_login_ip_hashed
                and not _verify_plain_text_with_hashed_text(
                    plain_text=ip, hashed_text=user.last_login_ip_hashed  # type: ignore
                )
            ):
                logger.info(
                    f"user {username} last log in ip != current ip, session {user.last_login_session} -> {user.last_login_session + 1}"
                )
                user.last_login_session += 1  # type: ignore
            if ip:
                user.last_login_ip_hashed = _get_plain_text_hash(plain_text=ip)  # type: ignore
            user.last_login_timestamp = get_utcnow()  # type: ignore
            return update_user(session=session, user=user)
        else:
            return user
    except Exception as e:
        logger.error(f"{str(e)}")
        tbs = traceback.format_exc().split("\n")
        for tb in tbs:
            logger.error(f"  {tb}")
        return None
    finally:
        if close_session and session:
            session.close()


def _handle_login_user(
    user: User,
    time_now: Optional[datetime] = None,
    expires_at: Optional[datetime] = None,
) -> TokenResponse:
    auth = UserAuthToken(
        sub=user.username,  # type: ignore
        session=user.last_login_session,  # type: ignore
        multi_session_ok=user.multi_session_ok,  # type: ignore
    )

    if time_now:
        try:
            access_token_expire_min = int(ACCESS_TOKEN_EXPIRE_MINUTES)
        except:
            access_token_expire_min = 10080
        access_token_expires = timedelta(minutes=access_token_expire_min)
        access_token = auth.create_access_token(expires_delta=access_token_expires)
        access_token_expires_at = time_now + access_token_expires
        logger.info(
            f"User {user.username} logged in at {time_now}, auth token expires at {access_token_expires_at}"
        )
    else:
        time_now = get_utcnow()
        access_token_expires_at = expires_at
        access_token = auth.create_access_token(expires_at=expires_at)

    return TokenResponse(
        token=access_token, expires_at=access_token_expires_at, success=True, message=""
    )


# APIs


def api_validate_token(
    token: str,
    ip: str = "",
    validate_only: bool = False,
    session: Optional[Session] = None,
) -> TokenResponse:
    close_session = False
    try:
        if not session:
            session = next(get_db_session())
            close_session = True

        auth_payload: UserAuthToken | None = UserAuthToken.from_access_token(
            token=token
        )
        if not auth_payload:
            return TokenResponse(success=False, token="", message="Invalid token")

        if not auth_payload.sub:
            return TokenResponse(success=False, token="", message="Invalid token")

        user = _authenticate_user(
            session=session,
            username=auth_payload.sub,
            ip=ip,
            revalidate=True,
            validate_only=validate_only,
        )

        if user is None:
            return TokenResponse(success=False, token="", message="Invalid token")

        # See if the session has expired.
        if (
            not auth_payload.multi_session_ok  # type: ignore
            and user.last_login_session != auth_payload.session  # type: ignore
        ):
            return TokenResponse(success=False, token="", message="Session expired")
        return _handle_login_user(user=user, expires_at=auth_payload.exp)
    except Exception as e:
        logger.error(f"{str(e)}")
        tbs = traceback.format_exc().split("\n")
        for tb in tbs:
            logger.error(f"  {tb}")
        return TokenResponse(success=False, token="", message="Server internal error")
    finally:
        if close_session and session:
            session.close()


def api_login_user(
    username: str,
    password: str,
    ip: str = "",
    expected_role: Optional[list[str]] = None,
    session: Optional[Session] = None,
) -> TokenResponse:
    close_session = False
    try:
        if not session:
            session = next(get_db_session())
            close_session = True

        user = _authenticate_user(
            username=username,
            password=password,
            session=session,
            ip=ip,
        )

        time_now = get_utcnow()
        if not user:
            logger.warning(f"User {username} failed logged in at {time_now}")
            return TokenResponse(
                success=False, token="", message="Incorrect username or password"
            )

        if expected_role and user.role not in expected_role:
            logger.warning(
                f"User {user.username} [role={user.role}] failed logged in at {time_now}, does not meet expected roles: {expected_role}"
            )
            return TokenResponse(
                success=False, token="", message="Incorrect username or password"
            )

        return _handle_login_user(user=user, time_now=time_now)
    except Exception as e:
        logger.error(f"{str(e)}")
        tbs = traceback.format_exc().split("\n")
        for tb in tbs:
            logger.error(f"  {tb}")
        return TokenResponse(success=False, token="", message="Server internal error")
    finally:
        if close_session and session:
            session.close()


def api_revalidate_token(
    token: str,
    ip: str = "",
    expected_role: Optional[list[str]] = None,
    session: Optional[Session] = None,
) -> TokenResponse:
    """
    Revalidate an existing token without updating login info.

    Args:
        token: JWT token to validate
        ip: Client IP address (optional, for logging)
        expected_role: List of expected roles (optional, validates user has one of these roles)
        session: Database session (optional)

    Returns:
        TokenResponse with validation status and same token if valid
    """
    close_session = False
    try:
        if not session:
            session = next(get_db_session())
            close_session = True

        # Decode the token
        auth_payload: UserAuthToken | None = UserAuthToken.from_access_token(
            token=token
        )
        if not auth_payload:
            return TokenResponse(
                success=False, token="", message="Invalid token format"
            )

        if not auth_payload.sub:
            return TokenResponse(
                success=False, token="", message="Token missing username"
            )

        # Authenticate user with validate_only=True (no login updates)
        user = _authenticate_user(
            session=session,
            username=auth_payload.sub,
            ip=ip,
            revalidate=True,
            validate_only=True,
        )

        if user is None:
            return TokenResponse(
                success=False, token="", message="User not found or inactive"
            )

        # Check if session has expired (multi-session check)
        if (
            not auth_payload.multi_session_ok  # type: ignore
            and user.last_login_session != auth_payload.session
        ):
            return TokenResponse(
                success=False, token="", message="Session expired - please login again"
            )

        # Check token expiration
        if auth_payload.exp and auth_payload.exp < get_utcnow():
            return TokenResponse(
                success=False, token="", message="Token expired - please login again"
            )

        # Check expected role if specified
        if expected_role and user.role not in expected_role:
            logger.warning(
                f"User {user.username} [role={user.role}] failed token revalidation, does not meet expected roles: {expected_role}"
            )
            return TokenResponse(
                success=False,
                token="",
                message="Access denied - insufficient permissions",
            )

        # Token is valid - return the same token
        logger.info(f"Token revalidation successful for user {user.username}")
        return TokenResponse(
            success=True,
            token=token,
            message="Token is valid",
            expires_at=auth_payload.exp,
        )

    except Exception as e:
        logger.error(f"Token revalidation error: {str(e)}")
        tbs = traceback.format_exc().split("\n")
        for tb in tbs:
            logger.error(f"  {tb}")
        return TokenResponse(success=False, token="", message="Server internal error")
    finally:
        if close_session and session:
            session.close()


def api_get_user_from_token(
    token: str,
    ip: str = "",
    session: Optional[Session] = None,
) -> tuple[Optional[User], TokenResponse]:
    """
    Get user model from token validation.

    This is a helper function for endpoints that need both token validation
    and user information without calling database operations directly.

    Args:
        token: JWT token to validate
        ip: Client IP address (optional, for logging)
        session: Database session (optional)

    Returns:
        Tuple of (User or None, TokenResponse)
        - If validation succeeds: (User, success TokenResponse)
        - If validation fails: (None, error TokenResponse)
    """
    close_session = False
    try:
        if not session:
            session = next(get_db_session())
            close_session = True

        # Decode the token
        auth_payload: UserAuthToken | None = UserAuthToken.from_access_token(
            token=token
        )
        if not auth_payload:
            return None, TokenResponse(
                success=False, token="", message="Invalid token format"
            )

        if not auth_payload.sub:
            return None, TokenResponse(
                success=False, token="", message="Token missing username"
            )

        # Authenticate user with validate_only=True (no login updates)
        user = _authenticate_user(
            session=session,
            username=auth_payload.sub,
            ip=ip,
            revalidate=True,
            validate_only=True,
        )

        if user is None:
            return None, TokenResponse(
                success=False, token="", message="User not found or inactive"
            )

        # Check if session has expired (multi-session check)
        if (
            not auth_payload.multi_session_ok  # type: ignore
            and user.last_login_session != auth_payload.session
        ):
            return None, TokenResponse(
                success=False, token="", message="Session expired - please login again"
            )

        # Check token expiration
        if auth_payload.exp and auth_payload.exp < get_utcnow():
            return None, TokenResponse(
                success=False, token="", message="Token expired - please login again"
            )

        # Token is valid - return user and success response
        logger.info(f"Token validation successful for user {user.username}")
        return user, TokenResponse(
            success=True,
            token=token,
            message="Token is valid",
            expires_at=auth_payload.exp,
        )

    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        tbs = traceback.format_exc().split("\n")
        for tb in tbs:
            logger.error(f"  {tb}")
        return None, TokenResponse(
            success=False, token="", message="Server internal error"
        )
    finally:
        if close_session and session:
            session.close()


def api_register_user(
    username: str,
    password: str,
    ip: str = "",
    role: Optional[str] = None,
    invite_code: Optional[str] = None,
    organization_id: Optional[int] = None,
    multi_session_ok: bool = True,
    session: Optional[Session] = None,
) -> TokenResponse:
    close_session = False
    try:
        if not session:
            session = next(get_db_session())
            close_session = True
        user = get_user_by_username(session=session, username=username)
        if user:
            return TokenResponse(token="", success=False, message="Already exists")

        time_now = time_now = get_utcnow()
        ip_hashed = _get_plain_text_hash(plain_text=ip)

        # Set organization_id - prioritize invite code's organization, then parameter, then NONE
        org_id = -1

        # If invite code is provided, get organization_id from it
        if invite_code:
            invite = get_user_invite_by_code(session=session, invite_code=invite_code)
            if invite and invite.organization_id != -1:  # type: ignore
                org_id = invite.organization_id

        # If no organization from invite, use the provided organization_id parameter
        if org_id == -1 and organization_id is not None:  # type: ignore
            org_id = organization_id

        user = User(
            username=username,
            password_hashed=_get_plain_text_hash(plain_text=password),
            register_ip_hashed=ip_hashed,
            last_login_ip_hashed=ip_hashed,
            last_login_timestamp=time_now,
            create_timestamp=time_now,
            multi_session_ok=multi_session_ok,
            role=role,
            invite_code=invite_code,
            organization_id=org_id,
        )
        user = create_user(session=session, user=user)
        logger.info(
            f"User {user.username} [role={user.role}, org={org_id}] created at {time_now}"
        )
        token = _handle_login_user(user=user, time_now=time_now)
        return TokenResponse(
            success=True, token=token.token, expires_at=token.expires_at, message=""
        )
    except Exception as e:
        logger.error(f"{str(e)}")
        tbs = traceback.format_exc().split("\n")
        for tb in tbs:
            logger.error(f"  {tb}")
        return TokenResponse(token="", success=False, message="Server internal failure")
    finally:
        if close_session and session:
            session.close()


def get_token_from_header(token: Annotated[str, Depends(oauth2_scheme)]) -> str:
    """
    Dependency function to extract JWT token from Authorization header.

    The OAuth2PasswordBearer scheme automatically extracts the token from
    the "Authorization: Bearer <token>" header.

    Args:
        token: JWT token extracted from Authorization header

    Returns:
        JWT token string

    Raises:
        HTTPException: If token is missing or invalid format

    Example:
        @app.get("/protected")
        def protected_route(token: Annotated[str, Depends(get_token_from_header)]):
            # Token is automatically extracted from Authorization header
            user, response = api_get_user_from_token(token=token)
            return {"user": user.username}
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


# User Invite Helpers


def db_helper_create_invite_code(
    invite_code: str,
    role: str,
    count_left: int = 1,
    expire_time: Optional[datetime] = None,
    created_by_user_id: int = 0,
    organization_id: Optional[int] = None,
    session: Optional[Session] = None,
) -> tuple[bool, str, Optional[UserInviteModel]]:
    """
    Create a new invite code.

    Args:
        invite_code: The unique invite code string
        role: The role to assign when this code is used
        count_left: Number of times this code can be used (default: 1)
        expire_time: When this code expires (None = never expires)
        created_by_user_id: User ID who created this code
        organization_id: Organization ID to assign to users who use this code (optional)
        session: Database session (optional)

    Returns:
        Tuple of (success: bool, message: str, invite: UserInviteModel | None)
    """
    close_session = False
    try:
        if not session:
            session = next(get_db_session())
            close_session = True

        # Check if code already exists
        existing = get_user_invite_by_code(session=session, invite_code=invite_code)
        if existing:
            return False, "Invite code already exists", None

        # Create new invite
        org_id = organization_id if organization_id is not None else -1

        invite = UserInviteModel(
            invite_code=invite_code,
            role=role,
            count_left=count_left,
            expire_time=expire_time,
            created_by_user_id=created_by_user_id,
            organization_id=org_id,
        )
        invite = create_user_invite(session=session, invite=invite)

        logger.info(
            f"Created invite code '{invite_code}' for role '{role}' with {count_left} uses"
        )
        return True, "Invite code created successfully", invite

    except Exception as e:
        logger.error(f"Error creating invite code: {str(e)}")
        tbs = traceback.format_exc().split("\n")
        for tb in tbs:
            logger.error(f"  {tb}")
        return False, "Failed to create invite code", None
    finally:
        if close_session and session:
            session.close()


def db_helper_validate_invite_code(
    invite_code: str,
    expected_roles: Optional[list[str]] = None,
    session: Optional[Session] = None,
) -> tuple[bool, str, Optional[str]]:
    """
    Validate an invite code WITHOUT decrementing its usage count.

    Validates that the invite code:
    1. Exists in database
    2. Is not deleted (handled by get_user_invite_by_code)
    3. Has not expired
    4. Has uses remaining (count_left > 0)
    5. Role matches expected roles (if expected_roles provided)

    This is useful for checking validity before performing other operations
    that might fail, to avoid consuming invite codes unnecessarily.

    Args:
        invite_code: The invite code to validate
        expected_roles: Optional list of allowed roles (None = any role accepted)
        session: Database session (optional)

    Returns:
        Tuple of (valid: bool, message: str, role: str | None)
    """
    close_session = False
    try:
        if not session:
            session = next(get_db_session())
            close_session = True

        # Get invite code
        invite = get_user_invite_by_code(session=session, invite_code=invite_code)

        if not invite:
            logger.warning(f"Invite code '{invite_code}' not found in database")
            return False, "Invalid invite code", None

        # Check if expired
        if invite.expire_time and invite.expire_time < get_utcnow():  # type: ignore
            logger.warning(f"Invite code '{invite_code}' has expired")
            return False, "Invite code has expired", None

        # Check if uses remaining
        if invite.count_left <= 0:  # type: ignore
            logger.warning(f"Invite code '{invite_code}' has no uses remaining")
            return False, "Invite code has no uses remaining", None

        # Validate role if expected_roles provided
        if expected_roles and invite.role not in expected_roles:
            logger.warning(
                f"Invite code '{invite_code}' role '{invite.role}' not in expected roles {expected_roles}"
            )
            return False, f"Invite code role not allowed for this server", None

        return True, "Invite code is valid", invite.role  # type: ignore

    except Exception as e:
        logger.error(f"Error validating invite code '{invite_code}': {str(e)}")
        tbs = traceback.format_exc().split("\n")
        for tb in tbs:
            logger.error(f"  {tb}")
        return False, "Failed to validate invite code", None
    finally:
        if close_session and session:
            session.close()


def db_helper_validate_and_use_invite_code(
    invite_code: str,
    expected_roles: Optional[list[str]] = None,
    session: Optional[Session] = None,
) -> tuple[bool, str, Optional[str]]:
    """
    Validate an invite code and decrement its usage count.

    Validates that the invite code:
    1. Exists in database
    2. Is not deleted (handled by get_user_invite_by_code)
    3. Has not expired
    4. Has uses remaining (count_left > 0)
    5. Role matches expected roles (if expected_roles provided)

    Args:
        invite_code: The invite code to validate
        expected_roles: Optional list of allowed roles (None = any role accepted)
        session: Database session (optional)

    Returns:
        Tuple of (valid: bool, message: str, role: str | None)
    """
    close_session = False
    try:
        if not session:
            session = next(get_db_session())
            close_session = True

        # Get invite code
        invite = get_user_invite_by_code(session=session, invite_code=invite_code)

        if not invite:
            logger.warning(f"Invite code '{invite_code}' not found in database")
            return False, "Invalid invite code", None

        # Check if expired
        if invite.expire_time and invite.expire_time < get_utcnow():  # type: ignore
            logger.warning(f"Invite code '{invite_code}' has expired")
            return False, "Invite code has expired", None

        # Check if uses remaining
        if invite.count_left <= 0:  # type: ignore
            logger.warning(f"Invite code '{invite_code}' has no uses remaining")
            return False, "Invite code has no uses remaining", None

        # Validate role if expected_roles provided
        if expected_roles and invite.role not in expected_roles:
            logger.warning(
                f"Invite code '{invite_code}' role '{invite.role}' not in expected roles {expected_roles}"
            )
            return False, f"Invite code role not allowed for this server", None

        # Decrement count (atomic operation)
        role = invite.role
        result = decrement_invite_count(session=session, invite_code=invite_code)

        if not result:
            logger.error(f"Failed to decrement count for invite code '{invite_code}'")
            return False, "Failed to use invite code", None

        logger.info(
            f"Used invite code '{invite_code}' for role '{role}' ({invite.count_left - 1} uses remaining)"
        )
        return True, "Invite code is valid", role  # type: ignore

    except Exception as e:
        logger.error(f"Error validating invite code '{invite_code}': {str(e)}")
        tbs = traceback.format_exc().split("\n")
        for tb in tbs:
            logger.error(f"  {tb}")
        if session:
            session.rollback()
        return False, "Failed to validate invite code", None
    finally:
        if close_session and session:
            session.close()


def db_helper_use_invite_code(
    invite_code: str,
    session: Optional[Session] = None,
) -> tuple[bool, str]:
    """
    Decrement the usage count of an invite code.

    This should be called AFTER successful user registration to consume the invite code.
    Use db_helper_validate_invite_code() first to check validity.

    Args:
        invite_code: The invite code to use/decrement
        session: Database session (optional)

    Returns:
        Tuple of (success: bool, message: str)
    """
    close_session = False
    try:
        if not session:
            session = next(get_db_session())
            close_session = True

        # Get invite to log remaining count
        invite = get_user_invite_by_code(session=session, invite_code=invite_code)
        if not invite:
            return False, "Invite code not found"

        # Decrement count (atomic operation)
        result = decrement_invite_count(session=session, invite_code=invite_code)

        if not result:
            logger.error(f"Failed to decrement count for invite code '{invite_code}'")
            return False, "Failed to use invite code"

        logger.info(
            f"Used invite code '{invite_code}' for role '{invite.role}' ({invite.count_left - 1} uses remaining)"
        )
        return True, "Invite code used successfully"

    except Exception as e:
        logger.error(f"Error using invite code '{invite_code}': {str(e)}")
        tbs = traceback.format_exc().split("\n")
        for tb in tbs:
            logger.error(f"  {tb}")
        if session:
            session.rollback()
        return False, "Failed to use invite code"
    finally:
        if close_session and session:
            session.close()


def db_helper_get_invite_codes_by_user(
    user_id: int, session: Optional[Session] = None
) -> list[UserInviteModel]:
    """
    Get all invite codes created by a user.

    Args:
        user_id: The user ID
        session: Database session (optional)

    Returns:
        List of UserInviteModel
    """
    close_session = False
    try:
        if not session:
            session = next(get_db_session())
            close_session = True

        return get_user_invites_by_creator(session=session, created_by_user_id=user_id)

    except Exception as e:
        logger.error(f"Error getting invite codes: {str(e)}")
        return []
    finally:
        if close_session and session:
            session.close()


def db_helper_delete_invite_code(
    invite_code: str, session: Optional[Session] = None
) -> tuple[bool, str]:
    """
    Delete an invite code.

    Args:
        invite_code: The invite code to delete
        session: Database session (optional)

    Returns:
        Tuple of (success: bool, message: str)
    """
    close_session = False
    try:
        if not session:
            session = next(get_db_session())
            close_session = True

        invite = get_user_invite_by_code(session=session, invite_code=invite_code)
        if not invite:
            return False, "Invite code not found"

        delete_user_invite(session=session, invite=invite)
        logger.info(f"Deleted invite code '{invite_code}'")
        return True, "Invite code deleted successfully"

    except Exception as e:
        logger.error(f"Error deleting invite code: {str(e)}")
        return False, "Failed to delete invite code"
    finally:
        if close_session and session:
            session.close()
