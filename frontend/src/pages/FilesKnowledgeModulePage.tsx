import React, { useEffect, useState } from "react";
import { Download, FileArchive, Link2, RefreshCw, RotateCcw, Sparkles, Trash2, Upload } from "lucide-react";
import { apiFetch, downloadAuthFile } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import { ModulePageProps } from "./CommandModulePage";
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

export default function FilesKnowledgeModulePage({
  subPage,
  onSelectSubPage,
  onNavigate,
  onSendToNeon,
}: ModulePageProps) {
  const mod = getModule("files");
  const page = getSubPage("files", subPage);
  const { pushToast } = useToast();

  const [files, setFiles] = useState<any[]>([]);
  const [storageStatus, setStorageStatus] = useState<any>(null);
  const [driveFiles, setDriveFiles] = useState<any[]>([]);
  const [driveError, setDriveError] = useState("");
  const [memories, setMemories] = useState<any[]>([]);
  const [selectedFile, setSelectedFile] = useState<any>(null);
  const [signedUrl, setSignedUrl] = useState<any>(null);
  const [memHistory, setMemHistory] = useState<any[]>([]);
  const [error, setError] = useState("");

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
      const [fRes, stRes, mRes] = await Promise.all([
        apiFetch<any>("/api/v1/files").catch(() => ({ files: [] })),
        apiFetch<any>("/api/v1/files/storage/status").catch(() => null),
        apiFetch<any>("/api/v1/memory").catch(() => ({ memories: [] })),
      ]);
      setFiles(fRes.files || []);
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
  }, [subPage]);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const fd = new FormData();
    fd.append("file", f);
    try {
      const res = await apiFetch<any>("/api/v1/files/upload", { method: "POST", body: fd, isFormData: true });
      setSelectedFile(res);
      pushToast(`Uploaded ${res.filename} (${res.scan_status}).`, "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    try {
      await apiFetch("/api/v1/files/generate", {
        method: "POST",
        body: { filename: genName, content: genContent, mime_type: "text/markdown" },
      });
      pushToast(`Generated ${genName}.`, "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function handleGenerateZip() {
    try {
      await apiFetch("/api/v1/files/generate-zip", {
        method: "POST",
        body: {
          archive_name: "ultron-bundle.zip",
          entries: [{ filename: genName || "notes.md", content: genContent }],
        },
      });
      pushToast("ZIP archive generated in File Hub.", "success");
      load();
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

  async function createSignedUrl(fileId: string) {
    try {
      const res = await apiFetch<any>(`/api/v1/files/${fileId}/signed-url`, {
        method: "POST",
        body: { expires_in_seconds: 300 },
      });
      setSignedUrl(res);
      pushToast("Short-lived signed download URL generated.", "success");
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

  const visibleFiles = files.filter(
    (f) => !fileSearch.trim() || (f.filename || "").toLowerCase().includes(fileSearch.toLowerCase())
  );

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
          <div className="grid-3">
            <MetricDisplay label="Stored Files" value={files.length} sub="Tenant-isolated" tone="info" />
            <MetricDisplay label="Storage Driver" value={storageStatus?.backend || storageStatus?.mode || "Active"} sub={storageStatus?.bucket || "Private bucket"} tone="success" />
            <MetricDisplay label="Knowledge Memories" value={memories.length} sub="Versioned & secret-redacted" tone="neutral" />
          </div>
          <div className="card">
            <div className="card-title"><span>Storage Backend Diagnostics (/api/v1/files/storage/status)</span></div>
            <pre className="code-block">{JSON.stringify(storageStatus || { status: "Ready" }, null, 2)}</pre>
          </div>
        </div>
      )}

      {/* 44. FILE BROWSER */}
      {page.id === "browser" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <SearchBar value={fileSearch} onChange={setFileSearch} placeholder="Filter stored files by name..." />
          <DataTable
            rows={visibleFiles}
            rowKey={(f) => f.file_id}
            emptyTitle="No Files Stored"
            emptyDescription="Upload documents or generate files in Upload Centre."
            columns={[
              { key: "name", header: "Filename", render: (f) => <strong>{f.filename}</strong> },
              { key: "scan", header: "AEGIS Scan", render: (f) => <StatusIndicator label={f.scan_status || "CLEAN"} tone={f.scan_status === "CLEAN" ? "success" : "warn"} /> },
              { key: "size", header: "Size", mono: true, render: (f) => `${f.size_bytes} B` },
              {
                key: "actions",
                header: "Actions",
                render: (f) => (
                  <div className="row">
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => inspectFile(f.file_id)}>Preview</button>
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
            <span>Google Drive Workspace (/api/v1/google/drive/files)</span>
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
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="card-title"><span>Upload Document (AEGIS + VAULT Scanned)</span></div>
            <label className="btn">
              <Upload size={14} /> Choose File to Upload
              <input type="file" style={{ display: "none" }} onChange={handleUpload} />
            </label>
            <div className="muted">Supports PDF, DOCX, Markdown, JSON, source code, and images. Secrets are redacted before NEON ingestion.</div>
          </div>
          <div className="card">
            <div className="card-title"><span>Generate Document or ZIP Bundle</span></div>
            <form onSubmit={handleGenerate} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <input className="input" value={genName} onChange={(e) => setGenName(e.target.value)} placeholder="Filename" />
              <textarea className="textarea" rows={4} value={genContent} onChange={(e) => setGenContent(e.target.value)} />
              <div className="row">
                <button type="submit" className="btn btn-sm">Generate File</button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={handleGenerateZip}>
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
          <div className="card-title"><span>Authenticated Downloads & Short-Lived Signed URLs</span></div>
          {signedUrl && (
            <div className="alert-box">
              <strong>Signed URL Ready:</strong> <code className="mono">{signedUrl.signed_url || signedUrl.url}</code>
            </div>
          )}
          <DataTable
            rows={files}
            rowKey={(f) => f.file_id}
            emptyTitle="No Downloadable Artifacts"
            emptyDescription="Upload or generate files first."
            columns={[
              { key: "name", header: "Filename", render: (f) => <strong>{f.filename}</strong> },
              { key: "dir", header: "Direction", mono: true, render: (f) => f.direction || "UPLOAD" },
              {
                key: "dl",
                header: "Download",
                render: (f) => (
                  <div className="row">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={() => downloadAuthFile(f.download_url || `/api/v1/files/${f.file_id}/download`, f.filename).catch((e) => pushToast(e.message, "error"))}
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
            <span>{selectedFile ? `Preview: ${selectedFile.filename}` : "Document Preview"}</span>
            {selectedFile && onSendToNeon && (
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => {
                  onSendToNeon(`Analyze document '${selectedFile.filename}':\n\n${(selectedFile.extracted_text || "(binary)").slice(0, 3000)}`);
                  onNavigate("neon", "chat");
                }}
              >
                <Sparkles size={13} /> Analyze in NEON
              </button>
            )}
          </div>
          {!selectedFile ? (
            <EmptyState title="No Document Selected" description="Choose Preview on any file in the File Browser." />
          ) : (
            <>
              <div className="muted mono">Extractor: {selectedFile.metadata?.extractor || "text"} · Scan: {selectedFile.scan_status}</div>
              <pre className="code-block">{selectedFile.extracted_text || "(Binary file — no extracted text)"}</pre>
            </>
          )}
        </div>
      )}

      {/* 49. KNOWLEDGE BASE */}
      {page.id === "knowledge" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span>Semantic Knowledge Recall (/api/v1/memory/search)</span></div>
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
                  {m.score !== undefined && <span className="muted mono">score: {Number(m.score).toFixed(3)}</span>}
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
                    message: "Run /api/v1/memory/prune to compact expired or low-retention memory entries?",
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
              <pre className="code-block" style={{ marginTop: 10 }}>{JSON.stringify(memHistory, null, 2)}</pre>
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
