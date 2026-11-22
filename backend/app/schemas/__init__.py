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
        "VERIFIED_TESTED",
    ]


class AgentInvokeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=16000)
    context: dict[str, Any] | None = None
    reasoning_tier: int | None = Field(default=None, ge=1, le=5)


class RoutePreviewRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=8000)
    financial_amount_usd: float = Field(default=0.0, ge=0.0)
    preferred_agent_id: str | None = None


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
    custom_dag: list[CustomDagStep] | None = None


class TransitionTaskRequest(BaseModel):
    next_state: str = Field(min_length=3, max_length=32)
    error_detail: str | None = None


# --- Approvals ---
class DecideApprovalRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    note: str = Field(default="", max_length=1000)


# --- Memory ---
class StoreMemoryRequest(BaseModel):
    content: str = Field(min_length=1, max_length=16000)
    memory_type: Literal["WORKING", "EPISODIC", "SEMANTIC"] = "EPISODIC"
    namespace: str = Field(default="default", max_length=120)
    agent_id: str = Field(default="AGT-21", max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)
    importance_score: float = Field(default=0.5, ge=0.0, le=1.0)
    ttl_seconds: int | None = Field(default=None, ge=1, le=31536000)


class SearchMemoryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    namespace: str | None = None
    memory_type: Literal["WORKING", "EPISODIC", "SEMANTIC"] | None = None
    agent_id: str | None = None
    limit: int = Field(default=10, ge=1, le=50)


# --- Tools ---
class ExecuteToolRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    agent_id: str | None = Field(default=None, max_length=32)


# --- Vault ---
class StoreSecretRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120, pattern=r"^[A-Za-z0-9_\-\.]+$")
    value: str = Field(min_length=1, max_length=8192)
    provider: str = Field(default="custom", max_length=64)
