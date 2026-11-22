-- ULTRON OS 2026 — Supabase / PostgreSQL Migration 004
-- Full-Platform Subsystems: AEGIS, EVOLVE, SENTINEL, ORBIT Location, ATLAS,
-- Tokenized Payment Methods, FILE HUB, FORGE, BRIDGE, PULSE, CARAVAN BI, Creative Studio

ALTER TABLE financial_transactions
    ADD COLUMN IF NOT EXISTS scope VARCHAR(16) NOT NULL DEFAULT 'BUSINESS';
CREATE INDEX IF NOT EXISTS ix_fin_tx_scope ON financial_transactions (tenant_id, scope);

-- AEGIS Autonomous Security
CREATE TABLE IF NOT EXISTS security_scans (
    scan_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    scan_type VARCHAR(48) NOT NULL DEFAULT 'FULL',
    status VARCHAR(32) NOT NULL DEFAULT 'COMPLETED',
    risk_score INTEGER NOT NULL DEFAULT 0,
    findings_count INTEGER NOT NULL DEFAULT 0,
    findings_json TEXT NOT NULL DEFAULT '[]',
    checks_run_json TEXT NOT NULL DEFAULT '[]',
    triggered_by VARCHAR(120) NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_security_scans_tenant ON security_scans (tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS security_incidents (
    incident_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    scan_id VARCHAR(64),
    severity VARCHAR(16) NOT NULL DEFAULT 'MEDIUM',
    category VARCHAR(64) NOT NULL,
    title VARCHAR(240) NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    status VARCHAR(32) NOT NULL DEFAULT 'OPEN',
    remediation_action TEXT NOT NULL DEFAULT '',
    approval_id VARCHAR(64),
    resolved_by VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_security_incidents_tenant_status ON security_incidents (tenant_id, status, severity);

CREATE TABLE IF NOT EXISTS file_integrity_baselines (
    baseline_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    relative_path VARCHAR(500) NOT NULL,
    sha256_hash VARCHAR(128) NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_fim_tenant_path UNIQUE (tenant_id, relative_path)
);

-- EVOLVE Self-Development
CREATE TABLE IF NOT EXISTS evolution_proposals (
    proposal_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    title VARCHAR(240) NOT NULL,
    capability_gap TEXT NOT NULL,
    target_module VARCHAR(200) NOT NULL,
    plan_json TEXT NOT NULL DEFAULT '{}',
    patch_summary TEXT NOT NULL DEFAULT '',
    status VARCHAR(32) NOT NULL DEFAULT 'IDENTIFIED',
    test_results_json TEXT NOT NULL DEFAULT '{}',
    aegis_scan_id VARCHAR(64),
    approval_id VARCHAR(64),
    rollback_reason TEXT,
    proposed_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_evolve_tenant_status ON evolution_proposals (tenant_id, status);

-- SENTINEL WebAuthn / Passkeys & Recovery Codes (Zero raw biometric data)
CREATE TABLE IF NOT EXISTS webauthn_credentials (
    credential_id VARCHAR(255) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    device_label VARCHAR(160) NOT NULL,
    public_key_b64 TEXT NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    transports_json TEXT NOT NULL DEFAULT '["internal"]',
    authenticator_type VARCHAR(32) NOT NULL DEFAULT 'platform',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_webauthn_user ON webauthn_credentials (tenant_id, user_id);

CREATE TABLE IF NOT EXISTS webauthn_challenges (
    challenge_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    user_id VARCHAR(64) NOT NULL,
    purpose VARCHAR(32) NOT NULL,
    challenge_b64 VARCHAR(160) NOT NULL,
    consumed BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS recovery_codes (
    code_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    code_hash VARCHAR(128) NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ORBIT Authorized Device Location & Geofences
CREATE TABLE IF NOT EXISTS device_locations (
    location_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    device_id VARCHAR(64) NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    accuracy_meters DOUBLE PRECISION NOT NULL DEFAULT 0,
    city VARCHAR(120) NOT NULL DEFAULT '',
    country VARCHAR(120) NOT NULL DEFAULT '',
    label VARCHAR(160) NOT NULL DEFAULT '',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_device_locations_device ON device_locations (tenant_id, device_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS location_alerts (
    alert_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    device_id VARCHAR(64) NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    name VARCHAR(160) NOT NULL,
    center_lat DOUBLE PRECISION NOT NULL,
    center_lng DOUBLE PRECISION NOT NULL,
    radius_meters DOUBLE PRECISION NOT NULL DEFAULT 500,
    trigger_on VARCHAR(16) NOT NULL DEFAULT 'ENTER',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_triggered_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ATLAS Orders & World Intelligence
CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    vendor VARCHAR(160) NOT NULL,
    item_summary TEXT NOT NULL,
    amount_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    currency VARCHAR(12) NOT NULL DEFAULT 'USD',
    status VARCHAR(32) NOT NULL DEFAULT 'PLACED',
    carrier VARCHAR(120) NOT NULL DEFAULT '',
    tracking_number VARCHAR(120) NOT NULL DEFAULT '',
    tracking_source VARCHAR(64) NOT NULL DEFAULT 'USER_RECORDED',
    estimated_delivery VARCHAR(64) NOT NULL DEFAULT '',
    approval_id VARCHAR(64),
    payment_method_id VARCHAR(64),
    events_json TEXT NOT NULL DEFAULT '[]',
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_orders_tenant_status ON orders (tenant_id, status);

CREATE TABLE IF NOT EXISTS intelligence_topics (
    topic_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    slug VARCHAR(64) NOT NULL,
    label VARCHAR(120) NOT NULL,
    region VARCHAR(64) NOT NULL DEFAULT 'GLOBAL',
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    priority INTEGER NOT NULL DEFAULT 5,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_intel_topic_slug UNIQUE (tenant_id, slug)
);

CREATE TABLE IF NOT EXISTS intelligence_briefings (
    briefing_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    briefing_date VARCHAR(32) NOT NULL,
    topics_json TEXT NOT NULL DEFAULT '[]',
    sections_json TEXT NOT NULL DEFAULT '[]',
    sources_json TEXT NOT NULL DEFAULT '[]',
    status VARCHAR(32) NOT NULL DEFAULT 'READY',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tokenized Payment Methods (Masked last4 only, never raw PAN or CVV)
CREATE TABLE IF NOT EXISTS payment_methods (
    payment_method_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    provider VARCHAR(64) NOT NULL,
    provider_token_ref VARCHAR(160) NOT NULL,
    brand VARCHAR(24) NOT NULL,
    last4 VARCHAR(4) NOT NULL,
    exp_month INTEGER NOT NULL,
    exp_year INTEGER NOT NULL,
    cardholder_label VARCHAR(160) NOT NULL DEFAULT '',
    currency VARCHAR(12) NOT NULL DEFAULT 'NGN',
    scope VARCHAR(16) NOT NULL DEFAULT 'PERSONAL',
    is_preferred BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_payment_methods_tenant ON payment_methods (tenant_id, scope);

-- FILE HUB
CREATE TABLE IF NOT EXISTS files (
    file_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    filename VARCHAR(255) NOT NULL,
    mime_type VARCHAR(120) NOT NULL DEFAULT 'application/octet-stream',
    size_bytes INTEGER NOT NULL DEFAULT 0,
    sha256_hash VARCHAR(128) NOT NULL,
    direction VARCHAR(16) NOT NULL DEFAULT 'UPLOAD',
    storage_path VARCHAR(500) NOT NULL,
    scan_status VARCHAR(32) NOT NULL DEFAULT 'CLEAN',
    secrets_redacted INTEGER NOT NULL DEFAULT 0,
    untrusted_content_tagged BOOLEAN NOT NULL DEFAULT TRUE,
    extracted_text TEXT NOT NULL DEFAULT '',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    project_id VARCHAR(64),
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_files_tenant ON files (tenant_id, created_at DESC);

-- FORGE & LIVE PREVIEW
CREATE TABLE IF NOT EXISTS forge_projects (
    forge_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    name VARCHAR(160) NOT NULL,
    template VARCHAR(64) NOT NULL,
    prompt TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'GENERATED',
    files_json TEXT NOT NULL DEFAULT '{}',
    preview_html TEXT NOT NULL DEFAULT '',
    build_logs_json TEXT NOT NULL DEFAULT '[]',
    test_results_json TEXT NOT NULL DEFAULT '{}',
    aegis_verdict_json TEXT NOT NULL DEFAULT '{}',
    archive_file_id VARCHAR(64),
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- BRIDGE Share-to-JARVIS
CREATE TABLE IF NOT EXISTS shared_items (
    share_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    source_app VARCHAR(80) NOT NULL DEFAULT 'ios_share_sheet',
    title VARCHAR(240) NOT NULL DEFAULT '',
    url VARCHAR(1000) NOT NULL DEFAULT '',
    shared_text TEXT NOT NULL DEFAULT '',
    file_id VARCHAR(64),
    aegis_url_verdict VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    extracted_metadata_json TEXT NOT NULL DEFAULT '{}',
    conversation_id VARCHAR(64),
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- PULSE Live Data-Backed Pages
CREATE TABLE IF NOT EXISTS pulse_pages (
    page_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    slug VARCHAR(120) NOT NULL,
    title VARCHAR(200) NOT NULL,
    page_type VARCHAR(48) NOT NULL,
    data_bindings_json TEXT NOT NULL DEFAULT '[]',
    layout_spec_json TEXT NOT NULL DEFAULT '{}',
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- CARAVAN Business Intelligence Analytics
CREATE TABLE IF NOT EXISTS business_analytics_events (
    event_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    venture VARCHAR(80) NOT NULL DEFAULT 'CARAVAN',
    event_type VARCHAR(64) NOT NULL,
    country VARCHAR(80) NOT NULL DEFAULT 'UNKNOWN',
    city VARCHAR(120) NOT NULL DEFAULT '',
    acquisition_source VARCHAR(80) NOT NULL DEFAULT 'DIRECT',
    amount_usd DOUBLE PRECISION NOT NULL DEFAULT 0,
    count_value INTEGER NOT NULL DEFAULT 1,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_caravan_events_tenant ON business_analytics_events (tenant_id, venture, event_type);

-- CREATIVE STUDIO Media Jobs
CREATE TABLE IF NOT EXISTS media_jobs (
    job_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    media_type VARCHAR(32) NOT NULL,
    agent_id VARCHAR(16) NOT NULL DEFAULT 'AGT-13',
    prompt TEXT NOT NULL,
    provider VARCHAR(64) NOT NULL DEFAULT 'gemini-nano-banana-2.1',
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    output_file_id VARCHAR(64),
    result_json TEXT NOT NULL DEFAULT '{}',
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Enable Row Level Security on all new tenant-scoped tables
DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY[
        'security_scans', 'security_incidents', 'file_integrity_baselines',
        'evolution_proposals', 'webauthn_credentials', 'webauthn_challenges',
        'recovery_codes', 'device_locations', 'location_alerts', 'orders',
        'intelligence_topics', 'intelligence_briefings', 'payment_methods',
        'files', 'forge_projects', 'shared_items', 'pulse_pages',
        'business_analytics_events', 'media_jobs'
    ] LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', tbl);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation_%I ON %I', tbl, tbl);
        EXECUTE format(
            'CREATE POLICY tenant_isolation_%I ON %I USING (tenant_id = current_setting(''app.tenant_id'', true))',
            tbl, tbl
        );
    END LOOP;
END $$;
