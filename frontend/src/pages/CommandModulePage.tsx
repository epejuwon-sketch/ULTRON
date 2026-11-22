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
  Sparkles,
  Workflow,
} from "lucide-react";
import { apiFetch } from "../lib/api";
import { getModule, getSubPage, ModuleId } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import { EarthGlobe } from "../components/EarthGlobe";
import {
  ActivityFeed,
  ConfirmationDialog,
  DataTable,
  EmptyState,
  ErrorState,
  LoadingState,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";

export type { ModulePageProps };

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
  const [overview, setOverview] = useState<any>(null);
  const [agents, setAgents] = useState<any[]>([]);
  const [tasks, setTasks] = useState<any[]>([]);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [auditLogs, setAuditLogs] = useState<any[]>([]);
  const [conversations, setConversations] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Quick command dispatch on Home
  const [cmd, setCmd] = useState("");
  const [cmdMode, setCmdMode] = useState<"neon" | "argon">("neon");
  const [dispatching, setDispatching] = useState(false);
  const [dispatchResult, setDispatchResult] = useState<{ title: string; detail: string; meta: string } | null>(null);
  const [confirmCancelId, setConfirmCancelId] = useState<string | null>(null);

  async function refresh() {
    setError("");
    try {
      const [h, r, ov, ag, tk, notif, aud, conv] = await Promise.all([
        apiFetch<any>("/health").catch(() => null),
        apiFetch<any>("/health/ready").catch(() => null),
        apiFetch<any>("/api/v1/monitoring/overview").catch(() => null),
        apiFetch<any>("/api/v1/agents").catch(() => ({ agents: [] })),
        apiFetch<any>("/api/v1/tasks").catch(() => ({ tasks: [] })),
        apiFetch<any>("/api/v1/notifications").catch(() => ({ notifications: [] })),
        apiFetch<any>("/api/v1/audit/logs?limit=25").catch(() => ({ logs: [] })),
        apiFetch<any>("/api/v1/neon/conversations").catch(() => ({ conversations: [] })),
      ]);
      setHealth(h);
      setReady(r);
      setOverview(ov);
      setAgents(ag.agents || []);
      setTasks(tk.tasks || []);
      setNotifications(notif.notifications || []);
      setAuditLogs(aud.logs || []);
      setConversations(conv.conversations || []);
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
    await apiFetch(`/api/v1/notifications/${id}/read`, { method: "POST" });
    refresh();
  }

  async function markAllNotificationsRead() {
    await apiFetch("/api/v1/notifications/read-all", { method: "POST" });
    pushToast("All notifications marked read.", "success");
    refresh();
  }

  const dbConnected = ready ? ready.status === "ready" || Boolean(ready.database?.connected) : null;
  const geminiLive = Boolean(health?.providers?.gemini?.configured);
  const globeStatus: "ready" | "degraded" | "loading" =
    dbConnected === null ? "loading" : dbConnected ? "ready" : "degraded";
  const unreadCount = notifications.filter((n) => !n.read).length;

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

      {/* 1. HOME / COMMAND CENTER — Rotating 3D Earth ONLY on Home */}
      {page.id === "home" && (
        <div className="command-stage">
          <section className="orbital-hero">
            <div className="orbital-header">
              <div>
                <div className="eyebrow-mono">ORBITAL COMMAND INTERFACE · {user.username.toUpperCase()}</div>
                <h2 className="hero-title">Global System Command</h2>
              </div>
              <div className="row">
                <StatusIndicator
                  label={dbConnected ? "DATABASE READY" : dbConnected === false ? "DB DEGRADED" : "SYNCING"}
                  tone={dbConnected ? "success" : dbConnected === false ? "warn" : "neutral"}
                />
                <StatusIndicator
                  label={geminiLive ? "GEMINI LIVE" : "GEMINI UNCONFIGURED"}
                  tone={geminiLive ? "info" : "neutral"}
                />
              </div>
            </div>

            <div className="orbital-core">
              <div className="orbital-globe-wrap">
                <EarthGlobe size={device.isMobile ? 250 : 320} status={globeStatus} />
                <div className="orbital-caption mono">
                  <span>{device.deviceClass.toUpperCase()}</span>
                  <span>·</span>
                  <span>DRAG TO ROTATE</span>
                </div>
              </div>

              <div className="telemetry-rail">
                <MetricDisplay
                  label="Specialist Agents"
                  value={`${agents.length || 60} Registered`}
                  sub="25 Core · 35 Extensible"
                  tone="info"
                />
                <MetricDisplay
                  label="Persistence"
                  value={ready?.database?.backend ? String(ready.database.backend).toUpperCase() : "Checking"}
                  sub={dbConnected ? "Transaction Pooler / Verified" : "Awaiting check"}
                  tone={dbConnected ? "success" : "warn"}
                />
                <MetricDisplay
                  label="Active Tasks"
                  value={tasks.length}
                  sub={`${tasks.filter((t) => t.lifecycle_state === "COMPLETED").length} completed`}
                  tone="neutral"
                />
                <MetricDisplay
                  label="Security & Alerts"
                  value={`${unreadCount} Unread`}
                  sub="AEGIS + VAULT Active"
                  tone={unreadCount > 0 ? "warn" : "success"}
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

          <section className="workspace-strip">
            {[
              { m: "neon" as ModuleId, label: "NEON Intelligence", desc: "Streaming AI console & multimodal", icon: Sparkles },
              { m: "argon" as ModuleId, label: "ARGON Orchestration", desc: "DAG workflows, jobs & approvals", icon: Workflow },
              { m: "agents" as ModuleId, label: "60 Specialist Agents", desc: "Inspect manifests & invoke directly", icon: Bot },
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
              <MetricDisplay label="Registered Agents" value={agents.length} sub="Independent manifests" tone="info" />
              <MetricDisplay label="HTTP Requests" value={overview?.total_requests ?? 0} sub="Live telemetry counter" tone="neutral" />
              <MetricDisplay label="Error Rate" value={`${overview?.error_rate_pct ?? 0}%`} sub="5xx response ratio" tone={Number(overview?.error_rate_pct || 0) > 2 ? "warn" : "success"} />
              <MetricDisplay label="Tenant Tasks" value={tasks.length} sub="ARGON task ledger" tone="info" />
              <MetricDisplay label="NEON Sessions" value={conversations.length} sub="Persisted conversations" tone="neutral" />
              <MetricDisplay label="Audit Events" value={auditLogs.length} sub="Hash-chained entries" tone="success" />
            </div>
            <div className="card">
              <div className="card-title"><span>Live Provider & Backend Readiness</span></div>
              <pre className="code-block">{JSON.stringify({ health: health?.providers, database: ready?.database, monitoring: overview }, null, 2)}</pre>
            </div>
          </div>
        )
      )}

      {/* 3. LIVE ACTIVITY */}
      {page.id === "activity" && (
        loading ? <LoadingState /> : (
          <div className="card">
            <div className="card-title"><span>Live System & Audit Activity ({auditLogs.length})</span></div>
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
        <div className="card">
          <div className="card-title">
            <span>Recent Tasks ({tasks.length})</span>
            <button type="button" className="btn btn-sm" onClick={() => onNavigate("argon", "orchestrate")}>
              New Orchestration
            </button>
          </div>
          <DataTable
            rows={tasks}
            rowKey={(t) => t.task_id}
            emptyTitle="No Tasks Recorded"
            emptyDescription="Dispatch a task from Home or ARGON Orchestration to track lifecycle execution here."
            columns={[
              { key: "title", header: "Task", render: (t) => <strong>{t.title || t.objective?.slice(0, 64)}</strong> },
              { key: "agent", header: "Agent", mono: true, render: (t) => t.assigned_agent_id || "AGT-02" },
              { key: "state", header: "Lifecycle", render: (t) => <StatusIndicator label={t.lifecycle_state || t.status} tone={t.lifecycle_state === "COMPLETED" ? "success" : t.lifecycle_state === "FAILED" ? "danger" : "info"} /> },
              {
                key: "actions",
                header: "Controls",
                render: (t) => (
                  <div className="row">
                    {["READY", "APPROVED"].includes(t.lifecycle_state) && (
                      <button type="button" className="btn btn-sm" onClick={() => runTaskAction(t.task_id, "execute")}><Play size={12} /> Run</button>
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
            { title: "Browse All 60 Agents", desc: "Inspect manifests and invoke specialists", action: () => onNavigate("agents", "directory") },
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
              <span><Gauge size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Readiness Probe (/health/ready)</span>
              <StatusIndicator label={dbConnected ? "HEALTHY" : "DEGRADED"} tone={dbConnected ? "success" : "warn"} />
            </div>
            <pre className="code-block">{JSON.stringify(ready, null, 2)}</pre>
          </div>
          <div className="card">
            <div className="card-title"><span>Runtime & Provider Probe (/health)</span></div>
            <pre className="code-block">{JSON.stringify(health, null, 2)}</pre>
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
