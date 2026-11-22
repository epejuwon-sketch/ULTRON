import React, { useEffect, useState } from "react";
import { ArrowRight, Bot, FolderOpen, Hammer, Layers, MessageSquare, Plug, Shield, Workflow } from "lucide-react";
import { apiFetch } from "../lib/api";
import { EarthGlobe } from "./EarthGlobe";

interface CommandCenterProps {
  backendReady: boolean | null;
  backendDetail: string;
  onNavigate: (viewId: string) => void;
  onSendToNeon: (prompt: string) => void;
}

export function CommandCenterView({
  backendReady,
  backendDetail,
  onNavigate,
  onSendToNeon,
}: CommandCenterProps) {
  const [overview, setOverview] = useState<any>(null);
  const [readyData, setReadyData] = useState<any>(null);
  const [approvalsCount, setApprovalsCount] = useState<number>(0);
  const [tasksCount, setTasksCount] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [command, setCommand] = useState("");
  const [dispatchMode, setDispatchMode] = useState<"neon" | "argon">("neon");
  const [dispatching, setDispatching] = useState(false);
  const [dispatchResult, setDispatchResult] = useState<{
    mode: string;
    model?: string;
    summary: string;
    lifecycle?: string;
    steps?: string[];
  } | null>(null);

  async function refreshTelemetry() {
    setLoading(true);
    setError("");
    try {
      const [rdyResp, mon, tsk, appv] = await Promise.all([
        fetch("/health/ready").then((r) => r.json()).catch(() => null),
        apiFetch<any>("/api/v1/monitoring/overview").catch(() => null),
        apiFetch<any>("/api/v1/tasks").catch(() => ({ tasks: [] })),
        apiFetch<any>("/api/v1/approvals").catch(() => ({ approvals: [] })),
      ]);
      setReadyData(rdyResp);
      setOverview(mon);
      setTasksCount((tsk?.tasks || []).length);
      setApprovalsCount((appv?.approvals || []).filter((a: any) => a.status === "PENDING").length);
    } catch (e: any) {
      setError(e.message || "Unable to load command telemetry.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshTelemetry();
  }, []);

  async function handleCommandSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = command.trim();
    if (!text) return;
    setDispatching(true);
    setError("");
    setDispatchResult(null);
    try {
      if (dispatchMode === "argon") {
        const res = await apiFetch<any>("/api/v1/orchestrate", {
          method: "POST",
          body: { objective: text, auto_execute: true },
        });
        setDispatchResult({
          mode: `ARGON · ${res.neon_routing?.selected_agent_id || "AGT-01"} (T${res.neon_routing?.reasoning_tier ?? 3})`,
          model: res.neon_routing?.primary_model,
          lifecycle: res.task?.lifecycle_state,
          steps: (res.task?.steps || []).map((s: any) => `${s.agent_id}: ${s.status}`),
          summary: res.task?.result_summary || "Orchestration plan dispatched.",
        });
        refreshTelemetry();
      } else {
        const conv = await apiFetch<any>("/api/v1/neon/conversations", {
          method: "POST",
          body: { title: text.slice(0, 48), agent_id: "AGT-01" },
        });
        const res = await apiFetch<any>(`/api/v1/neon/conversations/${conv.conversation_id}/messages`, {
          method: "POST",
          body: { content: text },
        });
        const replyObj = typeof res.reply === "object" && res.reply !== null ? res.reply : {};
        setDispatchResult({
          mode: `NEON · ${replyObj.agent_id || "AGT-01"} (${replyObj.execution_mode || "ACTIVE"})`,
          model: replyObj.model || "deterministic",
          summary:
            typeof replyObj.output === "string"
              ? replyObj.output
              : typeof res.reply === "string"
              ? res.reply
              : "Response recorded in NEON session.",
        });
      }
      setCommand("");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setDispatching(false);
    }
  }

  const dbBackend = readyData?.database?.backend || overview?.database?.backend || "unknown";
  const dbHealthy = readyData?.database?.healthy ?? overview?.database?.healthy ?? backendReady;
  const agentsRegistered = overview?.agents?.total_registered ?? 60;
  const configuredIntegrations = readyData?.config?.integrations_configured
    ? Object.values(readyData.config.integrations_configured).filter(Boolean).length
    : 0;
  const globeStatus = dbHealthy === false ? "degraded" : loading ? "loading" : "ready";

  return (
    <div className="command-stage">
      {/* Central Orbital Presence */}
      <section className="orbital-hero" aria-label="ULTRON Orbital Command Center">
        <div className="orbital-header">
          <div>
            <div className="eyebrow-mono">ULTRON OPERATING SYSTEM · V2026.4</div>
            <h1 className="hero-title">Global Command Interface</h1>
          </div>
          <button
            id="cmd-refresh-telemetry"
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={refreshTelemetry}
            disabled={loading}
          >
            {loading ? "Syncing..." : "Sync Telemetry"}
          </button>
        </div>

        <div className="orbital-core">
          <div className="orbital-globe-wrap">
            <EarthGlobe size={340} status={globeStatus} />
            <div className="orbital-caption mono">
              <span>DRAG TO ROTATE</span>
              <span>·</span>
              <span>{dbHealthy === false ? "DATABASE DEGRADED" : `PERSISTENCE: ${String(dbBackend).toUpperCase()}`}</span>
            </div>
          </div>

          <div className="telemetry-rail" role="region" aria-label="Live System Telemetry">
            <div className="telemetry-cell">
              <div className="telemetry-label">DATABASE ENGINE</div>
              <div className="telemetry-value mono">
                {dbHealthy === false ? "DEGRADED" : String(dbBackend).toUpperCase()}
              </div>
              <div className="telemetry-sub">
                {readyData?.database?.pool_strategy || (dbHealthy ? "Connectivity verified" : "Check /health/ready")}
              </div>
            </div>

            <div className="telemetry-cell">
              <div className="telemetry-label">SPECIALIST FLEET</div>
              <div className="telemetry-value mono">{agentsRegistered} AGENTS</div>
              <div className="telemetry-sub">NEON intelligence · ARGON DAG</div>
            </div>

            <div className="telemetry-cell">
              <div className="telemetry-label">OPERATIONS &amp; GATES</div>
              <div className="telemetry-value mono">
                {tasksCount} TASKS · {approvalsCount} PENDING
              </div>
              <div className="telemetry-sub">ApprovalGate &amp; SHA-256 audit active</div>
            </div>

            <div className="telemetry-cell">
              <div className="telemetry-label">CONNECTED PROVIDERS</div>
              <div className="telemetry-value mono">{configuredIntegrations} CONFIGURED</div>
              <div className="telemetry-sub">
                {readyData?.config?.integrations_configured?.gemini ? "Gemini primary live" : "Offline deterministic fallback"}
              </div>
            </div>
          </div>
        </div>

        {backendReady === false && backendDetail && (
          <div className="alert-box alert-warn">{backendDetail}</div>
        )}
        {error && <div className="alert-box alert-error">{error}</div>}

        {/* Direct Command Input */}
        <form onSubmit={handleCommandSubmit} className="command-dock" aria-label="Universal ULTRON Command Bar">
          <div className="command-dock-modes">
            <button
              id="cmd-mode-neon"
              type="button"
              className={`seg-btn ${dispatchMode === "neon" ? "active" : ""}`}
              onClick={() => setDispatchMode("neon")}
            >
              NEON Intelligence
            </button>
            <button
              id="cmd-mode-argon"
              type="button"
              className={`seg-btn ${dispatchMode === "argon" ? "active" : ""}`}
              onClick={() => setDispatchMode("argon")}
            >
              ARGON Orchestrate
            </button>
          </div>
          <div className="command-dock-row">
            <input
              id="cmd-universal-input"
              className="input command-input"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder={
                dispatchMode === "argon"
                  ? "Dispatch a multi-agent objective to ARGON..."
                  : "Issue a directive to NEON / Executive Agent (AGT-01)..."
              }
            />
            <button
              id="cmd-universal-submit"
              type="submit"
              className="btn"
              disabled={dispatching || !command.trim()}
            >
              {dispatching ? "Executing..." : "Execute"}
              <ArrowRight size={15} />
            </button>
          </div>
        </form>

        {dispatchResult && (
          <div className="dispatch-output">
            <div className="row-between">
              <span className="mono-tag">{dispatchResult.mode}</span>
              <div className="row">
                {dispatchResult.lifecycle && <span className="pill pill-cyan">{dispatchResult.lifecycle}</span>}
                {dispatchResult.model && <span className="muted mono">{dispatchResult.model}</span>}
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    onSendToNeon(dispatchResult.summary);
                    onNavigate("jarvis");
                  }}
                >
                  Open in NEON
                </button>
              </div>
            </div>
            {dispatchResult.steps && dispatchResult.steps.length > 0 && (
              <div className="row" style={{ marginTop: 8 }}>
                {dispatchResult.steps.map((s, idx) => (
                  <span key={`${s}-${idx}`} className="pill">{s}</span>
                ))}
              </div>
            )}
            <div className="dispatch-text">{dispatchResult.summary}</div>
          </div>
        )}
      </section>

      {/* Primary Workspace Matrix */}
      <section className="workspace-strip" aria-label="Core Workspaces">
        {[
          { id: "jarvis", title: "NEON Intelligence", desc: "Streaming conversations & secret interception", icon: <MessageSquare size={16} /> },
          { id: "argon", title: "ARGON Orchestrator", desc: "Multi-agent DAG plans, jobs & ApprovalGate", icon: <Workflow size={16} /> },
          { id: "agents", title: "60-Agent Directory", desc: "Inspect manifests & invoke AGT-01 to AGT-60", icon: <Bot size={16} /> },
          { id: "forge", title: "FORGE Engineering", desc: "Project generation, code workspace & preview", icon: <Hammer size={16} /> },
          { id: "files", title: "File Hub", desc: "Tenant-scoped upload, parsing & signed URLs", icon: <FolderOpen size={16} /> },
          { id: "memory", title: "Memory Controls", desc: "Versioned episodic & semantic recall", icon: <Layers size={16} /> },
          { id: "integrations", title: "Integrations", desc: "OAuth 2.0, PKCE & live provider verification", icon: <Plug size={16} /> },
          { id: "security", title: "Security & AEGIS", desc: "Passkeys, VAULT, EVOLVE & RBAC permissions", icon: <Shield size={16} /> },
        ].map((item) => (
          <button
            key={item.id}
            id={`quick-nav-${item.id}`}
            type="button"
            className="workspace-tile"
            onClick={() => onNavigate(item.id)}
          >
            <div className="row-between">
              <span className="tile-icon">{item.icon}</span>
              <ArrowRight size={14} className="muted" />
            </div>
            <div className="tile-title">{item.title}</div>
            <div className="tile-desc">{item.desc}</div>
          </button>
        ))}
      </section>
    </div>
  );
}
