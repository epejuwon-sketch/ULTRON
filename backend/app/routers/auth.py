"""Authentication, token refresh/revocation, and RBAC user provisioning routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError
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
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Authenticate with username & password and receive JWT access + refresh tokens."""
    res = login_user(
        db,
        username=body.username,
        password=body.password,
        settings=settings,
        requested_tenant_id=body.tenant_id,
    )
    raw_refresh = res.get("refresh_token")
    if raw_refresh:
        is_secure = settings.ultron_env == "production" or bool(settings.vercel)
        response.set_cookie(
            key="ultron_refresh_token",
            value=raw_refresh,
            httponly=True,
            secure=is_secure,
            samesite="lax",
            max_age=int(settings.refresh_token_ttl_days * 86400),
            path="/api/v1/auth",
        )
    return res


@router.post("/refresh")
def api_refresh(
    request: Request,
    response: Response,
    body: RefreshRequest | None = None,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Rotate refresh token and return a new access + refresh token pair."""
    token_candidate = ""
    if body and body.refresh_token:
        token_candidate = body.refresh_token.strip()
    if not token_candidate:
        token_candidate = request.cookies.get("ultron_refresh_token", "").strip()

    if not token_candidate:
        raise AuthenticationError("Refresh token required.")

    res = refresh_user_session(db, refresh_token=token_candidate, settings=settings)
    raw_refresh = res.get("refresh_token")
    if raw_refresh:
        is_secure = settings.ultron_env == "production" or bool(settings.vercel)
        response.set_cookie(
            key="ultron_refresh_token",
            value=raw_refresh,
            httponly=True,
            secure=is_secure,
            samesite="lax",
            max_age=int(settings.refresh_token_ttl_days * 86400),
            path="/api/v1/auth",
        )
    return res


@router.post("/logout")
def api_logout(
    response: Response,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    """Immediately revoke the current Bearer token session."""
    revoke_session(db, principal=principal)
    response.delete_cookie(key="ultron_refresh_token", path="/api/v1/auth")
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


from pydantic import BaseModel, Field  # noqa: E402


class RegisterCustomerRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=64)


class ConfirmTokenRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)


class PasswordResetRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    tenant_id: str | None = Field(default=None, max_length=64)


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=10, max_length=512)
    new_password: str = Field(min_length=8, max_length=128)


@router.post("/register", status_code=status.HTTP_201_CREATED)
def api_register_customer(
    body: RegisterCustomerRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Public customer self-registration (always assigns VIEWER role)."""
    from app.services.auth_service import register_customer_user

    return register_customer_user(
        db,
        username=body.username,
        email=body.email,
        password=body.password,
        tenant_id=body.tenant_id or settings.default_tenant_id,
        settings=settings,
    )


@router.post("/verify-email/confirm")
def api_confirm_email_verification(
    body: ConfirmTokenRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Confirm single-use email verification token."""
    from app.services.auth_service import confirm_email_verification

    return confirm_email_verification(db, token=body.token)


@router.post("/password-reset/request")
def api_request_password_reset(
    body: PasswordResetRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Non-enumerating password recovery request."""
    from app.services.auth_service import request_password_reset

    return request_password_reset(
        db,
        email=body.email,
        tenant_id=body.tenant_id or settings.default_tenant_id,
        settings=settings,
    )


@router.post("/password-reset/confirm")
def api_confirm_password_reset(
    body: PasswordResetConfirmRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Confirm password reset token, update password, and revoke active sessions."""
    from app.services.auth_service import confirm_password_reset

    return confirm_password_reset(db, token=body.token, new_password=body.new_password)

