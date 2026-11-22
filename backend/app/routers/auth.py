"""Authentication, token refresh/revocation, and RBAC user provisioning routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.models import User
from app.db.session import get_db
from app.routers.deps import get_current_principal, require_perm
from app.schemas import BootstrapOwnerRequest, CreateUserRequest, LoginRequest, RefreshRequest
from app.services.auth_service import (
    bootstrap_owner,
    create_user,
    login_user,
    refresh_user_session,
    revoke_session,
)

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication & RBAC"])


@router.post("/bootstrap-owner", status_code=status.HTTP_201_CREATED)
def api_bootstrap_owner(
    body: BootstrapOwnerRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Initialize the first OWNER account for a tenant (one-time per tenant)."""
    user = bootstrap_owner(
        db,
        username=body.username,
        email=body.email,
        password=body.password,
        tenant_id=body.tenant_id or settings.default_tenant_id,
        organization_name=body.organization_name,
    )
    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
    }


@router.post("/login")
def api_login(
    body: LoginRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Authenticate with username & password and receive JWT access + refresh tokens."""
    return login_user(
        db,
        username=body.username,
        password=body.password,
        settings=settings,
        requested_tenant_id=body.tenant_id,
    )


@router.post("/refresh")
def api_refresh(
    body: RefreshRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Rotate refresh token and return a new access + refresh token pair."""
    return refresh_user_session(db, refresh_token=body.refresh_token, settings=settings)


@router.post("/logout")
def api_logout(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    """Immediately revoke the current Bearer token session."""
    revoke_session(db, principal=principal)
    return {"status": "revoked", "jti": principal.jti}


@router.get("/me")
def api_me(principal: Principal = Depends(get_current_principal)) -> dict:
    """Return authenticated principal identity, tenant binding, and RBAC permissions."""
    return {
        "user_id": principal.user_id,
        "username": principal.username,
        "role": principal.role.value,
        "tenant_id": principal.tenant_id,
        "permissions": sorted(principal.permissions),
    }


@router.post("/users", status_code=status.HTTP_201_CREATED)
def api_create_user(
    body: CreateUserRequest,
    principal: Principal = Depends(require_perm("users:manage")),
    db: Session = Depends(get_db),
) -> dict:
    """Provision a new user within the caller's tenant (OWNER/ADMIN only)."""
    user = create_user(
        db,
        principal=principal,
        username=body.username,
        email=body.email,
        password=body.password,
        role=body.role,
    )
    return {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
    }


@router.get("/users")
def api_list_users(
    principal: Principal = Depends(require_perm("users:manage")),
    db: Session = Depends(get_db),
) -> dict:
    """List all users in the caller's tenant (password hashes are never returned)."""
    rows = db.execute(
        select(User).where(User.tenant_id == principal.tenant_id).order_by(User.created_at.asc())
    ).scalars().all()
    return {
        "tenant_id": principal.tenant_id,
        "users": [
            {
                "user_id": u.user_id,
                "username": u.username,
                "email": u.email,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat(),
            }
            for u in rows
        ],
    }
