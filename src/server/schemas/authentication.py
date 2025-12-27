from __future__ import annotations

import traceback
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt
from pydantic import BaseModel

from env_vars import ACCESS_TOKEN_SECRET_ALGORITHM, ACCESS_TOKEN_SECRET_KEY
from utilities import logger
from utilities.time import get_utcnow


class UserAuthToken(BaseModel):
    sub: str
    session: int
    multi_session_ok: bool
    exp: Optional[datetime] = None

    def create_access_token(
        self,
        expires_delta: Optional[timedelta] = None,
        expires_at: Optional[datetime] = None,
    ):
        if not ACCESS_TOKEN_SECRET_KEY:
            raise ValueError(
                "ACCESS_TOKEN_SECRET_KEY is not set in environment variable"
            )

        to_encode = self.model_copy(deep=True)
        if expires_delta:
            expire = get_utcnow() + expires_delta
        elif expires_at:
            expire = expires_at
        else:
            expire = get_utcnow() + timedelta(days=1)
        to_encode.exp = expire
        encoded_jwt = jwt.encode(
            to_encode.model_dump(),
            ACCESS_TOKEN_SECRET_KEY,
            algorithm=ACCESS_TOKEN_SECRET_ALGORITHM,
        )
        return encoded_jwt

    @classmethod
    def from_access_token(cls, token: str) -> UserAuthToken | None:
        try:
            if not ACCESS_TOKEN_SECRET_KEY:
                raise ValueError(
                    "ACCESS_TOKEN_SECRET_KEY is not set in environment variable"
                )

            payload = jwt.decode(
                token,
                ACCESS_TOKEN_SECRET_KEY,
                algorithms=[ACCESS_TOKEN_SECRET_ALGORITHM],
            )
            return UserAuthToken.model_validate(payload)
        except Exception as e:
            logger.error(f"{str(e)}")
            tbs = traceback.format_exc().split("\n")
            for tb in tbs:
                logger.error(f"  {tb}")
            return None


class TokenRequest(BaseModel):
    token: str


class TokenResponse(BaseModel):
    success: bool
    message: str
    token: str
    expires_at: Optional[datetime] = None


class InviteRegistrationRequest(BaseModel):
    """Request model for invite-based user registration with invite code."""

    username: str
    password: str
    invite_code: str
