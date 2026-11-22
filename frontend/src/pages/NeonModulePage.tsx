import React, { useEffect, useState } from "react";
import {
  Bot,
  Check,
  Copy,
  Paperclip,
  Plus,
  RefreshCw,
  Send,
  Sparkles,
  Upload,
} from "lucide-react";
import { apiFetch, streamNeon } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import {
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

function renderFormattedMessage(content: string, onCopy: (code: string) => void) {
  const parts = content.split(/(```[\s\S]*?```)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("```") && part.endsWith("```")) {
      const inner = part.slice(3, -3);
      const nl = inner.indexOf("\n");
      const lang = nl >= 0 ? inner.slice(0, nl).trim() : "";
      const code = nl >= 0 ? inner.slice(nl + 1) : inner;
      return (
        <div key={idx} className="code-wrap">
          <div className="row-between code-header">
            <span className="mono">{lang || "code"}</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onCopy(code)}>
              <Copy size={12} /> Copy
            </button>
          </div>
          <pre className="code-block">{code}</pre>
        </div>
      );
    }
    return (
      <div key={idx} style={{ whiteSpace: "pre-wrap", lineHeight: 1.55 }}>
        {part}
      </div>
    );
  });
}

export default function NeonModulePage({
  subPage,
  onSelectSubPage,
  onNavigate,
  pendingPrompt,
  onClearPendingPrompt,
  initialShare,
}: ModulePageProps) {
  const mod = getModule("neon");
  const page = getSubPage("neon", subPage);
  const { pushToast } = useToast();

  const [conversations, setConversations] = useState<any[]>([]);
  const [activeId, setActiveId] = useState("");
  const [messages, setMessages] = useState<any[]>([]);
  const [agents, setAgents] = useState<any[]>([]);
  const [selectedAgent, setSelectedAgent] = useState("AGT-01");
  const [input, setInput] = useState("");
  const [useStream, setUseStream] = useState(false);
  const [sending, setSending] = useState(false);
  const [warning, setWarning] = useState("");
  const [error, setError] = useState("");
  const [convSearch, setConvSearch] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [attachedFile, setAttachedFile] = useState<{ file_id: string; filename: string; text: string } | null>(null);

  // Models, tiers, usage, health, settings
  const [models, setModels] = useState<any>(null);
  const [tiers, setTiers] = useState<any>(null);
  const [usage, setUsage] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [defaultTier, setDefaultTier] = useState("T2");
  const [defaultTemp, setDefaultTemp] = useState("0.3");
  const [structuredMode, setStructuredMode] = useState(false);

  // Multimodal
  const [mmPrompt, setMmPrompt] = useState("Analyze this visual frame and summarize key details.");
  const [mmResult, setMmResult] = useState<any>(null);
  const [copiedFlag, setCopiedFlag] = useState(false);

  async function loadBase() {
    setError("");
    try {
      const [cRes, aRes, mRes, tRes, uRes, hRes] = await Promise.all([
        apiFetch<any>("/api/v1/neon/conversations").catch(() => ({ conversations: [] })),
        apiFetch<any>("/api/v1/agents").catch(() => ({ agents: [] })),
        apiFetch<any>("/api/v1/neon/models").catch(() => null),
        apiFetch<any>("/api/v1/neon/tiers").catch(() => null),
        apiFetch<any>("/api/v1/neon/usage").catch(() => null),
        apiFetch<any>("/health").catch(() => null),
      ]);
      const list = cRes.conversations || [];
      setConversations(list);
      if (!activeId && list.length > 0) setActiveId(list[0].conversation_id);
      setAgents(aRes.agents || []);
      setModels(mRes);
      setTiers(tRes);
      setUsage(uRes);
      setHealth(hRes);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function loadMessages(cid: string) {
    if (!cid) return;
    try {
      const res = await apiFetch<any>(`/api/v1/neon/conversations/${cid}`);
      setMessages(res.messages || []);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    loadBase();
  }, [subPage]);

  useEffect(() => {
    if (activeId) loadMessages(activeId);
  }, [activeId]);

  useEffect(() => {
    if (pendingPrompt) {
      setInput(pendingPrompt);
      onClearPendingPrompt?.();
    }
  }, [pendingPrompt]);

  useEffect(() => {
    if (initialShare && (initialShare.url || initialShare.text || initialShare.title)) {
      apiFetch<any>("/api/v1/bridge/share", {
        method: "POST",
        body: {
          title: initialShare.title,
          url: initialShare.url,
          shared_text: initialShare.text,
          source_app: "pwa_share_target",
        },
      })
        .then((res) => {
          setWarning(`BRIDGE ingested share (AEGIS: ${res.aegis_url_verdict}).`);
          if (res.conversation_id) {
            setActiveId(res.conversation_id);
            loadBase();
          }
        })
        .catch((e) => setError(`BRIDGE share blocked: ${e.message}`));
    }
  }, [initialShare]);

  async function handleCopyCode(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      setCopiedFlag(true);
      pushToast("Code block copied to clipboard.", "success");
      window.setTimeout(() => setCopiedFlag(false), 1800);
    } catch {
      pushToast("Clipboard access unavailable.", "error");
    }
  }

  async function handleAttachFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    try {
      const res = await apiFetch<any>("/api/v1/files/upload", {
        method: "POST",
        body: fd,
        isFormData: true,
      });
      setAttachedFile({
        file_id: res.file_id,
        filename: res.filename,
        text: (res.extracted_text || "").slice(0, 2000),
      });
      pushToast(`Attached ${res.filename} (VAULT scanned).`, "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    setSending(true);
    setError("");
    setWarning("");
    const composed = attachedFile
      ? `${input.trim()}\n\n[Attached File: ${attachedFile.filename}]\n${attachedFile.text}`
      : input.trim();

    try {
      if (useStream) {
        const uId = `u_${Date.now()}`;
        const aId = `a_${Date.now() + 1}`;
        setMessages((prev) => [
          ...prev,
          { message_id: uId, role: "user", content: composed },
          { message_id: aId, role: "assistant", content: "", model: "streaming..." },
        ]);
        await streamNeon(
          composed,
          selectedAgent,
          (delta) => {
            setMessages((prev) =>
              prev.map((m) => (m.message_id === aId ? { ...m, content: (m.content || "") + delta } : m))
            );
          },
          (meta) => {
            setMessages((prev) =>
              prev.map((m) =>
                m.message_id === aId ? { ...m, model: `${meta.model} (${meta.execution_mode})` } : m
              )
            );
          }
        );
      } else {
        let cid = activeId;
        if (!cid) {
          const created = await apiFetch<any>("/api/v1/neon/conversations", {
            method: "POST",
            body: { title: input.trim().slice(0, 48), agent_id: selectedAgent },
          });
          cid = created.conversation_id;
          setActiveId(cid);
          await loadBase();
        }
        const res = await apiFetch<any>(`/api/v1/neon/conversations/${cid}/messages`, {
          method: "POST",
          body: { content: composed },
        });
        if (res.secret_interception?.warnings?.length) {
          setWarning(res.secret_interception.warnings.join(" "));
        }
        await loadMessages(cid);
      }
      setInput("");
      setAttachedFile(null);
    } catch (err: any) {
      setError(err.message);
      pushToast(err.message, "error");
    } finally {
      setSending(false);
    }
  }

  async function createConversation(e: React.FormEvent) {
    e.preventDefault();
    try {
      const created = await apiFetch<any>("/api/v1/neon/conversations", {
        method: "POST",
        body: {
          title: newTitle.trim() || `NEON Session (${selectedAgent})`,
          agent_id: selectedAgent,
        },
      });
      setNewTitle("");
      setActiveId(created.conversation_id);
      await loadBase();
      onSelectSubPage("chat");
      pushToast(`Started conversation with ${selectedAgent}.`, "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function saveIntelligenceSettings(e: React.FormEvent) {
    e.preventDefault();
    try {
      await Promise.all([
        apiFetch("/api/v1/settings", { method: "PUT", body: { key: "neon_default_tier", value: defaultTier } }),
        apiFetch("/api/v1/settings", { method: "PUT", body: { key: "neon_default_temperature", value: Number(defaultTemp) } }),
        apiFetch("/api/v1/settings", { method: "PUT", body: { key: "neon_structured_mode", value: structuredMode } }),
      ]);
      pushToast("NEON intelligence defaults persisted.", "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function handleMultimodalUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    const reader = new FileReader();
    reader.onload = async () => {
      const b64 = String(reader.result || "").split(",")[1] || "";
      try {
        const res = await apiFetch<any>("/api/v1/creative/visual/analyze", {
          method: "POST",
          body: { prompt: mmPrompt, image_base64: b64, mime_type: f.type || "image/png", source: "neon_multimodal" },
        });
        setMmResult(res);
        pushToast("Multimodal analysis returned.", "success");
      } catch (err: any) {
        pushToast(err.message, "error");
      }
    };
    reader.readAsDataURL(f);
  }

  const filteredConversations = conversations.filter(
    (c) =>
      !convSearch.trim() ||
      (c.title || "").toLowerCase().includes(convSearch.toLowerCase()) ||
      (c.agent_id || "").toLowerCase().includes(convSearch.toLowerCase())
  );

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`NEON INTELLIGENCE // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <div className="row">
            <StatusIndicator
              label={health?.providers?.gemini?.configured ? "GEMINI LIVE" : "FALLBACK MODE"}
              tone={health?.providers?.gemini?.configured ? "success" : "warn"}
            />
            <button type="button" className="btn btn-secondary btn-sm" onClick={loadBase}>
              <RefreshCw size={13} /> Refresh
            </button>
          </div>
        }
      />

      {error && <ErrorState message={error} onRetry={loadBase} />}
      {warning && <div className="alert-box alert-warn">{warning}</div>}

      {/* 9. NEON CHAT */}
      {page.id === "chat" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="row-between">
            <div className="row">
              <select
                aria-label="Select NEON conversation"
                className="select"
                style={{ width: 220 }}
                value={activeId}
                onChange={(e) => setActiveId(e.target.value)}
              >
                {conversations.length === 0 && <option value="">New Conversation</option>}
                {conversations.map((c) => (
                  <option key={c.conversation_id} value={c.conversation_id}>
                    {c.title} ({c.agent_id})
                  </option>
                ))}
              </select>
              <select
                aria-label="Select specialist agent handoff"
                className="select"
                style={{ width: 190 }}
                value={selectedAgent}
                onChange={(e) => setSelectedAgent(e.target.value)}
              >
                {(agents.length ? agents : [{ agent_id: "AGT-01", name: "NEON Chief of Staff" }]).map((a) => (
                  <option key={a.agent_id} value={a.agent_id}>
                    {a.agent_id} · {a.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="row">
              <button
                type="button"
                className={`seg-btn ${!useStream ? "active" : ""}`}
                onClick={() => setUseStream(false)}
              >
                Persisted
              </button>
              <button
                type="button"
                className={`seg-btn ${useStream ? "active" : ""}`}
                onClick={() => setUseStream(true)}
              >
                SSE Stream
              </button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => onSelectSubPage("new-conversation")}>
                <Plus size={13} /> New
              </button>
            </div>
          </div>

          <div className="neon-transcript">
            {messages.length === 0 ? (
              <EmptyState
                title="NEON Ready"
                description="Type a prompt, attach a document, or switch agents. Raw secrets and card numbers are automatically intercepted by VAULT."
              />
            ) : (
              messages.map((m) => (
                <div key={m.message_id} className={`neon-bubble ${m.role === "user" ? "neon-user" : "neon-assistant"}`}>
                  <div className="row-between" style={{ marginBottom: 6 }}>
                    <span className="mono-tag">
                      {m.role === "user" ? "OPERATOR" : `NEON · ${selectedAgent}`}
                    </span>
                    <div className="row">
                      {m.model && <span className="muted mono" style={{ fontSize: 11 }}>{m.model}</span>}
                      {m.role === "assistant" && (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => handleCopyCode(m.content || "")}
                          aria-label="Copy response"
                        >
                          {copiedFlag ? <Check size={12} /> : <Copy size={12} />}
                        </button>
                      )}
                    </div>
                  </div>
                  {renderFormattedMessage(String(m.content || ""), handleCopyCode)}
                </div>
              ))
            )}
          </div>

          {attachedFile && (
            <div className="alert-box row-between">
              <span>Attached: <strong>{attachedFile.filename}</strong> (VAULT scanned)</span>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setAttachedFile(null)}>Remove</button>
            </div>
          )}

          <form onSubmit={handleSend} className="row">
            <label className="btn btn-secondary btn-sm" title="Attach file to NEON">
              <Paperclip size={14} />
              <input type="file" style={{ display: "none" }} onChange={handleAttachFile} />
            </label>
            <input
              id="neon-chat-input"
              className="input"
              style={{ flex: 1 }}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={useStream ? "Stream response via /api/v1/neon/stream..." : "Send message to NEON..."}
            />
            <button id="neon-chat-send" type="submit" className="btn" disabled={sending || !input.trim()}>
              <Send size={14} /> {sending ? "Working..." : "Send"}
            </button>
          </form>
        </div>
      )}

      {/* 10. CONVERSATION HISTORY */}
      {page.id === "conversations" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <SearchBar value={convSearch} onChange={setConvSearch} placeholder="Search persisted NEON conversations..." />
          <DataTable
            rows={filteredConversations}
            rowKey={(c) => c.conversation_id}
            emptyTitle="No Saved Conversations"
            emptyDescription="Start a NEON chat session to persist multi-turn threads."
            columns={[
              { key: "title", header: "Title", render: (c) => <strong>{c.title}</strong> },
              { key: "agent", header: "Agent", mono: true, render: (c) => c.agent_id || "AGT-01" },
              { key: "updated", header: "Updated", mono: true, render: (c) => c.updated_at || "—" },
              {
                key: "open",
                header: "Action",
                render: (c) => (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => {
                      setActiveId(c.conversation_id);
                      onSelectSubPage("chat");
                    }}
                  >
                    Open Thread
                  </button>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* 11. NEW CONVERSATION */}
      {page.id === "new-conversation" && (
        <div className="card" style={{ maxWidth: 640 }}>
          <div className="card-title"><span>Start Specialist NEON Session</span></div>
          <form onSubmit={createConversation} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <input
              className="input"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Session title (e.g., Q3 Architecture Review)"
            />
            <select className="select" value={selectedAgent} onChange={(e) => setSelectedAgent(e.target.value)}>
              {(agents.length ? agents : [{ agent_id: "AGT-01", name: "NEON Chief of Staff", domain: "Core" }]).map((a) => (
                <option key={a.agent_id} value={a.agent_id}>
                  {a.agent_id} — {a.name} ({a.domain})
                </option>
              ))}
            </select>
            <button type="submit" className="btn">
              <Sparkles size={14} /> Create & Open Chat
            </button>
          </form>
        </div>
      )}

      {/* 12. MODEL SELECTION */}
      {page.id === "models" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title"><span>Active Gemini & NEON Models</span></div>
            <pre className="code-block">{JSON.stringify(models || { status: "Loading models..." }, null, 2)}</pre>
          </div>
          <div className="card">
            <div className="card-title"><span>Reasoning Tiers (T1 – T5)</span></div>
            <pre className="code-block">{JSON.stringify(tiers || { status: "Loading tiers..." }, null, 2)}</pre>
          </div>
        </div>
      )}

      {/* 13. PROVIDER CONFIGURATION */}
      {page.id === "providers" && (
        <div className="card">
          <div className="card-title">
            <span>LLM Provider Readiness (Honest Backend State)</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("connections", "api-providers")}>
              Configure in Connections Centre
            </button>
          </div>
          <div className="grid-2">
            {["gemini", "openai", "anthropic", "ollama"].map((p) => {
              const info = health?.providers?.[p];
              const configured = Boolean(info?.configured);
              return (
                <div key={p} className="list-item">
                  <div className="row-between">
                    <strong>{p.toUpperCase()}</strong>
                    <StatusIndicator label={configured ? "Configured" : "Not connected"} tone={configured ? "success" : "neutral"} />
                  </div>
                  <div className="muted">{info?.detail || "Configure server environment key or backend VAULT."}</div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* 14. INTELLIGENCE SETTINGS */}
      {page.id === "intelligence-settings" && (
        <div className="card" style={{ maxWidth: 640 }}>
          <div className="card-title"><span>NEON Routing & Reasoning Defaults</span></div>
          <form onSubmit={saveIntelligenceSettings} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <label className="muted">Default Reasoning Tier</label>
            <select className="select" value={defaultTier} onChange={(e) => setDefaultTier(e.target.value)}>
              <option value="T1">T1 — Fast Utility & Classification</option>
              <option value="T2">T2 — Balanced Daily Operations</option>
              <option value="T3">T3 — Deep Technical Reasoning</option>
              <option value="T4">T4 — Multi-Agent Strategic Synthesis</option>
              <option value="T5">T5 — Maximum Verification & Governance</option>
            </select>
            <label className="muted">Temperature ({defaultTemp})</label>
            <input className="input" type="number" min="0" max="1" step="0.1" value={defaultTemp} onChange={(e) => setDefaultTemp(e.target.value)} />
            <label className="row">
              <input type="checkbox" checked={structuredMode} onChange={(e) => setStructuredMode(e.target.checked)} />
              <span>Prefer structured JSON responses when calling specialist tools</span>
            </label>
            <button type="submit" className="btn">Save Intelligence Defaults</button>
          </form>
        </div>
      )}

      {/* 15. EXECUTION HISTORY */}
      {page.id === "execution-history" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="grid-3">
            <MetricDisplay label="Total Invocations" value={usage?.total_invocations ?? 0} tone="info" />
            <MetricDisplay label="Total Tokens" value={usage?.total_tokens ?? 0} tone="neutral" />
            <MetricDisplay label="Est. Cost (USD)" value={`$${Number(usage?.total_cost_usd || 0).toFixed(4)}`} tone="success" />
          </div>
          <div className="card">
            <div className="card-title"><span>NEON Telemetry Breakdown (/api/v1/neon/usage)</span></div>
            <pre className="code-block">{JSON.stringify(usage, null, 2)}</pre>
          </div>
        </div>
      )}

      {/* 16. MULTIMODAL WORKSPACE */}
      {page.id === "multimodal" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span>Multimodal Vision & Document Analysis</span></div>
          <textarea
            className="textarea"
            rows={2}
            value={mmPrompt}
            onChange={(e) => setMmPrompt(e.target.value)}
            placeholder="Instruction for NEON visual analysis..."
          />
          <label className="btn" style={{ alignSelf: "flex-start" }}>
            <Upload size={14} /> Select Image for NEON Vision Analysis
            <input type="file" accept="image/*" style={{ display: "none" }} onChange={handleMultimodalUpload} />
          </label>
          {mmResult ? (
            <pre className="code-block">{JSON.stringify(mmResult, null, 2)}</pre>
          ) : (
            <div className="muted">Uploads are analyzed through POST /api/v1/creative/visual/analyze without fabricating findings.</div>
          )}
          <div className="row">
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("agents", "workspace")}>
              <Bot size={13} /> Open Specialist Agent Workspace
            </button>
          </div>
        </div>
      )}
    </ResponsiveWorkspace>
  );
}
