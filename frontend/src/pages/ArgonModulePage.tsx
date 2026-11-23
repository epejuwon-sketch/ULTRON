import React, { useEffect, useState } from "react";
import {
  ArrowRight,
  CheckCircle2,
  Clock,
  GitBranch,
  Pause,
  Play,
  RefreshCw,
  RotateCcw,
  Send,
  ShieldAlert,
  Square,
} from "lucide-react";
import { apiFetch } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import { AgentIcon } from "../catalog/agentIcons";
import type { ModulePageProps } from "../types/module";
import {
  ApprovalCard,
  ConfirmationDialog,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";
import { ReadableSummary, TechnicalDiagnostics } from "../components/ui/HumanPresentation";

type ArgonTaskFilter = "all" | "active" | "pending_approval" | "completed" | "failed" | "cancelled";

function lifecycleTone(state?: string): "success" | "info" | "warn" | "danger" | "neutral" {
  const s = String(state || "").toUpperCase();
  if (s === "COMPLETED") return "success";
  if (s === "FAILED" || s === "DEAD_LETTER") return "danger";
  if (s === "PENDING_APPROVAL" || s === "PAUSED") return "warn";
  if (s === "CANCELLED") return "neutral";
  return "info";
}

function ArgonTaskDagInspector({
  task,
  onAction,
  onCancelRequest,
}: {
  task: any;
  onAction: (taskId: string, action: "execute" | "enqueue" | "pause" | "resume" | "retry") => Promise<void>;
  onCancelRequest: (taskId: string) => void;
}) {
  if (!task) {
    return (
      <EmptyState
        title="Select a Task to Inspect DAG"
        description="Click any orchestrated task to inspect its multi-agent execution steps, handoffs, and verification outcome."
      />
    );
  }
  const state = String(task.lifecycle_state || task.status || "PLANNED").toUpperCase();
  const steps: any[] = Array.isArray(task.steps) ? task.steps : [];

  return (
    <div className="card" data-testid="argon-dag-inspector" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="row-between" style={{ flexWrap: "wrap", gap: 10 }}>
        <div>
          <div className="eyebrow-mono">DAG EXECUTION INSPECTOR · {task.task_id}</div>
          <h3 style={{ margin: "2px 0 0", fontSize: 16.5 }}>{task.title || task.objective?.slice(0, 72)}</h3>
          <div className="muted" style={{ fontSize: 12.5, marginTop: 3 }}>{task.objective}</div>
        </div>
        <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
          <StatusIndicator label={state} tone={lifecycleTone(state)} />
          {task.verification?.outcome_classification && (
            <StatusIndicator
              label={task.verification.outcome_classification}
              tone={
                task.verification.outcome_classification === "COMPLETED"
                  ? "success"
                  : task.verification.outcome_classification === "PARTIALLY_COMPLETED"
                  ? "warn"
                  : "danger"
              }
            />
          )}
          <span className="pill mono">Lead: {task.assigned_agent_id || "AGT-02"}</span>
          {task.reasoning_tier && <span className="pill mono">Tier {task.reasoning_tier}</span>}
          {Number(task.financial_amount_usd || 0) > 0 && (
            <span className="pill pill-warn mono">${task.financial_amount_usd} USD</span>
          )}
        </div>
      </div>

      {/* Visual Multi-Agent DAG Pipeline */}
      <div>
        <div className="telemetry-label" style={{ marginBottom: 8 }}>
          <GitBranch size={12} style={{ verticalAlign: "middle", marginRight: 5 }} />
          MULTI-AGENT WORKFLOW PIPELINE ({steps.length} STEP{steps.length === 1 ? "" : "S"})
        </div>
        {steps.length === 0 ? (
          <div className="muted" style={{ fontSize: 12.5 }}>Single-stage execution task (no decomposed sub-steps recorded).</div>
        ) : (
          <div className="argon-dag-track">
            {steps.map((step, idx) => {
              const st = String(step.status || "PENDING").toUpperCase();
              const tone = lifecycleTone(st);
              const deps: number[] = Array.isArray(step.depends_on) ? step.depends_on : [];
              const stepText = step.output?.output || step.output_summary || "";
              return (
                <React.Fragment key={step.step_id || idx}>
                  <div className={`argon-dag-node node-${tone}`}>
                    <div className="row-between" style={{ gap: 6 }}>
                      <span className="mono" style={{ fontSize: 10.5, color: "var(--accent)" }}>
                        STEP {step.step_number ?? step.step_order ?? idx + 1} · {step.agent_id}
                      </span>
                      <StatusIndicator label={st} tone={tone} />
                    </div>
                    <div className="row" style={{ gap: 8, marginTop: 6 }}>
                      <span className="agent-icon-badge" style={{ width: 28, height: 28 }}>
                        <AgentIcon agentId={step.agent_id || "AGT-02"} size={14} />
                      </span>
                      <strong style={{ fontSize: 13 }}>{step.description || step.action || "Execute Step"}</strong>
                    </div>
                    <div className="muted mono" style={{ fontSize: 10.5, marginTop: 5 }}>
                      {deps.length > 0 ? `Depends on: Step ${deps.join(", ")}` : "Root Wave"}
                      {Number(step.attempt_count || 0) > 0 ? ` · Attempts: ${step.attempt_count}` : ""}
                      {step.output?.execution_mode ? ` · ${step.output.execution_mode}` : ""}
                    </div>
                    {stepText && (
                      <div className="muted" style={{ fontSize: 11.5, marginTop: 6, lineHeight: 1.45 }}>
                        {String(stepText).slice(0, 180)}
                      </div>
                    )}
                    {step.error_detail && (
                      <div style={{ fontSize: 11.5, marginTop: 6, color: "var(--danger, #f87171)" }}>
                        Error: {step.error_detail}
                      </div>
                    )}
                  </div>
                  {idx < steps.length - 1 && (
                    <div className="argon-dag-connector" aria-hidden="true">
                      <ArrowRight size={15} />
                    </div>
                  )}
                </React.Fragment>
              );
            })}
          </div>
        )}
      </div>

      {/* Outcome / Verification Summary */}
      {(task.result?.final_output || task.result_summary || task.error_detail) && (
        <div className="dispatch-output">
          <div className="row-between" style={{ marginBottom: 4 }}>
            <span className="mono-tag">
              <CheckCircle2 size={12} style={{ verticalAlign: "middle", marginRight: 4 }} />
              VERIFICATION &amp; OUTCOME SUMMARY
            </span>
            <span className="muted mono" style={{ fontSize: 11 }}>
              Risk: {task.risk_level || "LOW"}
              {task.verification?.checked_steps ? ` · ${task.verification.completed_steps ?? 0}/${task.verification.checked_steps} Verified` : ""}
            </span>
          </div>
          <div className="dispatch-text">{task.result?.final_output || task.result_summary || task.error_detail}</div>
        </div>
      )}

      {/* Lifecycle Controls */}
      <div className="row-between" style={{ flexWrap: "wrap", gap: 8, paddingTop: 6, borderTop: "1px solid var(--border)" }}>
        <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
          {["PLANNED", "READY", "APPROVED"].includes(state) && (
            <>
              <button type="button" className="btn btn-sm" onClick={() => onAction(task.task_id, "execute")}>
                <Play size={12} /> Execute Now
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => onAction(task.task_id, "enqueue")}>
                <Clock size={12} /> Enqueue Worker
              </button>
            </>
          )}
          {state === "RUNNING" && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onAction(task.task_id, "pause")}>
              <Pause size={12} /> Pause
            </button>
          )}
          {state === "PAUSED" && (
            <button type="button" className="btn btn-sm" onClick={() => onAction(task.task_id, "resume")}>
              <Play size={12} /> Resume
            </button>
          )}
          {state === "FAILED" && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onAction(task.task_id, "retry")}>
              <RotateCcw size={12} /> Retry Failed Task
            </button>
          )}
          {!["COMPLETED", "CANCELLED"].includes(state) && (
            <button type="button" className="btn btn-danger btn-sm" onClick={() => onCancelRequest(task.task_id)}>
              <Square size={12} /> Cancel Task
            </button>
          )}
        </div>
        <TechnicalDiagnostics title="Technical Diagnostics — Task & Step Payload" data={task} />
      </div>
    </div>
  );
}

export default function ArgonModulePage({ subPage, onSelectSubPage }: ModulePageProps) {
  const mod = getModule("argon");
  const page = getSubPage("argon", subPage);
  const { pushToast } = useToast();

  const [tasks, setTasks] = useState<any[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string>("");
  const [taskFilter, setTaskFilter] = useState<ArgonTaskFilter>("all");
  const [jobs, setJobs] = useState<any[]>([]);
  const [schedules, setSchedules] = useState<any[]>([]);
  const [approvals, setApprovals] = useState<any[]>([]);
  const [messages, setMessages] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [dispatching, setDispatching] = useState(false);

  // Forms
  const [objective, setObjective] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [amountUsd, setAmountUsd] = useState("0");
  const [preferredAgent, setPreferredAgent] = useState("");
  const [schedName, setSchedName] = useState("");
  const [schedInterval, setSchedInterval] = useState("300");
  const [schedPrompt, setSchedPrompt] = useState("");
  const [routePrompt, setRoutePrompt] = useState("");
  const [routePreview, setRoutePreview] = useState<any>(null);
  const [fromAgent, setFromAgent] = useState("AGT-01");
  const [toAgent, setToAgent] = useState("AGT-03");
  const [msgSubject, setMsgSubject] = useState("");

  // Confirmation modal state
  const [confirmState, setConfirmState] = useState<{
    title: string;
    message: string;
    confirmLabel: string;
    destructive: boolean;
    onConfirm: () => Promise<void>;
  } | null>(null);

  async function load() {
    setError("");
    try {
      const [tRes, jRes, sRes, aRes, mRes, agRes] = await Promise.all([
        apiFetch<any>("/api/v1/tasks").catch(() => ({ tasks: [] })),
        apiFetch<any>("/api/v1/argon/jobs").catch(() => ({ jobs: [] })),
        apiFetch<any>("/api/v1/argon/schedules").catch(() => ({ schedules: [] })),
        apiFetch<any>("/api/v1/approvals").catch(() => ({ approvals: [] })),
        apiFetch<any>("/api/v1/agents/messages").catch(() => ({ messages: [] })),
        apiFetch<any>("/api/v1/agents").catch(() => ({ agents: [] })),
      ]);
      const tList = tRes.tasks || [];
      setTasks(tList);
      if (tList.length > 0 && !selectedTaskId) {
        setSelectedTaskId(tList[0].task_id);
      }
      setJobs(jRes.jobs || []);
      setSchedules(sRes.schedules || []);
      setApprovals(aRes.approvals || []);
      setMessages(mRes.messages || []);
      setAgents(agRes.agents || []);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, [subPage]);

  async function dispatchOrchestration(e: React.FormEvent) {
    e.preventDefault();
    if (!objective.trim()) return;
    setDispatching(true);
    try {
      let createdTaskId = "";
      if (Number(amountUsd) > 0 || taskTitle.trim() || preferredAgent) {
        const res = await apiFetch<any>("/api/v1/tasks", {
          method: "POST",
          body: {
            title: taskTitle.trim() || objective.trim().slice(0, 48),
            objective: objective.trim(),
            financial_amount_usd: Number(amountUsd) || 0,
            preferred_agent_id: preferredAgent || undefined,
          },
        });
        createdTaskId = res.task?.task_id || res.task_id || "";
      } else {
        const res = await apiFetch<any>("/api/v1/orchestrate", {
          method: "POST",
          body: { objective: objective.trim(), auto_execute: true },
        });
        createdTaskId = res.task?.task_id || "";
      }
      setObjective("");
      setTaskTitle("");
      setAmountUsd("0");
      if (createdTaskId) setSelectedTaskId(createdTaskId);
      pushToast("ARGON workflow planned & dispatched.", "success");
      await load();
    } catch (err: any) {
      pushToast(err.message, "error");
    } finally {
      setDispatching(false);
    }
  }

  async function runTaskAction(taskId: string, action: "execute" | "enqueue" | "pause" | "resume" | "retry" | "cancel") {
    try {
      await apiFetch(`/api/v1/tasks/${taskId}/${action}`, { method: "POST" });
      pushToast(`Task ${action} completed.`, "success");
      await load();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function processJobs() {
    try {
      await apiFetch("/api/v1/argon/jobs/process", { method: "POST", body: { max_jobs: 10 } });
      pushToast("Worker batch processed.", "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function createSchedule(e: React.FormEvent) {
    e.preventDefault();
    if (!schedName.trim() || !schedPrompt.trim()) return;
    try {
      await apiFetch("/api/v1/argon/schedules", {
        method: "POST",
        body: {
          name: schedName.trim(),
          interval_seconds: Math.max(60, Number(schedInterval) || 300),
          job_type: "agent_task",
          payload: { objective: schedPrompt.trim() },
        },
      });
      setSchedName("");
      setSchedPrompt("");
      pushToast("Recurring ARGON schedule created.", "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function previewRoute(e: React.FormEvent) {
    e.preventDefault();
    if (!routePrompt.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/neon/route", {
        method: "POST",
        body: { objective: routePrompt.trim() },
      });
      setRoutePreview(res);
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  function requestApprovalDecision(approvalId: string, decision: "APPROVED" | "REJECTED") {
    setConfirmState({
      title: decision === "APPROVED" ? "Approve Governed Action" : "Reject Governed Action",
      message: `Confirm recording ${decision} on ApprovalGate item ${approvalId}. This decision is written to the tamper-evident audit log.`,
      confirmLabel: decision === "APPROVED" ? "Confirm Approval" : "Confirm Rejection",
      destructive: decision === "REJECTED",
      onConfirm: async () => {
        await apiFetch(`/api/v1/approvals/${approvalId}/decide`, {
          method: "POST",
          body: { decision, note: `Decided via ULTRON Approval Centre (${decision})` },
        });
        pushToast(`Approval ${decision}.`, "success");
        await load();
      },
    });
  }

  async function sendAgentMsg(e: React.FormEvent) {
    e.preventDefault();
    if (!msgSubject.trim()) return;
    try {
      await apiFetch("/api/v1/agents/messages", {
        method: "POST",
        body: {
          from_agent_id: fromAgent,
          to_agent_id: toAgent,
          subject: msgSubject.trim(),
          payload: { source: "argon_comms" },
        },
      });
      setMsgSubject("");
      pushToast(`Dispatched handoff ${fromAgent} → ${toAgent}.`, "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  const pendingApprovals = approvals.filter((a) => a.status === "PENDING");
  const runningJobs = jobs.filter((j) => ["QUEUED", "RUNNING", "RETRYING"].includes(j.status));
  const dlqJobs = jobs.filter((j) => ["DEAD_LETTER", "FAILED"].includes(j.status));
  const selectedTask = tasks.find((t) => t.task_id === selectedTaskId) || tasks[0] || null;

  const filteredTasks = tasks.filter((t) => {
    const st = String(t.lifecycle_state || t.status || "").toUpperCase();
    if (taskFilter === "completed") return st === "COMPLETED";
    if (taskFilter === "failed") return st === "FAILED";
    if (taskFilter === "cancelled") return st === "CANCELLED";
    if (taskFilter === "pending_approval") return st === "PENDING_APPROVAL";
    if (taskFilter === "active") return !["COMPLETED", "FAILED", "CANCELLED", "PENDING_APPROVAL"].includes(st);
    return true;
  });

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`ARGON ORCHESTRATION // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <div className="row">
            <button type="button" className="btn btn-secondary btn-sm" onClick={processJobs}>
              <Play size={13} /> Drain Queue
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={load}>
              <RefreshCw size={13} /> Refresh
            </button>
          </div>
        }
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {/* 17. ARGON OVERVIEW */}
      {page.id === "overview" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="grid-3">
            <MetricDisplay label="Total Tasks" value={tasks.length} sub={`${tasks.filter((t) => t.lifecycle_state === "COMPLETED").length} completed`} tone="info" />
            <MetricDisplay label="Queued / Running Jobs" value={runningJobs.length} sub={`${jobs.length} total jobs`} tone="neutral" />
            <MetricDisplay label="Pending Approvals" value={pendingApprovals.length} sub="ApprovalGate queue" tone={pendingApprovals.length > 0 ? "warn" : "success"} />
            <MetricDisplay label="Recurring Schedules" value={schedules.length} sub="Autonomous cadence" tone="info" />
            <MetricDisplay label="Dead Letter Queue" value={dlqJobs.length} sub="Needs recovery" tone={dlqJobs.length > 0 ? "danger" : "success"} />
            <MetricDisplay label="Agent Handoffs" value={messages.length} sub="Inter-agent bus" tone="neutral" />
          </div>

          {selectedTask && (
            <ArgonTaskDagInspector
              task={selectedTask}
              onAction={runTaskAction}
              onCancelRequest={(tid) =>
                setConfirmState({
                  title: "Cancel ARGON Task",
                  message: `Are you sure you want to cancel task ${tid}?`,
                  confirmLabel: "Cancel Task",
                  destructive: true,
                  onConfirm: () => runTaskAction(tid, "cancel"),
                })
              }
            />
          )}

          <div className="card">
            <div className="card-title">
              <span>Latest Orchestrated Tasks</span>
              <button type="button" className="btn btn-sm" onClick={() => onSelectSubPage("orchestrate")}>
                Open Orchestration Desk
              </button>
            </div>
            <DataTable
              rows={tasks.slice(0, 10)}
              rowKey={(t) => t.task_id}
              emptyTitle="No Orchestrated Tasks Yet"
              emptyDescription="Dispatch a multi-agent workflow from Task Orchestration."
              columns={[
                {
                  key: "title",
                  header: "Objective",
                  render: (t) => (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      style={{ textAlign: "left", justifyContent: "flex-start" }}
                      onClick={() => setSelectedTaskId(t.task_id)}
                    >
                      {t.title || t.objective?.slice(0, 58)}
                    </button>
                  ),
                },
                { key: "agent", header: "Lead Agent", mono: true, render: (t) => t.assigned_agent_id || "AGT-02" },
                { key: "risk", header: "Risk", mono: true, render: (t) => t.risk_level || "LOW" },
                { key: "state", header: "State", render: (t) => <StatusIndicator label={t.lifecycle_state || t.status} tone={lifecycleTone(t.lifecycle_state)} /> },
              ]}
            />
          </div>
        </div>
      )}

      {/* 18. TASK ORCHESTRATION */}
      {page.id === "orchestrate" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <div className="card-title">
              <span>Plan &amp; Dispatch Multi-Agent DAG</span>
              {Number(amountUsd) > 50 && (
                <StatusIndicator label="APPROVALGATE > $50 TRIGGERED" tone="warn" />
              )}
            </div>
            <form onSubmit={dispatchOrchestration} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="grid-3" style={{ gap: 8 }}>
                <input
                  className="input"
                  value={taskTitle}
                  onChange={(e) => setTaskTitle(e.target.value)}
                  placeholder="Optional Task Title"
                />
                <select
                  aria-label="Preferred lead agent"
                  className="select"
                  value={preferredAgent}
                  onChange={(e) => setPreferredAgent(e.target.value)}
                >
                  <option value="">Auto-Route via NEON</option>
                  {agents.map((a) => (
                    <option key={a.agent_id} value={a.agent_id}>
                      {a.agent_id} · {a.name}
                    </option>
                  ))}
                </select>
                <input
                  className="input"
                  type="number"
                  min="0"
                  step="1"
                  value={amountUsd}
                  onChange={(e) => setAmountUsd(e.target.value)}
                  placeholder="Spend USD (0 = no gate)"
                />
              </div>
              {Number(amountUsd) > 50 && (
                <div className="alert-box alert-warn" style={{ fontSize: 12 }}>
                  <ShieldAlert size={13} style={{ verticalAlign: "middle", marginRight: 5 }} />
                  Financial spend above $50 USD will pause in <strong>PENDING_APPROVAL</strong> until authorized in the Approval Centre.
                </div>
              )}
              <textarea
                id="argon-objective-input"
                className="textarea"
                rows={3}
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="Describe the objective for ARGON to route, decompose into steps, and execute across specialist agents..."
              />
              <button id="argon-dispatch-btn" type="submit" className="btn" style={{ alignSelf: "flex-start" }} disabled={dispatching || !objective.trim()}>
                <Send size={14} /> {dispatching ? "Planning & Dispatching..." : "Dispatch Orchestration"}
              </button>
            </form>
          </div>

          {selectedTask && (
            <ArgonTaskDagInspector
              task={selectedTask}
              onAction={runTaskAction}
              onCancelRequest={(tid) =>
                setConfirmState({
                  title: "Cancel ARGON Task",
                  message: `Are you sure you want to cancel task ${tid}?`,
                  confirmLabel: "Cancel Task",
                  destructive: true,
                  onConfirm: () => runTaskAction(tid, "cancel"),
                })
              }
            />
          )}

          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="card-title"><span>Orchestrated Tasks ({filteredTasks.length})</span></div>
            <FilterBar<ArgonTaskFilter>
              value={taskFilter}
              onChange={setTaskFilter}
              options={[
                { value: "all", label: "All", count: tasks.length },
                { value: "active", label: "Active / Queued" },
                { value: "pending_approval", label: "Pending Approval" },
                { value: "completed", label: "Completed" },
                { value: "failed", label: "Failed" },
                { value: "cancelled", label: "Cancelled" },
              ]}
            />
            <DataTable
              rows={filteredTasks}
              rowKey={(t) => t.task_id}
              emptyTitle="No Matching Tasks"
              emptyDescription="Dispatch an objective above or adjust your lifecycle filter."
              columns={[
                {
                  key: "title",
                  header: "Task (Click to Inspect DAG)",
                  render: (t) => (
                    <button
                      type="button"
                      className={`btn btn-sm ${t.task_id === selectedTask?.task_id ? "" : "btn-secondary"}`}
                      onClick={() => setSelectedTaskId(t.task_id)}
                    >
                      {t.title || t.objective?.slice(0, 54)}
                    </button>
                  ),
                },
                { key: "steps", header: "Agent Steps", mono: true, render: (t) => (t.steps || []).map((s: any) => s.agent_id).join(" → ") || t.assigned_agent_id },
                { key: "state", header: "Lifecycle", render: (t) => <StatusIndicator label={t.lifecycle_state || t.status} tone={lifecycleTone(t.lifecycle_state)} /> },
              ]}
            />
          </div>
        </div>
      )}

      {/* 19. RUNNING JOBS */}
      {page.id === "running-jobs" && (
        <div className="card">
          <div className="card-title">
            <span>Running &amp; Queued Jobs ({runningJobs.length})</span>
            <button type="button" className="btn btn-sm" onClick={processJobs}><Play size={13} /> Process Queue</button>
          </div>
          <DataTable
            rows={runningJobs}
            rowKey={(j) => j.job_id}
            emptyTitle="Queue Clear"
            emptyDescription="No jobs are currently queued or running."
            columns={[
              { key: "id", header: "Job ID", mono: true, render: (j) => j.job_id.slice(0, 12) },
              { key: "type", header: "Type", render: (j) => <strong>{j.job_type}</strong> },
              { key: "status", header: "Status", render: (j) => <StatusIndicator label={j.status} tone="info" /> },
              {
                key: "cancel",
                header: "Control",
                render: (j) => (
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={() =>
                      setConfirmState({
                        title: "Cancel Worker Job",
                        message: `Cancel queued job ${j.job_id}?`,
                        confirmLabel: "Cancel Job",
                        destructive: true,
                        onConfirm: async () => {
                          await apiFetch(`/api/v1/argon/jobs/${j.job_id}/cancel`, { method: "POST" });
                          pushToast("Job cancelled.", "success");
                          load();
                        },
                      })
                    }
                  >
                    Cancel
                  </button>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* 20. JOB HISTORY */}
      {page.id === "job-history" && (
        <div className="card">
          <div className="card-title"><span>Durable Job History ({jobs.length})</span></div>
          <DataTable
            rows={jobs}
            rowKey={(j) => j.job_id}
            columns={[
              { key: "id", header: "Job ID", mono: true, render: (j) => j.job_id.slice(0, 14) },
              { key: "type", header: "Job Type", render: (j) => j.job_type },
              { key: "attempts", header: "Attempts", mono: true, render: (j) => `${j.attempts ?? 0}/${j.max_attempts ?? 3}` },
              { key: "status", header: "Status", render: (j) => <StatusIndicator label={j.status} tone={lifecycleTone(j.status)} /> },
            ]}
          />
        </div>
      )}

      {/* 21. SCHEDULED TASKS */}
      {page.id === "schedules" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title"><span>Create Recurring Schedule</span></div>
            <form onSubmit={createSchedule} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <input className="input" value={schedName} onChange={(e) => setSchedName(e.target.value)} placeholder="Schedule name (e.g., Daily Security Sweep)" />
              <input className="input" type="number" min="60" value={schedInterval} onChange={(e) => setSchedInterval(e.target.value)} placeholder="Interval seconds (min 60)" />
              <textarea className="textarea" rows={3} value={schedPrompt} onChange={(e) => setSchedPrompt(e.target.value)} placeholder="Objective payload..." />
              <button type="submit" className="btn">Create Schedule</button>
            </form>
          </div>
          <div className="card">
            <div className="card-title"><span>Active Schedules ({schedules.length})</span></div>
            {schedules.length === 0 ? (
              <EmptyState title="No Schedules" description="Create a recurring interval schedule on the left." />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {schedules.map((s) => (
                  <div key={s.schedule_id} className="list-item">
                    <div className="row-between">
                      <strong>{s.name}</strong>
                      <span className="pill mono">Every {s.interval_seconds}s</span>
                    </div>
                    <div className="muted">{s.job_type} · Next run: {s.next_run_at || "Scheduled"}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* 22. WORKFLOW BUILDER */}
      {page.id === "workflow-builder" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span>NEON Route &amp; Reasoning Tier Preview (/api/v1/neon/route)</span></div>
          <form onSubmit={previewRoute} className="row" style={{ flexWrap: "wrap", gap: 8 }}>
            <input
              className="input"
              style={{ flex: 1, minWidth: 200 }}
              value={routePrompt}
              onChange={(e) => setRoutePrompt(e.target.value)}
              placeholder="Test how NEON routes an objective across the 60 agents..."
            />
            <button type="submit" className="btn">Preview Route</button>
          </form>
          {routePreview && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <ReadableSummary title="NEON Route Selection" data={routePreview} diagnosticsTitle="Technical Diagnostics — Route Payload" />
              <button
                type="button"
                className="btn btn-sm"
                style={{ alignSelf: "flex-start" }}
                onClick={() => {
                  setObjective(routePrompt);
                  setPreferredAgent(routePreview.selected_agent_id || "");
                  onSelectSubPage("orchestrate");
                }}
              >
                <Send size={13} /> Open in Task Orchestration
              </button>
            </div>
          )}
        </div>
      )}

      {/* 23. APPROVAL CENTRE */}
      {page.id === "approvals" && (
        <div className="card">
          <div className="card-title">
            <span>ApprovalGate Governance Queue ({pendingApprovals.length} Pending)</span>
          </div>
          {approvals.length === 0 ? (
            <EmptyState
              title="No Approval Requests"
              description="High-impact actions and financial spends above policy thresholds appear here for explicit authorization."
            />
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {approvals.map((a) => (
                <ApprovalCard
                  key={a.approval_id}
                  approval={a}
                  onApprove={(id) => requestApprovalDecision(id, "APPROVED")}
                  onReject={(id) => requestApprovalDecision(id, "REJECTED")}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* 24. DEAD LETTER QUEUE */}
      {page.id === "dlq" && (
        <div className="card">
          <div className="card-title"><span>Dead Letter Queue ({dlqJobs.length})</span></div>
          <DataTable
            rows={dlqJobs}
            rowKey={(j) => j.job_id}
            emptyTitle="Dead Letter Queue Empty"
            emptyDescription="No exhausted or failed worker jobs require manual recovery."
            columns={[
              { key: "id", header: "Job ID", mono: true, render: (j) => j.job_id.slice(0, 14) },
              { key: "type", header: "Type", render: (j) => j.job_type },
              { key: "err", header: "Last Error", render: (j) => <span className="muted">{j.last_error || "—"}</span> },
              {
                key: "act",
                header: "Recovery",
                render: (j) => (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={async () => {
                      await apiFetch(`/api/v1/argon/jobs/${j.job_id}/requeue`, { method: "POST" });
                      pushToast("Job requeued from DLQ.", "success");
                      load();
                    }}
                  >
                    <RotateCcw size={12} /> Requeue
                  </button>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* 25. AGENT COMMUNICATION */}
      {page.id === "comms" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title"><span>Dispatch Inter-Agent Handoff</span></div>
            <form onSubmit={sendAgentMsg} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="grid-2" style={{ gap: 8 }}>
                <select aria-label="From agent" className="select" value={fromAgent} onChange={(e) => setFromAgent(e.target.value)}>
                  {agents.map((a) => (
                    <option key={a.agent_id} value={a.agent_id}>{a.agent_id} · {a.name}</option>
                  ))}
                </select>
                <select aria-label="To agent" className="select" value={toAgent} onChange={(e) => setToAgent(e.target.value)}>
                  {agents.map((a) => (
                    <option key={a.agent_id} value={a.agent_id}>{a.agent_id} · {a.name}</option>
                  ))}
                </select>
              </div>
              <input className="input" value={msgSubject} onChange={(e) => setMsgSubject(e.target.value)} placeholder="Handoff subject / task directive..." />
              <button type="submit" className="btn">Send Message</button>
            </form>
          </div>
          <div className="card">
            <div className="card-title"><span>Inter-Agent Bus ({messages.length})</span></div>
            {messages.length === 0 ? (
              <EmptyState title="No Bus Messages" description="Structured agent-to-agent handoffs appear here." />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {messages.slice(0, 15).map((m, idx) => (
                  <div key={m.message_id || idx} className="list-item">
                    <div className="row-between">
                      <span className="mono-tag">{m.from_agent_id} → {m.to_agent_id}</span>
                      <span className="pill">{m.status || "DELIVERED"}</span>
                    </div>
                    <div>{m.subject}</div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <ConfirmationDialog
        open={Boolean(confirmState)}
        title={confirmState?.title || "Confirm"}
        message={confirmState?.message || ""}
        confirmLabel={confirmState?.confirmLabel || "Confirm"}
        destructive={confirmState?.destructive ?? true}
        onCancel={() => setConfirmState(null)}
        onConfirm={async () => {
          const fn = confirmState?.onConfirm;
          setConfirmState(null);
          if (fn) {
            try {
              await fn();
            } catch (e: any) {
              pushToast(e.message, "error");
            }
          }
        }}
      />
    </ResponsiveWorkspace>
  );
}
