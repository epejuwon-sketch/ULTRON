import React, { useEffect, useState } from "react";
import { Play, RefreshCw, RotateCcw, Send } from "lucide-react";
import { apiFetch } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import {
  ApprovalCard,
  ConfirmationDialog,
  DataTable,
  EmptyState,
  ErrorState,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";
import { ReadableSummary } from "../components/ui/HumanPresentation";

export default function ArgonModulePage({ subPage, onSelectSubPage }: ModulePageProps) {
  const mod = getModule("argon");
  const page = getSubPage("argon", subPage);
  const { pushToast } = useToast();

  const [tasks, setTasks] = useState<any[]>([]);
  const [jobs, setJobs] = useState<any[]>([]);
  const [schedules, setSchedules] = useState<any[]>([]);
  const [approvals, setApprovals] = useState<any[]>([]);
  const [messages, setMessages] = useState<any[]>([]);
  const [error, setError] = useState("");

  // Forms
  const [objective, setObjective] = useState("");
  const [taskTitle, setTaskTitle] = useState("");
  const [amountUsd, setAmountUsd] = useState("0");
  const [schedName, setSchedName] = useState("");
  const [schedInterval, setSchedInterval] = useState("300");
  const [schedPrompt, setSchedPrompt] = useState("");
  const [routePrompt, setRoutePrompt] = useState("");
  const [routePreview, setRoutePreview] = useState<any>(null);
  const [fromAgent, setFromAgent] = useState("AGT-01");
  const [toAgent, setToAgent] = useState("AGT-02");
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
      const [tRes, jRes, sRes, aRes, mRes] = await Promise.all([
        apiFetch<any>("/api/v1/tasks").catch(() => ({ tasks: [] })),
        apiFetch<any>("/api/v1/argon/jobs").catch(() => ({ jobs: [] })),
        apiFetch<any>("/api/v1/argon/schedules").catch(() => ({ schedules: [] })),
        apiFetch<any>("/api/v1/approvals").catch(() => ({ approvals: [] })),
        apiFetch<any>("/api/v1/agents/messages").catch(() => ({ messages: [] })),
      ]);
      setTasks(tRes.tasks || []);
      setJobs(jRes.jobs || []);
      setSchedules(sRes.schedules || []);
      setApprovals(aRes.approvals || []);
      setMessages(mRes.messages || []);
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
    try {
      if (Number(amountUsd) > 0 || taskTitle.trim()) {
        await apiFetch("/api/v1/tasks", {
          method: "POST",
          body: {
            title: taskTitle.trim() || objective.trim().slice(0, 48),
            objective: objective.trim(),
            financial_amount_usd: Number(amountUsd) || 0,
          },
        });
      } else {
        await apiFetch("/api/v1/orchestrate", {
          method: "POST",
          body: { objective: objective.trim(), auto_execute: true },
        });
      }
      setObjective("");
      setTaskTitle("");
      setAmountUsd("0");
      pushToast("ARGON workflow planned & dispatched.", "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
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
        body: { prompt: routePrompt.trim() },
      });
      setRoutePreview(res);
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  // Verified backend contract: POST /api/v1/approvals/{approval_id}/decide
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
            <MetricDisplay label="Active Tasks" value={tasks.length} sub="DAG task ledger" tone="info" />
            <MetricDisplay label="Queued / Running Jobs" value={runningJobs.length} sub={`${jobs.length} total jobs`} tone="neutral" />
            <MetricDisplay label="Pending Approvals" value={pendingApprovals.length} sub="ApprovalGate queue" tone={pendingApprovals.length > 0 ? "warn" : "success"} />
            <MetricDisplay label="Recurring Schedules" value={schedules.length} sub="Autonomous cadence" tone="info" />
            <MetricDisplay label="Dead Letter Queue" value={dlqJobs.length} sub="Needs recovery" tone={dlqJobs.length > 0 ? "danger" : "success"} />
            <MetricDisplay label="Agent Handoffs" value={messages.length} sub="Inter-agent bus" tone="neutral" />
          </div>
          <div className="card">
            <div className="card-title"><span>Latest Orchestrated Tasks</span></div>
            <DataTable
              rows={tasks.slice(0, 10)}
              rowKey={(t) => t.task_id}
              emptyTitle="No Orchestrated Tasks Yet"
              emptyDescription="Dispatch a multi-agent workflow from Task Orchestration."
              columns={[
                { key: "title", header: "Objective", render: (t) => <strong>{t.title || t.objective?.slice(0, 64)}</strong> },
                { key: "agent", header: "Lead Agent", mono: true, render: (t) => t.assigned_agent_id || "AGT-02" },
                { key: "risk", header: "Risk", mono: true, render: (t) => t.risk_level || "LOW" },
                { key: "state", header: "State", render: (t) => <StatusIndicator label={t.lifecycle_state || t.status} tone={t.lifecycle_state === "COMPLETED" ? "success" : "info"} /> },
              ]}
            />
          </div>
        </div>
      )}

      {/* 18. TASK ORCHESTRATION */}
      {page.id === "orchestrate" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="card">
            <div className="card-title"><span>Plan & Dispatch Multi-Agent DAG (ApprovalGate &gt; $50)</span></div>
            <form onSubmit={dispatchOrchestration} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="row">
                <input className="input" style={{ flex: 2 }} value={taskTitle} onChange={(e) => setTaskTitle(e.target.value)} placeholder="Optional Task Title" />
                <input className="input" style={{ width: 150 }} type="number" step="1" value={amountUsd} onChange={(e) => setAmountUsd(e.target.value)} placeholder="Cost USD" />
              </div>
              <textarea
                id="argon-objective-input"
                className="textarea"
                rows={3}
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="Describe the objective for ARGON to route, plan, and execute across specialist agents..."
              />
              <button id="argon-dispatch-btn" type="submit" className="btn" style={{ alignSelf: "flex-start" }} disabled={!objective.trim()}>
                <Send size={14} /> Dispatch Orchestration
              </button>
            </form>
          </div>
          <div className="card">
            <div className="card-title"><span>All Tasks ({tasks.length})</span></div>
            <DataTable
              rows={tasks}
              rowKey={(t) => t.task_id}
              columns={[
                { key: "title", header: "Task", render: (t) => <strong>{t.title || t.objective?.slice(0, 60)}</strong> },
                { key: "steps", header: "Agent Steps", mono: true, render: (t) => (t.steps || []).map((s: any) => s.agent_id).join(" → ") || t.assigned_agent_id },
                { key: "state", header: "Lifecycle", render: (t) => <StatusIndicator label={t.lifecycle_state || t.status} tone={t.lifecycle_state === "COMPLETED" ? "success" : "info"} /> },
              ]}
            />
          </div>
        </div>
      )}

      {/* 19. RUNNING JOBS */}
      {page.id === "running-jobs" && (
        <div className="card">
          <div className="card-title">
            <span>Running & Queued Jobs ({runningJobs.length})</span>
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
              { key: "status", header: "Status", render: (j) => <StatusIndicator label={j.status} tone={j.status === "COMPLETED" ? "success" : j.status === "FAILED" ? "danger" : "neutral"} /> },
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
          <div className="card-title"><span>NEON Route & Reasoning Tier Preview (/api/v1/neon/route)</span></div>
          <form onSubmit={previewRoute} className="row">
            <input
              className="input"
              style={{ flex: 1 }}
              value={routePrompt}
              onChange={(e) => setRoutePrompt(e.target.value)}
              placeholder="Test how NEON routes an objective across the 60 agents..."
            />
            <button type="submit" className="btn">Preview Route</button>
          </form>
          {routePreview && (
            <ReadableSummary title="NEON Route Selection" data={routePreview} diagnosticsTitle="Technical Diagnostics — Route Payload" />
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
              <div className="row">
                <input className="input" style={{ flex: 1 }} value={fromAgent} onChange={(e) => setFromAgent(e.target.value.toUpperCase())} placeholder="From (AGT-01)" />
                <input className="input" style={{ flex: 1 }} value={toAgent} onChange={(e) => setToAgent(e.target.value.toUpperCase())} placeholder="To (AGT-02)" />
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
