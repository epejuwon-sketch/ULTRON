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
import { CommandCenterView } from "../components/CommandCenterView";

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
  onSendToNeon,
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

      {/* 1. HOME / COMMAND CENTER — Central Command Interface with Realistic Earth */}
      {page.id === "home" && (
        <CommandCenterView
          backendReady={dbConnected}
          backendDetail={error || (!dbConnected ? "Database degraded or in standalone mode." : "")}
          onNavigate={(mod, sub) => onNavigate(mod as ModuleId, sub)}
          onSendToNeon={onSendToNeon || (() => {})}
          device={device}
        />
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
