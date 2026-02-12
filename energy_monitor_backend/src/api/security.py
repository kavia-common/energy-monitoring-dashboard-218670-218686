import os
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext

from src.api import db

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def _jwt_secret() -> str:
    secret = os.getenv("JWT_SECRET")
    if not secret:
        # Do not silently generate secrets; would invalidate tokens across restarts.
        raise RuntimeError("Missing required environment variable JWT_SECRET.")
    return secret


def _jwt_exp_minutes() -> int:
    raw = os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", "120")
    try:
        return int(raw)
    except ValueError:
        return 120


# PUBLIC_INTERFACE
def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return pwd_context.hash(password)


# PUBLIC_INTERFACE
def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a stored hash."""
    return pwd_context.verify(password, password_hash)


# PUBLIC_INTERFACE
def create_access_token(subject: str, extra: Optional[dict[str, Any]] = None) -> str:
    """Create a signed JWT access token for a given subject (user_id)."""
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=_jwt_exp_minutes())
    payload: dict[str, Any] = {"sub": subject, "iat": int(now.timestamp()), "exp": int(exp.timestamp())}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256")


def _decode_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from e
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from e


# PUBLIC_INTERFACE
def get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, Any]:
    """FastAPI dependency: validate bearer token and return the current app_users row."""
    payload = _decode_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")

    user = db.fetch_one(
        """
        SELECT id, email, full_name, is_active, created_at, updated_at, last_login_at
        FROM app_users
        WHERE id = %s
        """,
        (user_id,),
    )
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")
    return user
