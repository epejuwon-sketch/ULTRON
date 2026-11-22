import React, { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";

export function ArgonOrchestrationView() {
  const [objective, setObjective] = useState("");
  const [autoExecute, setAutoExecute] = useState(true);
  const [orchestrating, setOrchestrating] = useState(false);
  const [lastRun, setLastRun] = useState<any>(null);

  const [jobs, setJobs] = useState<any[]>([]);
  const [schedules, setSchedules] = useState<any[]>([]);
  const [approvals, setApprovals] = useState<any[]>([]);
  const [processingQueue, setProcessingQueue] = useState(false);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");

  async function loadAll() {
    setLoading(true);
    setError("");
    try {
      const [jRes, sRes, aRes] = await Promise.all([
        apiFetch<any>("/api/v1/argon/jobs"),
        apiFetch<any>("/api/v1/argon/schedules"),
        apiFetch<any>("/api/v1/approvals"),
      ]);
      setJobs(jRes.jobs || []);
      setSchedules(sRes.schedules || []);
      setApprovals(aRes.approvals || []);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAll();
  }, []);

  async function runOrchestration(e: React.FormEvent) {
    e.preventDefault();
    if (!objective.trim()) return;
    setOrchestrating(true);
    setError("");
    setNotice("");
    try {
      const res = await apiFetch<any>("/api/v1/orchestrate", {
        method: "POST",
        body: { objective: objective.trim(), auto_execute: autoExecute },
      });
      setLastRun(res);
      setObjective("");
      setNotice(`ARGON orchestrated task ${res.task?.task_id || ""} (${res.task?.lifecycle_state || "CREATED"}).`);
      await loadAll();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setOrchestrating(false);
    }
  }

  async function processQueue() {
    setProcessingQueue(true);
    setError("");
    setNotice("");
    try {
      const res = await apiFetch<any>("/api/v1/argon/jobs/process", { method: "POST" });
      setNotice(`Queue cycle complete: processed ${res.processed ?? 0} jobs.`);
      await loadAll();
    } catch (e: any) {
      setError(e.message);
    } finally {
      setProcessingQueue(false);
    }
  }

  async function decideApproval(approvalId: string, decision: "APPROVED" | "REJECTED") {
    setError("");
    try {
      await apiFetch(`/api/v1/approvals/${approvalId}/decision`, {
        method: "POST",
        body: { decision, note: `Decided via ARGON Orchestration Console (${decision})` },
      });
      setNotice(`Approval ${approvalId} marked ${decision}.`);
      await loadAll();
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function requeueJob(jobId: string) {
    setError("");
    try {
      await apiFetch(`/api/v1/argon/jobs/${jobId}/requeue`, { method: "POST" });
      setNotice(`Requeued dead-letter job ${jobId}.`);
      await loadAll();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const pendingApprovals = approvals.filter((a) => a.status === "PENDING");

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card">
        <div className="card-title">
          <span>ARGON Multi-Agent Orchestrator</span>
          <div className="row">
            <button
              id="argon-process-queue"
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={processQueue}
              disabled={processingQueue}
            >
              {processingQueue ? "Draining..." : "Run Queue Cycle"}
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={loadAll} disabled={loading}>
              Refresh
            </button>
          </div>
        </div>

        {notice && <div className="alert-box" style={{ marginBottom: 12 }}>{notice}</div>}
        {error && <div className="alert-box alert-error" style={{ marginBottom: 12 }}>{error}</div>}

        <form onSubmit={runOrchestration} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <textarea
            id="argon-objective-input"
            className="textarea"
            rows={3}
            placeholder="Describe a multi-step objective (e.g., Research market trends and draft a launch campaign plan)..."
            value={objective}
            onChange={(e) => setObjective(e.target.value)}
          />
          <div className="row-between">
            <label className="row muted" style={{ cursor: "pointer" }}>
              <input
                type="checkbox"
                checked={autoExecute}
                onChange={(e) => setAutoExecute(e.target.checked)}
              />
              Auto-execute approved DAG steps immediately
            </label>
            <button id="argon-dispatch-btn" className="btn" type="submit" disabled={orchestrating || !objective.trim()}>
              {orchestrating ? "Orchestrating..." : "Dispatch Objective"}
            </button>
          </div>
        </form>

        {lastRun && (
          <div className="dispatch-output" style={{ marginTop: 14 }}>
            <div className="row-between">
              <span className="mono-tag">
                {lastRun.neon_routing?.selected_agent_id} · TIER {lastRun.neon_routing?.reasoning_tier} · {lastRun.neon_routing?.primary_model}
              </span>
              <span className="pill pill-cyan">{lastRun.task?.lifecycle_state}</span>
            </div>
            <div className="row" style={{ marginTop: 8 }}>
              {(lastRun.task?.steps || []).map((s: any) => (
                <span key={s.step_id || s.step_index} className={`pill ${s.status === "COMPLETED" ? "pill-green" : "pill-warn"}`}>
                  #{s.step_index} {s.agent_id} · {s.status}
                </span>
              ))}
            </div>
            {lastRun.task?.result_summary && (
              <div className="dispatch-text">{lastRun.task.result_summary}</div>
            )}
          </div>
        )}
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title">
            <span>Background Job Queue &amp; DLQ ({jobs.length})</span>
          </div>
          {loading ? (
            <div className="muted">Loading ARGON queue...</div>
          ) : jobs.length === 0 ? (
            <div className="muted">No queued or historical background jobs recorded for this tenant.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 360, overflowY: "auto" }}>
              {jobs.map((j) => (
                <div key={j.job_id} className="list-item">
                  <div className="row-between">
                    <strong className="mono">{j.job_type}</strong>
                    <span className={`pill ${j.status === "COMPLETED" ? "pill-green" : j.status === "DEAD_LETTER" ? "pill-danger" : "pill-cyan"}`}>
                      {j.status}
                    </span>
                  </div>
                  <div className="muted mono">
                    {j.job_id} · attempts {j.attempts}/{j.max_attempts}
                  </div>
                  {j.status === "DEAD_LETTER" && (
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => requeueJob(j.job_id)}>
                      Requeue DLQ Job
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title">
            <span>ApprovalGate Queue ({pendingApprovals.length} Pending) · Schedules ({schedules.length})</span>
          </div>
          {pendingApprovals.length === 0 ? (
            <div className="muted" style={{ marginBottom: 12 }}>No pending high-impact actions awaiting approval.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
              {pendingApprovals.map((a) => (
                <div key={a.approval_id} className="list-item">
                  <div className="row-between">
                    <strong>{a.action_type}</strong>
                    <span className="pill pill-warn">${a.estimated_cost_usd ?? 0}</span>
                  </div>
                  <div className="muted">{a.reason}</div>
                  <div className="row">
                    <button type="button" className="btn btn-sm" onClick={() => decideApproval(a.approval_id, "APPROVED")}>
                      Approve
                    </button>
                    <button type="button" className="btn btn-danger btn-sm" onClick={() => decideApproval(a.approval_id, "REJECTED")}>
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {schedules.length > 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div className="nav-section" style={{ paddingLeft: 0 }}>Active Schedules</div>
              {schedules.map((s) => (
                <div key={s.schedule_id} className="list-item">
                  <div className="row-between">
                    <strong>{s.name}</strong>
                    <span className="pill">every {s.interval_seconds}s</span>
                  </div>
                  <div className="muted mono">{s.job_type}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
