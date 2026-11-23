-- ULTRON OS 2026 — Finance Centre Safe Visual Display Cards & RLS
CREATE TABLE IF NOT EXISTS finance_cards (
    card_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    nickname VARCHAR(120) NOT NULL,
    issuer VARCHAR(120) NOT NULL DEFAULT 'Custom',
    network VARCHAR(32) NOT NULL DEFAULT '',
    card_type VARCHAR(32) NOT NULL DEFAULT 'VIRTUAL',
    scope VARCHAR(16) NOT NULL DEFAULT 'BUSINESS',
    background_style VARCHAR(64) NOT NULL DEFAULT 'emerald-obsidian',
    accent_color VARCHAR(24) NOT NULL DEFAULT '#10b981',
    visual_effect VARCHAR(32) NOT NULL DEFAULT 'glass',
    image_file_id VARCHAR(64),
    image_crop_json TEXT NOT NULL DEFAULT '{"zoom":1,"offsetX":0,"offsetY":0}',
    connection_status VARCHAR(32) NOT NULL DEFAULT 'DISPLAY_ONLY',
    provider_key VARCHAR(64),
    provider_token_ref VARCHAR(160),
    display_order INTEGER NOT NULL DEFAULT 0,
    is_preferred BOOLEAN NOT NULL DEFAULT FALSE,
    last_synced_at TIMESTAMPTZ,
    status VARCHAR(24) NOT NULL DEFAULT 'ACTIVE',
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_finance_cards_tenant ON finance_cards (tenant_id, scope, display_order);

ALTER TABLE finance_cards ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_finance_cards ON finance_cards;
CREATE POLICY tenant_isolation_finance_cards ON finance_cards USING (tenant_id = current_setting('app.tenant_id', true));
