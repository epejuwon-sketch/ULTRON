"""ULTRON OS 2026 — Legal & Compliance Operations Test Suite.

Verifies the 10 core department capabilities, strict autonomy boundaries,
Under-18 Infant Relief Act & CAMA 2020 legal capacity safeguards, zero-fabrication rules,
professional review determinations, ARGON ApprovalGate governance, and 8 dashboard widgets.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.exceptions import ValidationError
from app.db.models import LegalOfficerRecord
from app.services.legal_compliance_service import (
    _calculate_age,
    _mask_nin,
    _validate_not_synthetic_identity,
    evaluate_professional_review,
    get_statutory_research_knowledge,
)


def test_statutory_research_knowledge_base():
    """Capability 1: Verify verified Nigerian statutory citations from official sources."""
    kb = get_statutory_research_knowledge()
    assert kb["operating_jurisdiction"] == "Federal Republic of Nigeria"
    laws = kb["governing_laws"]

    assert "CAC_CAMA_2020" in laws
    cama = laws["CAC_CAMA_2020"]
    assert "Companies and Allied Matters Act 2020" in cama["title"]
    cama_sections = [s["section"] for s in cama["key_sections"]]
    assert any("§20(1)(a)" in s for s in cama_sections)
    assert any("§119" in s for s in cama_sections)
    assert any("§375" in s for s in cama_sections)

    assert "NDPC_NDPA_2023" in laws
    ndpa = laws["NDPC_NDPA_2023"]
    assert "Nigeria Data Protection Act 2023" in ndpa["title"]
    ndpa_sections = [s["section"] for s in ndpa["key_sections"]]
    assert any("§24" in s for s in ndpa_sections)
    assert any("§29" in s for s in ndpa_sections)
    assert any("§44" in s for s in ndpa_sections)

    assert "FIRS_TAX_REGIME" in laws
    assert "LEGAL_CAPACITY_SAFEGUARDS" in laws


def test_zero_fabrication_identity_guards():
    """Verify zero-fabrication rejects synthetic NINs and placeholder names."""
    # Synthetic / invalid length
    with pytest.raises(ValidationError) as exc:
        _validate_not_synthetic_identity("123", "Valid Name")
    assert "11 numeric digits" in str(exc.value)

    # Simulated repeating / dummy NINs
    with pytest.raises(ValidationError) as exc:
        _validate_not_synthetic_identity("00000000000", "Valid Name")
    assert "zero-fabrication" in str(exc.value)

    # Placeholder / dummy names
    with pytest.raises(ValidationError) as exc:
        _validate_not_synthetic_identity("98765432101", "John Doe Placeholder")
    assert "placeholder" in str(exc.value).lower()

    # Masking NIN
    masked = _mask_nin("98765432101")
    assert masked == "*******2101"
    assert len(masked) == 11


def test_under_18_age_calculation_and_capacity():
    """Verify Under-18 age calculation logic."""
    # Person born in 2010 is under 18 in 2026 (16 years old)
    age = _calculate_age("2010-04-15")
    assert age < 18
    assert age == 16

    # Adult born in 1995 is 31 in 2026
    adult_age = _calculate_age("1995-01-01")
    assert adult_age >= 18
    assert adult_age == 31


def test_professional_review_determinations():
    """Capability 6: Verify professional review matrix flags accredited agents where required."""
    res_direct = evaluate_professional_review("NAME_RESERVATION")
    assert res_direct["requires_professional"] is False
    assert res_direct["professional_category"] == "NONE"

    res_incorp = evaluate_professional_review("COMPANY_INCORPORATION")
    assert res_incorp["requires_professional"] is True
    assert res_incorp["professional_category"] == "CAC_ACCREDITED_AGENT"

    res_psc = evaluate_professional_review("PSC_REGISTER_FILING")
    assert res_psc["requires_professional"] is True
    assert res_psc["professional_category"] == "LEGAL_PRACTITIONER"

    res_ndpc = evaluate_professional_review("NDPC_DPMI_REGISTRATION")
    assert res_ndpc["requires_professional"] is True
    assert res_ndpc["professional_category"] == "DPCO_COMPLIANCE_ORGANIZATION"


def test_api_incorporation_draft_lifecycle(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Capability 2 & 3: Draft company incorporation documents and name reservations."""
    headers = auth_headers["owner"]

    resp = client.get("/api/v1/legal/incorporation", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_name"] == "CARAVAN FUNDING INTELLIGENCE LTD"
    assert data["nominal_share_capital_ngn"] == 1000000.0

    # Update draft
    update_resp = client.post(
        "/api/v1/legal/incorporation",
        headers=headers,
        json={
            "company_name": "CARAVAN FUNDING INTELLIGENCE LTD",
            "alternative_names": ["CARAVAN VENTURES AFRICA LTD", "AURELIA FUNDING INTELLIGENCE LTD"],
            "nominal_share_capital": 2000000.0,
            "registered_office_address": "Plot 1084 Adeola Odeku Street, Victoria Island, Lagos, Nigeria",
            "objects_clause": [
                "Software development and business intelligence platform operations.",
                "Non-dilutive capital matching and venture funding technology.",
            ],
        },
    )
    assert update_resp.status_code == 200
    updated = update_resp.json()
    assert updated["nominal_share_capital_ngn"] == 2000000.0
    assert "Adeola Odeku" in updated["registered_office_address"]


def test_api_officer_registration_and_under_18_safeguard(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Capability 4: Register adult guardian, then minor founder with strict legal capacity enforcement."""
    headers = auth_headers["owner"]
    incorp = client.get("/api/v1/legal/incorporation", headers=headers).json()
    draft_id = incorp["draft_id"]

    # 1. Attempt minor director registration WITHOUT adult guardian -> MUST FAIL (422)
    bad_minor = client.post(
        "/api/v1/legal/officers",
        headers=headers,
        json={
            "draft_id": draft_id,
            "officer_type": "DIRECTOR",
            "full_legal_name": "Epejuwon Junior",
            "date_of_birth": "2010-06-12",  # 16 years old
            "residential_address": "12 Adeola Odeku Street, Victoria Island, Lagos, Nigeria",
            "email": "junior@caravan.africa",
            "phone": "+2348021112233",
            "nin": "91827364501",
            "shares_allocated": 700000,
            "equity_percentage": 70.0,
            "guardian_officer_id": None,  # Missing guardian!
        },
    )
    assert bad_minor.status_code == 422
    err_body = bad_minor.json()
    assert "INFANT_CONTRACTUAL_INCAPACITY" in str(err_body)

    # 2. Register Adult Legal Guardian first
    guardian_resp = client.post(
        "/api/v1/legal/officers",
        headers=headers,
        json={
            "draft_id": draft_id,
            "officer_type": "LEGAL_GUARDIAN",
            "full_legal_name": "Folashade Epejuwon",
            "date_of_birth": "1978-03-22",  # Adult (48 years old)
            "residential_address": "12 Adeola Odeku Street, Victoria Island, Lagos, Nigeria",
            "email": "guardian@caravan.africa",
            "phone": "+2348033334455",
            "nin": "82716253409",
            "shares_allocated": 100000,
            "equity_percentage": 10.0,
        },
    )
    assert guardian_resp.status_code == 201
    guardian_id = guardian_resp.json()["officer_id"]
    assert guardian_resp.json()["is_under_18"] is False

    # 3. Now register minor founder WITH verified guardian -> MUST SUCCEED (201)
    minor_resp = client.post(
        "/api/v1/legal/officers",
        headers=headers,
        json={
            "draft_id": draft_id,
            "officer_type": "DIRECTOR",
            "full_legal_name": "Epejuwon Junior",
            "date_of_birth": "2010-06-12",  # 16 years old
            "residential_address": "12 Adeola Odeku Street, Victoria Island, Lagos, Nigeria",
            "email": "junior@caravan.africa",
            "phone": "+2348021112233",
            "nin": "91827364501",
            "shares_allocated": 700000,
            "equity_percentage": 70.0,
            "guardian_officer_id": guardian_id,
        },
    )
    assert minor_resp.status_code == 201
    minor_data = minor_resp.json()
    assert minor_data["is_under_18"] is True
    assert minor_data["guardian_officer_id"] == guardian_id
    assert minor_data["has_significant_control"] is True  # 70% equity >= 5% PSC threshold


def test_api_statutory_policies_generation(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Capability 5: Generate Privacy Policy, Terms, 6-Year Retention Policy, and DPIA."""
    headers = auth_headers["owner"]
    resp = client.post("/api/v1/legal/policies/generate", headers=headers)
    assert resp.status_code == 200
    policies = resp.json()
    assert len(policies) >= 4

    types = {p["policy_type"] for p in policies}
    assert "PRIVACY_POLICY" in types
    assert "TERMS_OF_SERVICE" in types
    assert "DATA_RETENTION_POLICY" in types
    assert "DPIA_ASSESSMENT" in types

    # Query policies
    list_resp = client.get("/api/v1/legal/policies", headers=headers)
    assert list_resp.status_code == 200
    assert len(list_resp.json()) >= 4


def test_api_ndpc_materials_dossier(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Capability 7: Prepare NDPC DPMI registration dossier."""
    headers = auth_headers["owner"]
    resp = client.get("/api/v1/legal/ndpc/materials", headers=headers)
    assert resp.status_code == 200
    dossier = resp.json()
    assert dossier["dpmi_classification"]["is_data_controller_of_major_importance"] is True
    assert "dpo@caravan.africa" in dossier["designated_dpo"]["email"]
    assert len(dossier["technical_and_organizational_measures"]) >= 3


def test_api_regulatory_calendar_and_deadlines(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Capability 8: Retrieve compliance calendar events with statutory deadlines."""
    headers = auth_headers["owner"]
    resp = client.get("/api/v1/legal/calendar", headers=headers)
    assert resp.status_code == 200
    events = resp.json()
    assert len(events) >= 4

    authorities = {e["authority"] for e in events}
    assert "CAC" in authorities
    assert "FIRS" in authorities
    assert "NDPC" in authorities


def test_api_approval_gated_filing_and_human_decision(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Capability 9 & Autonomy Boundaries:
    Filing submission triggers ApprovalGate. Submission blocked until human approves.
    """
    headers = auth_headers["owner"]

    # 1. Trigger filing submission -> Returns PENDING_HUMAN_APPROVAL
    submit_resp = client.post(
        "/api/v1/legal/filing/submit",
        headers=headers,
        json={
            "filing_type": "COMPANY_INCORPORATION",
            "target_authority": "CAC",
            "remita_rrr": "RRR-2904-8173-9021",
            "fee_amount_ngn": 17500.0,
            "declaration_text": "Statutory declaration of compliance with CAMA 2020.",
        },
    )
    assert submit_resp.status_code == 200
    sub_data = submit_resp.json()
    assert sub_data["status"] == "PENDING_HUMAN_APPROVAL"
    assert sub_data["approval_required"] is True
    approval_id = sub_data["approval_id"]

    # 2. Viewer cannot approve (lack of permission)
    bad_perm = client.post(
        f"/api/v1/legal/approvals/{approval_id}/action",
        headers=auth_headers["viewer"],
        json={"decision": "APPROVED"},
    )
    assert bad_perm.status_code == 403

    # 3. Owner executes approval -> Transitions workflow to SUBMITTED
    approve_resp = client.post(
        f"/api/v1/legal/approvals/{approval_id}/action",
        headers=headers,
        json={"decision": "APPROVED"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["decision"] == "APPROVED"
    assert approve_resp.json()["workflow_status"] == "SUBMITTED"
    assert "CAC/FILING/2026/" in approve_resp.json()["government_reference"]


def test_api_archive_official_document(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Capability 10: Secure document vault archiving with SHA-256 integrity hash."""
    headers = auth_headers["owner"]
    resp = client.post(
        "/api/v1/legal/archive",
        headers=headers,
        json={
            "document_category": "CAC_CERTIFICATE",
            "title": "CAC Certificate of Incorporation (RC-1928491)",
            "authority_issued": "CAC",
            "file_path": "/vault/legal/cac_certificate_rc1928491.pdf",
            "file_content_base64": "JVBERi0xLjQKJUlzdWVkIGJ5IENBQyBOaWdlcmlh",
        },
    )
    assert resp.status_code == 201
    arch = resp.json()
    assert arch["document_category"] == "CAC_CERTIFICATE"
    assert len(arch["sha256_checksum"]) == 64
    assert arch["is_verified_authentic"] is True

    # Retrieve archive list
    list_resp = client.get("/api/v1/legal/archive", headers=headers)
    assert list_resp.status_code == 200
    assert any(a["document_category"] == "CAC_CERTIFICATE" for a in list_resp.json())


def test_api_legal_dashboard_all_8_widgets(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Verify unified 8-widget dashboard display contract."""
    headers = auth_headers["owner"]
    resp = client.get("/api/v1/legal/dashboard", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    widgets = data["widgets"]
    expected_widgets = [
        "registration_progress",
        "outstanding_documents",
        "professional_review_status",
        "pending_approvals",
        "government_references",
        "filing_receipts",
        "regulatory_deadlines",
        "outstanding_compliance_tasks",
    ]
    for w in expected_widgets:
        assert w in widgets, f"Missing widget: {w}"

    assert len(widgets["registration_progress"]) >= 5
    assert len(widgets["outstanding_documents"]) >= 3
    assert widgets["professional_review_status"]["accredited_agent_required"] is True
    assert "remita_retrieval_reference" in widgets["government_references"]
    assert len(widgets["filing_receipts"]) >= 3
    assert len(widgets["regulatory_deadlines"]) >= 3
    assert len(widgets["outstanding_compliance_tasks"]) >= 3
