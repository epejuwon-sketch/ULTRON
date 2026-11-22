import React, { useEffect, useRef, useState } from "react";
import {
  Bot,
  Camera,
  Check,
  Copy,
  Mic,
  MicOff,
  Paperclip,
  Plus,
  RefreshCw,
  Send,
  Share2,
  Sparkles,
  Upload,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import { apiFetch, resolveGeminiProviderStatus, streamNeon } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import type { AttachedFileRef, ModulePageProps } from "../types/module";
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
import {
  ProvenanceBar,
  ReadableSummary,
  SourcesList,
  TechnicalDiagnostics,
} from "../components/ui/HumanPresentation";

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
  pendingFiles,
  onClearPendingFiles,
  initialShare,
}: ModulePageProps) {
  const mod = getModule("neon");
  const page = getSubPage("neon", subPage);
  const { pushToast } = useToast();

  const [conversations, setConversations] = useState<any[]>([]);
  const [activeId, setActiveId] = useState("");
  const [messages, setMessages] = useState<any[]>([]);
  const [messageExtras, setMessageExtras] = useState<
    Record<
      string,
      {
        provenance?: any;
        research_sources?: any[];
        attached_files?: any[];
        diagnostics?: any;
      }
    >
  >({});
  const [agents, setAgents] = useState<any[]>([]);
  const [selectedAgent, setSelectedAgent] = useState("AGT-01");
  const [input, setInput] = useState("");
  const [useStream, setUseStream] = useState(false);
  const [sending, setSending] = useState(false);
  const [uploadingFiles, setUploadingFiles] = useState(false);
  const [warning, setWarning] = useState("");
  const [error, setError] = useState("");
  const [convSearch, setConvSearch] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [attachedFiles, setAttachedFiles] = useState<AttachedFileRef[]>([]);
  const [listening, setListening] = useState(false);
  const [speakingMsgId, setSpeakingMsgId] = useState<string | null>(null);
  const recognitionRef = useRef<any>(null);

  // Models, tiers, usage, health, Gemini diagnostics, settings
  const [models, setModels] = useState<any>(null);
  const [tiers, setTiers] = useState<any>(null);
  const [usage, setUsage] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [geminiDiag, setGeminiDiag] = useState<any>(null);
  const [discoveringModels, setDiscoveringModels] = useState(false);
  const [defaultTier, setDefaultTier] = useState("T2");
  const [defaultTemp, setDefaultTemp] = useState("0.3");
  const [structuredMode, setStructuredMode] = useState(false);

  // Multimodal
  const [mmPrompt, setMmPrompt] = useState("Analyze this visual frame and summarize key details.");
  const [mmResult, setMmResult] = useState<any>(null);
  const [copiedFlag, setCopiedFlag] = useState(false);

  async function loadBase(discoverLive = false) {
    setError("");
    if (discoverLive) setDiscoveringModels(true);
    const authErrors: string[] = [];
    const trackErr = <T,>(fallback: T) => (err: any): T => {
      if (err?.message) authErrors.push(String(err.message));
      return fallback;
    };
    try {
      const [cRes, aRes, mRes, tRes, uRes, hRes, gRes] = await Promise.all([
        apiFetch<any>("/api/v1/neon/conversations").catch(trackErr({ conversations: [] })),
        apiFetch<any>("/api/v1/agents").catch(trackErr({ agents: [] })),
        apiFetch<any>("/api/v1/neon/models").catch(trackErr(null)),
        apiFetch<any>("/api/v1/neon/tiers").catch(trackErr(null)),
        apiFetch<any>("/api/v1/neon/usage").catch(trackErr(null)),
        apiFetch<any>("/health").catch(() => null),
        apiFetch<any>(`/api/v1/neon/gemini/diagnostics?discover=${discoverLive ? "true" : "false"}`).catch(trackErr(null)),
      ]);
      const list = cRes.conversations || [];
      setConversations(list);
      if (!activeId && list.length > 0) setActiveId(list[0].conversation_id);
      setAgents(aRes.agents || []);
      setModels(mRes);
      setTiers(tRes);
      setUsage(uRes);
      setHealth(hRes);
      setGeminiDiag(gRes);
      if (authErrors.length >= 3) {
        setError(authErrors[0]);
      }
      if (discoverLive && gRes?.catalog?.catalog_verified) {
        pushToast(`Discovered ${gRes.catalog.models_discovered} live Gemini models (${gRes.catalog.latency_ms}ms).`, "success");
      }
    } catch (e: any) {
      setError(e.message);
    } finally {
      if (discoverLive) setDiscoveringModels(false);
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
    if (pendingFiles && pendingFiles.length > 0) {
      setAttachedFiles((prev) => {
        const seen = new Set(prev.map((p) => p.file_id));
        const merged = [...prev];
        for (const f of pendingFiles) {
          if (!seen.has(f.file_id)) {
            merged.push(f);
            seen.add(f.file_id);
          }
        }
        return merged;
      });
      onClearPendingFiles?.();
    }
  }, [pendingFiles]);

  useEffect(() => {
    return () => {
      try {
        recognitionRef.current?.stop?.();
        if (typeof window !== "undefined" && "speechSynthesis" in window) {
          window.speechSynthesis.cancel();
        }
      } catch {
        // ignore cleanup errors
      }
    };
  }, []);

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
      pushToast("Copied to clipboard.", "success");
      window.setTimeout(() => setCopiedFlag(false), 1800);
    } catch {
      pushToast("Clipboard access unavailable.", "error");
    }
  }

  function handleSpeak(msgId: string, text: string) {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      pushToast("Voice readout (Speech Synthesis) is not supported in this browser.", "error");
      return;
    }
    if (speakingMsgId === msgId) {
      window.speechSynthesis.cancel();
      setSpeakingMsgId(null);
      return;
    }
    window.speechSynthesis.cancel();
    const utter = new SpeechSynthesisUtterance(text);
    utter.onend = () => setSpeakingMsgId(null);
    utter.onerror = () => setSpeakingMsgId(null);
    setSpeakingMsgId(msgId);
    window.speechSynthesis.speak(utter);
  }

  async function handleShareMessage(text: string) {
    try {
      if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
        await navigator.share({ title: "ULTRON OS · NEON Response", text });
        pushToast("Shared via system share sheet.", "success");
      } else {
        await navigator.clipboard.writeText(text);
        pushToast("Native share unavailable — copied response to clipboard.", "info");
      }
    } catch (err: any) {
      if (err?.name !== "AbortError") {
        pushToast("Could not share response.", "error");
      }
    }
  }

  function handleToggleVoiceInput() {
    if (listening) {
      try {
        recognitionRef.current?.stop?.();
      } catch {
        // ignore
      }
      setListening(false);
      return;
    }
    const SpeechRec =
      typeof window !== "undefined" &&
      ((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
    if (!SpeechRec) {
      pushToast("Speech-to-Text is not supported in this browser. Check ORBIT Device Permissions.", "error");
      return;
    }
    try {
      const rec = new SpeechRec();
      rec.continuous = false;
      rec.interimResults = false;
      rec.lang = "en-US";
      rec.onresult = (ev: any) => {
        const transcript = ev.results?.[0]?.[0]?.transcript || "";
        if (transcript) {
          setInput((prev) => (prev ? `${prev} ${transcript}` : transcript));
          pushToast("Voice captured into NEON composer.", "success");
        }
      };
      rec.onerror = (ev: any) => {
        pushToast(`Voice input error: ${ev?.error || "permission denied"}`, "error");
        setListening(false);
      };
      rec.onend = () => setListening(false);
      recognitionRef.current = rec;
      rec.start();
      setListening(true);
      pushToast("Listening for voice command...", "info");
    } catch (err: any) {
      pushToast(err?.message || "Could not start microphone.", "error");
      setListening(false);
    }
  }

  async function handleAttachFiles(e: React.ChangeEvent<HTMLInputElement>) {
    const fileList = Array.from(e.target.files || []);
    e.target.value = "";
    if (fileList.length === 0) return;

    const MAX_BYTES = 10 * 1024 * 1024;
    setUploadingFiles(true);
    const uploaded: AttachedFileRef[] = [];
    try {
      for (const file of fileList) {
        if (file.size > MAX_BYTES) {
          pushToast(`Skipped ${file.name}: exceeds 10 MB limit.`, "error");
          continue;
        }
        const fd = new FormData();
        fd.append("file", file);
        fd.append("folder", "neon-attachments");
        const res = await apiFetch<any>("/api/v1/files/upload", {
          method: "POST",
          body: fd,
          isFormData: true,
        });
        uploaded.push({
          file_id: res.file_id,
          filename: res.filename,
          mime_type: res.mime_type,
          is_image: Boolean(res.is_image || (res.mime_type || "").startsWith("image/")),
          size_bytes: res.size_bytes,
        });
      }
      if (uploaded.length > 0) {
        setAttachedFiles((prev) => [...prev, ...uploaded]);
        pushToast(
          `Attached ${uploaded.length} file${uploaded.length === 1 ? "" : "s"} for multimodal Gemini analysis.`,
          "success"
        );
      }
    } catch (err: any) {
      pushToast(err.message, "error");
    } finally {
      setUploadingFiles(false);
    }
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim() && attachedFiles.length === 0) return;
    setSending(true);
    setError("");
    setWarning("");
    const promptText =
      input.trim() ||
      `Analyze the attached file${attachedFiles.length === 1 ? "" : "s"} (${attachedFiles.map((f) => f.filename).join(", ")}) and explain the key contents in natural language.`;
    const fileIds = attachedFiles.map((f) => f.file_id);

    try {
      if (useStream) {
        const uId = `u_${Date.now()}`;
        const aId = `a_${Date.now() + 1}`;
        setMessages((prev) => [
          ...prev,
          { message_id: uId, role: "user", content: promptText },
          { message_id: aId, role: "assistant", content: "", model: "streaming..." },
        ]);
        await streamNeon(
          promptText,
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
            setMessageExtras((prev) => ({
              ...prev,
              [aId]: {
                provenance: meta.provenance,
                research_sources: meta.research_sources,
                attached_files: meta.attached_files,
                diagnostics: meta,
              },
            }));
          },
          fileIds
        );
      } else {
        let cid = activeId;
        if (!cid) {
          const created = await apiFetch<any>("/api/v1/neon/conversations", {
            method: "POST",
            body: { title: promptText.slice(0, 48), agent_id: selectedAgent },
          });
          cid = created.conversation_id;
          setActiveId(cid);
          await loadBase();
        }
        const res = await apiFetch<any>(`/api/v1/neon/conversations/${cid}/messages`, {
          method: "POST",
          body: {
            content: promptText,
            file_ids: fileIds.length > 0 ? fileIds : undefined,
            enable_web_research: true,
          },
        });
        if (res.secret_interception?.warnings?.length) {
          setWarning(res.secret_interception.warnings.join(" "));
        }
        const assistantId = res.assistant_message_id || res.assistant_message?.message_id;
        const replyData = res.reply || res;
        if (assistantId) {
          setMessageExtras((prev) => ({
            ...prev,
            [assistantId]: {
              provenance: res.provenance || replyData.provenance,
              research_sources: res.research_sources || replyData.research_sources || [],
              attached_files: res.attached_files || replyData.attached_files || [],
              diagnostics: {
                execution_id: replyData.execution_id,
                provider: replyData.provider,
                model: replyData.model,
                execution_mode: replyData.execution_mode,
                fallback_used: replyData.fallback_used,
                provenance: res.provenance || replyData.provenance,
                attached_files: res.attached_files || replyData.attached_files,
                research_sources: res.research_sources || replyData.research_sources,
              },
            },
          }));
        }
        await loadMessages(cid);
      }
      setInput("");
      setAttachedFiles([]);
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

  const geminiStatus = resolveGeminiProviderStatus({ geminiDiag, health });
  const geminiConfigured = geminiStatus.configured;
  const liveInf = geminiDiag?.live_inference;
  const geminiBadgeLabel = geminiStatus.label;
  const geminiBadgeTone = geminiStatus.tone;

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`NEON INTELLIGENCE // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <div className="row">
            <StatusIndicator label={geminiBadgeLabel} tone={geminiBadgeTone} />
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => loadBase(false)}>
              <RefreshCw size={13} /> Refresh
            </button>
          </div>
        }
      />

      {error && <ErrorState message={error} onRetry={() => loadBase(false)} />}
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
                description="Ask anything in plain language, speak with voice input, take a photo, or attach images and PDFs. Live web research and VAULT protection run automatically."
              />
            ) : (
              messages.map((m) => {
                const extra = messageExtras[m.message_id];
                return (
                  <div key={m.message_id} className={`neon-bubble ${m.role === "user" ? "neon-user" : "neon-assistant"}`}>
                    <div className="row-between" style={{ marginBottom: 6 }}>
                      <span className="mono-tag">
                        {m.role === "user" ? "OPERATOR" : `NEON · ${selectedAgent}`}
                      </span>
                      <div className="row">
                        {m.model && <span className="muted mono" style={{ fontSize: 11 }}>{m.model}</span>}
                        {m.role === "assistant" && (
                          <>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => handleSpeak(m.message_id, String(m.content || ""))}
                              aria-label={speakingMsgId === m.message_id ? "Stop voice readout" : "Read response aloud"}
                              title={speakingMsgId === m.message_id ? "Stop voice readout" : "Read aloud"}
                            >
                              {speakingMsgId === m.message_id ? <VolumeX size={12} /> : <Volume2 size={12} />}
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => handleShareMessage(String(m.content || ""))}
                              aria-label="Share response"
                              title="Share"
                            >
                              <Share2 size={12} />
                            </button>
                            <button
                              type="button"
                              className="btn btn-secondary btn-sm"
                              onClick={() => handleCopyCode(m.content || "")}
                              aria-label="Copy response"
                              title="Copy"
                            >
                              {copiedFlag ? <Check size={12} /> : <Copy size={12} />}
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                    {renderFormattedMessage(String(m.content || ""), handleCopyCode)}
                    {extra?.attached_files && extra.attached_files.length > 0 && (
                      <div className="row" style={{ flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                        {extra.attached_files.map((af: any) => (
                          <span key={af.file_id || af.filename} className="pill mono">
                            {af.is_image ? "Image" : "Doc"}: {af.filename}
                          </span>
                        ))}
                      </div>
                    )}
                    {extra?.research_sources && extra.research_sources.length > 0 && (
                      <SourcesList sources={extra.research_sources} />
                    )}
                    {extra?.provenance && <ProvenanceBar provenance={extra.provenance} />}
                    {extra?.diagnostics && (
                      <TechnicalDiagnostics title="Technical Diagnostics (Authorized Debugging)" data={extra.diagnostics} />
                    )}
                  </div>
                );
              })
            )}
          </div>

          {attachedFiles.length > 0 && (
            <div className="alert-box" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
              <span className="muted" style={{ fontSize: 12 }}>Attached for Gemini analysis:</span>
              {attachedFiles.map((f) => (
                <span key={f.file_id} className="pill pill-cyan" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                  {f.is_image ? "IMG" : "FILE"} · {f.filename}
                  <button
                    type="button"
                    aria-label={`Remove ${f.filename}`}
                    onClick={() => setAttachedFiles((prev) => prev.filter((item) => item.file_id !== f.file_id))}
                    style={{ background: "none", border: 0, color: "inherit", cursor: "pointer", padding: 0, display: "inline-flex" }}
                  >
                    <X size={12} />
                  </button>
                </span>
              ))}
            </div>
          )}

          {uploadingFiles && <div className="muted mono" style={{ fontSize: 12 }}>Uploading &amp; scanning attachment(s) with AEGIS + VAULT...</div>}

          <form onSubmit={handleSend} className="row" style={{ flexWrap: "wrap", gap: 8 }}>
            <label className="btn btn-secondary btn-sm" title="Attach image, PDF, or document to NEON" aria-label="Attach files">
              <Paperclip size={14} />
              <input
                id="neon-file-attach-input"
                type="file"
                multiple
                accept="image/*,.pdf,.txt,.md,.csv,.json,.docx,.py,.ts,.tsx,.js"
                style={{ display: "none" }}
                onChange={handleAttachFiles}
              />
            </label>
            <label className="btn btn-secondary btn-sm" title="Take photo with iPhone camera" aria-label="Capture photo with camera">
              <Camera size={14} />
              <input
                id="neon-camera-capture-input"
                type="file"
                accept="image/*"
                capture="environment"
                style={{ display: "none" }}
                onChange={handleAttachFiles}
              />
            </label>
            <button
              id="neon-voice-btn"
              type="button"
              className={`btn btn-sm ${listening ? "" : "btn-secondary"}`}
              onClick={handleToggleVoiceInput}
              title={listening ? "Stop listening" : "Voice input (Speech-to-Text)"}
              aria-label={listening ? "Stop listening" : "Voice input"}
            >
              {listening ? <MicOff size={14} /> : <Mic size={14} />}
            </button>
            <input
              id="neon-chat-input"
              className="input"
              style={{ flex: 1, minWidth: 160 }}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={useStream ? "Stream response via Gemini..." : "Ask NEON anything or attach files..."}
            />
            <button
              id="neon-chat-send"
              type="submit"
              className="btn"
              disabled={sending || uploadingFiles || (!input.trim() && attachedFiles.length === 0)}
            >
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
              <Sparkles size={14} /> Create &amp; Open Chat
            </button>
          </form>
        </div>
      )}

      {/* 12. MODEL SELECTION */}
      {page.id === "models" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="card">
            <div className="card-title">
              <span>5-Tier Gemini Reasoning Assignments (Configurable + Controlled Fallback)</span>
              <div className="row">
                <StatusIndicator label={`API: ${geminiDiag?.api_mode || "generate_content"}`} tone="info" />
                <button
                  id="neon-discover-models-btn"
                  type="button"
                  className="btn btn-sm"
                  disabled={discoveringModels}
                  onClick={() => loadBase(true)}
                >
                  <RefreshCw size={12} /> {discoveringModels ? "Discovering..." : "Discover Live Models"}
                </button>
              </div>
            </div>
            <DataTable
              rows={geminiDiag?.reasoning_tiers || tiers?.tiers || []}
              rowKey={(t: any) => String(t.tier)}
              columns={[
                { key: "tier", header: "Tier", mono: true, render: (t: any) => <strong>T{t.tier}</strong> },
                { key: "primary", header: "Primary Verified Model", mono: true, render: (t: any) => <strong>{t.primary_model}</strong> },
                {
                  key: "fallback",
                  header: "Controlled Gemini Fallback Chain",
                  mono: true,
                  render: (t: any) => (t.gemini_fallback_chain || t.fallback_models || []).join(" → "),
                },
                { key: "purpose", header: "Purpose", render: (t: any) => t.purpose },
              ]}
            />
          </div>

          <div className="card">
            <div className="card-title">
              <span>
                Available Gemini Model Catalogue ({geminiDiag?.catalog?.models_discovered ?? models?.total ?? 0})
              </span>
              <StatusIndicator
                label={geminiDiag?.catalog?.source === "live_api" ? "LIVE API CATALOG" : "CONFIGURED REGISTRY"}
                tone={geminiDiag?.catalog?.source === "live_api" ? "success" : "neutral"}
              />
            </div>
            <DataTable
              rows={geminiDiag?.catalog?.available_models || models?.models || []}
              rowKey={(m: any) => m.id || `${m.provider}:${m.model}`}
              columns={[
                { key: "id", header: "Model ID", mono: true, render: (m: any) => <strong>{m.id || m.model}</strong> },
                {
                  key: "ctx",
                  header: "Context / Output",
                  mono: true,
                  render: (m: any) =>
                    m.input_token_limit
                      ? `${Number(m.input_token_limit).toLocaleString()} / ${Number(m.output_token_limit || 0).toLocaleString()}`
                      : "1,048,576 / 65,536",
                },
                {
                  key: "caps",
                  header: "Capabilities",
                  mono: true,
                  render: (m: any) =>
                    [
                      m.supports_streaming ? "Stream" : null,
                      m.supports_structured_output ? "JSON" : null,
                      m.supports_tool_calling ? "Tools" : null,
                      m.supports_interactions_api ? "Interactions" : null,
                    ]
                      .filter(Boolean)
                      .join(" · ") || "Standard",
                },
                {
                  key: "notice",
                  header: "Lifecycle / Notes",
                  render: (m: any) => m.deprecation_notice || (m.tiers ? `Assigned: T${m.tiers.join(", T")}` : "Active"),
                },
              ]}
            />
          </div>
        </div>
      )}

      {/* 13. PROVIDER CONFIGURATION */}
      {page.id === "providers" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="grid-3">
            <MetricDisplay
              label="Primary Provider"
              value={geminiDiag?.provider_label || "Google Gemini"}
              sub={`Interface: ${geminiDiag?.api_mode || "generate_content"} (Interactions adapter ready)`}
              tone={geminiConfigured ? "success" : "warn"}
            />
            <MetricDisplay
              label="Live Inference Status"
              value={liveInf?.status || (geminiConfigured ? "NOT TESTED" : "NOT CONFIGURED")}
              sub={
                liveInf?.last_model
                  ? `Last: ${liveInf.last_model} (${liveInf.last_latency_ms}ms)`
                  : "Model list alone never marks live inference verified"
              }
              tone={liveInf?.verified ? "success" : geminiConfigured ? "info" : "warn"}
            />
            <MetricDisplay
              label="Fallback & Latency"
              value={liveInf?.avg_latency_ms != null ? `${liveInf.avg_latency_ms} ms avg` : "—"}
              sub={`Live calls: ${liveInf?.total_live_calls ?? 0} · Intra-Gemini fallbacks: ${liveInf?.intra_gemini_fallback_calls ?? 0}`}
              tone="info"
            />
          </div>

          <div className="card">
            <div className="card-title">
              <span>Google Gemini Primary Diagnostics &amp; API Compatibility</span>
              <div className="row">
                <button type="button" className="btn btn-sm" onClick={() => onNavigate("agents", "evaluation")}>
                  Run Live Verification Suite
                </button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("connections", "overview")}>
                  Connections Centre
                </button>
              </div>
            </div>
            <div className="list-item" style={{ marginBottom: 10 }}>
              <div className="row-between">
                <strong>Last Successful Live Inference Check</strong>
                <span className="mono">{liveInf?.last_successful_check_at || "Not yet executed in this tenant"}</span>
              </div>
              <div className="muted" style={{ marginTop: 4 }}>
                {geminiDiag?.api_compatibility?.rationale ||
                  "generateContent is the stable default; Google Interactions API (/v1beta/interactions) is available behind GEMINI_API_MODE=interactions|auto."}
              </div>
              <div className="muted mono" style={{ fontSize: 11.5, marginTop: 6 }}>
                Timeout: {geminiDiag?.reliability_policy?.timeout_seconds ?? 25}s · Max Retries: {geminiDiag?.reliability_policy?.max_retries ?? 1} · ApprovalGates Immutable: YES
              </div>
            </div>

            <div className="grid-2">
              {["gemini", "openai", "anthropic", "ollama"].map((p) => {
                const isPrimary = p === "gemini";
                const configured = isPrimary
                  ? geminiConfigured
                  : Boolean(geminiDiag?.secondary_providers?.[p]?.configured);
                const modelLabel = isPrimary
                  ? `T1–T5 (${(geminiDiag?.reasoning_tiers || []).map((t: any) => t.primary_model).filter((v: string, i: number, a: string[]) => a.indexOf(v) === i).join(", ") || "Gemini 3.5/3.8/4"})`
                  : geminiDiag?.secondary_providers?.[p]?.model || "Optional failover";
                return (
                  <div key={p} className="list-item">
                    <div className="row-between">
                      <strong>{p.toUpperCase()} {isPrimary ? "(PRIMARY)" : "(SECONDARY)"}</strong>
                      <StatusIndicator label={configured ? "Configured" : "Not connected"} tone={configured ? "success" : "neutral"} />
                    </div>
                    <div className="muted">{modelLabel}</div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* 14. INTELLIGENCE SETTINGS */}
      {page.id === "intelligence-settings" && (
        <div className="card" style={{ maxWidth: 640 }}>
          <div className="card-title"><span>NEON Routing &amp; Reasoning Defaults</span></div>
          <form onSubmit={saveIntelligenceSettings} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <label className="muted">Default Reasoning Tier</label>
            <select className="select" value={defaultTier} onChange={(e) => setDefaultTier(e.target.value)}>
              <option value="T1">T1 — Fast Utility &amp; Classification</option>
              <option value="T2">T2 — Balanced Daily Operations</option>
              <option value="T3">T3 — Deep Technical Reasoning</option>
              <option value="T4">T4 — Multi-Agent Strategic Synthesis</option>
              <option value="T5">T5 — Maximum Verification &amp; Governance</option>
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
            <MetricDisplay label="Total Invocations" value={usage?.total_calls ?? 0} tone="info" />
            <MetricDisplay label="Total Tokens" value={usage?.total_tokens ?? 0} tone="neutral" />
            <MetricDisplay label="Est. Cost (USD)" value={`$${Number(usage?.estimated_cost_usd || 0).toFixed(4)}`} tone="success" />
          </div>
          <div className="card">
            <div className="card-title"><span>NEON Usage &amp; Provider Breakdown</span></div>
            <ReadableSummary
              data={usage || { status: "No invocations recorded yet in this tenant." }}
              diagnosticsTitle="Technical Diagnostics — Raw Usage Telemetry"
            />
          </div>
        </div>
      )}

      {/* 16. MULTIMODAL WORKSPACE */}
      {page.id === "multimodal" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span>Multimodal Vision &amp; Document Analysis</span></div>
          <textarea
            className="textarea"
            rows={2}
            value={mmPrompt}
            onChange={(e) => setMmPrompt(e.target.value)}
            placeholder="Instruction for NEON visual analysis..."
          />
          <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
            <label className="btn">
              <Upload size={14} /> Select Image for NEON Vision Analysis
              <input type="file" accept="image/*" style={{ display: "none" }} onChange={handleMultimodalUpload} />
            </label>
            <label className="btn btn-secondary">
              <Camera size={14} /> Capture Photo (Camera)
              <input type="file" accept="image/*" capture="environment" style={{ display: "none" }} onChange={handleMultimodalUpload} />
            </label>
          </div>
          {mmResult ? (
            <ReadableSummary
              title="Visual Analysis Result"
              data={mmResult}
              diagnosticsTitle="Technical Diagnostics — Visual Analysis Payload"
            />
          ) : (
            <div className="muted">Uploads are analyzed through Google Gemini Vision without fabricating findings.</div>
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
