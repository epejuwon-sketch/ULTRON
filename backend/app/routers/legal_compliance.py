"""ULTRON OS 2026 — Legal & Compliance Operations Router.

Endpoints for managing CARAVAN's statutory establishment, CAMA 2020 incorporation,
NDPA 2023 compliance, FIRS filings, officers/PSC register, and approval-gated workflows.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import Principal
from app.db.models import (
    LegalArchivedDocumentRecord,
    LegalComplianceCalendarEventRecord,
    LegalEntityDraftRecord,
    LegalFilingWorkflowRecord,
    LegalOfficerRecord,
    LegalStatutoryPolicyRecord,
)
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.legal_compliance_service import (
    archive_official_document,
    calculate_statutory_filing_fees,
    evaluate_professional_review,
    execute_approved_filing,
    generate_statutory_policies,
    get_company_registration_workflow,
    get_legal_compliance_dashboard,
    get_pre_registration_questionnaire,
    get_statutory_research_knowledge,
    populate_regulatory_compliance_calendar,
    prepare_incorporation_draft,
    prepare_ndpc_registration_materials,
    register_officer_with_safeguards,
    save_pre_registration_questionnaire,
    trigger_statutory_filing_action,
    validate_and_process_pre_registration_questionnaire,
)

router = APIRouter(prefix="/api/v1/legal", tags=["Legal & Compliance Operations"])


class IncorporationDraftRequest(BaseModel):
    company_name: str = Field(default="CARAVAN FUNDING INTELLIGENCE LTD", min_length=3, max_length=200)
    alternative_names: list[str] = Field(default_factory=lambda: ["CARAVAN VENTURES AFRICA LTD", "AURELIA FUNDING INTELLIGENCE LTD"])
    nominal_share_capital: float = Field(default=1000000.0, ge=100000.0)
    registered_office_address: str = Field(default="12 Adeola Odeku Street, Victoria Island, Lagos, Nigeria", min_length=10, max_length=300)
    objects_clause: list[str] = Field(default_factory=list)


class RegisterOfficerRequest(BaseModel):
    draft_id: str = Field(min_length=1, max_length=64)
    officer_type: str = Field(default="DIRECTOR", max_length=32)
    full_legal_name: str = Field(min_length=3, max_length=200)
    date_of_birth: str = Field(min_length=10, max_length=10)  # YYYY-MM-DD
    residential_address: str = Field(min_length=10, max_length=300)
    email: str = Field(min_length=5, max_length=120)
    phone: str = Field(min_length=7, max_length=32)
    nin: str = Field(min_length=11, max_length=11)
    shares_allocated: int = Field(default=0, ge=0)
    equity_percentage: float = Field(default=0.0, ge=0.0, le=100.0)
    guardian_officer_id: str | None = Field(default=None, max_length=64)
    professional_accreditation_number: str | None = Field(default=None, max_length=64)


class FilingSubmitRequest(BaseModel):
    workflow_id: str | None = Field(default=None, max_length=64)
    filing_type: str = Field(default="COMPANY_INCORPORATION", max_length=64)
    target_authority: str = Field(default="CAC", max_length=32)
    remita_rrr: str = Field(default="", max_length=64)
    fee_amount_ngn: float = Field(default=17500.0, ge=0.0)
    declaration_text: str = Field(
        default="I hereby confirm and declare compliance with all CAMA 2020 legal provisions for incorporation.",
        max_length=1000,
    )


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(min_length=4, max_length=16)  # APPROVED | REJECTED
    rejection_reason: str = Field(default="", max_length=500)


class DocumentArchiveRequest(BaseModel):
    document_category: str = Field(min_length=3, max_length=64)
    title: str = Field(min_length=3, max_length=200)
    authority_issued: str = Field(default="CAC", max_length=32)
    file_path: str = Field(min_length=3, max_length=300)
    file_content_base64: str = Field(default="")
    workflow_id: str | None = Field(default=None, max_length=64)


class ProfessionalReviewRequest(BaseModel):
    filing_type: str = Field(min_length=3, max_length=64)


class PreRegistrationFeeRequest(BaseModel):
    entity_type: str = Field(default="PRIVATE_COMPANY_LIMITED_BY_SHARES")
    issued_share_capital: float = Field(default=100000.0, ge=0.0)
    include_ctc: bool = Field(default=False)
    include_ai_search: bool = Field(default=False)
    include_express_delivery: bool = Field(default=False)
    include_professional_advisory: bool = Field(default=False)


class PreRegistrationQuestionnaireRequest(BaseModel):
    company_type: str = Field(default="PRIVATE_COMPANY_LIMITED_BY_SHARES")
    proposed_name: str = Field(min_length=3, max_length=200)
    alternative_names: list[str] = Field(default_factory=list)
    business_activities: str = Field(min_length=5)
    principal_objects: list[str] = Field(default_factory=list)
    issued_share_capital: float = Field(default=100000.0, ge=0.0)
    nominal_value_per_share: float = Field(default=1.0, gt=0.0)
    registered_office_address: str = Field(min_length=10, max_length=300)
    registered_office_state: str = Field(default="Lagos", max_length=64)
    registered_office_lga: str = Field(default="Eti-Osa", max_length=64)
    shareholders: list[dict[str, Any]] = Field(default_factory=list)
    include_ctc: bool = Field(default=False)
    include_ai_search: bool = Field(default=False)
    include_express_delivery: bool = Field(default=False)
    include_professional_advisory: bool = Field(default=False)


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------

@router.post("/pre-registration/calculate-fees")
def api_calculate_statutory_fees(
    body: PreRegistrationFeeRequest,
    principal: Principal = Depends(require_perm("legal:read")),
) -> dict[str, Any]:
    """Calculate itemized statutory filing fees, FIRS stamp duty, optional services, and legal advisory estimates."""
    return calculate_statutory_filing_fees(
        entity_type=body.entity_type,
        issued_share_capital=body.issued_share_capital,
        include_ctc=body.include_ctc,
        include_ai_search=body.include_ai_search,
        include_express_delivery=body.include_express_delivery,
        include_professional_advisory=body.include_professional_advisory,
    )


@router.get("/pre-registration/questionnaire")
def api_get_pre_registration_questionnaire(
    principal: Principal = Depends(require_perm("legal:read")),
    db: Session = Depends(get_db),
) -> dict[str, Any] | None:
    """Retrieve pre-registration questionnaire in DRAFT status."""
    return get_pre_registration_questionnaire(db, tenant_id=principal.tenant_id)


@router.post("/pre-registration/questionnaire", status_code=status.HTTP_200_OK)
def api_save_pre_registration_questionnaire(
    body: PreRegistrationQuestionnaireRequest,
    principal: Principal = Depends(require_perm("legal:write")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Save or update pre-registration questionnaire strictly in DRAFT status with zero-sensitive-ID checks and capacity safeguards."""
    return save_pre_registration_questionnaire(
        db,
        principal=principal,
        data=body.model_dump(),
    )


@router.get("/dashboard")
def api_get_dashboard(
    principal: Principal = Depends(require_perm("legal:read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve full 8-widget dashboard summary for Legal & Compliance Operations."""
    # Ensure regulatory calendar has baseline items
    populate_regulatory_compliance_calendar(db, tenant_id=principal.tenant_id)
    return get_legal_compliance_dashboard(db, tenant_id=principal.tenant_id)


@router.get("/registration/workflow")
def api_get_registration_workflow(
    principal: Principal = Depends(require_perm("legal:read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Retrieve full 14-item CAC Company Registration Workflow with canonical statuses and statutory references."""
    return get_company_registration_workflow(db, tenant_id=principal.tenant_id)


@router.get("/research")
def api_get_research(
    principal: Principal = Depends(require_perm("legal:read")),
) -> dict[str, Any]:
    """Capability 1: Official statutory research citations (CAMA 2020, NDPA 2023, FIRS, Infants Relief Act)."""
    return get_statutory_research_knowledge()


@router.get("/incorporation")
def api_get_incorporation(
    principal: Principal = Depends(require_perm("legal:read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Get active incorporation draft."""
    draft = db.execute(
        select(LegalEntityDraftRecord).where(LegalEntityDraftRecord.tenant_id == principal.tenant_id)
    ).scalar_one_or_none()

    if draft is None:
        return prepare_incorporation_draft(db, principal=principal)
    return {
        "draft_id": draft.draft_id,
        "company_name": draft.company_name,
        "entity_type": draft.entity_type,
        "nominal_share_capital_ngn": draft.nominal_share_capital,
        "share_nominal_value_ngn": draft.share_nominal_value,
        "registered_office_address": draft.registered_office_address,
        "cac_availability_code": draft.cac_availability_code,
        "status": draft.status,
    }


@router.post("/incorporation", status_code=status.HTTP_200_OK)
def api_save_incorporation(
    body: IncorporationDraftRequest,
    principal: Principal = Depends(require_perm("legal:write")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Capability 2 & 3: Save or update company incorporation draft & name reservations."""
    return prepare_incorporation_draft(
        db,
        principal=principal,
        company_name=body.company_name,
        alternative_names=body.alternative_names,
        nominal_share_capital=body.nominal_share_capital,
        registered_office_address=body.registered_office_address,
        objects_clause=body.objects_clause,
    )


@router.get("/officers")
def api_get_officers(
    principal: Principal = Depends(require_perm("legal:read")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Capability 4: List directors, shareholders, and PSC register."""
    officers = db.execute(
        select(LegalOfficerRecord).where(LegalOfficerRecord.tenant_id == principal.tenant_id)
    ).scalars().all()

    return [
        {
            "officer_id": o.officer_id,
            "officer_type": o.officer_type,
            "full_legal_name": o.full_legal_name,
            "date_of_birth": o.date_of_birth,
            "is_under_18": o.is_under_18,
            "guardian_officer_id": o.guardian_officer_id,
            "residential_address": o.residential_address,
            "email": o.email,
            "phone": o.phone,
            "identity_masked": o.identity_number_masked,
            "shares_allocated": o.shares_allocated,
            "equity_percentage": o.equity_percentage,
            "has_significant_control": o.has_significant_control,
            "professional_accreditation_number": o.professional_accreditation_number,
        }
        for o in officers
    ]


@router.post("/officers", status_code=status.HTTP_201_CREATED)
def api_register_officer(
    body: RegisterOfficerRequest,
    principal: Principal = Depends(require_perm("legal:write")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Capability 4: Register officer with strict under-18 guardian capacity rules and zero-fabrication validation."""
    return register_officer_with_safeguards(
        db,
        principal=principal,
        draft_id=body.draft_id,
        officer_type=body.officer_type,
        full_legal_name=body.full_legal_name,
        date_of_birth=body.date_of_birth,
        residential_address=body.residential_address,
        email=body.email,
        phone=body.phone,
        nin=body.nin,
        shares_allocated=body.shares_allocated,
        equity_percentage=body.equity_percentage,
        guardian_officer_id=body.guardian_officer_id,
        professional_accreditation_number=body.professional_accreditation_number,
    )


@router.get("/policies")
def api_get_policies(
    principal: Principal = Depends(require_perm("legal:read")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Capability 5: Get statutory compliance policies."""
    policies = db.execute(
        select(LegalStatutoryPolicyRecord).where(LegalStatutoryPolicyRecord.tenant_id == principal.tenant_id)
    ).scalars().all()

    if not policies:
        return generate_statutory_policies(db, principal=principal)

    return [
        {
            "policy_id": p.policy_id,
            "policy_type": p.policy_type,
            "title": p.title,
            "version": p.version,
            "status": p.status,
            "content_markdown": p.content_markdown,
        }
        for p in policies
    ]


@router.post("/policies/generate")
def api_generate_policies(
    principal: Principal = Depends(require_perm("legal:write")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Capability 5: Autonomous drafting of Privacy Policy, Terms, 6-Year Retention, Deletion, and DPIA."""
    return generate_statutory_policies(db, principal=principal)


@router.get("/ndpc/materials")
def api_get_ndpc_materials(
    principal: Principal = Depends(require_perm("legal:read")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Capability 7: Prepare NDPC DPMI registration dossier & materials."""
    return prepare_ndpc_registration_materials(db, principal=principal)


@router.get("/calendar")
def api_get_calendar(
    principal: Principal = Depends(require_perm("legal:read")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Capability 8: Regulatory compliance calendar events & countdowns."""
    events = db.execute(
        select(LegalComplianceCalendarEventRecord)
        .where(LegalComplianceCalendarEventRecord.tenant_id == principal.tenant_id)
        .order_by(LegalComplianceCalendarEventRecord.due_date.asc())
    ).scalars().all()

    if not events:
        return populate_regulatory_compliance_calendar(db, tenant_id=principal.tenant_id)

    return [
        {
            "event_id": e.event_id,
            "authority": e.authority,
            "title": e.title,
            "statutory_deadline": e.statutory_deadline,
            "due_date": e.due_date.isoformat(),
            "recurrence": e.recurrence,
            "status": e.status,
            "filing_fee_ngn": e.filing_fee_ngn,
            "penalty_risk": e.penalty_risk_description,
        }
        for e in events
    ]


@router.post("/calendar/populate")
def api_populate_calendar(
    principal: Principal = Depends(require_perm("legal:write")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Capability 8: Repopulate statutory compliance calendar deadlines."""
    return populate_regulatory_compliance_calendar(db, tenant_id=principal.tenant_id)


@router.post("/filing/submit")
def api_submit_filing(
    body: FilingSubmitRequest,
    principal: Principal = Depends(require_perm("legal:write")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Capability 9: Submit statutory filing action (Strictly gated by ARGON ApprovalGate)."""
    return trigger_statutory_filing_action(
        db,
        principal=principal,
        workflow_id=body.workflow_id,
        filing_type=body.filing_type,
        target_authority=body.target_authority,
        remita_rrr=body.remita_rrr,
        fee_amount_ngn=body.fee_amount_ngn,
        declaration_text=body.declaration_text,
    )


@router.post("/approvals/{approval_id}/action")
def api_action_approval(
    approval_id: str,
    body: ApprovalDecisionRequest,
    principal: Principal = Depends(require_perm("legal:approve")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Capability 9: Explicit human approval or rejection for filing submission, declarations, or payments."""
    return execute_approved_filing(
        db,
        principal=principal,
        approval_id=approval_id,
        decision=body.decision,
        rejection_reason=body.rejection_reason,
    )


@router.get("/archive")
def api_get_archive(
    principal: Principal = Depends(require_perm("legal:read")),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    """Capability 10: Secure document vault of official certificates, receipts, and approved documents."""
    docs = db.execute(
        select(LegalArchivedDocumentRecord).where(LegalArchivedDocumentRecord.tenant_id == principal.tenant_id)
    ).scalars().all()

    return [
        {
            "archive_id": d.archive_id,
            "document_category": d.document_category,
            "title": d.title,
            "authority_issued": d.authority_issued,
            "file_path": d.file_path,
            "sha256_checksum": d.sha256_checksum,
            "is_verified_authentic": d.is_verified_authentic,
            "created_at": d.created_at.isoformat(),
        }
        for d in docs
    ]


@router.post("/archive", status_code=status.HTTP_201_CREATED)
def api_create_archive(
    body: DocumentArchiveRequest,
    principal: Principal = Depends(require_perm("legal:write")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Capability 10: Archive official certificate or receipt with SHA-256 verification hash."""
    raw_content = body.file_content_base64.encode("utf-8") if body.file_content_base64 else f"{body.title}-{body.authority_issued}".encode("utf-8")
    return archive_official_document(
        db,
        principal=principal,
        document_category=body.document_category,
        title=body.title,
        authority_issued=body.authority_issued,
        file_path=body.file_path,
        file_content=raw_content,
        workflow_id=body.workflow_id,
    )


@router.post("/professional-review/evaluate")
def api_evaluate_professional(
    body: ProfessionalReviewRequest,
    principal: Principal = Depends(require_perm("legal:read")),
) -> dict[str, Any]:
    """Capability 6: Evaluate whether filing requires an accredited agent / legal practitioner."""
    return evaluate_professional_review(body.filing_type)
