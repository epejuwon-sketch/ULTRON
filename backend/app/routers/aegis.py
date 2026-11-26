"""AEGIS Autonomous Security & Defence API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.services.aegis_service import (
    get_aegis_posture,
    inspect_url_safety,
    list_security_incidents,
    list_security_scans,
    refresh_fim_baselines,
    remediate_incident,
    run_security_scan,
    scan_code_bundle,
)

router = APIRouter(prefix="/api/v1/aegis", tags=["AEGIS Autonomous Security"])


class TriggerScanRequest(BaseModel):
    scan_type: str = Field(default="FULL", pattern="^(FAST|FULL|DEEP)$")


class RemediateRequest(BaseModel):
    action: str = Field(min_length=3, max_length=500)
    high_impact: bool = False


class InspectUrlRequest(BaseModel):
    url: str = Field(min_length=4, max_length=2000)


class ScanCodeRequest(BaseModel):
    files: dict[str, str]


@router.get("/posture")
def api_aegis_posture(
    principal: Principal = Depends(require_perm("security:read")),
    db: Session = Depends(get_db),
) -> dict:
    return get_aegis_posture(db, tenant_id=principal.tenant_id)


@router.post("/scans", status_code=status.HTTP_201_CREATED)
def api_run_scan(
    body: TriggerScanRequest,
    principal: Principal = Depends(require_perm("security:manage")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return run_security_scan(db, principal=principal, settings=settings, scan_type=body.scan_type)


@router.get("/scans")
def api_list_scans(
    limit: int = Query(default=25, ge=1, le=100),
    principal: Principal = Depends(require_perm("security:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_security_scans(db, tenant_id=principal.tenant_id, limit=limit)
    return {"total": len(items), "scans": items}


@router.get("/incidents")
def api_list_incidents(
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    principal: Principal = Depends(require_perm("security:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_security_incidents(db, tenant_id=principal.tenant_id, status_filter=status_filter, limit=limit)
    return {"total": len(items), "incidents": items}


@router.post("/incidents/{incident_id}/remediate")
def api_remediate_incident(
    incident_id: str,
    body: RemediateRequest,
    principal: Principal = Depends(require_perm("security:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return remediate_incident(
        db,
        principal=principal,
        incident_id=incident_id,
        action=body.action,
        high_impact=body.high_impact,
    )


@router.post("/fim/rebaseline")
def api_refresh_fim(
    principal: Principal = Depends(require_perm("security:manage")),
    db: Session = Depends(get_db),
) -> dict:
    return refresh_fim_baselines(db, principal=principal)


@router.post("/inspect-url")
def api_inspect_url(
    body: InspectUrlRequest,
    _principal: Principal = Depends(require_perm("security:read")),
) -> dict:
    return inspect_url_safety(body.url)


@router.post("/scan-code")
def api_scan_code(
    body: ScanCodeRequest,
    _principal: Principal = Depends(require_perm("security:read")),
) -> dict:
    return scan_code_bundle(body.files)


class OperationalActionRequest(BaseModel):
    action_category: str = Field(min_length=3, max_length=64)
    summary: str = Field(min_length=3, max_length=500)
    venture: str = Field(default="CARAVAN", max_length=64)
    payload: dict = Field(default_factory=dict)


@router.get("/operational-control")
def api_get_operational_control(
    principal: Principal = Depends(require_perm("security:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.operational_control_service import get_operational_control_policy

    return get_operational_control_policy(db, tenant_id=principal.tenant_id)


@router.post("/operational-control/evaluate")
def api_evaluate_operational_control(
    body: OperationalActionRequest,
    principal: Principal = Depends(require_perm("security:read")),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.operational_control_service import evaluate_operational_action

    return evaluate_operational_action(
        db,
        principal=principal,
        action_category=body.action_category,
        summary=body.summary,
        venture=body.venture,
        payload=body.payload,
    )

