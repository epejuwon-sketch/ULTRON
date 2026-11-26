-- ==============================================================================
-- ULTRON OS 2026 — Supabase / PostgreSQL Migration 002 (Full Backend Finalization)
-- ==============================================================================
-- Adds idempotency, schema migrations, NEON conversations & usage tracking,
-- inter-agent messaging, memory versioning & user preferences, Financial Command
-- Center tables, Developer Projects/Deployments, notifications, settings, and
-- background/scheduled job queues with Row-Level Security (RLS) policies.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(64) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    checksum VARCHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS idempotency_keys (
    idempotency_key VARCHAR(128) NOT NULL,
    tenant_id VARCHAR(64) NOT NULL,
    request_hash VARCHAR(64) NOT NULL,
    status_code INTEGER NOT NULL,
    response_json TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (idempotency_key, tenant_id)
);

-- Extend existing tables idempotently
ALTER TABLE agents ADD COLUMN IF NOT EXISTS manifest_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE agents ADD COLUMN IF NOT EXISTS is_extension BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS approved BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS tasks_failed INTEGER NOT NULL DEFAULT 0;
ALTER TABLE agents ADD COLUMN IF NOT EXISTS total_latency_ms INTEGER NOT NULL DEFAULT 0;

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS project_id VARCHAR(64);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS progress_percent INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS max_retries INTEGER NOT NULL DEFAULT 2;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS retry_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS max_concurrency INTEGER NOT NULL DEFAULT 4;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS verification_json TEXT NOT NULL DEFAULT '{}';

ALTER TABLE task_steps ADD COLUMN IF NOT EXISTS attempt_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE task_steps ADD COLUMN IF NOT EXISTS error_detail TEXT;

ALTER TABLE approvals ADD COLUMN IF NOT EXISTS resource_ref VARCHAR(120);

ALTER TABLE memories ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(64);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS project_id VARCHAR(64);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS parent_memory_id VARCHAR(64);
ALTER TABLE memories ADD COLUMN IF NOT EXISTS is_latest BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS access_level VARCHAR(32) NOT NULL DEFAULT 'TENANT';

CREATE INDEX IF NOT EXISTS ix_memories_project ON memories(tenant_id, project_id);
CREATE INDEX IF NOT EXISTS ix_memories_parent ON memories(parent_memory_id);

-- Inter-Agent Communication Bus
CREATE TABLE IF NOT EXISTS agent_messages (
    message_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    from_agent_id VARCHAR(32) NOT NULL,
    to_agent_id VARCHAR(32) NOT NULL,
    task_id VARCHAR(64),
    subject VARCHAR(200) NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status VARCHAR(32) NOT NULL DEFAULT 'DELIVERED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_agent_messages_to ON agent_messages(tenant_id, to_agent_id);

-- NEON Conversations & LLM Usage/Cost Tracking
CREATE TABLE IF NOT EXISTS conversations (
    conversation_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    user_id VARCHAR(64) NOT NULL,
    agent_id VARCHAR(32) NOT NULL DEFAULT 'AGT-01',
    title VARCHAR(200) NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    message_id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL,
    content TEXT NOT NULL,
    model VARCHAR(120),
    token_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_conv_msgs_conv ON conversation_messages(conversation_id, created_at);

CREATE TABLE IF NOT EXISTS llm_usage_logs (
    usage_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    actor VARCHAR(120) NOT NULL,
    agent_id VARCHAR(32) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(120) NOT NULL,
    reasoning_tier INTEGER NOT NULL DEFAULT 2,
    execution_mode VARCHAR(64) NOT NULL,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    estimated_cost_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_llm_usage_tenant_created ON llm_usage_logs(tenant_id, created_at);

-- Background & Scheduled Jobs (persistent worker queue)
CREATE TABLE IF NOT EXISTS background_jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    job_type VARCHAR(64) NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    status VARCHAR(32) NOT NULL DEFAULT 'QUEUED',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 3,
    result_json TEXT NOT NULL DEFAULT '{}',
    error_detail TEXT,
    scheduled_for TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_bg_jobs_status ON background_jobs(status, scheduled_for);

CREATE TABLE IF NOT EXISTS scheduled_jobs (
    schedule_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    name VARCHAR(160) NOT NULL,
    job_type VARCHAR(64) NOT NULL,
    interval_seconds INTEGER NOT NULL DEFAULT 3600,
    payload_json TEXT NOT NULL DEFAULT '{}',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    last_run_at TIMESTAMPTZ,
    next_run_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- User Preferences
CREATE TABLE IF NOT EXISTS user_preferences (
    pref_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    pref_key VARCHAR(120) NOT NULL,
    pref_value_json TEXT NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_user_pref UNIQUE (tenant_id, user_id, pref_key)
);

-- Financial Command Center
CREATE TABLE IF NOT EXISTS financial_transactions (
    tx_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    project_id VARCHAR(64),
    entry_type VARCHAR(32) NOT NULL,
    category VARCHAR(80) NOT NULL,
    amount_usd DOUBLE PRECISION NOT NULL,
    currency VARCHAR(12) NOT NULL DEFAULT 'USD',
    counterparty VARCHAR(160) NOT NULL DEFAULT '',
    description TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'RECORDED',
    approval_id VARCHAR(64),
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_fin_tx_tenant_type ON financial_transactions(tenant_id, entry_type);

CREATE TABLE IF NOT EXISTS financial_budgets (
    budget_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    name VARCHAR(160) NOT NULL,
    category VARCHAR(80) NOT NULL,
    period VARCHAR(32) NOT NULL DEFAULT 'MONTHLY',
    limit_usd DOUBLE PRECISION NOT NULL,
    alert_threshold_pct DOUBLE PRECISION NOT NULL DEFAULT 80.0,
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_investments (
    investment_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    asset_name VARCHAR(160) NOT NULL,
    asset_class VARCHAR(64) NOT NULL,
    cost_basis_usd DOUBLE PRECISION NOT NULL,
    current_value_usd DOUBLE PRECISION NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_by VARCHAR(120) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS financial_reserves (
    reserve_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    name VARCHAR(160) NOT NULL,
    currency VARCHAR(12) NOT NULL DEFAULT 'USD',
    balance_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    target_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    custodian VARCHAR(120) NOT NULL DEFAULT 'Treasury',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Developer & Coding Infrastructure
CREATE TABLE IF NOT EXISTS projects (
    project_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    name VARCHAR(160) NOT NULL,
    slug VARCHAR(120) NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    repo_full_name VARCHAR(200) NOT NULL DEFAULT '',
    default_branch VARCHAR(80) NOT NULL DEFAULT 'main',
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    budget_usd DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dev_activities (
    activity_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    actor VARCHAR(120) NOT NULL,
    activity_type VARCHAR(64) NOT NULL,
    summary TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deployment_requests (
    deployment_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    project_id VARCHAR(64) NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    environment VARCHAR(32) NOT NULL,
    git_ref VARCHAR(160) NOT NULL,
    previous_ref VARCHAR(160),
    status VARCHAR(32) NOT NULL DEFAULT 'WAITING_FOR_APPROVAL',
    approval_id VARCHAR(64),
    requested_by VARCHAR(120) NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Notifications & System Settings
CREATE TABLE IF NOT EXISTS notifications (
    notification_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    user_id VARCHAR(64),
    severity VARCHAR(24) NOT NULL DEFAULT 'INFO',
    category VARCHAR(64) NOT NULL DEFAULT 'SYSTEM',
    title VARCHAR(200) NOT NULL,
    message TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_notifications_tenant_read ON notifications(tenant_id, read);

CREATE TABLE IF NOT EXISTS system_settings (
    setting_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    setting_key VARCHAR(120) NOT NULL,
    value_json TEXT NOT NULL,
    updated_by VARCHAR(120) NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_setting UNIQUE (tenant_id, setting_key)
);

-- Enable Row-Level Security on all new tenant-owned tables
ALTER TABLE idempotency_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE llm_usage_logs ENABLE ROW LEVEL SECURITY;
ALTER TABLE background_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE scheduled_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_investments ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_reserves ENABLE ROW LEVEL SECURITY;
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;
ALTER TABLE dev_activities ENABLE ROW LEVEL SECURITY;
ALTER TABLE deployment_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE system_settings ENABLE ROW LEVEL SECURITY;
