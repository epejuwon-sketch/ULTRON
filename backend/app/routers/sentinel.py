"""SENTINEL Passkeys / WebAuthn (Face ID) & Recovery Codes API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import get_current_principal
from app.services.sentinel_service import (
    complete_passkey_registration,
    complete_reauth_assertion,
    generate_recovery_codes,
    list_passkeys,
    revoke_passkey,
    start_passkey_registration,
    start_reauth_challenge,
    verify_recovery_code,
)

router = APIRouter(prefix="/api/v1/sentinel", tags=["SENTINEL Passkeys & Security Auth"])


class RegisterOptionsRequest(BaseModel):
    rp_id: str = Field(default="localhost", max_length=160)


class RegisterCompleteRequest(BaseModel):
    challenge_id: str = Field(min_length=4, max_length=64)
    credential_id: str = Field(min_length=8, max_length=255)
    public_key_b64: str = Field(min_length=16, max_length=4096)
    device_label: str = Field(min_length=2, max_length=160)
    transports: list[str] | None = None


class ReauthCompleteRequest(BaseModel):
    challenge_id: str = Field(min_length=4, max_length=64)
    credential_id: str = Field(min_length=8, max_length=255)
    assertion_proof: str = Field(min_length=8, max_length=4096)
    sign_count: int = Field(default=1, ge=0)


class VerifyRecoveryCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


@router.get("/passkeys")
def api_list_passkeys(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    items = list_passkeys(db, principal=principal)
    return {"total": len(items), "passkeys": items, "biometric_storage_policy": "ZERO_RAW_BIOMETRICS_STORED"}


@router.post("/passkeys/register/options")
def api_passkey_register_options(
    body: RegisterOptionsRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    return start_passkey_registration(db, principal=principal, rp_id=body.rp_id)


@router.post("/passkeys/register/complete", status_code=status.HTTP_201_CREATED)
def api_passkey_register_complete(
    body: RegisterCompleteRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    return complete_passkey_registration(
        db,
        principal=principal,
        challenge_id=body.challenge_id,
        credential_id=body.credential_id,
        public_key_b64=body.public_key_b64,
        device_label=body.device_label,
        transports=body.transports,
    )


@router.post("/passkeys/{credential_id}/revoke")
def api_revoke_passkey(
    credential_id: str,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    return revoke_passkey(db, principal=principal, credential_id=credential_id)


@router.post("/reauth/options")
def api_reauth_options(
    body: RegisterOptionsRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    return start_reauth_challenge(db, principal=principal, rp_id=body.rp_id)


@router.post("/reauth/complete")
def api_reauth_complete(
    body: ReauthCompleteRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return complete_reauth_assertion(
        db,
        principal=principal,
        settings=settings,
        challenge_id=body.challenge_id,
        credential_id=body.credential_id,
        assertion_proof=body.assertion_proof,
        sign_count=body.sign_count,
    )


@router.post("/recovery-codes/generate", status_code=status.HTTP_201_CREATED)
def api_generate_recovery_codes(
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    return generate_recovery_codes(db, principal=principal)


@router.post("/recovery-codes/verify")
def api_verify_recovery_code(
    body: VerifyRecoveryCodeRequest,
    principal: Principal = Depends(get_current_principal),
    db: Session = Depends(get_db),
) -> dict:
    return verify_recovery_code(db, principal=principal, code=body.code)
