"""Developer & Coding Infrastructure routes: projects, repo inspection, AST analysis, code proposals, deployments, and rollbacks."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.routers.deps import require_perm
from app.schemas import (
    AnalyzeCodeRequest,
    CreateProjectRequest,
    ProposeCodeChangeRequest,
    RequestDeploymentRequest,
    RollbackDeploymentRequest,
)
from app.services.dev_service import (
    analyze_project_code,
    create_project,
    inspect_repository,
    list_project_activity,
    list_project_deployments,
    list_projects,
    propose_code_change,
    request_deployment,
    rollback_deployment,
)

router = APIRouter(prefix="/api/v1/projects", tags=["Developer & Projects"])


@router.post("", status_code=status.HTTP_201_CREATED)
def api_create_project(
    body: CreateProjectRequest,
    principal: Principal = Depends(require_perm("projects:write")),
    db: Session = Depends(get_db),
) -> dict:
    return create_project(
        db,
        principal=principal,
        name=body.name,
        description=body.description,
        repo_full_name=body.repo_full_name,
        default_branch=body.default_branch,
        budget_usd=body.budget_usd,
    )


@router.get("")
def api_list_projects(
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_projects(db, tenant_id=principal.tenant_id)
    return {"total": len(items), "projects": items}


@router.get("/{project_id}/repository")
def api_inspect_repo(
    project_id: str,
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return inspect_repository(db, principal=principal, project_id=project_id, settings=settings)


@router.post("/{project_id}/analyze")
def api_analyze_code(
    project_id: str,
    body: AnalyzeCodeRequest,
    principal: Principal = Depends(require_perm("projects:write")),
    db: Session = Depends(get_db),
) -> dict:
    return analyze_project_code(
        db,
        principal=principal,
        project_id=project_id,
        filename=body.filename,
        source_code=body.source_code,
    )


@router.post("/{project_id}/code-proposals")
def api_propose_code_change(
    project_id: str,
    body: ProposeCodeChangeRequest,
    principal: Principal = Depends(require_perm("projects:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return propose_code_change(
        db,
        principal=principal,
        project_id=project_id,
        specification=body.specification,
        target_branch=body.target_branch,
        settings=settings,
    )


@router.post("/{project_id}/deployments", status_code=status.HTTP_201_CREATED)
def api_request_deployment(
    project_id: str,
    body: RequestDeploymentRequest,
    principal: Principal = Depends(require_perm("projects:write")),
    db: Session = Depends(get_db),
) -> dict:
    return request_deployment(
        db,
        principal=principal,
        project_id=project_id,
        environment=body.environment,
        git_ref=body.git_ref,
        previous_ref=body.previous_ref,
        notes=body.notes,
    )


@router.get("/{project_id}/deployments")
def api_list_deployments(
    project_id: str,
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_project_deployments(db, tenant_id=principal.tenant_id, project_id=project_id)
    return {"total": len(items), "deployments": items}


@router.post("/{project_id}/deployments/{deployment_id}/rollback")
def api_rollback_deployment(
    project_id: str,
    deployment_id: str,
    body: RollbackDeploymentRequest,
    principal: Principal = Depends(require_perm("projects:deploy")),
    db: Session = Depends(get_db),
) -> dict:
    return rollback_deployment(
        db,
        principal=principal,
        project_id=project_id,
        deployment_id=deployment_id,
        reason=body.reason,
    )


@router.get("/{project_id}/activity")
def api_project_activity(
    project_id: str,
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
) -> dict:
    items = list_project_activity(db, tenant_id=principal.tenant_id, project_id=project_id)
    return {"total": len(items), "activities": items}
