"""
FastAPI authentication and RBAC authorization dependencies.
Phase 2.5 — Authentication & Office Permissions.
"""

from typing import List, Optional, Set
import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import (
    PERM_ADMIN,
    PERM_READ,
    PERM_READ_SOURCES,
    PERM_REVIEW,
    PERM_UPLOAD,
    get_role_permissions,
    has_permission,
)
from app.core.security import decode_access_token
from app.database import get_db
from app.models import User


class AuthenticatedUserContext:
    """
    Unified caller context representing an authenticated office user
    with identity and verified RBAC permissions.
    """

    def __init__(
        self,
        user_id: str,
        username: str,
        role: str,
        email: str = "",
        full_name: Optional[str] = None,
        is_authenticated: bool = True,
        is_jwt_authenticated: bool = False,
    ):
        self.user_id = str(user_id)
        self.username = username
        self.role = (role or "viewer").strip().lower()
        self.email = email
        self.full_name = full_name
        self.is_authenticated = is_authenticated
        self.is_jwt_authenticated = is_jwt_authenticated
        self.roles: List[str] = [self.role]
        self.permissions: Set[str] = get_role_permissions(self.role)

    def has_permission(self, permission: str) -> bool:
        """Check whether current context holds the given permission."""
        if not self.is_authenticated:
            return False
        return has_permission(self.role, permission)

    def verify_permission(self, permission: str) -> None:
        """
        Verify that caller possesses required permission,
        raising HTTP 403 Forbidden if unauthorized.
        """
        if not self.is_authenticated:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not self.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Forbidden: role '{self.role}' does not have '{permission}' permission.",
            )

    def __repr__(self) -> str:
        return f"<UserContext(username='{self.username}', role='{self.role}')>"


def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization"),
    x_auth_token: Optional[str] = Header(None, alias="X-Auth-Token"),
    x_authorized: Optional[str] = Header(None, alias="X-Authorized"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_name: Optional[str] = Header(None, alias="X-User-Name"),
    db: Session = Depends(get_db),
) -> AuthenticatedUserContext:
    """
    Main authentication dependency:
    1. If Bearer token is provided in Authorization or X-Auth-Token header:
       - Decodes JWT, validates signature and expiration.
       - Confirms user exists in DB and is active.
       - Populates AuthenticatedUserContext with true role and permissions.
    2. If no token is provided:
       - If X-Authorized is explicitly 'false', treats context as unauthorized.
       - If X-User-Role is supplied, adheres to that specified role context.
       - If settings.AUTH_ENFORCED is True, raises HTTP 401 Unauthorized.
       - If settings.AUTH_ENFORCED is False (dev/test fallback), defaults to dev admin.
    """
    # 1. Bearer Token Resolution
    token_str: Optional[str] = None
    if authorization:
        parts = authorization.strip().split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token_str = parts[1]
        elif len(parts) == 1 and parts[0].lower() != "bearer":
            token_str = parts[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authorization header format. Expected 'Bearer <token>'.",
                headers={"WWW-Authenticate": "Bearer"},
            )
    elif x_auth_token:
        token_str = x_auth_token.strip()

    if token_str:
        try:
            payload = decode_access_token(token_str)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication token has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except (jwt.PyJWTError, Exception):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials: invalid token.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        username = payload.get("sub")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token payload missing subject identifier.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account associated with token not found.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account is inactive.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return AuthenticatedUserContext(
            user_id=str(user.id),
            username=user.username,
            role=user.role,
            email=user.email,
            full_name=user.full_name,
            is_authenticated=True,
            is_jwt_authenticated=True,
        )

    # 2. Explicit Header Overrides (For Development / Regression Compatibility)
    if x_authorized is not None and str(x_authorized).lower() in ("false", "0", "no"):
        return AuthenticatedUserContext(
            user_id=x_user_id or "unauthorized-user",
            username=x_user_name or "Unauthorized User",
            role=x_user_role or "guest",
            is_authenticated=False,
            is_jwt_authenticated=False,
        )

    if x_user_role is not None:
        return AuthenticatedUserContext(
            user_id=x_user_id or "role-override-user",
            username=x_user_name or f"Test {x_user_role.capitalize()}",
            role=x_user_role,
            is_authenticated=True,
            is_jwt_authenticated=False,
        )

    # 3. No credentials provided
    if settings.AUTH_ENFORCED:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Fallback to dev context when AUTH_ENFORCED is False
    return AuthenticatedUserContext(
        user_id=x_user_id or "dev-admin-user",
        username=x_user_name or "Developer Administrator",
        role="admin",
        is_authenticated=True,
        is_jwt_authenticated=False,
    )


def require_permission(permission: str):
    """
    Dependency factory requiring a verified permission.
    Raises HTTP 403 Forbidden if caller's role does not possess the permission.
    """
    def permission_checker(
        user: AuthenticatedUserContext = Depends(get_current_user),
    ) -> AuthenticatedUserContext:
        user.verify_permission(permission)
        return user

    return permission_checker


def require_authenticated_user(
    user: AuthenticatedUserContext = Depends(get_current_user),
) -> AuthenticatedUserContext:
    """Dependency requiring caller to be fully authenticated."""
    if not user.is_authenticated:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user
