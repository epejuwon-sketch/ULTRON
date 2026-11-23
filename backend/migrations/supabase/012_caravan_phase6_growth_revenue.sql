-- CARAVAN Phase 6: Growth, Revenue, CRM, Payment Events, Operating Expenses & Privacy Consent
CREATE TABLE IF NOT EXISTS caravan_payment_events (
    payment_event_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    account_id VARCHAR(64) NOT NULL,
    provider VARCHAR(32) NOT NULL,
    provider_ref VARCHAR(128) NOT NULL,
    event_type VARCHAR(48) NOT NULL,
    amount DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    currency VARCHAR(16) NOT NULL DEFAULT 'USD',
    status VARCHAR(24) NOT NULL DEFAULT 'PENDING',
    sandbox_mode BOOLEAN NOT NULL DEFAULT TRUE,
    signature_verified BOOLEAN NOT NULL DEFAULT FALSE,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_caravan_pay_tenant_prov_ref ON caravan_payment_events (tenant_id, provider, provider_ref);

CREATE TABLE IF NOT EXISTS caravan_operating_expenses (
    expense_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    category VARCHAR(48) NOT NULL,
    description VARCHAR(240) NOT NULL,
    amount DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    currency VARCHAR(16) NOT NULL DEFAULT 'USD',
    recorded_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS caravan_crm_notes (
    note_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    account_id VARCHAR(64) NOT NULL,
    author VARCHAR(120) NOT NULL,
    note TEXT NOT NULL,
    segment_tag VARCHAR(64) NOT NULL DEFAULT 'GENERAL',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS caravan_growth_drafts (
    draft_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    draft_type VARCHAR(32) NOT NULL DEFAULT 'CAMPAIGN',
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    target_segment VARCHAR(64) NOT NULL DEFAULT 'ALL',
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    approval_id VARCHAR(64),
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS caravan_privacy_consents (
    consent_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    account_id VARCHAR(64) NOT NULL,
    analytics_consent BOOLEAN NOT NULL DEFAULT FALSE,
    marketing_consent BOOLEAN NOT NULL DEFAULT FALSE,
    deletion_requested BOOLEAN NOT NULL DEFAULT FALSE,
    deletion_reason TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
