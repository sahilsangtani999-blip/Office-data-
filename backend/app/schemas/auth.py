"""
Pydantic schemas for authentication and user management.
Phase 2.5 — Authentication & Office Permissions.
"""

import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Payload for user login authentication."""
    username: str = Field(..., description="Office username", min_length=1)
    password: str = Field(..., description="User password", min_length=1)


class UserResponse(BaseModel):
    """Public representation of an authenticated user."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    full_name: Optional[str] = None
    role: str
    permissions: List[str] = Field(default_factory=list)
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """JWT Bearer authentication response payload."""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse


class UserCreateRequest(BaseModel):
    """Payload for user provisioning."""
    username: str = Field(..., min_length=3, max_length=100)
    email: str = Field(..., min_length=5, max_length=255)
    password: str = Field(..., min_length=6)
    role: str = Field(default="viewer")
    full_name: Optional[str] = None
