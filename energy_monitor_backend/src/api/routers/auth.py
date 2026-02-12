from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import EmailStr

from src.api import db
from src.api.schemas import LoginRequest, RegisterRequest, TokenResponse, UserMeResponse
from src.api.security import create_access_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=UserMeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
    description="Creates an account in app_users. Email must be unique.",
    operation_id="auth_register",
)
def register(payload: RegisterRequest) -> UserMeResponse:
    """
    Register a new user.

    - **email**: unique email.
    - **password**: plaintext password; will be hashed before storage.
    - **full_name**: optional.

    Returns the created user profile.
    """
    email = EmailStr(payload.email).lower()
    existing = db.fetch_one("SELECT id FROM app_users WHERE email = %s", (email,))
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    user = db.execute_returning_one(
        """
        INSERT INTO app_users (email, password_hash, full_name)
        VALUES (%s, %s, %s)
        RETURNING id, email, full_name, is_active, created_at, updated_at, last_login_at
        """,
        (email, hash_password(payload.password), payload.full_name),
    )
    return UserMeResponse(**user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive an access token",
    description="Validates credentials and returns a JWT access token.",
    operation_id="auth_login",
)
def login(payload: LoginRequest) -> TokenResponse:
    """
    Login a user by email/password.

    Returns a bearer token (JWT) to be used in Authorization header:
      `Authorization: Bearer <token>`
    """
    email = EmailStr(payload.email).lower()
    user = db.fetch_one(
        "SELECT id, email, password_hash, is_active FROM app_users WHERE email = %s",
        (email,),
    )
    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.get("is_active", True):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    # Update last_login_at best-effort
    db.execute("UPDATE app_users SET last_login_at = now() WHERE id = %s", (user["id"],))
    token = create_access_token(str(user["id"]), extra={"email": user["email"]})
    return TokenResponse(access_token=token)


@router.get(
    "/me",
    response_model=UserMeResponse,
    summary="Get current user profile",
    description="Returns the current user's profile based on the bearer token.",
    operation_id="auth_me",
)
def me(current_user: dict = Depends(get_current_user)) -> UserMeResponse:
    """
    Get current user profile.

    Requires `Authorization: Bearer <token>`.
    """
    return UserMeResponse(**current_user)
