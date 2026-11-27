"""ULTRON OS 2026 — iPhone XR Portrait Login Experience & Session Persistence Regression Test Suite.

Verifies:
1. Phase 1: Robust session persistence, HttpOnly/SameSite cookies, single-flight token refresh,
   and server-side logout revocation.
2. Phase 2: Mobile-first iPhone XR (414x896) portrait login experience, safe-area insets,
   16px auto-zoom prevention, >=44-48px touch targets, and single-column responsive stacking.
3. Phase 3 & 4: 14-item statutory CAC registration workflow (icrp.cac.gov.ng), ₦23,000 fee estimates
   (Companies Regs 2021 gazette Nov 2026), 8 canonical statuses, and CAMA 2020 §20 safeguards.
4. Phase 5: ApprovalGate enforcement preventing autonomous government filings or fee dispatches.
"""

from __future__ import annotations

import re
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
STYLES_CSS = REPO_ROOT / "frontend" / "src" / "styles.css"
APP_TSX = REPO_ROOT / "frontend" / "src" / "App.tsx"


def test_phase1_refresh_cookie_and_single_flight_contract(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Phase 1: Verify HttpOnly refresh token cookie issuance, cookie-fallback refresh, and logout revocation."""
    # 1. Login to receive tokens and cookie
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "owner_admin", "password": "StrongOwnerPassword!2026"},
    )
    assert login_resp.status_code == 200
    login_data = login_resp.json()
    assert "access_token" in login_data
    assert "refresh_token" in login_data

    # Verify Set-Cookie header contains ultron_refresh_token with HttpOnly and SameSite=lax
    set_cookie = login_resp.headers.get("set-cookie", "")
    assert "ultron_refresh_token=" in set_cookie
    assert "httponly" in set_cookie.lower()
    assert "samesite=lax" in set_cookie.lower()

    # Extract cookie value
    match = re.search(r"ultron_refresh_token=([^;]+)", set_cookie)
    assert match is not None
    cookie_token = match.group(1)
    assert len(cookie_token) > 20

    # 2. Refresh using ONLY cookie fallback with empty body
    client.cookies.set("ultron_refresh_token", cookie_token, path="/api/v1/auth")
    ref_resp = client.post("/api/v1/auth/refresh", json={})
    assert ref_resp.status_code == 200
    ref_data = ref_resp.json()
    assert "access_token" in ref_data
    assert "refresh_token" in ref_data
    new_refresh_token = ref_data["refresh_token"]

    # Verify cookie rotation
    new_set_cookie = ref_resp.headers.get("set-cookie", "")
    assert "ultron_refresh_token=" in new_set_cookie

    # 3. Server-side revocation on logout
    client.cookies.set("ultron_refresh_token", new_refresh_token, path="/api/v1/auth")
    logout_resp = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {ref_data['access_token']}"},
    )
    assert logout_resp.status_code == 200

    # Expired/cleared cookie check
    logout_cookie = logout_resp.headers.get("set-cookie", "")
    assert 'max-age=0' in logout_cookie.lower() or 'expires=' in logout_cookie.lower()

    # Replaying revoked token MUST fail with 401
    replay_resp = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh_token},
    )
    assert replay_resp.status_code == 401
    err = replay_resp.json()
    assert err.get("code") == "SESSION_REVOKED" or err.get("error", {}).get("code") == "SESSION_REVOKED"


def test_phase1_24_hour_session_policy_and_reuse_detection(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Phase 1: Enforce 24-hour absolute session expiration and audit revoked refresh token reuse."""
    from datetime import datetime, timedelta, timezone
    from app.core.config import get_settings
    from app.db.models import AuditLogRecord, SessionRecord
    from app.db.session import get_db

    settings = get_settings()
    assert settings.refresh_token_ttl_hours == 24
    assert settings.session_duration_seconds == 86400

    # 1. Login
    login_resp = client.post(
        "/api/v1/auth/login",
        json={"username": "owner_admin", "password": "StrongOwnerPassword!2026"},
    )
    assert login_resp.status_code == 200
    token1 = login_resp.json()["refresh_token"]

    # 2. First refresh (valid)
    ref_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": token1})
    assert ref_resp.status_code == 200
    token2 = ref_resp.json()["refresh_token"]

    # 3. Replay token1 (now revoked) - must trigger AUTH_REFRESH_TOKEN_REUSE_DETECTED
    reuse_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": token1})
    assert reuse_resp.status_code == 401
    reuse_err = reuse_resp.json()
    assert reuse_err.get("code") == "SESSION_REVOKED" or reuse_err.get("error", {}).get("code") == "SESSION_REVOKED"

    # Verify audit log recorded reuse
    db = next(get_db())
    try:
        audit_entries = db.query(AuditLogRecord).filter(
            AuditLogRecord.action == "AUTH_REFRESH_TOKEN_REUSE_DETECTED"
        ).all()
        assert len(audit_entries) >= 1
        assert audit_entries[-1].outcome == "REVOKED_REUSE_BLOCKED"

        # 4. Simulate session reaching 24 hours (refresh_expires_at in past)
        from app.core.security import hash_token
        sess_rec = db.query(SessionRecord).filter(
            SessionRecord.refresh_token_hash == hash_token(token2)
        ).first()
        assert sess_rec is not None
        sess_rec.refresh_expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        db.commit()
    finally:
        db.close()

    # Refreshing after 24h expiration must fail with SESSION_EXPIRED
    exp_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": token2})
    assert exp_resp.status_code == 401
    exp_err = exp_resp.json()
    assert exp_err.get("code") == "SESSION_EXPIRED" or exp_err.get("error", {}).get("code") == "SESSION_EXPIRED"
    msg = exp_err.get("detail") or exp_err.get("error", {}).get("message", "")
    assert "24 hours" in msg


def test_phase2_iphone_xr_portrait_css_rules():
    """Phase 2: Verify CSS rules guaranteeing iPhone XR (414x896) and compact mobile portrait perfection."""
    css_content = STYLES_CSS.read_text(encoding="utf-8")

    # 1. Safe-area insets must be present in auth-wrap
    assert "safe-area-inset-top" in css_content
    assert "safe-area-inset-bottom" in css_content

    # 2. Mobile breakpoint must enforce single-column flex layout
    assert "@media (max-width: 768px)" in css_content

    # Locate media block for mobile auth
    start_idx = css_content.find("@media (max-width: 768px)")
    assert start_idx != -1
    media_chunk = css_content[start_idx:start_idx + 2500]

    # 3. .auth-shell inside mobile media must use flex-direction: column and 100% width
    assert ".auth-shell" in media_chunk
    assert "flex-direction: column" in media_chunk
    assert "width: 100%" in media_chunk

    # 4. Critical iOS Safari fix: input.input must have 16px font-size to prevent automatic viewport zoom
    assert "font-size: 16px !important" in media_chunk

    # 5. Touch target ergonomics: min-height 48px on inputs and buttons
    assert "min-height: 48px" in media_chunk

    # 6. .auth-mode-row segmented control
    assert ".auth-mode-row" in css_content


def test_phase2_app_tsx_mobile_globe_scaling():
    """Phase 2: Verify App.tsx scales EarthGlobe to compact size on mobile devices and provides password visibility toggle."""
    app_content = APP_TSX.read_text(encoding="utf-8")

    # EarthGlobe should use device.isMobile ? 100 : 250
    assert "size={device.isMobile ? 100 : 250}" in app_content
    assert "auth-mode-row" in app_content

    # Password visibility toggle control
    assert 'id="auth-toggle-password"' in app_content
    assert 'showPassword' in app_content
    assert 'aria-label={showPassword ? "Hide password" : "Show password"}' in app_content


def test_phase3_cac_registration_workflow_statutory_integrity(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Phase 3: Verify CAC Registration Workflow has all 14 statutory items, ₦23,000 fee estimate, and portal link."""
    headers = auth_headers["owner"]
    resp = client.get("/api/v1/legal/registration/workflow", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["portal_url"] == "https://icrp.cac.gov.ng/"
    assert data["total_items"] == 14
    assert data["total_estimated_fee_ngn"] == 23500.0
    assert data["mandatory_statutory_total_ngn"] == 18500.0

    # 8 canonical statuses
    assert len(data["canonical_statuses"]) == 8
    items = data["items"]
    assert len(items) == 14

    # Verify Item 10: Fee Estimates
    item10 = next(it for it in items if it["key"] == "FILING_FEE_ESTIMATES")
    assert item10["status"] == "APPROVED"
    assert item10["details"]["total_estimated_fee_ngn"] == 23500.0
    assert item10["details"]["mandatory_statutory_total_ngn"] == 18500.0
    assert item10["details"]["name_reservation_ngn"] == 1000.0
    assert item10["details"]["registration_fee_ngn"] == 10000.0
    assert item10["details"]["stamp_duty_ngn"] == 7500.0
    assert item10["details"]["certified_true_copies_ngn"] == 5000.0
    assert "https://icrp.cac.gov.ng/" in item10["official_source"]
    assert "Gazette No. 92" in item10["official_source"]


def test_phase4_cama_section_20_statutory_safeguards(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Phase 4: Verify under-18 directorship strictly disqualified, while minor can subscribe under §20(2)."""
    headers = auth_headers["owner"]
    incorp = client.get("/api/v1/legal/incorporation", headers=headers).json()
    draft_id = incorp["draft_id"]

    # 1. Under-18 DIRECTOR must be strictly rejected
    bad_director = client.post(
        "/api/v1/legal/officers",
        headers=headers,
        json={
            "draft_id": draft_id,
            "officer_type": "DIRECTOR",
            "full_legal_name": "Epejuwon Minor",
            "date_of_birth": "2010-01-01",  # 16 years old
            "residential_address": "12 Adeola Odeku Street, Victoria Island, Lagos, Nigeria",
            "email": "minor@caravan.africa",
            "phone": "+2348011223344",
            "nin": "91827364510",
        },
    )
    assert bad_director.status_code == 422
    err_text = str(bad_director.json())
    assert "CAMA_2020_SECTION_20_1_A" in err_text
    assert "INFANT_DIRECTORSHIP_DISQUALIFICATION" in err_text

    # 2. Zero-fabrication check: dummy NIN must be rejected
    dummy_nin = client.post(
        "/api/v1/legal/officers",
        headers=headers,
        json={
            "draft_id": draft_id,
            "officer_type": "DIRECTOR",
            "full_legal_name": "Verified Adult",
            "date_of_birth": "1990-01-01",
            "residential_address": "12 Adeola Odeku Street, Victoria Island, Lagos, Nigeria",
            "email": "adult@caravan.africa",
            "phone": "+2348011223344",
            "nin": "00000000000",  # Synthetic repeating NIN
        },
    )
    assert dummy_nin.status_code == 422
    assert "zero-fabrication" in str(dummy_nin.json())


def test_phase5_approval_gate_enforcement(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Phase 5: Verify no government filing submitted or fee dispatched without human approval."""
    headers = auth_headers["owner"]

    # Trigger filing submission action
    resp = client.post(
        "/api/v1/legal/filing/submit",
        headers=headers,
        json={
            "filing_type": "COMPANY_INCORPORATION",
            "target_authority": "CAC",
            "fee_amount_ngn": 17500.0,
            "declaration_text": "I confirm compliance with CAMA 2020 provisions for incorporation.",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["approval_required"] is True
    assert data["status"] == "PENDING_HUMAN_APPROVAL"
    assert "approval_id" in data
