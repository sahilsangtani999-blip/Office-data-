"""
API Router for Authentication & User Identity.
Phase 2.5 — Authentication & Office Permissions.

Provides:
- POST /api/v1/auth/login: Authenticate credentials and retrieve JWT bearer token.
- GET /api/v1/auth/me: Retrieve current authenticated user profile and permissions.
- POST /api/v1/auth/seed: Ensure standard office seed accounts exist.
"""

from datetime import timedelta
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.dependencies import AuthenticatedUserContext, require_authenticated_user
from app.core.security import create_access_token
from app.database import get_db
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.services.auth_service import (
    authenticate_user,
    seed_default_users,
    user_to_response,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & Identity"])


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Office User Login",
    description="Authenticates office username and password, returning a signed JWT Bearer access token with assigned office role and permissions.",
)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Validate credentials and issue JWT access token."""
    user = authenticate_user(db, payload.username.strip(), payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Calculate token expiration
    expires_delta = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token_data = {
        "sub": user.username,
        "role": user.role,
        "user_id": str(user.id),
    }
    access_token = create_access_token(data=token_data, expires_delta=expires_delta)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=user_to_response(user),
    )


@router.get(
    "/me",
    response_model=UserResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Current User Profile",
    description="Returns the profile and evaluated permissions of the currently authenticated office user.",
)
def get_current_user_profile(
    context: AuthenticatedUserContext = Depends(require_authenticated_user),
    db: Session = Depends(get_db),
) -> UserResponse:
    """Retrieve identity and permissions for current session."""
    user = db.query(User).filter(User.username == context.username).first()
    if user:
        return user_to_response(user)

    # In dev fallback context where user is not in DB
    from app.core.permissions import get_role_permissions
    import uuid
    return UserResponse(
        id=uuid.UUID(context.user_id) if len(context.user_id) == 36 else uuid.uuid4(),
        username=context.username,
        email=context.email or f"{context.username}@rssb.local",
        full_name=context.full_name or context.username.capitalize(),
        role=context.role,
        permissions=sorted(list(get_role_permissions(context.role))),
        is_active=True,
        created_at=getattr(user, "created_at", None) or "2026-01-01T00:00:00Z",
    )


@router.post(
    "/seed",
    response_model=List[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="Seed Default Office Accounts",
    description="Idempotently ensures default development/testing accounts (admin, reviewer, uploader, viewer) are initialized.",
)
def seed_users_endpoint(db: Session = Depends(get_db)) -> List[UserResponse]:
    """Seed default accounts."""
    users = seed_default_users(db)
    return [user_to_response(u) for u in users]
