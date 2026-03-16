"""Role-Based Access Control (RBAC) for HordeForge."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from typing import Any


class Role(str, Enum):
    """Available roles in the system."""

    ADMIN = "admin"
    OPERATOR = "operator"
    VIEWER = "viewer"


class Permission(str, Enum):
    """Available permissions."""

    # Pipeline operations
    PIPELINE_RUN = "pipeline:run"
    PIPELINE_READ = "pipeline:read"
    PIPELINE_CANCEL = "pipeline:cancel"

    # Override operations
    OVERRIDE_EXECUTE = "override:execute"

    # Cron operations
    CRON_TRIGGER = "cron:trigger"
    CRON_READ = "cron:read"

    # Queue operations
    QUEUE_DRAIN = "queue:drain"
    QUEUE_READ = "queue:read"

    # Runs operations
    RUNS_READ = "runs:read"
    RUNS_WRITE = "runs:write"

    # Metrics
    METRICS_READ = "metrics:read"

    # Admin
    ADMIN_ACCESS = "admin:access"


# Role to permissions mapping
ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.ADMIN: frozenset(
        {
            Permission.PIPELINE_RUN,
            Permission.PIPELINE_READ,
            Permission.PIPELINE_CANCEL,
            Permission.OVERRIDE_EXECUTE,
            Permission.CRON_TRIGGER,
            Permission.CRON_READ,
            Permission.QUEUE_DRAIN,
            Permission.QUEUE_READ,
            Permission.RUNS_READ,
            Permission.RUNS_WRITE,
            Permission.METRICS_READ,
            Permission.ADMIN_ACCESS,
        }
    ),
    Role.OPERATOR: frozenset(
        {
            Permission.PIPELINE_RUN,
            Permission.PIPELINE_READ,
            Permission.OVERRIDE_EXECUTE,
            Permission.CRON_TRIGGER,
            Permission.CRON_READ,
            Permission.QUEUE_DRAIN,
            Permission.QUEUE_READ,
            Permission.RUNS_READ,
            Permission.METRICS_READ,
        }
    ),
    Role.VIEWER: frozenset(
        {
            Permission.PIPELINE_READ,
            Permission.CRON_READ,
            Permission.QUEUE_READ,
            Permission.RUNS_READ,
            Permission.METRICS_READ,
        }
    ),
}


@dataclass(frozen=True)
class RBACUser:
    """User with role information."""

    user_id: str
    role: Role
    email: str | None = None
    tenant_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has a specific permission."""
        return permission in ROLE_PERMISSIONS.get(self.role, frozenset())


def check_permission(required_permission: Permission) -> Callable:
    """Decorator to check if user has required permission."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            # Get user from request state
            request = kwargs.get("request")
            if request and hasattr(request.state, "user"):
                user_data = request.state.user
                if isinstance(user_data, dict):
                    role_str = user_data.get("role", "viewer")
                    try:
                        role = Role(role_str)
                    except ValueError:
                        role = Role.VIEWER
                    user = RBACUser(
                        user_id=user_data.get("user_id", ""),
                        role=role,
                        email=user_data.get("email"),
                    )
                    if not user.has_permission(required_permission):
                        from fastapi import HTTPException

                        raise HTTPException(
                            status_code=403,
                            detail={
                                "error": "forbidden",
                                "message": f"Permission denied: {required_permission.value}",
                            },
                        )
            return func(*args, **kwargs)

        return wrapper

    return decorator


def get_role_permissions(role: Role) -> frozenset[Permission]:
    """Get all permissions for a role."""
    return ROLE_PERMISSIONS.get(role, frozenset())


def get_user_permissions(user: RBACUser) -> frozenset[Permission]:
    """Get all permissions for a user."""
    return ROLE_PERMISSIONS.get(user.role, frozenset())


def has_role_permission(role: Role, permission: Permission) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
