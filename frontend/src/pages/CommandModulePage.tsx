import React, { useEffect, useState } from "react";
import {
  Activity,
  ArrowUpRight,
  Bell,
  Bot,
  CheckCheck,
  FolderOpen,
  Gauge,
  Hammer,
  Play,
  Plug,
  RefreshCw,
  Send,
  Shield,
  ShieldAlert,
  Sparkles,
  Workflow,
} from "lucide-react";
import { apiFetch, resolveGeminiProviderStatus } from "../lib/api";
import { getModule, getSubPage, ModuleId } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import { EarthGlobe } from "../components/EarthGlobe";
import { MasterSchematicView } from "../components/MasterSchematicView";
import {
  ActivityFeed,
  ConfirmationDialog,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  LoadingState,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";
import { ReadableSummary } from "../components/ui/HumanPresentation";
import { UniversalIntegrationHub } from "../components/integrations/UniversalIntegrationHub";

export type { ModulePageProps };

type TaskFilter = "all" | "active" | "completed" | "failed" | "cancelled";

function taskTone(state?: string): "success" | "info" | "warn" | "danger" | "neutral" {
  const s = String(state || "").toUpperCase();
  if (s === "COMPLETED") return "success";
  if (s === "FAILED") return "danger";
  if (s === "PENDING_APPROVAL" || s === "PAUSED") return "warn";
  if (s === "CANCELLED") return "neutral";
  return "info";
}

export default function CommandModulePage({
  subPage,
  onSelectSubPage,
  onNavigate,
  user,
  device,
}: ModulePageProps) {
  const mod = getModule("command");
  const page = getSubPage("command", subPage);
  const { pushToast } = useToast();

  const [health, setHealth] = useState<any>(null);
  const [ready, setReady] = useState<any>(null);
  const [geminiDiag, setGeminiDiag] = useState<any>(null);
  const [overview, setOverview] = useState<any>(null);
  const [agents, setAgents] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [approvals, setApprovals] = useState<any[]>([]);
  const [connections, setConnections] = useState<any[]>([]);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [conversations, setConversations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [taskFilter, setTaskFilter] = useState<TaskFilter>("all");

  // Quick command dispatch on Home
  const [cmd, setCmd] = useState("");
  const [cmdMode, setCmdMode] = useState<"neon" | "argon">("neon");
  const [viewMode, setViewMode] = useState<"schematic" | "globe">("schematic");
  const [dispatching, setDispatching] = useState(false);
  const [dispatchResult, setDispatchResult] = useState<{ title: string; detail: string; meta: string } | null>(null);
  const [confirmCancelId, setConfirmCancelId] = useState<string | null>(null);

  async function refresh() {
    setError("");
    const authErrors: string[] = [];
    const trackErr = <T,>(fallback: T) => (err: any): T => {
      if (err?.message) authErrors.push(String(err.message));
      return fallback;
    };
    try {
      const [h, r, gd, ov, ag, tk, ap, conn, notif, aud, conv] = await Promise.all([
        apiFetch<any>("/health").catch(() => null),
        apiFetch<any>("/health/ready").catch(() => null),
        apiFetch<any>("/api/v1/neon/gemini/diagnostics?discover=false").catch(trackErr(null)),
        apiFetch<any>("/api/v1/monitoring/overview").catch(trackErr(null)),
        apiFetch<any>("/api/v1/agents").catch(trackErr({ agents: [] })),
        apiFetch<any>("/api/v1/tasks").catch(trackErr({ tasks: [] })),
        apiFetch<any>("/api/v1/approvals").catch(trackErr({ approvals: [] })),
        apiFetch<any>("/api/v1/integrations/connections").catch(trackErr({ connections: [] })),
        apiFetch<any>("/api/v1/notifications").catch(trackErr({ notifications: [] })),
        apiFetch<any>("/api/v1/audit/logs?limit=25").catch(trackErr({ logs: [] })),
        apiFetch<any>("/api/v1/neon/conversations").catch(trackErr({ conversations: [] })),
      ]);
      setHealth(h);
      setReady(r);
      setGeminiDiag(gd);
      setOverview(ov);
      setAgents(ag.agents || []);
      setTasks(tk.tasks || []);
      setApprovals(ap.approvals || []);
      setConnections(conn.connections || conn.integrations || []);
      setNotifications(notif.notifications || []);
      setAuditLogs(aud.logs || []);
      setConversations(conv.conversations || []);
      if (authErrors.length >= 3) {
        setError(authErrors[0]);
      }
    } catch (e: any) {
      setError(e.message || "Failed to load Command Centre telemetry.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refresh();
  }, [subPage]);

  async function handleDispatch(e: React.FormEvent) {
    e.preventDefault();
    const prompt = cmd.trim();
    if (!prompt) return;
    setDispatching(true);
    setError("");
    try {
      if (cmdMode === "argon") {
        const res = await apiFetch<any>("/api/v1/orchestrate", {
          method: "POST",
          body: { objective: prompt, auto_execute: true },
        });
        setDispatchResult({
          title: `ARGON · ${res.neon_routing?.selected_agent_id || "AGT-02"}`,
          detail:
            res.task?.result_summary ||
            `Lifecycle: ${res.task?.lifecycle_state} (${(res.task?.steps || []).length} steps)`,
          meta: `Tier ${res.neon_routing?.reasoning_tier ?? "T2"} · ${res.task?.lifecycle_state || "EXECUTED"}`,
        });
        pushToast("ARGON workflow dispatched.", "success");
      } else {
        const conv = await apiFetch<any>("/api/v1/neon/conversations", {
          method: "POST",
          body: { title: prompt.slice(0, 48), agent_id: "AGT-01" },
        });
        const msg = await apiFetch<any>(`/api/v1/neon/conversations/${conv.conversation_id}/messages`, {
          method: "POST",
          body: { content: prompt },
        });
        const replyObj = msg.reply;
        const replyText =
          typeof replyObj === "string"
            ? replyObj
            : replyObj?.output || msg.assistant_message?.content || "NEON processed directive.";
        const replyModel =
          (typeof replyObj === "object" && replyObj?.model) ||
          msg.assistant_message?.model ||
          "NEON";
        setDispatchResult({
          title: "NEON · AGT-01",
          detail: replyText,
          meta: `${replyModel} · VAULT guarded`,
        });
        pushToast("NEON directive completed.", "success");
      }
      setCmd("");
      refresh();
    } catch (err: any) {
      setError(err.message);
      pushToast(err.message, "error");
    } finally {
      setDispatching(false);
    }
  }

  async function runTaskAction(taskId: string, action: "execute" | "pause" | "resume" | "retry" | "cancel") {
    try {
      await apiFetch(`/api/v1/tasks/${taskId}/${action}`, { method: "POST" });
      pushToast(`Task ${action}d.`, "success");
      refresh();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function markNotificationRead(id: string) {
    try {
      await apiFetch(`/api/v1/notifications/${id}/read`, { method: "POST" });
      refresh();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function markAllNotificationsRead() {
    try {
      await apiFetch("/api/v1/notifications/read-all", { method: "POST" });
      pushToast("All notifications marked read.", "success");
      refresh();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  const dbConnected = ready ? ready.status === "ready" || Boolean(ready.database?.connected) : null;
  const geminiStatus = resolveGeminiProviderStatus({ geminiDiag, health, ready });
  const globeStatus: "ready" | "degraded" | "loading" =
    dbConnected === null ? "loading" : dbConnected ? "ready" : "degraded";

  const unreadCount = notifications.filter((n) => !n.read).length;
  const pendingApprovals = approvals.filter((a) => a.status === "PENDING");
  const availableAgentsCount = agents.filter(
    (a) => String(a.capability_state || "AVAILABLE").toUpperCase() === "AVAILABLE"
  ).length;
  const degradedAgentsCount = agents.length - availableAgentsCount;
  const completedTasksCount = tasks.filter((t) => t.lifecycle_state === "COMPLETED").length;
  const failedTasksCount = tasks.filter((t) => t.lifecycle_state === "FAILED").length;
  const activeTasksCount = tasks.filter(
    (t) => !["COMPLETED", "FAILED", "CANCELLED"].includes(String(t.lifecycle_state || "").toUpperCase())
  ).length;
  const connectedIntegrations = connections.filter(
    (c) => String(c.status || c.state || "").toUpperCase() === "CONNECTED" || c.connected === true
  );

  const filteredTasks = tasks.filter((t) => {
    const st = String(t.lifecycle_state || t.status || "").toUpperCase();
    if (taskFilter === "completed") return st === "COMPLETED";
    if (taskFilter === "failed") return st === "FAILED";
    if (taskFilter === "cancelled") return st === "CANCELLED";
    if (taskFilter === "active") return !["COMPLETED", "FAILED", "CANCELLED"].includes(st);
    return true;
  });

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`ULTRON OS 2026 // MODULE 01 · PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <button type="button" className="btn btn-secondary btn-sm" onClick={refresh}>
            <RefreshCw size={13} /> Refresh
          </button>
        }
      />

      {error && <ErrorState message={error} onRetry={refresh} />}

      {/* 1. HOME / COMMAND CENTER — Central Operational Headquarters & 112 Master Schematic */}
      {page.id === "home" && (
        <div className="command-stage">
          <div className="row-between mb-3" style={{ flexWrap: "wrap", gap: 8 }}>
            <div className="segmented">
              <button
                type="button"
                className={`seg-btn ${viewMode === "schematic" ? "active" : ""}`}
                onClick={() => setViewMode("schematic")}
              >
                112-PAGE MASTER SCHEMATIC
              </button>
              <button
                type="button"
                className={`seg-btn ${viewMode === "globe" ? "active" : ""}`}
                onClick={() => setViewMode("globe")}
              >
                ORBITAL EARTH COMMAND
              </button>
            </div>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => onNavigate("terminal", "master-terminal")}
              style={{ color: "#38bdf8", borderColor: "rgba(56,189,248,0.4)" }}
            >
              <Sparkles size={13} /> Launch Master Terminal (112)
            </button>
          </div>

          {viewMode === "schematic" ? (
            <MasterSchematicView
              device={device}
              activeModule="command"
              activeSubPage={subPage}
              onNavigate={onNavigate}
              onDispatchToTerminal={() => onNavigate("terminal", "master-terminal")}
            />
          ) : (
            <section className="orbital-hero">
            <div className="orbital-header">
              <div>
                <div className="eyebrow-mono">OPERATIONAL HEADQUARTERS · {user.username.toUpperCase()}</div>
                <h2 className="hero-title">ULTRON Command Centre</h2>
              </div>
              <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                <StatusIndicator
                  label={dbConnected ? "DATABASE READY" : dbConnected === false ? "DB DEGRADED" : "SYNCING"}
                  tone={dbConnected ? "success" : dbConnected === false ? "warn" : "neutral"}
                />
                <StatusIndicator label={geminiStatus.label} tone={geminiStatus.tone} />
                <StatusIndicator
                  label={`ARGON: ${activeTasksCount} ACTIVE`}
                  tone={failedTasksCount > 0 ? "warn" : "info"}
                />
              </div>
            </div>

            <div className="orbital-core">
              <div className="orbital-globe-wrap">
                <EarthGlobe size={device.isMobile ? 240 : 300} status={globeStatus} />
                <div className="orbital-caption mono">
                  <span>{device.deviceClass.toUpperCase()}</span>
                  <span>·</span>
                  <span>{ready?.config?.env ? String(ready.config.env).toUpperCase() : "ACTIVE"}</span>
                </div>
              </div>

              <div className="telemetry-rail">
                <MetricDisplay
                  label="60 Specialist Agents"
                  value={`${availableAgentsCount || agents.length}/${agents.length || 60} Ready`}
                  sub={degradedAgentsCount > 0 ? `${degradedAgentsCount} degraded/disabled` : "25 Core · 35 Specialist"}
                  tone={degradedAgentsCount > 0 ? "warn" : "success"}
                />
                <MetricDisplay
                  label="ARGON Tasks"
                  value={tasks.length}
                  sub={`${completedTasksCount} done · ${failedTasksCount} failed`}
                  tone={failedTasksCount > 0 ? "warn" : "info"}
                />
                <MetricDisplay
                  label="ApprovalGate Queue"
                  value={`${pendingApprovals.length} Pending`}
                  sub={pendingApprovals.length > 0 ? "Requires operator review" : "All gates clear"}
                  tone={pendingApprovals.length > 0 ? "warn" : "success"}
                />
                <MetricDisplay
                  label="Integrations"
                  value={`${connectedIntegrations.length} Connected`}
                  sub={`${connections.length} tenant record(s)`}
                  tone={connectedIntegrations.length > 0 ? "success" : "neutral"}
                />
                <MetricDisplay
                  label="System Health"
                  value={`${overview?.error_rate_pct ?? 0}% Err`}
                  sub={`${overview?.total_requests ?? 0} HTTP requests`}
                  tone={Number(overview?.error_rate_pct || 0) > 2 ? "warn" : "success"}
                />
                <MetricDisplay
                  label="Alerts & Audit"
                  value={`${unreadCount} Unread`}
                  sub={`${auditLogs.length} recent audit events`}
                  tone={unreadCount > 0 ? "warn" : "neutral"}
                />
              </div>
            </div>

            <form className="command-dock" onSubmit={handleDispatch}>
              <div className="row-between">
                <div className="command-dock-modes">
                  <button
                    id="cmd-mode-neon"
                    type="button"
                    className={`seg-btn ${cmdMode === "neon" ? "active" : ""}`}
                    onClick={() => setCmdMode("neon")}
                  >
                    NEON Intelligence
                  </button>
                  <button
                    id="cmd-mode-argon"
                    type="button"
                    className={`seg-btn ${cmdMode === "argon" ? "active" : ""}`}
                    onClick={() => setCmdMode("argon")}
                  >
                    ARGON Orchestrate
                  </button>
                </div>
                <span className="muted mono" style={{ fontSize: 11 }}>
                  {cmdMode === "argon" ? "POST /api/v1/orchestrate" : "POST /api/v1/neon/conversations"}
                </span>
              </div>
              <div className="command-dock-row">
                <input
                  id="command-center-input"
                  className="input command-input"
                  value={cmd}
                  onChange={(e) => setCmd(e.target.value)}
                  placeholder={
                    cmdMode === "argon"
                      ? "Dispatch multi-agent objective to ARGON..."
                      : "Issue command or question to NEON (VAULT protected)..."
                  }
                />
                <button
                  id="command-center-submit"
                  className="btn"
                  type="submit"
                  disabled={dispatching || !cmd.trim()}
                >
                  <Send size={14} />
                  <span>{dispatching ? "Executing..." : "Execute"}</span>
                </button>
              </div>
            </form>

            {dispatchResult && (
              <div id="command-dispatch-result" className="dispatch-output">
                <div className="row-between">
                  <span className="mono-tag">{dispatchResult.title}</span>
                  <span className="muted mono">{dispatchResult.meta}</span>
                </div>
                <div className="dispatch-text">{dispatchResult.detail}</div>
              </div>
            )}
          </section>
          )}

          {/* Operational Headquarters Panels (Live Backend State Only) */}
          <section className="grid-3">
            {/* Live Tasks & Recent Operations */}
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="card-title">
                <span>Live Tasks &amp; Operations</span>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => onSelectSubPage("recent-tasks")}>
                  Manage
                </button>
              </div>
              {tasks.length === 0 ? (
                <div className="muted" style={{ fontSize: 12.5 }}>No tasks recorded yet. Dispatch via ARGON or the command dock above.</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {tasks.slice(0, 4).map((t) => (
                    <div key={t.task_id} className="list-item" style={{ padding: "8px 10px" }}>
                      <div className="row-between" style={{ gap: 6 }}>
                        <strong style={{ fontSize: 12.5 }}>{t.title || t.objective?.slice(0, 42)}</strong>
                        <StatusIndicator label={t.lifecycle_state || t.status} tone={taskTone(t.lifecycle_state)} />
                      </div>
                      <div className="muted mono" style={{ fontSize: 11, marginTop: 2 }}>
                        {t.assigned_agent_id || "AGT-02"} · {(t.steps || []).length} steps
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Pending Approvals & Connected Integrations */}
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="card-title">
                <span><ShieldAlert size={14} style={{ verticalAlign: "middle", marginRight: 5 }} />Approvals &amp; Integrations</span>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("argon", "approvals")}>
                  Queue
                </button>
              </div>
              {pendingApprovals.length > 0 ? (
                <div className="list-item" style={{ borderLeft: "3px solid var(--warn)" }}>
                  <div className="row-between">
                    <strong>{pendingApprovals.length} Pending Approval{pendingApprovals.length === 1 ? "" : "s"}</strong>
                    <button type="button" className="btn btn-sm" onClick={() => onNavigate("argon", "approvals")}>
                      Review
                    </button>
                  </div>
                  <div className="muted" style={{ fontSize: 12 }}>
                    {pendingApprovals[0]?.action_type || pendingApprovals[0]?.resource || "Governed mutation awaiting decision"}
                  </div>
                </div>
              ) : (
                <div className="list-item" style={{ padding: "8px 10px" }}>
                  <div className="row-between">
                    <span style={{ fontSize: 12.5 }}>ApprovalGate Queue</span>
                    <StatusIndicator label="CLEAR" tone="success" />
                  </div>
                </div>
              )}

              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <div className="row-between">
                  <span className="telemetry-label">INTEGRATION STATES</span>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("connections", "directory")}>
                    Directory
                  </button>
                </div>
                {connections.length === 0 ? (
                  <div className="muted" style={{ fontSize: 12 }}>
                    Gemini: {geminiStatus.label}. Open Connections Centre to configure OAuth or API providers.
                  </div>
                ) : (
                  connections.slice(0, 3).map((c: any, idx: number) => (
                    <div key={c.provider || idx} className="row-between list-item" style={{ padding: "6px 10px" }}>
                      <span className="mono" style={{ fontSize: 12 }}>{c.provider || c.name}</span>
                      <StatusIndicator
                        label={String(c.status || "CONFIGURED").toUpperCase()}
                        tone={String(c.status || "").toUpperCase() === "CONNECTED" ? "success" : "neutral"}
                      />
                    </div>
                  ))
                )}
              </div>
            </div>

            {/* Recent Activity & Audit Trail */}
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="card-title">
                <span>Recent Audit &amp; Activity</span>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => onSelectSubPage("activity")}>
                  Full Feed
                </button>
              </div>
              {auditLogs.length === 0 ? (
                <div className="muted" style={{ fontSize: 12.5 }}>No audit events recorded yet.</div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  {auditLogs.slice(0, 4).map((l: any, idx: number) => (
                    <div key={l.audit_id || idx} className="list-item" style={{ padding: "7px 10px" }}>
                      <div className="row-between">
                        <strong style={{ fontSize: 12 }}>{l.action || l.event_type || "AUDIT"}</strong>
                        <span className="pill mono" style={{ fontSize: 10 }}>{l.outcome || l.status || "OK"}</span>
                      </div>
                      <div className="muted mono" style={{ fontSize: 10.5 }}>
                        {l.resource || "system"}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>

          <section className="workspace-strip">
            {[
              { m: "neon" as ModuleId, label: "NEON Intelligence", desc: "Streaming AI console & multimodal", icon: Sparkles },
              { m: "argon" as ModuleId, label: "ARGON Orchestration", desc: "DAG workflows, jobs & approvals", icon: Workflow },
              { m: "agents" as ModuleId, label: "60 Specialist Agents", desc: "Domain workbenches & manifests", icon: Bot },
              { m: "connections" as ModuleId, label: "Connections Centre", desc: "38 integrations & honest OAuth", icon: Plug },
              { m: "files" as ModuleId, label: "Files & Knowledge", desc: "File Hub, Drive & semantic memory", icon: FolderOpen },
              { m: "projects" as ModuleId, label: "Projects & FORGE", desc: "Code generation, preview & GitHub", icon: Hammer },
              { m: "security" as ModuleId, label: "Security Centre", desc: "AEGIS, SHA-256 audit & VAULT", icon: Shield },
              { m: "pulse" as ModuleId, label: "PULSE & Automation", desc: "Live telemetry & tool execution", icon: Activity },
            ].map((tile) => {
              const Icon = tile.icon;
              return (
                <button
                  key={tile.m}
                  id={`tile-${tile.m}`}
                  type="button"
                  className="workspace-tile"
                  onClick={() => onNavigate(tile.m)}
                >
                  <div className="row-between">
                    <span className="tile-icon"><Icon size={17} /></span>
                    <ArrowUpRight size={14} className="muted" />
                  </div>
                  <div className="tile-title">{tile.label}</div>
                  <div className="tile-desc">{tile.desc}</div>
                </button>
              );
            })}
          </section>
        </div>
      )}

      {/* 2. GLOBAL SYSTEM OVERVIEW */}
      {page.id === "overview" && (
        loading ? <LoadingState /> : (
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div className="grid-3">
              <MetricDisplay label="Registered Agents" value={agents.length} sub={`${availableAgentsCount} available`} tone="info" />
              <MetricDisplay label="HTTP Requests" value={overview?.total_requests ?? 0} sub="Live telemetry counter" tone="neutral" />
              <MetricDisplay label="Error Rate" value={`${overview?.error_rate_pct ?? 0}%`} sub="5xx response ratio" tone={Number(overview?.error_rate_pct || 0) > 2 ? "warn" : "success"} />
              <MetricDisplay label="Tenant Tasks" value={tasks.length} sub={`${completedTasksCount} completed · ${failedTasksCount} failed`} tone="info" />
              <MetricDisplay label="NEON Sessions" value={conversations.length} sub="Persisted conversations" tone="neutral" />
              <MetricDisplay label="Audit Events" value={auditLogs.length} sub="Hash-chained entries" tone="success" />
            </div>
            <div className="card">
              <div className="card-title"><span>Live Provider &amp; Backend Readiness</span></div>
              <ReadableSummary
                data={{
                  database_status: ready?.database?.connected ? "Connected" : "Degraded",
                  environment: ready?.config?.env || ready?.env || health?.env || "active",
                  gemini_configured: geminiStatus.configured,
                  gemini_status: geminiStatus.label,
                  total_requests: overview?.total_requests ?? 0,
                  error_rate_pct: `${overview?.error_rate_pct ?? 0}%`,
                  providers: health?.integrations?.providers,
                  database: ready?.database,
                  monitoring: overview,
                }}
                diagnosticsTitle="Technical Diagnostics — Readiness & Provider Telemetry"
              />
            </div>
          </div>
        )
      )}

      {/* 3. LIVE ACTIVITY */}
      {page.id === "activity" && (
        loading ? <LoadingState /> : (
          <div className="card">
            <div className="card-title"><span>Live System &amp; Audit Activity ({auditLogs.length})</span></div>
            <ActivityFeed
              items={auditLogs.map((l: any, i: number) => ({
                id: l.audit_id || String(i),
                title: l.action || l.event_type || "Audit Event",
                actor: l.actor_user_id || l.user_id || "system",
                status: l.status || l.outcome || "RECORDED",
                timestamp: l.created_at,
                detail: l.resource || l.detail || undefined,
              }))}
            />
          </div>
        )
      )}

      {/* 4. NOTIFICATIONS */}
      {page.id === "notifications" && (
        <div className="card">
          <div className="card-title">
            <span>System Notifications ({unreadCount} Unread)</span>
            {unreadCount > 0 && (
              <button type="button" className="btn btn-secondary btn-sm" onClick={markAllNotificationsRead}>
                <CheckCheck size={13} /> Mark All Read
              </button>
            )}
          </div>
          {notifications.length === 0 ? (
            <EmptyState title="No Notifications" description="ApprovalGate triggers, AEGIS alerts, and ORBIT updates will appear here." />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {notifications.map((n: any) => (
                <div key={n.notification_id} className="list-item">
                  <div className="row-between">
                    <div className="row">
                      <Bell size={14} className="muted" />
                      <strong>{n.title}</strong>
                    </div>
                    {!n.read ? (
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => markNotificationRead(n.notification_id)}>
                        Mark Read
                      </button>
                    ) : (
                      <span className="pill">READ</span>
                    )}
                  </div>
                  <div className="muted">{n.message}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 5. RECENT TASKS */}
      {page.id === "recent-tasks" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title">
            <span>Task Lifecycle Manager ({filteredTasks.length})</span>
            <button type="button" className="btn btn-sm" onClick={() => onNavigate("argon", "orchestrate")}>
              New Orchestration
            </button>
          </div>
          <FilterBar<TaskFilter>
            value={taskFilter}
            onChange={setTaskFilter}
            options={[
              { value: "all", label: "All", count: tasks.length },
              { value: "active", label: "Active", count: activeTasksCount },
              { value: "completed", label: "Completed", count: completedTasksCount },
              { value: "failed", label: "Failed", count: failedTasksCount },
              { value: "cancelled", label: "Cancelled" },
            ]}
          />
          <DataTable
            rows={filteredTasks}
            rowKey={(t) => t.task_id}
            emptyTitle="No Matching Tasks"
            emptyDescription="Dispatch a task from Home or ARGON Orchestration to track lifecycle execution here."
            columns={[
              { key: "title", header: "Task", render: (t) => <strong>{t.title || t.objective?.slice(0, 64)}</strong> },
              { key: "agent", header: "Agent", mono: true, render: (t) => t.assigned_agent_id || "AGT-02" },
              { key: "state", header: "Lifecycle", render: (t) => <StatusIndicator label={t.lifecycle_state || t.status} tone={taskTone(t.lifecycle_state)} /> },
              {
                key: "actions",
                header: "Controls",
                render: (t) => (
                  <div className="row" style={{ flexWrap: "wrap", gap: 5 }}>
                    {["READY", "APPROVED", "PLANNED"].includes(t.lifecycle_state) && (
                      <button type="button" className="btn btn-sm" onClick={() => runTaskAction(t.task_id, "execute")}><Play size={12} /> Run</button>
                    )}
                    {t.lifecycle_state === "RUNNING" && (
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => runTaskAction(t.task_id, "pause")}>Pause</button>
                    )}
                    {t.lifecycle_state === "PAUSED" && (
                      <button type="button" className="btn btn-sm" onClick={() => runTaskAction(t.task_id, "resume")}>Resume</button>
                    )}
                    {t.lifecycle_state === "FAILED" && (
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => runTaskAction(t.task_id, "retry")}>Retry</button>
                    )}
                    {!["COMPLETED", "CANCELLED"].includes(t.lifecycle_state) && (
                      <button type="button" className="btn btn-danger btn-sm" onClick={() => setConfirmCancelId(t.task_id)}>Cancel</button>
                    )}
                  </div>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* 6. QUICK ACTIONS */}
      {page.id === "quick-actions" && (
        <div className="grid-3">
          {[
            { title: "Start NEON Session", desc: "Open streaming intelligence chat", action: () => onNavigate("neon", "chat") },
            { title: "Review ApprovalGate", desc: "Approve or reject governed actions", action: () => onNavigate("argon", "approvals") },
            { title: "Browse All 60 Agents", desc: "Inspect manifests and specialist workbenches", action: () => onNavigate("agents", "directory") },
            { title: "Verify Integrations", desc: "Inspect honest 4-stage connectivity", action: () => onNavigate("connections", "directory") },
            { title: "Run AEGIS Security Scan", desc: "Check posture, incidents & audit chain", action: () => onNavigate("security", "overview") },
            { title: "Upload to File Hub", desc: "Upload documents with VAULT redaction", action: () => onNavigate("files", "upload") },
          ].map((qa) => (
            <div key={qa.title} className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <strong>{qa.title}</strong>
              <div className="muted">{qa.desc}</div>
              <button type="button" className="btn btn-secondary btn-sm" style={{ alignSelf: "flex-start" }} onClick={qa.action}>
                Launch <ArrowUpRight size={13} />
              </button>
            </div>
          ))}
        </div>
      )}

      {/* 7. SYSTEM HEALTH */}
      {page.id === "system-health" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title">
              <span><Gauge size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Database &amp; Readiness Status</span>
              <StatusIndicator label={dbConnected ? "HEALTHY" : "DEGRADED"} tone={dbConnected ? "success" : "warn"} />
            </div>
            <ReadableSummary
              data={ready || { status: "Loading..." }}
              diagnosticsTitle="Technical Diagnostics — /health/ready Payload"
            />
          </div>
          <div className="card">
            <div className="card-title"><span>Runtime &amp; Provider Status</span></div>
            <ReadableSummary
              data={health || { status: "Loading..." }}
              diagnosticsTitle="Technical Diagnostics — /health Payload"
            />
          </div>
        </div>
      )}

      {/* 8. COMMAND HISTORY */}
      {page.id === "command-history" && (
        <div className="card">
          <div className="card-title"><span>Dispatched NEON Sessions ({conversations.length})</span></div>
          <DataTable
            rows={conversations}
            rowKey={(c) => c.conversation_id}
            emptyTitle="No Command History"
            emptyDescription="Dispatched NEON conversations will be listed here with timestamps."
            columns={[
              { key: "title", header: "Session Title", render: (c) => <strong>{c.title}</strong> },
              { key: "agent", header: "Agent", mono: true, render: (c) => c.agent_id || "AGT-01" },
              { key: "updated", header: "Updated", mono: true, render: (c) => c.updated_at || c.created_at || "—" },
              {
                key: "open",
                header: "Open",
                render: () => (
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("neon", "chat")}>
                    Resume in NEON
                  </button>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* 120. UNIVERSAL INTEGRATION HUB */}
      {page.id === "integrations" && <UniversalIntegrationHub />}

      <ConfirmationDialog
        open={Boolean(confirmCancelId)}
        title="Cancel Active Task"
        message="Are you sure you want to cancel this ARGON task? Any running steps will stop."
        confirmLabel="Cancel Task"
        onCancel={() => setConfirmCancelId(null)}
        onConfirm={async () => {
          if (confirmCancelId) await runTaskAction(confirmCancelId, "cancel");
          setConfirmCancelId(null);
        }}
      />
    </ResponsiveWorkspace>
  );
}
