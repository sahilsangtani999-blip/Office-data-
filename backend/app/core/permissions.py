"""
Role-based Access Control (RBAC) definitions and permissions matrix.
Phase 2.5 — Authentication & Office Permissions.
"""

from typing import Dict, Set

# Office Roles
ROLE_ADMIN = "admin"
ROLE_REVIEWER = "reviewer"
ROLE_UPLOADER = "uploader"
ROLE_VIEWER = "viewer"

ALL_ROLES = {ROLE_ADMIN, ROLE_REVIEWER, ROLE_UPLOADER, ROLE_VIEWER}

# Explicit Office Permissions
PERM_READ = "read"
PERM_READ_SOURCES = "read_sources"
PERM_UPLOAD = "upload"
PERM_REVIEW = "review"
PERM_GENERATE_REPORTS = "generate_reports"
PERM_ADMIN = "admin"

# Role -> Allowed Permissions Matrix
ROLE_PERMISSIONS: Dict[str, Set[str]] = {
    ROLE_ADMIN: {
        PERM_READ,
        PERM_READ_SOURCES,
        PERM_UPLOAD,
        PERM_REVIEW,
        PERM_GENERATE_REPORTS,
        PERM_ADMIN,
    },
    ROLE_REVIEWER: {
        PERM_READ,
        PERM_READ_SOURCES,
        PERM_REVIEW,
        PERM_GENERATE_REPORTS,
    },
    ROLE_UPLOADER: {
        PERM_READ,
        PERM_READ_SOURCES,
        PERM_UPLOAD,
    },
    ROLE_VIEWER: {
        PERM_READ,
        PERM_READ_SOURCES,
    },
}


def get_role_permissions(role: str) -> Set[str]:
    """Retrieve explicit permissions set for a given role name."""
    normalized_role = (role or "").strip().lower()
    return ROLE_PERMISSIONS.get(normalized_role, set())


def has_permission(role: str, permission: str) -> bool:
    """
    Check if a specific role possesses the requested permission.
    Admin role inherently satisfies all permissions.
    """
    normalized_role = (role or "").strip().lower()
    perms = get_role_permissions(normalized_role)
    if PERM_ADMIN in perms or permission in perms:
        return True
    return False
