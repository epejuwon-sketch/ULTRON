-- ULTRON OS 2026 — ORBIT 2.0 Universal Application Registry & RLS
CREATE TABLE IF NOT EXISTS orbit_registered_apps (
    app_record_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    user_id VARCHAR(64) NOT NULL,
    app_id VARCHAR(64) NOT NULL,
    name VARCHAR(120) NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    category VARCHAR(64) NOT NULL DEFAULT 'Custom',
    platforms_json TEXT NOT NULL DEFAULT '["ios","android","windows","macos","linux","web"]',
    ios_scheme VARCHAR(255) NOT NULL DEFAULT '',
    universal_link VARCHAR(500) NOT NULL DEFAULT '',
    android_package VARCHAR(255) NOT NULL DEFAULT '',
    android_intent VARCHAR(500) NOT NULL DEFAULT '',
    desktop_app_key VARCHAR(120) NOT NULL DEFAULT '',
    web_fallback VARCHAR(500) NOT NULL DEFAULT '',
    verification_status VARCHAR(48) NOT NULL DEFAULT 'MANUAL_REGISTERED',
    last_launch_at TIMESTAMPTZ,
    last_launch_status VARCHAR(48),
    last_launch_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_orbit_registered_apps_lookup ON orbit_registered_apps (tenant_id, user_id, app_id);

ALTER TABLE orbit_registered_apps ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_orbit_registered_apps ON orbit_registered_apps;
CREATE POLICY tenant_isolation_orbit_registered_apps ON orbit_registered_apps USING (tenant_id = current_setting('app.tenant_id', true));
