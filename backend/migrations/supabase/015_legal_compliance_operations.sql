-- ULTRON OS 2026: Migration 015 - Legal & Compliance Operations Department
-- Tables for Nigerian CAC, NDPC, Tax, Statutory Policies, Officers & PSC, Regulatory Calendar, and Document Vault

CREATE TABLE IF NOT EXISTS legal_entity_drafts (
    draft_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    company_name VARCHAR(200) NOT NULL DEFAULT 'CARAVAN FUNDING INTELLIGENCE LTD',
    alternative_names_json TEXT NOT NULL DEFAULT '["CARAVAN VENTURES AFRICA LTD", "AURELIA FUNDING INTELLIGENCE LTD"]',
    entity_type VARCHAR(48) NOT NULL DEFAULT 'PRIVATE_COMPANY_LIMITED_BY_SHARES',
    nominal_share_capital FLOAT NOT NULL DEFAULT 1000000.0,
    share_nominal_value FLOAT NOT NULL DEFAULT 1.0,
    currency VARCHAR(8) NOT NULL DEFAULT 'NGN',
    objects_clause_json TEXT NOT NULL DEFAULT '[]',
    registered_office_address VARCHAR(300) NOT NULL DEFAULT '12 Adeola Odeku Street, Victoria Island, Lagos, Nigeria',
    head_office_address VARCHAR(300) NOT NULL DEFAULT '12 Adeola Odeku Street, Victoria Island, Lagos, Nigeria',
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    cac_availability_code VARCHAR(64),
    cac_registration_number VARCHAR(64),
    tax_identification_number VARCHAR(64),
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_legal_entity_drafts_tenant ON legal_entity_drafts (tenant_id);

CREATE TABLE IF NOT EXISTS legal_officers (
    officer_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    draft_id VARCHAR(64) NOT NULL,
    officer_type VARCHAR(32) NOT NULL DEFAULT 'DIRECTOR',
    full_legal_name VARCHAR(200) NOT NULL,
    date_of_birth VARCHAR(32) NOT NULL,
    is_under_18 BOOLEAN NOT NULL DEFAULT FALSE,
    guardian_officer_id VARCHAR(64),
    nationality VARCHAR(64) NOT NULL DEFAULT 'Nigerian',
    residential_address VARCHAR(300) NOT NULL,
    email VARCHAR(120) NOT NULL,
    phone VARCHAR(32) NOT NULL,
    identity_type VARCHAR(32) NOT NULL DEFAULT 'NIN',
    identity_number_masked VARCHAR(32) NOT NULL,
    identity_verified BOOLEAN NOT NULL DEFAULT FALSE,
    shares_allocated INTEGER NOT NULL DEFAULT 0,
    equity_percentage FLOAT NOT NULL DEFAULT 0.0,
    voting_percentage FLOAT NOT NULL DEFAULT 0.0,
    has_significant_control BOOLEAN NOT NULL DEFAULT FALSE,
    professional_accreditation_number VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_legal_officers_tenant_draft ON legal_officers (tenant_id, draft_id);

CREATE TABLE IF NOT EXISTS legal_statutory_policies (
    policy_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    policy_type VARCHAR(48) NOT NULL,
    title VARCHAR(200) NOT NULL,
    version VARCHAR(16) NOT NULL DEFAULT '1.0.0',
    content_markdown TEXT NOT NULL,
    statutory_references_json TEXT NOT NULL DEFAULT '[]',
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    approval_id VARCHAR(64),
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_legal_policies_tenant_type ON legal_statutory_policies (tenant_id, policy_type);

CREATE TABLE IF NOT EXISTS legal_compliance_calendar_events (
    event_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    authority VARCHAR(32) NOT NULL,
    title VARCHAR(200) NOT NULL,
    statutory_deadline VARCHAR(64) NOT NULL,
    due_date TIMESTAMPTZ NOT NULL,
    recurrence VARCHAR(32) NOT NULL DEFAULT 'ANNUAL',
    status VARCHAR(32) NOT NULL DEFAULT 'UPCOMING',
    filing_fee_ngn FLOAT NOT NULL DEFAULT 0.0,
    penalty_risk_description VARCHAR(300) NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_legal_calendar_tenant_due ON legal_compliance_calendar_events (tenant_id, due_date);

CREATE TABLE IF NOT EXISTS legal_filing_workflows (
    workflow_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    filing_type VARCHAR(64) NOT NULL,
    target_authority VARCHAR(32) NOT NULL DEFAULT 'CAC',
    status VARCHAR(48) NOT NULL DEFAULT 'DRAFT',
    requires_professional BOOLEAN NOT NULL DEFAULT FALSE,
    professional_category VARCHAR(64) NOT NULL DEFAULT 'NONE',
    professional_status VARCHAR(32) NOT NULL DEFAULT 'NOT_REQUIRED',
    government_reference VARCHAR(128) NOT NULL DEFAULT '',
    remita_rrr VARCHAR(64) NOT NULL DEFAULT '',
    payment_status VARCHAR(32) NOT NULL DEFAULT 'UNPAID',
    payment_amount_ngn FLOAT NOT NULL DEFAULT 0.0,
    approval_id VARCHAR(64),
    queries_json TEXT NOT NULL DEFAULT '[]',
    submitted_at TIMESTAMPTZ,
    approved_at TIMESTAMPTZ,
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_legal_workflows_tenant_status ON legal_filing_workflows (tenant_id, status);

CREATE TABLE IF NOT EXISTS legal_archived_documents (
    archive_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    workflow_id VARCHAR(64),
    document_category VARCHAR(64) NOT NULL,
    title VARCHAR(200) NOT NULL,
    authority_issued VARCHAR(32) NOT NULL DEFAULT 'CAC',
    file_path VARCHAR(300) NOT NULL,
    sha256_checksum VARCHAR(64) NOT NULL,
    is_verified_authentic BOOLEAN NOT NULL DEFAULT TRUE,
    uploaded_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_legal_archives_tenant_cat ON legal_archived_documents (tenant_id, document_category);

CREATE TABLE IF NOT EXISTS legal_pre_registration_questionnaires (
    questionnaire_id VARCHAR(64) PRIMARY KEY,
    tenant_id VARCHAR(64) NOT NULL REFERENCES tenants(tenant_id),
    draft_id VARCHAR(64) NOT NULL,
    company_type VARCHAR(48) NOT NULL DEFAULT 'PRIVATE_COMPANY_LIMITED_BY_SHARES',
    proposed_name VARCHAR(200) NOT NULL,
    alternative_names_json TEXT NOT NULL DEFAULT '[]',
    business_activities TEXT NOT NULL,
    principal_objects_json TEXT NOT NULL DEFAULT '[]',
    issued_share_capital FLOAT NOT NULL DEFAULT 100000.0,
    nominal_value_per_share FLOAT NOT NULL DEFAULT 1.0,
    registered_office_address VARCHAR(300) NOT NULL,
    registered_office_state VARCHAR(64) NOT NULL DEFAULT 'Lagos',
    registered_office_lga VARCHAR(64) NOT NULL DEFAULT 'Eti-Osa',
    shareholders_json TEXT NOT NULL DEFAULT '[]',
    capacity_safeguards_json TEXT NOT NULL DEFAULT '{}',
    fee_breakdown_json TEXT NOT NULL DEFAULT '{}',
    status VARCHAR(32) NOT NULL DEFAULT 'DRAFT',
    created_by VARCHAR(120) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_legal_pre_reg_tenant ON legal_pre_registration_questionnaires (tenant_id);
CREATE INDEX IF NOT EXISTS ix_legal_pre_reg_draft ON legal_pre_registration_questionnaires (draft_id);
CREATE INDEX IF NOT EXISTS ix_legal_pre_reg_status ON legal_pre_registration_questionnaires (status);

ALTER TABLE legal_entity_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_officers ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_statutory_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_compliance_calendar_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_filing_workflows ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_archived_documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE legal_pre_registration_questionnaires ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation_legal_entity_drafts ON legal_entity_drafts
    USING (tenant_id = current_setting('app.current_tenant_id', true));
CREATE POLICY tenant_isolation_legal_officers ON legal_officers
    USING (tenant_id = current_setting('app.current_tenant_id', true));
CREATE POLICY tenant_isolation_legal_statutory_policies ON legal_statutory_policies
    USING (tenant_id = current_setting('app.current_tenant_id', true));
CREATE POLICY tenant_isolation_legal_calendar ON legal_compliance_calendar_events
    USING (tenant_id = current_setting('app.current_tenant_id', true));
CREATE POLICY tenant_isolation_legal_workflows ON legal_filing_workflows
    USING (tenant_id = current_setting('app.current_tenant_id', true));
CREATE POLICY tenant_isolation_legal_archives ON legal_archived_documents
    USING (tenant_id = current_setting('app.current_tenant_id', true));
CREATE POLICY tenant_isolation_legal_pre_registration_questionnaires ON legal_pre_registration_questionnaires
    USING (tenant_id = current_setting('app.current_tenant_id', true));
