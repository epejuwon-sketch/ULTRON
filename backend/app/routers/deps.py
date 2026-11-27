"""Reusable FastAPI authentication, RBAC permission, and tenant-isolation dependencies."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError
from app.core.permissions import Principal, assert_tenant_access, require_permission
from app.db.session import get_db
from app.services.auth_service import authenticate_bearer_token


def get_current_principal(
    request: Request,
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-ID"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> Principal:
    """Extract and validate Bearer JWT + active session + optional X-Tenant-ID header."""
    auth_val = authorization
    if not auth_val or not auth_val.strip():
        # Defensive fallback for case-normalized proxy headers
        auth_val = request.headers.get("authorization") or request.headers.get("Authorization")

    if not auth_val or not auth_val.strip():
        # Fallback for query-string token in streaming/preview contexts
        token_param = request.query_params.get("token") or request.query_params.get("access_token")
        if token_param and token_param.strip():
            auth_val = f"Bearer {token_param.strip()}"

    if not auth_val or not auth_val.strip():
        raise AuthenticationError("Missing Authorization Bearer token.")

    parts = auth_val.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1].strip():
        raise AuthenticationError("Invalid Authorization header. Expected 'Bearer <token>'.")

    principal = authenticate_bearer_token(db, token=parts[1].strip(), settings=settings)
    assert_tenant_access(principal, x_tenant_id or request.headers.get("x-tenant-id"))
    return principal


def require_perm(permission: str) -> Callable[[Principal], Principal]:
    """Dependency factory asserting a specific RBAC permission on the authenticated principal."""

    def _checker(principal: Principal = Depends(get_current_principal)) -> Principal:
        require_permission(principal, permission)
        return principal

    return _checker
