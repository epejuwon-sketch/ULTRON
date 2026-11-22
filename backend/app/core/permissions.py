"""Role-based access control (RBAC) and strict multi-tenant isolation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.core.exceptions import AuthorizationError


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    VIEWER = "VIEWER"
    AGENT = "AGENT"


ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.OWNER: frozenset(
        {
            "agents:read",
            "agents:invoke",
            "agents:manage",
            "tasks:read",
            "tasks:create",
            "tasks:execute",
            "tasks:cancel",
            "approvals:read",
            "approvals:decide",
            "memory:read",
            "memory:write",
            "memory:delete",
            "tools:read",
            "tools:execute",
            "vault:read",
            "vault:write",
            "audit:read",
            "users:manage",
            "integrations:verify",
            "finance:read",
            "finance:write",
            "finance:approve",
            "projects:read",
            "projects:write",
            "projects:deploy",
            "notifications:read",
            "notifications:write",
            "settings:read",
            "settings:write",
            "monitoring:read",
            "jobs:manage",
        }
    ),
    Role.ADMIN: frozenset(
        {
            "agents:read",
            "agents:invoke",
            "agents:manage",
            "tasks:read",
            "tasks:create",
            "tasks:execute",
            "tasks:cancel",
            "approvals:read",
            "approvals:decide",
            "memory:read",
            "memory:write",
            "memory:delete",
            "tools:read",
            "tools:execute",
            "vault:read",
            "vault:write",
            "audit:read",
            "users:manage",
            "integrations:verify",
            "finance:read",
            "finance:write",
            "projects:read",
            "projects:write",
            "notifications:read",
            "notifications:write",
            "settings:read",
            "settings:write",
            "monitoring:read",
            "jobs:manage",
        }
    ),
    Role.OPERATOR: frozenset(
        {
            "agents:read",
            "agents:invoke",
            "tasks:read",
            "tasks:create",
            "tasks:execute",
            "tasks:cancel",
            "approvals:read",
            "memory:read",
            "memory:write",
            "tools:read",
            "tools:execute",
            "audit:read",
            "integrations:verify",
            "finance:read",
            "finance:write",
            "projects:read",
            "projects:write",
            "notifications:read",
            "notifications:write",
            "settings:read",
            "monitoring:read",
        }
    ),
    Role.VIEWER: frozenset(
        {
            "agents:read",
            "tasks:read",
            "approvals:read",
            "memory:read",
            "tools:read",
            "audit:read",
            "finance:read",
            "projects:read",
            "notifications:read",
            "settings:read",
            "monitoring:read",
        }
    ),
    Role.AGENT: frozenset(
        {
            "agents:read",
            "agents:invoke",
            "tasks:read",
            "memory:read",
            "memory:write",
            "tools:read",
            "tools:execute",
            "projects:read",
            "notifications:read",
        }
    ),
}


@dataclass(frozen=True)
class Principal:
    """Authenticated request principal bound to a single tenant and role."""

    user_id: str
    username: str
    role: Role
    tenant_id: str
    jti: str

    @property
    def permissions(self) -> frozenset[str]:
        return ROLE_PERMISSIONS.get(self.role, frozenset())

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions


def require_permission(principal: Principal, permission: str) -> None:
    """Raise AuthorizationError if the principal does not hold the required permission."""
    if not principal.has_permission(permission):
        raise AuthorizationError(
            f"Role '{principal.role.value}' lacks required permission '{permission}'.",
            details={"required_permission": permission, "role": principal.role.value},
        )


def assert_tenant_access(principal: Principal, requested_tenant_id: str | None) -> str:
    """Enforce tenant isolation and prevent cross-tenant header/payload spoofing."""
    if requested_tenant_id and requested_tenant_id.strip() != principal.tenant_id:
        raise AuthorizationError(
            "Cross-tenant access denied.",
            details={"principal_tenant": principal.tenant_id, "requested_tenant": requested_tenant_id.strip()},
        )
    return principal.tenant_id
