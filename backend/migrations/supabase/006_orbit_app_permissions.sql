-- ULTRON OS 2026 — ORBIT Persistent Device Application Launch Permissions & RLS
CREATE TABLE IF NOT EXISTS device_app_permissions (
    permission_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    user_id VARCHAR(64) NOT NULL,
    device_id VARCHAR(64) NOT NULL,
    device_label VARCHAR(160) NOT NULL DEFAULT 'This Device',
    app_id VARCHAR(64) NOT NULL,
    app_name VARCHAR(120) NOT NULL,
    status VARCHAR(24) NOT NULL DEFAULT 'ALWAYS_ALLOW',
    permission_scope VARCHAR(64) NOT NULL DEFAULT 'app_launch',
    approved_at TIMESTAMPTZ,
    last_launch_at TIMESTAMPTZ,
    last_launch_status VARCHAR(48),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_device_app_perms_lookup ON device_app_permissions (tenant_id, user_id, device_id, app_id);

ALTER TABLE device_app_permissions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_device_app_permissions ON device_app_permissions;
CREATE POLICY tenant_isolation_device_app_permissions ON device_app_permissions USING (tenant_id = current_setting('app.tenant_id', true));
