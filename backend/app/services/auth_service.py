"""
Authentication and User management service.
Phase 2.5 — Authentication & Office Permissions.
"""

from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from app.core.permissions import get_role_permissions
from app.core.security import get_password_hash, verify_password
from app.models import User
from app.schemas.auth import UserResponse


DEFAULT_SEED_USERS = [
    {
        "username": "admin",
        "email": "admin@rssb.local",
        "password": "admin123",
        "role": "admin",
        "full_name": "RSSB Office Administrator",
    },
    {
        "username": "reviewer",
        "email": "reviewer@rssb.local",
        "password": "reviewer123",
        "role": "reviewer",
        "full_name": "RSSB Office Reviewer",
    },
    {
        "username": "uploader",
        "email": "uploader@rssb.local",
        "password": "uploader123",
        "role": "uploader",
        "full_name": "RSSB Data Operator",
    },
    {
        "username": "viewer",
        "email": "viewer@rssb.local",
        "password": "viewer123",
        "role": "viewer",
        "full_name": "RSSB Office Viewer",
    },
]


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """Retrieve an active or inactive user by username."""
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """Retrieve an active or inactive user by email."""
    return db.query(User).filter(User.email == email).first()


def authenticate_user(
    db: Session, username: str, password: str
) -> Optional[User]:
    """
    Authenticate a user by username and password.
    Returns the user instance if credentials are valid and account is active, else None.
    Auto-seeds default office accounts if the users table is empty.
    """
    user = get_user_by_username(db, username)
    if not user:
        # If users table is empty, auto-seed default accounts on demand
        if db.query(User).count() == 0:
            seed_default_users(db)
            user = get_user_by_username(db, username)
        if not user:
            return None
    if not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(
    db: Session,
    username: str,
    email: str,
    password: str,
    role: str = "viewer",
    full_name: Optional[str] = None,
    is_active: bool = True,
    auto_commit: bool = True,
) -> User:
    """Create a new user with securely hashed password."""
    user = User(
        username=username,
        email=email,
        hashed_password=get_password_hash(password),
        role=role,
        full_name=full_name,
        is_active=is_active,
    )
    db.add(user)
    if auto_commit:
        db.commit()
        db.refresh(user)
    return user


def user_to_response(user: User) -> UserResponse:
    """Convert User ORM model to UserResponse schema including evaluated permissions."""
    permissions = sorted(list(get_role_permissions(user.role)))
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        permissions=permissions,
        is_active=user.is_active,
        created_at=user.created_at,
    )


def seed_default_users(db: Session) -> List[User]:
    """
    Idempotently seeds standard office users for development, testing, and operations.
    If a user already exists, it is left untouched.
    """
    seeded = []
    for spec in DEFAULT_SEED_USERS:
        existing = get_user_by_username(db, spec["username"])
        if not existing:
            new_user = create_user(
                db=db,
                username=spec["username"],
                email=spec["email"],
                password=spec["password"],
                role=spec["role"],
                full_name=spec["full_name"],
                auto_commit=False,
            )
            seeded.append(new_user)
        else:
            seeded.append(existing)
    db.commit()
    return seeded
