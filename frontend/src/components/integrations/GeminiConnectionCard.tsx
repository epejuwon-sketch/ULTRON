import React, { useEffect, useState } from "react";
import {
  Activity,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Cpu,
  History,
  Info,
  Play,
  RefreshCw,
  Shield,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { apiFetch } from "../../lib/api";
import { IntegrationLogo } from "./IntegrationLogo";
import {
  DataTable,
  Drawer,
  EmptyState,
  MetricDisplay,
  StatusIndicator,
  StatusTone,
  useToast,
} from "../ui/DesignSystem";

export type GeminiConnectionStatus =
  | "NOT CONFIGURED"
  | "CONFIGURED"
  | "TESTING"
  | "CONNECTED"
  | "DEGRADED"
  | "FAILED";

export interface GeminiCardData {
  provider: string;
  provider_id: string;
  connection_status: GeminiConnectionStatus;
  credential_status: {
    configured: boolean;
    source: "SERVER_ENV" | "VAULT" | "NONE";
    missing_env_vars: string[];
    masked_key: string | null;
  };
  models: {
    standard: string;
    reasoning: string;
    fast: string;
    tier4_reasoning: string;
    embedding: string;
    image: string;
  };
  last_successful_verification: {
    verification_id: string;
    model: string;
    test_type: string;
    latency_ms: number;
    trace_id: string;
    timestamp: string;
    response_excerpt?: string;
  } | null;
  last_failed_verification: {
    verification_id: string;
    model: string;
    test_type: string;
    error_code: string | null;
    error_message: string | null;
    trace_id: string;
    timestamp: string;
  } | null;
  last_verification: {
    verification_id: string;
    result: string;
    model: string;
    test_type: string;
    latency_ms: number;
    timestamp: string;
  } | null;
  request_latency_ms: number | null;
  last_error_sanitized: string | null;
  total_verifications_count: number;
  environment: string;
  is_deployed: boolean;
}

function getStatusTone(status: GeminiConnectionStatus): StatusTone {
  switch (status) {
    case "CONNECTED":
      return "success";
    case "CONFIGURED":
      return "warn";
    case "TESTING":
      return "info";
    case "DEGRADED":
      return "warn";
    case "FAILED":
      return "danger";
    case "NOT CONFIGURED":
    default:
      return "neutral";
  }
}

export function GeminiConnectionCard({
  onStatusChange,
}: {
  onStatusChange?: (status: GeminiConnectionStatus) => void;
}) {
  const { pushToast } = useToast();
  const [data, setData] = useState<GeminiCardData | null>(null);
  const [loading, setLoading] = useState(false);
  const [testingType, setTestingType] = useState<string | null>(null);

  // Drawers
  const [showHistory, setShowHistory] = useState(false);
  const [historyList, setHistoryList] = useState<any[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const [showDiagnostics, setShowDiagnostics] = useState(false);
  const [diagnosticsData, setDiagnosticsData] = useState<any>(null);
  const [loadingDiagnostics, setLoadingDiagnostics] = useState(false);

  async function loadCardData() {
    try {
      const res = await apiFetch<GeminiCardData>("/api/v1/integrations/gemini/card");
      setData(res);
      if (onStatusChange) {
        onStatusChange(res.connection_status);
      }
    } catch (e: any) {
      console.warn("Could not load Gemini card telemetry:", e.message);
    }
  }

  useEffect(() => {
    loadCardData();
  }, []);

  async function runTest(type: "CONNECTION" | "STANDARD_INFERENCE" | "TIER5_REASONING") {
    setTestingType(type);
    const endpoint =
      type === "CONNECTION"
        ? "/api/v1/integrations/gemini/test-connection"
        : type === "STANDARD_INFERENCE"
        ? "/api/v1/integrations/gemini/test-standard"
        : "/api/v1/integrations/gemini/test-tier5";

    const label =
      type === "CONNECTION"
        ? "Connection (Catalog Discovery)"
        : type === "STANDARD_INFERENCE"
        ? "Standard Inference (gemini-3.8-flash)"
        : "Tier 5 Reasoning (gemini-4-argon)";

    try {
      const res = await apiFetch<any>(endpoint, { method: "POST" });
      await loadCardData();

      if (res.result === "VERIFIED") {
        pushToast(`${label} VERIFIED (${res.latency_ms} ms). Response confirmed.`, "success");
      } else {
        pushToast(
          `${label} ${res.result}: ${res.error_message || "Verification did not pass."}`,
          "error"
        );
      }
    } catch (e: any) {
      pushToast(`Verification request failed: ${e.message}`, "error");
      await loadCardData();
    } finally {
      setTestingType(null);
    }
  }

  async function openHistory() {
    setShowHistory(true);
    setLoadingHistory(true);
    try {
      const res = await apiFetch<any>("/api/v1/integrations/gemini/history?limit=40");
      setHistoryList(res.history || []);
    } catch (e: any) {
      pushToast(`Failed to load history: ${e.message}`, "error");
    } finally {
      setLoadingHistory(false);
    }
  }

  async function openDiagnostics() {
    setShowDiagnostics(true);
    setLoadingDiagnostics(true);
    try {
      const res = await apiFetch<any>("/api/v1/integrations/gemini/diagnostics");
      setDiagnosticsData(res);
    } catch (e: any) {
      pushToast(`Failed to load diagnostics: ${e.message}`, "error");
    } finally {
      setLoadingDiagnostics(false);
    }
  }

  const status: GeminiConnectionStatus = testingType
    ? "TESTING"
    : data?.connection_status || "NOT CONFIGURED";

  return (
    <div
      id="gemini-connection-center-card"
      className="card"
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 16,
        border: "1px solid rgba(56, 189, 248, 0.25)",
        background: "linear-gradient(180deg, rgba(11, 19, 36, 0.7) 0%, rgba(13, 17, 23, 0.95) 100%)",
        position: "relative",
      }}
    >
      {/* Top Header */}
      <div className="row-between" style={{ alignItems: "flex-start", gap: 12, flexWrap: "wrap" }}>
        <div className="row" style={{ gap: 14, alignItems: "center" }}>
          <div style={{ padding: 2, borderRadius: 10, background: "rgba(56, 189, 248, 0.1)", border: "1px solid rgba(56, 189, 248, 0.3)" }}>
            <IntegrationLogo id="gemini" size={40} />
          </div>
          <div>
            <div className="row" style={{ gap: 8, alignItems: "center" }}>
              <span style={{ fontSize: 17, fontWeight: 700, letterSpacing: "-0.01em" }}>Google Gemini</span>
              <span className="muted mono" style={{ fontSize: 10.5, padding: "2px 6px", borderRadius: 4, background: "rgba(255,255,255,0.06)" }}>
                PRIMARY NEON INTELLIGENCE
              </span>
            </div>
            <div className="muted" style={{ fontSize: 12.5, marginTop: 2 }}>
              Authoritative multimodal & multi-tier reasoning engine for ULTRON OS 2026.
            </div>
          </div>
        </div>

        <div className="row" style={{ gap: 8, alignItems: "center" }}>
          <StatusIndicator label={status} tone={getStatusTone(status)} />
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={loadCardData}
            title="Refresh card telemetry"
            style={{ padding: "6px 8px" }}
          >
            <RefreshCw size={13} className={loading ? "spin" : ""} />
          </button>
        </div>
      </div>

      {/* Primary Metrics Grid */}
      <div className="grid-4" style={{ gap: 10 }}>
        <MetricDisplay
          label="Credential Status"
          value={data?.credential_status.configured ? "CONFIGURED" : "MISSING"}
          sub={
            data?.credential_status.configured
              ? `${data.credential_status.source} (${data.credential_status.masked_key || "Masked"})`
              : "GEMINI_API_KEY required"
          }
          tone={data?.credential_status.configured ? "info" : "warn"}
        />
        <MetricDisplay
          label="Standard Model"
          value={data?.models.standard || "gemini-3.8-flash"}
          sub="Tier 2/3 default inference"
          tone="neutral"
        />
        <MetricDisplay
          label="Reasoning Model"
          value={data?.models.reasoning || "gemini-4-argon"}
          sub="Tier 5 flagship reasoning"
          tone="neutral"
        />
        <MetricDisplay
          label="Request Latency"
          value={data?.request_latency_ms != null ? `${data.request_latency_ms} ms` : "— ms"}
          sub={
            data?.last_successful_verification
              ? `Verified ${new Date(data.last_successful_verification.timestamp).toLocaleTimeString()}`
              : "Awaiting live test"
          }
          tone={data?.request_latency_ms != null ? "success" : "neutral"}
        />
      </div>

      {/* Model Roster Metadata Banner */}
      <div
        style={{
          display: "flex",
          gap: 16,
          flexWrap: "wrap",
          padding: "10px 14px",
          borderRadius: 8,
          background: "rgba(255, 255, 255, 0.03)",
          border: "1px solid rgba(255, 255, 255, 0.06)",
          fontSize: 11.5,
        }}
      >
        <div>
          <span className="muted">Fast (T1): </span>
          <span className="mono">{data?.models.fast || "gemini-3.5-flash-lite"}</span>
        </div>
        <div>
          <span className="muted">Reasoning (T4): </span>
          <span className="mono">{data?.models.tier4_reasoning || "gemini-4-hydrogen"}</span>
        </div>
        <div>
          <span className="muted">Embedding: </span>
          <span className="mono">{data?.models.embedding || "gemini-embedding-2"}</span>
        </div>
        <div>
          <span className="muted">Image Gen: </span>
          <span className="mono">{data?.models.image || "imagen-3.0-generate-002"}</span>
        </div>
        <div style={{ marginLeft: "auto" }}>
          <span className="muted">Runs: </span>
          <span className="mono">{data?.total_verifications_count ?? 0}</span>
        </div>
      </div>

      {/* Last Error Banner if FAILED or DEGRADED */}
      {data?.last_error_sanitized && status !== "CONNECTED" && (
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 10,
            padding: "10px 14px",
            borderRadius: 8,
            background: "rgba(239, 68, 68, 0.1)",
            border: "1px solid rgba(239, 68, 68, 0.25)",
            color: "var(--danger-light, #fca5a5)",
            fontSize: 12,
          }}
        >
          <AlertCircle size={15} style={{ flexShrink: 0, marginTop: 2 }} />
          <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
            <strong>Last Verification Notice:</strong>
            <span>{data.last_error_sanitized}</span>
            {data.last_failed_verification?.timestamp && (
              <span className="muted mono" style={{ fontSize: 10.5, marginTop: 2 }}>
                Recorded {new Date(data.last_failed_verification.timestamp).toLocaleString()} · Trace {data.last_failed_verification.trace_id}
              </span>
            )}
          </div>
        </div>
      )}

      {/* Functional Controls Bar */}
      <div className="row-between" style={{ gap: 10, flexWrap: "wrap", paddingTop: 4 }}>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <button
            id="gemini-btn-test-connection"
            type="button"
            className="btn btn-sm btn-secondary"
            disabled={Boolean(testingType)}
            onClick={() => runTest("CONNECTION")}
            title="Fast catalog discovery & authorization probe"
          >
            <Activity size={13} className={testingType === "CONNECTION" ? "spin" : ""} />
            {testingType === "CONNECTION" ? "Testing..." : "Test Connection"}
          </button>

          <button
            id="gemini-btn-test-standard"
            type="button"
            className="btn btn-sm"
            disabled={Boolean(testingType)}
            onClick={() => runTest("STANDARD_INFERENCE")}
            title="Execute live server-side inference on standard model gemini-3.8-flash"
          >
            <Play size={13} className={testingType === "STANDARD_INFERENCE" ? "spin" : ""} />
            {testingType === "STANDARD_INFERENCE" ? "Verifying Flash..." : "Test Standard Model"}
          </button>

          <button
            id="gemini-btn-test-tier5"
            type="button"
            className="btn btn-sm btn-secondary"
            disabled={Boolean(testingType)}
            onClick={() => runTest("TIER5_REASONING")}
            title="Explicit Tier 5 reasoning verification on gemini-4-argon (quota-conserving)"
          >
            <Sparkles size={13} className={testingType === "TIER5_REASONING" ? "spin" : ""} />
            {testingType === "TIER5_REASONING" ? "Verifying Argon..." : "Test Tier 5 Reasoning"}
          </button>
        </div>

        <div className="row" style={{ gap: 8 }}>
          <button
            id="gemini-btn-view-history"
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={openHistory}
          >
            <History size={13} /> Verification History
          </button>

          <button
            id="gemini-btn-view-diagnostics"
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={openDiagnostics}
          >
            <Cpu size={13} /> Technical Diagnostics
          </button>
        </div>
      </div>

      {/* Verification History Drawer */}
      <Drawer
        open={showHistory}
        onClose={() => setShowHistory(false)}
        title="Google Gemini — Persisted Verification History"
      >
        <p className="muted" style={{ marginTop: 0, marginBottom: 16, fontSize: 12 }}>
          Real server-side audit logs recorded across catalog probes and live inference runs.
        </p>
        {loadingHistory ? (
          <div className="center muted" style={{ padding: 40 }}>
            <RefreshCw size={18} className="spin" style={{ marginRight: 8 }} /> Loading persisted verification history...
          </div>
        ) : historyList.length === 0 ? (
          <EmptyState
            title="No Verifications Recorded"
            description="No verification runs have been performed yet for this tenant. Use 'Test Standard Model' above to execute the first live probe."
            action={
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => {
                  setShowHistory(false);
                  runTest("STANDARD_INFERENCE");
                }}
              >
                Run Standard Inference Test
              </button>
            }
          />
        ) : (
          <DataTable
            rows={historyList}
            rowKey={(r: any) => r.verification_id}
            columns={[
              {
                key: "created_at",
                header: "Timestamp",
                render: (r) => (
                  <span className="mono" style={{ fontSize: 11 }}>
                    {new Date(r.created_at).toLocaleString()}
                  </span>
                ),
              },
              {
                key: "test_type",
                header: "Type",
                render: (r) => (
                  <span className="mono" style={{ fontSize: 11 }}>
                    {r.test_type}
                  </span>
                ),
              },
              {
                key: "model",
                header: "Model",
                render: (r) => (
                  <span className="mono" style={{ fontSize: 11 }}>
                    {r.model}
                  </span>
                ),
              },
              {
                key: "result",
                header: "Result",
                render: (r) => (
                  <StatusIndicator
                    label={r.result}
                    tone={r.result === "VERIFIED" ? "success" : r.result === "DEGRADED" ? "warn" : "danger"}
                  />
                ),
              },
              {
                key: "latency_ms",
                header: "Latency",
                render: (r) => <span className="mono">{r.latency_ms} ms</span>,
              },
              {
                key: "tokens",
                header: "Tokens",
                render: (r) => (
                  <span className="mono muted" style={{ fontSize: 11 }}>
                    {r.tokens?.total_tokens != null ? `${r.tokens.total_tokens} total` : "—"}
                  </span>
                ),
              },
              {
                key: "trace_id",
                header: "Trace ID",
                render: (r) => (
                  <span className="mono muted" style={{ fontSize: 10.5 }}>
                    {r.trace_id}
                  </span>
                ),
              },
            ]}
          />
        )}
      </Drawer>

      {/* Technical Diagnostics Drawer */}
      <Drawer
        open={showDiagnostics}
        onClose={() => setShowDiagnostics(false)}
        title="Google Gemini — Technical Diagnostics & Model Matrix"
      >
        <p className="muted" style={{ marginTop: 0, marginBottom: 16, fontSize: 12 }}>
          Authoritative NEON multi-tier hierarchy, provider isolation audit, and sampling policies.
        </p>
        {loadingDiagnostics ? (
          <div className="center muted" style={{ padding: 40 }}>
            <RefreshCw size={18} className="spin" style={{ marginRight: 8 }} /> Inspecting technical diagnostics...
          </div>
        ) : diagnosticsData ? (
          <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
            {/* Provider Isolation Notice */}
            <div
              style={{
                padding: "12px 16px",
                borderRadius: 8,
                background: "rgba(56, 189, 248, 0.08)",
                border: "1px solid rgba(56, 189, 248, 0.25)",
                display: "flex",
                flexDirection: "column",
                gap: 6,
              }}
            >
              <div className="row" style={{ gap: 8, alignItems: "center" }}>
                <ShieldCheck size={16} color="#38BDF8" />
                <strong style={{ color: "#38BDF8" }}>Provider Isolation Verified</strong>
              </div>
              <p style={{ margin: 0, fontSize: 12 }}>
                {diagnosticsData.isolation_audit?.note ||
                  "NEON Intelligence Layer is exclusively bound to Google Gemini. Zero silent failover to unapproved providers."}
              </p>
              <div className="row" style={{ gap: 14, fontSize: 11, marginTop: 4 }}>
                <span>OpenAI Fallback: <strong className="mono">{diagnosticsData.isolation_audit?.openai_active ? "CONFIGURED" : "OFF"}</strong></span>
                <span>Anthropic Fallback: <strong className="mono">{diagnosticsData.isolation_audit?.anthropic_active ? "CONFIGURED" : "OFF"}</strong></span>
                <span>Carbon Model: <strong className="mono">EXCLUDED (Prohibited)</strong></span>
              </div>
            </div>

            {/* 5-Tier Model Hierarchy */}
            <div>
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>
                NEON 5-Tier Model Hierarchy & Fallback Policy
              </div>
              <DataTable
                rows={diagnosticsData.tier_hierarchy || []}
                rowKey={(t: any) => `tier_${t.tier}`}
                columns={[
                  {
                    key: "tier",
                    header: "Tier",
                    render: (t: any) => <span className="mono">Tier {t.tier}</span>,
                  },
                  {
                    key: "primary_model",
                    header: "Primary Model",
                    render: (t: any) => <strong className="mono">{t.primary_model}</strong>,
                  },
                  {
                    key: "fallback_chain",
                    header: "Intra-Gemini Fallback Chain",
                    render: (t: any) => (
                      <span className="mono muted" style={{ fontSize: 11 }}>
                        {(t.fallback_chain || []).join(" → ")}
                      </span>
                    ),
                  },
                  {
                    key: "sampling",
                    header: "Sampling Deprecation",
                    render: (t: any) => (
                      <span className="mono" style={{ fontSize: 10.5 }}>
                        {t.deprecates_sampling_params ? "Deprecates temp/top_p" : "Standard"}
                      </span>
                    ),
                  },
                ]}
              />
            </div>

            {/* Rate Limits & Policies */}
            <div
              style={{
                padding: "10px 14px",
                borderRadius: 8,
                background: "rgba(255, 255, 255, 0.03)",
                border: "1px solid rgba(255, 255, 255, 0.08)",
                fontSize: 11.5,
                display: "flex",
                flexDirection: "column",
                gap: 4,
              }}
            >
              <div><strong>Rate Limiting:</strong> Maximum {diagnosticsData.rate_limits?.max_tests_per_minute || 10} verification probes per minute per tenant.</div>
              <div><strong>Concurrency:</strong> Single-probe mutex lock active per tenant to prevent duplicate or racing requests.</div>
              <div><strong>Environment:</strong> <span className="mono">{diagnosticsData.environment}</span> (Serverless Vercel: {String(diagnosticsData.serverless_vercel)})</div>
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
