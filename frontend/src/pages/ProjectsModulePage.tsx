import React, { useEffect, useMemo, useState } from "react";
import {
  Archive,
  Bug,
  CheckCircle2,
  Code2,
  Download,
  Edit3,
  Eye,
  FileText,
  FolderGit2,
  GitBranch,
  Layers,
  LayoutGrid,
  List,
  Pause,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Save,
  ShieldAlert,
  Sparkles,
  Trash2,
  XCircle,
} from "lucide-react";
import { apiFetch, downloadAuthFile } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import {
  ActivityFeed,
  ConfirmationDialog,
  DataTable,
  EmptyState,
  ErrorState,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  SearchBar,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";
import { ReadableSummary, TechnicalDiagnostics } from "../components/ui/HumanPresentation";

type TaskViewMode = "board" | "list" | "timeline";

function taskTone(state: string): "success" | "info" | "warn" | "danger" | "neutral" {
  const s = (state || "").toUpperCase();
  if (s === "COMPLETED") return "success";
  if (s === "RUNNING" || s === "QUEUED") return "info";
  if (s === "WAITING_FOR_APPROVAL" || s === "PAUSED") return "warn";
  if (s === "FAILED" || s === "CANCELLED") return "danger";
  return "neutral";
}

function projectTone(status: string): "success" | "info" | "warn" | "neutral" {
  const s = (status || "ACTIVE").toUpperCase();
  if (s === "ACTIVE") return "success";
  if (s === "COMPLETED") return "info";
  if (s === "PAUSED") return "warn";
  return "neutral";
}

export default function ProjectsModulePage({
  subPage,
  onSelectSubPage,
  onNavigate,
  onSendToNeon,
  onAttachFileToNeon,
}: ModulePageProps) {
  const mod = getModule("projects");
  const page = getSubPage("projects", subPage);
  const { pushToast } = useToast();

  // Core data
  const [projects, setProjects] = useState<any[]>([]);
  const [forgeProjects, setForgeProjects] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [selectedProjId, setSelectedProjId] = useState("");
  const [projectTasks, setProjectTasks] = useState<any[]>([]);
  const [projectFiles, setProjectFiles] = useState<any[]>([]);
  const [allFiles, setAllFiles] = useState<any[]>([]);
  const [activity, setActivity] = useState<any[]>([]);
  const [deployments, setDeployments] = useState<any[]>([]);
  const [repoInfo, setRepoInfo] = useState<any>(null);
  const [repos, setRepos] = useState<any[]>([]);
  const [repoError, setRepoError] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Overview search / filter / sort
  const [projSearch, setProjSearch] = useState("");
  const [projStatusFilter, setProjStatusFilter] = useState("ALL");
  const [projSort, setProjSort] = useState<"newest" | "name" | "budget">("newest");

  // Create / Edit Project
  const [projName, setProjName] = useState("");
  const [projDesc, setProjDesc] = useState("");
  const [projRepo, setProjRepo] = useState("epejuwon-sketch/ULTRON");
  const [projBranch, setProjBranch] = useState("main");
  const [projBudget, setProjBudget] = useState("0");
  const [editingProj, setEditingProj] = useState(false);
  const [editProjName, setEditProjName] = useState("");
  const [editProjDesc, setEditProjDesc] = useState("");
  const [editProjRepo, setEditProjRepo] = useState("");
  const [editProjBranch, setEditProjBranch] = useState("main");
  const [editProjStatus, setEditProjStatus] = useState("ACTIVE");
  const [editProjBudget, setEditProjBudget] = useState("0");

  // Project Tasks & Intelligence
  const [taskView, setTaskView] = useState<TaskViewMode>("board");
  const [taskTitle, setTaskTitle] = useState("");
  const [taskObjective, setTaskObjective] = useState("");
  const [taskAgent, setTaskAgent] = useState("AGT-02");
  const [attachFileId, setAttachFileId] = useState("");
  const [neonPlanPrompt, setNeonPlanPrompt] = useState("");
  const [neonPlanResult, setNeonPlanResult] = useState<any>(null);
  const [neonPlanning, setNeonPlanning] = useState(false);

  // AST Analyzer & Code Proposals
  const [analyzeFilename, setAnalyzeFilename] = useState("app/main.py");
  const [analyzeSource, setAnalyzeSource] = useState("def verify_health():\n    return {'status': 'ok'}\n");
  const [analysisResult, setAnalysisResult] = useState<any>(null);
  const [proposalSpec, setProposalSpec] = useState("");
  const [proposalBranch, setProposalBranch] = useState("feat/ultron-os-2026-backend");
  const [proposalResult, setProposalResult] = useState<any>(null);

  // FORGE Workspace & Editor
  const [selectedForge, setSelectedForge] = useState<any>(null);
  const [editedForgeFiles, setEditedForgeFiles] = useState<Record<string, string>>({});
  const [activeForgeFile, setActiveForgeFile] = useState("");
  const [previewHtml, setPreviewHtml] = useState("");
  const [forgeName, setForgeName] = useState("ULTRON Micro-Console");
  const [forgeTemplate, setForgeTemplate] = useState("web_app");
  const [forgePrompt, setForgePrompt] = useState("Minimalist spacecraft telemetry dashboard with status badges.");

  // Debugging & AEGIS
  const [debugInput, setDebugInput] = useState("");
  const [debugOutput, setDebugOutput] = useState<any>(null);
  const [codeToScan, setCodeToScan] = useState("def run(cmd):\n    return cmd.strip()");
  const [scanResult, setScanResult] = useState<any>(null);

  // Deployments
  const [deployEnv, setDeployEnv] = useState<"staging" | "production">("staging");
  const [deployRef, setDeployRef] = useState("feat/ultron-os-2026-backend");
  const [deployNotes, setDeployNotes] = useState("");

  // Confirmations
  const [confirmDialog, setConfirmDialog] = useState<{
    title: string;
    message: string;
    confirmLabel: string;
    fn: () => Promise<void>;
  } | null>(null);

  const selectedProject = useMemo(
    () => projects.find((p) => p.project_id === selectedProjId) || null,
    [projects, selectedProjId]
  );

  const forgeDirty = useMemo(() => {
    if (!selectedForge?.files) return false;
    return Object.keys(editedForgeFiles).some((k) => editedForgeFiles[k] !== selectedForge.files[k]);
  }, [selectedForge, editedForgeFiles]);

  async function load(overrideProjId?: string) {
    setError("");
    setLoading(true);
    try {
      const [pRes, fRes, aRes, filesRes] = await Promise.all([
        apiFetch<any>("/api/v1/projects").catch(() => ({ projects: [] })),
        apiFetch<any>("/api/v1/forge/projects").catch(() => ({ projects: [] })),
        apiFetch<any>("/api/v1/agents").catch(() => ({ agents: [] })),
        apiFetch<any>("/api/v1/files").catch(() => ({ files: [] })),
      ]);
      const pList = pRes.projects || [];
      setProjects(pList);
      setForgeProjects(fRes.projects || []);
      setAgents(aRes.agents || []);
      setAllFiles(filesRes.files || []);

      const pid = overrideProjId ?? (selectedProjId || pList[0]?.project_id || "");
      if (pid && pid !== selectedProjId) setSelectedProjId(pid);

      if (pid) {
        const [act, dep, tRes, pfRes, rInfo] = await Promise.all([
          apiFetch<any>(`/api/v1/projects/${pid}/activity`).catch(() => ({ activities: [] })),
          apiFetch<any>(`/api/v1/projects/${pid}/deployments`).catch(() => ({ deployments: [] })),
          apiFetch<any>(`/api/v1/tasks?project_id=${encodeURIComponent(pid)}`).catch(() => ({ tasks: [] })),
          apiFetch<any>(`/api/v1/files?project_id=${encodeURIComponent(pid)}`).catch(() => ({ files: [] })),
          apiFetch<any>(`/api/v1/projects/${pid}/repository`).catch(() => null),
        ]);
        setActivity(act.activities || act.activity || act.events || []);
        setDeployments(dep.deployments || []);
        setProjectTasks(tRes.tasks || []);
        setProjectFiles(pfRes.files || []);
        setRepoInfo(rInfo);
      } else {
        setActivity([]);
        setDeployments([]);
        setProjectTasks([]);
        setProjectFiles([]);
        setRepoInfo(null);
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
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, [subPage, selectedProjId]);

  useEffect(() => {
    if (selectedProject) {
      setEditProjName(selectedProject.name || "");
      setEditProjDesc(selectedProject.description || "");
      setEditProjRepo(selectedProject.repo_full_name || "");
      setEditProjBranch(selectedProject.default_branch || "main");
      setEditProjStatus(selectedProject.status || "ACTIVE");
      setEditProjBudget(String(selectedProject.budget_usd ?? 0));
    }
  }, [selectedProject?.project_id]);

  async function createProject(e: React.FormEvent) {
    e.preventDefault();
    if (!projName.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/projects", {
        method: "POST",
        body: {
          name: projName.trim(),
          description: projDesc.trim() || "Managed in ULTRON Projects",
          repo_full_name: projRepo.trim(),
          default_branch: projBranch.trim() || "main",
          budget_usd: Number(projBudget) || 0,
        },
      });
      setProjName("");
      setProjDesc("");
      if (res.project_id) setSelectedProjId(res.project_id);
      pushToast(`Project '${res.name}' created.`, "success");
      await load(res.project_id);
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function saveProjectEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedProjId) return;
    try {
      await apiFetch(`/api/v1/projects/${selectedProjId}`, {
        method: "PATCH",
        body: {
          name: editProjName.trim(),
          description: editProjDesc.trim(),
          repo_full_name: editProjRepo.trim(),
          default_branch: editProjBranch.trim() || "main",
          status: editProjStatus,
          budget_usd: Number(editProjBudget) || 0,
        },
      });
      setEditingProj(false);
      pushToast("Project updated.", "success");
      await load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function createProjectTask(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedProjId || !taskTitle.trim()) return;
    try {
      await apiFetch("/api/v1/tasks", {
        method: "POST",
        body: {
          title: taskTitle.trim(),
          objective: taskObjective.trim() || taskTitle.trim(),
          preferred_agent_id: taskAgent,
          project_id: selectedProjId,
        },
      });
      setTaskTitle("");
      setTaskObjective("");
      pushToast(`Task assigned to ${taskAgent}.`, "success");
      await load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function runTaskAction(taskId: string, action: "execute" | "pause" | "resume" | "retry" | "cancel") {
    try {
      await apiFetch(`/api/v1/tasks/${taskId}/${action}`, { method: "POST" });
      pushToast(`Task ${action}d.`, "success");
      await load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function askNeonAboutProject(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedProject || !neonPlanPrompt.trim()) return;
    setNeonPlanning(true);
    try {
      const ctx = `Project: ${selectedProject.name} (${selectedProject.status})\nRepo: ${selectedProject.repo_full_name || "local"} (${selectedProject.default_branch})\nTasks: ${projectTasks.length} total, ${projectTasks.filter((t) => t.lifecycle_state === "COMPLETED").length} completed.\nAttached files: ${projectFiles.map((f) => f.filename).join(", ") || "none"}.\nRequest: ${neonPlanPrompt.trim()}`;
      const res = await apiFetch<any>("/api/v1/neon/conversations", {
        method: "POST",
        body: {
          prompt: ctx,
          agent_id: "AGT-01",
          file_ids: projectFiles.map((f) => f.file_id).slice(0, 4),
        },
      });
      setNeonPlanResult(res);
      pushToast("NEON project intelligence completed.", "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    } finally {
      setNeonPlanning(false);
    }
  }

  async function openForgeWorkspace(forgeId: string) {
    try {
      const full = await apiFetch<any>(`/api/v1/forge/projects/${forgeId}`);
      setSelectedForge(full);
      setEditedForgeFiles({ ...(full.files || {}) });
      setActiveForgeFile(Object.keys(full.files || {})[0] || "");
      setPreviewHtml(full.preview_html || "");
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
      setEditedForgeFiles({ ...(res.files || {}) });
      setActiveForgeFile(Object.keys(res.files || {})[0] || "");
      setPreviewHtml(res.preview_html || "");
      pushToast(`FORGE workspace '${res.name}' generated & AEGIS-verified.`, "success");
      await load();
      onSelectSubPage("coding");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function saveForgeEdits() {
    if (!selectedForge) return;
    try {
      const updated = await apiFetch<any>(`/api/v1/forge/projects/${selectedForge.forge_id}`, {
        method: "PATCH",
        body: { files: editedForgeFiles },
      });
      setSelectedForge(updated);
      setEditedForgeFiles({ ...(updated.files || {}) });
      setPreviewHtml(updated.preview_html || "");
      pushToast(`Saved & AEGIS-verified (${updated.status}).`, updated.status === "VERIFIED" ? "success" : "info");
      await load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function openForgePreview(forgeId: string) {
    try {
      const htmlText = await apiFetch<string>(`/api/v1/forge/projects/${forgeId}/preview`);
      setPreviewHtml(typeof htmlText === "string" ? htmlText : "");
      pushToast("Sandboxed live preview loaded.", "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function submitCodeProposal(e: React.FormEvent) {
    e.preventDefault();
    if (!selectedProjId || !proposalSpec.trim()) return;
    try {
      const res = await apiFetch<any>(`/api/v1/projects/${selectedProjId}/code-proposals`, {
        method: "POST",
        body: { specification: proposalSpec.trim(), target_branch: proposalBranch.trim() || "main" },
      });
      setProposalResult(res);
      pushToast("Code proposal generated (review required before applying).", "success");
      await load();
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

  const visibleProjects = useMemo(() => {
    const q = projSearch.trim().toLowerCase();
    const filtered = projects.filter((p) => {
      const matchSearch =
        !q ||
        (p.name || "").toLowerCase().includes(q) ||
        (p.repo_full_name || "").toLowerCase().includes(q) ||
        (p.description || "").toLowerCase().includes(q);
      const matchStatus = projStatusFilter === "ALL" || (p.status || "ACTIVE").toUpperCase() === projStatusFilter;
      return matchSearch && matchStatus;
    });
    if (projSort === "name") return [...filtered].sort((a, b) => (a.name || "").localeCompare(b.name || ""));
    if (projSort === "budget") return [...filtered].sort((a, b) => Number(b.budget_usd || 0) - Number(a.budget_usd || 0));
    return filtered;
  }, [projects, projSearch, projStatusFilter, projSort]);

  const completedTaskCount = projectTasks.filter((t) => t.lifecycle_state === "COMPLETED").length;
  const projectProgressPct = projectTasks.length > 0 ? Math.round((completedTaskCount / projectTasks.length) * 100) : 0;

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`PROJECTS & FORGE // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <div className="row" style={{ gap: 8 }}>
            {projects.length > 0 && (
              <select
                className="select"
                aria-label="Active Project"
                value={selectedProjId}
                onChange={(e) => setSelectedProjId(e.target.value)}
                style={{ maxWidth: 220 }}
              >
                {projects.map((p) => (
                  <option key={p.project_id} value={p.project_id}>
                    {p.name} ({p.status || "ACTIVE"})
                  </option>
                ))}
              </select>
            )}
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => load()} disabled={loading}>
              <RefreshCw size={13} /> {loading ? "Syncing..." : "Refresh"}
            </button>
          </div>
        }
      />

      {error && <ErrorState message={error} onRetry={() => load()} />}

      {/* 51. PROJECTS OVERVIEW */}
      {page.id === "overview" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="grid-4">
            <MetricDisplay label="Managed Projects" value={projects.length} sub="Tenant-isolated workspaces" tone="info" />
            <MetricDisplay
              label="Active Projects"
              value={projects.filter((p) => (p.status || "ACTIVE") === "ACTIVE").length}
              sub={`${projects.filter((p) => p.status === "ARCHIVED").length} archived`}
              tone="success"
            />
            <MetricDisplay
              label="Selected Project Tasks"
              value={projectTasks.length}
              sub={`${completedTaskCount} completed (${projectProgressPct}%)`}
              tone="neutral"
            />
            <MetricDisplay label="FORGE Workspaces" value={forgeProjects.length} sub="AEGIS-verified bundles" tone="info" />
          </div>

          <div className="grid-2">
            <div className="card">
              <div className="card-title">
                <span><Plus size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Create Engineering Project</span>
              </div>
              <form onSubmit={createProject} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <input
                  className="input"
                  value={projName}
                  onChange={(e) => setProjName(e.target.value)}
                  placeholder="Project Name (e.g., ULTRON Core v2)"
                  required
                />
                <input
                  className="input"
                  value={projDesc}
                  onChange={(e) => setProjDesc(e.target.value)}
                  placeholder="Project objective & scope"
                />
                <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                  <input
                    className="input"
                    style={{ flex: 2, minWidth: 160 }}
                    value={projRepo}
                    onChange={(e) => setProjRepo(e.target.value)}
                    placeholder="Repository (owner/repo)"
                  />
                  <input
                    className="input"
                    style={{ flex: 1, minWidth: 100 }}
                    value={projBranch}
                    onChange={(e) => setProjBranch(e.target.value)}
                    placeholder="Branch"
                  />
                  <input
                    className="input"
                    type="number"
                    min="0"
                    step="10"
                    style={{ width: 110 }}
                    value={projBudget}
                    onChange={(e) => setProjBudget(e.target.value)}
                    placeholder="Budget $"
                    aria-label="Project Budget USD"
                  />
                </div>
                <button type="submit" className="btn">Create Project</button>
              </form>
            </div>

            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="card-title">
                <span>Project Directory ({visibleProjects.length})</span>
                <select className="select" style={{ width: 130 }} value={projSort} onChange={(e) => setProjSort(e.target.value as any)} aria-label="Sort projects">
                  <option value="newest">Newest</option>
                  <option value="name">Name A–Z</option>
                  <option value="budget">Budget High–Low</option>
                </select>
              </div>
              <SearchBar value={projSearch} onChange={setProjSearch} placeholder="Search projects by name, repo, or scope..." />
              <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                {["ALL", "ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED"].map((st) => (
                  <button
                    key={st}
                    type="button"
                    className={`seg-btn ${projStatusFilter === st ? "active" : ""}`}
                    onClick={() => setProjStatusFilter(st)}
                  >
                    {st}
                  </button>
                ))}
              </div>
              {visibleProjects.length === 0 ? (
                <EmptyState title="No Matching Projects" description="Create a project on the left or adjust your filters." />
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {visibleProjects.map((p) => (
                    <div
                      key={p.project_id}
                      className={`list-item ${selectedProjId === p.project_id ? "list-item-active" : ""}`}
                      style={{ display: "flex", flexDirection: "column", gap: 6 }}
                    >
                      <div className="row-between" style={{ gap: 8, flexWrap: "wrap" }}>
                        <button
                          type="button"
                          className="btn-link"
                          style={{ textAlign: "left", background: "none", border: 0, color: "inherit", cursor: "pointer", padding: 0 }}
                          onClick={() => {
                            setSelectedProjId(p.project_id);
                            onSelectSubPage("details");
                          }}
                        >
                          <strong>{p.name}</strong>
                        </button>
                        <StatusIndicator label={p.status || "ACTIVE"} tone={projectTone(p.status)} />
                      </div>
                      <div className="muted mono" style={{ fontSize: 11 }}>
                        {p.repo_full_name || "local workspace"} · {p.default_branch || "main"} · ${Number(p.budget_usd || 0).toFixed(0)}
                      </div>
                      <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            setSelectedProjId(p.project_id);
                            onSelectSubPage("details");
                          }}
                        >
                          Open Workspace
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => {
                            setSelectedProjId(p.project_id);
                            setEditingProj(true);
                            onSelectSubPage("details");
                          }}
                        >
                          <Edit3 size={12} /> Edit
                        </button>
                        {p.status !== "ARCHIVED" && (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() =>
                              setConfirmDialog({
                                title: "Archive Project",
                                message: `Archive '${p.name}'? Existing tasks and files remain preserved.`,
                                confirmLabel: "Archive",
                                fn: async () => {
                                  await apiFetch(`/api/v1/projects/${p.project_id}`, {
                                    method: "PATCH",
                                    body: { status: "ARCHIVED" },
                                  });
                                  pushToast(`Archived '${p.name}'.`, "success");
                                  await load();
                                },
                              })
                            }
                          >
                            <Archive size={12} /> Archive
                          </button>
                        )}
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          aria-label={`Delete ${p.name}`}
                          onClick={() =>
                            setConfirmDialog({
                              title: "Delete Project",
                              message: `Permanently delete '${p.name}' and its activity/deployment history?`,
                              confirmLabel: "Delete Project",
                              fn: async () => {
                                await apiFetch(`/api/v1/projects/${p.project_id}`, { method: "DELETE" });
                                if (selectedProjId === p.project_id) setSelectedProjId("");
                                pushToast(`Deleted '${p.name}'.`, "success");
                                await load("");
                              },
                            })
                          }
                        >
                          <Trash2 size={12} />
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 52. PROJECT DETAILS & TASK BOARD */}
      {page.id === "details" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {!selectedProject ? (
            <EmptyState
              title="No Project Selected"
              description="Create or select a project in Projects Overview."
              action={
                <button type="button" className="btn btn-sm" onClick={() => onSelectSubPage("overview")}>
                  Go to Projects Overview
                </button>
              }
            />
          ) : (
            <>
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
                  <div>
                    <div className="eyebrow-mono">{selectedProject.project_id} · OWNER: {selectedProject.created_by}</div>
                    <h3 style={{ margin: "4px 0" }}>{selectedProject.name}</h3>
                    <div className="muted">{selectedProject.description || "No description provided."}</div>
                  </div>
                  <div className="row" style={{ gap: 8 }}>
                    <StatusIndicator label={selectedProject.status || "ACTIVE"} tone={projectTone(selectedProject.status)} />
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditingProj((v) => !v)}>
                      <Edit3 size={13} /> {editingProj ? "Close Editor" : "Edit Project"}
                    </button>
                  </div>
                </div>

                {/* Progress Bar from real tasks */}
                <div>
                  <div className="row-between" style={{ fontSize: 12, marginBottom: 6 }}>
                    <span className="muted">Task Completion Progress</span>
                    <span className="mono">{completedTaskCount}/{projectTasks.length} tasks ({projectProgressPct}%)</span>
                  </div>
                  <div style={{ height: 8, borderRadius: 999, background: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                    <div style={{ width: `${projectProgressPct}%`, height: "100%", background: "var(--accent, #22d3ee)", transition: "width 0.25s ease" }} />
                  </div>
                </div>

                {editingProj && (
                  <form onSubmit={saveProjectEdit} style={{ display: "flex", flexDirection: "column", gap: 10, paddingTop: 10, borderTop: "1px solid var(--border-subtle, rgba(255,255,255,0.1))" }}>
                    <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                      <input className="input" style={{ flex: 2 }} value={editProjName} onChange={(e) => setEditProjName(e.target.value)} placeholder="Project Name" required />
                      <select className="select" style={{ flex: 1 }} value={editProjStatus} onChange={(e) => setEditProjStatus(e.target.value)}>
                        <option value="ACTIVE">ACTIVE</option>
                        <option value="PAUSED">PAUSED</option>
                        <option value="COMPLETED">COMPLETED</option>
                        <option value="ARCHIVED">ARCHIVED</option>
                      </select>
                      <input className="input" type="number" style={{ width: 110 }} value={editProjBudget} onChange={(e) => setEditProjBudget(e.target.value)} placeholder="Budget $" />
                    </div>
                    <input className="input" value={editProjDesc} onChange={(e) => setEditProjDesc(e.target.value)} placeholder="Description" />
                    <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                      <input className="input" style={{ flex: 2 }} value={editProjRepo} onChange={(e) => setEditProjRepo(e.target.value)} placeholder="owner/repo" />
                      <input className="input" style={{ flex: 1 }} value={editProjBranch} onChange={(e) => setEditProjBranch(e.target.value)} placeholder="default branch" />
                      <button type="submit" className="btn btn-sm"><Save size={13} /> Save Changes</button>
                    </div>
                  </form>
                )}
              </div>

              {/* Task Board & Agent Assignment */}
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
                  <span><strong>Project Tasks &amp; Milestones ({projectTasks.length})</strong></span>
                  <div className="row" style={{ gap: 6 }}>
                    <button type="button" className={`seg-btn ${taskView === "board" ? "active" : ""}`} onClick={() => setTaskView("board")}>
                      <LayoutGrid size={12} /> Board
                    </button>
                    <button type="button" className={`seg-btn ${taskView === "list" ? "active" : ""}`} onClick={() => setTaskView("list")}>
                      <List size={12} /> List
                    </button>
                    <button type="button" className={`seg-btn ${taskView === "timeline" ? "active" : ""}`} onClick={() => setTaskView("timeline")}>
                      <Layers size={12} /> Timeline
                    </button>
                  </div>
                </div>

                <form onSubmit={createProjectTask} className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                  <input
                    className="input"
                    style={{ flex: 2, minWidth: 180 }}
                    value={taskTitle}
                    onChange={(e) => setTaskTitle(e.target.value)}
                    placeholder="New task or milestone title..."
                    required
                  />
                  <input
                    className="input"
                    style={{ flex: 2, minWidth: 180 }}
                    value={taskObjective}
                    onChange={(e) => setTaskObjective(e.target.value)}
                    placeholder="Execution objective (optional)"
                  />
                  <select className="select" style={{ flex: 1, minWidth: 150 }} value={taskAgent} onChange={(e) => setTaskAgent(e.target.value)} aria-label="Assign Specialist Agent">
                    {agents.length > 0 ? (
                      agents.map((a) => (
                        <option key={a.agent_id} value={a.agent_id}>
                          {a.agent_id} · {a.name}
                        </option>
                      ))
                    ) : (
                      <option value="AGT-02">AGT-02 · Engineering</option>
                    )}
                  </select>
                  <button type="submit" className="btn btn-sm"><Plus size={13} /> Add Task</button>
                </form>

                {projectTasks.length === 0 ? (
                  <EmptyState title="No Project Tasks Yet" description="Add a task above to assign work to an authorized specialist agent." />
                ) : taskView === "board" ? (
                  <div className="grid-4" style={{ alignItems: "start" }}>
                    {[
                      { key: "queued", label: "Queued / Planned", match: (s: string) => ["CREATED", "PLANNED", "QUEUED"].includes(s) },
                      { key: "active", label: "Running / Approval", match: (s: string) => ["RUNNING", "WAITING_FOR_APPROVAL", "PAUSED"].includes(s) },
                      { key: "done", label: "Completed", match: (s: string) => s === "COMPLETED" },
                      { key: "failed", label: "Failed / Cancelled", match: (s: string) => ["FAILED", "CANCELLED"].includes(s) },
                    ].map((col) => {
                      const items = projectTasks.filter((t) => col.match((t.lifecycle_state || "").toUpperCase()));
                      return (
                        <div key={col.key} style={{ background: "rgba(255,255,255,0.02)", border: "1px solid var(--border-subtle, rgba(255,255,255,0.08))", borderRadius: 10, padding: 10 }}>
                          <div className="eyebrow-mono" style={{ marginBottom: 8 }}>{col.label} ({items.length})</div>
                          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                            {items.map((t) => (
                              <div key={t.task_id} className="list-item" style={{ padding: 10, display: "flex", flexDirection: "column", gap: 6 }}>
                                <strong style={{ fontSize: 13 }}>{t.title}</strong>
                                <div className="muted mono" style={{ fontSize: 11 }}>{t.assigned_agent_id} · {t.lifecycle_state}</div>
                                <div className="row" style={{ gap: 4, flexWrap: "wrap" }}>
                                  {["CREATED", "PLANNED", "QUEUED"].includes(t.lifecycle_state) && (
                                    <button type="button" className="btn btn-sm" onClick={() => runTaskAction(t.task_id, "execute")}><Play size={11} /></button>
                                  )}
                                  {t.lifecycle_state === "RUNNING" && (
                                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => runTaskAction(t.task_id, "pause")}><Pause size={11} /></button>
                                  )}
                                  {t.lifecycle_state === "PAUSED" && (
                                    <button type="button" className="btn btn-sm" onClick={() => runTaskAction(t.task_id, "resume")}><Play size={11} /></button>
                                  )}
                                  {t.lifecycle_state === "FAILED" && (
                                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => runTaskAction(t.task_id, "retry")}><RotateCcw size={11} /></button>
                                  )}
                                  {!["COMPLETED", "CANCELLED"].includes(t.lifecycle_state) && (
                                    <button type="button" className="btn btn-danger btn-sm" onClick={() => runTaskAction(t.task_id, "cancel")}><XCircle size={11} /></button>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                ) : taskView === "list" ? (
                  <DataTable
                    rows={projectTasks}
                    rowKey={(t) => t.task_id}
                    emptyTitle="No Tasks"
                    emptyDescription="Add a task above."
                    columns={[
                      { key: "title", header: "Task", render: (t) => <strong>{t.title}</strong> },
                      { key: "agent", header: "Agent", mono: true, render: (t) => t.assigned_agent_id },
                      { key: "state", header: "Status", render: (t) => <StatusIndicator label={t.lifecycle_state} tone={taskTone(t.lifecycle_state)} /> },
                      { key: "prog", header: "Progress", mono: true, render: (t) => `${t.progress_percent ?? 0}%` },
                    ]}
                  />
                ) : (
                  <ActivityFeed
                    emptyLabel="No timeline events."
                    items={projectTasks.map((t) => ({
                      id: t.task_id,
                      title: `${t.title} (${t.assigned_agent_id})`,
                      actor: t.assigned_agent_id,
                      status: t.lifecycle_state,
                      timestamp: t.updated_at || t.created_at,
                    }))}
                  />
                )}
              </div>

              {/* Project Documents + NEON Intelligence */}
              <div className="grid-2">
                <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div className="card-title">
                    <span><FileText size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Project Documents ({projectFiles.length})</span>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("files", "upload")}>
                      Open File Hub
                    </button>
                  </div>
                  <div className="row" style={{ gap: 8 }}>
                    <select className="select" style={{ flex: 1 }} value={attachFileId} onChange={(e) => setAttachFileId(e.target.value)} aria-label="Attach existing file">
                      <option value="">Select File Hub document to attach...</option>
                      {allFiles
                        .filter((f) => f.project_id !== selectedProjId)
                        .map((f) => (
                          <option key={f.file_id} value={f.file_id}>
                            {f.filename} ({f.folder || "general"})
                          </option>
                        ))}
                    </select>
                    <button
                      type="button"
                      className="btn btn-sm"
                      disabled={!attachFileId}
                      onClick={async () => {
                        if (!attachFileId) return;
                        await apiFetch(`/api/v1/files/${attachFileId}`, {
                          method: "PATCH",
                          body: { project_id: selectedProjId },
                        });
                        setAttachFileId("");
                        pushToast("File attached to project.", "success");
                        await load();
                      }}
                    >
                      Attach
                    </button>
                  </div>
                  {projectFiles.length === 0 ? (
                    <EmptyState title="No Attached Files" description="Attach files from File Hub above to give NEON and agents project context." />
                  ) : (
                    projectFiles.map((f) => (
                      <div key={f.file_id} className="list-item row-between" style={{ gap: 8 }}>
                        <div>
                          <strong>{f.filename}</strong>
                          <div className="muted mono" style={{ fontSize: 11 }}>{f.folder || "general"} · {f.mime_type}</div>
                        </div>
                        <div className="row" style={{ gap: 4 }}>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={() => {
                              onAttachFileToNeon?.({
                                file_id: f.file_id,
                                filename: f.filename,
                                mime_type: f.mime_type,
                                is_image: Boolean(f.is_image),
                                size_bytes: f.size_bytes,
                              });
                              onSendToNeon?.(`Analyze '${f.filename}' in the context of project '${selectedProject.name}'.`);
                              onNavigate("neon", "chat");
                            }}
                          >
                            <Sparkles size={12} /> NEON
                          </button>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            onClick={async () => {
                              await apiFetch(`/api/v1/files/${f.file_id}`, {
                                method: "PATCH",
                                body: { clear_project: true },
                              });
                              pushToast("File detached from project.", "info");
                              await load();
                            }}
                          >
                            Detach
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>

                <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  <div className="card-title">
                    <span><Sparkles size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />NEON Project Intelligence</span>
                  </div>
                  <form onSubmit={askNeonAboutProject} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                    <textarea
                      className="textarea"
                      rows={3}
                      value={neonPlanPrompt}
                      onChange={(e) => setNeonPlanPrompt(e.target.value)}
                      placeholder="Ask NEON to generate a project plan, summarize deliverables, or identify blockers..."
                    />
                    <button type="submit" className="btn btn-sm" disabled={neonPlanning}>
                      {neonPlanning ? "Analyzing with NEON..." : "Ask NEON with Project Context"}
                    </button>
                  </form>
                  {neonPlanResult && (
                    <ReadableSummary
                      title="NEON Project Analysis"
                      data={neonPlanResult}
                      diagnosticsTitle="Technical Diagnostics — NEON Response"
                    />
                  )}
                </div>
              </div>

              {/* AST Analyzer */}
              <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div className="card-title">
                  <span>Python AST Code Analyzer</span>
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={async () => {
                      try {
                        const res = await apiFetch<any>(`/api/v1/projects/${selectedProjId}/analyze`, {
                          method: "POST",
                          body: { filename: analyzeFilename.trim() || "module.py", source_code: analyzeSource },
                        });
                        setAnalysisResult(res);
                        pushToast("AST analysis completed.", "success");
                      } catch (err: any) {
                        pushToast(err.message, "error");
                      }
                    }}
                  >
                    <Play size={13} /> Run AST Analysis
                  </button>
                </div>
                <input className="input mono" value={analyzeFilename} onChange={(e) => setAnalyzeFilename(e.target.value)} placeholder="Filename (e.g., app/main.py)" />
                <textarea className="textarea mono" rows={4} value={analyzeSource} onChange={(e) => setAnalyzeSource(e.target.value)} />
                {analysisResult && (
                  <ReadableSummary title="AST Analysis Summary" data={analysisResult} diagnosticsTitle="Technical Diagnostics — AST Payload" />
                )}
              </div>
            </>
          )}
        </div>
      )}

      {/* 53. FORGE CODING WORKSPACE & LIVE PREVIEW */}
      {page.id === "coding" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="grid-2">
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="card-title">
                <span><Code2 size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />FORGE Code Editor &amp; File Tree</span>
                <div className="row" style={{ gap: 6 }}>
                  {selectedForge && (
                    <>
                      <button
                        type="button"
                        className="btn btn-sm"
                        disabled={!forgeDirty}
                        onClick={() =>
                          setConfirmDialog({
                            title: "Save & Re-Verify FORGE Workspace",
                            message: "Save your proposed code edits and run AEGIS static security verification?",
                            confirmLabel: "Save & Verify",
                            fn: saveForgeEdits,
                          })
                        }
                      >
                        <Save size={13} /> {forgeDirty ? "Save Proposed Changes" : "Saved"}
                      </button>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => openForgePreview(selectedForge.forge_id)}>
                        <Eye size={13} /> Preview
                      </button>
                      {selectedForge.archive_download_url && (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => downloadAuthFile(selectedForge.archive_download_url, `${selectedForge.name}.zip`).catch((e) => pushToast(e.message, "error"))}
                        >
                          <Download size={13} /> ZIP
                        </button>
                      )}
                    </>
                  )}
                </div>
              </div>

              <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                {forgeProjects.map((fp) => (
                  <button
                    key={fp.forge_id}
                    type="button"
                    className={`seg-btn ${selectedForge?.forge_id === fp.forge_id ? "active" : ""}`}
                    onClick={() => openForgeWorkspace(fp.forge_id)}
                  >
                    {fp.name}
                  </button>
                ))}
              </div>

              {selectedForge?.files ? (
                <>
                  <div className="row-between" style={{ fontSize: 12 }}>
                    <StatusIndicator label={selectedForge.status || "VERIFIED"} tone={selectedForge.status === "VERIFIED" ? "success" : "warn"} />
                    <span className="muted mono">
                      {forgeDirty ? "PROPOSED EDITS (UNSAVED)" : "AEGIS-VERIFIED SAVED STATE"}
                    </span>
                  </div>
                  <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                    {Object.keys(editedForgeFiles).map((fn) => (
                      <button
                        key={fn}
                        type="button"
                        className={`seg-btn ${activeForgeFile === fn ? "active" : ""}`}
                        onClick={() => setActiveForgeFile(fn)}
                      >
                        {fn}{editedForgeFiles[fn] !== selectedForge.files[fn] ? " *" : ""}
                      </button>
                    ))}
                  </div>
                  <textarea
                    className="textarea mono"
                    rows={12}
                    aria-label="FORGE Code Editor"
                    value={editedForgeFiles[activeForgeFile] || ""}
                    onChange={(e) => setEditedForgeFiles((prev) => ({ ...prev, [activeForgeFile]: e.target.value }))}
                  />
                </>
              ) : (
                <EmptyState
                  title="No FORGE Workspace Open"
                  description="Select a workspace above or generate a new one in Code Generation."
                  action={
                    <button type="button" className="btn btn-sm" onClick={() => onSelectSubPage("generation")}>
                      Generate Workspace
                    </button>
                  }
                />
              )}
            </div>

            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="card-title"><span>Sandboxed Live Preview &amp; Build Diagnostics</span></div>
              {previewHtml ? (
                <iframe
                  title="FORGE Live Preview"
                  sandbox="allow-scripts"
                  srcDoc={previewHtml}
                  style={{ width: "100%", height: 320, border: "1px solid var(--border)", borderRadius: 8, background: "#fff" }}
                />
              ) : (
                <EmptyState title="Preview Idle" description="Click 'Preview' on any FORGE workspace." />
              )}
              {selectedForge?.build_logs && (
                <div>
                  <div className="eyebrow-mono" style={{ marginBottom: 4 }}>BUILD &amp; AEGIS LOGS</div>
                  <pre className="code-block" style={{ maxHeight: 140, overflow: "auto", fontSize: 11 }}>
                    {(selectedForge.build_logs || []).join("\n")}
                  </pre>
                </div>
              )}
            </div>
          </div>

          {selectedProjId && (
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="card-title"><span>Agent-Assisted Code Proposal (Review Required)</span></div>
              <form onSubmit={submitCodeProposal} className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                <input
                  className="input"
                  style={{ flex: 2, minWidth: 200 }}
                  value={proposalSpec}
                  onChange={(e) => setProposalSpec(e.target.value)}
                  placeholder="Describe the feature, refactor, or fix to propose..."
                />
                <input
                  className="input mono"
                  style={{ flex: 1, minWidth: 140 }}
                  value={proposalBranch}
                  onChange={(e) => setProposalBranch(e.target.value)}
                  placeholder="Target branch"
                />
                <button type="submit" className="btn btn-sm">Generate Proposed Change</button>
              </form>
              {proposalResult && (
                <ReadableSummary
                  title="Proposed Code Change (Unapplied)"
                  data={proposalResult}
                  diagnosticsTitle="Technical Diagnostics — Code Proposal"
                />
              )}
            </div>
          )}
        </div>
      )}

      {/* 54. CODE GENERATION */}
      {page.id === "generation" && (
        <div className="card" style={{ maxWidth: 720 }}>
          <div className="card-title"><span>FORGE Application &amp; Code Generator</span></div>
          <form onSubmit={generateForge} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <input className="input" style={{ flex: 2 }} value={forgeName} onChange={(e) => setForgeName(e.target.value)} placeholder="Workspace Name" required />
              <select className="select" style={{ flex: 1 }} value={forgeTemplate} onChange={(e) => setForgeTemplate(e.target.value)}>
                <option value="web_app">Web Application</option>
                <option value="react_vite">React + Vite</option>
                <option value="dashboard">Telemetry Dashboard</option>
                <option value="landing_page">Landing Page</option>
                <option value="fastapi_service">FastAPI Service</option>
              </select>
            </div>
            <textarea className="textarea" rows={4} value={forgePrompt} onChange={(e) => setForgePrompt(e.target.value)} required />
            <button type="submit" className="btn">Generate &amp; Verify FORGE Project</button>
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
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {repoInfo && (
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div className="card-title">
                <span><FolderGit2 size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Active Checkout &amp; Branch Diagnostics</span>
                <StatusIndicator label={repoInfo.local_git?.branch || selectedProject?.default_branch || "main"} tone="info" />
              </div>
              {repoInfo.local_git?.recent_commits && (
                <pre className="code-block" style={{ fontSize: 12 }}>
                  {(repoInfo.local_git.recent_commits || []).join("\n")}
                </pre>
              )}
              <TechnicalDiagnostics title="Technical Diagnostics — Repository Metadata" data={repoInfo} />
            </div>
          )}

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
        </div>
      )}

      {/* 57. DEVELOPMENT ACTIVITY */}
      {page.id === "dev-activity" && (
        <div className="card">
          <div className="card-title"><span>Engineering Activity Trail ({activity.length})</span></div>
          <ActivityFeed
            emptyLabel="No project activity recorded yet."
            items={activity.map((a, idx) => ({
              id: a.activity_id || String(idx),
              title: a.summary || a.action || a.activity_type || "Project Event",
              actor: a.actor || "FORGE",
              status: a.activity_type || a.status || "RECORDED",
              timestamp: a.created_at,
            }))}
          />
        </div>
      )}

      {/* 58. DEPLOYMENT HISTORY */}
      {page.id === "deployments" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {selectedProjId && (
            <div className="card">
              <div className="card-title"><span>Request ApprovalGate-Governed Deployment</span></div>
              <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                <select className="select" value={deployEnv} onChange={(e) => setDeployEnv(e.target.value as any)}>
                  <option value="staging">staging</option>
                  <option value="production">production</option>
                </select>
                <input className="input mono" style={{ flex: 1 }} value={deployRef} onChange={(e) => setDeployRef(e.target.value)} placeholder="Git ref or commit SHA" />
                <input className="input" style={{ flex: 2 }} value={deployNotes} onChange={(e) => setDeployNotes(e.target.value)} placeholder="Release notes" />
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() =>
                    setConfirmDialog({
                      title: `Request ${deployEnv.toUpperCase()} Deployment`,
                      message: `Submit a deployment request for '${deployRef}' to ${deployEnv}? ApprovalGate sign-off is required.`,
                      confirmLabel: "Submit Request",
                      fn: async () => {
                        await apiFetch(`/api/v1/projects/${selectedProjId}/deployments`, {
                          method: "POST",
                          body: { environment: deployEnv, git_ref: deployRef.trim() || "main", notes: deployNotes.trim() },
                        });
                        setDeployNotes("");
                        pushToast("Deployment submitted to ApprovalGate.", "success");
                        await load();
                      },
                    })
                  }
                >
                  <CheckCircle2 size={13} /> Request Deployment
                </button>
              </div>
            </div>
          )}

          <div className="card">
            <div className="card-title"><span>Deployment History ({deployments.length})</span></div>
            <DataTable
              rows={deployments}
              rowKey={(d, i) => d.deployment_id || String(i)}
              emptyTitle="No Deployments Recorded"
              emptyDescription="Project deployments and ApprovalGate rollbacks appear here."
              columns={[
                { key: "env", header: "Environment", mono: true, render: (d) => d.environment || "staging" },
                { key: "ref", header: "Git Ref", mono: true, render: (d) => d.git_ref || "main" },
                { key: "status", header: "Status", render: (d) => <StatusIndicator label={d.status || "READY"} tone={d.status === "READY" ? "success" : "info"} /> },
                {
                  key: "rb",
                  header: "Rollback",
                  render: (d) => (
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={() =>
                        setConfirmDialog({
                          title: "Request Deployment Rollback",
                          message: "Submit an ApprovalGate-governed rollback request for this deployment?",
                          confirmLabel: "Request Rollback",
                          fn: async () => {
                            await apiFetch(`/api/v1/projects/${selectedProjId}/deployments/${d.deployment_id}/rollback`, {
                              method: "POST",
                              body: { reason: "Operator-requested rollback from ULTRON Projects" },
                            });
                            pushToast("Rollback submitted to ApprovalGate.", "success");
                            await load();
                          },
                        })
                      }
                    >
                      <RotateCcw size={12} /> Rollback
                    </button>
                  ),
                },
              ]}
            />
          </div>
        </div>
      )}

      <ConfirmationDialog
        open={Boolean(confirmDialog)}
        title={confirmDialog?.title || "Confirm"}
        message={confirmDialog?.message || ""}
        confirmLabel={confirmDialog?.confirmLabel || "Confirm"}
        onCancel={() => setConfirmDialog(null)}
        onConfirm={async () => {
          const fn = confirmDialog?.fn;
          setConfirmDialog(null);
          if (fn) await fn().catch((e) => pushToast(e.message, "error"));
        }}
      />
    </ResponsiveWorkspace>
  );
}
