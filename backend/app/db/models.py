"""SQLAlchemy 2.0 ORM models for ULTRON OS 2026 (Supabase PostgreSQL + SQLite WAL)."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Platform & Schema Tracking
# ---------------------------------------------------------------------------
class SchemaMigration(Base):
    __tablename__ = "schema_migrations"

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_keys"

    idempotency_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    response_json: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Identity, Tenancy & Sessions
# ---------------------------------------------------------------------------
class Tenant(Base):
    __tablename__ = "tenants"

    tenant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="OPERATOR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class SessionRecord(Base):
    __tablename__ = "sessions"

    jti: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    refresh_token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    access_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refresh_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Specialist Agents (AGT-01..AGT-60 + Approved Extensions) & Inter-Agent Bus
# ---------------------------------------------------------------------------
class AgentRecord(Base):
    __tablename__ = "agents"

    agent_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    tier: Mapped[str] = mapped_column(String(32), nullable=False, default="CORE_25")
    domain: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    role_description: Mapped[str] = mapped_column(Text, nullable=False)
    system_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    tools_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    permission_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="TIER_2_READ")
    capability_state: Mapped[str] = mapped_column(String(32), nullable=False, default="AVAILABLE")
    default_reasoning_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    is_extension: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    tasks_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_active: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class AgentMessageRecord(Base):
    __tablename__ = "agent_messages"

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    from_agent_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    to_agent_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DELIVERED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# NEON Conversations & Token/Cost Usage Tracking
# ---------------------------------------------------------------------------
class ConversationRecord(Base):
    __tablename__ = "conversations"

    conversation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(32), nullable=False, default="AGT-01")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ConversationMessageRecord(Base):
    __tablename__ = "conversation_messages"

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("conversations.conversation_id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False)  # user | assistant | tool | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str | None] = mapped_column(String(120), nullable=True)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class LLMUsageLog(Base):
    __tablename__ = "llm_usage_logs"
    __table_args__ = (Index("ix_llm_usage_tenant_created", "tenant_id", "created_at"),)

    usage_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(32), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    reasoning_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    execution_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# ARGON Tasks, DAG Steps, Approvals & Background Jobs
# ---------------------------------------------------------------------------
class TaskRecord(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED", index=True)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="LOW")
    financial_amount_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    assigned_agent_id: Mapped[str] = mapped_column(String(32), nullable=False, default="AGT-01")
    reasoning_tier: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_concurrency: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    dag_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    verification_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class TaskStepRecord(Base):
    __tablename__ = "task_steps"

    step_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    task_id: Mapped[str] = mapped_column(String(64), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False, index=True)
    step_number: Mapped[int] = mapped_column(Integer, nullable=False)
    agent_id: Mapped[str] = mapped_column(String(32), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    depends_on_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalRecord(Base):
    __tablename__ = "approvals"

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    task_id: Mapped[str | None] = mapped_column(String(64), ForeignKey("tasks.task_id"), nullable=True, index=True)
    tool_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    resource_ref: Mapped[str | None] = mapped_column(String(120), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    action_type: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="HIGH")
    financial_amount_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    decided_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BackgroundJobRecord(Base):
    __tablename__ = "background_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED", index=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ScheduledJobRecord(Base):
    __tablename__ = "scheduled_jobs"

    schedule_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Multi-Tier Memory, Versioning & User Preferences
# ---------------------------------------------------------------------------
class MemoryRecord(Base):
    __tablename__ = "memories"

    memory_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    owner_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    agent_id: Mapped[str] = mapped_column(String(32), nullable=False, default="AGT-21", index=True)
    memory_type: Mapped[str] = mapped_column(String(32), nullable=False, default="EPISODIC", index=True)
    namespace: Mapped[str] = mapped_column(String(120), nullable=False, default="default", index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    embedding_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    importance_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_memory_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    access_level: Mapped[str] = mapped_column(String(32), nullable=False, default="TENANT")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class UserPreferenceRecord(Base):
    __tablename__ = "user_preferences"
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", "pref_key", name="uq_user_pref"),)

    pref_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    pref_key: Mapped[str] = mapped_column(String(120), nullable=False)
    pref_value_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Governed Tool Executions, Vault & Audit Ledger
# ---------------------------------------------------------------------------
class ToolExecutionRecord(Base):
    __tablename__ = "tool_executions"

    execution_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    tool_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    agent_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    input_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    output_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class VaultSecretRecord(Base):
    __tablename__ = "vault_secrets"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_vault_tenant_name"),)

    secret_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="custom")
    ciphertext_b64: Mapped[str] = mapped_column(Text, nullable=False)
    nonce_b64: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class AuditLogRecord(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_tenant_created", "tenant_id", "created_at"),)

    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    resource: Mapped[str] = mapped_column(String(255), nullable=False)
    outcome: Mapped[str] = mapped_column(String(120), nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Financial Command Center
# ---------------------------------------------------------------------------
class FinancialTransaction(Base):
    __tablename__ = "financial_transactions"
    __table_args__ = (Index("ix_fin_tx_tenant_type", "tenant_id", "entry_type"),)

    tx_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)  # REVENUE | EXPENSE | API_SPEND | HOSTING | PROJECT_COST | OWNER_DISTRIBUTION | RESERVE_ALLOCATION
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(12), nullable=False, default="USD")
    counterparty: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="BUSINESS", index=True)  # PERSONAL | BUSINESS
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RECORDED")  # RECORDED | PENDING_APPROVAL | APPROVED | REJECTED
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FinancialBudget(Base):
    __tablename__ = "financial_budgets"

    budget_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    period: Mapped[str] = mapped_column(String(32), nullable=False, default="MONTHLY")
    limit_usd: Mapped[float] = mapped_column(Float, nullable=False)
    alert_threshold_pct: Mapped[float] = mapped_column(Float, nullable=False, default=80.0)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FinancialInvestment(Base):
    __tablename__ = "financial_investments"

    investment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    asset_name: Mapped[str] = mapped_column(String(160), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(64), nullable=False)
    cost_basis_usd: Mapped[float] = mapped_column(Float, nullable=False)
    current_value_usd: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class FinancialReserve(Base):
    __tablename__ = "financial_reserves"

    reserve_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    currency: Mapped[str] = mapped_column(String(12), nullable=False, default="USD")
    balance_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    target_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    custodian: Mapped[str] = mapped_column(String(120), nullable=False, default="Treasury")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Developer & Coding Infrastructure (Projects, Activity, Deployments)
# ---------------------------------------------------------------------------
class ProjectRecord(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    repo_full_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    default_branch: Mapped[str] = mapped_column(String(80), nullable=False, default="main")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACTIVE")
    budget_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class DevActivityRecord(Base):
    __tablename__ = "dev_activities"

    activity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    activity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DeploymentRequest(Base):
    __tablename__ = "deployment_requests"

    deployment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)  # staging | production
    git_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    previous_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="WAITING_FOR_APPROVAL")
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    requested_by: Mapped[str] = mapped_column(String(120), nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Notifications & System Settings
# ---------------------------------------------------------------------------
class NotificationRecord(Base):
    __tablename__ = "notifications"

    notification_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(24), nullable=False, default="INFO")  # INFO | WARNING | CRITICAL
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="SYSTEM")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SystemSettingRecord(Base):
    __tablename__ = "system_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "setting_key", name="uq_tenant_setting"),)

    setting_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    setting_key: Mapped[str] = mapped_column(String(120), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by: Mapped[str] = mapped_column(String(120), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Unified Integration Connections & OAuth 2.0 PKCE State
# ---------------------------------------------------------------------------
class IntegrationConnectionRecord(Base):
    __tablename__ = "integration_connections"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", name="uq_tenant_provider_conn"),)

    connection_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, default="API_KEY")
    encrypted_credentials_b64: Mapped[str] = mapped_column(Text, nullable=False, default="")
    credentials_nonce_b64: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    scopes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REQUIRES_CONFIGURATION")
    account_label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    connected_by: Mapped[str] = mapped_column(String(120), nullable=False)
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class OAuthStateRecord(Base):
    __tablename__ = "oauth_states"

    state_token: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    code_verifier: Mapped[str] = mapped_column(String(160), nullable=False)
    redirect_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    scopes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Multi-Device Connectivity Mesh (Desktop, Mobile, PWA)
# ---------------------------------------------------------------------------
class DeviceRecord(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    owner_user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)  # windows | macos | ios | ipados | android | pwa
    device_token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    os_version: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    app_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    permissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    authorized_folders_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ONLINE", index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DevicePairingCodeRecord(Base):
    __tablename__ = "device_pairing_codes"

    pairing_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_username: Mapped[str] = mapped_column(String(120), nullable=False)
    code_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    target_platform: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_permissions_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    authorized_folders_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class DeviceTaskRecord(Base):
    __tablename__ = "device_tasks"

    device_task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False, index=True)
    parent_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    requires_user_interaction: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING", index=True)
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# AEGIS — Autonomous Security & Defence Engine
# ---------------------------------------------------------------------------
class SecurityScanRecord(Base):
    __tablename__ = "security_scans"

    scan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    scan_type: Mapped[str] = mapped_column(String(48), nullable=False, default="FULL")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="COMPLETED")
    risk_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 (safe) - 100 (critical)
    findings_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    findings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    checks_run_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    triggered_by: Mapped[str] = mapped_column(String(120), nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SecurityIncidentRecord(Base):
    __tablename__ = "security_incidents"

    incident_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    scan_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM", index=True)  # LOW | MEDIUM | HIGH | CRITICAL
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    details_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="OPEN", index=True)  # OPEN | REMEDIATED | WAITING_FOR_APPROVAL | DISMISSED
    remediation_action: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class FileIntegrityBaselineRecord(Base):
    __tablename__ = "file_integrity_baselines"
    __table_args__ = (UniqueConstraint("tenant_id", "relative_path", name="uq_fim_tenant_path"),)

    baseline_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    relative_path: Mapped[str] = mapped_column(String(500), nullable=False)
    sha256_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# EVOLVE — Controlled Self-Development Engine
# ---------------------------------------------------------------------------
class EvolutionProposalRecord(Base):
    __tablename__ = "evolution_proposals"

    proposal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    capability_gap: Mapped[str] = mapped_column(Text, nullable=False)
    target_module: Mapped[str] = mapped_column(String(200), nullable=False)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    patch_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="IDENTIFIED", index=True)
    # IDENTIFIED | PLANNED | DEVELOPED | TESTED | AEGIS_VERIFIED | WAITING_FOR_APPROVAL | PROMOTED | ROLLED_BACK
    test_results_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    aegis_scan_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rollback_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# SENTINEL — Passkeys / WebAuthn (Face ID Platform Authenticator) & Recovery
# ---------------------------------------------------------------------------
class WebAuthnCredentialRecord(Base):
    __tablename__ = "webauthn_credentials"

    credential_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    device_label: Mapped[str] = mapped_column(String(160), nullable=False)
    public_key_b64: Mapped[str] = mapped_column(Text, nullable=False)
    sign_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transports_json: Mapped[str] = mapped_column(Text, nullable=False, default='["internal"]')
    authenticator_type: Mapped[str] = mapped_column(String(32), nullable=False, default="platform")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class WebAuthnChallengeRecord(Base):
    __tablename__ = "webauthn_challenges"

    challenge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)  # REGISTRATION | AUTHENTICATION | REAUTH
    challenge_b64: Mapped[str] = mapped_column(String(160), nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class RecoveryCodeRecord(Base):
    __tablename__ = "recovery_codes"

    code_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# ORBIT — Authorized Device Location & Geofence Alerts
# ---------------------------------------------------------------------------
class DeviceLocationRecord(Base):
    __tablename__ = "device_locations"

    location_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    accuracy_meters: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    city: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    country: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    label: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


class LocationAlertRecord(Base):
    __tablename__ = "location_alerts"

    alert_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    center_lat: Mapped[float] = mapped_column(Float, nullable=False)
    center_lng: Mapped[float] = mapped_column(Float, nullable=False)
    radius_meters: Mapped[float] = mapped_column(Float, nullable=False, default=500.0)
    trigger_on: Mapped[str] = mapped_column(String(16), nullable=False, default="ENTER")  # ENTER | EXIT
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# ATLAS — Orders, Personal Tasks & World Intelligence / Daily Briefing
# ---------------------------------------------------------------------------
class OrderRecord(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    vendor: Mapped[str] = mapped_column(String(160), nullable=False)
    item_summary: Mapped[str] = mapped_column(Text, nullable=False)
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(12), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PLACED", index=True)
    # PLACED | PROCESSING | SHIPPED | IN_TRANSIT | OUT_FOR_DELIVERY | DELIVERED | DELAYED | RETURNED | CANCELLED
    carrier: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    tracking_number: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    tracking_source: Mapped[str] = mapped_column(String(64), nullable=False, default="USER_RECORDED")
    estimated_delivery: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_method_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    events_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class IntelligenceTopicRecord(Base):
    __tablename__ = "intelligence_topics"
    __table_args__ = (UniqueConstraint("tenant_id", "slug", name="uq_intel_topic_slug"),)

    topic_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    region: Mapped[str] = mapped_column(String(64), nullable=False, default="GLOBAL")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class IntelligenceBriefingRecord(Base):
    __tablename__ = "intelligence_briefings"

    briefing_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    briefing_date: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    topics_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    sections_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    sources_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="READY")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# FINANCE — Tokenized Payment Methods (NEVER stores raw PAN or CVV)
# ---------------------------------------------------------------------------
class PaymentMethodRecord(Base):
    __tablename__ = "payment_methods"

    payment_method_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)  # paystack | flutterwave | stripe | bank_token
    provider_token_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    brand: Mapped[str] = mapped_column(String(24), nullable=False)  # VISA | MASTERCARD | VERVE | AMEX
    last4: Mapped[str] = mapped_column(String(4), nullable=False)
    exp_month: Mapped[int] = mapped_column(Integer, nullable=False)
    exp_year: Mapped[int] = mapped_column(Integer, nullable=False)
    cardholder_label: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    currency: Mapped[str] = mapped_column(String(12), nullable=False, default="NGN")
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="PERSONAL")  # PERSONAL | BUSINESS
    is_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class FinanceCardRecord(Base):
    __tablename__ = "finance_cards"

    card_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    nickname: Mapped[str] = mapped_column(String(120), nullable=False)
    issuer: Mapped[str] = mapped_column(String(120), nullable=False, default="Custom")
    network: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    card_type: Mapped[str] = mapped_column(String(32), nullable=False, default="VIRTUAL")
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="BUSINESS")
    background_style: Mapped[str] = mapped_column(String(64), nullable=False, default="emerald-obsidian")
    accent_color: Mapped[str] = mapped_column(String(24), nullable=False, default="#10b981")
    visual_effect: Mapped[str] = mapped_column(String(32), nullable=False, default="glass")
    image_file_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    image_crop_json: Mapped[str] = mapped_column(Text, nullable=False, default='{"zoom":1,"offsetX":0,"offsetY":0}')
    connection_status: Mapped[str] = mapped_column(String(32), nullable=False, default="DISPLAY_ONLY")
    provider_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_token_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_preferred: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# FILE HUB — Two-Way Secure File Intake, Extraction & Generation
# ---------------------------------------------------------------------------
class FileRecord(Base):
    __tablename__ = "files"

    file_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False, default="application/octet-stream")
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256_hash: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="UPLOAD")  # UPLOAD | GENERATED
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    scan_status: Mapped[str] = mapped_column(String(32), nullable=False, default="CLEAN")  # CLEAN | QUARANTINED | REDACTED
    secrets_redacted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    untrusted_content_tagged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    extracted_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    project_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# FORGE & LIVE PREVIEW — Complete Multi-File Project Generator
# ---------------------------------------------------------------------------
class ForgeProjectRecord(Base):
    __tablename__ = "forge_projects"

    forge_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    template: Mapped[str] = mapped_column(String(64), nullable=False)  # web_app | landing_page | dashboard | fastapi_service | react_vite
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="GENERATED")  # GENERATED | VERIFIED | FAILED
    files_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    preview_html: Mapped[str] = mapped_column(Text, nullable=False, default="")
    build_logs_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    test_results_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    aegis_verdict_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    archive_file_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# BRIDGE — iPhone PWA Share-to-JARVIS Intake
# ---------------------------------------------------------------------------
class SharedItemRecord(Base):
    __tablename__ = "shared_items"

    share_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    source_app: Mapped[str] = mapped_column(String(80), nullable=False, default="ios_share_sheet")
    title: Mapped[str] = mapped_column(String(240), nullable=False, default="")
    url: Mapped[str] = mapped_column(String(1000), nullable=False, default="")
    shared_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    file_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    aegis_url_verdict: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")  # SAFE | BLOCKED | UNVERIFIED
    extracted_metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    conversation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# PULSE — Live Data-Backed Generated Web Pages
# ---------------------------------------------------------------------------
class PulsePageRecord(Base):
    __tablename__ = "pulse_pages"

    page_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    page_type: Mapped[str] = mapped_column(String(48), nullable=False)  # ORDERS | FINANCE | CARAVAN | AGENTS | PROJECTS | RESEARCH | BRIEFING
    data_bindings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    layout_spec_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# CARAVAN — Business Intelligence Analytics (Zero Fabricated Metrics)
# ---------------------------------------------------------------------------
class BusinessAnalyticsEventRecord(Base):
    __tablename__ = "business_analytics_events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    venture: Mapped[str] = mapped_column(String(80), nullable=False, default="CARAVAN", index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)  # SIGNUP | ACTIVE_USER | REVENUE | GRANT_APPLICATION | CONVERSION
    country: Mapped[str] = mapped_column(String(80), nullable=False, default="UNKNOWN")
    city: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    acquisition_source: Mapped[str] = mapped_column(String(80), nullable=False, default="DIRECT")
    amount_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    count_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)


# ---------------------------------------------------------------------------
# CREATIVE STUDIO — Media & Multimodal Production Jobs
# ---------------------------------------------------------------------------
class MediaJobRecord(Base):
    __tablename__ = "media_jobs"

    job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # IMAGE | VIDEO | AUDIO | 3D | PRESENTATION | GRAPHIC
    agent_id: Mapped[str] = mapped_column(String(16), nullable=False, default="AGT-13")
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="gemini-nano-banana-2.1")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")  # COMPLETED | REQUIRES_PROVIDER_CONFIG | FAILED
    output_file_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# ORBIT — Persistent Device Application Launch Permissions
# ---------------------------------------------------------------------------
class DeviceAppPermissionRecord(Base):
    __tablename__ = "device_app_permissions"

    permission_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    device_label: Mapped[str] = mapped_column(String(160), nullable=False, default="This Device")
    app_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    app_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ALWAYS_ALLOW")  # ALWAYS_ALLOW | DENIED | REVOKED
    permission_scope: Mapped[str] = mapped_column(String(64), nullable=False, default="app_launch")
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_launch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_launch_status: Mapped[str | None] = mapped_column(String(48), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class OrbitRegisteredAppRecord(Base):
    __tablename__ = "orbit_registered_apps"

    app_record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    app_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    aliases_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="Custom")
    platforms_json: Mapped[str] = mapped_column(Text, nullable=False, default='["ios","android","windows","macos","linux","web"]')
    ios_scheme: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    universal_link: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    android_package: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    android_intent: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    desktop_app_key: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    web_fallback: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    verification_status: Mapped[str] = mapped_column(String(48), nullable=False, default="MANUAL_REGISTERED")
    last_launch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_launch_status: Mapped[str | None] = mapped_column(String(48), nullable=True)
    last_launch_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class FlutterwaveCheckoutPaymentRecord(Base):
    __tablename__ = "flutterwave_checkout_payments"

    payment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    tx_ref: Mapped[str] = mapped_column(String(120), nullable=False, unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    flw_transaction_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(12), nullable=False, default="NGN")
    payment_options: Mapped[str] = mapped_column(String(120), nullable=False, default="card,banktransfer,ussd")
    customer_email: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_name: Mapped[str] = mapped_column(String(160), nullable=False, default="")
    checkout_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    environment: Mapped[str] = mapped_column(String(16), nullable=False, default="test")
    status: Mapped[str] = mapped_column(String(48), nullable=False, default="INITIATED")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_webhook_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class UniversalConnectorRecord(Base):
    __tablename__ = "universal_connectors"

    connector_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="Custom websites and APIs")
    connection_method: Mapped[str] = mapped_column(String(32), nullable=False, default="API_KEY")
    lifecycle_state: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_CONFIGURED")
    website_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    docs_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    api_base_url: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    required_headers_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    required_scopes_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    capabilities_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    discovered_auth_methods_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    webhook_endpoint_path: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    encrypted_webhook_secret_b64: Mapped[str | None] = mapped_column(Text, nullable=True)
    webhook_secret_nonce_b64: Mapped[str | None] = mapped_column(String(128), nullable=True)
    subscribed_events_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    mcp_config_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    mcp_tools_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class WebhookDeliveryRecord(Base):
    __tablename__ = "universal_webhook_deliveries"

    delivery_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    connector_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ACCEPTED")
    payload_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ConnectorScopeGrantRecord(Base):
    __tablename__ = "connector_scope_grants"

    grant_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    connector_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, default="*")
    project_id: Mapped[str] = mapped_column(String(64), nullable=False, default="*")
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False, default="*")
    allowed_tools_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE")
    granted_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CaravanFundingSourceRecord(Base):
    __tablename__ = "caravan_funding_sources"

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False, default="PUBLIC_PORTAL")
    base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    connector_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verification_policy: Mapped[str] = mapped_column(String(64), nullable=False, default="MANUAL_REVIEW")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE")
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CaravanFundingOpportunityRecord(Base):
    __tablename__ = "caravan_funding_opportunities"

    opportunity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    source_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    provider_org: Mapped[str] = mapped_column(String(180), nullable=False)
    funding_type: Mapped[str] = mapped_column(String(32), nullable=False, default="GRANT")
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    amount_display: Mapped[str] = mapped_column(String(120), nullable=False, default="Not specified by source")
    currency: Mapped[str] = mapped_column(String(16), nullable=False, default="USD")
    eligibility_requirements: Mapped[str] = mapped_column(Text, nullable=False)
    geographic_restrictions: Mapped[str] = mapped_column(String(240), nullable=False, default="Global / See source")
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[str] = mapped_column(String(24), nullable=False, default="UNVERIFIED", index=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    supporting_evidence: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tags_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CaravanCustomerAccountRecord(Base):
    __tablename__ = "caravan_customer_accounts"

    account_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    organization_name: Mapped[str] = mapped_column(String(180), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, default="STARTUP")
    country: Mapped[str] = mapped_column(String(80), nullable=False, default="Nigeria")
    sector: Mapped[str] = mapped_column(String(80), nullable=False, default="Technology")
    stage: Mapped[str] = mapped_column(String(64), nullable=False, default="SEED")
    annual_revenue_band: Mapped[str] = mapped_column(String(64), nullable=False, default="PRE_REVENUE")
    profile_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    onboarding_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CaravanEligibilityAssessmentRecord(Base):
    __tablename__ = "caravan_eligibility_assessments"

    assessment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    verdict: Mapped[str] = mapped_column(String(32), nullable=False, default="INSUFFICIENT_DATA")
    matched_criteria_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    gaps_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    recommendations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    neon_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="DETERMINISTIC")
    assessed_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CaravanApplicationRecord(Base):
    __tablename__ = "caravan_applications"

    application_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    progress_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    checklist_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CaravanSavedOpportunityRecord(Base):
    __tablename__ = "caravan_saved_opportunities"

    saved_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    opportunity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class CaravanSubscriptionRecord(Base):
    __tablename__ = "caravan_subscriptions"

    subscription_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    plan_tier: Mapped[str] = mapped_column(String(32), nullable=False, default="FREE")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE")
    live_payments_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    entitlements_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CaravanSupportTicketRecord(Base):
    __tablename__ = "caravan_support_tickets"

    ticket_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="GENERAL")
    priority: Mapped[str] = mapped_column(String(24), nullable=False, default="NORMAL")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OPEN")
    messages_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    assigned_to: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CaravanNotificationRecord(Base):
    __tablename__ = "caravan_notifications"

    notification_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(64), ForeignKey("tenants.tenant_id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False, default="OPPORTUNITY")
    read: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)




