"""Pydantic v2 request and response schemas for ULTRON OS 2026."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.core.permissions import Role


# --- Auth ---
class BootstrapOwnerRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=64)
    organization_name: str | None = Field(default=None, max_length=160)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=64)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class CreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=8, max_length=128)
    role: Role = Role.OPERATOR


# --- Agents & NEON ---
class UpdateAgentStateRequest(BaseModel):
    capability_state: Literal[
        "REGISTERED",
        "DEFINED_NOT_INSTALLED",
        "INSTALLED",
        "AVAILABLE",
        "UNAVAILABLE",
        "DEGRADED",
        "REQUIRES_APPROVAL",
        "VERIFIED_TESTED",
    ]


class AgentInvokeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16000)
    context: dict[str, Any] | None = None
    reasoning_tier: int | None = Field(default=None, ge=1, le=5)
    response_format: Literal["text", "json"] = "text"
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class RoutePreviewRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=8000)
    financial_amount_usd: float = Field(default=0.0, ge=0.0)
    preferred_agent_id: str | None = None


class AgentMessageRequest(BaseModel):
    from_agent_id: str = Field(min_length=3, max_length=32)
    to_agent_id: str = Field(min_length=3, max_length=32)
    subject: str = Field(min_length=1, max_length=200)
    payload: dict[str, Any] = Field(default_factory=dict)
    task_id: str | None = None


class RegisterAgentExtensionRequest(BaseModel):
    agent_id: str = Field(min_length=4, max_length=32, pattern=r"^[A-Za-z0-9\-_]+$")
    name: str = Field(min_length=2, max_length=160)
    domain: str = Field(min_length=2, max_length=120)
    role_description: str = Field(min_length=5, max_length=1000)
    tools: list[str] = Field(default_factory=list)
    permission_scope: str = Field(default="TIER_2_READ", max_length=64)
    default_reasoning_tier: int = Field(default=2, ge=1, le=5)


class NeonCompleteRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16000)
    agent_id: str | None = Field(default=None, max_length=32)
    reasoning_tier: int | None = Field(default=None, ge=1, le=5)
    response_format: Literal["text", "json"] = "text"
    context: dict[str, Any] | None = None
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1024, ge=32, le=8192)
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    file_ids: list[str] = Field(default_factory=list, max_length=8)
    enable_web_research: bool = True
    conversation_id: str | None = Field(default=None, max_length=64)


class CreateConversationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    agent_id: str = Field(default="AGT-01", max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SendConversationMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=16000)
    reasoning_tier: int | None = Field(default=None, ge=1, le=5)
    file_ids: list[str] = Field(default_factory=list, max_length=8)
    enable_web_research: bool = True


# --- Tasks & ARGON ---
class CustomDagStep(BaseModel):
    step_number: int = Field(ge=1)
    agent_id: str = Field(min_length=3, max_length=32)
    description: str = Field(min_length=1, max_length=2000)
    depends_on: list[int] = Field(default_factory=list)


class CreateTaskRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    objective: str = Field(min_length=1, max_length=8000)
    financial_amount_usd: float = Field(default=0.0, ge=0.0)
    preferred_agent_id: str | None = None
    project_id: str | None = None
    custom_dag: list[CustomDagStep] | None = None
    max_retries: int = Field(default=2, ge=0, le=5)
    max_concurrency: int = Field(default=4, ge=1, le=16)


class TransitionTaskRequest(BaseModel):
    next_state: str = Field(min_length=3, max_length=32)
    error_detail: str | None = None


class EnqueueJobRequest(BaseModel):
    job_type: str = Field(min_length=2, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)
    max_attempts: int = Field(default=3, ge=1, le=10)
    delay_seconds: int = Field(default=0, ge=0, le=86400)


class CreateScheduleRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    job_type: str = Field(min_length=2, max_length=64)
    interval_seconds: int = Field(default=3600, ge=60, le=2592000)
    payload: dict[str, Any] = Field(default_factory=dict)


# --- Approvals ---
class DecideApprovalRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    note: str = Field(default="", max_length=1000)


# --- Memory ---
MemoryTypeLiteral = Literal[
    "WORKING", "SHORT_TERM", "LONG_TERM", "EPISODIC", "SEMANTIC", "PROJECT", "USER_PREFERENCE"
]


class StoreMemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=16000)
    memory_type: MemoryTypeLiteral = "EPISODIC"
    namespace: str = Field(default="default", max_length=120)
    agent_id: str = Field(default="AGT-21", max_length=32)
    project_id: str | None = None
    access_level: Literal["TENANT", "PRIVATE"] = "TENANT"
    metadata: dict[str, Any] = Field(default_factory=dict)
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    ttl_seconds: int | None = Field(default=None, ge=1, le=31536000)


class UpdateMemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=16000)
    importance_score: float | None = Field(default=None, ge=0.0, le=1.0)


class SearchMemoryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    namespace: str | None = None
    memory_type: MemoryTypeLiteral | None = None
    agent_id: str | None = None
    project_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


class SetPreferenceRequest(BaseModel):
    key: str = Field(min_length=1, max_length=120)
    value: Any


# --- Tools ---
class ExecuteToolRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = Field(default=None, max_length=32)


# --- Vault ---
class StoreSecretRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120, pattern=r"^[A-Za-z0-9_\-\.]+$")
    value: str = Field(min_length=1, max_length=8192)
    provider: str = Field(default="custom", max_length=64)


# --- Financial Command Center ---
class RecordTransactionRequest(BaseModel):
    entry_type: Literal[
        "REVENUE",
        "EXPENSE",
        "API_SPEND",
        "HOSTING",
        "PROJECT_COST",
        "OWNER_DISTRIBUTION",
        "RESERVE_ALLOCATION",
    ]
    category: str = Field(min_length=1, max_length=80)
    amount_usd: float = Field(gt=0.0)
    description: str = Field(min_length=1, max_length=1000)
    currency: str = Field(default="USD", max_length=12)
    counterparty: str = Field(default="", max_length=160)
    project_id: str | None = None
    scope: Literal["PERSONAL", "BUSINESS"] = "BUSINESS"


class CreatePaymentMethodRequest(BaseModel):
    provider: Literal["paystack", "uba_verve", "stripe", "bank_token"]
    provider_token_ref: str = Field(min_length=6, max_length=160)
    brand: Literal["VISA", "MASTERCARD", "VERVE", "AMEX"]
    last4: str = Field(min_length=4, max_length=4, pattern=r"^\d{4}$")
    exp_month: int = Field(ge=1, le=12)
    exp_year: int = Field(ge=2025, le=2050)
    cardholder_label: str = Field(default="", max_length=160)
    currency: str = Field(default="NGN", max_length=12)
    scope: Literal["PERSONAL", "BUSINESS"] = "PERSONAL"
    is_preferred: bool = False


class CreateBudgetRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=1, max_length=80)
    limit_usd: float = Field(gt=0.0)
    period: Literal["WEEKLY", "MONTHLY", "QUARTERLY", "ANNUAL"] = "MONTHLY"
    alert_threshold_pct: float = Field(default=80.0, ge=1.0, le=100.0)


class RecordInvestmentRequest(BaseModel):
    asset_name: str = Field(min_length=2, max_length=160)
    asset_class: str = Field(min_length=2, max_length=64)
    cost_basis_usd: float = Field(ge=0.0)
    current_value_usd: float = Field(ge=0.0)
    notes: str = Field(default="", max_length=1000)


class RecordReserveRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    balance_usd: float = Field(ge=0.0)
    target_usd: float = Field(default=0.0, ge=0.0)
    currency: str = Field(default="USD", max_length=12)
    custodian: str = Field(default="Treasury", max_length=120)


# --- Developer & Projects ---
class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str = Field(default="", max_length=2000)
    repo_full_name: str = Field(default="", max_length=200)
    default_branch: str = Field(default="main", max_length=80)
    budget_usd: float = Field(default=0.0, ge=0.0)


class UpdateProjectRequest(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    repo_full_name: str | None = Field(default=None, max_length=200)
    default_branch: str | None = Field(default=None, max_length=80)
    status: Literal["ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED"] | None = None
    budget_usd: float | None = Field(default=None, ge=0.0)


class AnalyzeCodeRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    source_code: str = Field(min_length=1, max_length=200000)


class ProposeCodeChangeRequest(BaseModel):
    specification: str = Field(min_length=5, max_length=8000)
    target_branch: str = Field(min_length=1, max_length=120)


class RequestDeploymentRequest(BaseModel):
    environment: Literal["staging", "production"]
    git_ref: str = Field(min_length=1, max_length=160)
    previous_ref: str | None = Field(default=None, max_length=160)
    notes: str = Field(default="", max_length=1000)


class RollbackDeploymentRequest(BaseModel):
    reason: str = Field(default="", max_length=500)


# --- System Settings ---
class UpdateSettingRequest(BaseModel):
    key: str = Field(min_length=2, max_length=120)
    value: Any
