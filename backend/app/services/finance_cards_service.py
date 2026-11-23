"""ULTRON Finance Cards service: safe display cards, Pillow card-photo credential redaction, and honest provider linking."""

from __future__ import annotations

import base64
import io
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any

from PIL import Image, ImageDraw, ImageFilter, ImageOps
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.permissions import Principal
from app.core.secret_interceptor import contains_raw_payment_card_or_cvv
from app.db.models import FinanceCardRecord
from app.db.repositories import append_audit_log
from app.services.file_hub_service import generate_and_store_file

SUPPORTED_CARD_LINK_PROVIDERS = {
    "paystack": "Paystack tokenized authorization reference",
    "flutterwave": "Flutterwave tokenized card reference",
    "stripe": "Stripe PaymentMethod token (pm_...)",
}

VALID_NETWORKS = frozenset({"", "VISA", "MASTERCARD", "VERVE", "AMEX", "OTHER"})
VALID_CARD_TYPES = frozenset({"VIRTUAL", "PHYSICAL", "CORPORATE", "DEBIT", "CREDIT"})
VALID_SCOPES = frozenset({"BUSINESS", "PERSONAL"})
VALID_EFFECTS = frozenset({"glass", "matte", "metallic", "holographic"})
_RAW_DIGITS_RE = re.compile(r"\b(?:\d[ -]*?){13,19}\b")


def _reject_sensitive_input(*values: str | None) -> None:
    for val in values:
        if not val:
            continue
        if contains_raw_payment_card_or_cvv(val) or _RAW_DIGITS_RE.search(val):
            raise ValidationError(
                "Raw payment card numbers (PAN), CVV, expiry, or PIN values are strictly prohibited. "
                "Use only safe card nicknames and provider-issued token references."
            )


def _validate_provider_token_ref(provider_key: str | None, provider_token_ref: str | None) -> None:
    if not provider_token_ref:
        return
    tok = provider_token_ref.strip()
    if len(tok) < 8 or any(ch.isspace() for ch in tok):
        raise ValidationError("provider_token_ref must be a valid provider-issued token (min 8 chars, no spaces).")
    if (provider_key or "").strip().lower() == "stripe" and not tok.startswith(("pm_", "card_", "tok_")):
        raise ValidationError("Stripe provider_token_ref must begin with 'pm_', 'card_', or 'tok_'.")


def _resolve_connection_status(
    _db: Session,
    *,
    tenant_id: str,
    provider_key: str | None,
    provider_token_ref: str | None,
    last_synced_at: datetime | None = None,
) -> tuple[str, str]:
    clean_prov = (provider_key or "").strip().lower()
    clean_tok = (provider_token_ref or "").strip()
    if not clean_prov or clean_prov in {"manual", "display_only", "custom"}:
        return "DISPLAY_ONLY", "Visual display card only. No external payment rail connected."
    if clean_prov not in SUPPORTED_CARD_LINK_PROVIDERS:
        return (
            "UNSUPPORTED_PROVIDER",
            f"Provider '{clean_prov}' does not support direct card linking in ULTRON. Stored as visual display card only.",
        )
    if not clean_tok:
        return (
            "AWAITING_PROVIDER_AUTH",
            f"{SUPPORTED_CARD_LINK_PROVIDERS[clean_prov]} required to initiate card linking.",
        )
    if last_synced_at is not None:
        return "PROVIDER_LINKED", f"Card-level authorization verified via {clean_prov}."
    return (
        "AWAITING_PROVIDER_AUTH",
        f"Tokenized reference recorded; card-level authorization with {clean_prov} has not been live-verified yet.",
    )


def create_card(
    db: Session,
    *,
    principal: Principal,
    nickname: str,
    issuer: str = "Custom",
    network: str = "",
    card_type: str = "VIRTUAL",
    scope: str = "BUSINESS",
    background_style: str = "emerald-obsidian",
    accent_color: str = "#10b981",
    visual_effect: str = "glass",
    provider_key: str | None = None,
    provider_token_ref: str | None = None,
    is_preferred: bool = False,
) -> dict[str, Any]:
    _reject_sensitive_input(nickname, issuer, provider_token_ref)
    _validate_provider_token_ref(provider_key, provider_token_ref)
    clean_net = network.strip().upper()
    if clean_net not in VALID_NETWORKS:
        raise ValidationError(f"Unsupported network '{clean_net}'.")
    clean_type = card_type.strip().upper()
    if clean_type not in VALID_CARD_TYPES:
        raise ValidationError(f"Unsupported card_type '{clean_type}'.")
    clean_scope = scope.strip().upper()
    if clean_scope not in VALID_SCOPES:
        raise ValidationError("scope must be BUSINESS or PERSONAL.")
    clean_effect = visual_effect.strip().lower()
    if clean_effect not in VALID_EFFECTS:
        clean_effect = "glass"

    conn_status, _note = _resolve_connection_status(
        db,
        tenant_id=principal.tenant_id,
        provider_key=provider_key,
        provider_token_ref=provider_token_ref,
    )

    if is_preferred:
        siblings = db.execute(
            select(FinanceCardRecord).where(
                FinanceCardRecord.tenant_id == principal.tenant_id,
                FinanceCardRecord.status == "ACTIVE",
            )
        ).scalars().all()
        for s in siblings:
            s.is_preferred = False

    rec = FinanceCardRecord(
        card_id=f"crd_{uuid.uuid4().hex[:14]}",
        tenant_id=principal.tenant_id,
        nickname=nickname.strip()[:120],
        issuer=(issuer or "Custom").strip()[:120],
        network=clean_net,
        card_type=clean_type,
        scope=clean_scope,
        background_style=(background_style or "emerald-obsidian").strip()[:64],
        accent_color=(accent_color or "#10b981").strip()[:24],
        visual_effect=clean_effect,
        connection_status=conn_status,
        provider_key=(provider_key or "").strip().lower() or None,
        provider_token_ref=(provider_token_ref or "").strip() or None,
        is_preferred=is_preferred,
        created_by=principal.username,
    )
    db.add(rec)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FINANCE_CARD_CREATED",
        resource=rec.card_id,
        outcome=f"{rec.nickname}|{rec.connection_status}",
    )
    db.commit()
    db.refresh(rec)
    return serialize_card(db, rec)


def list_cards(db: Session, *, tenant_id: str, scope: str | None = None) -> list[dict[str, Any]]:
    stmt = select(FinanceCardRecord).where(
        FinanceCardRecord.tenant_id == tenant_id,
        FinanceCardRecord.status == "ACTIVE",
    )
    if scope:
        stmt = stmt.where(FinanceCardRecord.scope == scope.strip().upper())
    rows = db.execute(
        stmt.order_by(
            FinanceCardRecord.is_preferred.desc(),
            FinanceCardRecord.display_order.asc(),
            FinanceCardRecord.created_at.desc(),
        )
    ).scalars().all()
    return [serialize_card(db, r) for r in rows]


def _get_card(db: Session, *, tenant_id: str, card_id: str) -> FinanceCardRecord:
    rec = db.execute(
        select(FinanceCardRecord).where(
            FinanceCardRecord.card_id == card_id,
            FinanceCardRecord.tenant_id == tenant_id,
            FinanceCardRecord.status == "ACTIVE",
        )
    ).scalar_one_or_none()
    if rec is None:
        raise NotFoundError(f"Card '{card_id}' not found.")
    return rec


def update_card(
    db: Session,
    *,
    principal: Principal,
    card_id: str,
    updates: dict[str, Any],
) -> dict[str, Any]:
    rec = _get_card(db, tenant_id=principal.tenant_id, card_id=card_id)
    _reject_sensitive_input(updates.get("nickname"), updates.get("issuer"), updates.get("provider_token_ref"))

    if updates.get("nickname"):
        rec.nickname = str(updates["nickname"]).strip()[:120]
    if updates.get("issuer") is not None:
        rec.issuer = str(updates["issuer"]).strip()[:120] or "Custom"
    if updates.get("network") is not None:
        net = str(updates["network"]).strip().upper()
        if net not in VALID_NETWORKS:
            raise ValidationError(f"Unsupported network '{net}'.")
        rec.network = net
    if updates.get("card_type") is not None:
        ct = str(updates["card_type"]).strip().upper()
        if ct not in VALID_CARD_TYPES:
            raise ValidationError(f"Unsupported card_type '{ct}'.")
        rec.card_type = ct
    if updates.get("scope") is not None:
        sc = str(updates["scope"]).strip().upper()
        if sc not in VALID_SCOPES:
            raise ValidationError("scope must be BUSINESS or PERSONAL.")
        rec.scope = sc
    if updates.get("background_style"):
        rec.background_style = str(updates["background_style"]).strip()[:64]
    if updates.get("accent_color"):
        rec.accent_color = str(updates["accent_color"]).strip()[:24]
    if updates.get("visual_effect") in VALID_EFFECTS:
        rec.visual_effect = updates["visual_effect"]
    if updates.get("image_crop") is not None:
        rec.image_crop_json = json.dumps(updates["image_crop"])
    if updates.get("display_order") is not None:
        rec.display_order = int(updates["display_order"])
    if "provider_key" in updates or "provider_token_ref" in updates:
        if "provider_key" in updates:
            rec.provider_key = (str(updates["provider_key"] or "").strip().lower()) or None
        if "provider_token_ref" in updates:
            rec.provider_token_ref = (str(updates["provider_token_ref"] or "").strip()) or None
        rec.connection_status, _ = _resolve_connection_status(
            db,
            tenant_id=principal.tenant_id,
            provider_key=rec.provider_key,
            provider_token_ref=rec.provider_token_ref,
        )
    if updates.get("is_preferred") is True:
        siblings = db.execute(
            select(FinanceCardRecord).where(
                FinanceCardRecord.tenant_id == principal.tenant_id,
                FinanceCardRecord.status == "ACTIVE",
            )
        ).scalars().all()
        for s in siblings:
            s.is_preferred = s.card_id == rec.card_id

    rec.updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FINANCE_CARD_UPDATED",
        resource=rec.card_id,
        outcome=rec.nickname,
    )
    db.commit()
    db.refresh(rec)
    return serialize_card(db, rec)


def delete_card(db: Session, *, principal: Principal, card_id: str) -> dict[str, Any]:
    rec = _get_card(db, tenant_id=principal.tenant_id, card_id=card_id)
    rec.status = "REMOVED"
    rec.is_preferred = False
    rec.provider_token_ref = None
    rec.updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FINANCE_CARD_REMOVED",
        resource=rec.card_id,
        outcome=rec.nickname,
    )
    db.commit()
    return {"card_id": rec.card_id, "status": "REMOVED"}


def sanitize_card_image_bytes(
    raw_bytes: bytes,
    *,
    redaction_mode: str = "standard",
) -> tuple[bytes, str]:
    """Sanitize card photo in memory: EXIF transpose, strip metadata, normalize 960x600, extract accent, and redact credential zone."""
    try:
        opened = Image.open(io.BytesIO(raw_bytes))
        img = ImageOps.exif_transpose(opened).convert("RGB")
    except Exception as exc:
        raise ValidationError(f"Unsupported or corrupt image file: {exc}") from exc

    target_w, target_h = 960, 600
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / max(src_h, 1)
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))
    img = img.resize((target_w, target_h), Image.Resampling.LANCZOS)

    sample = img.crop((0, 0, target_w, 80)).resize((1, 1)).getpixel((0, 0))
    accent_hex = f"#{sample[0]:02x}{sample[1]:02x}{sample[2]:02x}"

    mode = (redaction_mode or "standard").strip().lower()
    if mode == "full":
        cred_box = (int(target_w * 0.04), int(target_h * 0.14), int(target_w * 0.96), int(target_h * 0.92))
        blur_radius = 34
    else:
        cred_box = (int(target_w * 0.05), int(target_h * 0.30), int(target_w * 0.95), int(target_h * 0.92))
        blur_radius = 28

    blurred_zone = img.crop(cred_box).filter(ImageFilter.GaussianBlur(radius=blur_radius))
    img.paste(blurred_zone, cred_box)

    overlay = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(cred_box, radius=24, fill=(10, 14, 22, 138))
    sanitized = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    out_buf = io.BytesIO()
    sanitized.save(out_buf, format="PNG", optimize=True)
    return out_buf.getvalue(), accent_hex


def preview_sanitized_card_image(
    db: Session,
    *,
    principal: Principal,
    card_id: str,
    raw_bytes: bytes,
    redaction_mode: str = "standard",
) -> dict[str, Any]:
    """Return an unsaved sanitized image preview so the user can verify all credentials are obscured before saving."""
    _get_card(db, tenant_id=principal.tenant_id, card_id=card_id)
    png_bytes, accent_hex = sanitize_card_image_bytes(raw_bytes, redaction_mode=redaction_mode)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return {
        "card_id": card_id,
        "redaction_mode": "full" if (redaction_mode or "").strip().lower() == "full" else "standard",
        "accent_color": accent_hex,
        "preview_data_url": f"data:image/png;base64,{b64}",
        "saved": False,
    }


def process_and_attach_card_image(
    db: Session,
    *,
    principal: Principal,
    settings: Settings,
    card_id: str,
    raw_bytes: bytes,
    redaction_mode: str = "standard",
) -> dict[str, Any]:
    """Sanitize uploaded card photo in memory and store ONLY the redacted PNG in tenant-isolated File Hub."""
    rec = _get_card(db, tenant_id=principal.tenant_id, card_id=card_id)
    png_bytes, accent_hex = sanitize_card_image_bytes(raw_bytes, redaction_mode=redaction_mode)

    stored = generate_and_store_file(
        db,
        principal=principal,
        settings=settings,
        filename=f"card_{rec.card_id}.png",
        content_bytes=png_bytes,
        mime_type="image/png",
        folder="cards",
    )

    rec.image_file_id = stored["file_id"]
    rec.background_style = "custom-image"
    rec.accent_color = accent_hex
    rec.updated_at = datetime.now(timezone.utc)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FINANCE_CARD_IMAGE_PROCESSED",
        resource=rec.card_id,
        outcome=f"file={stored['file_id']}|redaction_mode={redaction_mode}",
    )
    db.commit()
    db.refresh(rec)
    return serialize_card(db, rec)


def verify_card_provider_authorization(
    db: Session,
    *,
    principal: Principal,
    card_id: str,
    settings: Settings,
    http_client: Any = None,
) -> dict[str, Any]:
    """Verify card-level provider authorization against live provider API before setting PROVIDER_LINKED."""
    import httpx

    from app.core.exceptions import ConflictError
    from app.services.integration_manager import resolve_provider_token

    rec = _get_card(db, tenant_id=principal.tenant_id, card_id=card_id)
    prov = (rec.provider_key or "").strip().lower()
    tok_ref = (rec.provider_token_ref or "").strip()
    if prov not in SUPPORTED_CARD_LINK_PROVIDERS or not tok_ref:
        raise ValidationError("Card must have a supported provider_key and provider_token_ref to verify.")

    api_secret = resolve_provider_token(db, tenant_id=principal.tenant_id, provider=prov, settings=settings)
    if not api_secret:
        raise ConflictError(
            f"No live {prov} API credentials configured for this tenant. Card remains at AWAITING_PROVIDER_AUTH."
        )

    url_map = {
        "stripe": f"https://api.stripe.com/v1/payment_methods/{tok_ref}",
        "paystack": "https://api.paystack.co/bank",
        "flutterwave": f"https://api.flutterwave.com/v3/tokens/{tok_ref}",
    }
    client = http_client or httpx.Client(timeout=8.0)
    should_close = http_client is None
    try:
        resp = client.get(url_map[prov], headers={"Authorization": f"Bearer {api_secret}"})
    except Exception as exc:
        raise ConflictError(f"Provider verification request failed: {exc}") from exc
    finally:
        if should_close:
            client.close()

    if resp.status_code != 200:
        raise ConflictError(
            f"Provider {prov} rejected card authorization check (HTTP {resp.status_code}). Card remains AWAITING_PROVIDER_AUTH."
        )

    now = datetime.now(timezone.utc)
    rec.last_synced_at = now
    rec.connection_status = "PROVIDER_LINKED"
    rec.updated_at = now
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="FINANCE_CARD_PROVIDER_VERIFIED",
        resource=rec.card_id,
        outcome=f"provider={prov}|status=PROVIDER_LINKED",
    )
    db.commit()
    db.refresh(rec)
    return serialize_card(db, rec)


def serialize_card(db: Session, r: FinanceCardRecord) -> dict[str, Any]:
    """Never expose raw card credentials or full provider tokens."""
    _, support_note = _resolve_connection_status(
        db,
        tenant_id=r.tenant_id,
        provider_key=r.provider_key,
        provider_token_ref=r.provider_token_ref,
        last_synced_at=r.last_synced_at,
    )
    return {
        "card_id": r.card_id,
        "nickname": r.nickname,
        "issuer": r.issuer,
        "network": r.network,
        "card_type": r.card_type,
        "scope": r.scope,
        "background_style": r.background_style,
        "accent_color": r.accent_color,
        "visual_effect": r.visual_effect,
        "image_file_id": r.image_file_id,
        "image_preview_url": f"/api/v1/files/{r.image_file_id}/preview" if r.image_file_id else None,
        "image_crop": json.loads(r.image_crop_json or '{"zoom":1,"offsetX":0,"offsetY":0}'),
        "connection_status": r.connection_status,
        "provider_key": r.provider_key,
        "has_provider_token": bool(r.provider_token_ref),
        "provider_support_note": support_note,
        "display_order": r.display_order,
        "is_preferred": r.is_preferred,
        "last_synced_at": r.last_synced_at.isoformat() if r.last_synced_at else None,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }
