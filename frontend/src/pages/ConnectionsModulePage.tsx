import React, { useEffect, useMemo, useState } from "react";
import {
  CheckCircle2,
  ExternalLink,
  KeyRound,
  Play,
  RefreshCw,
  RotateCw,
  Shield,
  Unplug,
} from "lucide-react";
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
import { AdminOAuthSetupPanel } from "../components/integrations/AdminOAuthSetupPanel";
import { UniversalConnectPanel } from "../components/integrations/UniversalConnectPanel";
import { GeminiConnectionCard } from "../components/integrations/GeminiConnectionCard";
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

const PRIORITY_IDS = ["gemini", "google_antigravity", "google_drive", "github", "supabase", "google_gmail", "google_calendar"];
const PENDING_OAUTH_KEY = "ultron_pending_oauth_provider";

function statusTone(status: HonestConnectionStatus): "success" | "info" | "warn" | "danger" | "neutral" {
  switch (status) {
    case "Live Verified":
      return "success";
    case "Authenticated":
      return "info";
    case "Configured":
      return "warn";
    case "Authentication expired":
    case "Error":
      return "danger";
    default:
      return "neutral";
  }
}

function stageIndex(status: HonestConnectionStatus): number {
  if (status === "Live Verified") return 4;
  if (status === "Authenticated") return 3;
  if (status === "Configured") return 2;
  if (status === "Supported") return 1;
  return 0;
}

/**
 * Strictly computes the 4-stage lifecycle status from real backend responses.
 * NEVER marks an integration as Live Verified merely because environment variables exist.
 */
function resolveHonestStatus(
  entry: IntegrationCatalogEntry,
  statusData: any,
  connections: any[],
  health: any,
  geminiDiag: any
): { status: HonestConnectionStatus; detail: string; record?: any; lastVerifiedAt?: string | null } {
  if (!entry.supportedByBackend || entry.authFlow === "ROADMAP") {
    return {
      status: "Coming soon",
      detail: "Planned integration on the ULTRON roadmap. No backend adapter is active yet.",
    };
  }

  const record = connections.find(
    (c) => c.provider === entry.backendProviderKey || c.provider === entry.id
  );

  // Special live-verified check for Gemini via diagnostics endpoint
  if (entry.id === "gemini" && geminiDiag?.live_inference?.verified) {
    return {
      status: "Live Verified",
      detail: `Live verified on ${geminiDiag.live_inference.last_model || "Gemini"} (${geminiDiag.live_inference.last_latency_ms ?? "—"} ms).`,
      record,
      lastVerifiedAt: geminiDiag.live_inference.last_successful_check_at || record?.last_verified_at || null,
    };
  }

  // Special check for Google Antigravity runtime environment
  if (entry.id === "google_antigravity") {
    const agEnv = statusData?.antigravity_environment;
    if (agEnv?.runtime_detected) {
      const connected = Object.keys(agEnv.connected_plugin_adapters || {}).join(", ");
      return {
        status: "Live Verified",
        detail: `Antigravity VM active. Plugin bridges detected: ${connected || "Standard toolchain"}. Approval gates active for destructive tasks.`,
        record: {
          account_label: "Google Antigravity Dedicated Linux VM",
          provider: "google_antigravity",
          status: "AVAILABLE",
        },
        lastVerifiedAt: new Date().toISOString(),
      };
    }
    return {
      status: "Configured",
      detail: "Antigravity runtime adapter ready; active when running within an Antigravity VM session.",
    };
  }

  // Special live-verified check for PostgreSQL database
  if (entry.id === "postgresql" && (health?.database?.connected || health?.database?.healthy)) {
    return {
      status: "Live Verified",
      detail: "PostgreSQL Transaction Pooler live connection verified.",
      record,
      lastVerifiedAt: health?.timestamp || null,
    };
  }

  if (record) {
    const st = String(record.status || "").toUpperCase();
    const stage = String(record.lifecycle_stage || "").toUpperCase();

    if (record.token_expired || st === "EXPIRED" || stage === "EXPIRED") {
      return {
        status: "Authentication expired",
        detail: "OAuth token expired — refresh token or reconnect.",
        record,
        lastVerifiedAt: record.last_verified_at,
      };
    }
    if (stage === "LIVE_VERIFIED" || st === "AVAILABLE" || st === "VERIFIED") {
      return {
        status: "Live Verified",
        detail: record.account_label
          ? `Live verified (${record.account_label}).`
          : "Outbound health check passed; credentials encrypted in VAULT.",
        record,
        lastVerifiedAt: record.last_verified_at,
      };
    }
    if (st === "DEGRADED" || st === "ERROR" || st === "FAILED") {
      return {
        status: "Error",
        detail: record.last_error || "Last live verification probe failed.",
        record,
        lastVerifiedAt: record.last_verified_at,
      };
    }
    if (stage === "AUTHENTICATED" || (record.connection_id && !record.disconnected_at)) {
      return {
        status: "Authenticated",
        detail: "Encrypted tenant credentials stored in VAULT. Run Test Connection to live-verify.",
        record,
        lastVerifiedAt: record.last_verified_at,
      };
    }
    if (stage === "CONFIGURED" || record.configured_via_env) {
      return {
        status: "Configured",
        detail: "Server configuration detected; awaiting tenant authentication or live verification.",
        record,
        lastVerifiedAt: record.last_verified_at,
      };
    }
  }

  // Check /api/v1/integrations/status capabilities
  const cap = entry.statusCapabilityKey ? statusData?.capabilities?.[entry.statusCapabilityKey] : null;
  if (cap) {
    if (cap.verified === true || cap.capability_state === "AVAILABLE") {
      return {
        status: "Live Verified",
        detail: cap.detail || "Live verified via backend IntegrationManager.",
      };
    }
    if (cap.configured === true && !cap.verified) {
      return {
        status: "Configured",
        detail: cap.detail || "Server configuration present — run Verify Live Status to test outbound connectivity.",
      };
    }
    if (cap.missing_env_vars?.length > 0) {
      return {
        status: "Supported",
        detail: `Connector implemented. Missing: ${cap.missing_env_vars.join(", ")}`,
      };
    }
  }

  // Check /health providers (configured != live verified!)
  const hp =
    health?.integrations?.capabilities?.[entry.id] ||
    health?.integrations?.providers?.[entry.id] ||
    health?.providers?.[entry.id];
  if (hp) {
    if (hp.live_verified) {
      return { status: "Live Verified", detail: hp.detail || "Live verified on backend." };
    }
    if (hp.configured) {
      return { status: "Configured", detail: hp.detail || "Configured on server — awaiting live verification." };
    }
  }

  return {
    status: "Supported",
    detail: entry.authFlow === "OAUTH2"
      ? `${entry.name} setup is not yet available. Administrator configuration is required.`
      : "Connector supported — connect via encrypted VAULT credentials.",
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
  const [stageFilter, setStageFilter] = useState<"ALL" | HonestConnectionStatus>("ALL");
  const [selected, setSelected] = useState<IntegrationCatalogEntry | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [oauthCode, setOauthCode] = useState("");
  const [oauthState, setOauthState] = useState("");
  const [oauthAuthUrl, setOauthAuthUrl] = useState("");
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
        apiFetch<any>("/api/v1/audit/logs?limit=40").catch(() => ({ logs: [] })),
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
    const map = new Map<string, { status: HonestConnectionStatus; detail: string; record?: any; lastVerifiedAt?: string | null }>();
    for (const entry of INTEGRATIONS_CATALOG) {
      map.set(entry.id, resolveHonestStatus(entry, statusData, connections, health, geminiDiag));
    }
    return map;
  }, [statusData, connections, health, geminiDiag]);

  async function verifyAll() {
    setVerifying(true);
    try {
      const res = await apiFetch<any>("/api/v1/integrations/verify", { method: "POST" });
      setStatusData(res);
      await load();
      pushToast("Live outbound integration verification complete.", "success");
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
      pushToast(`${entry.name} encrypted & saved in backend VAULT (Stage 3: Authenticated).`, "success");
      await load();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function handleStartOAuth(entry: IntegrationCatalogEntry) {
    if (!entry.backendProviderKey) return;
    try {
      sessionStorage.setItem("ultron_pending_oauth_provider", entry.backendProviderKey);
      const res = await apiFetch<any>(`/api/v1/integrations/oauth/${entry.backendProviderKey}/start`, {
        method: "POST",
        body: { redirect_uri: `${window.location.origin}/oauth/callback` },
      });
      if (res.authorization_url) {
        window.location.assign(res.authorization_url);
      }
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function handleCompleteOAuthCallback(entry: IntegrationCatalogEntry) {
    if (!entry.backendProviderKey || !oauthCode.trim() || !oauthState.trim()) return;
    try {
      await apiFetch(`/api/v1/integrations/oauth/${entry.backendProviderKey}/callback`, {
        method: "POST",
        body: { code: oauthCode.trim(), state: oauthState.trim() },
      });
      setOauthCode("");
      setOauthAuthUrl("");
      pushToast(`${entry.name} OAuth tokens encrypted & stored in VAULT.`, "success");
      await load();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function handleRefreshToken(providerKey: string) {
    try {
      await apiFetch(`/api/v1/integrations/${providerKey}/refresh`, { method: "POST" });
      pushToast(`OAuth token refreshed for ${providerKey}.`, "success");
      await load();
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
      pushToast(
        res.live_verified
          ? `${entry.name} live verification PASSED.`
          : `${entry.name}: ${res.detail || "Verification failed."}`,
        res.live_verified ? "success" : "info"
      );
      await load();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function handleDisconnect(entry: IntegrationCatalogEntry) {
    if (!entry.backendProviderKey) return;
    try {
      await apiFetch(`/api/v1/integrations/${entry.backendProviderKey}/disconnect`, { method: "POST" });
      pushToast(`${entry.name} disconnected and VAULT credentials cleared.`, "success");
      setProbeResult(null);
      setOauthAuthUrl("");
      await load();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  const filteredCatalog = INTEGRATIONS_CATALOG.filter((item) => {
    if (category !== "All" && item.category !== category) return false;
    const st = resolvedMap.get(item.id)?.status || "Supported";
    if (stageFilter !== "ALL" && st !== stageFilter) return false;
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      item.name.toLowerCase().includes(q) ||
      item.category.toLowerCase().includes(q) ||
      item.shortDescription.toLowerCase().includes(q)
    );
  });

  const supportedCount = INTEGRATIONS_CATALOG.filter((i) => i.supportedByBackend).length;
  const configuredCount = INTEGRATIONS_CATALOG.filter((i) => resolvedMap.get(i.id)?.status === "Configured").length;
  const authenticatedCount = INTEGRATIONS_CATALOG.filter((i) => resolvedMap.get(i.id)?.status === "Authenticated").length;
  const liveVerifiedCount = INTEGRATIONS_CATALOG.filter((i) => resolvedMap.get(i.id)?.status === "Live Verified").length;
  const persistedVaultAccounts = connections.filter((c) => Boolean(c.connection_id));

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`CONNECTIONS CENTRE // PAGE ${page.number} · ${INTEGRATIONS_CATALOG.length} INTEGRATIONS`}
        title={page.label}
        description={page.description}
        actions={
          <div className="row" style={{ gap: 8 }}>
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
          <div className="grid-4">
            <MetricDisplay label="Stage 1: Supported" value={supportedCount} sub={`Out of ${INTEGRATIONS_CATALOG.length} catalogued`} tone="neutral" />
            <MetricDisplay label="Stage 2: Configured" value={configuredCount} sub="Env config present, unverified" tone="warn" />
            <MetricDisplay label="Stage 3: Authenticated" value={authenticatedCount} sub="Encrypted in VAULT, run test" tone="info" />
            <MetricDisplay label="Stage 4: Live Verified" value={liveVerifiedCount} sub="Outbound health check passed" tone={liveVerifiedCount > 0 ? "success" : "neutral"} />
          </div>

          {/* Dedicated Google Gemini Connection Center Centerpiece */}
          <GeminiConnectionCard onStatusChange={() => load()} />

          {/* Priority Integrations Matrix */}
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="card-title">
              <span>Priority Operational Integrations</span>
              <span className="muted mono" style={{ fontSize: 11 }}>4-STAGE STRICT LIFECYCLE</span>
            </div>
            <div className="grid-2">
              {PRIORITY_IDS.map((pid) => {
                const entry = INTEGRATIONS_CATALOG.find((i) => i.id === pid);
                if (!entry) return null;
                const info = resolvedMap.get(entry.id) || { status: "Supported" as HonestConnectionStatus, detail: "" };
                return (
                  <div key={entry.id} className="list-item" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <div className="row-between" style={{ gap: 8 }}>
                      <div className="row" style={{ gap: 10 }}>
                        <IntegrationLogo id={entry.id} size={28} />
                        <div>
                          <strong>{entry.name}</strong>
                          <div className="muted mono" style={{ fontSize: 11 }}>{entry.authFlow}</div>
                        </div>
                      </div>
                      <StatusIndicator label={info.status} tone={statusTone(info.status)} />
                    </div>
                    <div className="muted" style={{ fontSize: 12 }}>{info.detail}</div>
                    <div className="row-between" style={{ gap: 8, flexWrap: "wrap" }}>
                      <span className="muted mono" style={{ fontSize: 10.5 }}>
                        {info.lastVerifiedAt ? `Verified: ${info.lastVerifiedAt.slice(0, 19).replace("T", " ")}` : "Not yet live-verified"}
                      </span>
                      <div className="row" style={{ gap: 6 }}>
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleTestProvider(entry)}>
                          <Play size={11} /> Test
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => {
                            setSelected(entry);
                            setFieldValues({});
                            setProbeResult(null);
                            setOauthAuthUrl("");
                          }}
                        >
                          Manage
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          <div className="card">
            <div className="card-title">
              <span>Google Gemini Primary Intelligence Diagnostics</span>
              <StatusIndicator
                label={geminiDiag?.live_inference?.status || (geminiDiag?.configured ? "CONFIGURED" : "UNCONFIGURED")}
                tone={geminiDiag?.live_inference?.verified ? "success" : geminiDiag?.configured ? "warn" : "neutral"}
              />
            </div>
            <div className="grid-3" style={{ marginBottom: 12 }}>
              <MetricDisplay
                label="Primary Provider"
                value={geminiDiag?.provider_label || "Google Gemini"}
                sub={`API: ${geminiDiag?.api_mode || "generate_content"} · Models: ${geminiDiag?.catalog?.models_discovered ?? 0}`}
                tone={geminiDiag?.configured ? "info" : "warn"}
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
                    : "Env config alone never marks Live Verified"
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
          </div>

          <UniversalConnectPanel onChanged={load} />

          {antigravity?.connected_plugin_adapters && (
            <div className="card">
              <div className="card-title"><span>Antigravity Plugin Adapters</span></div>
              <div className="grid-2">
                {Object.entries(antigravity.connected_plugin_adapters).map(([k, v]: [string, any]) => (
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
          )}
        </div>
      )}

      {/* 35. INTEGRATION DIRECTORY */}
      {page.id === "directory" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <SearchBar
            id="integrations-search"
            value={search}
            onChange={setSearch}
            placeholder={`Search ${INTEGRATIONS_CATALOG.length} integrations (Gemini, Google Drive, GitHub, Supabase, Gmail, Calendar...)`}
          />
          <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
            {(["ALL", "Live Verified", "Authenticated", "Configured", "Supported", "Error", "Coming soon"] as const).map((st) => (
              <button
                key={st}
                type="button"
                className={`seg-btn ${stageFilter === st ? "active" : ""}`}
                onClick={() => setStageFilter(st)}
              >
                {st}
              </button>
            ))}
          </div>
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
            <EmptyState title="No Integrations Match" description="Clear the search query or pick another category/stage." />
          ) : (
            <div className="integrations-grid">
              {filteredCatalog.map((entry) => (
                <IntegrationCard
                  key={entry.id}
                  entry={entry}
                  status={resolvedMap.get(entry.id)?.status || "Supported"}
                  onSelect={(e) => {
                    setSelected(e);
                    setFieldValues({});
                    setProbeResult(null);
                    setOauthAuthUrl("");
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
          <div className="row" style={{ marginBottom: 12, flexWrap: "wrap", gap: 8 }}>
            {INTEGRATIONS_CATALOG.slice(0, 14).map((e) => (
              <button
                key={e.id}
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setSelected(e);
                  setFieldValues({});
                  setProbeResult(null);
                  setOauthAuthUrl("");
                }}
              >
                <IntegrationLogo id={e.id} size={16} /> {e.name}
              </button>
            ))}
          </div>
          <div className="muted">Click any integration above or in the Integration Directory to open its full 4-stage lifecycle drawer.</div>
        </div>
      )}

      {/* 37. CONNECTED ACCOUNTS */}
      {page.id === "accounts" && (
        <div className="card">
          <div className="card-title"><span>Tenant Encrypted VAULT &amp; OAuth Accounts ({persistedVaultAccounts.length})</span></div>
          <DataTable
            rows={persistedVaultAccounts}
            rowKey={(c, idx) => c.connection_id || c.provider || String(idx)}
            emptyTitle="No Persisted OAuth / Vault Account Connections"
            emptyDescription="Connect Google Workspace, GitHub, or API providers from the Integration Directory."
            columns={[
              { key: "provider", header: "Provider", mono: true, render: (c) => <strong>{c.provider}</strong> },
              {
                key: "stage",
                header: "Lifecycle Stage",
                render: (c) => (
                  <StatusIndicator
                    label={c.lifecycle_stage || c.status || "AUTHENTICATED"}
                    tone={c.lifecycle_stage === "LIVE_VERIFIED" ? "success" : c.token_expired ? "danger" : "info"}
                  />
                ),
              },
              { key: "verified", header: "Last Verified", mono: true, render: (c) => c.last_verified_at ? c.last_verified_at.slice(0, 19).replace("T", " ") : "Never" },
              {
                key: "actions",
                header: "Controls",
                render: (c) => {
                  const entry = INTEGRATIONS_CATALOG.find((i) => i.backendProviderKey === c.provider);
                  return (
                    <div className="row" style={{ gap: 6 }}>
                      {entry && (
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleTestProvider(entry)}>
                          <Play size={11} /> Test
                        </button>
                      )}
                      {c.auth_type === "OAUTH2" && (
                        <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleRefreshToken(c.provider)}>
                          <RotateCw size={11} /> Refresh
                        </button>
                      )}
                      {entry && (
                        <button type="button" className="btn btn-danger btn-sm" onClick={() => setConfirmDisconnect(entry)}>
                          <Unplug size={11} /> Revoke
                        </button>
                      )}
                    </div>
                  );
                },
              },
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
              status={resolvedMap.get(entry.id)?.status || "Supported"}
              onSelect={(e) => {
                setSelected(e);
                setFieldValues({});
                setProbeResult(null);
                setOauthAuthUrl("");
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
              status={resolvedMap.get(entry.id)?.status || "Supported"}
              onSelect={(e) => {
                setSelected(e);
                setFieldValues({});
                setProbeResult(null);
                setOauthAuthUrl("");
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
              title: `${l.action || "Integration Event"} (${l.resource || "system"})`,
              actor: l.actor || l.actor_user_id || "system",
              status: l.outcome || l.status || "RECORDED",
              timestamp: l.created_at,
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
          const info = resolvedMap.get(selected.id) || { status: "Supported" as HonestConnectionStatus, detail: "" };
          const activeStage = stageIndex(info.status);
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
                <StatusIndicator label={info.status} tone={statusTone(info.status)} />
              </div>

              {/* 4-Stage Lifecycle Stepper */}
              <div className="grid-4" style={{ gap: 6 }}>
                {[
                  { n: 1, label: "1. Supported" },
                  { n: 2, label: "2. Configured" },
                  { n: 3, label: "3. Authenticated" },
                  { n: 4, label: "4. Live Verified" },
                ].map((s) => (
                  <div
                    key={s.n}
                    className="list-item"
                    style={{
                      padding: "6px 8px",
                      textAlign: "center",
                      fontSize: 11,
                      borderColor: activeStage >= s.n ? "var(--accent, #22d3ee)" : undefined,
                      opacity: activeStage >= s.n ? 1 : 0.55,
                    }}
                  >
                    <strong>{s.label}</strong>
                  </div>
                ))}
              </div>

              <p className="muted" style={{ margin: 0 }}>{selected.shortDescription}</p>
              {(selected.setupInstructions || selected.docsUrl) && (
                <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div className="telemetry-label">ACTIVATION INSTRUCTIONS</div>
                  {selected.setupInstructions && (
                    <div className="muted" style={{ fontSize: 12, lineHeight: 1.45 }}>
                      {selected.setupInstructions}
                    </div>
                  )}
                  {selected.docsUrl && (
                    <a
                      href={selected.docsUrl}
                      target="_blank"
                      rel="noreferrer noopener"
                      className="btn btn-secondary btn-sm"
                      style={{ alignSelf: "flex-start" }}
                    >
                      <ExternalLink size={12} /> Provider Documentation
                    </a>
                  )}
                </div>
              )}
              <div className="alert-box">
                <div>{info.detail}</div>
                {info.lastVerifiedAt && (
                  <div className="muted mono" style={{ fontSize: 11, marginTop: 4 }}>
                    Last Verified: {info.lastVerifiedAt}
                  </div>
                )}
              </div>

              <div className="list-item">
                <div className="telemetry-label">LEAST-PRIVILEGE SCOPES</div>
                <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                  {selected.permissions.map((p) => (
                    <span key={p} className="pill mono">{p}</span>
                  ))}
                </div>
              </div>

              {(selected.authFlow === "API_KEY" || (selected.authFlow === "OAUTH2" && Boolean(selected.connectFields?.length))) &&
                selected.connectFields && (
                <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div className="telemetry-label">
                    <KeyRound size={12} style={{ verticalAlign: "middle", marginRight: 4 }} />
                    VAULT CREDENTIAL CONNECT / ROTATE
                  </div>
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
                    Encrypt &amp; Save in VAULT
                  </button>
                </div>
              )}

              {selected.authFlow === "OAUTH2" && selected.backendProviderKey && (
                <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <div className="telemetry-label">OAUTH 2.0 + PKCE AUTHORIZATION</div>
                  <AdminOAuthSetupPanel
                    entry={selected}
                    oauthReady={Boolean(info.record?.oauth_client_configured)}
                    onConfigured={load}
                  />
                  <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                    <button
                      type="button"
                      className="btn btn-sm"
                      disabled={!info.record?.oauth_client_configured}
                      onClick={() => handleStartOAuth(selected)}
                    >
                      <ExternalLink size={13} /> {info.record?.connection_id ? "Reauthorize in Browser" : "Configure"}
                    </button>
                    {info.record?.connection_id && (
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleRefreshToken(selected.backendProviderKey!)}>
                        <RotateCw size={13} /> Refresh Token
                      </button>
                    )}
                  </div>
                </div>
              )}

              {selected.authFlow === "SERVER_ENV" && (
                <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div className="telemetry-label">SERVER-MANAGED CONFIGURATION</div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {selected.id === "supabase"
                      ? "Requires server-side Supabase Project URL (SUPABASE_URL), backend-only service-role key (SUPABASE_SERVICE_ROLE_KEY — never exposed to frontend), and Transaction Pooler / Supavisor connection string (ULTRON_DATABASE_URL) with migration and RLS permissions."
                      : selected.id === "webhooks" || selected.id === "rest_apis" || selected.id === "mcp"
                      ? "Server-level defaults are managed by the backend runtime. Register custom MCP servers, signed webhooks, or custom REST APIs in Universal Connections Centre 2.0."
                      : "Managed via server environment configuration. Use Run Health Check below to verify live runtime connectivity."}
                  </div>
                  {selected.requiredEnvVars.length > 0 && (
                    <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                      {selected.requiredEnvVars.map((envVar) => (
                        <span key={envVar} className="pill mono" style={{ fontSize: 11 }}>{envVar}</span>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {selected.backendProviderKey && (
                <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleTestProvider(selected)}>
                    <Play size={12} /> Run Health Check
                  </button>
                  {info.record?.connection_id && !info.record?.disconnected_at && (
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={() => setConfirmDisconnect(selected)}
                    >
                      <Unplug size={13} /> Disconnect &amp; Revoke
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
        title="Disconnect & Revoke Integration"
        message={`Revoke stored VAULT credentials and OAuth tokens for ${confirmDisconnect?.name}? Agents using this provider will stop until reconnected.`}
        confirmLabel="Disconnect & Revoke"
        onCancel={() => setConfirmDisconnect(null)}
        onConfirm={async () => {
          if (confirmDisconnect) await handleDisconnect(confirmDisconnect);
          setConfirmDisconnect(null);
        }}
      />
    </ResponsiveWorkspace>
  );
}
