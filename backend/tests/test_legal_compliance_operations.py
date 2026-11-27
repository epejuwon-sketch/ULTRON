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
    """Capability 4: Register adult guardian, then minor shareholder and adult directors with CAMA 2020 §20(1)(a) enforcement."""
    headers = auth_headers["owner"]
    incorp = client.get("/api/v1/legal/incorporation", headers=headers).json()
    draft_id = incorp["draft_id"]

    # 1. Attempt minor DIRECTOR registration -> MUST FAIL (422) under CAMA 2020 §20(1)(a)
    bad_minor_director = client.post(
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
            "guardian_officer_id": None,
        },
    )
    assert bad_minor_director.status_code == 422
    err_body = bad_minor_director.json()
    assert "CAMA_2020_SECTION_20_1_A" in str(err_body)
    assert "INFANT_DIRECTORSHIP_DISQUALIFICATION" in str(err_body)

    # 2. Attempt minor SHAREHOLDER registration WITHOUT adult guardian -> MUST FAIL (422)
    bad_minor_shareholder = client.post(
        "/api/v1/legal/officers",
        headers=headers,
        json={
            "draft_id": draft_id,
            "officer_type": "SHAREHOLDER",
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
    assert bad_minor_shareholder.status_code == 422
    assert "INFANT_EQUITY_TRUST_CAPACITY" in str(bad_minor_shareholder.json())

    # 3. Register Adult Legal Guardian first
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

    # 4. Register minor founder as SHAREHOLDER / BENEFICIAL_OWNER WITH verified guardian -> MUST SUCCEED (201)
    minor_resp = client.post(
        "/api/v1/legal/officers",
        headers=headers,
        json={
            "draft_id": draft_id,
            "officer_type": "SHAREHOLDER",
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

    # 5. Register Adult Director to satisfy CAMA §271 governance
    adult_director = client.post(
        "/api/v1/legal/officers",
        headers=headers,
        json={
            "draft_id": draft_id,
            "officer_type": "DIRECTOR",
            "full_legal_name": "Babatunde Epejuwon",
            "date_of_birth": "1980-11-15",  # Adult (45 years old)
            "residential_address": "12 Adeola Odeku Street, Victoria Island, Lagos, Nigeria",
            "email": "director@caravan.africa",
            "phone": "+2348099887766",
            "nin": "71829304152",
            "shares_allocated": 200000,
            "equity_percentage": 20.0,
        },
    )
    assert adult_director.status_code == 201
    assert adult_director.json()["is_under_18"] is False


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
    """Verify unified 8-widget dashboard display contract and embedded registration workflow."""
    headers = auth_headers["owner"]
    resp = client.get("/api/v1/legal/dashboard", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    # Verify embedded company registration workflow
    assert "company_registration_workflow" in data
    assert len(data["company_registration_workflow"]["items"]) == 14
    assert data["company_registration_workflow"]["total_estimated_fee_ngn"] == 23000.0

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


def test_api_company_registration_workflow_14_items(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Verify 14-item statutory CAC company registration workflow with 8 canonical statuses."""
    headers = auth_headers["owner"]
    resp = client.get("/api/v1/legal/registration/workflow", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert data["portal_url"] == "https://icrp.cac.gov.ng/"
    assert data["total_items"] == 14
    assert data["total_estimated_fee_ngn"] == 23000.0
    assert "CAC Official Portal (https://icrp.cac.gov.ng/)" in data["fee_schedule_source"]

    canonical_statuses = set(data["canonical_statuses"])
    expected_statuses = {
        "NOT_STARTED",
        "IN_PROGRESS",
        "AWAITING_INFORMATION",
        "AWAITING_PROFESSIONAL_REVIEW",
        "AWAITING_OWNER_APPROVAL",
        "SUBMITTED",
        "APPROVED",
        "REJECTED_QUERIED",
    }
    assert canonical_statuses == expected_statuses

    items = data["items"]
    assert len(items) == 14
    item_keys = [it["key"] for it in items]
    expected_keys = [
        "COMPANY_TYPE_STRUCTURE",
        "PROPOSED_NAME_RESEARCH",
        "REGISTERED_OFFICE_INFO",
        "BUSINESS_ACTIVITIES_OBJECTS",
        "SHARE_CAPITAL_ALLOCATION",
        "SHAREHOLDERS_SUBSCRIBERS",
        "DIRECTORS_AND_SECRETARY",
        "SUPPORTING_DOCUMENTS",
        "MEMART_PREPARATION",
        "FILING_FEE_ESTIMATES",
        "PROFESSIONAL_REVIEW",
        "APPLICATION_SUBMISSION_PREP",
        "CERTIFICATE_STATUS_REPORT",
        "POST_INCORPORATION_COMPLIANCE",
    ]
    assert item_keys == expected_keys

    # Each item must have valid canonical status
    for it in items:
        assert it["status"] in canonical_statuses, f"Item {it['key']} has non-canonical status: {it['status']}"
        assert it["statutory_ref"] != ""


def test_cama_section_20_2_minor_subscriber_with_two_adults(
    client: TestClient,
    auth_headers: dict[str, dict[str, str]],
):
    """Verify CAMA 2020 §20(2): Minor can subscribe without guardian_officer_id if 2 adult subscribers exist."""
    headers = auth_headers["owner"]
    incorp = client.get("/api/v1/legal/incorporation", headers=headers).json()
    draft_id = incorp["draft_id"]

    # Register first adult subscriber
    resp_adult1 = client.post(
        "/api/v1/legal/officers",
        headers=headers,
        json={
            "draft_id": draft_id,
            "officer_type": "SHAREHOLDER",
            "full_legal_name": "Babatunde Adeleke",
            "date_of_birth": "1985-05-14",
            "residential_address": "45 Marina Street, Lagos Island, Lagos, Nigeria",
            "email": "adeleke@caravan.africa",
            "phone": "+2348034445566",
            "nin": "71625348901",
            "shares_allocated": 150000,
            "equity_percentage": 15.0,
        },
    )
    assert resp_adult1.status_code == 201

    # Register second adult subscriber
    resp_adult2 = client.post(
        "/api/v1/legal/officers",
        headers=headers,
        json={
            "draft_id": draft_id,
            "officer_type": "SHAREHOLDER",
            "full_legal_name": "Chidinma Okonkwo",
            "date_of_birth": "1990-11-20",
            "residential_address": "88 Awolowo Road, Ikoyi, Lagos, Nigeria",
            "email": "okonkwo@caravan.africa",
            "phone": "+2348056667788",
            "nin": "62534891702",
            "shares_allocated": 150000,
            "equity_percentage": 15.0,
        },
    )
    assert resp_adult2.status_code == 201

    # Now register a minor subscriber without guardian_officer_id -> MUST SUCCEED under CAMA 2020 §20(2)
    resp_minor = client.post(
        "/api/v1/legal/officers",
        headers=headers,
        json={
            "draft_id": draft_id,
            "officer_type": "SHAREHOLDER",
            "full_legal_name": "Temitope Epejuwon",
            "date_of_birth": "2010-09-05",  # 16 years old
            "residential_address": "12 Adeola Odeku Street, Victoria Island, Lagos, Nigeria",
            "email": "temi@caravan.africa",
            "phone": "+2348091112233",
            "nin": "53489172603",
            "shares_allocated": 50000,
            "equity_percentage": 5.0,
            "guardian_officer_id": None,
        },
    )
    assert resp_minor.status_code == 201
    minor_data = resp_minor.json()
    assert minor_data["is_under_18"] is True
    assert minor_data["guardian_officer_id"] is None

