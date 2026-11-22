"""Authentication, session lifecycle, token rotation, brute-force lockout, and RBAC user management."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import (
    AccountLockedError,
    AuthenticationError,
    AuthorizationError,
    ConflictError,
)
from app.core.permissions import Principal, Role
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.models import SessionRecord, Tenant, User
from app.db.repositories import append_audit_log


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def bootstrap_owner(
    db: Session,
    *,
    username: str,
    email: str,
    password: str,
    tenant_id: str,
    organization_name: str | None = None,
) -> User:
    """Create the initial OWNER user for a tenant. Fails if an OWNER already exists."""
    clean_username = username.strip()
    clean_tenant = tenant_id.strip()

    tenant = db.get(Tenant, clean_tenant)
    if tenant is None:
        tenant = Tenant(tenant_id=clean_tenant, name=organization_name or f"Tenant {clean_tenant}")
        db.add(tenant)
        db.flush()

    existing_owner = db.execute(
        select(User).where(User.tenant_id == clean_tenant, User.role == Role.OWNER.value)
    ).scalar_one_or_none()
    if existing_owner is not None:
        raise ConflictError("An OWNER account is already initialized for this tenant.")

    existing_username = db.execute(select(User).where(User.username == clean_username)).scalar_one_or_none()
    if existing_username is not None:
        raise ConflictError(f"Username '{clean_username}' is already taken.")

    user = User(
        user_id=f"usr_{uuid.uuid4().hex[:16]}",
        tenant_id=clean_tenant,
        username=clean_username,
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role=Role.OWNER.value,
        is_active=True,
    )
    db.add(user)
    append_audit_log(
        db,
        tenant_id=clean_tenant,
        actor=clean_username,
        action="AUTH_BOOTSTRAP_OWNER",
        resource=user.user_id,
        outcome="SUCCESS",
    )
    db.commit()
    db.refresh(user)
    return user


def create_user(
    db: Session,
    *,
    principal: Principal,
    username: str,
    email: str,
    password: str,
    role: Role,
) -> User:
    """Create a user within the caller's tenant. Only OWNER can assign OWNER role."""
    if role == Role.OWNER and principal.role != Role.OWNER:
        raise AuthorizationError("Only an OWNER may provision another OWNER account.")

    clean_username = username.strip()
    if db.execute(select(User).where(User.username == clean_username)).scalar_one_or_none() is not None:
        raise ConflictError(f"Username '{clean_username}' already exists.")

    user = User(
        user_id=f"usr_{uuid.uuid4().hex[:16]}",
        tenant_id=principal.tenant_id,
        username=clean_username,
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role=role.value,
        is_active=True,
    )
    db.add(user)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="USER_CREATED",
        resource=user.user_id,
        outcome=f"ROLE={role.value}",
    )
    db.commit()
    db.refresh(user)
    return user


def login_user(
    db: Session,
    *,
    username: str,
    password: str,
    settings: Settings,
    requested_tenant_id: str | None = None,
) -> dict[str, Any]:
    """Authenticate a user with Argon2id + lockout enforcement and issue JWT + refresh token."""
    now = datetime.now(timezone.utc)
    clean_username = username.strip()
    user = db.execute(select(User).where(User.username == clean_username)).scalar_one_or_none()
    if user is None or not user.is_active:
        append_audit_log(
            db,
            tenant_id=requested_tenant_id or settings.default_tenant_id,
            actor=clean_username or "UNKNOWN",
            action="AUTH_LOGIN_FAILED",
            resource="AUTH",
            outcome="INVALID_CREDENTIALS",
        )
        db.commit()
        raise AuthenticationError("Invalid username or password.")

    locked_until = _ensure_utc(user.locked_until)
    if locked_until is not None and now < locked_until:
        raise AccountLockedError(
            "Account temporarily locked due to repeated failed authentication attempts.",
            details={"locked_until": locked_until.isoformat()},
        )

    if not verify_password(password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= settings.max_failed_logins:
            user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
        append_audit_log(
            db,
            tenant_id=user.tenant_id,
            actor=user.username,
            action="AUTH_LOGIN_FAILED",
            resource=user.user_id,
            outcome=f"ATTEMPT_{user.failed_attempts}",
        )
        db.commit()
        raise AuthenticationError("Invalid username or password.")

    if requested_tenant_id and requested_tenant_id.strip() != user.tenant_id:
        append_audit_log(
            db,
            tenant_id=user.tenant_id,
            actor=user.username,
            action="AUTH_CROSS_TENANT_DENIED",
            resource=requested_tenant_id.strip(),
            outcome="DENIED",
        )
        db.commit()
        raise AuthorizationError("Cross-tenant login denied.")

    user.failed_attempts = 0
    user.locked_until = None

    access_token, jti, access_exp = create_access_token(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        tenant_id=user.tenant_id,
        settings=settings,
    )
    raw_refresh, refresh_hash = generate_refresh_token()
    refresh_exp = now + timedelta(days=settings.refresh_token_ttl_days)

    db.add(
        SessionRecord(
            jti=jti,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            refresh_token_hash=refresh_hash,
            access_expires_at=access_exp,
            refresh_expires_at=refresh_exp,
            revoked=False,
        )
    )
    append_audit_log(
        db,
        tenant_id=user.tenant_id,
        actor=user.username,
        action="AUTH_LOGIN_SUCCESS",
        resource=jti,
        outcome="GRANTED",
    )
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "Bearer",
        "expires_at": access_exp.isoformat(),
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "tenant_id": user.tenant_id,
        },
    }


def refresh_user_session(db: Session, *, refresh_token: str, settings: Settings) -> dict[str, Any]:
    """Rotate a valid refresh token and issue a fresh access + refresh token pair."""
    now = datetime.now(timezone.utc)
    digest = hash_token(refresh_token.strip())
    session = db.execute(
        select(SessionRecord).where(SessionRecord.refresh_token_hash == digest)
    ).scalar_one_or_none()
    if session is None or session.revoked:
        raise AuthenticationError("Invalid or revoked refresh token.")

    refresh_exp = _ensure_utc(session.refresh_expires_at)
    if refresh_exp is None or now >= refresh_exp:
        session.revoked = True
        session.revoked_at = now
        db.commit()
        raise AuthenticationError("Refresh token has expired.")

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is no longer active.")

    # Revoke rotated session
    session.revoked = True
    session.revoked_at = now

    access_token, jti, access_exp = create_access_token(
        user_id=user.user_id,
        username=user.username,
        role=user.role,
        tenant_id=user.tenant_id,
        settings=settings,
    )
    raw_refresh, refresh_hash = generate_refresh_token()
    new_refresh_exp = now + timedelta(days=settings.refresh_token_ttl_days)
    db.add(
        SessionRecord(
            jti=jti,
            user_id=user.user_id,
            tenant_id=user.tenant_id,
            refresh_token_hash=refresh_hash,
            access_expires_at=access_exp,
            refresh_expires_at=new_refresh_exp,
            revoked=False,
        )
    )
    append_audit_log(
        db,
        tenant_id=user.tenant_id,
        actor=user.username,
        action="AUTH_TOKEN_REFRESHED",
        resource=jti,
        outcome="ROTATED",
    )
    db.commit()

    return {
        "access_token": access_token,
        "refresh_token": raw_refresh,
        "token_type": "Bearer",
        "expires_at": access_exp.isoformat(),
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "email": user.email,
            "role": user.role,
            "tenant_id": user.tenant_id,
        },
    }


def revoke_session(db: Session, *, principal: Principal) -> None:
    """Immediately revoke the caller's active JWT session."""
    session = db.get(SessionRecord, principal.jti)
    if session is not None and not session.revoked:
        session.revoked = True
        session.revoked_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="AUTH_SESSION_REVOKED",
        resource=principal.jti,
        outcome="REVOKED",
    )
    db.commit()


def authenticate_bearer_token(db: Session, *, token: str, settings: Settings) -> Principal:
    """Validate JWT signature + active non-revoked session record and return Principal."""
    payload = decode_access_token(token, settings)
    jti = str(payload["jti"])
    session = db.get(SessionRecord, jti)
    if session is None or session.revoked:
        raise AuthenticationError("Session has been revoked or does not exist.")

    user = db.get(User, str(payload["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("Authenticated user is inactive or missing.")

    return Principal(
        user_id=user.user_id,
        username=user.username,
        role=Role(user.role),
        tenant_id=user.tenant_id,
        jti=jti,
    )
