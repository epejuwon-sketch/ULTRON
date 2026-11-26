import React, { useEffect, useState } from "react";
import { CheckCircle2, KeyRound, Lock, RefreshCw, Shield, ShieldCheck, Trash2, UserPlus } from "lucide-react";
import { apiFetch } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import { SecurityView } from "../components/SystemViews";
import {
  ConfirmationDialog,
  DataTable,
  EmptyState,
  ErrorState,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";
import { ReadableSummary } from "../components/ui/HumanPresentation";

export default function SecurityModulePage({ subPage, onSelectSubPage, onNavigate, user }: ModulePageProps) {
  const mod = getModule("security");
  const page = getSubPage("security", subPage);
  const { pushToast } = useToast();

  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [chain, setChain] = useState<any>(null);
  const [users, setUsers] = useState<any[]>([]);
  const [secrets, setSecrets] = useState<any[]>([]);
  const [passkeys, setPasskeys] = useState<any[]>([]);
  const [error, setError] = useState("");

  // Forms
  const [newUsername, setNewUsername] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState("OPERATOR");
  const [secName, setSecName] = useState("");
  const [secVal, setSecVal] = useState("");
  const [secProv, setSecProv] = useState("custom");
  const [inspectUrl, setInspectUrl] = useState("https://github.com");
  const [diagResult, setDiagResult] = useState<any>(null);
  const [confirmAction, setConfirmAction] = useState<{ title: string; message: string; fn: () => Promise<void> } | null>(null);

  async function load() {
    setError("");
    try {
      const [aud, ch, usr, sec, pk] = await Promise.all([
        apiFetch<any>("/api/v1/audit/logs?limit=50").catch(() => ({ logs: [] })),
        apiFetch<any>("/api/v1/audit/verify").catch(() => null),
        apiFetch<any>("/api/v1/auth/users").catch(() => ({ users: [] })),
        apiFetch<any>("/api/v1/vault/secrets").catch(() => ({ secrets: [] })),
        apiFetch<any>("/api/v1/sentinel/passkeys").catch(() => ({ passkeys: [] })),
      ]);
      setAuditLogs(aud.logs || []);
      setChain(ch);
      setUsers(usr.users || []);
      setSecrets(sec.secrets || []);
      setPasskeys(pk.passkeys || []);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, [subPage]);

  async function createUser(e: React.FormEvent) {
    e.preventDefault();
    if (!newUsername.trim() || !newEmail.trim() || !newPassword.trim()) return;
    try {
      await apiFetch("/api/v1/auth/users", {
        method: "POST",
        body: { username: newUsername.trim(), email: newEmail.trim(), password: newPassword, role: newRole },
      });
      setNewUsername("");
      setNewEmail("");
      setNewPassword("");
      pushToast(`Provisioned ${newRole} user.`, "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function storeSecret(e: React.FormEvent) {
    e.preventDefault();
    if (!secName.trim() || !secVal.trim()) return;
    try {
      await apiFetch("/api/v1/vault/secrets", {
        method: "POST",
        body: { name: secName.trim(), value: secVal, provider: secProv },
      });
      setSecName("");
      setSecVal("");
      pushToast("Secret encrypted with AES-256-GCM in VAULT.", "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`SECURITY CENTRE // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <button type="button" className="btn btn-secondary btn-sm" onClick={load}>
            <RefreshCw size={13} /> Refresh
          </button>
        }
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {/* 82. AEGIS OVERVIEW & 83. SECURITY EVENTS */}
      {(page.id === "overview" || page.id === "events") && <SecurityView />}

      {/* 84. AUDIT LOGS */}
      {page.id === "audit" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="grid-3">
            <MetricDisplay
              label="SHA-256 Chain Status"
              value={chain?.valid ? "INTACT" : "VERIFY"}
              sub={`${chain?.checked_entries ?? auditLogs.length} entries verified`}
              tone={chain?.valid ? "success" : "danger"}
            />
            <MetricDisplay label="Audit Records" value={auditLogs.length} sub="Tamper-evident ledger" tone="info" />
            <MetricDisplay label="Tenant Scope" value={user.tenant_id.slice(0, 12)} sub="Strict RLS / tenant isolation" tone="neutral" />
          </div>
          <div className="card">
            <div className="card-title"><span>Tamper-Evident Audit Ledger</span></div>
            <DataTable
              rows={auditLogs}
              rowKey={(l, i) => l.audit_id || String(i)}
              columns={[
                { key: "action", header: "Action", mono: true, render: (l) => <strong>{l.action || l.event_type}</strong> },
                { key: "actor", header: "Actor", mono: true, render: (l) => l.actor_user_id || "system" },
                { key: "status", header: "Outcome", render: (l) => <StatusIndicator label={l.status || "OK"} tone="success" /> },
                { key: "time", header: "Timestamp", mono: true, render: (l) => l.created_at || "—" },
              ]}
            />
          </div>
        </div>
      )}

      {/* 85. ACCESS CONTROL */}
      {page.id === "access" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title"><span><UserPlus size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Provision RBAC User</span></div>
            <form onSubmit={createUser} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <input className="input" value={newUsername} onChange={(e) => setNewUsername(e.target.value)} placeholder="Username" />
              <input className="input" type="email" value={newEmail} onChange={(e) => setNewEmail(e.target.value)} placeholder="Email" />
              <input className="input" type="password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} placeholder="Strong password (min 10 chars)" />
              <select className="select" value={newRole} onChange={(e) => setNewRole(e.target.value)}>
                <option value="ADMIN">ADMIN</option>
                <option value="OPERATOR">OPERATOR</option>
                <option value="VIEWER">VIEWER</option>
              </select>
              <button type="submit" className="btn">Create Tenant User</button>
            </form>
          </div>
          <div className="card">
            <div className="card-title"><span>Tenant Users ({users.length})</span></div>
            <DataTable
              rows={users}
              rowKey={(u, i) => u.user_id || String(i)}
              columns={[
                { key: "user", header: "Username", render: (u) => <strong>{u.username}</strong> },
                { key: "email", header: "Email", render: (u) => u.email },
                { key: "role", header: "RBAC Role", mono: true, render: (u) => <span className="pill pill-cyan">{u.role}</span> },
              ]}
            />
          </div>
        </div>
      )}

      {/* 86. PERMISSIONS */}
      {page.id === "permissions" && (
        <div className="card">
          <div className="card-title"><span><ShieldCheck size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Active Principal & Isolation Boundaries</span></div>
          <div className="grid-3">
            <MetricDisplay label="Operator" value={user.username} sub={user.email} tone="info" />
            <MetricDisplay label="RBAC Role" value={user.role} sub="Hierarchical enforcement" tone="success" />
            <MetricDisplay label="Tenant ID" value={user.tenant_id.slice(0, 14)} sub="Cross-tenant access denied" tone="neutral" />
          </div>
        </div>
      )}

      {/* 87. APPROVAL POLICIES */}
      {page.id === "policies" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span><Shield size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />ApprovalGate Governance Policy</span></div>
          <div className="list-item"><strong>Financial Soft Limit</strong><div className="muted">Any task or spend &gt; $50 USD requires explicit OWNER/ADMIN approval before execution.</div></div>
          <div className="list-item"><strong>Outbound Communication & Destructive Ops</strong><div className="muted">External email sends, deployment rollbacks, and EVOLVE promotions require ApprovalGate sign-off.</div></div>
          <button type="button" className="btn btn-sm" style={{ alignSelf: "flex-start" }} onClick={() => onNavigate("argon", "approvals")}>
            Open Approval Centre
          </button>
        </div>
      )}

      {/* 88. ACTIVE SESSIONS & PASSKEYS */}
      {page.id === "sessions" && (
        <div className="card">
          <div className="card-title">
            <span><KeyRound size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />SENTINEL Passkeys ({passkeys.length})</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("settings", "security-settings")}>
              Register New Passkey
            </button>
          </div>
          {passkeys.length === 0 ? (
            <EmptyState title="No Passkeys Registered" description="Register Face ID / Touch ID passkeys in Settings → Security Settings." />
          ) : (
            passkeys.map((pk) => (
              <div key={pk.credential_id} className="list-item" style={{ marginBottom: 8 }}>
                <div className="row-between">
                  <strong>{pk.device_label}</strong>
                  {pk.is_active && (
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={() =>
                        setConfirmAction({
                          title: "Revoke Passkey",
                          message: `Revoke passkey '${pk.device_label}'?`,
                          fn: async () => {
                            await apiFetch(`/api/v1/sentinel/passkeys/${pk.credential_id}/revoke`, { method: "POST" });
                            pushToast("Passkey revoked.", "success");
                            load();
                          },
                        })
                      }
                    >
                      Revoke
                    </button>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* 89. CREDENTIAL VAULT */}
      {page.id === "vault" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title"><span><Lock size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Store AES-256-GCM Secret</span></div>
            <form onSubmit={storeSecret} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <input className="input" value={secName} onChange={(e) => setSecName(e.target.value)} placeholder="Secret name (e.g., CUSTOM_API_KEY)" />
              <input className="input" type="password" value={secVal} onChange={(e) => setSecVal(e.target.value)} placeholder="Secret value (never logged or echoed)" />
              <input className="input" value={secProv} onChange={(e) => setSecProv(e.target.value)} placeholder="Provider tag" />
              <button type="submit" className="btn">Encrypt & Store</button>
            </form>
          </div>
          <div className="card">
            <div className="card-title"><span>Encrypted Vault Entries ({secrets.length})</span></div>
            {secrets.length === 0 ? (
              <EmptyState title="Vault Empty" description="Store secrets encrypted at rest with AES-256-GCM." />
            ) : (
              secrets.map((s) => (
                <div key={s.name} className="list-item" style={{ marginBottom: 8 }}>
                  <div className="row-between">
                    <strong className="mono">{s.name}</strong>
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={() =>
                        setConfirmAction({
                          title: "Delete Vault Secret",
                          message: `Permanently delete encrypted secret '${s.name}' from VAULT?`,
                          fn: async () => {
                            await apiFetch(`/api/v1/vault/secrets/${encodeURIComponent(s.name)}`, { method: "DELETE" });
                            pushToast("Secret deleted.", "success");
                            load();
                          },
                        })
                      }
                    >
                      <Trash2 size={12} /> Delete
                    </button>
                  </div>
                  <div className="muted">Provider: {s.provider} · Updated: {s.updated_at}</div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* 90. SECURITY DIAGNOSTICS */}
      {page.id === "diagnostics" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span>AEGIS URL Inspector & FIM Baseline Diagnostics</span></div>
          <div className="row">
            <input className="input" style={{ flex: 1 }} value={inspectUrl} onChange={(e) => setInspectUrl(e.target.value)} placeholder="https://..." />
            <button
              type="button"
              className="btn btn-sm"
              onClick={async () => {
                const res = await apiFetch<any>("/api/v1/aegis/inspect-url", { method: "POST", body: { url: inspectUrl } });
                setDiagResult(res);
                pushToast("SSRF / URL inspection complete.", "success");
              }}
            >
              <CheckCircle2 size={13} /> Inspect URL
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={async () => {
                const res = await apiFetch<any>("/api/v1/aegis/fim/rebaseline", { method: "POST" });
                setDiagResult(res);
                pushToast("FIM baseline refreshed.", "success");
              }}
            >
              Rebaseline FIM
            </button>
          </div>
          {diagResult && (
            <ReadableSummary title="Security Diagnostic Result" data={diagResult} diagnosticsTitle="Technical Diagnostics — AEGIS Payload" />
          )}
        </div>
      )}

      <ConfirmationDialog
        open={Boolean(confirmAction)}
        title={confirmAction?.title || "Confirm"}
        message={confirmAction?.message || ""}
        onCancel={() => setConfirmAction(null)}
        onConfirm={async () => {
          const fn = confirmAction?.fn;
          setConfirmAction(null);
          if (fn) await fn().catch((e) => pushToast(e.message, "error"));
        }}
      />
    </ResponsiveWorkspace>
  );
}
