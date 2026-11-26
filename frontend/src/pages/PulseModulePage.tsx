import React, { useEffect, useState } from "react";
import { Play, RefreshCw } from "lucide-react";
import { apiFetch } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import {
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

export default function PulseModulePage({ subPage, onSelectSubPage, onNavigate }: ModulePageProps) {
  const mod = getModule("pulse");
  const page = getSubPage("pulse", subPage);
  const { pushToast } = useToast();

  const [pages, setPages] = useState<any[]>([]);
  const [liveData, setLiveData] = useState<any>(null);
  const [tools, setTools] = useState<any[]>([]);
  const [toolHistory, setToolHistory] = useState<any[]>([]);
  const [schedules, setSchedules] = useState<any[]>([]);
  const [monitoring, setMonitoring] = useState<any>(null);
  const [error, setError] = useState("");

  // Builder & tool execute
  const [pageTitle, setPageTitle] = useState("ULTRON Operations Live");
  const [pageType, setPageType] = useState("AGENTS");
  const [selectedTool, setSelectedTool] = useState("");
  const [toolArgs, setToolArgs] = useState("{}");
  const [toolOutput, setToolOutput] = useState<any>(null);

  async function load() {
    setError("");
    try {
      const [pRes, tRes, hRes, sRes, mRes] = await Promise.all([
        apiFetch<any>("/api/v1/pulse/pages").catch(() => ({ pages: [] })),
        apiFetch<any>("/api/v1/tools").catch(() => ({ tools: [] })),
        apiFetch<any>("/api/v1/tools/executions/history").catch(() => ({ executions: [] })),
        apiFetch<any>("/api/v1/argon/schedules").catch(() => ({ schedules: [] })),
        apiFetch<any>("/api/v1/monitoring/overview").catch(() => null),
      ]);
      setPages(pRes.pages || []);
      const toolList = tRes.tools || [];
      setTools(toolList);
      if (!selectedTool && toolList.length > 0) setSelectedTool(toolList[0].name || toolList[0].tool_name);
      setToolHistory(hRes.executions || hRes.history || []);
      setSchedules(sRes.schedules || []);
      setMonitoring(mRes);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, [subPage]);

  async function createPulsePage(e: React.FormEvent) {
    e.preventDefault();
    if (!pageTitle.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/pulse/pages", {
        method: "POST",
        body: { title: pageTitle.trim(), page_type: pageType },
      });
      setLiveData(await apiFetch(`/api/v1/pulse/pages/${res.page_id}/live`));
      pushToast(`PULSE page '${pageTitle}' created.`, "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function executeTool(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedTool) return;
    try {
      const parsed = JSON.parse(toolArgs || "{}");
      const res = await apiFetch<any>(`/api/v1/tools/${encodeURIComponent(selectedTool)}/execute`, {
        method: "POST",
        body: { arguments: parsed },
      });
      setToolOutput(res);
      pushToast(`Executed tool ${selectedTool}.`, "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`PULSE & AUTOMATION // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <button type="button" className="btn btn-secondary btn-sm" onClick={load}>
            <RefreshCw size={13} /> Refresh
          </button>
        }
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {/* 74. PULSE OVERVIEW */}
      {page.id === "overview" && (
        <div className="grid-3">
          <MetricDisplay label="Live PULSE Pages" value={pages.length} sub="DB-hydrated views" tone="info" />
          <MetricDisplay label="Registered Tools" value={tools.length} sub="RBAC + ApprovalGate checked" tone="success" />
          <MetricDisplay label="Recurring Schedules" value={schedules.length} sub="ARGON automation" tone="neutral" />
        </div>
      )}

      {/* 75. LIVE PAGES */}
      {page.id === "live-pages" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title"><span>Live Operational Pages ({pages.length})</span></div>
            {pages.length === 0 ? (
              <EmptyState title="No PULSE Pages Yet" description="Build your first live page in Page Builder." />
            ) : (
              pages.map((p) => (
                <div key={p.page_id} className="list-item" style={{ marginBottom: 8 }}>
                  <div className="row-between">
                    <strong>{p.title} ({p.page_type})</strong>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={async () => setLiveData(await apiFetch(`/api/v1/pulse/pages/${p.page_id}/live`))}
                    >
                      Hydrate Live
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
          <div className="card">
            <div className="card-title"><span>Live Telemetry Hydration</span></div>
            {liveData ? (
              <ReadableSummary title="Hydrated Page Telemetry" data={liveData} diagnosticsTitle="Technical Diagnostics — Live Page Payload" />
            ) : (
              <EmptyState title="Select a Page" description="Click Hydrate Live to fetch current backend metrics." />
            )}
          </div>
        </div>
      )}

      {/* 76. PAGE BUILDER */}
      {page.id === "builder" && (
        <div className="card" style={{ maxWidth: 640 }}>
          <div className="card-title"><span>Create Live PULSE Page</span></div>
          <form onSubmit={createPulsePage} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <input className="input" value={pageTitle} onChange={(e) => setPageTitle(e.target.value)} placeholder="Page title" />
            <select className="select" value={pageType} onChange={(e) => setPageType(e.target.value)}>
              <option value="AGENTS">AGENTS — 60-Agent Telemetry</option>
              <option value="CARAVAN">CARAVAN — Growth & Funnel BI</option>
              <option value="FINANCE">FINANCE — Treasury Ledger</option>
              <option value="ORDERS">ORDERS — ATLAS Fulfillment</option>
            </select>
            <button type="submit" className="btn">Create & Hydrate Page</button>
          </form>
        </div>
      )}

      {/* 77. PAGE ANALYTICS */}
      {page.id === "analytics" && (
        <div className="card">
          <div className="card-title"><span>Runtime HTTP &amp; System Analytics</span></div>
          <ReadableSummary
            data={monitoring || { status: "Loading..." }}
            diagnosticsTitle="Technical Diagnostics — Monitoring Overview"
          />
        </div>
      )}

      {/* 78. AUTOMATION CENTRE (TOOLS) */}
      {page.id === "automation" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title"><span>Execute Authorized Backend Tool ({tools.length})</span></div>
            <form onSubmit={executeTool} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <select className="select" value={selectedTool} onChange={(e) => setSelectedTool(e.target.value)}>
                {tools.map((t) => {
                  const nm = t.name || t.tool_name;
                  return <option key={nm} value={nm}>{nm} ({t.risk_level || "SAFE"})</option>;
                })}
              </select>
              <textarea className="textarea mono" rows={4} value={toolArgs} onChange={(e) => setToolArgs(e.target.value)} placeholder='{"key": "value"}' />
              <button type="submit" className="btn"><Play size={14} /> Execute Tool</button>
            </form>
            {toolOutput && (
              <div style={{ marginTop: 10 }}>
                <ReadableSummary title="Tool Execution Result" data={toolOutput} diagnosticsTitle="Technical Diagnostics — Raw Tool Output" />
              </div>
            )}
          </div>
          <div className="card">
            <div className="card-title"><span>Authorized Tool Registry</span></div>
            <DataTable
              rows={tools}
              rowKey={(t, i) => t.name || t.tool_name || String(i)}
              columns={[
                { key: "name", header: "Tool", mono: true, render: (t) => <strong>{t.name || t.tool_name}</strong> },
                { key: "risk", header: "Risk", render: (t) => <StatusIndicator label={t.risk_level || "LOW"} tone={t.risk_level === "HIGH" ? "warn" : "info"} /> },
              ]}
            />
          </div>
        </div>
      )}

      {/* 79. WORKFLOW AUTOMATION */}
      {page.id === "workflows" && (
        <div className="card">
          <div className="card-title"><span>Multi-Agent Workflow Automation</span></div>
          <p className="muted">Workflows execute through the ARGON Orchestration DAG engine with ApprovalGate governance.</p>
          <button type="button" className="btn btn-sm" onClick={() => onNavigate("argon", "orchestrate")}>
            Open ARGON Workflow Dispatcher
          </button>
        </div>
      )}

      {/* 80. SCHEDULED AUTOMATION */}
      {page.id === "scheduled" && (
        <div className="card">
          <div className="card-title">
            <span>Scheduled Automation ({schedules.length})</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("argon", "schedules")}>
              Manage in ARGON
            </button>
          </div>
          <DataTable
            rows={schedules}
            rowKey={(s, i) => s.schedule_id || String(i)}
            emptyTitle="No Scheduled Automations"
            emptyDescription="Create a recurring schedule in ARGON Scheduled Tasks."
            columns={[
              { key: "name", header: "Schedule", render: (s) => <strong>{s.name}</strong> },
              { key: "interval", header: "Interval", mono: true, render: (s) => `${s.interval_seconds}s` },
              { key: "type", header: "Type", mono: true, render: (s) => s.job_type },
            ]}
          />
        </div>
      )}

      {/* 81. AUTOMATION HISTORY */}
      {page.id === "history" && (
        <div className="card">
          <div className="card-title"><span>Tool Execution History ({toolHistory.length})</span></div>
          <DataTable
            rows={toolHistory}
            rowKey={(h, i) => h.execution_id || String(i)}
            emptyTitle="No Tool Executions Recorded"
            emptyDescription="Executed tools from Automation Centre will be logged here."
            columns={[
              { key: "tool", header: "Tool", mono: true, render: (h) => <strong>{h.tool_name}</strong> },
              { key: "status", header: "Status", render: (h) => <StatusIndicator label={h.status || "DONE"} tone={h.status === "FAILED" ? "danger" : "success"} /> },
              { key: "time", header: "Executed", mono: true, render: (h) => h.created_at || "—" },
            ]}
          />
        </div>
      )}
    </ResponsiveWorkspace>
  );
}
