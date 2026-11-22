"""GitHub Engineering, Web Research, and Unified Natural-Language Orchestration routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.permissions import Principal
from app.db.session import get_db
from app.integrations.github_client import GitHubEngineeringClient
from app.integrations.web_research import WebResearchClient
from app.routers.deps import require_perm
from app.services.integration_manager import resolve_provider_token
from app.services.orchestration_bridge import orchestrate_natural_language_objective

router = APIRouter(tags=["GitHub, Web Research & Unified Orchestration"])


class CreateBranchRequest(BaseModel):
    new_branch: str = Field(min_length=2, max_length=120)
    from_branch: str = "main"


class UpsertRepoFileRequest(BaseModel):
    path: str = Field(min_length=1, max_length=500)
    branch: str = Field(min_length=2, max_length=120)
    content: str
    message: str = Field(min_length=3, max_length=300)
    sha: str | None = None


class CreatePRRequest(BaseModel):
    title: str = Field(min_length=3, max_length=250)
    head: str = Field(min_length=2, max_length=120)
    base: str = "main"
    body: str = ""
    draft: bool = False


class CreateIssueRequest(BaseModel):
    title: str = Field(min_length=3, max_length=250)
    body: str = ""
    labels: list[str] = Field(default_factory=list)


class ResearchSearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    max_results: int = Field(default=5, ge=1, le=10)


class ResearchFetchRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    max_chars: int = Field(default=4000, ge=200, le=20000)


class NaturalLanguageOrchestrateRequest(BaseModel):
    objective: str = Field(min_length=3, max_length=8000)
    financial_amount_usd: float = Field(default=0.0, ge=0.0)
    project_id: str | None = None
    auto_execute: bool = True


# --- Unified Natural-Language NEON + ARGON Entrypoint ---
@router.post("/api/v1/orchestrate")
def api_orchestrate_natural_language(
    body: NaturalLanguageOrchestrateRequest,
    principal: Principal = Depends(require_perm("tasks:create")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Accept a natural-language objective; NEON plans/routes and ARGON coordinates, gates, executes, and verifies."""
    return orchestrate_natural_language_objective(
        db,
        principal=principal,
        objective=body.objective,
        financial_amount_usd=body.financial_amount_usd,
        project_id=body.project_id,
        auto_execute=body.auto_execute,
        settings=settings,
    )


# --- Real Web Research ---
@router.post("/api/v1/research/search")
def api_research_search(
    body: ResearchSearchRequest,
    _principal: Principal = Depends(require_perm("tools:execute")),
    settings: Settings = Depends(get_settings),
) -> dict:
    return WebResearchClient(settings).search(body.query, max_results=body.max_results)


@router.post("/api/v1/research/fetch")
def api_research_fetch(
    body: ResearchFetchRequest,
    _principal: Principal = Depends(require_perm("tools:execute")),
    settings: Settings = Depends(get_settings),
) -> dict:
    return WebResearchClient(settings).fetch_and_extract(body.url, max_chars=body.max_chars)


# --- GitHub Engineering ---
def _gh(db: Session, principal: Principal, settings: Settings) -> GitHubEngineeringClient:
    tok = resolve_provider_token(db, tenant_id=principal.tenant_id, provider="github", settings=settings)
    return GitHubEngineeringClient(settings, token_override=tok)


@router.get("/api/v1/github/repos")
def api_gh_list_repos(
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    repos = _gh(db, principal, settings).list_repos()
    return {"total": len(repos), "repos": repos}


@router.get("/api/v1/github/repos/{owner}/{repo}")
def api_gh_repo(
    owner: str,
    repo: str,
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _gh(db, principal, settings).get_repo(f"{owner}/{repo}")


@router.get("/api/v1/github/repos/{owner}/{repo}/branches")
def api_gh_branches(
    owner: str,
    repo: str,
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    items = _gh(db, principal, settings).list_branches(f"{owner}/{repo}")
    return {"total": len(items), "branches": items}


@router.post("/api/v1/github/repos/{owner}/{repo}/branches")
def api_gh_create_branch(
    owner: str,
    repo: str,
    body: CreateBranchRequest,
    principal: Principal = Depends(require_perm("projects:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _gh(db, principal, settings).create_branch(f"{owner}/{repo}", body.new_branch, from_branch=body.from_branch)


@router.get("/api/v1/github/repos/{owner}/{repo}/commits")
def api_gh_commits(
    owner: str,
    repo: str,
    sha: str = Query(default="main"),
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    items = _gh(db, principal, settings).list_commits(f"{owner}/{repo}", sha=sha)
    return {"total": len(items), "commits": items}


@router.get("/api/v1/github/repos/{owner}/{repo}/file")
def api_gh_get_file(
    owner: str,
    repo: str,
    path: str = Query(...),
    ref: str = Query(default="main"),
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _gh(db, principal, settings).get_file_content(f"{owner}/{repo}", path, ref=ref)


@router.put("/api/v1/github/repos/{owner}/{repo}/file")
def api_gh_upsert_file(
    owner: str,
    repo: str,
    body: UpsertRepoFileRequest,
    principal: Principal = Depends(require_perm("projects:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _gh(db, principal, settings).upsert_file(
        f"{owner}/{repo}",
        path=body.path,
        branch=body.branch,
        content=body.content,
        message=body.message,
        sha=body.sha,
    )


@router.get("/api/v1/github/repos/{owner}/{repo}/pulls")
def api_gh_pulls(
    owner: str,
    repo: str,
    state: str = Query(default="open"),
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    items = _gh(db, principal, settings).list_pull_requests(f"{owner}/{repo}", state=state)
    return {"total": len(items), "pull_requests": items}


@router.post("/api/v1/github/repos/{owner}/{repo}/pulls")
def api_gh_create_pr(
    owner: str,
    repo: str,
    body: CreatePRRequest,
    principal: Principal = Depends(require_perm("projects:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _gh(db, principal, settings).create_pull_request(
        f"{owner}/{repo}", title=body.title, head=body.head, base=body.base, body=body.body, draft=body.draft
    )


@router.get("/api/v1/github/repos/{owner}/{repo}/issues")
def api_gh_issues(
    owner: str,
    repo: str,
    state: str = Query(default="open"),
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    items = _gh(db, principal, settings).list_issues(f"{owner}/{repo}", state=state)
    return {"total": len(items), "issues": items}


@router.post("/api/v1/github/repos/{owner}/{repo}/issues")
def api_gh_create_issue(
    owner: str,
    repo: str,
    body: CreateIssueRequest,
    principal: Principal = Depends(require_perm("projects:write")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    return _gh(db, principal, settings).create_issue(
        f"{owner}/{repo}", title=body.title, body=body.body, labels=body.labels
    )


@router.get("/api/v1/github/repos/{owner}/{repo}/workflows")
def api_gh_workflows(
    owner: str,
    repo: str,
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    items = _gh(db, principal, settings).list_workflow_runs(f"{owner}/{repo}")
    return {"total": len(items), "workflow_runs": items}


@router.get("/api/v1/github/repos/{owner}/{repo}/releases")
def api_gh_releases(
    owner: str,
    repo: str,
    principal: Principal = Depends(require_perm("projects:read")),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict:
    items = _gh(db, principal, settings).list_releases(f"{owner}/{repo}")
    return {"total": len(items), "releases": items}
