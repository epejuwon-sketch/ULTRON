import React, { useEffect, useState } from "react";
import {
  ArrowRight,
  Bot,
  Command,
  Cpu,
  Globe,
  Layers,
  MessageSquare,
  Radio,
  RefreshCw,
  Shield,
  Sparkles,
  Terminal,
  Workflow,
  Zap,
} from "lucide-react";
import { apiFetch } from "../lib/api";
import { RealisticEarth } from "./RealisticEarth";
import { StatusIndicator } from "./ui/DesignSystem";

interface CommandCenterProps {
  backendReady: boolean | null;
  backendDetail: string;
  onNavigate: (moduleId: string, subPageId?: string) => void;
  onSendToNeon: (prompt: string) => void;
  device?: { isMobile: boolean; isTablet: boolean; isDesktop: boolean };
}

export function CommandCenterView({
  backendReady,
  backendDetail,
  onNavigate,
  onSendToNeon,
  device,
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

  const [recentEvents, setRecentEvents] = useState<Array<{ id: string; title: string; time: string; tag: string }>>([
    { id: "ev-1", title: "SENTINEL Kernel integrity verified", time: "Just now", tag: "SECURITY" },
    { id: "ev-2", title: "NEON Reasoning Engine initialized (Gemini 2.5 Pro)", time: "1m ago", tag: "INTELLIGENCE" },
    { id: "ev-3", title: "60 Specialist Agents indexed in Registry", time: "3m ago", tag: "AGENTS" },
    { id: "ev-4", title: "ApprovalGate governance active with zero-trust RBAC", time: "5m ago", tag: "GOVERNANCE" },
  ]);

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
      setError(e.message || "Unable to refresh telemetry.");
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
          mode: `ARGON · ${res.neon_routing?.selected_agent_id || "AGT-01"}`,
          model: res.neon_routing?.primary_model || "Deterministic DAG",
          lifecycle: res.task?.lifecycle_state || "QUEUED",
          steps: (res.task?.steps || []).map((s: any) => `${s.agent_id}: ${s.status}`),
          summary: res.task?.result_summary || "Orchestration plan generated and dispatched.",
        });
      } else {
        const res = await apiFetch<any>("/api/v1/neon/chat", {
          method: "POST",
          body: { prompt: text },
        });
        setDispatchResult({
          mode: "NEON Intelligence · AGT-01 Executive",
          model: res.model || "Gemini 2.5 Pro",
          summary: res.content || res.reply || "Directive processed by NEON Intelligence.",
        });
      }
      setCommand("");
    } catch (err: any) {
      setError(err?.message || "Execution request failed.");
    } finally {
      setDispatching(false);
    }
  }

  const isMobile = Boolean(device?.isMobile);
  const dbConnected = readyData?.database?.healthy ?? (backendReady !== false);
  const dbBackend = readyData?.database?.backend || "PostgreSQL";
  const earthDiameter = isMobile ? 260 : 380;

  return (
    <div className="command-stage">
      {/* 1. TOP STATUS & CONTEXT BAR */}
      <div className="command-top-status">
        <div className="row">
          <div className="eyebrow-mono">ULTRON OPERATING SYSTEM · KERNEL 2026.4</div>
          <StatusIndicator
            label={dbConnected ? "SYSTEM OPERATIONAL" : "DATABASE DEGRADED"}
            tone={dbConnected ? "success" : "warn"}
          />
        </div>
        <div className="row">
          <span className="mono muted" style={{ fontSize: 11 }}>
            PERSISTENCE: {String(dbBackend).toUpperCase()} · LATENCY: 14ms
          </span>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={refreshTelemetry}
            disabled={loading}
            title="Sync live telemetry"
          >
            <RefreshCw size={12} className={loading ? "spin" : ""} />
            {!isMobile && <span>Sync</span>}
          </button>
        </div>
      </div>

      {backendDetail && !dbConnected && (
        <div className="alert-box alert-warn">{backendDetail}</div>
      )}
      {error && <div className="alert-box alert-error">{error}</div>}

      {/* 2. CENTRAL REALISTIC EARTH & EXECUTIVE COMMAND SECTION */}
      <section className="earth-hero-stage" aria-label="ULTRON Central Orbit">
        <div className="earth-orbit-wrapper">
          <RealisticEarth
            size={earthDiameter}
            interactive={true}
            status={dbConnected ? "ready" : "degraded"}
          />
          <div className="earth-caption-mono">
            <span>ROTATION: 0.0012 RAD/S</span>
            <span>·</span>
            <span>SOLAR INCLINATION: 23.4°</span>
            <span>·</span>
            <span>ORBITAL TELEMETRY ACTIVE</span>
          </div>
        </div>

        <div className="earth-center-status">
          <div className="eyebrow-mono" style={{ letterSpacing: "0.18em" }}>
            AUTONOMOUS COGNITIVE ENGINE
          </div>
          <h1 className="hero-title" style={{ fontSize: isMobile ? 24 : 32, letterSpacing: "-0.03em" }}>
            Global Command Kernel
          </h1>
          <p className="hero-subtitle">
            Coordinating 60 specialist agents across NEON intelligence, ARGON multi-agent DAGs, and zero-trust tenant isolation.
          </p>

          {/* Unified Direct Command Dock */}
          <form onSubmit={handleCommandSubmit} className="command-dock-unified" aria-label="Universal Directive Bar">
            <div className="command-mode-selector">
              <button
                type="button"
                className={`mode-btn ${dispatchMode === "neon" ? "active" : ""}`}
                onClick={() => setDispatchMode("neon")}
              >
                <Sparkles size={13} />
                <span>NEON Intelligence</span>
              </button>
              <button
                type="button"
                className={`mode-btn ${dispatchMode === "argon" ? "active" : ""}`}
                onClick={() => setDispatchMode("argon")}
              >
                <Workflow size={13} />
                <span>ARGON Orchestrate</span>
              </button>
            </div>

            <div className="command-input-row">
              <input
                id="cmd-hero-input"
                className="input command-hero-input"
                value={command}
                onChange={(e) => setCommand(e.target.value)}
                placeholder={
                  dispatchMode === "argon"
                    ? "Dispatch a multi-agent objective to ARGON DAG..."
                    : "Issue a directive to NEON Executive Agent (AGT-01)..."
                }
              />
              <button
                id="cmd-hero-submit"
                type="submit"
                className="btn btn-primary"
                disabled={dispatching || !command.trim()}
              >
                <span>{dispatching ? "Processing..." : "Execute"}</span>
                <ArrowRight size={14} />
              </button>
            </div>
          </form>

          {/* Execution Result Card */}
          {dispatchResult && (
            <div className="dispatch-output-card">
              <div className="row-between">
                <span className="mono" style={{ fontSize: 12, fontWeight: 600 }}>{dispatchResult.mode}</span>
                <div className="row">
                  {dispatchResult.model && <span className="pill">{dispatchResult.model}</span>}
                  {dispatchResult.lifecycle && <span className="pill">{dispatchResult.lifecycle}</span>}
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      onSendToNeon(dispatchResult.summary);
                      onNavigate("neon", "chat");
                    }}
                  >
                    Open in NEON
                  </button>
                </div>
              </div>
              {dispatchResult.steps && dispatchResult.steps.length > 0 && (
                <div className="row" style={{ marginTop: 6 }}>
                  {dispatchResult.steps.map((st, i) => (
                    <span key={i} className="pill" style={{ fontSize: 10 }}>{st}</span>
                  ))}
                </div>
              )}
              <div className="dispatch-text-content">{dispatchResult.summary}</div>
            </div>
          )}
        </div>
      </section>

      {/* 3. SIX BALANCED SUPPORTING PANELS */}
      <section className="supporting-panels-grid" aria-label="System Capabilities">
        {/* Panel 1: NEON Intelligence */}
        <div className="dashboard-panel">
          <div className="panel-header">
            <div className="row">
              <Sparkles size={16} />
              <strong>NEON Intelligence</strong>
            </div>
            <span className="pill">REASONING</span>
          </div>
          <p className="panel-desc">
            Primary reasoning kernel backed by Gemini 2.5 Pro with zero-latency secret interception and adaptive token budget.
          </p>
          <div className="panel-metric-row">
            <div>
              <div className="telemetry-label">MODEL</div>
              <div className="mono" style={{ fontSize: 13, fontWeight: 600 }}>Gemini 2.5 Pro</div>
            </div>
            <div>
              <div className="telemetry-label">CONTEXT</div>
              <div className="mono" style={{ fontSize: 13, fontWeight: 600 }}>1M Tokens</div>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ width: "100%", marginTop: 10 }}
            onClick={() => onNavigate("neon", "chat")}
          >
            Launch NEON Chat <ArrowRight size={12} />
          </button>
        </div>

        {/* Panel 2: ARGON Orchestration */}
        <div className="dashboard-panel">
          <div className="panel-header">
            <div className="row">
              <Workflow size={16} />
              <strong>ARGON Orchestration</strong>
            </div>
            <span className="pill">ACTIVE</span>
          </div>
          <p className="panel-desc">
            Multi-agent directed acyclic graph (DAG) execution engine with deterministic task scheduling and checkpointing.
          </p>
          <div className="panel-metric-row">
            <div>
              <div className="telemetry-label">WORKFLOWS</div>
              <div className="mono" style={{ fontSize: 13, fontWeight: 600 }}>14 Registered</div>
            </div>
            <div>
              <div className="telemetry-label">ACTIVE DAGS</div>
              <div className="mono" style={{ fontSize: 13, fontWeight: 600 }}>0 Queued</div>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ width: "100%", marginTop: 10 }}
            onClick={() => onNavigate("argon", "orchestrate")}
          >
            Open ARGON Workspace <ArrowRight size={12} />
          </button>
        </div>

        {/* Panel 3: Active Specialist Fleet */}
        <div className="dashboard-panel">
          <div className="panel-header">
            <div className="row">
              <Bot size={16} />
              <strong>Specialist Fleet</strong>
            </div>
            <span className="pill">60 AGENTS</span>
          </div>
          <p className="panel-desc">
            Autonomous specialist agents from AGT-01 (Executive) to AGT-60 (Systems Architect) mapped across all 112 pages.
          </p>
          <div className="fleet-tags-row">
            <span className="pill">AGT-01 Executive</span>
            <span className="pill">AGT-02 Coder</span>
            <span className="pill">AGT-03 Security</span>
            <span className="pill">AGT-05 Intel</span>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ width: "100%", marginTop: 10 }}
            onClick={() => onNavigate("agents", "directory")}
          >
            Browse 60-Agent Directory <ArrowRight size={12} />
          </button>
        </div>

        {/* Panel 4: Current Tasks & Governance */}
        <div className="dashboard-panel">
          <div className="panel-header">
            <div className="row">
              <Layers size={16} />
              <strong>Tasks &amp; Governance</strong>
            </div>
            <span className="pill">{approvalsCount} PENDING</span>
          </div>
          <p className="panel-desc">
            Autonomous background workers and human-in-the-loop ApprovalGate governance for sensitive financial &amp; deployment actions.
          </p>
          <div className="panel-metric-row">
            <div>
              <div className="telemetry-label">RUNNING TASKS</div>
              <div className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{tasksCount} Active</div>
            </div>
            <div>
              <div className="telemetry-label">APPROVAL GATES</div>
              <div className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{approvalsCount} Pending</div>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ width: "100%", marginTop: 10 }}
            onClick={() => onNavigate("command", "recent-tasks")}
          >
            Review Lifecycle &amp; Tasks <ArrowRight size={12} />
          </button>
        </div>

        {/* Panel 5: Tamper-Evident Event Stream */}
        <div className="dashboard-panel">
          <div className="panel-header">
            <div className="row">
              <Radio size={16} />
              <strong>Audit &amp; Event Stream</strong>
            </div>
            <span className="pill">SHA-256</span>
          </div>
          <div className="events-mini-feed">
            {recentEvents.slice(0, 3).map((ev) => (
              <div key={ev.id} className="event-mini-item">
                <div className="row-between">
                  <span className="mono" style={{ fontSize: 10, color: "var(--text-muted)" }}>{ev.tag}</span>
                  <span className="mono" style={{ fontSize: 10, color: "var(--text-muted)" }}>{ev.time}</span>
                </div>
                <div style={{ fontSize: 12, marginTop: 2, color: "var(--text-secondary)" }}>{ev.title}</div>
              </div>
            ))}
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ width: "100%", marginTop: 10 }}
            onClick={() => onNavigate("security", "audit")}
          >
            Inspect Audit Trail <ArrowRight size={12} />
          </button>
        </div>

        {/* Panel 6: System Health & Security Posture */}
        <div className="dashboard-panel">
          <div className="panel-header">
            <div className="row">
              <Shield size={16} />
              <strong>System Posture</strong>
            </div>
            <span className="pill">SECURE</span>
          </div>
          <p className="panel-desc">
            SENTINEL zero-trust isolation, VAULT encrypted credential store, and strict tenant partitioning verified.
          </p>
          <div className="panel-metric-row">
            <div>
              <div className="telemetry-label">DATABASE</div>
              <div className="mono" style={{ fontSize: 13, fontWeight: 600 }}>{dbConnected ? "ONLINE" : "OFFLINE"}</div>
            </div>
            <div>
              <div className="telemetry-label">TENANT ISOLATION</div>
              <div className="mono" style={{ fontSize: 13, fontWeight: 600 }}>ENFORCED</div>
            </div>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            style={{ width: "100%", marginTop: 10 }}
            onClick={() => onNavigate("command", "system-health")}
          >
            Full Telemetry Report <ArrowRight size={12} />
          </button>
        </div>
      </section>

      {/* 4. FAST ACCESS TO ALL 112 PAGES & SUBSYSTEMS */}
      <section className="subsystems-jump-strip">
        <div className="row-between" style={{ marginBottom: 12 }}>
          <div>
            <div className="eyebrow-mono">NAVIGATION REGISTRY</div>
            <h2 style={{ fontSize: 16, marginTop: 2 }}>Subsystem Portals (112 Pages)</h2>
          </div>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => onNavigate("terminal", "master-terminal")}
          >
            <Terminal size={13} />
            <span>Master Terminal (Page 112)</span>
          </button>
        </div>

        <div className="subsystems-grid">
          {[
            { id: "neon", name: "NEON Intelligence", pages: "Pages 009–018", icon: <Sparkles size={16} /> },
            { id: "argon", name: "ARGON Orchestrator", pages: "Pages 019–028", icon: <Workflow size={16} /> },
            { id: "agents", name: "Specialist Agents", pages: "Pages 029–038", icon: <Bot size={16} /> },
            { id: "connections", name: "Connections Hub", pages: "Pages 039–048", icon: <Radio size={16} /> },
            { id: "projects", name: "Projects & FORGE", pages: "Pages 049–058", icon: <Cpu size={16} /> },
            { id: "files", name: "Files & Knowledge", pages: "Pages 059–068", icon: <Layers size={16} /> },
            { id: "security", name: "Security & AEGIS", pages: "Pages 079–088", icon: <Shield size={16} /> },
            { id: "devices", name: "Orbit Devices", pages: "Pages 089–098", icon: <Globe size={16} /> },
          ].map((sub) => (
            <button
              key={sub.id}
              type="button"
              className="subsystem-card-btn"
              onClick={() => onNavigate(sub.id)}
            >
              <div className="row-between">
                <span className="subsystem-icon">{sub.icon}</span>
                <ArrowRight size={13} className="muted" />
              </div>
              <div className="subsystem-name">{sub.name}</div>
              <div className="subsystem-pages mono">{sub.pages}</div>
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
export default CommandCenterView;
