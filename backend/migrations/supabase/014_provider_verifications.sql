-- Provider Verifications: Persisted verification history for Google Gemini & ecosystem providers.
CREATE TABLE IF NOT EXISTS provider_verifications (
    verification_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    provider VARCHAR(64) NOT NULL,
    model VARCHAR(120) NOT NULL,
    test_type VARCHAR(64) NOT NULL DEFAULT 'STANDARD_INFERENCE',
    result VARCHAR(32) NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    prompt_tokens INTEGER,
    completion_tokens INTEGER,
    total_tokens INTEGER,
    response_excerpt VARCHAR(256),
    error_code VARCHAR(64),
    error_message TEXT,
    trace_id VARCHAR(64) NOT NULL,
    environment VARCHAR(32) NOT NULL DEFAULT 'development',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_provider_verifications_tenant_provider ON provider_verifications (tenant_id, provider, created_at);
