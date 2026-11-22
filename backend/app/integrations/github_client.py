"""Full GitHub Engineering REST API v3 client with protected-branch safety and ApprovalGate guards."""

from __future__ import annotations

import base64
import time
from typing import Any

import httpx

from app.core.config import Settings
from app.core.exceptions import AuthorizationError, IntegrationError
from app.integrations.base import HonestCapabilityState, IntegrationStatus, classify_http_error

PROTECTED_BRANCHES = frozenset({"main", "master", "production", "prod"})


class GitHubEngineeringClient:
    """Real GitHub REST API v3 client for repositories, branches, files, PRs, issues, CI runs, and releases."""

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        settings: Settings,
        *,
        token_override: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = settings
        self._token_override = token_override
        self._client = http_client

    @property
    def _token(self) -> str:
        if self._token_override:
            return self._token_override.strip()
        return self._settings.github_token.get_secret_value().strip() if self._settings.github_token else ""

    def is_configured(self) -> bool:
        return bool(self._token)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _req(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: float = 12.0,
    ) -> Any:
        if not self.is_configured():
            raise IntegrationError("GITHUB_TOKEN is not configured.")
        url = f"{self.BASE_URL}{path}"
        try:
            if self._client is not None:
                resp = self._client.request(method, url, headers=self._headers(), params=params, json=json_body, timeout=timeout)
            else:
                with httpx.Client(timeout=timeout) as client:
                    resp = client.request(method, url, headers=self._headers(), params=params, json=json_body)
        except httpx.HTTPError as exc:
            raise IntegrationError(f"GitHub network error: {type(exc).__name__}") from exc
        if resp.status_code >= 400:
            raise IntegrationError(f"GitHub API error on {path}: {classify_http_error(resp.status_code)}")
        return resp.json() if resp.content else {}

    def verify_live(self, timeout_seconds: float = 8.0) -> IntegrationStatus:
        if not self.is_configured():
            return IntegrationStatus(
                provider="github",
                configured=False,
                capability_state=HonestCapabilityState.DEFINED_NOT_INSTALLED,
                live_verified=False,
                requires_approval_for_mutations=True,
                missing_env_vars=["GITHUB_TOKEN"],
                detail="GITHUB_TOKEN not set; connect GitHub OAuth or token to enable live API operations.",
            )
        started = time.perf_counter()
        try:
            user = self._req("GET", "/user", timeout=timeout_seconds)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return IntegrationStatus(
                provider="github",
                configured=True,
                capability_state=HonestCapabilityState.AVAILABLE,
                live_verified=True,
                requires_approval_for_mutations=True,
                endpoint=f"{self.BASE_URL}/user",
                latency_ms=latency_ms,
                detail=f"GitHub API authenticated as '{user.get('login', 'user')}'.",
            )
        except IntegrationError as exc:
            return IntegrationStatus(
                provider="github",
                configured=True,
                capability_state=HonestCapabilityState.DEGRADED,
                live_verified=False,
                requires_approval_for_mutations=True,
                endpoint=f"{self.BASE_URL}/user",
                detail=str(exc),
            )

    def list_repos(self, per_page: int = 30) -> list[dict[str, Any]]:
        return self._req("GET", "/user/repos", params={"per_page": min(100, per_page), "sort": "updated"})

    def get_repo(self, owner_repo: str) -> dict[str, Any]:
        return self._req("GET", f"/repos/{owner_repo}")

    def list_branches(self, owner_repo: str) -> list[dict[str, Any]]:
        return self._req("GET", f"/repos/{owner_repo}/branches")

    def create_branch(self, owner_repo: str, new_branch: str, from_branch: str = "main") -> dict[str, Any]:
        if new_branch.strip().lower() in PROTECTED_BRANCHES:
            raise AuthorizationError(f"Cannot directly target protected branch '{new_branch}'.")
        ref_data = self._req("GET", f"/repos/{owner_repo}/git/ref/heads/{from_branch}")
        sha = ref_data["object"]["sha"]
        return self._req(
            "POST",
            f"/repos/{owner_repo}/git/refs",
            json_body={"ref": f"refs/heads/{new_branch}", "sha": sha},
        )

    def list_commits(self, owner_repo: str, sha: str = "main", per_page: int = 20) -> list[dict[str, Any]]:
        return self._req("GET", f"/repos/{owner_repo}/commits", params={"sha": sha, "per_page": min(100, per_page)})

    def get_file_content(self, owner_repo: str, path: str, ref: str = "main") -> dict[str, Any]:
        data = self._req("GET", f"/repos/{owner_repo}/contents/{path.lstrip('/')}", params={"ref": ref})
        raw = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace") if data.get("content") else ""
        return {"path": data.get("path"), "sha": data.get("sha"), "size": data.get("size"), "content": raw}

    def upsert_file(
        self,
        owner_repo: str,
        *,
        path: str,
        branch: str,
        content: str,
        message: str,
        sha: str | None = None,
    ) -> dict[str, Any]:
        if branch.strip().lower() in PROTECTED_BRANCHES:
            raise AuthorizationError(
                f"Direct file writes to protected branch '{branch}' are blocked. Create a feature branch and Pull Request instead."
            )
        body: dict[str, Any] = {
            "message": message,
            "branch": branch,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        }
        if sha:
            body["sha"] = sha
        return self._req("PUT", f"/repos/{owner_repo}/contents/{path.lstrip('/')}", json_body=body)

    def list_pull_requests(self, owner_repo: str, state: str = "open") -> list[dict[str, Any]]:
        return self._req("GET", f"/repos/{owner_repo}/pulls", params={"state": state})

    def create_pull_request(
        self, owner_repo: str, *, title: str, head: str, base: str = "main", body: str = "", draft: bool = False
    ) -> dict[str, Any]:
        return self._req(
            "POST",
            f"/repos/{owner_repo}/pulls",
            json_body={"title": title, "head": head, "base": base, "body": body, "draft": draft},
        )

    def get_pull_request_files(self, owner_repo: str, pr_number: int) -> list[dict[str, Any]]:
        return self._req("GET", f"/repos/{owner_repo}/pulls/{pr_number}/files")

    def list_issues(self, owner_repo: str, state: str = "open") -> list[dict[str, Any]]:
        return self._req("GET", f"/repos/{owner_repo}/issues", params={"state": state})

    def create_issue(self, owner_repo: str, *, title: str, body: str = "", labels: list[str] | None = None) -> dict[str, Any]:
        return self._req(
            "POST",
            f"/repos/{owner_repo}/issues",
            json_body={"title": title, "body": body, "labels": labels or []},
        )

    def list_workflow_runs(self, owner_repo: str, per_page: int = 10) -> list[dict[str, Any]]:
        data = self._req("GET", f"/repos/{owner_repo}/actions/runs", params={"per_page": min(50, per_page)})
        return data.get("workflow_runs", [])

    def list_releases(self, owner_repo: str) -> list[dict[str, Any]]:
        return self._req("GET", f"/repos/{owner_repo}/releases")

    def create_release(
        self, owner_repo: str, *, tag_name: str, name: str, body: str = "", approval_verified: bool = False
    ) -> dict[str, Any]:
        if not approval_verified:
            raise AuthorizationError("Creating a GitHub release requires explicit ApprovalGate authorization.")
        return self._req(
            "POST",
            f"/repos/{owner_repo}/releases",
            json_body={"tag_name": tag_name, "name": name, "body": body},
        )
