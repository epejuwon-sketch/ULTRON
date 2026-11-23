import React, { useEffect, useState } from "react";
import {
  CheckCircle2,
  ExternalLink,
  Globe,
  KeyRound,
  Link2,
  Plus,
  RefreshCw,
  RotateCw,
  Search,
  ShieldCheck,
  Trash2,
  Webhook,
} from "lucide-react";
import { apiFetch } from "../../lib/api";
import { DataTable, Drawer, StatusIndicator, useToast } from "../ui/DesignSystem";

function lifecycleTone(state: string): "success" | "info" | "warn" | "danger" | "neutral" {
  switch (state) {
    case "LIVE_VERIFIED":
    case "CONNECTED":
      return "success";
    case "AUTHENTICATED":
    case "DISCOVERED":
      return "info";
    case "AWAITING_AUTHORIZATION":
    case "CONFIGURATION_REQUIRED":
    case "DEGRADED":
      return "warn";
    case "EXPIRED":
    case "REVOKED":
    case "FAILED":
      return "danger";
    default:
      return "neutral";
  }
}

export function UniversalConnectPanel({ onChanged }: { onChanged?: () => void }) {
  const { pushToast } = useToast();
  const [catalogue, setCatalogue] = useState<any[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [connectOpen, setConnectOpen] = useState(false);
  const [configConnector, setConfigConnector] = useState<any>(null);
  const [deliveries, setDeliveries] = useState<any[]>([]);

  // Connect form state
  const [method, setMethod] = useState<"API_KEY" | "OAUTH2" | "WEBSITE" | "WEBHOOK">("API_KEY");
  const [svcName, setSvcName] = useState("");
  const [svcCategory, setSvcCategory] = useState("Custom websites and APIs");
  const [websiteUrl, setWebsiteUrl] = useState("");
  const [docsUrl, setDocsUrl] = useState("");
  const [apiBaseUrl, setApiBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [scopesText, setScopesText] = useState("");
  const [capsText, setCapsText] = useState("");
  const [webhookSecret, setWebhookSecret] = useState("");
  const [eventsText, setEventsText] = useState("order.created, payment.succeeded");
  const [inspectResult, setInspectResult] = useState<any>(null);
  const [rotateKey, setRotateKey] = useState("");
  const [rotateWhSecret, setRotateWhSecret] = useState("");

  async function loadCatalogue() {
    try {
      const qs = new URLSearchParams();
      if (query.trim()) qs.set("query", query.trim());
      if (selectedCategory) qs.set("category", selectedCategory);
      const res = await apiFetch<any>(`/api/v1/integrations/universal/catalogue?${qs.toString()}`);
      setCatalogue(res.connectors || []);
      setCategories(res.categories || []);
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    loadCatalogue();
  }, [query, selectedCategory]);

  async function handleInspectWebsite() {
    if (!websiteUrl.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/integrations/universal/website-inspect", {
        method: "POST",
        body: { website_url: websiteUrl.trim() },
      });
      setInspectResult(res);
      if (!svcName.trim() && res.name) setSvcName(res.name);
      if (!docsUrl.trim() && res.docs_url) setDocsUrl(res.docs_url);
      pushToast(`Inspected ${res.website_url} (state: DISCOVERED, not authenticated).`, "info");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function handleCreateConnector(e: React.FormEvent) {
    e.preventDefault();
    if (!svcName.trim()) return;
    try {
      const creds: Record<string, string> = {};
      if (apiKey.trim()) creds.api_key = apiKey.trim();
      if (clientId.trim()) creds.client_id = clientId.trim();
      if (clientSecret.trim()) creds.client_secret = clientSecret.trim();

      const created = await apiFetch<any>("/api/v1/integrations/universal/connectors", {
        method: "POST",
        body: {
          name: svcName.trim(),
          category: svcCategory,
          connection_method: method,
          website_url: websiteUrl.trim(),
          docs_url: docsUrl.trim(),
          api_base_url: apiBaseUrl.trim(),
          required_scopes: scopesText.split(",").map((s) => s.trim()).filter(Boolean),
          capabilities: capsText.split(",").map((s) => s.trim()).filter(Boolean),
          credentials: creds,
          webhook_secret: webhookSecret.trim(),
          subscribed_events: eventsText.split(",").map((s) => s.trim()).filter(Boolean),
        },
      });
      pushToast(`Registered '${created.name}' (${created.lifecycle_state}).`, "success");
      setConnectOpen(false);
      setApiKey("");
      setClientSecret("");
      setWebhookSecret("");
      setInspectResult(null);
      await loadCatalogue();
      onChanged?.();
      setConfigConnector(created);
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function openWorkspace(connector: any) {
    setConfigConnector(connector);
    if (connector.source === "CUSTOM_UNIVERSAL" && connector.connection_method === "WEBHOOK") {
      try {
        const d = await apiFetch<any>(`/api/v1/integrations/universal/connectors/${connector.connector_id}/deliveries`);
        setDeliveries(d.deliveries || []);
      } catch {
        setDeliveries([]);
      }
    } else {
      setDeliveries([]);
    }
  }

  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }} data-testid="universal-connections-2">
      <div className="row-between" style={{ flexWrap: "wrap", gap: 10 }}>
        <div>
          <strong style={{ fontSize: 15 }}>Universal Connections Centre 2.0</strong>
          <div className="muted" style={{ fontSize: 12 }}>
            Connect any service via API Key, OAuth 2.0, Website Inspection, or Signed Webhook. All secrets encrypted server-side in VAULT.
          </div>
        </div>
        <button id="universal-connect-service-btn" type="button" className="btn btn-sm" onClick={() => setConnectOpen(true)}>
          <Plus size={14} /> Connect a Service
        </button>
      </div>

      {/* Search & Category Filter */}
      <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: 1, minWidth: 200 }}>
          <Search size={13} style={{ position: "absolute", left: 10, top: 10, opacity: 0.6 }} />
          <input
            className="input"
            style={{ paddingLeft: 28, width: "100%" }}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search any service, website, or category..."
          />
        </div>
        <select className="select" value={selectedCategory} onChange={(e) => setSelectedCategory(e.target.value)} aria-label="Filter category">
          <option value="">All 14 Categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </select>
      </div>

      <DataTable
        rows={catalogue}
        rowKey={(r) => `${r.source}_${r.connector_id}`}
        emptyTitle="No Matching Services"
        emptyDescription="Click 'Connect a Service' to register any custom API, OAuth 2.0 app, website, or webhook."
        columns={[
          {
            key: "name",
            header: "Service",
            render: (r) => (
              <div>
                <strong>{r.name}</strong>
                <div className="muted" style={{ fontSize: 11 }}>{r.category} · {r.connection_method}</div>
              </div>
            ),
          },
          {
            key: "state",
            header: "Lifecycle State",
            render: (r) => <StatusIndicator label={r.lifecycle_state} tone={lifecycleTone(r.lifecycle_state)} />,
          },
          {
            key: "caps",
            header: "Capabilities",
            render: (r) => <span className="muted" style={{ fontSize: 11 }}>{(r.capabilities || []).slice(0, 3).join(", ") || "Custom"}</span>,
          },
          {
            key: "actions",
            header: "Workspace",
            render: (r) =>
              r.source === "CUSTOM_UNIVERSAL" ? (
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => openWorkspace(r)}>
                  Configure
                </button>
              ) : (
                <span className="muted" style={{ fontSize: 11 }}>Built-in</span>
              ),
          },
        ]}
      />

      {/* Connect a Service Drawer */}
      <Drawer open={connectOpen} title="Connect a Service (Universal 2.0)" onClose={() => setConnectOpen(false)}>
        <form onSubmit={handleCreateConnector} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="segmented" style={{ flexWrap: "wrap" }}>
            {[
              { id: "API_KEY", label: "API Key", icon: KeyRound },
              { id: "OAUTH2", label: "OAuth 2.0", icon: Link2 },
              { id: "WEBSITE", label: "Website URL", icon: Globe },
              { id: "WEBHOOK", label: "Webhook", icon: Webhook },
            ].map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  type="button"
                  className={`seg-btn ${method === tab.id ? "active" : ""}`}
                  onClick={() => setMethod(tab.id as any)}
                >
                  <Icon size={12} /> {tab.label}
                </button>
              );
            })}
          </div>

          <input className="input" placeholder="Service Name (e.g. Linear, HubSpot, Custom API)" value={svcName} onChange={(e) => setSvcName(e.target.value)} required />
          <select className="select" value={svcCategory} onChange={(e) => setSvcCategory(e.target.value)}>
            {(categories.length ? categories : ["Custom websites and APIs"]).map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>

          {method === "WEBSITE" && (
            <div className="row" style={{ gap: 8 }}>
              <input className="input" style={{ flex: 1 }} placeholder="https://example.com" value={websiteUrl} onChange={(e) => setWebsiteUrl(e.target.value)} />
              <button type="button" className="btn btn-secondary btn-sm" onClick={handleInspectWebsite}>Inspect URL</button>
            </div>
          )}

          {inspectResult && (
            <div className="alert-box" style={{ fontSize: 12 }}>
              <strong>Discovered:</strong> {inspectResult.detected_auth_methods.join(", ")} · {inspectResult.note}
            </div>
          )}

          {method !== "WEBSITE" && (
            <input className="input" placeholder="Website URL (optional)" value={websiteUrl} onChange={(e) => setWebsiteUrl(e.target.value)} />
          )}
          <input className="input" placeholder="Documentation URL (optional)" value={docsUrl} onChange={(e) => setDocsUrl(e.target.value)} />

          {method === "API_KEY" && (
            <>
              <input className="input" placeholder="API Base URL (HTTPS, e.g. https://api.service.com/v1)" value={apiBaseUrl} onChange={(e) => setApiBaseUrl(e.target.value)} />
              <input className="input" type="password" placeholder="API Key (stored encrypted in VAULT)" value={apiKey} onChange={(e) => setApiKey(e.target.value)} />
              <div className="row" style={{ gap: 8 }}>
                <input className="input" style={{ flex: 1 }} placeholder="Client ID (optional)" value={clientId} onChange={(e) => setClientId(e.target.value)} />
                <input className="input" style={{ flex: 1 }} type="password" placeholder="Client Secret (optional)" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} />
              </div>
            </>
          )}

          {method === "WEBHOOK" && (
            <>
              <input className="input" type="password" placeholder="Signing Secret (HMAC-SHA256, stored in VAULT)" value={webhookSecret} onChange={(e) => setWebhookSecret(e.target.value)} required />
              <input className="input" placeholder="Subscribed Events (comma-separated)" value={eventsText} onChange={(e) => setEventsText(e.target.value)} />
            </>
          )}

          <input className="input" placeholder="Required Scopes (comma-separated)" value={scopesText} onChange={(e) => setScopesText(e.target.value)} />
          <input className="input" placeholder="Capabilities (comma-separated, e.g. read_issues, create_webhook)" value={capsText} onChange={(e) => setCapsText(e.target.value)} />

          <button type="submit" className="btn">Save &amp; Register Connector</button>
        </form>
      </Drawer>

      {/* Per-Service Configuration Workspace Drawer */}
      <Drawer open={Boolean(configConnector)} title={configConnector ? `${configConnector.name} — Configuration Workspace` : ""} onClose={() => setConfigConnector(null)}>
        {configConnector && (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="row-between">
              <span className="pill mono">{configConnector.connection_method}</span>
              <StatusIndicator label={configConnector.lifecycle_state} tone={lifecycleTone(configConnector.lifecycle_state)} />
            </div>
            <div className="list-item" style={{ fontSize: 12, display: "flex", flexDirection: "column", gap: 4 }}>
              <div><strong>Category:</strong> {configConnector.category}</div>
              <div><strong>Approved By:</strong> {configConnector.approved_by || "Pending explicit user approval"}</div>
              <div><strong>Last Verified:</strong> {configConnector.last_verified_at || "Never"}</div>
              {configConnector.webhook_endpoint_path && <div><strong>Webhook Endpoint:</strong> <span className="mono">{configConnector.webhook_endpoint_path}</span></div>}
              {configConnector.last_error && <div style={{ color: "#f87171" }}><strong>Last Error:</strong> {configConnector.last_error}</div>}
              {configConnector.docs_url && (
                <a href={configConnector.docs_url} target="_blank" rel="noopener noreferrer" className="row" style={{ gap: 4 }}>
                  <ExternalLink size={12} /> Official Documentation
                </a>
              )}
            </div>

            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={async () => {
                  const res = await apiFetch<any>(`/api/v1/integrations/universal/connectors/${configConnector.connector_id}/test`, { method: "POST" });
                  setConfigConnector(res);
                  await loadCatalogue();
                  pushToast(`Test result: ${res.lifecycle_state}`, res.lifecycle_state === "LIVE_VERIFIED" ? "success" : "info");
                }}
              >
                <RefreshCw size={12} /> Test Connection
              </button>
              <button
                type="button"
                className="btn btn-sm"
                onClick={async () => {
                  const res = await apiFetch<any>(`/api/v1/integrations/universal/connectors/${configConnector.connector_id}/approve`, {
                    method: "POST",
                    body: {},
                  });
                  setConfigConnector(res);
                  await loadCatalogue();
                  pushToast(`Permissions approved for ${res.name}.`, "success");
                }}
              >
                <ShieldCheck size={12} /> Approve Permissions
              </button>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={async () => {
                  const res = await apiFetch<any>(`/api/v1/integrations/universal/connectors/${configConnector.connector_id}/revoke`, { method: "POST" });
                  setConfigConnector(res);
                  await loadCatalogue();
                  pushToast(`Revoked ${res.name}.`, "info");
                }}
              >
                <Trash2 size={12} /> Revoke
              </button>
            </div>

            <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <strong style={{ fontSize: 12 }}><RotateCw size={12} /> Rotate Credentials</strong>
              <input className="input" type="password" placeholder="New API Key (optional)" value={rotateKey} onChange={(e) => setRotateKey(e.target.value)} />
              <input className="input" type="password" placeholder="New Webhook Secret (optional)" value={rotateWhSecret} onChange={(e) => setRotateWhSecret(e.target.value)} />
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={async () => {
                  const res = await apiFetch<any>(`/api/v1/integrations/universal/connectors/${configConnector.connector_id}/rotate`, {
                    method: "POST",
                    body: {
                      credentials: rotateKey.trim() ? { api_key: rotateKey.trim() } : {},
                      webhook_secret: rotateWhSecret.trim(),
                    },
                  });
                  setRotateKey("");
                  setRotateWhSecret("");
                  setConfigConnector(res);
                  await loadCatalogue();
                  pushToast("Credentials rotated in VAULT.", "success");
                }}
              >
                <CheckCircle2 size={12} /> Rotate in VAULT
              </button>
            </div>

            {deliveries.length > 0 && (
              <div className="list-item" style={{ fontSize: 12 }}>
                <strong>Recent Webhook Deliveries ({deliveries.length})</strong>
                {deliveries.slice(0, 5).map((d) => (
                  <div key={d.delivery_id} className="row-between" style={{ paddingTop: 4 }}>
                    <span className="mono">{d.event_type}</span>
                    <span>{d.status}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
