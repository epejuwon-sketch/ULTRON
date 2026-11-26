-- ULTRON OS 2026 — Flutterwave Sandbox Hosted Checkout Payments & RLS
CREATE TABLE IF NOT EXISTS flutterwave_checkout_payments (
    payment_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    tx_ref VARCHAR(120) NOT NULL UNIQUE,
    idempotency_key VARCHAR(120) NOT NULL,
    flw_transaction_id VARCHAR(64),
    amount DOUBLE PRECISION NOT NULL,
    currency VARCHAR(12) NOT NULL DEFAULT 'NGN',
    payment_options VARCHAR(120) NOT NULL DEFAULT 'card,banktransfer,ussd',
    customer_email VARCHAR(255) NOT NULL,
    customer_name VARCHAR(160) NOT NULL DEFAULT '',
    checkout_url TEXT NOT NULL DEFAULT '',
    environment VARCHAR(16) NOT NULL DEFAULT 'test',
    status VARCHAR(48) NOT NULL DEFAULT 'INITIATED',
    verified_at TIMESTAMPTZ,
    last_webhook_at TIMESTAMPTZ,
    verification_detail TEXT,
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_flw_checkout_tenant_idem ON flutterwave_checkout_payments (tenant_id, idempotency_key);

ALTER TABLE flutterwave_checkout_payments ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_flutterwave_checkout_payments ON flutterwave_checkout_payments;
CREATE POLICY tenant_isolation_flutterwave_checkout_payments ON flutterwave_checkout_payments USING (tenant_id = current_setting('app.tenant_id', true));
