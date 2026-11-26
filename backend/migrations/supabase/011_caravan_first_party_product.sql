-- ULTRON OS 2026 — Caravan First-Party Product Schema with Tenant Isolation & RLS

CREATE TABLE IF NOT EXISTS caravan_funding_sources (
    source_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    name VARCHAR(160) NOT NULL,
    source_type VARCHAR(32) NOT NULL DEFAULT 'PUBLIC_PORTAL',
    base_url VARCHAR(500) NOT NULL,
    connector_id VARCHAR(64),
    verification_policy VARCHAR(64) NOT NULL DEFAULT 'MANUAL_REVIEW',
    status VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
    last_synced_at TIMESTAMPTZ,
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_caravan_funding_sources_tenant ON caravan_funding_sources (tenant_id, status);
ALTER TABLE caravan_funding_sources ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_caravan_funding_sources ON caravan_funding_sources;
CREATE POLICY tenant_isolation_caravan_funding_sources ON caravan_funding_sources USING (tenant_id = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS caravan_funding_opportunities (
    opportunity_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    source_id VARCHAR(64),
    title VARCHAR(240) NOT NULL,
    provider_org VARCHAR(180) NOT NULL,
    funding_type VARCHAR(32) NOT NULL DEFAULT 'GRANT',
    source_url VARCHAR(500) NOT NULL,
    amount_display VARCHAR(120) NOT NULL DEFAULT 'Not specified by source',
    currency VARCHAR(16) NOT NULL DEFAULT 'USD',
    eligibility_requirements TEXT NOT NULL,
    geographic_restrictions VARCHAR(240) NOT NULL DEFAULT 'Global / See source',
    deadline_at TIMESTAMPTZ,
    verification_status VARCHAR(24) NOT NULL DEFAULT 'UNVERIFIED',
    last_verified_at TIMESTAMPTZ,
    verified_by VARCHAR(120),
    supporting_evidence TEXT NOT NULL DEFAULT '',
    tags_json TEXT NOT NULL DEFAULT '[]',
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_caravan_funding_opportunities_lookup ON caravan_funding_opportunities (tenant_id, verification_status, funding_type);
ALTER TABLE caravan_funding_opportunities ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_caravan_funding_opportunities ON caravan_funding_opportunities;
CREATE POLICY tenant_isolation_caravan_funding_opportunities ON caravan_funding_opportunities USING (tenant_id = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS caravan_customer_accounts (
    account_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    user_id VARCHAR(64) NOT NULL,
    organization_name VARCHAR(180) NOT NULL,
    entity_type VARCHAR(64) NOT NULL DEFAULT 'STARTUP',
    country VARCHAR(80) NOT NULL DEFAULT 'Nigeria',
    sector VARCHAR(80) NOT NULL DEFAULT 'Technology',
    stage VARCHAR(64) NOT NULL DEFAULT 'SEED',
    annual_revenue_band VARCHAR(64) NOT NULL DEFAULT 'PRE_REVENUE',
    profile_summary TEXT NOT NULL DEFAULT '',
    onboarding_completed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_caravan_customer_accounts_user ON caravan_customer_accounts (tenant_id, user_id);
ALTER TABLE caravan_customer_accounts ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_caravan_customer_accounts ON caravan_customer_accounts;
CREATE POLICY tenant_isolation_caravan_customer_accounts ON caravan_customer_accounts USING (tenant_id = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS caravan_eligibility_assessments (
    assessment_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    account_id VARCHAR(64) NOT NULL,
    opportunity_id VARCHAR(64) NOT NULL,
    score INTEGER NOT NULL DEFAULT 0,
    verdict VARCHAR(32) NOT NULL DEFAULT 'INSUFFICIENT_DATA',
    matched_criteria_json TEXT NOT NULL DEFAULT '[]',
    gaps_json TEXT NOT NULL DEFAULT '[]',
    recommendations_json TEXT NOT NULL DEFAULT '[]',
    neon_mode VARCHAR(32) NOT NULL DEFAULT 'DETERMINISTIC',
    assessed_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_caravan_assessments_lookup ON caravan_eligibility_assessments (tenant_id, account_id, opportunity_id);
ALTER TABLE caravan_eligibility_assessments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_caravan_eligibility_assessments ON caravan_eligibility_assessments;
CREATE POLICY tenant_isolation_caravan_eligibility_assessments ON caravan_eligibility_assessments USING (tenant_id = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS caravan_applications (
    application_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    account_id VARCHAR(64) NOT NULL,
    opportunity_id VARCHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    progress_pct INTEGER NOT NULL DEFAULT 10,
    checklist_json TEXT NOT NULL DEFAULT '[]',
    notes TEXT NOT NULL DEFAULT '',
    approval_id VARCHAR(64),
    submitted_at TIMESTAMPTZ,
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_caravan_applications_lookup ON caravan_applications (tenant_id, account_id, status);
ALTER TABLE caravan_applications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_caravan_applications ON caravan_applications;
CREATE POLICY tenant_isolation_caravan_applications ON caravan_applications USING (tenant_id = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS caravan_saved_opportunities (
    saved_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    account_id VARCHAR(64) NOT NULL,
    opportunity_id VARCHAR(64) NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_caravan_saved_lookup ON caravan_saved_opportunities (tenant_id, account_id, opportunity_id);
ALTER TABLE caravan_saved_opportunities ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_caravan_saved_opportunities ON caravan_saved_opportunities;
CREATE POLICY tenant_isolation_caravan_saved_opportunities ON caravan_saved_opportunities USING (tenant_id = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS caravan_subscriptions (
    subscription_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    account_id VARCHAR(64) NOT NULL,
    plan_tier VARCHAR(32) NOT NULL DEFAULT 'FREE',
    status VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
    live_payments_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    entitlements_json TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_caravan_subscriptions_account ON caravan_subscriptions (tenant_id, account_id);
ALTER TABLE caravan_subscriptions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_caravan_subscriptions ON caravan_subscriptions;
CREATE POLICY tenant_isolation_caravan_subscriptions ON caravan_subscriptions USING (tenant_id = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS caravan_support_tickets (
    ticket_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    account_id VARCHAR(64) NOT NULL,
    subject VARCHAR(200) NOT NULL,
    category VARCHAR(64) NOT NULL DEFAULT 'GENERAL',
    priority VARCHAR(24) NOT NULL DEFAULT 'NORMAL',
    status VARCHAR(24) NOT NULL DEFAULT 'OPEN',
    messages_json TEXT NOT NULL DEFAULT '[]',
    assigned_to VARCHAR(120),
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_caravan_support_tickets_lookup ON caravan_support_tickets (tenant_id, account_id, status);
ALTER TABLE caravan_support_tickets ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_caravan_support_tickets ON caravan_support_tickets;
CREATE POLICY tenant_isolation_caravan_support_tickets ON caravan_support_tickets USING (tenant_id = current_setting('app.tenant_id', true));

CREATE TABLE IF NOT EXISTS caravan_notifications (
    notification_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    account_id VARCHAR(64) NOT NULL,
    title VARCHAR(180) NOT NULL,
    body TEXT NOT NULL,
    category VARCHAR(32) NOT NULL DEFAULT 'OPPORTUNITY',
    read BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_caravan_notifications_lookup ON caravan_notifications (tenant_id, account_id, read);
ALTER TABLE caravan_notifications ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_caravan_notifications ON caravan_notifications;
CREATE POLICY tenant_isolation_caravan_notifications ON caravan_notifications USING (tenant_id = current_setting('app.tenant_id', true));
