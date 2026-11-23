import React, { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  ExternalLink,
  KeyRound,
  Link2,
  Plug,
  RefreshCw,
  Search,
  Settings2,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { apiFetch } from "../../lib/api";
import {
  INTEGRATION_CATEGORIES,
  INTEGRATIONS_CATALOG,
  IntegrationCatalogEntry,
  IntegrationCategory,
} from "../../catalog/integrationsCatalog";
import { DataTable, Drawer, MetricDisplay, StatusIndicator, useToast } from "../ui/DesignSystem";
import { AdminOAuthSetupPanel } from "./AdminOAuthSetupPanel";
import { UniversalConnectPanel } from "./UniversalConnectPanel";

const PENDING_OAUTH_KEY = "ultron_pending_oauth_provider";

type HubLifecycle =
  | "Live Verified"
  | "Connected"
  | "Authenticated"
  | "Configured"
  | "Awaiting Authorization"
  | "Configuration Required"
  | "Admin Action Required"
  | "Supported"
  | "Degraded"
  | "Expired"
  | "Revoked"
  | "Failed"
  | "Provider Limitation";

function hubTone(status: HubLifecycle): "success" | "info" | "warn" | "danger" | "neutral" {
  switch (status) {
    case "Live Verified":
    case "Connected":
      return "success";
    case "Authenticated":
    case "Configured":
    case "Supported":
      return "info";
    case "Awaiting Authorization":
    case "Configuration Required":
    case "Admin Action Required":
    case "Degraded":
      return "warn";
    case "Expired":
    case "Revoked":
    case "Failed":
      return "danger";
    default:
      return "neutral";
  }
}

function resolveHubStatus(
  entry: IntegrationCatalogEntry,
  managedByKey: Map<string, any>,
  statusCaps: Record<string, any>
): { status: HubLifecycle; record?: any; cap?: any; oauthReady: boolean; stageIndex: number } {
  if (!entry.supportedByBackend || entry.authFlow === "ROADMAP") {
    return { status: "Provider Limitation", oauthReady: false, stageIndex: 0 };
  }
  const rec = entry.backendProviderKey ? managedByKey.get(entry.backendProviderKey) : undefined;
  const cap = entry.statusCapabilityKey ? statusCaps[entry.statusCapabilityKey] : undefined;
  const oauthReady = Boolean(rec?.oauth_client_configured);

  if (rec?.disconnected_at) {
    return { status: "Revoked", record: rec, cap, oauthReady, stageIndex: oauthReady ? 2 : 1 };
  }
  if (rec?.token_expired) {
    return { status: "Expired", record: rec, cap, oauthReady, stageIndex: 2 };
  }
  const raw = String(rec?.status || "").toUpperCase();
  if (raw === "AVAILABLE" || (cap?.live_verified && cap?.capability_state === "AVAILABLE")) {
    return { status: "Live Verified", record: rec, cap, oauthReady, stageIndex: 4 };
  }
  if (raw === "ERROR" || raw === "FAILED") {
    return { status: "Failed", record: rec, cap, oauthReady, stageIndex: 3 };
  }
  if (raw === "DEGRADED") {
    return { status: "Degraded", record: rec, cap, oauthReady, stageIndex: 3 };
  }
  if (raw === "IMPLEMENTED_NOT_LIVE" || rec?.connection_id || rec?.configured_via_env) {
    return { status: "Authenticated", record: rec, cap, oauthReady, stageIndex: 3 };
  }
  if (entry.authFlow === "OAUTH2") {
    return oauthReady
      ? { status: "Configured", record: rec, cap, oauthReady, stageIndex: 2 }
      : { status: "Admin Action Required", record: rec, cap, oauthReady, stageIndex: 1 };
  }
  if (entry.authFlow === "API_KEY" || entry.authFlow === "SERVER_ENV") {
    return { status: "Configuration Required", record: rec, cap, oauthReady, stageIndex: 1 };
  }
  return { status: "Supported", record: rec, cap, oauthReady, stageIndex: 1 };
}

export function UniversalIntegrationHub() {
  const { pushToast } = useToast();
  const [connections, setConnections] = useState<any[]>([]);
  const [statusData, setStatusData] = useState<any>(null);
  const [readinessGate, setReadinessGate] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<"All" | IntegrationCategory>("All");
  const [viewFilter, setViewFilter] = useState<"ALL" | "CONNECTED" | "AVAILABLE" | "ATTENTION" | "RECENT">("ALL");
  const [configuring, setConfiguring] = useState<IntegrationCatalogEntry | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [awaitingAuth, setAwaitingAuth] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadAll() {
    try {
      const [cRes, sRes, gRes] = await Promise.all([
        apiFetch<any>("/api/v1/integrations/connections").catch(() => ({ connections: [] })),
        apiFetch<any>("/api/v1/integrations/status").catch(() => null),
        apiFetch<any>("/api/v1/integrations/readiness-gate").catch(() => null),
      ]);
      setConnections(cRes.connections || []);
      setStatusData(sRes);
      setReadinessGate(gRes);
    } catch (err: any) {
      pushToast(err.message || "Failed to load integration status.", "error");
    }
  }

  useEffect(() => {
    const rawFb = sessionStorage.getItem("ultron_oauth_feedback");
    if (rawFb) {
      sessionStorage.removeItem("ultron_oauth_feedback");
      try {
        const fb = JSON.parse(rawFb);
        pushToast(fb.message, fb.type === "error" ? "error" : "success");
      } catch {
        // ignore
      }
    }
    loadAll();
  }, []);

  const managedByKey = useMemo(() => {
    const m = new Map<string, any>();
    for (const c of connections) m.set(c.provider, c);
    return m;
  }, [connections]);

  const statusCaps = useMemo(() => statusData?.capabilities || {}, [statusData]);

  const enriched = useMemo(() => {
    return INTEGRATIONS_CATALOG.map((entry) => {
      const resolved = resolveHubStatus(entry, managedByKey, statusCaps);
      return { entry, ...resolved };
    });
  }, [managedByKey, statusCaps]);

  const stats = useMemo(() => {
    const total = enriched.length;
    let configured = 0;
    let authenticated = 0;
    let connected = 0;
    let verified = 0;
    let expired = 0;
    let failed = 0;
    let adminRequired = 0;
    let limitations = 0;
    let attention = 0;
    let available = 0;
    for (const item of enriched) {
      if (item.status === "Live Verified") {
        verified += 1;
        connected += 1;
        authenticated += 1;
        configured += 1;
      } else if (item.status === "Connected" || item.status === "Authenticated") {
        connected += 1;
        authenticated += 1;
        configured += 1;
      } else if (item.status === "Configured") {
        configured += 1;
        available += 1;
      } else if (item.status === "Expired") {
        expired += 1;
        attention += 1;
      } else if (item.status === "Failed" || item.status === "Degraded" || item.status === "Revoked") {
        failed += 1;
        attention += 1;
      } else if (item.status === "Admin Action Required") {
        adminRequired += 1;
        available += 1;
      } else if (item.status === "Provider Limitation") {
        limitations += 1;
      } else if (item.entry.supportedByBackend) {
        available += 1;
      }
    }
    return {
      total,
      configured,
      authenticated,
      connected,
      verified,
      expired,
      failed,
      adminRequired,
      limitations,
      attention,
      available,
    };
  }, [enriched]);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return enriched.filter((item) => {
      if (category !== "All" && item.entry.category !== category) return false;
      if (q && !item.entry.name.toLowerCase().includes(q) && !item.entry.shortDescription.toLowerCase().includes(q)) {
        return false;
      }
      if (viewFilter === "CONNECTED") {
        return ["Live Verified", "Connected", "Authenticated"].includes(item.status);
      }
      if (viewFilter === "AVAILABLE") {
        return item.entry.supportedByBackend && !["Live Verified", "Connected", "Authenticated"].includes(item.status);
      }
      if (viewFilter === "ATTENTION") {
        return ["Expired", "Revoked", "Failed", "Degraded", "Configuration Required"].includes(item.status);
      }
      if (viewFilter === "RECENT") {
        return Boolean(item.record?.updated_at);
      }
      return true;
    });
  }, [enriched, category, search, viewFilter]);

  async function handleStartOAuth(entry: IntegrationCatalogEntry) {
    if (!entry.backendProviderKey) return;
    setBusy(true);
    try {
      const res = await apiFetch<any>(`/api/v1/integrations/oauth/${entry.backendProviderKey}/start`, {
        method: "POST",
        body: {
          scopes: entry.permissions,
          redirect_uri: `${window.location.origin}/oauth/callback`,
        },
      });
      sessionStorage.setItem(PENDING_OAUTH_KEY, entry.backendProviderKey);
      setAwaitingAuth(entry.backendProviderKey);
      window.location.assign(res.authorization_url);
    } catch (err: any) {
      pushToast(err.message || "Could not start OAuth authorization.", "error");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveApiKey(e: React.FormEvent) {
    e.preventDefault();
    if (!configuring?.backendProviderKey) return;
    setBusy(true);
    try {
      await apiFetch(`/api/v1/integrations/${configuring.backendProviderKey}/connect`, {
        method: "POST",
        body: { credentials: fieldValues, auth_type: "API_KEY", scopes: configuring.permissions },
      });
      setFieldValues({});
      pushToast(`${configuring.name} encrypted & saved in VAULT.`, "success");
      await loadAll();
    } catch (err: any) {
      pushToast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function handleVerifyProvider(providerKey: string) {
    setBusy(true);
    try {
      const res = await apiFetch<any>(`/api/v1/integrations/${providerKey}/verify`, { method: "POST" });
      pushToast(`Health check: ${res.status}${res.last_error ? ` (${res.last_error})` : ""}`, res.status === "AVAILABLE" ? "success" : "info");
      await loadAll();
    } catch (err: any) {
      pushToast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function handleRefreshToken(providerKey: string) {
    setBusy(true);
    try {
      await apiFetch(`/api/v1/integrations/${providerKey}/refresh`, { method: "POST" });
      pushToast("OAuth token refreshed in VAULT.", "success");
      await loadAll();
    } catch (err: any) {
      pushToast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function handleDisconnect(providerKey: string) {
    setBusy(true);
    try {
      await apiFetch(`/api/v1/integrations/${providerKey}/disconnect`, { method: "POST" });
      pushToast(`Disconnected and revoked credentials for ${providerKey}.`, "info");
      setConfiguring(null);
      await loadAll();
    } catch (err: any) {
      pushToast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  const activeConfigItem = configuring
    ? enriched.find((x) => x.entry.id === configuring.id) || null
    : null;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Summary Strip */}
      <div className="grid-4" style={{ gap: 10 }}>
        <MetricDisplay
          label="Total / Configured"
          value={`${stats.total} / ${stats.configured}`}
          sub={`${stats.authenticated} Authenticated · ${stats.limitations} Limitation`}
          tone="info"
        />
        <MetricDisplay
          label="Connected / Live"
          value={`${stats.connected} / ${stats.verified}`}
          sub="Verified via real provider API"
          tone="success"
        />
        <MetricDisplay
          label="Expired / Failed"
          value={`${stats.expired} / ${stats.failed}`}
          sub={`${stats.adminRequired} Admin Action Required`}
          tone={stats.attention > 0 || stats.adminRequired > 0 ? "warn" : "neutral"}
        />
        <MetricDisplay
          label="Vault & Caravan Gate"
          value={readinessGate?.core_infrastructure_ready ? "READY" : "GATED"}
          sub={`AES-256-GCM · Screen-Share ${readinessGate?.screen_sharing_readiness?.supported ? "Ready" : "Pending"}`}
          tone={readinessGate?.core_infrastructure_ready ? "success" : "warn"}
        />
      </div>

      {readinessGate && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 6, padding: "10px 14px" }}>
          <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
            <strong style={{ fontSize: 13 }}>
              <ShieldCheck size={13} style={{ verticalAlign: "middle", marginRight: 4 }} />
              Caravan Infrastructure Readiness Gate &amp; Screen-Sharing Policy
            </strong>
            <StatusIndicator
              label={readinessGate.core_infrastructure_ready ? "CORE INFRASTRUCTURE READY" : "BLOCKERS PRESENT"}
              tone={readinessGate.core_infrastructure_ready ? "success" : "warn"}
            />
          </div>
          <div className="row" style={{ gap: 8, flexWrap: "wrap", fontSize: 12 }}>
            {["github", "supabase", "vercel", "cloudflare"].map((p) => {
              const gp = readinessGate.core_providers?.[p];
              return (
                <span key={p} className="pill mono">
                  {p}: {gp?.lifecycle_stage || "SUPPORTED"}
                </span>
              );
            })}
            <span className="pill mono">vault: {readinessGate.vault?.ready ? "AES-256-GCM" : "UNCONFIGURED"}</span>
            <span className="pill mono">argon: {readinessGate.argon?.ready ? "GATED" : "BLOCKED"}</span>
            <span className="pill mono">
              screen_share: {readinessGate.screen_sharing_readiness?.consent_required ? "CONSENT+MASKED" : "OFF"}
            </span>
          </div>
          {Array.isArray(readinessGate.outstanding_blockers) && readinessGate.outstanding_blockers.length > 0 && (
            <div className="muted" style={{ fontSize: 11 }}>
              Outstanding blockers: {readinessGate.outstanding_blockers.join(" · ")}
            </div>
          )}
        </div>
      )}

      {awaitingAuth && (
        <div className="alert-box" style={{ fontSize: 12 }}>
          <RefreshCw size={12} /> Completing OAuth 2.0 + PKCE verification for <strong>{awaitingAuth}</strong>...
        </div>
      )}

      {/* Search, View Tabs & Category Filter */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
          <div>
            <strong style={{ fontSize: 15 }}><Plug size={14} /> Universal Integration Hub</strong>
            <div className="muted" style={{ fontSize: 12 }}>
              Discover → Configure → Authorize → Connect → Verify. All secrets encrypted server-side in VAULT.
            </div>
          </div>
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadAll}>
            <RefreshCw size={12} /> Refresh Status
          </button>
        </div>

        <div className="segmented" style={{ flexWrap: "wrap" }}>
          {[
            { id: "ALL", label: "All Services" },
            { id: "CONNECTED", label: `Connected (${stats.connected})` },
            { id: "AVAILABLE", label: `Available (${stats.available})` },
            { id: "ATTENTION", label: "Requires Attention" },
            { id: "RECENT", label: "Recently Connected" },
          ].map((t) => (
            <button
              key={t.id}
              type="button"
              className={`seg-btn ${viewFilter === t.id ? "active" : ""}`}
              onClick={() => setViewFilter(t.id as any)}
            >
              {t.label}
            </button>
          ))}
        </div>

        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <div style={{ position: "relative", flex: 1, minWidth: 200 }}>
            <Search size={13} style={{ position: "absolute", left: 10, top: 10, opacity: 0.6 }} />
            <input
              className="input"
              style={{ paddingLeft: 28, width: "100%" }}
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search Google Workspace, GitHub, AI, Cloud, Finance, Marketing..."
            />
          </div>
          <select className="select" value={category} onChange={(e) => setCategory(e.target.value as any)} aria-label="Filter category">
            <option value="All">All Categories</option>
            {INTEGRATION_CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>

        <DataTable
          rows={filtered}
          rowKey={(r) => r.entry.id}
          emptyTitle="No Matching Integrations"
          emptyDescription="Adjust your search or category filter, or register a custom MCP / HTTP / Webhook service below."
          columns={[
            {
              key: "service",
              header: "Integration",
              render: (r) => (
                <div>
                  <strong>{r.entry.name}</strong>
                  <div className="muted" style={{ fontSize: 11 }}>
                    {r.entry.category} · {r.entry.supportedByBackend ? r.entry.authFlow : "Unavailable"}
                    {r.record?.account_label ? ` · ${r.record.account_label}` : ""}
                  </div>
                </div>
              ),
            },
            {
              key: "status",
              header: "Lifecycle Status",
              render: (r) => <StatusIndicator label={r.status} tone={hubTone(r.status)} />,
            },
            {
              key: "verified",
              header: "Last Verified",
              render: (r) => (
                <span className="muted" style={{ fontSize: 11 }}>
                  {r.record?.last_verified_at ? new Date(r.record.last_verified_at).toLocaleString() : "Not verified"}
                </span>
              ),
            },
            {
              key: "action",
              header: "Action",
              render: (r) =>
                r.entry.supportedByBackend ? (
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={() => {
                      setFieldValues({});
                      setConfiguring(r.entry);
                    }}
                  >
                    <Settings2 size={12} /> Configure
                  </button>
                ) : (
                  <span className="muted" style={{ fontSize: 11 }}>Unavailable</span>
                ),
            },
          ]}
        />
      </div>

      {/* Custom, MCP (STDIO / Streamable HTTP), Google ADC & Signed Webhooks */}
      <UniversalConnectPanel onChanged={loadAll} />

      {/* Configure & Account Management Drawer */}
      <Drawer
        open={Boolean(activeConfigItem)}
        title={activeConfigItem ? `${activeConfigItem.entry.name} — Integration Manager` : ""}
        onClose={() => setConfiguring(null)}
      >
        {activeConfigItem && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12, fontSize: 12 }}>
            <div className="row-between">
              <span className="pill mono">{activeConfigItem.entry.authFlow}</span>
              <StatusIndicator label={activeConfigItem.status} tone={hubTone(activeConfigItem.status)} />
            </div>

            {/* 4-Stage Lifecycle Progress */}
            <div className="list-item" style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 6, textAlign: "center" }}>
              {[
                { idx: 1, label: "1. Supported" },
                { idx: 2, label: "2. Configured" },
                { idx: 3, label: "3. Authenticated" },
                { idx: 4, label: "4. Live Verified" },
              ].map((st) => {
                const reached = activeConfigItem.stageIndex >= st.idx;
                return (
                  <div
                    key={st.idx}
                    className="pill"
                    style={{
                      justifyContent: "center",
                      opacity: reached ? 1 : 0.45,
                      borderColor: reached ? "var(--accent, #38bdf8)" : undefined,
                    }}
                  >
                    {st.label}
                  </div>
                );
              })}
            </div>

            <div className="muted">{activeConfigItem.entry.shortDescription}</div>

            {/* Account & Health Metadata */}
            <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div><strong>Authorized Account:</strong> {activeConfigItem.record?.account_label || "Not linked"}</div>
              <div><strong>Connection Method:</strong> {activeConfigItem.record?.auth_type || activeConfigItem.entry.authFlow}</div>
              <div><strong>Granted Scopes:</strong> {(activeConfigItem.record?.scopes?.length ? activeConfigItem.record.scopes : activeConfigItem.entry.permissions).join(", ") || "Default"}</div>
              <div><strong>Connected / Updated:</strong> {activeConfigItem.record?.updated_at || "Never"}</div>
              <div><strong>Last Health Check:</strong> {activeConfigItem.record?.last_verified_at || "Never"}</div>
              {activeConfigItem.record?.token_expired && (
                <div style={{ color: "#f59e0b" }}><AlertTriangle size={12} /> OAuth token expired. Click Reauthorize in Browser or Refresh Token.</div>
              )}
              {activeConfigItem.record?.last_error && (
                <div style={{ color: "#f87171" }}><AlertTriangle size={12} /> {activeConfigItem.record.last_error}</div>
              )}
            </div>

            {/* OAuth 2.0 Flow */}
            {activeConfigItem.entry.authFlow === "OAUTH2" && activeConfigItem.entry.backendProviderKey && (
              <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <strong><Link2 size={12} /> OAuth 2.0 + PKCE Authorization</strong>
                <AdminOAuthSetupPanel
                  entry={activeConfigItem.entry}
                  oauthReady={activeConfigItem.oauthReady}
                  busy={busy}
                  onConfigured={loadAll}
                />
                <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={busy || !activeConfigItem.oauthReady}
                    onClick={() => handleStartOAuth(activeConfigItem.entry)}
                  >
                    <ExternalLink size={12} /> {activeConfigItem.record?.connection_id ? "Reauthorize in Browser" : "Authorize in Browser"}
                  </button>
                  {activeConfigItem.record?.connection_id && (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      disabled={busy}
                      onClick={() => handleRefreshToken(activeConfigItem.entry.backendProviderKey!)}
                    >
                      <RefreshCw size={12} /> Refresh Token
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* API Key / PAT Credential Form */}
            {(activeConfigItem.entry.authFlow === "API_KEY" ||
              (activeConfigItem.entry.authFlow === "OAUTH2" && Boolean(activeConfigItem.entry.connectFields?.length))) &&
              activeConfigItem.entry.backendProviderKey && (
                <form onSubmit={handleSaveApiKey} className="list-item" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <strong><KeyRound size={12} /> Encrypted VAULT Credentials</strong>
                  {(activeConfigItem.entry.connectFields || [
                    { key: "api_key", label: "API Key", placeholder: "Enter API key (encrypted in VAULT)", sensitive: true },
                  ]).map((f) => (
                    <input
                      key={f.key}
                      className="input"
                      type={f.sensitive ? "password" : "text"}
                      placeholder={f.placeholder}
                      value={fieldValues[f.key] || ""}
                      onChange={(e) => setFieldValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
                      required
                    />
                  ))}
                  <button type="submit" className="btn btn-sm" disabled={busy}>
                    <ShieldCheck size={12} /> Save Encrypted in VAULT
                  </button>
                </form>
              )}

            {/* Server-Managed / Universal Connections 2.0 Guidance */}
            {activeConfigItem.entry.authFlow === "SERVER_ENV" && (
              <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <strong><ShieldCheck size={12} /> Server-Managed Integration</strong>
                <div className="muted" style={{ fontSize: 12 }}>
                  {activeConfigItem.entry.id === "supabase"
                    ? "Requires server-side Supabase Project URL (SUPABASE_URL), backend-only service-role key (SUPABASE_SERVICE_ROLE_KEY — never exposed to frontend), and Transaction Pooler / Supavisor connection string (ULTRON_DATABASE_URL) with migration and RLS permissions. Use Run Health Check below to verify live PostgREST and database connectivity."
                    : activeConfigItem.entry.id === "webhooks" ||
                      activeConfigItem.entry.id === "rest_apis" ||
                      activeConfigItem.entry.id === "mcp"
                    ? "Server-level defaults are managed by the backend runtime. To register custom MCP servers, signed webhooks, or custom REST API endpoints, use Universal Connections Centre 2.0 → Connect a Service below."
                    : "Managed via server environment configuration. Use Run Health Check below to verify live runtime connectivity."}
                </div>
                {activeConfigItem.entry.requiredEnvVars.length > 0 && (
                  <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                    {activeConfigItem.entry.requiredEnvVars.map((envVar) => (
                      <span key={envVar} className="pill mono" style={{ fontSize: 11 }}>{envVar}</span>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Live Verification & Disconnect */}
            {activeConfigItem.entry.backendProviderKey && (
              <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={busy}
                  onClick={() => handleVerifyProvider(activeConfigItem.entry.backendProviderKey!)}
                >
                  <Activity size={12} /> Run Health Check
                </button>
                {activeConfigItem.record?.connection_id && !activeConfigItem.record?.disconnected_at && (
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    disabled={busy}
                    onClick={() => handleDisconnect(activeConfigItem.entry.backendProviderKey!)}
                  >
                    <Trash2 size={12} /> Disconnect &amp; Revoke
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
