import React, { useEffect, useMemo, useState } from "react";
import {
  ArrowUp,
  Bug,
  CheckCircle2,
  Code2,
  Download,
  Eye,
  FileCode2,
  FolderGit2,
  Globe,
  History,
  Paperclip,
  Play,
  Plus,
  Save,
  Server,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Terminal,
  X,
} from "lucide-react";
import { apiFetch, downloadAuthFile } from "../../lib/api";
import type { ModuleId } from "../../catalog/navigation";
import {
  ConfirmationDialog,
  EmptyState,
  StatusIndicator,
  useToast,
} from "../ui/DesignSystem";
import { ReadableSummary, TechnicalDiagnostics } from "../ui/HumanPresentation";

type QuickStartKind = "website" | "mobile" | "backend" | "debug";
type WorkbenchTab = "files" | "preview" | "terminal" | "history";

interface QuickStartSpec {
  id: QuickStartKind;
  label: string;
  desc: string;
  template: "web_app" | "react_vite" | "fastapi_service";
  mode: "build" | "debug";
  starterPrompt: string;
  icon: React.ReactNode;
}

const QUICK_STARTS: QuickStartSpec[] = [
  {
    id: "website",
    label: "Website",
    desc: "Responsive web app or landing page",
    template: "web_app",
    mode: "build",
    starterPrompt: "Build a modern, responsive web application with clean navigation, interactive status cards, and dark-mode styling.",
    icon: <Globe size={18} style={{ color: "var(--accent, #22d3ee)" }} />,
  },
  {
    id: "mobile",
    label: "Mobile App",
    desc: "iPhone-first React + Vite PWA",
    template: "react_vite",
    mode: "build",
    starterPrompt: "Build a mobile-first React + Vite PWA interface optimized for iPhone XR with touch-friendly cards and bottom navigation.",
    icon: <Smartphone size={18} style={{ color: "var(--accent, #22d3ee)" }} />,
  },
  {
    id: "backend",
    label: "Backend / API",
    desc: "FastAPI service with health & tests",
    template: "fastapi_service",
    mode: "build",
    starterPrompt: "Build a production-ready FastAPI backend service with typed Pydantic schemas, health endpoint, and pytest unit tests.",
    icon: <Server size={18} style={{ color: "var(--accent, #22d3ee)" }} />,
  },
  {
    id: "debug",
    label: "Debug Code",
    desc: "Diagnose errors with AGT-04 & AEGIS",
    template: "web_app",
    mode: "debug",
    starterPrompt: "Diagnose this error, inspect root cause, and propose a verified fix:\n",
    icon: <Bug size={18} style={{ color: "#fbbf24" }} />,
  },
];

export function CodingAgentWorkspace({
  agent,
  manifest,
  onExecutionComplete,
}: {
  agent: any;
  manifest: any;
  onNavigate?: (moduleId: ModuleId, subPageId?: string) => void;
  onExecutionComplete?: () => void;
}) {
  const { pushToast } = useToast();
  const [activeSession, setActiveSession] = useState(false);
  const [mode, setMode] = useState<"build" | "debug">("build");
  const [template, setTemplate] = useState<"web_app" | "react_vite" | "fastapi_service">("web_app");
  const [prompt, setPrompt] = useState("");
  const [followUpPrompt, setFollowUpPrompt] = useState("");

  // Context attachments
  const [projects, setProjects] = useState<any[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<Array<{ file_id: string; filename: string }>>([]);
  const [uploading, setUploading] = useState(false);

  // Live backend state
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [messages, setMessages] = useState<Array<{ role: "user" | "agent"; text: string; meta?: any }>>([]);
  const [argonTask, setArgonTask] = useState<any>(null);
  const [forgeWorkspace, setForgeWorkspace] = useState<any>(null);
  const [editedFiles, setEditedFiles] = useState<Record<string, string>>({});
  const [activeFile, setActiveFile] = useState("");
  const [previewHtml, setPreviewHtml] = useState("");
  const [aegisScan, setAegisScan] = useState<any>(null);
  const [workbenchTab, setWorkbenchTab] = useState<WorkbenchTab>("files");

  // History
  const [recentConversations, setRecentConversations] = useState<any[]>([]);
  const [recentForge, setRecentForge] = useState<any[]>([]);
  const [recentTasks, setRecentTasks] = useState<any[]>([]);

  // Confirmation dialog for saving proposed edits
  const [confirmSaveOpen, setConfirmSaveOpen] = useState(false);

  const isDirty = useMemo(() => {
    if (!forgeWorkspace?.files) return false;
    return Object.keys(editedFiles).some((k) => editedFiles[k] !== forgeWorkspace.files[k]);
  }, [forgeWorkspace, editedFiles]);

  async function loadHistory() {
    const [pRes, cRes, fRes, tRes] = await Promise.all([
      apiFetch<any>("/api/v1/projects").catch(() => ({ projects: [] })),
      apiFetch<any>("/api/v1/neon/conversations").catch(() => ({ conversations: [] })),
      apiFetch<any>("/api/v1/forge/projects").catch(() => ({ projects: [] })),
      apiFetch<any>("/api/v1/tasks?limit=15").catch(() => ({ tasks: [] })),
    ]);
    setProjects(pRes.projects || []);
    setRecentConversations((cRes.conversations || []).filter((c: any) => !c.agent_id || c.agent_id === "AGT-03").slice(0, 6));
    setRecentForge((fRes.projects || []).slice(0, 6));
    setRecentTasks((tRes.tasks || []).filter((t: any) => ["AGT-03", "AGT-04", "AGT-25"].includes(t.assigned_agent_id)).slice(0, 8));
  }

  useEffect(() => {
    loadHistory();
  }, []);

  async function handleFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("folder", "coding");
      if (selectedProjectId) fd.append("project_id", selectedProjectId);
      const res = await apiFetch<any>("/api/v1/files/upload", {
        method: "POST",
        body: fd,
        isFormData: true,
      });
      setAttachedFiles((prev) => [...prev, { file_id: res.file_id, filename: res.filename }]);
      pushToast(`Attached '${res.filename}' (AEGIS scanned).`, "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    } finally {
      setUploading(false);
    }
  }

  async function openExistingForge(forgeId: string) {
    try {
      const full = await apiFetch<any>(`/api/v1/forge/projects/${forgeId}`);
      setForgeWorkspace(full);
      setEditedFiles({ ...(full.files || {}) });
      const first = Object.keys(full.files || {})[0] || "";
      setActiveFile(first);
      setPreviewHtml(full.preview_html || "");
      setActiveSession(true);
      setWorkbenchTab("files");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function resumeConversation(convId: string) {
    try {
      const detail = await apiFetch<any>(`/api/v1/neon/conversations/${convId}`);
      setConversationId(convId);
      const msgs = (detail.messages || []).map((m: any) => ({
        role: m.role === "user" ? ("user" as const) : ("agent" as const),
        text: m.content || "",
        meta: m,
      }));
      setMessages(msgs);
      setActiveSession(true);
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function runCodingObjective(objectiveText: string, isFollowUp = false) {
    const clean = objectiveText.trim();
    if (!clean) return;
    setError("");
    setRunning(true);
    setActiveSession(true);
    setMessages((prev) => [...prev, { role: "user", text: clean }]);
    if (!isFollowUp) setPrompt("");
    else setFollowUpPrompt("");

    try {
      const projObj = projects.find((p) => p.project_id === selectedProjectId);
      const fullPrompt = projObj
        ? `[Project: ${projObj.name} | Repo: ${projObj.repo_full_name || "local"}]\n${clean}`
        : clean;

      // 1. NEON Intelligence conversation (persisted)
      let cid = conversationId;
      if (!cid) {
        const conv = await apiFetch<any>("/api/v1/neon/conversations", {
          method: "POST",
          body: { title: clean.slice(0, 64), agent_id: "AGT-03" },
        });
        cid = conv.conversation_id;
        setConversationId(cid);
      }
      const msgRes = await apiFetch<any>(`/api/v1/neon/conversations/${cid}/messages`, {
        method: "POST",
        body: {
          content: fullPrompt,
          agent_id: mode === "debug" ? "AGT-04" : "AGT-03",
          file_ids: attachedFiles.map((f) => f.file_id),
        },
      });
      const assistantMsg = msgRes.assistant_message || msgRes.message || msgRes;
      setMessages((prev) => [
        ...prev,
        {
          role: "agent",
          text: assistantMsg.content || msgRes.output || "Execution recorded.",
          meta: assistantMsg,
        },
      ]);

      // 2. ARGON Multi-Agent DAG Orchestration (AGT-01 -> AGT-03/AGT-04 -> AGT-25)
      const createdTask = await apiFetch<any>("/api/v1/tasks", {
        method: "POST",
        body: {
          title: clean.slice(0, 90),
          objective: fullPrompt,
          preferred_agent_id: mode === "debug" ? "AGT-04" : "AGT-03",
          project_id: selectedProjectId || undefined,
        },
      });
      const executedTask = await apiFetch<any>(`/api/v1/tasks/${createdTask.task_id}/execute`, {
        method: "POST",
      });
      setArgonTask(executedTask);

      // 3. FORGE Multi-File Workspace + AEGIS Verification (on initial build or when no workspace open)
      if (mode === "build" && (!forgeWorkspace || !isFollowUp)) {
        const shortName = clean.replace(/[^a-zA-Z0-9 ]/g, "").trim().slice(0, 36) || "ULTRON App";
        const frg = await apiFetch<any>("/api/v1/forge/projects", {
          method: "POST",
          body: {
            name: shortName,
            template,
            prompt: clean,
          },
        });
        setForgeWorkspace(frg);
        setEditedFiles({ ...(frg.files || {}) });
        setActiveFile(Object.keys(frg.files || {})[0] || "");
        setPreviewHtml(frg.preview_html || "");
        setWorkbenchTab(frg.preview_html ? "preview" : "files");
      }

      onExecutionComplete?.();
      await loadHistory();
      pushToast("NEON, ARGON & FORGE coding workflow completed.", "success");
    } catch (err: any) {
      setError(err.message);
      pushToast(err.message, "error");
    } finally {
      setRunning(false);
    }
  }

  async function saveProposedChanges() {
    if (!forgeWorkspace) return;
    try {
      const updated = await apiFetch<any>(`/api/v1/forge/projects/${forgeWorkspace.forge_id}`, {
        method: "PATCH",
        body: { files: editedFiles },
      });
      setForgeWorkspace(updated);
      setEditedFiles({ ...(updated.files || {}) });
      setPreviewHtml(updated.preview_html || "");
      pushToast(`Proposed changes saved & AEGIS-verified (${updated.status}).`, "success");
      await loadHistory();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function runAegisScan() {
    const code = editedFiles[activeFile] || "";
    if (!code.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/aegis/scan-code", {
        method: "POST",
        body: { code, language: activeFile.endsWith(".py") ? "python" : "typescript" },
      });
      setAegisScan(res);
      setWorkbenchTab("terminal");
      pushToast("AEGIS static security scan completed.", "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  // --- LANDING EXPERIENCE (REPLIT-INSPIRED, ULTRON-NATIVE) ---
  if (!activeSession) {
    return (
      <div className="coding-landing" data-testid="coding-agent-landing">
        <div className="coding-landing-inner">
          <div className="row" style={{ gap: 8, justifyContent: "center", flexWrap: "wrap" }}>
            <span className="pill pill-cyan mono">AGT-03 · {manifest?.name || agent?.name || "Coding Agent"}</span>
            <span className="pill mono">NEON + ARGON + FORGE + AEGIS</span>
          </div>

          <h1 className="coding-hero-title">What are we building?</h1>
          <p className="coding-hero-subtitle">
            Describe your idea. I’ll help turn it into working software.
          </p>

          <form
            className="coding-composer"
            onSubmit={(e) => {
              e.preventDefault();
              runCodingObjective(prompt, false);
            }}
          >
            <textarea
              id="coding-landing-prompt"
              className="coding-composer-input"
              rows={3}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Describe what you want to build…"
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  runCodingObjective(prompt, false);
                }
              }}
            />

            {attachedFiles.length > 0 && (
              <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                {attachedFiles.map((f) => (
                  <span key={f.file_id} className="pill mono" style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
                    {f.filename}
                    <button
                      type="button"
                      aria-label={`Remove ${f.filename}`}
                      style={{ background: "none", border: 0, color: "inherit", cursor: "pointer", padding: 0 }}
                      onClick={() => setAttachedFiles((prev) => prev.filter((x) => x.file_id !== f.file_id))}
                    >
                      <X size={11} />
                    </button>
                  </span>
                ))}
              </div>
            )}

            <div className="coding-composer-toolbar">
              <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                <label className="btn btn-secondary btn-sm" style={{ cursor: "pointer" }}>
                  <Paperclip size={13} /> {uploading ? "Uploading..." : "Attach"}
                  <input
                    type="file"
                    accept="image/*,.pdf,.txt,.md,.json,.py,.ts,.tsx,.js,.csv"
                    style={{ display: "none" }}
                    onChange={handleFileUpload}
                  />
                </label>

                {projects.length > 0 && (
                  <select
                    className="select"
                    aria-label="Project Context"
                    value={selectedProjectId}
                    onChange={(e) => setSelectedProjectId(e.target.value)}
                    style={{ maxWidth: 180, padding: "5px 10px", fontSize: 12 }}
                  >
                    <option value="">No Project Context</option>
                    {projects.map((p) => (
                      <option key={p.project_id} value={p.project_id}>
                        {p.name}
                      </option>
                    ))}
                  </select>
                )}

                <span className="pill mono" style={{ fontSize: 11 }}>
                  {mode === "debug" ? "Debug Mode (AGT-04)" : `Template: ${template}`}
                </span>
              </div>

              <button
                id="coding-landing-submit"
                type="submit"
                className="btn btn-sm"
                disabled={running || !prompt.trim()}
                style={{ borderRadius: 999, padding: "8px 16px" }}
              >
                <ArrowUp size={14} /> {running ? "Building..." : "Start Building"}
              </button>
            </div>
          </form>

          {/* 4 Quick-Start Actions */}
          <div className="coding-quickstart-grid">
            {QUICK_STARTS.map((qs) => (
              <button
                key={qs.id}
                id={`coding-quickstart-${qs.id}`}
                type="button"
                className="coding-quickstart-btn"
                onClick={() => {
                  setMode(qs.mode);
                  setTemplate(qs.template);
                  setPrompt(qs.starterPrompt);
                  pushToast(`${qs.label} context loaded.`, "info");
                }}
              >
                {qs.icon}
                <strong style={{ fontSize: 13.5 }}>{qs.label}</strong>
                <span className="muted" style={{ fontSize: 11.5, lineHeight: 1.35 }}>{qs.desc}</span>
              </button>
            ))}
          </div>

          {/* Continue Existing Session */}
          {(recentConversations.length > 0 || recentForge.length > 0) && (
            <div className="card" style={{ width: "100%", textAlign: "left", marginTop: 8 }}>
              <div className="card-title">
                <span><History size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Continue Recent Coding Session</span>
              </div>
              <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                {recentForge.slice(0, 3).map((fp) => (
                  <button key={fp.forge_id} type="button" className="btn btn-secondary btn-sm" onClick={() => openExistingForge(fp.forge_id)}>
                    <Code2 size={12} /> {fp.name}
                  </button>
                ))}
                {recentConversations.slice(0, 3).map((c) => (
                  <button key={c.conversation_id} type="button" className="btn btn-secondary btn-sm" onClick={() => resumeConversation(c.conversation_id)}>
                    <Sparkles size={12} /> {c.title || c.conversation_id}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  // --- ACTIVE CODING WORKSPACE ---
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }} data-testid="coding-agent-workbench">
      {/* Top Action Bar */}
      <div className="card row-between" style={{ flexWrap: "wrap", gap: 10, padding: "12px 14px" }}>
        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              setActiveSession(false);
              setError("");
            }}
          >
            <Plus size={13} /> New Idea
          </button>
          <span className="pill pill-cyan mono">AGT-03 Coding Workspace</span>
          {argonTask && (
            <StatusIndicator
              label={`ARGON: ${argonTask.verification?.outcome_classification || argonTask.lifecycle_state}`}
              tone={argonTask.lifecycle_state === "COMPLETED" ? "success" : "info"}
            />
          )}
          {forgeWorkspace && (
            <StatusIndicator
              label={isDirty ? "PROPOSED EDITS (UNSAVED)" : `FORGE: ${forgeWorkspace.status}`}
              tone={isDirty ? "warn" : forgeWorkspace.status === "VERIFIED" ? "success" : "danger"}
            />
          )}
        </div>

        <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
          {forgeWorkspace && isDirty && (
            <button type="button" className="btn btn-sm" onClick={() => setConfirmSaveOpen(true)}>
              <Save size={13} /> Approve &amp; Save Changes
            </button>
          )}
          {activeFile && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={runAegisScan}>
              <ShieldCheck size={13} /> AEGIS Scan
            </button>
          )}
          {forgeWorkspace?.archive_download_url && (
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => downloadAuthFile(forgeWorkspace.archive_download_url, `${forgeWorkspace.name}.zip`).catch((e) => pushToast(e.message, "error"))}
            >
              <Download size={13} /> ZIP
            </button>
          )}
        </div>
      </div>

      {error && <div className="alert-box" style={{ borderColor: "var(--danger, #f87171)" }}>{error}</div>}

      <div className="coding-workbench-grid">
        {/* Left: Live Agent Activity, Plan & Conversation */}
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title">
            <span><Sparkles size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Live Agent Activity &amp; Plan</span>
            {running && <StatusIndicator label="EXECUTING" tone="info" />}
          </div>

          {/* ARGON Multi-Agent DAG Steps */}
          {argonTask?.steps && (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <div className="eyebrow-mono">ARGON WORKFLOW ({argonTask.steps.length} STEPS)</div>
              {argonTask.steps.map((s: any) => (
                <div key={s.step_id} className="list-item row-between" style={{ padding: "8px 10px", gap: 8 }}>
                  <div>
                    <strong style={{ fontSize: 12.5 }}>Step {s.step_number} · {s.agent_id}</strong>
                    <div className="muted" style={{ fontSize: 11.5 }}>{s.description}</div>
                  </div>
                  <StatusIndicator label={s.status} tone={s.status === "COMPLETED" ? "success" : "info"} />
                </div>
              ))}
            </div>
          )}

          {/* Conversation Messages */}
          <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 340, overflowY: "auto" }}>
            {messages.map((m, idx) => (
              <div
                key={idx}
                className="list-item"
                style={{
                  borderColor: m.role === "user" ? "rgba(34,211,238,0.28)" : undefined,
                  background: m.role === "user" ? "rgba(34,211,238,0.04)" : undefined,
                }}
              >
                <div className="row-between" style={{ marginBottom: 4 }}>
                  <span className="eyebrow-mono">{m.role === "user" ? "OPERATOR" : "AGT-03 / NEON"}</span>
                  {m.meta?.model_used && <span className="muted mono" style={{ fontSize: 10.5 }}>{m.meta.model_used}</span>}
                </div>
                <div style={{ whiteSpace: "pre-wrap", fontSize: 13, lineHeight: 1.55 }}>{m.text}</div>
              </div>
            ))}
          </div>

          {/* Continue Coding Conversation */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              runCodingObjective(followUpPrompt, true);
            }}
            className="row"
            style={{ gap: 8 }}
          >
            <input
              className="input"
              style={{ flex: 1 }}
              value={followUpPrompt}
              onChange={(e) => setFollowUpPrompt(e.target.value)}
              placeholder="Ask AGT-03 to refine code, add tests, or explain..."
            />
            <button type="submit" className="btn btn-sm" disabled={running || !followUpPrompt.trim()}>
              <Play size={12} /> Send
            </button>
          </form>
        </div>

        {/* Right: Tabbed Workbench (Files & Editor | Preview | Terminal & Tests | History) */}
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
            {[
              { id: "files", label: "Files & Editor", icon: <FileCode2 size={12} /> },
              { id: "preview", label: "Live Preview", icon: <Eye size={12} /> },
              { id: "terminal", label: "Terminal & Tests", icon: <Terminal size={12} /> },
              { id: "history", label: "History", icon: <History size={12} /> },
            ].map((t) => (
              <button
                key={t.id}
                type="button"
                className={`seg-btn ${workbenchTab === t.id ? "active" : ""}`}
                onClick={() => setWorkbenchTab(t.id as WorkbenchTab)}
              >
                {t.icon} {t.label}
              </button>
            ))}
          </div>

          {workbenchTab === "files" && (
            forgeWorkspace?.files ? (
              <div className="coding-file-layout">
                <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <div className="eyebrow-mono" style={{ marginBottom: 4 }}>EXPLORER</div>
                  {Object.keys(editedFiles).map((fn) => (
                    <button
                      key={fn}
                      type="button"
                      className={`seg-btn ${activeFile === fn ? "active" : ""}`}
                      style={{ textAlign: "left", width: "100%", justifyContent: "flex-start" }}
                      onClick={() => setActiveFile(fn)}
                    >
                      {fn}{editedFiles[fn] !== forgeWorkspace.files[fn] ? " *" : ""}
                    </button>
                  ))}
                </div>
                <textarea
                  className="textarea mono"
                  rows={16}
                  aria-label="Coding Agent File Editor"
                  value={editedFiles[activeFile] || ""}
                  onChange={(e) => setEditedFiles((prev) => ({ ...prev, [activeFile]: e.target.value }))}
                />
              </div>
            ) : (
              <EmptyState title="No FORGE Files Loaded" description="Submit a build objective or open a recent FORGE workspace in History." />
            )
          )}

          {workbenchTab === "preview" && (
            previewHtml ? (
              <iframe
                title="Coding Agent Live Preview"
                sandbox="allow-scripts"
                srcDoc={previewHtml}
                style={{ width: "100%", height: 400, border: "1px solid var(--border)", borderRadius: 10, background: "#fff" }}
              />
            ) : (
              <EmptyState title="Preview Unavailable" description="Backend/API or Debug workflows do not render an HTML preview." />
            )
          )}

          {workbenchTab === "terminal" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {forgeWorkspace?.test_results && (
                <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                  <StatusIndicator
                    label={forgeWorkspace.test_results.aegis_passed ? "AEGIS PASSED" : "AEGIS FAILED"}
                    tone={forgeWorkspace.test_results.aegis_passed ? "success" : "danger"}
                  />
                  <span className="pill mono">Files: {forgeWorkspace.test_results.files_generated ?? 0}</span>
                  <span className="pill mono">Preview Ready: {String(Boolean(forgeWorkspace.test_results.preview_ready))}</span>
                </div>
              )}
              {forgeWorkspace?.build_logs && (
                <pre className="code-block" style={{ maxHeight: 220, overflow: "auto", fontSize: 11.5 }}>
                  {(forgeWorkspace.build_logs || []).join("\n")}
                </pre>
              )}
              {aegisScan && (
                <ReadableSummary title="AEGIS Static Scan Result" data={aegisScan} diagnosticsTitle="Technical Diagnostics — AEGIS Scan" />
              )}
              {!forgeWorkspace?.build_logs && !aegisScan && (
                <EmptyState title="Terminal Idle" description="Run a build or AEGIS scan to inspect build logs and test results." />
              )}
            </div>
          )}

          {workbenchTab === "history" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="eyebrow-mono">FORGE WORKSPACES ({recentForge.length})</div>
              {recentForge.map((fp) => (
                <div key={fp.forge_id} className="list-item row-between" style={{ padding: "8px 10px" }}>
                  <div>
                    <strong style={{ fontSize: 12.5 }}>{fp.name}</strong>
                    <div className="muted mono" style={{ fontSize: 11 }}>{fp.template} · {fp.status}</div>
                  </div>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => openExistingForge(fp.forge_id)}>
                    Open
                  </button>
                </div>
              ))}
              <div className="eyebrow-mono" style={{ marginTop: 6 }}>ARGON EXECUTIONS ({recentTasks.length})</div>
              {recentTasks.map((t) => (
                <div key={t.task_id} className="list-item row-between" style={{ padding: "8px 10px" }}>
                  <div>
                    <strong style={{ fontSize: 12.5 }}>{t.title}</strong>
                    <div className="muted mono" style={{ fontSize: 11 }}>{t.assigned_agent_id} · {t.lifecycle_state}</div>
                  </div>
                  <CheckCircle2 size={14} style={{ color: t.lifecycle_state === "COMPLETED" ? "var(--success, #34d399)" : "var(--text-muted)" }} />
                </div>
              ))}
              <TechnicalDiagnostics title="Technical Diagnostics — ARGON Task Payload" data={argonTask || {}} />
            </div>
          )}
        </div>
      </div>

      <ConfirmationDialog
        open={confirmSaveOpen}
        title="Approve & Save Proposed Code Changes"
        message="Apply your edited files to the FORGE workspace and run AEGIS static security verification?"
        confirmLabel="Save & Verify"
        onCancel={() => setConfirmSaveOpen(false)}
        onConfirm={async () => {
          setConfirmSaveOpen(false);
          await saveProposedChanges();
        }}
      />
    </div>
  );
}
