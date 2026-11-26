-- CARAVAN Phase 7: Production Auth Verification/Reset Tokens, Notification Preferences & Delivery Outbox,
-- Customer Listing Reports, and Persistent Worker Heartbeats.

CREATE TABLE IF NOT EXISTS auth_verification_tokens (
    token_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    user_id VARCHAR(64) NOT NULL REFERENCES users(user_id),
    purpose VARCHAR(32) NOT NULL,
    token_hash VARCHAR(128) NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_auth_verif_token_hash ON auth_verification_tokens (token_hash);
CREATE INDEX IF NOT EXISTS ix_auth_verif_user_purpose ON auth_verification_tokens (user_id, purpose);

CREATE TABLE IF NOT EXISTS caravan_notification_preferences (
    pref_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    account_id VARCHAR(64) NOT NULL,
    in_app_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    email_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    deadline_alerts BOOLEAN NOT NULL DEFAULT TRUE,
    saved_updates BOOLEAN NOT NULL DEFAULT TRUE,
    subscription_alerts BOOLEAN NOT NULL DEFAULT TRUE,
    support_updates BOOLEAN NOT NULL DEFAULT TRUE,
    whatsapp_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    whatsapp_authorized BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_caravan_notif_pref_account ON caravan_notification_preferences (tenant_id, account_id);

CREATE TABLE IF NOT EXISTS caravan_notification_deliveries (
    delivery_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    account_id VARCHAR(64) NOT NULL,
    channel VARCHAR(24) NOT NULL,
    event_type VARCHAR(48) NOT NULL,
    recipient VARCHAR(255) NOT NULL DEFAULT '',
    subject VARCHAR(200) NOT NULL,
    body TEXT NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'QUEUED',
    error_detail TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_caravan_notif_deliv_tenant_status ON caravan_notification_deliveries (tenant_id, status);

CREATE TABLE IF NOT EXISTS caravan_listing_reports (
    report_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    opportunity_id VARCHAR(64) NOT NULL,
    account_id VARCHAR(64) NOT NULL,
    reported_by VARCHAR(120) NOT NULL,
    reason VARCHAR(48) NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    status VARCHAR(24) NOT NULL DEFAULT 'OPEN',
    resolution_note TEXT NOT NULL DEFAULT '',
    reviewed_by VARCHAR(120),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_caravan_reports_tenant_status ON caravan_listing_reports (tenant_id, status);

CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id VARCHAR(80) PRIMARY KEY,
    status VARCHAR(24) NOT NULL DEFAULT 'ALIVE',
    last_poll_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    jobs_processed INTEGER NOT NULL DEFAULT 0,
    jobs_failed INTEGER NOT NULL DEFAULT 0,
    detail TEXT NOT NULL DEFAULT ''
);
