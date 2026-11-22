import React, { useEffect, useState } from "react";
import { Bug, Code2, Eye, GitBranch, Play, RefreshCw, RotateCcw, ShieldAlert } from "lucide-react";
import { apiFetch } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import {
  ActivityFeed,
  ConfirmationDialog,
  DataTable,
  EmptyState,
  ErrorState,
  PageHeader,
  ResponsiveWorkspace,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";
import { ReadableSummary } from "../components/ui/HumanPresentation";

export default function ProjectsModulePage({ subPage, onSelectSubPage, onNavigate }: ModulePageProps) {
  const mod = getModule("projects");
  const page = getSubPage("projects", subPage);
  const { pushToast } = useToast();

  const [projects, setProjects] = useState<any[]>([]);
  const [forgeProjects, setForgeProjects] = useState<any[]>([]);
  const [selectedProjId, setSelectedProjId] = useState("");
  const [selectedForge, setSelectedForge] = useState<any>(null);
  const [activeForgeFile, setActiveForgeFile] = useState("");
  const [previewHtml, setPreviewHtml] = useState("");
  const [activity, setActivity] = useState<any[]>([]);
  const [deployments, setDeployments] = useState<any[]>([]);
  const [repos, setRepos] = useState<any[]>([]);
  const [repoError, setRepoError] = useState("");
  const [error, setError] = useState("");

  // Forms
  const [projName, setProjName] = useState("");
  const [projRepo, setProjRepo] = useState("epejuwon-sketch/ULTRON");
  const [forgeName, setForgeName] = useState("ULTRON Micro-Console");
  const [forgeTemplate, setForgeTemplate] = useState("react_vite");
  const [forgePrompt, setForgePrompt] = useState("Minimalist spacecraft telemetry dashboard with status badges.");
  const [debugInput, setDebugInput] = useState("");
  const [debugOutput, setDebugOutput] = useState<any>(null);
  const [codeToScan, setCodeToScan] = useState("def run(cmd):\n    return cmd.strip()");
  const [scanResult, setScanResult] = useState<any>(null);
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [confirmRollback, setConfirmRollback] = useState<{ projectId: string; deploymentId: string } | null>(null);

  async function load() {
    setError("");
    try {
      const [pRes, fRes] = await Promise.all([
        apiFetch<any>("/api/v1/projects").catch(() => ({ projects: [] })),
        apiFetch<any>("/api/v1/forge/projects").catch(() => ({ projects: [] })),
      ]);
      const pList = pRes.projects || [];
      setProjects(pList);
      setForgeProjects(fRes.projects || []);
      const pid = selectedProjId || pList[0]?.project_id || "";
      if (pid && !selectedProjId) setSelectedProjId(pid);

      if (pid) {
        const [act, dep] = await Promise.all([
          apiFetch<any>(`/api/v1/projects/${pid}/activity`).catch(() => ({ activity: [] })),
          apiFetch<any>(`/api/v1/projects/${pid}/deployments`).catch(() => ({ deployments: [] })),
        ]);
        setActivity(act.activity || act.events || []);
        setDeployments(dep.deployments || []);
      }

      if (subPage === "repositories") {
        apiFetch<any>("/api/v1/github/repos")
          .then((r) => {
            setRepos(r.repositories || r.repos || []);
            setRepoError("");
          })
          .catch((e) => setRepoError(e.message));
      }
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, [subPage, selectedProjId]);

  async function createProject(e: React.FormEvent) {
    e.preventDefault();
    if (!projName.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/projects", {
        method: "POST",
        body: { name: projName.trim(), repository_url: projRepo.trim(), description: "Managed in ULTRON Projects" },
      });
      setProjName("");
      if (res.project_id) setSelectedProjId(res.project_id);
      pushToast("Project created.", "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function generateForge(e: React.FormEvent) {
    e.preventDefault();
    try {
      const res = await apiFetch<any>("/api/v1/forge/projects", {
        method: "POST",
        body: { name: forgeName, template: forgeTemplate, prompt: forgePrompt },
      });
      setSelectedForge(res);
      const keys = Object.keys(res.files || {});
      setActiveForgeFile(keys[0] || "");
      pushToast(`FORGE workspace '${res.name}' generated.`, "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function openForgePreview(forgeId: string) {
    try {
      const res = await apiFetch<any>(`/api/v1/forge/projects/${forgeId}/preview`);
      setPreviewHtml(res.html || "");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function runDebugAgent(e: React.FormEvent) {
    e.preventDefault();
    if (!debugInput.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/agents/AGT-04/invoke", {
        method: "POST",
        body: { prompt: debugInput.trim() },
      });
      setDebugOutput(res);
      pushToast("AGT-04 Debugging Agent completed analysis.", "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function runCodeScan() {
    try {
      const res = await apiFetch<any>("/api/v1/aegis/scan-code", {
        method: "POST",
        body: { code: codeToScan, language: "python" },
      });
      setScanResult(res);
      pushToast("AEGIS static code scan completed.", "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`PROJECTS & FORGE // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <button type="button" className="btn btn-secondary btn-sm" onClick={load}>
            <RefreshCw size={13} /> Refresh
          </button>
        }
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {/* 51. PROJECTS OVERVIEW */}
      {page.id === "overview" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title"><span>Register Engineering Project</span></div>
            <form onSubmit={createProject} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <input className="input" value={projName} onChange={(e) => setProjName(e.target.value)} placeholder="Project Name (e.g., ULTRON OS)" />
              <input className="input" value={projRepo} onChange={(e) => setProjRepo(e.target.value)} placeholder="Repository (owner/repo)" />
              <button type="submit" className="btn">Create Project</button>
            </form>
          </div>
          <div className="card">
            <div className="card-title"><span>Managed Projects ({projects.length}) · FORGE ({forgeProjects.length})</span></div>
            {projects.length === 0 ? (
              <EmptyState title="No Projects Yet" description="Create a project on the left or generate a FORGE workspace." />
            ) : (
              projects.map((p) => (
                <button
                  key={p.project_id}
                  type="button"
                  className={`list-item list-item-btn ${selectedProjId === p.project_id ? "list-item-active" : ""}`}
                  style={{ marginBottom: 8 }}
                  onClick={() => {
                    setSelectedProjId(p.project_id);
                    onSelectSubPage("details");
                  }}
                >
                  <div className="row-between" style={{ width: "100%" }}>
                    <strong>{p.name}</strong>
                    <span className="pill">{p.status || "ACTIVE"}</span>
                  </div>
                  <div className="muted mono">{p.repository_url || p.project_id}</div>
                </button>
              ))
            )}
          </div>
        </div>
      )}

      {/* 52. PROJECT DETAILS */}
      {page.id === "details" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title">
            <span>Project Inspector</span>
            {selectedProjId && (
              <button
                type="button"
                className="btn btn-sm"
                onClick={async () => {
                  const res = await apiFetch<any>(`/api/v1/projects/${selectedProjId}/analyze`, { method: "POST" });
                  setAnalysisResult(res);
                  pushToast("Project analysis completed.", "success");
                }}
              >
                <Play size={13} /> Run Automated Analysis
              </button>
            )}
          </div>
          {!selectedProjId ? (
            <EmptyState title="No Project Selected" description="Create or select a project in Projects Overview." />
          ) : (
            <>
              <div className="mono muted">Selected Project ID: {selectedProjId}</div>
              {analysisResult && (
                <ReadableSummary title="Project Analysis Summary" data={analysisResult} diagnosticsTitle="Technical Diagnostics — Analysis Payload" />
              )}
            </>
          )}
        </div>
      )}

      {/* 53. CODING WORKSPACE & LIVE PREVIEW */}
      {page.id === "coding" && (
        <div className="grid-2">
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="card-title">
              <span><Code2 size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />FORGE Source Explorer</span>
              {selectedForge && (
                <button type="button" className="btn btn-sm" onClick={() => openForgePreview(selectedForge.forge_id)}>
                  <Eye size={13} /> Load Sandbox Preview
                </button>
              )}
            </div>
            <div className="row">
              {forgeProjects.map((fp) => (
                <button
                  key={fp.forge_id}
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={async () => {
                    const full = await apiFetch<any>(`/api/v1/forge/projects/${fp.forge_id}`);
                    setSelectedForge(full);
                    setActiveForgeFile(Object.keys(full.files || {})[0] || "");
                  }}
                >
                  {fp.name}
                </button>
              ))}
            </div>
            {selectedForge?.files ? (
              <>
                <div className="row">
                  {Object.keys(selectedForge.files).map((fn) => (
                    <button
                      key={fn}
                      type="button"
                      className={`seg-btn ${activeForgeFile === fn ? "active" : ""}`}
                      onClick={() => setActiveForgeFile(fn)}
                    >
                      {fn}
                    </button>
                  ))}
                </div>
                <pre className="code-block">{selectedForge.files[activeForgeFile] || ""}</pre>
              </>
            ) : (
              <EmptyState title="No FORGE Workspace Open" description="Generate a workspace in Code Generation or pick one above." />
            )}
          </div>

          <div className="card">
            <div className="card-title"><span>Sandboxed Live Preview</span></div>
            {previewHtml ? (
              <iframe
                title="FORGE Live Preview"
                sandbox="allow-scripts"
                srcDoc={previewHtml}
                style={{ width: "100%", height: 360, border: "1px solid var(--border)", borderRadius: 8, background: "#fff" }}
              />
            ) : (
              <EmptyState title="Preview Idle" description="Click 'Load Sandbox Preview' on any FORGE workspace." />
            )}
          </div>
        </div>
      )}

      {/* 54. CODE GENERATION */}
      {page.id === "generation" && (
        <div className="card" style={{ maxWidth: 680 }}>
          <div className="card-title"><span>FORGE Application & Code Generator</span></div>
          <form onSubmit={generateForge} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="row">
              <input className="input" style={{ flex: 2 }} value={forgeName} onChange={(e) => setForgeName(e.target.value)} placeholder="Workspace Name" />
              <select className="select" style={{ flex: 1 }} value={forgeTemplate} onChange={(e) => setForgeTemplate(e.target.value)}>
                <option value="react_vite">React + Vite</option>
                <option value="fastapi_service">FastAPI Service</option>
                <option value="static_site">Static HTML/CSS/JS</option>
              </select>
            </div>
            <textarea className="textarea" rows={3} value={forgePrompt} onChange={(e) => setForgePrompt(e.target.value)} />
            <button type="submit" className="btn">Generate FORGE Project</button>
          </form>
        </div>
      )}

      {/* 55. DEBUGGING WORKSPACE */}
      {page.id === "debugging" && (
        <div className="grid-2">
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="card-title"><span><Bug size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />AGT-04 Debugging Specialist</span></div>
            <form onSubmit={runDebugAgent} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <textarea className="textarea" rows={4} value={debugInput} onChange={(e) => setDebugInput(e.target.value)} placeholder="Paste stack trace, failing test, or bug context for AGT-04..." />
              <button type="submit" className="btn">Diagnose with AGT-04</button>
            </form>
            {debugOutput && (
              <ReadableSummary title="AGT-04 Debugging Diagnosis" data={debugOutput} diagnosticsTitle="Technical Diagnostics — Debug Payload" />
            )}
          </div>

          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="card-title"><span><ShieldAlert size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />AEGIS Static Code Scanner</span></div>
            <textarea className="textarea mono" rows={4} value={codeToScan} onChange={(e) => setCodeToScan(e.target.value)} />
            <button type="button" className="btn btn-secondary" onClick={runCodeScan}>Run AEGIS Static Security Scan</button>
            {scanResult && (
              <ReadableSummary title="AEGIS Security Scan Result" data={scanResult} diagnosticsTitle="Technical Diagnostics — Scan Findings" />
            )}
          </div>
        </div>
      )}

      {/* 56. REPOSITORY CONNECTIONS */}
      {page.id === "repositories" && (
        <div className="card">
          <div className="card-title">
            <span><GitBranch size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />GitHub Repositories (/api/v1/github/repos)</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("connections", "oauth")}>
              Configure GitHub OAuth
            </button>
          </div>
          {repoError ? (
            <EmptyState title="GitHub Not Authenticated" description={`${repoError}. Authenticate GitHub in Connections Centre.`} />
          ) : (
            <DataTable
              rows={repos}
              rowKey={(r, i) => r.full_name || String(i)}
              emptyTitle="No Repositories Listed"
              emptyDescription="Connect GitHub to inspect repositories, branches, and PRs."
              columns={[
                { key: "name", header: "Repository", mono: true, render: (r) => <strong>{r.full_name || r.name}</strong> },
                { key: "branch", header: "Default Branch", mono: true, render: (r) => r.default_branch || "main" },
              ]}
            />
          )}
        </div>
      )}

      {/* 57. DEVELOPMENT ACTIVITY */}
      {page.id === "dev-activity" && (
        <div className="card">
          <div className="card-title"><span>Engineering Activity Trail</span></div>
          <ActivityFeed
            emptyLabel="No project activity recorded yet."
            items={activity.map((a, idx) => ({
              id: a.activity_id || String(idx),
              title: a.action || a.summary || "Project Event",
              actor: a.actor || "FORGE",
              status: a.status || "RECORDED",
              timestamp: a.created_at,
            }))}
          />
        </div>
      )}

      {/* 58. DEPLOYMENT HISTORY */}
      {page.id === "deployments" && (
        <div className="card">
          <div className="card-title"><span>Deployment History ({deployments.length})</span></div>
          <DataTable
            rows={deployments}
            rowKey={(d, i) => d.deployment_id || String(i)}
            emptyTitle="No Deployments Recorded"
            emptyDescription="Project deployments and ApprovalGate rollbacks appear here."
            columns={[
              { key: "env", header: "Environment", mono: true, render: (d) => d.environment || "preview" },
              { key: "status", header: "Status", render: (d) => <StatusIndicator label={d.status || "READY"} tone={d.status === "READY" ? "success" : "info"} /> },
              {
                key: "rb",
                header: "Rollback",
                render: (d) => (
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={() => setConfirmRollback({ projectId: selectedProjId, deploymentId: d.deployment_id })}
                  >
                    <RotateCcw size={12} /> Rollback
                  </button>
                ),
              },
            ]}
          />
        </div>
      )}

      <ConfirmationDialog
        open={Boolean(confirmRollback)}
        title="Request Deployment Rollback"
        message="Submit an ApprovalGate-governed rollback request for this deployment?"
        confirmLabel="Request Rollback"
        onCancel={() => setConfirmRollback(null)}
        onConfirm={async () => {
          if (confirmRollback) {
            await apiFetch(
              `/api/v1/projects/${confirmRollback.projectId}/deployments/${confirmRollback.deploymentId}/rollback`,
              { method: "POST" }
            );
            pushToast("Rollback submitted to ApprovalGate.", "success");
            load();
          }
          setConfirmRollback(null);
        }}
      />
    </ResponsiveWorkspace>
  );
}
