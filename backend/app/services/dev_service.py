"""Developer & Coding Infrastructure service: projects, git inspection, AST code analysis, codegen proposals, and ApprovalGate deployments/rollbacks."""

from __future__ import annotations

import json
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Principal
from app.db.models import DeploymentRequest, DevActivityRecord, ProjectRecord
from app.db.repositories import append_audit_log
from app.integrations.extended import GitHubClient
from app.services.approval_service import create_approval_request, serialize_approval
from app.services.neon_router import invoke_agent_reasoning
from app.services.tool_service import analyze_python_ast

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or f"project-{uuid.uuid4().hex[:6]}"


def _log_activity(
    db: Session,
    *,
    tenant_id: str,
    project_id: str,
    actor: str,
    activity_type: str,
    summary: str,
    details: dict[str, Any] | None = None,
) -> None:
    db.add(
        DevActivityRecord(
            activity_id=f"act_{uuid.uuid4().hex[:16]}",
            tenant_id=tenant_id,
            project_id=project_id,
            actor=actor,
            activity_type=activity_type,
            summary=summary,
            details_json=json.dumps(details or {}, default=str),
        )
    )


def create_project(
    db: Session,
    *,
    principal: Principal,
    name: str,
    description: str = "",
    repo_full_name: str = "",
    default_branch: str = "main",
    budget_usd: float = 0.0,
) -> dict[str, Any]:
    project = ProjectRecord(
        project_id=f"prj_{uuid.uuid4().hex[:16]}",
        tenant_id=principal.tenant_id,
        name=name.strip(),
        slug=_slugify(name),
        description=description.strip(),
        repo_full_name=repo_full_name.strip(),
        default_branch=default_branch.strip() or "main",
        status="ACTIVE",
        budget_usd=round(float(budget_usd), 2),
        created_by=principal.username,
    )
    db.add(project)
    db.flush()
    _log_activity(
        db,
        tenant_id=principal.tenant_id,
        project_id=project.project_id,
        actor=principal.username,
        activity_type="PROJECT_CREATED",
        summary=f"Created project '{project.name}' ({project.repo_full_name or 'local'})",
    )
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="PROJECT_CREATED",
        resource=project.project_id,
        outcome=project.slug,
    )
    db.commit()
    db.refresh(project)
    return _serialize_project(project)


def list_projects(db: Session, *, tenant_id: str) -> list[dict[str, Any]]:
    rows = db.execute(
        select(ProjectRecord)
        .where(ProjectRecord.tenant_id == tenant_id)
        .order_by(ProjectRecord.created_at.desc())
    ).scalars().all()
    return [_serialize_project(r) for r in rows]


def get_project(db: Session, *, tenant_id: str, project_id: str) -> ProjectRecord:
    project = db.execute(
        select(ProjectRecord).where(
            ProjectRecord.project_id == project_id,
            ProjectRecord.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    if project is None:
        raise NotFoundError(f"Project '{project_id}' not found.")
    return project


def update_project(
    db: Session,
    *,
    principal: Principal,
    project_id: str,
    name: str | None = None,
    description: str | None = None,
    repo_full_name: str | None = None,
    default_branch: str | None = None,
    status: str | None = None,
    budget_usd: float | None = None,
) -> dict[str, Any]:
    project = get_project(db, tenant_id=principal.tenant_id, project_id=project_id)
    changes: list[str] = []
    if name is not None and name.strip():
        project.name = name.strip()
        project.slug = _slugify(project.name)
        changes.append("name")
    if description is not None:
        project.description = description.strip()
        changes.append("description")
    if repo_full_name is not None:
        project.repo_full_name = repo_full_name.strip()
        changes.append("repo_full_name")
    if default_branch is not None and default_branch.strip():
        project.default_branch = default_branch.strip()
        changes.append("default_branch")
    if status is not None and status.strip():
        project.status = status.strip().upper()
        changes.append(f"status:{project.status}")
    if budget_usd is not None:
        project.budget_usd = round(float(budget_usd), 2)
        changes.append(f"budget:{project.budget_usd}")
    project.updated_at = datetime.now(timezone.utc)
    if changes:
        _log_activity(
            db,
            tenant_id=principal.tenant_id,
            project_id=project.project_id,
            actor=principal.username,
            activity_type="PROJECT_UPDATED",
            summary=f"Updated project '{project.name}' ({', '.join(changes)})",
        )
        append_audit_log(
            db,
            tenant_id=principal.tenant_id,
            actor=principal.username,
            action="PROJECT_UPDATED",
            resource=project.project_id,
            outcome=",".join(changes),
        )
    db.commit()
    db.refresh(project)
    return _serialize_project(project)


def delete_project(
    db: Session,
    *,
    principal: Principal,
    project_id: str,
) -> dict[str, Any]:
    project = get_project(db, tenant_id=principal.tenant_id, project_id=project_id)
    name = project.name
    db.delete(project)
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="PROJECT_DELETED",
        resource=project_id,
        outcome=name,
    )
    db.commit()
    return {"deleted": True, "project_id": project_id, "name": name}


def inspect_repository(
    db: Session,
    *,
    principal: Principal,
    project_id: str,
    settings: Settings,
) -> dict[str, Any]:
    """Inspect local git checkout status/branches/commits plus optional GitHub API metadata."""
    project = get_project(db, tenant_id=principal.tenant_id, project_id=project_id)
    local_git: dict[str, Any] = {"available": False}

    if (_REPO_ROOT / ".git").exists():
        try:
            branch = subprocess.check_output(
                ["git", "-C", str(_REPO_ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
                text=True,
                timeout=5,
            ).strip()
            commits = subprocess.check_output(
                ["git", "-C", str(_REPO_ROOT), "log", "-n", "5", "--oneline"],
                text=True,
                timeout=5,
            ).strip().splitlines()
            branches = subprocess.check_output(
                ["git", "-C", str(_REPO_ROOT), "branch", "--format=%(refname:short)"],
                text=True,
                timeout=5,
            ).strip().splitlines()
            local_git = {
                "available": True,
                "current_branch": branch,
                "branches": branches,
                "recent_commits": commits,
            }
        except Exception as exc:
            local_git = {"available": False, "error": str(exc)}

    github_info: dict[str, Any] = {"configured": False}
    gh = GitHubClient(settings)
    if gh.is_configured() and project.repo_full_name:
        try:
            data = gh.get_repo_info(project.repo_full_name)
            github_info = {
                "configured": True,
                "full_name": data.get("full_name"),
                "default_branch": data.get("default_branch"),
                "private": data.get("private"),
                "html_url": data.get("html_url"),
            }
        except Exception as exc:
            github_info = {"configured": True, "error": str(exc)}

    _log_activity(
        db,
        tenant_id=principal.tenant_id,
        project_id=project.project_id,
        actor=principal.username,
        activity_type="REPO_INSPECTED",
        summary=f"Inspected repository for '{project.name}'",
    )
    db.commit()
    return {
        "project_id": project.project_id,
        "repo_full_name": project.repo_full_name,
        "local_git": local_git,
        "github_api": github_info,
    }


def analyze_project_code(
    db: Session,
    *,
    principal: Principal,
    project_id: str,
    filename: str,
    source_code: str,
) -> dict[str, Any]:
    """Run real Python AST static analysis and log dev activity."""
    project = get_project(db, tenant_id=principal.tenant_id, project_id=project_id)
    report = analyze_python_ast(source_code)
    _log_activity(
        db,
        tenant_id=principal.tenant_id,
        project_id=project.project_id,
        actor=principal.username,
        activity_type="CODE_ANALYZED",
        summary=f"Analyzed '{filename}' (valid={report['syntax_valid']}, findings={len(report['security_findings'])})",
        details={"filename": filename, "findings_count": len(report["security_findings"])},
    )
    db.commit()
    return {"project_id": project.project_id, "filename": filename, "analysis": report}


def propose_code_change(
    db: Session,
    *,
    principal: Principal,
    project_id: str,
    specification: str,
    target_branch: str,
    settings: Settings,
) -> dict[str, Any]:
    """Generate a proposed code change via AGT-03 Coding Agent without auto-writing or merging."""
    project = get_project(db, tenant_id=principal.tenant_id, project_id=project_id)
    reasoning = invoke_agent_reasoning(
        db,
        agent_id="AGT-03",
        prompt=f"Propose a clean, reviewed code patch for branch '{target_branch}': {specification}",
        settings=settings,
        context={"project_id": project.project_id, "repo": project.repo_full_name},
        tenant_id=principal.tenant_id,
        actor=principal.username,
    )
    _log_activity(
        db,
        tenant_id=principal.tenant_id,
        project_id=project.project_id,
        actor=principal.username,
        activity_type="CODE_PROPOSAL_GENERATED",
        summary=f"Generated code proposal for branch '{target_branch}' (auto-merge disabled).",
        details={"branch": target_branch, "execution_mode": reasoning["execution_mode"]},
    )
    db.commit()
    return {
        "project_id": project.project_id,
        "target_branch": target_branch,
        "auto_applied": False,
        "requires_human_review": True,
        "proposal": reasoning,
    }


def request_deployment(
    db: Session,
    *,
    principal: Principal,
    project_id: str,
    environment: str,
    git_ref: str,
    previous_ref: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    """Submit a deployment request. Production deployments strictly require ApprovalGate approval."""
    project = get_project(db, tenant_id=principal.tenant_id, project_id=project_id)
    env = environment.strip().lower()
    requires_gate = env == "production"

    dep_id = f"dep_{uuid.uuid4().hex[:16]}"
    dep = DeploymentRequest(
        deployment_id=dep_id,
        tenant_id=principal.tenant_id,
        project_id=project.project_id,
        environment=env,
        git_ref=git_ref.strip(),
        previous_ref=previous_ref.strip() if previous_ref else None,
        status="WAITING_FOR_APPROVAL" if requires_gate else "APPROVED_READY_TO_DEPLOY",
        requested_by=principal.username,
        notes=notes.strip(),
    )
    db.add(dep)
    db.flush()

    approval_payload: dict[str, Any] | None = None
    if requires_gate:
        approval = create_approval_request(
            db,
            tenant_id=principal.tenant_id,
            requested_by=principal.username,
            action_type="PRODUCTION_DEPLOYMENT",
            reason=f"Production deployment of '{project.name}' at ref '{dep.git_ref}' requires OWNER/ADMIN sign-off.",
            risk_level="HIGH",
            resource_ref=dep_id,
            payload={"project_id": project.project_id, "git_ref": dep.git_ref, "environment": env},
            commit=False,
        )
        dep.approval_id = approval.approval_id
        approval_payload = serialize_approval(approval)

    _log_activity(
        db,
        tenant_id=principal.tenant_id,
        project_id=project.project_id,
        actor=principal.username,
        activity_type="DEPLOYMENT_REQUESTED",
        summary=f"Requested {env} deployment for ref '{dep.git_ref}' (status={dep.status})",
        details={"deployment_id": dep_id, "environment": env},
    )
    db.commit()
    db.refresh(dep)
    out = _serialize_deployment(dep)
    out["approval"] = approval_payload
    return out


def rollback_deployment(
    db: Session,
    *,
    principal: Principal,
    project_id: str,
    deployment_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Record a controlled rollback request back to `previous_ref`, gated by ApprovalGate for production."""
    project = get_project(db, tenant_id=principal.tenant_id, project_id=project_id)
    dep = db.execute(
        select(DeploymentRequest).where(
            DeploymentRequest.deployment_id == deployment_id,
            DeploymentRequest.project_id == project.project_id,
            DeploymentRequest.tenant_id == principal.tenant_id,
        )
    ).scalar_one_or_none()
    if dep is None:
        raise NotFoundError(f"Deployment '{deployment_id}' not found.")
    if not dep.previous_ref:
        raise ConflictError("Cannot rollback deployment without a recorded `previous_ref`.")

    dep.status = "ROLLED_BACK"
    dep.notes = f"{dep.notes} | Rolled back to {dep.previous_ref}: {reason}".strip(" |")
    dep.updated_at = datetime.now(timezone.utc)

    _log_activity(
        db,
        tenant_id=principal.tenant_id,
        project_id=project.project_id,
        actor=principal.username,
        activity_type="DEPLOYMENT_ROLLED_BACK",
        summary=f"Rolled back {dep.environment} from '{dep.git_ref}' to '{dep.previous_ref}'",
        details={"deployment_id": dep.deployment_id, "reason": reason},
    )
    append_audit_log(
        db,
        tenant_id=principal.tenant_id,
        actor=principal.username,
        action="DEPLOYMENT_ROLLBACK",
        resource=dep.deployment_id,
        outcome=f"TARGET_REF={dep.previous_ref}",
    )
    db.commit()
    db.refresh(dep)
    return _serialize_deployment(dep)


def list_project_activity(db: Session, *, tenant_id: str, project_id: str, limit: int = 50) -> list[dict[str, Any]]:
    get_project(db, tenant_id=tenant_id, project_id=project_id)
    rows = db.execute(
        select(DevActivityRecord)
        .where(DevActivityRecord.tenant_id == tenant_id, DevActivityRecord.project_id == project_id)
        .order_by(DevActivityRecord.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [
        {
            "activity_id": r.activity_id,
            "actor": r.actor,
            "activity_type": r.activity_type,
            "summary": r.summary,
            "details": json.loads(r.details_json or "{}"),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


def list_project_deployments(db: Session, *, tenant_id: str, project_id: str) -> list[dict[str, Any]]:
    get_project(db, tenant_id=tenant_id, project_id=project_id)
    rows = db.execute(
        select(DeploymentRequest)
        .where(DeploymentRequest.tenant_id == tenant_id, DeploymentRequest.project_id == project_id)
        .order_by(DeploymentRequest.created_at.desc())
    ).scalars().all()
    return [_serialize_deployment(r) for r in rows]


def _serialize_project(p: ProjectRecord) -> dict[str, Any]:
    return {
        "project_id": p.project_id,
        "tenant_id": p.tenant_id,
        "name": p.name,
        "slug": p.slug,
        "description": p.description,
        "repo_full_name": p.repo_full_name,
        "default_branch": p.default_branch,
        "status": p.status,
        "budget_usd": p.budget_usd,
        "created_by": p.created_by,
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def _serialize_deployment(d: DeploymentRequest) -> dict[str, Any]:
    return {
        "deployment_id": d.deployment_id,
        "project_id": d.project_id,
        "environment": d.environment,
        "git_ref": d.git_ref,
        "previous_ref": d.previous_ref,
        "status": d.status,
        "approval_id": d.approval_id,
        "requested_by": d.requested_by,
        "notes": d.notes,
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    }
