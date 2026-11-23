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
import { UniversalConnectPanel } from "./UniversalConnectPanel";

const PENDING_OAUTH_KEY = "ultron_pending_oauth_provider";

type HubLifecycle =
  | "Live Verified"
  | "Connected"
  | "Authenticated"
  | "Awaiting Authorization"
  | "Configuration Required"
  | "Supported"
  | "Degraded"
  | "Expired"
  | "Revoked"
  | "Failed"
  | "Unavailable";

function hubTone(status: HubLifecycle): "success" | "info" | "warn" | "danger" | "neutral" {
  switch (status) {
    case "Live Verified":
    case "Connected":
      return "success";
    case "Authenticated":
    case "Supported":
      return "info";
    case "Awaiting Authorization":
    case "Configuration Required":
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
): { status: HubLifecycle; record?: any; cap?: any; oauthReady: boolean } {
  if (!entry.supportedByBackend || entry.authFlow === "ROADMAP") {
    return { status: "Unavailable", oauthReady: false };
  }
  const rec = entry.backendProviderKey ? managedByKey.get(entry.backendProviderKey) : undefined;
  const cap = entry.statusCapabilityKey ? statusCaps[entry.statusCapabilityKey] : undefined;
  const oauthReady = Boolean(rec?.oauth_client_configured);

  if (rec?.disconnected_at) {
    return { status: "Revoked", record: rec, cap, oauthReady };
  }
  if (rec?.token_expired) {
    return { status: "Expired", record: rec, cap, oauthReady };
  }
  const raw = String(rec?.status || "").toUpperCase();
  if (raw === "AVAILABLE" || (cap?.live_verified && cap?.capability_state === "AVAILABLE")) {
    return { status: "Live Verified", record: rec, cap, oauthReady };
  }
  if (raw === "ERROR" || raw === "FAILED") {
    return { status: "Failed", record: rec, cap, oauthReady };
  }
  if (raw === "DEGRADED") {
    return { status: "Degraded", record: rec, cap, oauthReady };
  }
  if (raw === "IMPLEMENTED_NOT_LIVE" || rec?.connection_id || rec?.configured_via_env) {
    return { status: "Authenticated", record: rec, cap, oauthReady };
  }
  if (entry.authFlow === "OAUTH2" && !oauthReady) {
    return { status: "Configuration Required", record: rec, cap, oauthReady };
  }
  if (entry.authFlow === "API_KEY" || entry.authFlow === "SERVER_ENV") {
    return { status: "Configuration Required", record: rec, cap, oauthReady };
  }
  return { status: "Supported", record: rec, cap, oauthReady };
}

export function UniversalIntegrationHub() {
  const { pushToast } = useToast();
  const [connections, setConnections] = useState<any[]>([]);
  const [statusData, setStatusData] = useState<any>(null);
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<"All" | IntegrationCategory>("All");
  const [viewFilter, setViewFilter] = useState<"ALL" | "CONNECTED" | "AVAILABLE" | "ATTENTION" | "RECENT">("ALL");
  const [configuring, setConfiguring] = useState<IntegrationCatalogEntry | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [awaitingAuth, setAwaitingAuth] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function loadAll() {
    try {
      const [cRes, sRes] = await Promise.all([
        apiFetch<any>("/api/v1/integrations/connections").catch(() => ({ connections: [] })),
        apiFetch<any>("/api/v1/integrations/status").catch(() => null),
      ]);
      setConnections(cRes.connections || []);
      setStatusData(sRes);
    } catch (err: any) {
      pushToast(err.message || "Failed to load integration status.", "error");
    }
  }

  useEffect(() => {
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
    let connected = 0;
    let verified = 0;
    let attention = 0;
    let available = 0;
    for (const item of enriched) {
      if (item.status === "Live Verified") {
        verified += 1;
        connected += 1;
      } else if (item.status === "Connected" || item.status === "Authenticated") {
        connected += 1;
      } else if (["Expired", "Revoked", "Failed", "Degraded"].includes(item.status)) {
        attention += 1;
      } else if (item.entry.supportedByBackend) {
        available += 1;
      }
    }
    return { connected, verified, attention, available };
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
        <MetricDisplay label="Connected" value={String(stats.connected)} sub={`${stats.verified} Live Verified`} tone="success" />
        <MetricDisplay label="Available" value={String(stats.available)} sub="Ready to Configure" tone="info" />
        <MetricDisplay label="Needs Attention" value={String(stats.attention)} sub="Expired / Degraded / Revoked" tone="warn" />
        <MetricDisplay label="Vault Security" value="AES-256-GCM" sub="PKCE + SENTINEL + AEGIS" tone="neutral" />
      </div>

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

            <div className="muted">{activeConfigItem.entry.shortDescription}</div>

            {/* Account & Health Metadata */}
            <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <div><strong>Authorized Account:</strong> {activeConfigItem.record?.account_label || "Not linked"}</div>
              <div><strong>Connection Method:</strong> {activeConfigItem.record?.auth_type || activeConfigItem.entry.authFlow}</div>
              <div><strong>Granted Scopes:</strong> {(activeConfigItem.record?.scopes?.length ? activeConfigItem.record.scopes : activeConfigItem.entry.permissions).join(", ") || "Default"}</div>
              <div><strong>Connected / Updated:</strong> {activeConfigItem.record?.updated_at || "Never"}</div>
              <div><strong>Last Health Check:</strong> {activeConfigItem.record?.last_verified_at || "Never"}</div>
              {activeConfigItem.record?.last_error && (
                <div style={{ color: "#f87171" }}><AlertTriangle size={12} /> {activeConfigItem.record.last_error}</div>
              )}
            </div>

            {/* OAuth 2.0 Flow */}
            {activeConfigItem.entry.authFlow === "OAUTH2" && activeConfigItem.entry.backendProviderKey && (
              <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <strong><Link2 size={12} /> OAuth 2.0 + PKCE Authorization</strong>
                {!activeConfigItem.oauthReady && (
                  <div className="muted">
                    Server OAuth client credentials are not configured yet ({activeConfigItem.entry.requiredEnvVars.join(", ")}). Browser OAuth cannot start until configured on the backend.
                  </div>
                )}
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

            {/* API Key / Credential Form */}
            {(activeConfigItem.entry.authFlow === "API_KEY" || activeConfigItem.entry.authFlow === "SERVER_ENV") &&
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
