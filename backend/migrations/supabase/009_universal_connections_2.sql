-- ULTRON OS 2026 — Universal Connections Centre 2.0 & Webhook Deliveries with RLS
CREATE TABLE IF NOT EXISTS universal_connectors (
    connector_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    provider_key VARCHAR(64) NOT NULL,
    name VARCHAR(120) NOT NULL,
    category VARCHAR(64) NOT NULL DEFAULT 'Custom websites and APIs',
    connection_method VARCHAR(32) NOT NULL DEFAULT 'API_KEY',
    lifecycle_state VARCHAR(32) NOT NULL DEFAULT 'NOT_CONFIGURED',
    website_url VARCHAR(500) NOT NULL DEFAULT '',
    docs_url VARCHAR(500) NOT NULL DEFAULT '',
    api_base_url VARCHAR(500) NOT NULL DEFAULT '',
    required_headers_json TEXT NOT NULL DEFAULT '{}',
    required_scopes_json TEXT NOT NULL DEFAULT '[]',
    capabilities_json TEXT NOT NULL DEFAULT '[]',
    discovered_auth_methods_json TEXT NOT NULL DEFAULT '[]',
    webhook_endpoint_path VARCHAR(255) NOT NULL DEFAULT '',
    encrypted_webhook_secret_b64 TEXT,
    webhook_secret_nonce_b64 VARCHAR(128),
    subscribed_events_json TEXT NOT NULL DEFAULT '[]',
    approved_by VARCHAR(120),
    last_verified_at TIMESTAMPTZ,
    last_error TEXT,
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_universal_connectors_lookup ON universal_connectors (tenant_id, provider_key);

ALTER TABLE universal_connectors ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_universal_connectors ON universal_connectors;
CREATE POLICY tenant_isolation_universal_connectors ON universal_connectors USING (tenant_id = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS universal_webhook_deliveries (
    delivery_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    connector_id VARCHAR(64) NOT NULL,
    event_type VARCHAR(120) NOT NULL,
    idempotency_key VARCHAR(160) NOT NULL,
    signature_valid BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(32) NOT NULL DEFAULT 'ACCEPTED',
    payload_summary TEXT NOT NULL DEFAULT '',
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_universal_webhook_deliveries_lookup ON universal_webhook_deliveries (tenant_id, connector_id, idempotency_key);

ALTER TABLE universal_webhook_deliveries ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_universal_webhook_deliveries ON universal_webhook_deliveries;
CREATE POLICY tenant_isolation_universal_webhook_deliveries ON universal_webhook_deliveries USING (tenant_id = current_setting('app.tenant_id', true));
