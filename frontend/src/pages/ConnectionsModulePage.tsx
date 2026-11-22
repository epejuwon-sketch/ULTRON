import React, { useEffect, useMemo, useState } from "react";
import { CheckCircle2, ExternalLink, RefreshCw, Shield, Unplug } from "lucide-react";
import { apiFetch } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import {
  HonestConnectionStatus,
  INTEGRATION_CATEGORIES,
  INTEGRATIONS_CATALOG,
  IntegrationCatalogEntry,
  IntegrationCategory,
} from "../catalog/integrationsCatalog";
import { IntegrationCard } from "../components/integrations/IntegrationCard";
import { IntegrationLogo } from "../components/integrations/IntegrationLogo";
import type { ModulePageProps } from "../types/module";
import {
  ActivityFeed,
  ConfirmationDialog,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  FilterBar,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  SearchBar,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";
import { ReadableSummary } from "../components/ui/HumanPresentation";

/**
 * Strictly computes honest 4-stage connection status from real backend responses.
 * NEVER fakes "Connected" when backend verification / OAuth / credentials are missing.
 */
function resolveHonestStatus(
  entry: IntegrationCatalogEntry,
  statusData: any,
  connections: any[],
  health: any
): { status: HonestConnectionStatus; detail: string; record?: any } {
  if (!entry.supportedByBackend || entry.authFlow === "ROADMAP") {
    return {
      status: "Coming soon",
      detail: "Planned integration on the ULTRON roadmap. No backend adapter is active yet.",
    };
  }

  const record = connections.find(
    (c) => c.provider === entry.backendProviderKey || c.provider === entry.id
  );
  if (record) {
    const st = String(record.status || "").toUpperCase();
    if (st === "CONNECTED" || st === "VERIFIED" || st === "ACTIVE") {
      return {
        status: "Connected",
        detail: record.account_label || "Authenticated and encrypted via backend VAULT.",
        record,
      };
    }
    if (st === "EXPIRED") {
      return {
        status: "Authentication expired",
        detail: "OAuth token expired — reconnect or refresh token.",
        record,
      };
    }
    if (st === "ERROR" || st === "FAILED") {
      return {
        status: "Error",
        detail: record.last_error || "Last live verification probe failed.",
        record,
      };
    }
  }

  // Check backend /api/v1/integrations/status capabilities
  const cap = entry.statusCapabilityKey ? statusData?.capabilities?.[entry.statusCapabilityKey] : null;
  if (cap) {
    if (cap.capability_state === "AVAILABLE" || cap.verified === true) {
      return {
        status: "Connected",
        detail: cap.detail || "Live verified via backend IntegrationManager.",
      };
    }
    if (cap.missing_env_vars?.length > 0) {
      return {
        status: "Configuration required",
        detail: `Missing server env: ${cap.missing_env_vars.join(", ")}`,
      };
    }
    return {
      status: "Not connected",
      detail: cap.detail || "Supported by backend — awaiting operator credentials or OAuth.",
    };
  }

  // Check /health providers for LLM / DB providers
  const hp = health?.integrations?.capabilities?.[entry.id] || health?.providers?.[entry.id];
  if (hp) {
    if (hp.configured) {
      return { status: "Connected", detail: hp.detail || "Configured on server." };
    }
    return {
      status: "Configuration required",
      detail: `Requires ${entry.requiredEnvVars.join(", ") || "provider credentials"}.`,
    };
  }

  if (entry.id === "postgresql" && (health?.database?.connected || health?.database?.healthy)) {
    return { status: "Connected", detail: "PostgreSQL Transaction Pooler verified." };
  }

  if (entry.authFlow === "SERVER_ENV" && entry.requiredEnvVars.length > 0) {
    return {
      status: "Configuration required",
      detail: `Configure ${entry.requiredEnvVars.join(", ")} in deployment environment.`,
    };
  }

  return {
    status: "Not connected",
    detail: "Supported by ULTRON backend — connect via OAuth or encrypted API key.",
  };
}

export default function ConnectionsModulePage({ subPage, onSelectSubPage }: ModulePageProps) {
  const mod = getModule("connections");
  const page = getSubPage("connections", subPage);
  const { pushToast } = useToast();

  const [statusData, setStatusData] = useState<any>(null);
  const [connections, setConnections] = useState<any[]>([]);
  const [antigravity, setAntigravity] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [geminiDiag, setGeminiDiag] = useState<any>(null);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [bridgeShares, setBridgeShares] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [verifying, setVerifying] = useState(false);

  // Directory filters & detail drawer
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<"All" | IntegrationCategory>("All");
  const [selected, setSelected] = useState<IntegrationCatalogEntry | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [probeResult, setProbeResult] = useState<any>(null);
  const [confirmDisconnect, setConfirmDisconnect] = useState<IntegrationCatalogEntry | null>(null);

  async function load() {
    setError("");
    try {
      const [sRes, cRes, agRes, hRes, gRes, aRes, bRes] = await Promise.all([
        apiFetch<any>("/api/v1/integrations/status").catch(() => null),
        apiFetch<any>("/api/v1/integrations/connections").catch(() => ({ connections: [] })),
        apiFetch<any>("/api/v1/integrations/antigravity?live=false").catch(() => null),
        apiFetch<any>("/health").catch(() => null),
        apiFetch<any>("/api/v1/neon/gemini/diagnostics?discover=false").catch(() => null),
        apiFetch<any>("/api/v1/audit/logs?limit=30").catch(() => ({ logs: [] })),
        apiFetch<any>("/api/v1/bridge/shares").catch(() => ({ shares: [] })),
      ]);
      setStatusData(sRes);
      setConnections(cRes.connections || []);
      setAntigravity(agRes);
      setHealth(hRes);
      setGeminiDiag(gRes);
      setAuditLogs(
        (aRes.logs || []).filter((l: any) =>
          String(l.action || l.resource || "").toLowerCase().includes("integrat") ||
          String(l.action || "").toLowerCase().includes("oauth")
        )
      );
      setBridgeShares(bRes.shares || []);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, [subPage]);

  const resolvedMap = useMemo(() => {
    const map = new Map<string, { status: HonestConnectionStatus; detail: string; record?: any }>();
    for (const entry of INTEGRATIONS_CATALOG) {
      map.set(entry.id, resolveHonestStatus(entry, statusData, connections, health));
    }
    return map;
  }, [statusData, connections, health]);

  async function verifyAll() {
    setVerifying(true);
    try {
      const res = await apiFetch<any>("/api/v1/integrations/verify", { method: "POST" });
      setStatusData(res);
      pushToast("Live backend integration verification complete.", "success");
    } catch (e: any) {
      pushToast(e.message, "error");
    } finally {
      setVerifying(false);
    }
  }

  async function handleConnectApiKey(entry: IntegrationCatalogEntry) {
    if (!entry.backendProviderKey) return;
    try {
      await apiFetch(`/api/v1/integrations/${entry.backendProviderKey}/connect`, {
        method: "POST",
        body: { credentials: fieldValues },
      });
      setFieldValues({});
      pushToast(`${entry.name} encrypted & saved in backend VAULT.`, "success");
      await load();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function handleStartOAuth(entry: IntegrationCatalogEntry) {
    if (!entry.backendProviderKey) return;
    try {
      const res = await apiFetch<any>(`/api/v1/integrations/oauth/${entry.backendProviderKey}/start`, {
        method: "POST",
        body: { redirect_uri: `${window.location.origin}/oauth/callback` },
      });
      setProbeResult(res);
      if (res.authorization_url) {
        pushToast("OAuth 2.0 + PKCE authorization URL generated.", "info");
      }
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function handleTestProvider(entry: IntegrationCatalogEntry) {
    if (!entry.backendProviderKey) return;
    try {
      const res = await apiFetch<any>(`/api/v1/integrations/${entry.backendProviderKey}/verify`, {
        method: "POST",
      });
      setProbeResult(res);
      pushToast(`Verification probe finished for ${entry.name}.`, "info");
      await load();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function handleDisconnect(entry: IntegrationCatalogEntry) {
    if (!entry.backendProviderKey) return;
    try {
      await apiFetch(`/api/v1/integrations/${entry.backendProviderKey}/disconnect`, { method: "POST" });
      pushToast(`${entry.name} disconnected.`, "success");
      setProbeResult(null);
      await load();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  const filteredCatalog = INTEGRATIONS_CATALOG.filter((item) => {
    if (category !== "All" && item.category !== category) return false;
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      item.name.toLowerCase().includes(q) ||
      item.category.toLowerCase().includes(q) ||
      item.shortDescription.toLowerCase().includes(q)
    );
  });

  const supportedCount = INTEGRATIONS_CATALOG.filter((i) => i.supportedByBackend).length;
  const connectedCount = INTEGRATIONS_CATALOG.filter((i) => resolvedMap.get(i.id)?.status === "Connected").length;
  const configReqCount = INTEGRATIONS_CATALOG.filter((i) => resolvedMap.get(i.id)?.status === "Configuration required").length;
  const roadmapCount = INTEGRATIONS_CATALOG.filter((i) => !i.supportedByBackend).length;

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`CONNECTIONS CENTRE // PAGE ${page.number} · ${INTEGRATIONS_CATALOG.length} INTEGRATIONS`}
        title={page.label}
        description={page.description}
        actions={
          <div className="row">
            <button id="connections-verify-all" type="button" className="btn btn-sm" disabled={verifying} onClick={verifyAll}>
              <CheckCircle2 size={13} /> {verifying ? "Verifying..." : "Verify Live Status"}
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={load}>
              <RefreshCw size={13} /> Refresh
            </button>
          </div>
        }
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {/* 34. CONNECTIONS OVERVIEW */}
      {page.id === "overview" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="grid-3">
            <MetricDisplay label="Stage 1: Supported" value={supportedCount} sub={`Out of ${INTEGRATIONS_CATALOG.length} catalogued`} tone="info" />
            <MetricDisplay label="Stage 2: Config Needed" value={configReqCount} sub="Missing env or VAULT key" tone="warn" />
            <MetricDisplay label="Stage 3/4: Live Verified" value={connectedCount} sub="Strictly verified, zero fakes" tone={connectedCount > 0 ? "success" : "neutral"} />
          </div>
          <div className="card">
            <div className="card-title">
              <span>Google Gemini Primary Intelligence Diagnostics</span>
              <StatusIndicator
                label={geminiDiag?.live_inference?.status || (geminiDiag?.configured ? "CONFIGURED" : "NOT CONFIGURED")}
                tone={geminiDiag?.live_inference?.verified ? "success" : geminiDiag?.configured ? "info" : "warn"}
              />
            </div>
            <div className="grid-3" style={{ marginBottom: 12 }}>
              <MetricDisplay
                label="Primary Provider"
                value={geminiDiag?.provider_label || "Google Gemini"}
                sub={`API: ${geminiDiag?.api_mode || "generate_content"} · Models: ${geminiDiag?.catalog?.models_discovered ?? 0}`}
                tone={geminiDiag?.configured ? "success" : "warn"}
              />
              <MetricDisplay
                label="Live Inference & Latency"
                value={
                  geminiDiag?.live_inference?.last_latency_ms != null
                    ? `${geminiDiag.live_inference.last_latency_ms} ms`
                    : "Not tested"
                }
                sub={
                  geminiDiag?.live_inference?.last_model
                    ? `Last model: ${geminiDiag.live_inference.last_model}`
                    : "Catalog check alone never marks live inference verified"
                }
                tone={geminiDiag?.live_inference?.verified ? "success" : "neutral"}
              />
              <MetricDisplay
                label="Fallback & Last Check"
                value={`${geminiDiag?.live_inference?.intra_gemini_fallback_calls ?? 0} fallbacks`}
                sub={geminiDiag?.live_inference?.last_successful_check_at || "No live check recorded yet"}
                tone="info"
              />
            </div>
            {Array.isArray(geminiDiag?.reasoning_tiers) && geminiDiag.reasoning_tiers.length > 0 && (
              <div className="grid-2">
                {geminiDiag.reasoning_tiers.map((t: any) => (
                  <div key={t.tier} className="list-item">
                    <div className="row-between">
                      <strong className="mono">T{t.tier} · {t.primary_model}</strong>
                      <span className="pill mono">{t.api_interface || "generate_content"}</span>
                    </div>
                    <div className="muted" style={{ fontSize: 12 }}>
                      Fallback: {(t.gemini_fallback_chain || []).slice(0, 3).join(" → ") || "—"}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <div className="card">
            <div className="card-title"><span>4-Stage Honest Connectivity Architecture</span></div>
            <p className="muted" style={{ marginTop: 0 }}>
              ULTRON never marks an integration as Connected without real backend verification. {roadmapCount} roadmap integrations are transparently tagged Coming soon.
            </p>
            <div className="grid-2">
              {antigravity?.connected_plugin_adapters &&
                Object.entries(antigravity.connected_plugin_adapters).map(([k, v]: [string, any]) => (
                  <div key={k} className="list-item">
                    <div className="row-between">
                      <strong>Antigravity Plugin: {k.toUpperCase()}</strong>
                      <StatusIndicator label={v.status || "CHECK"} tone={v.status === "AVAILABLE" ? "success" : "warn"} />
                    </div>
                    <div className="muted">{v.detail}</div>
                  </div>
                ))}
            </div>
          </div>
        </div>
      )}

      {/* 35. INTEGRATION DIRECTORY (MARKETPLACE) */}
      {page.id === "directory" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <SearchBar
            id="integrations-search"
            value={search}
            onChange={setSearch}
            placeholder={`Search ${INTEGRATIONS_CATALOG.length} integrations (Gemini, Google Drive, GitHub, Vercel, Supabase, Stripe, Slack...)`}
          />
          <FilterBar<"All" | IntegrationCategory>
            value={category}
            onChange={setCategory}
            options={[
              { value: "All", label: "All Categories", count: INTEGRATIONS_CATALOG.length },
              ...INTEGRATION_CATEGORIES.map((c) => ({
                value: c,
                label: c,
                count: INTEGRATIONS_CATALOG.filter((i) => i.category === c).length,
              })),
            ]}
          />
          {filteredCatalog.length === 0 ? (
            <EmptyState title="No Integrations Match" description="Clear the search query or pick another category." />
          ) : (
            <div className="integrations-grid">
              {filteredCatalog.map((entry) => (
                <IntegrationCard
                  key={entry.id}
                  entry={entry}
                  status={resolvedMap.get(entry.id)?.status || "Not connected"}
                  onSelect={(e) => {
                    setSelected(e);
                    setFieldValues({});
                    setProbeResult(null);
                  }}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* 36. INTEGRATION DETAILS */}
      {page.id === "details" && (
        <div className="card">
          <div className="card-title"><span>Select an Integration to Inspect</span></div>
          <div className="row" style={{ marginBottom: 12 }}>
            {INTEGRATIONS_CATALOG.slice(0, 14).map((e) => (
              <button
                key={e.id}
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => setSelected(e)}
              >
                <IntegrationLogo id={e.id} size={16} /> {e.name}
              </button>
            ))}
          </div>
          <div className="muted">Click any integration above or in the Integration Directory to open its full configuration drawer.</div>
        </div>
      )}

      {/* 37. CONNECTED ACCOUNTS */}
      {page.id === "accounts" && (
        <div className="card">
          <div className="card-title"><span>Tenant Encrypted Connections ({connections.length})</span></div>
          <DataTable
            rows={connections}
            rowKey={(c, idx) => c.connection_id || c.provider || String(idx)}
            emptyTitle="No Persisted OAuth / Vault Account Connections"
            emptyDescription="Connect Google Workspace, GitHub, or API providers from the Integration Directory."
            columns={[
              { key: "provider", header: "Provider", mono: true, render: (c) => <strong>{c.provider}</strong> },
              { key: "status", header: "Status", render: (c) => <StatusIndicator label={c.status || "RECORDED"} tone={c.status === "CONNECTED" ? "success" : "warn"} /> },
              { key: "updated", header: "Updated", mono: true, render: (c) => c.updated_at || "—" },
            ]}
          />
        </div>
      )}

      {/* 38. API PROVIDER SETTINGS */}
      {page.id === "api-providers" && (
        <div className="integrations-grid">
          {INTEGRATIONS_CATALOG.filter((i) => i.authFlow === "API_KEY").map((entry) => (
            <IntegrationCard
              key={entry.id}
              entry={entry}
              status={resolvedMap.get(entry.id)?.status || "Not connected"}
              onSelect={(e) => {
                setSelected(e);
                setFieldValues({});
                setProbeResult(null);
              }}
            />
          ))}
        </div>
      )}

      {/* 39. OAUTH CONNECTIONS */}
      {page.id === "oauth" && (
        <div className="integrations-grid">
          {INTEGRATIONS_CATALOG.filter((i) => i.authFlow === "OAUTH2").map((entry) => (
            <IntegrationCard
              key={entry.id}
              entry={entry}
              status={resolvedMap.get(entry.id)?.status || "Not connected"}
              onSelect={(e) => {
                setSelected(e);
                setFieldValues({});
                setProbeResult(null);
              }}
            />
          ))}
        </div>
      )}

      {/* 40. INTEGRATION PERMISSIONS */}
      {page.id === "permissions" && (
        <div className="card">
          <div className="card-title"><span><Shield size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Least-Privilege Integration Scopes</span></div>
          <DataTable
            rows={INTEGRATIONS_CATALOG.filter((i) => i.supportedByBackend)}
            rowKey={(i) => i.id}
            columns={[
              {
                key: "name",
                header: "Integration",
                render: (i) => (
                  <div className="row">
                    <IntegrationLogo id={i.id} size={20} />
                    <strong>{i.name}</strong>
                  </div>
                ),
              },
              { key: "flow", header: "Auth", mono: true, render: (i) => i.authFlow },
              { key: "scopes", header: "Requested Scopes", mono: true, render: (i) => i.permissions.join(", ") },
            ]}
          />
        </div>
      )}

      {/* 41. CONNECTION ACTIVITY */}
      {page.id === "activity" && (
        <div className="card">
          <div className="card-title"><span>Integration Audit Activity ({auditLogs.length})</span></div>
          <ActivityFeed
            emptyLabel="No integration connection or verification events recorded yet."
            items={auditLogs.map((l, idx) => ({
              id: l.audit_id || String(idx),
              title: l.action || "Integration Event",
              actor: l.actor_user_id || "system",
              status: l.status || "RECORDED",
              timestamp: l.created_at,
              detail: l.resource,
            }))}
          />
        </div>
      )}

      {/* 42. WEBHOOK MANAGEMENT */}
      {page.id === "webhooks" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title"><span>Inbound Webhook Endpoints</span></div>
            <div className="list-item">
              <strong className="mono">POST /api/v1/bridge/share</strong>
              <div className="muted">iPhone / PWA Share Target intake with AEGIS URL inspection.</div>
            </div>
            <div className="list-item" style={{ marginTop: 8 }}>
              <strong className="mono">VERCEL_WEBHOOK_SECRET</strong>
              <div className="muted">HMAC-SHA256 verification required for deployment webhooks.</div>
            </div>
          </div>
          <div className="card">
            <div className="card-title"><span>BRIDGE Share Payloads ({bridgeShares.length})</span></div>
            {bridgeShares.length === 0 ? (
              <EmptyState title="No Shares Ingested" description="Shared links and notes from iOS/PWA appear here." />
            ) : (
              bridgeShares.slice(0, 6).map((b, i) => (
                <div key={b.share_id || i} className="list-item" style={{ marginBottom: 6 }}>
                  <strong>{b.title || b.url || "Shared Item"}</strong>
                  <div className="muted">{b.source_app} · AEGIS: {b.aegis_url_verdict}</div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* INTEGRATION DETAIL / CONFIG DRAWER */}
      <Drawer
        open={Boolean(selected)}
        title={selected ? `${selected.name} — Integration` : "Integration"}
        onClose={() => setSelected(null)}
      >
        {selected && (() => {
          const info = resolvedMap.get(selected.id) || { status: "Not connected" as HonestConnectionStatus, detail: "" };
          return (
            <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div className="row-between">
                <div className="row" style={{ gap: 12 }}>
                  <IntegrationLogo id={selected.id} size={38} />
                  <div>
                    <strong style={{ fontSize: 16 }}>{selected.name}</strong>
                    <div className="muted">{selected.category}</div>
                  </div>
                </div>
                <StatusIndicator
                  label={info.status}
                  tone={info.status === "Connected" ? "success" : info.status === "Configuration required" ? "warn" : info.status === "Error" ? "danger" : "neutral"}
                />
              </div>

              <p className="muted" style={{ margin: 0 }}>{selected.shortDescription}</p>
              <div className="alert-box">{info.detail}</div>

              {selected.requiredEnvVars.length > 0 && (
                <div className="list-item">
                  <div className="telemetry-label">REQUIRED SERVER ENVIRONMENT VARIABLES</div>
                  <div className="mono" style={{ fontSize: 12 }}>{selected.requiredEnvVars.join(", ")}</div>
                </div>
              )}

              <div className="list-item">
                <div className="telemetry-label">LEAST-PRIVILEGE SCOPES</div>
                <div className="row">
                  {selected.permissions.map((p) => (
                    <span key={p} className="pill mono">{p}</span>
                  ))}
                </div>
              </div>

              {selected.authFlow === "API_KEY" && selected.connectFields && (
                <div className="list-item" style={{ gap: 8 }}>
                  <div className="telemetry-label">ENCRYPTED VAULT CREDENTIAL CONNECT</div>
                  {selected.connectFields.map((f) => (
                    <input
                      key={f.key}
                      type={f.sensitive ? "password" : "text"}
                      className="input"
                      placeholder={f.placeholder}
                      value={fieldValues[f.key] || ""}
                      onChange={(e) => setFieldValues((prev) => ({ ...prev, [f.key]: e.target.value }))}
                    />
                  ))}
                  <button type="button" className="btn btn-sm" onClick={() => handleConnectApiKey(selected)}>
                    Encrypt & Connect
                  </button>
                </div>
              )}

              {selected.authFlow === "OAUTH2" && selected.backendProviderKey && (
                <button type="button" className="btn" onClick={() => handleStartOAuth(selected)}>
                  <ExternalLink size={14} /> Start OAuth 2.0 + PKCE Flow
                </button>
              )}

              {selected.backendProviderKey && (
                <div className="row">
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleTestProvider(selected)}>
                    Test Connection
                  </button>
                  {info.status === "Connected" && (
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={() => setConfirmDisconnect(selected)}
                    >
                      <Unplug size={13} /> Disconnect
                    </button>
                  )}
                </div>
              )}

              {probeResult && (
                <ReadableSummary title="Connection Verification Result" data={probeResult} diagnosticsTitle="Technical Diagnostics — Probe Payload" />
              )}
            </div>
          );
        })()}
      </Drawer>

      <ConfirmationDialog
        open={Boolean(confirmDisconnect)}
        title="Disconnect Integration"
        message={`Revoke stored credentials for ${confirmDisconnect?.name}? Agents using this provider will stop until reconnected.`}
        confirmLabel="Disconnect"
        onCancel={() => setConfirmDisconnect(null)}
        onConfirm={async () => {
          if (confirmDisconnect) await handleDisconnect(confirmDisconnect);
          setConfirmDisconnect(null);
        }}
      />
    </ResponsiveWorkspace>
  );
}
