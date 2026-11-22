-- ==============================================================================
-- ULTRON OS 2026 — Supabase / PostgreSQL Migration 003
-- Unified Integration Connections, OAuth 2.0 PKCE States, & Multi-Device Mesh
-- ==============================================================================

CREATE TABLE IF NOT EXISTS integration_connections (
    connection_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    provider VARCHAR(64) NOT NULL,
    auth_type VARCHAR(32) NOT NULL DEFAULT 'API_KEY',
    encrypted_credentials_b64 TEXT NOT NULL DEFAULT '',
    credentials_nonce_b64 VARCHAR(64) NOT NULL DEFAULT '',
    scopes_json TEXT NOT NULL DEFAULT '[]',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    status VARCHAR(32) NOT NULL DEFAULT 'REQUIRES_CONFIGURATION',
    account_label VARCHAR(200) NOT NULL DEFAULT '',
    token_expires_at TIMESTAMPTZ,
    last_verified_at TIMESTAMPTZ,
    last_error TEXT,
    connected_by VARCHAR(120) NOT NULL,
    disconnected_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_tenant_provider_conn UNIQUE (tenant_id, provider)
);
CREATE INDEX IF NOT EXISTS ix_integration_conn_tenant ON integration_connections(tenant_id, status);

CREATE TABLE IF NOT EXISTS oauth_states (
    state_token VARCHAR(128) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    user_id VARCHAR(64) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    code_verifier VARCHAR(160) NOT NULL,
    redirect_uri VARCHAR(500) NOT NULL,
    scopes_json TEXT NOT NULL DEFAULT '[]',
    consumed BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS devices (
    device_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    owner_user_id VARCHAR(64) NOT NULL,
    name VARCHAR(160) NOT NULL,
    platform VARCHAR(32) NOT NULL,
    device_token_hash VARCHAR(128) UNIQUE NOT NULL,
    os_version VARCHAR(120) NOT NULL DEFAULT '',
    app_version VARCHAR(64) NOT NULL DEFAULT '',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    permissions_json TEXT NOT NULL DEFAULT '{}',
    authorized_folders_json TEXT NOT NULL DEFAULT '[]',
    status VARCHAR(32) NOT NULL DEFAULT 'ONLINE',
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_devices_tenant_status ON devices(tenant_id, status);

CREATE TABLE IF NOT EXISTS device_pairing_codes (
    pairing_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    created_by_user_id VARCHAR(64) NOT NULL,
    created_by_username VARCHAR(120) NOT NULL,
    code_hash VARCHAR(128) UNIQUE NOT NULL,
    target_platform VARCHAR(32) NOT NULL,
    requested_permissions_json TEXT NOT NULL DEFAULT '{}',
    authorized_folders_json TEXT NOT NULL DEFAULT '[]',
    consumed BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS device_tasks (
    device_task_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    device_id VARCHAR(64) NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    parent_task_id VARCHAR(64),
    action VARCHAR(80) NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    requires_user_interaction BOOLEAN NOT NULL DEFAULT TRUE,
    approval_id VARCHAR(64),
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    result_json TEXT NOT NULL DEFAULT '{}',
    error_detail TEXT,
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_device_tasks_device_status ON device_tasks(device_id, status);

ALTER TABLE integration_connections ENABLE ROW LEVEL SECURITY;
ALTER TABLE oauth_states ENABLE ROW LEVEL SECURITY;
ALTER TABLE devices ENABLE ROW LEVEL SECURITY;
ALTER TABLE device_pairing_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE device_tasks ENABLE ROW LEVEL SECURITY;
