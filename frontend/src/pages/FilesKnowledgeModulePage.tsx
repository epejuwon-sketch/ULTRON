import React, { useEffect, useMemo, useState } from "react";
import {
  Camera,
  Check,
  Copy,
  Download,
  Edit3,
  FileArchive,
  FileCode2,
  FileText,
  Folder,
  FolderPlus,
  Image as ImageIcon,
  Link2,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { apiFetch, downloadAuthFile, fetchAuthBlobUrl } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import {
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

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
const BLOCKED_EXTENSIONS = [".exe", ".bat", ".cmd", ".sh", ".dll", ".msi", ".scr", ".com"];

function formatBytes(bytes: number | undefined): string {
  const n = Number(bytes || 0);
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(2)} MB`;
}

function isImageFile(f: any): boolean {
  return Boolean(f?.is_image || String(f?.mime_type || "").toLowerCase().startsWith("image/"));
}

function isPdfFile(f: any): boolean {
  const mime = String(f?.mime_type || "").toLowerCase();
  const name = String(f?.filename || "").toLowerCase();
  return mime === "application/pdf" || name.endsWith(".pdf");
}

function isArchiveFile(f: any): boolean {
  const mime = String(f?.mime_type || "").toLowerCase();
  const name = String(f?.filename || "").toLowerCase();
  return mime.includes("zip") || name.endsWith(".zip") || name.endsWith(".tar") || name.endsWith(".gz");
}

export default function FilesKnowledgeModulePage({
  subPage,
  onSelectSubPage,
  onNavigate,
  onSendToNeon,
  onAttachFileToNeon,
}: ModulePageProps) {
  const mod = getModule("files");
  const page = getSubPage("files", subPage);
  const { pushToast } = useToast();

  const [files, setFiles] = useState<any[]>([]);
  const [projects, setProjects] = useState<any[]>([]);
  const [folders, setFolders] = useState<string[]>([]);
  const [selectedFolder, setSelectedFolder] = useState<string>("ALL");
  const [typeFilter, setTypeFilter] = useState<"ALL" | "IMAGES" | "DOCS" | "ARCHIVES">("ALL");
  const [sortBy, setSortBy] = useState<"newest" | "name" | "size">("newest");
  const [showDeleted, setShowDeleted] = useState(false);

  const [uploadFolder, setUploadFolder] = useState<string>("general");
  const [uploadProjectId, setUploadProjectId] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [uploadQueue, setUploadQueue] = useState<Array<{ name: string; status: "uploading" | "done" | "error"; detail?: string }>>([]);
  const [dragActive, setDragActive] = useState(false);

  const [storageStatus, setStorageStatus] = useState<any>(null);
  const [driveFiles, setDriveFiles] = useState<any[]>([]);
  const [driveError, setDriveError] = useState("");
  const [memories, setMemories] = useState<any[]>([]);
  const [selectedFile, setSelectedFile] = useState<any>(null);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [signedUrl, setSignedUrl] = useState<any>(null);
  const [memHistory, setMemHistory] = useState<any[]>([]);
  const [error, setError] = useState("");

  // Rename / move folder / attach project state
  const [editingFileId, setEditingFileId] = useState<string | null>(null);
  const [editFilename, setEditFilename] = useState("");
  const [editFolder, setEditFolder] = useState("general");
  const [editProjectId, setEditProjectId] = useState("");

  // Forms & filters
  const [fileSearch, setFileSearch] = useState("");
  const [genName, setGenName] = useState("ultron-brief.md");
  const [genContent, setGenContent] = useState("# ULTRON OS Brief\nGenerated securely inside File Hub.");
  const [kbQuery, setKbQuery] = useState("");
  const [kbResults, setKbResults] = useState<any[]>([]);
  const [memContent, setMemContent] = useState("");
  const [memType, setMemType] = useState("LONG_TERM");
  const [confirmAction, setConfirmAction] = useState<{ title: string; message: string; fn: () => Promise<void> } | null>(null);

  async function load() {
    setError("");
    try {
      const [fRes, stRes, mRes, pRes] = await Promise.all([
        apiFetch<any>(`/api/v1/files${showDeleted ? "?include_deleted=true" : ""}`).catch(() => ({ files: [], folders: [] })),
        apiFetch<any>("/api/v1/files/storage/status").catch(() => null),
        apiFetch<any>("/api/v1/memory").catch(() => ({ memories: [] })),
        apiFetch<any>("/api/v1/projects").catch(() => ({ projects: [] })),
      ]);
      const list = fRes.files || [];
      setFiles(list);
      setProjects(pRes.projects || []);
      const discoveredFolders = Array.isArray(fRes.folders)
        ? fRes.folders
        : Array.from(new Set(list.map((f: any) => f.folder || "general")));
      setFolders(discoveredFolders as string[]);
      setStorageStatus(stRes);
      setMemories(mRes.memories || []);
      if (subPage === "drive") {
        apiFetch<any>("/api/v1/google/drive/files")
          .then((d) => {
            setDriveFiles(d.files || []);
            setDriveError("");
          })
          .catch((e) => setDriveError(e.message));
      }
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, [subPage, showDeleted]);

  // Fetch authenticated visual preview for images and PDFs
  useEffect(() => {
    let active = true;
    let createdUrl: string | null = null;
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl(null);
    }
    const needsBlobPreview = selectedFile && (isImageFile(selectedFile) || isPdfFile(selectedFile));
    if (needsBlobPreview && selectedFile?.file_id) {
      setPreviewLoading(true);
      fetchAuthBlobUrl(selectedFile.preview_url || `/api/v1/files/${selectedFile.file_id}/preview`)
        .then((url) => {
          createdUrl = url;
          if (active) setPreviewBlobUrl(url);
          else URL.revokeObjectURL(url);
        })
        .catch(() => {
          if (active) setPreviewBlobUrl(null);
        })
        .finally(() => {
          if (active) setPreviewLoading(false);
        });
    }
    return () => {
      active = false;
      if (createdUrl) URL.revokeObjectURL(createdUrl);
    };
  }, [selectedFile?.file_id]);

  async function processUploadFiles(fileList: File[]) {
    if (fileList.length === 0) return;
    setUploading(true);
    setUploadQueue(fileList.map((f) => ({ name: f.name, status: "uploading" })));
    let lastUploaded: any = null;
    let uploadedCount = 0;

    for (let i = 0; i < fileList.length; i++) {
      const f = fileList[i];
      const lower = f.name.toLowerCase();
      if (BLOCKED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
        setUploadQueue((prev) =>
          prev.map((q, idx) => (idx === i ? { ...q, status: "error", detail: "Blocked executable type (AEGIS)" } : q))
        );
        pushToast(`Blocked ${f.name}: executable file types are prohibited by AEGIS.`, "error");
        continue;
      }
      if (f.size > MAX_UPLOAD_BYTES) {
        setUploadQueue((prev) =>
          prev.map((q, idx) => (idx === i ? { ...q, status: "error", detail: "Exceeds 10 MB limit" } : q))
        );
        pushToast(`Skipped ${f.name}: exceeds 10 MB limit.`, "error");
        continue;
      }
      try {
        const fd = new FormData();
        fd.append("file", f);
        fd.append("folder", uploadFolder.trim() || "general");
        if (uploadProjectId) fd.append("project_id", uploadProjectId);
        const res = await apiFetch<any>("/api/v1/files/upload", {
          method: "POST",
          body: fd,
          isFormData: true,
        });
        lastUploaded = res;
        uploadedCount += 1;
        setUploadQueue((prev) =>
          prev.map((q, idx) => (idx === i ? { ...q, status: "done", detail: `${formatBytes(res.size_bytes)} · ${res.scan_status}` } : q))
        );
      } catch (err: any) {
        setUploadQueue((prev) =>
          prev.map((q, idx) => (idx === i ? { ...q, status: "error", detail: err.message } : q))
        );
        pushToast(`Failed ${f.name}: ${err.message}`, "error");
      }
    }

    if (uploadedCount > 0) {
      if (lastUploaded) setSelectedFile(lastUploaded);
      pushToast(
        `Uploaded ${uploadedCount} file${uploadedCount === 1 ? "" : "s"} to '${uploadFolder.trim() || "general"}' (AEGIS + VAULT scanned).`,
        "success"
      );
      await load();
    }
    setUploading(false);
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const fileList = Array.from(e.target.files || []);
    e.target.value = "";
    await processUploadFiles(fileList);
  }

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    try {
      await apiFetch("/api/v1/files/generate", {
        method: "POST",
        body: {
          filename: genName,
          content: genContent,
          mime_type: "text/markdown",
          folder: uploadFolder.trim() || "general",
          project_id: uploadProjectId || undefined,
        },
      });
      pushToast(`Generated ${genName}.`, "success");
      await load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function handleGenerateZip() {
    const entryName = (genName || "notes.md").trim() || "notes.md";
    const archiveBase = entryName.replace(/\.[^.]+$/, "") || "ultron-bundle";
    try {
      await apiFetch("/api/v1/files/generate-zip", {
        method: "POST",
        body: {
          archive_name: `${archiveBase}.zip`,
          files: { [entryName]: genContent },
          project_id: uploadProjectId || undefined,
        },
      });
      pushToast(`ZIP archive '${archiveBase}.zip' generated in File Hub.`, "success");
      await load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function inspectFile(fileId: string) {
    try {
      const detail = await apiFetch<any>(`/api/v1/files/${fileId}`);
      setSelectedFile(detail);
      onSelectSubPage("preview");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  function startEditFile(f: any) {
    setEditingFileId(f.file_id);
    setEditFilename(f.filename || "");
    setEditFolder(f.folder || "general");
    setEditProjectId(f.project_id || "");
  }

  async function saveEditFile(fileId: string) {
    if (!editFilename.trim()) {
      pushToast("Filename cannot be empty.", "error");
      return;
    }
    try {
      const updated = await apiFetch<any>(`/api/v1/files/${fileId}`, {
        method: "PATCH",
        body: {
          filename: editFilename.trim(),
          folder: editFolder.trim() || "general",
          project_id: editProjectId || undefined,
          clear_project: !editProjectId,
        },
      });
      if (selectedFile?.file_id === fileId) {
        setSelectedFile((prev: any) => ({ ...(prev || {}), ...updated }));
      }
      setEditingFileId(null);
      pushToast(`Updated '${updated.filename}' in folder '${updated.folder}'.`, "success");
      await load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  function sendFileToNeon(f: any) {
    const isImage = isImageFile(f);
    onAttachFileToNeon?.({
      file_id: f.file_id,
      filename: f.filename,
      mime_type: f.mime_type,
      is_image: isImage,
      size_bytes: f.size_bytes,
    });
    onSendToNeon?.(
      isImage
        ? `Analyze the attached image '${f.filename}' and describe what you see in natural language.`
        : `Analyze the attached document '${f.filename}' and summarize its key points in natural language.`
    );
    onNavigate("neon", "chat");
  }

  async function createSignedUrl(fileId: string) {
    try {
      const res = await apiFetch<any>(`/api/v1/files/${fileId}/signed-url`, {
        method: "POST",
        body: { expires_in_seconds: 300 },
      });
      setSignedUrl(res);
      pushToast("Short-lived signed download URL generated (expires in 5 min).", "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function searchKnowledge(e: React.FormEvent) {
    e.preventDefault();
    if (!kbQuery.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/memory/search", {
        method: "POST",
        body: { query: kbQuery.trim(), limit: 15 },
      });
      setKbResults(res.results || []);
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function storeMemory(e: React.FormEvent) {
    e.preventDefault();
    if (!memContent.trim()) return;
    try {
      await apiFetch("/api/v1/memory", {
        method: "POST",
        body: { content: memContent.trim(), memory_type: memType },
      });
      setMemContent("");
      pushToast("Memory stored with secret redaction.", "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  const projectMap = useMemo(() => {
    const m: Record<string, string> = {};
    for (const p of projects) m[p.project_id] = p.name;
    return m;
  }, [projects]);

  const totalStorageBytes = useMemo(
    () => files.reduce((acc, f) => acc + Number(f.size_bytes || 0), 0),
    [files]
  );

  const visibleFiles = useMemo(() => {
    const q = fileSearch.trim().toLowerCase();
    const filtered = files.filter((f) => {
      const matchesSearch =
        !q ||
        (f.filename || "").toLowerCase().includes(q) ||
        (f.folder || "general").toLowerCase().includes(q) ||
        (f.mime_type || "").toLowerCase().includes(q);
      const matchesFolder = selectedFolder === "ALL" || (f.folder || "general") === selectedFolder;
      const matchesType =
        typeFilter === "ALL" ||
        (typeFilter === "IMAGES" && isImageFile(f)) ||
        (typeFilter === "ARCHIVES" && isArchiveFile(f)) ||
        (typeFilter === "DOCS" && !isImageFile(f) && !isArchiveFile(f));
      return matchesSearch && matchesFolder && matchesType;
    });
    if (sortBy === "name") return [...filtered].sort((a, b) => (a.filename || "").localeCompare(b.filename || ""));
    if (sortBy === "size") return [...filtered].sort((a, b) => Number(b.size_bytes || 0) - Number(a.size_bytes || 0));
    return filtered;
  }, [files, fileSearch, selectedFolder, typeFilter, sortBy]);

  const activeDriver =
    storageStatus?.active_backend || storageStatus?.backend || storageStatus?.mode || "Local Tenant Vault";
  const bucketSub = storageStatus?.private_bucket_default
    ? `Private bucket · ${storageStatus?.supabase_storage_configured ? "Supabase Storage" : "Tenant-isolated local"}`
    : storageStatus?.bucket || "Tenant-isolated storage";

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`FILES & KNOWLEDGE // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <button type="button" className="btn btn-secondary btn-sm" onClick={load}>
            <RefreshCw size={13} /> Refresh
          </button>
        }
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {/* 43. FILE HUB */}
      {page.id === "hub" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="grid-4">
            <MetricDisplay label="Stored Files" value={files.length} sub={`${folders.length || 1} folder(s) · Tenant-isolated`} tone="info" />
            <MetricDisplay label="Storage Used" value={formatBytes(totalStorageBytes)} sub="Actual stored byte sum" tone="neutral" />
            <MetricDisplay label="Storage Driver" value={activeDriver} sub={bucketSub} tone="success" />
            <MetricDisplay label="Knowledge Memories" value={memories.length} sub="Versioned & secret-redacted" tone="info" />
          </div>

          <div className="grid-2">
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="card-title">
                <span>Storage &amp; Security Overview</span>
                <div className="row" style={{ gap: 6 }}>
                  <button type="button" className="btn btn-sm" onClick={() => onSelectSubPage("upload")}>
                    <Upload size={13} /> Upload
                  </button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => onSelectSubPage("browser")}>
                    <Folder size={13} /> Browse
                  </button>
                </div>
              </div>
              <div className="grid-3">
                <div className="list-item" style={{ textAlign: "center" }}>
                  <ImageIcon size={16} />
                  <div style={{ fontWeight: 600, marginTop: 4 }}>{files.filter(isImageFile).length}</div>
                  <div className="muted" style={{ fontSize: 11 }}>Images</div>
                </div>
                <div className="list-item" style={{ textAlign: "center" }}>
                  <FileCode2 size={16} />
                  <div style={{ fontWeight: 600, marginTop: 4 }}>{files.filter((f) => !isImageFile(f) && !isArchiveFile(f)).length}</div>
                  <div className="muted" style={{ fontSize: 11 }}>Docs &amp; Code</div>
                </div>
                <div className="list-item" style={{ textAlign: "center" }}>
                  <FileArchive size={16} />
                  <div style={{ fontWeight: 600, marginTop: 4 }}>{files.filter(isArchiveFile).length}</div>
                  <div className="muted" style={{ fontSize: 11 }}>Archives</div>
                </div>
              </div>
              <ReadableSummary
                data={storageStatus || { active_backend: activeDriver, private_bucket_default: true, status: "Ready" }}
                diagnosticsTitle="Technical Diagnostics — Storage Backend Configuration"
              />
            </div>

            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="card-title"><span>Recent Files ({files.slice(0, 5).length})</span></div>
              {files.length === 0 ? (
                <EmptyState title="No Files Yet" description="Upload images, PDFs, spreadsheets, or code in Upload Centre." />
              ) : (
                files.slice(0, 5).map((f) => (
                  <div key={f.file_id} className="list-item row-between" style={{ gap: 8 }}>
                    <div>
                      <strong>{f.filename}</strong>
                      <div className="muted mono" style={{ fontSize: 11 }}>
                        {f.folder || "general"} · {formatBytes(f.size_bytes)}
                        {f.project_id ? ` · ${projectMap[f.project_id] || f.project_id}` : ""}
                      </div>
                    </div>
                    <div className="row" style={{ gap: 4 }}>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => inspectFile(f.file_id)}>
                        Preview
                      </button>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => sendFileToNeon(f)}>
                        <Sparkles size={12} /> NEON
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* 44. FILE BROWSER */}
      {page.id === "browser" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
            <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
              <button
                type="button"
                className={`seg-btn ${selectedFolder === "ALL" ? "active" : ""}`}
                onClick={() => setSelectedFolder("ALL")}
              >
                All Folders ({files.length})
              </button>
              {folders.map((folder) => (
                <button
                  key={folder}
                  type="button"
                  className={`seg-btn ${selectedFolder === folder ? "active" : ""}`}
                  onClick={() => setSelectedFolder(folder)}
                >
                  <Folder size={11} style={{ marginRight: 4, verticalAlign: "middle" }} />
                  {folder}
                </button>
              ))}
            </div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <label className="row muted" style={{ gap: 5, fontSize: 12, cursor: "pointer" }}>
                <input type="checkbox" checked={showDeleted} onChange={(e) => setShowDeleted(e.target.checked)} />
                Show Deleted
              </label>
              <button type="button" className="btn btn-sm" onClick={() => onSelectSubPage("upload")}>
                <Upload size={13} /> Upload
              </button>
            </div>
          </div>

          <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
            <div style={{ flex: 2, minWidth: 200 }}>
              <SearchBar value={fileSearch} onChange={setFileSearch} placeholder="Search stored files by filename, folder, or MIME type..." />
            </div>
            <div className="row" style={{ gap: 6 }}>
              {(["ALL", "IMAGES", "DOCS", "ARCHIVES"] as const).map((tf) => (
                <button key={tf} type="button" className={`seg-btn ${typeFilter === tf ? "active" : ""}`} onClick={() => setTypeFilter(tf)}>
                  {tf}
                </button>
              ))}
            </div>
            <select className="select" style={{ width: 130 }} value={sortBy} onChange={(e) => setSortBy(e.target.value as any)} aria-label="Sort files">
              <option value="newest">Newest</option>
              <option value="name">Name A–Z</option>
              <option value="size">Largest</option>
            </select>
          </div>

          <DataTable
            rows={visibleFiles}
            rowKey={(f) => f.file_id}
            emptyTitle="No Files Stored"
            emptyDescription="Upload images, PDFs, or documents in Upload Centre, or generate a file."
            columns={[
              {
                key: "name",
                header: "Filename",
                render: (f) =>
                  editingFileId === f.file_id ? (
                    <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
                      <input
                        className="input"
                        style={{ minWidth: 140, padding: "4px 8px" }}
                        value={editFilename}
                        onChange={(e) => setEditFilename(e.target.value)}
                        aria-label="New filename"
                      />
                      <input
                        className="input"
                        style={{ width: 100, padding: "4px 8px" }}
                        value={editFolder}
                        onChange={(e) => setEditFolder(e.target.value)}
                        aria-label="Folder name"
                        placeholder="folder"
                      />
                      <select
                        className="select"
                        style={{ width: 140, padding: "4px 8px" }}
                        value={editProjectId}
                        onChange={(e) => setEditProjectId(e.target.value)}
                        aria-label="Attach to project"
                      >
                        <option value="">No project</option>
                        {projects.map((p) => (
                          <option key={p.project_id} value={p.project_id}>{p.name}</option>
                        ))}
                      </select>
                      <button type="button" className="btn btn-sm" onClick={() => saveEditFile(f.file_id)} aria-label="Save rename">
                        <Check size={12} />
                      </button>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => setEditingFileId(null)} aria-label="Cancel rename">
                        <X size={12} />
                      </button>
                    </div>
                  ) : (
                    <div>
                      <strong>{f.filename}</strong>
                      <div className="muted mono" style={{ fontSize: 11 }}>
                        {f.folder || "general"} · {f.mime_type || "file"}
                        {f.project_id ? ` · Project: ${projectMap[f.project_id] || f.project_id}` : ""}
                      </div>
                    </div>
                  ),
              },
              {
                key: "scan",
                header: "AEGIS Scan",
                render: (f) => (
                  <StatusIndicator
                    label={f.is_deleted ? "DELETED" : f.scan_status || "CLEAN"}
                    tone={f.is_deleted ? "neutral" : f.scan_status === "CLEAN" ? "success" : "warn"}
                  />
                ),
              },
              { key: "size", header: "Size", mono: true, render: (f) => formatBytes(f.size_bytes) },
              {
                key: "actions",
                header: "Actions",
                render: (f) => (
                  <div className="row" style={{ flexWrap: "wrap", gap: 5 }}>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => inspectFile(f.file_id)}>
                      Preview
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => sendFileToNeon(f)}
                      title="Attach directly to NEON for Gemini multimodal analysis"
                    >
                      <Sparkles size={12} /> NEON
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => startEditFile(f)}
                      title="Rename, move folder, or attach to project"
                      aria-label={`Rename ${f.filename}`}
                    >
                      <Edit3 size={12} />
                    </button>
                    {f.is_deleted ? (
                      <button
                        type="button"
                        className="btn btn-sm"
                        onClick={async () => {
                          await apiFetch(`/api/v1/files/${f.file_id}/restore`, { method: "POST" });
                          pushToast("File restored.", "success");
                          load();
                        }}
                      >
                        <RotateCcw size={12} /> Restore
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="btn btn-danger btn-sm"
                        aria-label={`Delete ${f.filename}`}
                        onClick={() =>
                          setConfirmAction({
                            title: "Soft-Delete File",
                            message: `Move '${f.filename}' to soft-delete trash? You can restore it later.`,
                            fn: async () => {
                              await apiFetch(`/api/v1/files/${f.file_id}`, { method: "DELETE" });
                              pushToast("File soft-deleted.", "success");
                              load();
                            },
                          })
                        }
                      >
                        <Trash2 size={12} />
                      </button>
                    )}
                  </div>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* 45. GOOGLE DRIVE WORKSPACE */}
      {page.id === "drive" && (
        <div className="card">
          <div className="card-title">
            <span>Google Drive Workspace</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("connections", "oauth")}>
              Manage Google OAuth
            </button>
          </div>
          {driveError ? (
            <EmptyState
              title="Google Drive Not Connected Yet"
              description={`${driveError}. Connect Google Drive via OAuth 2.0 + PKCE in Connections Centre.`}
              action={
                <button type="button" className="btn btn-sm" onClick={() => onNavigate("connections", "directory")}>
                  Open Connections Centre
                </button>
              }
            />
          ) : (
            <DataTable
              rows={driveFiles}
              rowKey={(d, i) => d.id || String(i)}
              emptyTitle="No Drive Files Returned"
              emptyDescription="Your connected Google Drive folder is empty."
              columns={[
                { key: "name", header: "Name", render: (d) => <strong>{d.name}</strong> },
                { key: "mime", header: "Type", mono: true, render: (d) => d.mimeType || "file" },
              ]}
            />
          )}
        </div>
      )}

      {/* 46. UPLOAD CENTRE */}
      {page.id === "upload" && (
        <div className="grid-2">
          <div
            className="card"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 12,
              border: dragActive ? "1px dashed var(--accent, #22d3ee)" : undefined,
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={async (e) => {
              e.preventDefault();
              setDragActive(false);
              await processUploadFiles(Array.from(e.dataTransfer.files || []));
            }}
          >
            <div className="card-title">
              <span><FolderPlus size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Upload Files or Photos (AEGIS + VAULT Scanned)</span>
            </div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <div style={{ flex: 1, minWidth: 150 }}>
                <label className="muted" htmlFor="upload-folder-input" style={{ fontSize: 12 }}>Destination Folder</label>
                <input
                  id="upload-folder-input"
                  className="input"
                  value={uploadFolder}
                  onChange={(e) => setUploadFolder(e.target.value)}
                  placeholder="e.g., general, specs, receipts"
                />
              </div>
              <div style={{ flex: 1, minWidth: 150 }}>
                <label className="muted" htmlFor="upload-project-select" style={{ fontSize: 12 }}>Attach to Project (Optional)</label>
                <select
                  id="upload-project-select"
                  className="select"
                  value={uploadProjectId}
                  onChange={(e) => setUploadProjectId(e.target.value)}
                >
                  <option value="">None (Tenant File Hub)</option>
                  {projects.map((p) => (
                    <option key={p.project_id} value={p.project_id}>{p.name}</option>
                  ))}
                </select>
              </div>
            </div>

            <div
              style={{
                border: "1px dashed var(--border-subtle, rgba(255,255,255,0.2))",
                borderRadius: 10,
                padding: 18,
                textAlign: "center",
                background: dragActive ? "rgba(34,211,238,0.06)" : "rgba(255,255,255,0.02)",
              }}
            >
              <div className="muted" style={{ marginBottom: 10, fontSize: 13 }}>
                Drag &amp; drop files here, or choose from device / camera
              </div>
              <div className="row" style={{ flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
                <label className="btn">
                  <Upload size={14} /> {uploading ? "Uploading..." : "Choose Files / Photos"}
                  <input
                    id="file-hub-upload-input"
                    type="file"
                    multiple
                    accept="image/*,.pdf,.docx,.txt,.md,.csv,.json,.py,.ts,.tsx,.js,.zip"
                    style={{ display: "none" }}
                    onChange={handleUpload}
                  />
                </label>
                <label className="btn btn-secondary">
                  <Camera size={14} /> Capture with Camera
                  <input
                    id="file-hub-camera-input"
                    type="file"
                    accept="image/*"
                    capture="environment"
                    style={{ display: "none" }}
                    onChange={handleUpload}
                  />
                </label>
              </div>
            </div>

            {uploadQueue.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {uploadQueue.map((item, idx) => (
                  <div key={`${item.name}-${idx}`} className="list-item row-between" style={{ padding: "6px 10px" }}>
                    <span className="mono" style={{ fontSize: 12 }}>{item.name}</span>
                    <StatusIndicator
                      label={item.detail || item.status.toUpperCase()}
                      tone={item.status === "done" ? "success" : item.status === "error" ? "danger" : "info"}
                    />
                  </div>
                ))}
              </div>
            )}

            <div className="muted" style={{ fontSize: 12 }}>
              Supports images (PNG, JPEG, WebP), PDFs, Word docs, spreadsheets, text, Markdown, JSON, and source code (up to 10 MB per file). Secrets are automatically redacted by VAULT before NEON ingestion.
            </div>
          </div>

          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="card-title"><span><FileText size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Generate Document or ZIP Bundle</span></div>
            <form onSubmit={handleGenerate} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <input className="input" value={genName} onChange={(e) => setGenName(e.target.value)} placeholder="Filename" />
              <textarea className="textarea mono" rows={6} value={genContent} onChange={(e) => setGenContent(e.target.value)} />
              <div className="row" style={{ gap: 8 }}>
                <button type="submit" className="btn btn-sm">Generate File</button>
                <button id="file-hub-generate-zip-btn" type="button" className="btn btn-secondary btn-sm" onClick={handleGenerateZip}>
                  <FileArchive size={13} /> Generate ZIP
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 47. DOWNLOADS */}
      {page.id === "downloads" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span>Authenticated Downloads &amp; Short-Lived Signed URLs</span></div>
          {signedUrl && (
            <div className="alert-box row-between" style={{ flexWrap: "wrap", gap: 8 }}>
              <div style={{ overflow: "hidden", textOverflow: "ellipsis" }}>
                <strong>Signed URL Ready:</strong> <code className="mono">{signedUrl.signed_url || signedUrl.url}</code>
              </div>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  const u = signedUrl.signed_url || signedUrl.url || "";
                  navigator.clipboard?.writeText(u);
                  pushToast("Signed URL copied to clipboard.", "success");
                }}
              >
                <Copy size={12} /> Copy
              </button>
            </div>
          )}
          <DataTable
            rows={files}
            rowKey={(f) => f.file_id}
            emptyTitle="No Downloadable Artifacts"
            emptyDescription="Upload or generate files first."
            columns={[
              {
                key: "name",
                header: "Filename",
                render: (f) => (
                  <div>
                    <strong>{f.filename}</strong>
                    <div className="muted mono" style={{ fontSize: 11 }}>{f.folder || "general"} · {formatBytes(f.size_bytes)}</div>
                  </div>
                ),
              },
              { key: "dir", header: "Direction", mono: true, render: (f) => f.direction || "UPLOAD" },
              {
                key: "dl",
                header: "Download",
                render: (f) => (
                  <div className="row" style={{ gap: 6 }}>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() =>
                        downloadAuthFile(f.download_url || `/api/v1/files/${f.file_id}/download`, f.filename).catch((e) =>
                          pushToast(e.message, "error")
                        )
                      }
                    >
                      <Download size={12} /> Download
                    </button>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => createSignedUrl(f.file_id)}>
                      <Link2 size={12} /> Signed URL
                    </button>
                  </div>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* 48. DOCUMENT PREVIEW */}
      {page.id === "preview" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title">
            <span>{selectedFile ? `Preview: ${selectedFile.filename}` : "Document, PDF, Code & Image Preview"}</span>
            {selectedFile && (
              <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => createSignedUrl(selectedFile.file_id)}
                >
                  <Link2 size={13} /> Share Signed URL
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() =>
                    downloadAuthFile(
                      selectedFile.download_url || `/api/v1/files/${selectedFile.file_id}/download`,
                      selectedFile.filename
                    ).catch((e) => pushToast(e.message, "error"))
                  }
                >
                  <Download size={13} /> Download
                </button>
                <button
                  id="file-preview-analyze-neon-btn"
                  type="button"
                  className="btn btn-sm"
                  onClick={() => sendFileToNeon(selectedFile)}
                >
                  <Sparkles size={13} /> Analyze in NEON
                </button>
              </div>
            )}
          </div>
          {!selectedFile ? (
            <EmptyState title="No File Selected" description="Choose Preview on any image, PDF, or document in the File Browser." />
          ) : (
            <>
              <div className="muted mono" style={{ fontSize: 12 }}>
                Folder: {selectedFile.folder || "general"} · Type: {selectedFile.mime_type || "unknown"} · Size: {formatBytes(selectedFile.size_bytes)} · Scan: {selectedFile.scan_status}
                {selectedFile.project_id ? ` · Project: ${projectMap[selectedFile.project_id] || selectedFile.project_id}` : ""}
              </div>
              {previewLoading && <div className="muted">Loading authenticated visual preview...</div>}
              {previewBlobUrl && isImageFile(selectedFile) && (
                <div
                  style={{
                    borderRadius: 12,
                    overflow: "hidden",
                    border: "1px solid var(--border-subtle, rgba(255,255,255,0.1))",
                    background: "rgba(0,0,0,0.25)",
                    padding: 10,
                    textAlign: "center",
                  }}
                >
                  <img
                    src={previewBlobUrl}
                    alt={selectedFile.filename}
                    style={{ maxWidth: "100%", maxHeight: 420, objectFit: "contain", borderRadius: 8 }}
                  />
                </div>
              )}
              {previewBlobUrl && isPdfFile(selectedFile) && (
                <iframe
                  title={`PDF Preview: ${selectedFile.filename}`}
                  src={previewBlobUrl}
                  style={{ width: "100%", height: 480, border: "1px solid var(--border-subtle, rgba(255,255,255,0.1))", borderRadius: 10, background: "#fff" }}
                />
              )}
              {selectedFile.extracted_text ? (
                <pre
                  style={{
                    whiteSpace: "pre-wrap",
                    lineHeight: 1.55,
                    padding: 12,
                    borderRadius: 10,
                    background: "rgba(255,255,255,0.03)",
                    margin: 0,
                    overflowX: "auto",
                  }}
                >
                  {selectedFile.extracted_text}
                </pre>
              ) : !previewBlobUrl && !previewLoading ? (
                <div className="muted">Binary file stored securely. Click "Analyze in NEON" or "Download" to inspect.</div>
              ) : null}
              <TechnicalDiagnostics title="Technical Diagnostics — File Metadata" data={selectedFile} />
            </>
          )}
        </div>
      )}

      {/* 49. KNOWLEDGE BASE */}
      {page.id === "knowledge" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span>Semantic Knowledge Recall</span></div>
          <form onSubmit={searchKnowledge} className="row">
            <input className="input" style={{ flex: 1 }} value={kbQuery} onChange={(e) => setKbQuery(e.target.value)} placeholder="Ask semantic vector search across tenant memory..." />
            <button type="submit" className="btn">Search Knowledge</button>
          </form>
          {kbResults.length === 0 ? (
            <div className="muted">Enter a semantic query to retrieve relevant knowledge entries.</div>
          ) : (
            kbResults.map((m, idx) => (
              <div key={m.memory_id || idx} className="list-item">
                <div className="row-between">
                  <span className="pill pill-cyan">{m.memory_type || "SEMANTIC"}</span>
                  {m.score !== undefined && <span className="muted mono">relevance: {Number(m.score).toFixed(3)}</span>}
                </div>
                <div>{m.content}</div>
              </div>
            ))
          )}
        </div>
      )}

      {/* 50. MEMORY MANAGEMENT */}
      {page.id === "memory" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title">
              <span>Store Versioned Memory</span>
              <button
                type="button"
                className="btn btn-danger btn-sm"
                onClick={() =>
                  setConfirmAction({
                    title: "Prune Low-Priority Memory",
                    message: "Compact expired or low-retention memory entries older than 90 days?",
                    fn: async () => {
                      await apiFetch("/api/v1/memory/prune", { method: "POST", body: { max_age_days: 90 } });
                      pushToast("Memory prune completed.", "success");
                      load();
                    },
                  })
                }
              >
                Prune Old
              </button>
            </div>
            <form onSubmit={storeMemory} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <select className="select" value={memType} onChange={(e) => setMemType(e.target.value)}>
                <option value="LONG_TERM">LONG_TERM</option>
                <option value="EPISODIC">EPISODIC</option>
                <option value="SEMANTIC">SEMANTIC</option>
                <option value="PROJECT">PROJECT</option>
              </select>
              <textarea className="textarea" rows={3} value={memContent} onChange={(e) => setMemContent(e.target.value)} placeholder="Store durable operational knowledge..." />
              <button type="submit" className="btn">Store Memory</button>
            </form>
          </div>

          <div className="card">
            <div className="card-title"><span>Persisted Memories ({memories.length})</span></div>
            {memories.length === 0 ? (
              <EmptyState title="No Memories Yet" description="Add long-term context on the left." />
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {memories.map((m) => (
                  <div key={m.memory_id} className="list-item">
                    <div className="row-between">
                      <span className="pill pill-cyan">{m.memory_type} v{m.version || 1}</span>
                      <div className="row">
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={async () => {
                            const h = await apiFetch<any>(`/api/v1/memory/${m.memory_id}/history`);
                            setMemHistory(h.history || []);
                          }}
                        >
                          History
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger btn-sm"
                          onClick={() =>
                            setConfirmAction({
                              title: "Delete Memory Entry",
                              message: "Permanently remove this memory entry?",
                              fn: async () => {
                                await apiFetch(`/api/v1/memory/${m.memory_id}`, { method: "DELETE" });
                                pushToast("Memory deleted.", "success");
                                load();
                              },
                            })
                          }
                        >
                          Delete
                        </button>
                      </div>
                    </div>
                    <div>{m.content}</div>
                  </div>
                ))}
              </div>
            )}
            {memHistory.length > 0 && (
              <div style={{ marginTop: 12 }}>
                <div className="eyebrow-mono" style={{ marginBottom: 6 }}>VERSION HISTORY ({memHistory.length})</div>
                {memHistory.map((item, idx) => (
                  <div key={item.version || idx} className="list-item" style={{ marginBottom: 6 }}>
                    <div className="row-between">
                      <strong>Version {item.version ?? idx + 1}</strong>
                      <span className="muted mono" style={{ fontSize: 11 }}>{item.updated_at || item.created_at || ""}</span>
                    </div>
                    <div>{item.content || item.summary || "Recorded revision"}</div>
                  </div>
                ))}
                <TechnicalDiagnostics title="Technical Diagnostics — Raw Memory History" data={memHistory} />
              </div>
            )}
          </div>
        </div>
      )}

      <ConfirmationDialog
        open={Boolean(confirmAction)}
        title={confirmAction?.title || "Confirm"}
        message={confirmAction?.message || ""}
        onCancel={() => setConfirmAction(null)}
        onConfirm={async () => {
          const fn = confirmAction?.fn;
          setConfirmAction(null);
          if (fn) await fn().catch((e) => pushToast(e.message, "error"));
        }}
      />
    </ResponsiveWorkspace>
  );
}
