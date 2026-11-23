-- ULTRON OS 2026 — Antigravity-Standard MCP Clients & Per-User/Project/Agent Scope Grants
ALTER TABLE universal_connectors ADD COLUMN IF NOT EXISTS mcp_config_json TEXT NOT NULL DEFAULT '{}';
ALTER TABLE universal_connectors ADD COLUMN IF NOT EXISTS mcp_tools_json TEXT NOT NULL DEFAULT '[]';

CREATE TABLE IF NOT EXISTS connector_scope_grants (
    grant_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    connector_id VARCHAR(64) NOT NULL,
    user_id VARCHAR(64) NOT NULL DEFAULT '*',
    project_id VARCHAR(64) NOT NULL DEFAULT '*',
    agent_id VARCHAR(64) NOT NULL DEFAULT '*',
    allowed_tools_json TEXT NOT NULL DEFAULT '[]',
    status VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
    granted_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_connector_scope_grants_lookup ON connector_scope_grants (tenant_id, connector_id, user_id, project_id, agent_id);

ALTER TABLE connector_scope_grants ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_connector_scope_grants ON connector_scope_grants;
CREATE POLICY tenant_isolation_connector_scope_grants ON connector_scope_grants USING (tenant_id = current_setting('app.tenant_id', true));
