import React, { useEffect, useRef, useState } from "react";
import { Play, RefreshCw, ShieldCheck, Square } from "lucide-react";
import { apiFetch } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import { AgentIcon } from "../catalog/agentIcons";
import { ModulePageProps } from "./CommandModulePage";
import {
  ActivityFeed,
  DataTable,
  EmptyState,
  ErrorState,
  FilterBar,
  LoadingState,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  SearchBar,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";

type AgentFilter = "all" | "core" | "specialist" | "active" | "idle" | "attention";

export function AgentCard({
  agent,
  selected,
  onSelect,
}: {
  agent: any;
  selected?: boolean;
  onSelect: (agentId: string) => void;
}) {
  const statusStr = String(agent.capability_state || agent.status || "READY").toUpperCase();
  const tone =
    statusStr.includes("ACTIVE") || statusStr === "READY" || statusStr === "AVAILABLE"
      ? "success"
      : statusStr.includes("ATTENTION") || statusStr.includes("DEGRADED") || statusStr.includes("DISABLED")
      ? "warn"
      : "neutral";

  return (
    <button
      id={`agent-card-${agent.agent_id}`}
      type="button"
      className={`agent-card ${selected ? "list-item-active" : ""}`}
      onClick={() => onSelect(agent.agent_id)}
    >
      <div className="row-between" style={{ width: "100%", flexWrap: "nowrap", alignItems: "flex-start" }}>
        <div className="row" style={{ gap: 10, flexWrap: "nowrap", minWidth: 0 }}>
          <span className="agent-icon-badge">
            <AgentIcon agentId={agent.agent_id} size={16} />
          </span>
          <div style={{ textAlign: "left", minWidth: 0 }}>
            <div className="mono" style={{ fontSize: 11, color: "var(--accent)" }}>
              {agent.agent_id} · {agent.tier === "CORE_25" ? "CORE" : "SPECIALIST"}
            </div>
            <strong style={{ fontSize: 13.5, display: "block" }}>{agent.name}</strong>
          </div>
        </div>
        <span className="pill mono" style={{ flexShrink: 0 }}>T{agent.default_reasoning_tier ?? 2}</span>
      </div>
      <div className="muted" style={{ textAlign: "left" }}>
        {agent.domain} · {agent.permission_scope}
      </div>
      <div className="row-between" style={{ width: "100%", marginTop: "auto" }}>
        <StatusIndicator label={statusStr} tone={tone} />
        <span className="muted mono" style={{ fontSize: 11 }}>
          {(agent.tools || []).length} tools
        </span>
      </div>
    </button>
  );
}

export function AgentProfile({
  manifest,
  onInvokeTab,
}: {
  manifest: any;
  onInvokeTab?: () => void;
}) {
  if (!manifest) {
    return (
      <EmptyState
        title="Select an Agent"
        description="Choose any specialist from AGT-01 to AGT-60 in the Agent Directory to inspect its independent contract."
      />
    );
  }
  return (
    <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="row-between">
        <div className="row" style={{ gap: 12 }}>
          <span className="agent-icon-badge" style={{ width: 42, height: 42 }}>
            <AgentIcon agentId={manifest.agent_id} size={20} />
          </span>
          <div>
            <div className="mono" style={{ fontSize: 12, color: "var(--accent)" }}>
              {manifest.agent_id} · {manifest.tier}
            </div>
            <h2 style={{ fontSize: 19 }}>{manifest.name}</h2>
          </div>
        </div>
        <div className="row">
          <StatusIndicator label={manifest.execution_backing || "NEON"} tone="success" />
          {onInvokeTab && (
            <button type="button" className="btn btn-sm" onClick={onInvokeTab}>
              <Play size={13} /> Open Workspace
            </button>
          )}
        </div>
      </div>

      <p className="muted" style={{ margin: 0 }}>{manifest.role_description}</p>

      <div className="grid-3">
        <MetricDisplay label="Domain" value={manifest.domain} />
        <MetricDisplay label="Permission Scope" value={manifest.permission_scope} />
        <MetricDisplay label="Default Tier" value={`T${manifest.default_reasoning_tier ?? 2}`} />
      </div>

      <div>
        <div className="telemetry-label" style={{ marginBottom: 6 }}>AUTHORIZED TOOLS</div>
        <div className="row">
          {(manifest.tools || []).map((t: string) => (
            <span key={t} className="pill mono">{t}</span>
          ))}
        </div>
      </div>

      {manifest.contract?.execution_workflow && (
        <div className="list-item">
          <div className="telemetry-label">INDEPENDENT EXECUTION WORKFLOW</div>
          <div className="mono muted" style={{ fontSize: 12 }}>
            {manifest.contract.execution_workflow.join(" → ")}
          </div>
        </div>
      )}
    </div>
  );
}

export default function AgentsModulePage({ subPage, onSelectSubPage }: ModulePageProps) {
  const mod = getModule("agents");
  const page = getSubPage("agents", subPage);
  const { pushToast } = useToast();

  const [agents, setAgents] = useState<any[]>([]);
  const [selectedId, setSelectedId] = useState("AGT-01");
  const [manifest, setManifest] = useState<any>(null);
  const [agentMessages, setAgentMessages] = useState<any[]>([]);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<AgentFilter>("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Workspace invocation
  const [prompt, setPrompt] = useState("");
  const [invoking, setInvoking] = useState(false);
  const [invokeResult, setInvokeResult] = useState<any>(null);

  // Configuration / Extension registration
  const [capState, setCapState] = useState("AVAILABLE");
  const [extName, setExtName] = useState("");
  const [extDomain, setExtDomain] = useState("");
  const [extRole, setExtRole] = useState("");
  const [turboStats, setTurboStats] = useState<any>(null);

  // Live non-destructive 60-Agent & 5-Tier Gemini verification runner
  type AuditStatus = "LIVE VERIFIED" | "LIVE VERIFIED WITH FALLBACK" | "FAILED" | "NOT TESTED";
  interface AuditRow {
    agent_id: string;
    name: string;
    tier: number;
    status: AuditStatus;
    provider: string;
    primary_model: string;
    actual_model: string;
    latency_ms: number | null;
    fallback_used: boolean;
    note?: string;
  }
  const [auditRows, setAuditRows] = useState<Record<string, AuditRow>>({});
  const [auditRunning, setAuditRunning] = useState(false);
  const [auditProgress, setAuditProgress] = useState({ done: 0, total: 0 });
  const abortAuditRef = useRef(false);

  async function runLiveAudit(targetList: any[]) {
    if (auditRunning || targetList.length === 0) return;
    abortAuditRef.current = false;
    setAuditRunning(true);
    setAuditProgress({ done: 0, total: targetList.length });
    for (let i = 0; i < targetList.length; i++) {
      if (abortAuditRef.current) break;
      const ag = targetList[i];
      try {
        const res = await apiFetch<any>(`/api/v1/agents/${ag.agent_id}/invoke`, {
          method: "POST",
          body: {
            prompt: `Non-destructive readiness check for ${ag.agent_id} (${ag.domain}). Reply in one concise sentence confirming your specialist domain.`,
            reasoning_tier: ag.default_reasoning_tier,
          },
        });
        const isLive = res.execution_mode === "gemini_live" && res.provider === "gemini";
        const fb = Boolean(res.fallback_used || (res.primary_model && res.model !== res.primary_model));
        const status: AuditStatus = !isLive
          ? "FAILED"
          : fb
          ? "LIVE VERIFIED WITH FALLBACK"
          : "LIVE VERIFIED";
        setAuditRows((prev) => ({
          ...prev,
          [ag.agent_id]: {
            agent_id: ag.agent_id,
            name: ag.name,
            tier: res.reasoning_tier ?? ag.default_reasoning_tier,
            status,
            provider: res.provider || "unknown",
            primary_model: res.primary_model || res.model || "—",
            actual_model: res.model || "—",
            latency_ms: typeof res.latency_ms === "number" ? res.latency_ms : null,
            fallback_used: fb,
            note: isLive ? undefined : String(res.output || "").slice(0, 140),
          },
        }));
      } catch (e: any) {
        setAuditRows((prev) => ({
          ...prev,
          [ag.agent_id]: {
            agent_id: ag.agent_id,
            name: ag.name,
            tier: ag.default_reasoning_tier,
            status: "FAILED",
            provider: "error",
            primary_model: "—",
            actual_model: "—",
            latency_ms: null,
            fallback_used: false,
            note: e.message,
          },
        }));
      }
      setAuditProgress({ done: i + 1, total: targetList.length });
      if (i + 1 < targetList.length && !abortAuditRef.current) {
        await new Promise((r) => window.setTimeout(r, 900));
      }
    }
    setAuditRunning(false);
    pushToast("Live agent verification batch finished.", "success");
  }

  async function loadAgents() {
    setError("");
    try {
      const [aRes, tRes] = await Promise.all([
        apiFetch<any>("/api/v1/agents"),
        apiFetch<any>("/api/v1/turbo/stats").catch(() => null),
      ]);
      setAgents(aRes.agents || []);
      setTurboStats(tRes);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadManifest(aid: string) {
    if (!aid) return;
    try {
      const [m, msgs] = await Promise.all([
        apiFetch<any>(`/api/v1/agents/${aid}/manifest`),
        apiFetch<any>(`/api/v1/agents/messages?agent_id=${aid}`).catch(() => ({ messages: [] })),
      ]);
      setManifest(m);
      setAgentMessages(msgs.messages || []);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    loadAgents();
  }, []);

  useEffect(() => {
    if (selectedId) loadManifest(selectedId);
  }, [selectedId, subPage]);

  async function handleInvoke(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setInvoking(true);
    setError("");
    try {
      const res = await apiFetch<any>(`/api/v1/agents/${selectedId}/invoke`, {
        method: "POST",
        body: { prompt: prompt.trim() },
      });
      setInvokeResult(res);
      pushToast(`${selectedId} execution completed.`, "success");
    } catch (err: any) {
      setError(err.message);
      pushToast(err.message, "error");
    } finally {
      setInvoking(false);
    }
  }

  async function updateAgentState() {
    try {
      await apiFetch(`/api/v1/agents/${selectedId}/state`, {
        method: "PATCH",
        body: { capability_state: capState },
      });
      pushToast(`Updated ${selectedId} capability state to ${capState}.`, "success");
      loadAgents();
      loadManifest(selectedId);
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function registerExtension(e: React.FormEvent) {
    e.preventDefault();
    if (!extName.trim() || !extDomain.trim() || !extRole.trim()) return;
    try {
      await apiFetch("/api/v1/agents/register", {
        method: "POST",
        body: {
          name: extName.trim(),
          domain: extDomain.trim(),
          role_description: extRole.trim(),
        },
      });
      setExtName("");
      setExtDomain("");
      setExtRole("");
      pushToast("Extension agent proposal submitted.", "success");
      loadAgents();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  const filtered = agents.filter((a) => {
    if (filter === "core" && a.tier !== "CORE_25") return false;
    if (filter === "specialist" && a.tier !== "EXTENSIBLE_35") return false;
    const st = String(a.capability_state || a.status || "AVAILABLE").toUpperCase();
    if (filter === "active" && !(st === "AVAILABLE" || st === "ACTIVE" || st === "READY")) return false;
    if (filter === "idle" && (a.tasks_completed || 0) > 0) return false;
    if (filter === "attention" && !(st.includes("DEGRADED") || st.includes("DISABLED") || (a.tasks_failed || 0) > 0)) return false;
    const q = search.trim().toLowerCase();
    if (!q) return true;
    return (
      a.agent_id.toLowerCase().includes(q) ||
      a.name.toLowerCase().includes(q) ||
      a.domain.toLowerCase().includes(q)
    );
  });

  const coreCount = agents.filter((a) => a.tier === "CORE_25").length;
  const specCount = agents.filter((a) => a.tier === "EXTENSIBLE_35").length;

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`THE 60 AGENTS // PAGE ${page.number} · SELECTED ${selectedId}`}
        title={page.label}
        description={page.description}
        actions={
          <div className="row">
            <select
              aria-label="Active specialist agent"
              className="select"
              style={{ width: 210 }}
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              {agents.map((a) => (
                <option key={a.agent_id} value={a.agent_id}>
                  {a.agent_id} · {a.name}
                </option>
              ))}
            </select>
            <button type="button" className="btn btn-secondary btn-sm" onClick={loadAgents}>
              <RefreshCw size={13} /> Refresh
            </button>
          </div>
        }
      />

      {error && <ErrorState message={error} onRetry={loadAgents} />}

      {/* 26. COMPLETE AGENT DIRECTORY */}
      {page.id === "directory" && (
        loading ? <LoadingState /> : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            <div className="row-between">
              <div style={{ flex: 1, minWidth: 220 }}>
                <SearchBar
                  id="agents-directory-search"
                  value={search}
                  onChange={setSearch}
                  placeholder="Search all 60 specialist agents by ID, name, or domain..."
                />
              </div>
              <FilterBar<AgentFilter>
                value={filter}
                onChange={setFilter}
                options={[
                  { value: "all", label: "All 60", count: agents.length },
                  { value: "core", label: "Core agents", count: coreCount },
                  { value: "specialist", label: "Specialist agents", count: specCount },
                  { value: "active", label: "Active" },
                  { value: "idle", label: "Idle" },
                  { value: "attention", label: "Needs attention" },
                ]}
              />
            </div>

            {filtered.length === 0 ? (
              <EmptyState title="No Matching Agents" description="Adjust your search term or status filter." />
            ) : (
              <div className="agents-grid">
                {filtered.map((a) => (
                  <AgentCard
                    key={a.agent_id}
                    agent={a}
                    selected={a.agent_id === selectedId}
                    onSelect={(id) => {
                      setSelectedId(id);
                      onSelectSubPage("profile");
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        )
      )}

      {/* 27. INDIVIDUAL AGENT PROFILE */}
      {page.id === "profile" && (
        <AgentProfile manifest={manifest} onInvokeTab={() => onSelectSubPage("workspace")} />
      )}

      {/* 28. AGENT WORKSPACE */}
      {page.id === "workspace" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title">
            <div className="row">
              <AgentIcon agentId={selectedId} size={18} />
              <span>Direct Workspace · {selectedId} ({manifest?.name || "Loading..."})</span>
            </div>
            <StatusIndicator label={manifest?.permission_scope || "TIER_2"} tone="info" />
          </div>
          <div className="muted">{manifest?.role_description}</div>
          <form onSubmit={handleInvoke} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <textarea
              id="agent-workspace-prompt"
              className="textarea"
              rows={4}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder={`Issue a specialist directive to ${selectedId}...`}
            />
            <button id="agent-workspace-submit" type="submit" className="btn" style={{ alignSelf: "flex-start" }} disabled={invoking || !prompt.trim()}>
              <Play size={14} /> {invoking ? `Invoking ${selectedId}...` : `Invoke ${selectedId}`}
            </button>
          </form>
          {invokeResult && (
            <div className="dispatch-output">
              <div className="row-between">
                <span className="mono-tag">{invokeResult.agent_id} · {invokeResult.execution_mode}</span>
                <span className="muted mono">{invokeResult.model}</span>
              </div>
              <div className="dispatch-text">{invokeResult.output}</div>
            </div>
          )}
        </div>
      )}

      {/* 29. AGENT PERFORMANCE */}
      {page.id === "performance" && (
        <div className="card">
          <div className="card-title"><span>Live 60-Agent Performance Telemetry</span></div>
          <DataTable
            rows={agents}
            rowKey={(a) => a.agent_id}
            columns={[
              {
                key: "agent",
                header: "Agent",
                render: (a) => (
                  <div className="row">
                    <AgentIcon agentId={a.agent_id} size={14} />
                    <span className="mono">{a.agent_id}</span>
                    <strong>{a.name}</strong>
                  </div>
                ),
              },
              { key: "tier", header: "Tier", mono: true, render: (a) => `T${a.default_reasoning_tier ?? 2}` },
              { key: "completed", header: "Completed", mono: true, render: (a) => a.tasks_completed ?? 0 },
              { key: "failed", header: "Failed", mono: true, render: (a) => a.tasks_failed ?? 0 },
              { key: "latency", header: "Avg Latency", mono: true, render: (a) => `${a.avg_latency_ms ?? 0} ms` },
            ]}
          />
        </div>
      )}

      {/* 30. AGENT PERMISSIONS */}
      {page.id === "permissions" && (
        <div className="card">
          <div className="card-title">
            <span><ShieldCheck size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Permission Scopes & Governance Matrix</span>
          </div>
          <DataTable
            rows={agents}
            rowKey={(a) => a.agent_id}
            columns={[
              { key: "id", header: "ID", mono: true, render: (a) => a.agent_id },
              { key: "name", header: "Agent", render: (a) => a.name },
              { key: "scope", header: "Permission Scope", mono: true, render: (a) => <span className="pill pill-cyan">{a.permission_scope}</span> },
              { key: "tools", header: "Authorized Tools", mono: true, render: (a) => (a.tools || []).join(", ") || "NEON core" },
            ]}
          />
        </div>
      )}

      {/* 31. AGENT ACTIVITY */}
      {page.id === "activity" && (
        <div className="card">
          <div className="card-title"><span>Activity & Bus Messages for {selectedId}</span></div>
          <ActivityFeed
            emptyLabel={`No inter-agent handoffs recorded for ${selectedId} yet.`}
            items={agentMessages.map((m, idx) => ({
              id: m.message_id || String(idx),
              title: `${m.from_agent_id} → ${m.to_agent_id}: ${m.subject}`,
              actor: m.from_agent_id,
              status: m.status || "SENT",
              timestamp: m.created_at,
            }))}
          />
        </div>
      )}

      {/* 32. AGENT CONFIGURATION */}
      {page.id === "configuration" && (
        <div className="grid-2">
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="card-title"><span>Capability State ({selectedId})</span></div>
            <select className="select" value={capState} onChange={(e) => setCapState(e.target.value)}>
              <option value="AVAILABLE">AVAILABLE</option>
              <option value="DEGRADED">DEGRADED</option>
              <option value="DISABLED">DISABLED</option>
            </select>
            <button type="button" className="btn" onClick={updateAgentState}>Update Capability State</button>
          </div>

          <div className="card">
            <div className="card-title"><span>Register Extension Agent (ApprovalGate)</span></div>
            <form onSubmit={registerExtension} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <input className="input" value={extName} onChange={(e) => setExtName(e.target.value)} placeholder="Extension agent name" />
              <input className="input" value={extDomain} onChange={(e) => setExtDomain(e.target.value)} placeholder="Domain (e.g., Aerospace Telemetry)" />
              <textarea className="textarea" rows={2} value={extRole} onChange={(e) => setExtRole(e.target.value)} placeholder="Role description & responsibilities..." />
              <button type="submit" className="btn btn-secondary">Submit Registration</button>
            </form>
          </div>
        </div>
      )}

      {/* 33. AGENT EVALUATION */}
      {page.id === "evaluation" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="card-title">
              <span>Live 60-Agent &amp; 5-Tier Gemini Verification Matrix</span>
              <div className="row">
                <button
                  id="audit-run-5-tiers"
                  type="button"
                  className="btn btn-sm"
                  disabled={auditRunning || agents.length === 0}
                  onClick={() => {
                    const repIds = ["AGT-19", "AGT-06", "AGT-03", "AGT-02", "AGT-01"];
                    runLiveAudit(agents.filter((a) => repIds.includes(a.agent_id)));
                  }}
                >
                  <Play size={12} /> Test All 5 Tiers (T1–T5)
                </button>
                <button
                  id="audit-run-all-60"
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={auditRunning || agents.length === 0}
                  onClick={() => runLiveAudit(agents)}
                >
                  <Play size={12} /> Run All 60 Live
                </button>
                {auditRunning && (
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={() => {
                      abortAuditRef.current = true;
                    }}
                  >
                    <Square size={12} /> Stop ({auditProgress.done}/{auditProgress.total})
                  </button>
                )}
              </div>
            </div>
            <p className="muted" style={{ margin: 0 }}>
              Runs real, non-destructive, uncached calls through <code>POST /api/v1/agents/&#123;id&#125;/invoke</code> via NEON → Gemini. Every agent starts as <strong>NOT TESTED</strong> until its own upstream inference finishes.
            </p>
            <DataTable
              rows={agents.map((a) => {
                const r = auditRows[a.agent_id];
                return (
                  r || {
                    agent_id: a.agent_id,
                    name: a.name,
                    tier: a.default_reasoning_tier,
                    status: "NOT TESTED" as AuditStatus,
                    provider: "—",
                    primary_model: "—",
                    actual_model: "—",
                    latency_ms: null,
                    fallback_used: false,
                  }
                );
              })}
              rowKey={(r) => r.agent_id}
              columns={[
                { key: "id", header: "Agent", mono: true, render: (r) => <strong>{r.agent_id}</strong> },
                { key: "name", header: "Specialist", render: (r) => r.name },
                { key: "tier", header: "Tier", mono: true, render: (r) => `T${r.tier}` },
                {
                  key: "status",
                  header: "Status",
                  render: (r) => (
                    <StatusIndicator
                      label={r.status}
                      tone={
                        r.status === "LIVE VERIFIED"
                          ? "success"
                          : r.status === "LIVE VERIFIED WITH FALLBACK"
                          ? "info"
                          : r.status === "FAILED"
                          ? "danger"
                          : "neutral"
                      }
                    />
                  ),
                },
                { key: "provider", header: "Provider", mono: true, render: (r) => r.provider },
                { key: "model", header: "Actual Model", mono: true, render: (r) => r.actual_model },
                { key: "latency", header: "Latency", mono: true, render: (r) => (r.latency_ms !== null ? `${r.latency_ms} ms` : "—") },
                { key: "fb", header: "Fallback", mono: true, render: (r) => (r.status === "NOT TESTED" ? "—" : r.fallback_used ? "YES" : "NO") },
              ]}
            />
          </div>

          <div className="card">
            <div className="card-title"><span>TURBO Runtime Telemetry</span></div>
            <pre className="code-block">{JSON.stringify(turboStats || { registered_agents: agents.length, policy: "ZERO_FABRICATION_ENFORCED" }, null, 2)}</pre>
          </div>
        </div>
      )}
    </ResponsiveWorkspace>
  );
}
