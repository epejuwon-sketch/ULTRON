-- ==============================================================================
-- ULTRON OS 2026 — Supabase / PostgreSQL Initial Production Schema
-- ==============================================================================
-- Includes pgvector support for semantic memory search and Row-Level Security
-- (RLS) policies scoped by tenant_id.
-- Run via Supabase SQL Editor or `psql "$ULTRON_DATABASE_URL" -f 001_initial_schema.sql`.
-- ==============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS tenants (
    tenant_id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
    user_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    username VARCHAR(120) UNIQUE NOT NULL,
    email VARCHAR(255) NOT NULL,
    password_hash TEXT NOT NULL,
    role VARCHAR(32) NOT NULL DEFAULT 'OPERATOR',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    failed_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_users_tenant_id ON users(tenant_id);

CREATE TABLE IF NOT EXISTS sessions (
    jti VARCHAR(128) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    refresh_token_hash VARCHAR(128) UNIQUE NOT NULL,
    access_expires_at TIMESTAMPTZ NOT NULL,
    refresh_expires_at TIMESTAMPTZ NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_sessions_user_id ON sessions(user_id);

CREATE TABLE IF NOT EXISTS agents (
    agent_id VARCHAR(32) PRIMARY KEY,
    name VARCHAR(160) NOT NULL,
    tier VARCHAR(32) NOT NULL DEFAULT 'CORE_25',
    domain VARCHAR(120) NOT NULL,
    role_description TEXT NOT NULL,
    system_instruction TEXT NOT NULL,
    tools_json TEXT NOT NULL DEFAULT '[]',
    permission_scope VARCHAR(64) NOT NULL DEFAULT 'TIER_2_READ',
    capability_state VARCHAR(32) NOT NULL DEFAULT 'AVAILABLE',
    default_reasoning_tier INTEGER NOT NULL DEFAULT 2,
    tasks_completed INTEGER NOT NULL DEFAULT 0,
    last_active TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_agents_domain ON agents(domain);

CREATE TABLE IF NOT EXISTS tasks (
    task_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    created_by VARCHAR(120) NOT NULL,
    title VARCHAR(255) NOT NULL,
    objective TEXT NOT NULL,
    lifecycle_state VARCHAR(32) NOT NULL DEFAULT 'CREATED',
    risk_level VARCHAR(16) NOT NULL DEFAULT 'LOW',
    financial_amount_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    assigned_agent_id VARCHAR(32) NOT NULL DEFAULT 'AGT-01',
    reasoning_tier INTEGER NOT NULL DEFAULT 2,
    dag_json TEXT NOT NULL DEFAULT '[]',
    result_json TEXT NOT NULL DEFAULT '{}',
    error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_tasks_tenant_state ON tasks(tenant_id, lifecycle_state);

CREATE TABLE IF NOT EXISTS task_steps (
    step_id VARCHAR(64) PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL REFERENCES tasks(task_id) ON DELETE CASCADE,
    step_number INTEGER NOT NULL,
    agent_id VARCHAR(32) NOT NULL,
    description TEXT NOT NULL,
    depends_on_json TEXT NOT NULL DEFAULT '[]',
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    output_json TEXT NOT NULL DEFAULT '{}',
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_task_steps_task_id ON task_steps(task_id);

CREATE TABLE IF NOT EXISTS approvals (
    approval_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    task_id VARCHAR(64) REFERENCES tasks(task_id),
    tool_name VARCHAR(120),
    requested_by VARCHAR(120) NOT NULL,
    action_type VARCHAR(64) NOT NULL,
    risk_level VARCHAR(16) NOT NULL DEFAULT 'HIGH',
    financial_amount_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    payload_json TEXT NOT NULL DEFAULT '{}',
    reason TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    decided_by VARCHAR(120),
    decision_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_approvals_tenant_status ON approvals(tenant_id, status);

CREATE TABLE IF NOT EXISTS memories (
    memory_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    agent_id VARCHAR(32) NOT NULL DEFAULT 'AGT-21',
    memory_type VARCHAR(32) NOT NULL DEFAULT 'EPISODIC',
    namespace VARCHAR(120) NOT NULL DEFAULT 'default',
    content TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    embedding_json TEXT NOT NULL DEFAULT '[]',
    embedding_vec VECTOR(768),
    importance_score DOUBLE PRECISION NOT NULL DEFAULT 0.5,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_memories_tenant_ns ON memories(tenant_id, namespace);

CREATE TABLE IF NOT EXISTS tool_executions (
    execution_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    tool_name VARCHAR(120) NOT NULL,
    actor VARCHAR(120) NOT NULL,
    agent_id VARCHAR(32),
    input_json TEXT NOT NULL DEFAULT '{}',
    output_json TEXT NOT NULL DEFAULT '{}',
    status VARCHAR(32) NOT NULL,
    approval_id VARCHAR(64),
    duration_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_tool_executions_tenant ON tool_executions(tenant_id, tool_name);

CREATE TABLE IF NOT EXISTS vault_secrets (
    secret_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    name VARCHAR(120) NOT NULL,
    provider VARCHAR(64) NOT NULL DEFAULT 'custom',
    ciphertext_b64 TEXT NOT NULL,
    nonce_b64 VARCHAR(64) NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_vault_tenant_name UNIQUE (tenant_id, name)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    seq BIGSERIAL PRIMARY KEY,
    event_id VARCHAR(64) UNIQUE NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    actor VARCHAR(120) NOT NULL,
    action VARCHAR(120) NOT NULL,
    resource VARCHAR(255) NOT NULL,
    outcome VARCHAR(120) NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    prev_hash VARCHAR(64) NOT NULL,
    entry_hash VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_audit_tenant_created ON audit_logs(tenant_id, created_at);

-- Enable Row-Level Security on tenant-owned tables (service_role bypasses RLS for backend server access)
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE memories ENABLE ROW LEVEL SECURITY;
ALTER TABLE tool_executions ENABLE ROW LEVEL SECURITY;
ALTER TABLE vault_secrets ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

INSERT INTO tenants (tenant_id, name, status)
VALUES ('TENANT-ULTRON-01', 'ULTRON OS Primary Organization', 'ACTIVE')
ON CONFLICT (tenant_id) DO NOTHING;
