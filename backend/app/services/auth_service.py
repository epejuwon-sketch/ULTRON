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
        raise AuthenticationError("Invalid username or password.", code="INVALID_CREDENTIALS")

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
        raise AuthenticationError("Invalid username or password.", code="INVALID_CREDENTIALS")

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
    refresh_exp = now + timedelta(seconds=settings.session_duration_seconds)

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
    """Rotate a valid refresh token and issue a fresh access + refresh token pair bound to the 24h session window."""
    now = datetime.now(timezone.utc)
    digest = hash_token(refresh_token.strip())
    session = db.execute(
        select(SessionRecord).where(SessionRecord.refresh_token_hash == digest)
    ).scalar_one_or_none()

    if session is not None and session.revoked:
        append_audit_log(
            db,
            tenant_id=session.tenant_id,
            actor=session.user_id,
            action="AUTH_REFRESH_TOKEN_REUSE_DETECTED",
            resource=session.jti,
            outcome="REVOKED_REUSE_BLOCKED",
        )
        db.commit()
        raise AuthenticationError("Invalid or revoked refresh token.", code="SESSION_REVOKED")

    if session is None:
        raise AuthenticationError("Invalid or revoked refresh token.", code="SESSION_REVOKED")

    refresh_exp = _ensure_utc(session.refresh_expires_at)
    if refresh_exp is None or now >= refresh_exp:
        session.revoked = True
        session.revoked_at = now
        db.commit()
        raise AuthenticationError("Session has expired after 24 hours. Please sign in again.", code="SESSION_EXPIRED")

    user = db.get(User, session.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is no longer active.", code="ACCOUNT_INACTIVE")

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
    # Preserve original 24-hour expiration window across rotations so session resets after 24 hours
    new_refresh_exp = refresh_exp
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
        raise AuthenticationError("Session has been revoked or does not exist.", code="SESSION_REVOKED")

    user = db.get(User, str(payload["sub"]))
    if user is None or not user.is_active:
        raise AuthenticationError("Authenticated user is inactive or missing.", code="ACCOUNT_INACTIVE")

    return Principal(
        user_id=user.user_id,
        username=user.username,
        role=Role(user.role),
        tenant_id=user.tenant_id,
        jti=jti,
    )


def _issue_verification_token(
    db: Session,
    *,
    tenant_id: str,
    user_id: str,
    purpose: str,
    ttl_hours: int,
) -> str:
    import secrets
    from app.db.models import AuthVerificationTokenRecord

    raw_token = f"ultron_{purpose.lower()}_{secrets.token_urlsafe(32)}"
    token_digest = hash_token(raw_token)
    now = datetime.now(timezone.utc)
    rec = AuthVerificationTokenRecord(
        token_id=f"avt_{uuid.uuid4().hex[:14]}",
        tenant_id=tenant_id,
        user_id=user_id,
        purpose=purpose,
        token_hash=token_digest,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    db.add(rec)
    return raw_token


def register_customer_user(
    db: Session,
    *,
    username: str,
    email: str,
    password: str,
    tenant_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Public self-registration for Caravan customers (always Role.VIEWER)."""
    clean_username = username.strip()
    clean_email = email.strip().lower()
    clean_tenant = tenant_id.strip()

    if len(clean_username) < 3 or "@" not in clean_email or "." not in clean_email.split("@")[-1]:
        raise ConflictError("Valid username (>=3 chars) and email address are required.")

    tenant = db.get(Tenant, clean_tenant)
    if tenant is None:
        tenant = Tenant(tenant_id=clean_tenant, name=f"Tenant {clean_tenant}")
        db.add(tenant)
        db.flush()

    existing_u = db.execute(select(User).where(User.username == clean_username)).scalar_one_or_none()
    existing_e = db.execute(select(User).where(User.email == clean_email, User.tenant_id == clean_tenant)).scalar_one_or_none()
    if existing_u is not None or existing_e is not None:
        # Generic conflict message to avoid revealing which field collided
        raise ConflictError("An account with those registration details already exists.")

    user = User(
        user_id=f"usr_{uuid.uuid4().hex[:16]}",
        tenant_id=clean_tenant,
        username=clean_username,
        email=clean_email,
        password_hash=hash_password(password),
        role=Role.VIEWER.value,
        is_active=True,
    )
    db.add(user)
    db.flush()

    raw_token = _issue_verification_token(
        db,
        tenant_id=clean_tenant,
        user_id=user.user_id,
        purpose="EMAIL_VERIFY",
        ttl_hours=24,
    )

    from app.db.models import CaravanNotificationDeliveryRecord

    db.add(
        CaravanNotificationDeliveryRecord(
            delivery_id=f"cdlv_{uuid.uuid4().hex[:14]}",
            tenant_id=clean_tenant,
            account_id=user.user_id,
            channel="EMAIL",
            event_type="EMAIL_VERIFICATION",
            recipient=clean_email,
            subject="Verify your Caravan account email",
            body="Use the verification link sent to your email to verify your Caravan account.",
            status="QUEUED",
        )
    )
    append_audit_log(
        db,
        tenant_id=clean_tenant,
        actor=clean_username,
        action="AUTH_CUSTOMER_REGISTERED",
        resource=user.user_id,
        outcome="VIEWER_EMAIL_VERIFICATION_QUEUED",
    )
    db.commit()
    db.refresh(user)
    out: dict[str, Any] = {
        "user_id": user.user_id,
        "username": user.username,
        "email": user.email,
        "role": user.role,
        "tenant_id": user.tenant_id,
        "email_verified": False,
        "verification_queued": True,
    }
    if settings.ultron_env == "test":
        out["test_verification_token"] = raw_token
    return out


def confirm_email_verification(db: Session, *, token: str) -> dict[str, Any]:
    """Confirm a single-use email verification token."""
    from app.db.models import AuthVerificationTokenRecord

    digest = hash_token(token.strip())
    rec = db.execute(
        select(AuthVerificationTokenRecord).where(
            AuthVerificationTokenRecord.token_hash == digest,
            AuthVerificationTokenRecord.purpose == "EMAIL_VERIFY",
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if rec is None or rec.used_at is not None or _ensure_utc(rec.expires_at) < now:
        raise AuthenticationError("Invalid or expired verification token.")
    rec.used_at = now
    append_audit_log(
        db,
        tenant_id=rec.tenant_id,
        actor=rec.user_id,
        action="AUTH_EMAIL_VERIFIED",
        resource=rec.token_id,
        outcome="VERIFIED",
    )
    db.commit()
    return {"status": "verified", "user_id": rec.user_id, "verified_at": now.isoformat()}


def request_password_reset(
    db: Session,
    *,
    email: str,
    tenant_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Non-enumerating password reset request. Always returns generic accepted message."""
    clean_email = email.strip().lower()
    user = db.execute(
        select(User).where(User.email == clean_email, User.tenant_id == tenant_id.strip(), User.is_active == True)  # noqa: E712
    ).scalar_one_or_none()
    raw_token: str | None = None
    if user is not None:
        raw_token = _issue_verification_token(
            db,
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            purpose="PASSWORD_RESET",
            ttl_hours=1,
        )
        from app.db.models import CaravanNotificationDeliveryRecord

        db.add(
            CaravanNotificationDeliveryRecord(
                delivery_id=f"cdlv_{uuid.uuid4().hex[:14]}",
                tenant_id=user.tenant_id,
                account_id=user.user_id,
                channel="EMAIL",
                event_type="PASSWORD_RESET",
                recipient=user.email,
                subject="Caravan password recovery",
                body="A password recovery request was initiated for your account.",
                status="QUEUED",
            )
        )
        append_audit_log(
            db,
            tenant_id=user.tenant_id,
            actor=user.username,
            action="AUTH_PASSWORD_RESET_REQUESTED",
            resource=user.user_id,
            outcome="QUEUED",
        )
        db.commit()
    out: dict[str, Any] = {
        "status": "accepted",
        "message": "If an account matches that email, password recovery instructions have been queued.",
    }
    if settings.ultron_env == "test" and raw_token is not None:
        out["test_reset_token"] = raw_token
    return out


def confirm_password_reset(db: Session, *, token: str, new_password: str) -> dict[str, Any]:
    """Verify single-use reset token, update Argon2id password, and revoke all active sessions."""
    from app.db.models import AuthVerificationTokenRecord

    digest = hash_token(token.strip())
    rec = db.execute(
        select(AuthVerificationTokenRecord).where(
            AuthVerificationTokenRecord.token_hash == digest,
            AuthVerificationTokenRecord.purpose == "PASSWORD_RESET",
        )
    ).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if rec is None or rec.used_at is not None or _ensure_utc(rec.expires_at) < now:
        raise AuthenticationError("Invalid or expired password reset token.")

    user = db.get(User, rec.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is inactive or unavailable.")

    user.password_hash = hash_password(new_password)
    user.failed_attempts = 0
    user.locked_until = None
    rec.used_at = now

    # Revoke all active sessions for this user upon password reset
    active_sessions = db.execute(
        select(SessionRecord).where(SessionRecord.user_id == user.user_id, SessionRecord.revoked == False)  # noqa: E712
    ).scalars().all()
    for sess in active_sessions:
        sess.revoked = True
        sess.revoked_at = now

    append_audit_log(
        db,
        tenant_id=user.tenant_id,
        actor=user.username,
        action="AUTH_PASSWORD_RESET_COMPLETED",
        resource=user.user_id,
        outcome=f"REVOKED_SESSIONS={len(active_sessions)}",
    )
    db.commit()
    return {"status": "password_updated", "revoked_sessions": len(active_sessions)}

