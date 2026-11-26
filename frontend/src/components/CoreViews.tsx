import React, { useEffect, useState } from "react";
import { apiFetch, downloadAuthFile, streamNeon } from "../lib/api";

/* 1. JARVIS Conversation, SSE Streaming, ARGON Orchestration & BRIDGE Share Intake */
export function JarvisView({
  initialShare,
  pendingPrompt,
  onClearPendingPrompt,
}: {
  initialShare?: { title: string; text: string; url: string } | null;
  pendingPrompt?: string;
  onClearPendingPrompt?: () => void;
}) {
  const [conversations, setConversations] = useState<any[]>([]);
  const [activeId, setActiveId] = useState<string>("");
  const [messages, setMessages] = useState<any[]>([]);
  const [input, setInput] = useState("");
  const [mode, setMode] = useState<"chat" | "stream" | "orchestrate">("chat");
  const [warning, setWarning] = useState<string>("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function loadConversations() {
    try {
      const res = await apiFetch<any>("/api/v1/neon/conversations");
      setConversations(res.conversations || []);
      if (!activeId && res.conversations?.length) {
        setActiveId(res.conversations[0].conversation_id);
      }
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
    loadConversations();
  }, []);

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
          const fetchStatus = res.extracted_metadata?.public_fetch?.fetch_status || "PROCESSED";
          setWarning(`BRIDGE received shared item (AEGIS: ${res.aegis_url_verdict}, Fetch: ${fetchStatus}).`);
          if (res.conversation_id) {
            setActiveId(res.conversation_id);
            loadConversations();
          }
        })
        .catch((e) => setError(`BRIDGE blocked share: ${e.message}`));
    }
  }, [initialShare]);

  async function createNewChat() {
    setError("");
    const res = await apiFetch<any>("/api/v1/neon/conversations", {
      method: "POST",
      body: { title: `JARVIS Session ${new Date().toLocaleTimeString()}`, agent_id: "AGT-01" },
    });
    setActiveId(res.conversation_id);
    await loadConversations();
  }

  async function handleSend(e: React.FormEvent) {
    e.preventDefault();
    if (!input.trim()) return;
    setLoading(true);
    setError("");
    setWarning("");
    const userText = input;
    try {
      if (mode === "orchestrate") {
        const res = await apiFetch<any>("/api/v1/orchestrate", {
          method: "POST",
          body: { objective: userText, auto_execute: true },
        });
        setMessages((prev) => [
          ...prev,
          { message_id: `u_${Date.now()}`, role: "user", content: userText },
          {
            message_id: `a_${Date.now()}`,
            role: "assistant",
            model: res.neon_routing?.primary_model,
            content: `[ARGON ${res.neon_routing?.selected_agent_id} | Tier ${res.neon_routing?.reasoning_tier}] Lifecycle: ${res.task?.lifecycle_state}\nSteps: ${(res.task?.steps || []).map((s: any) => `${s.agent_id}:${s.status}`).join(" -> ")}\n${res.task?.result_summary || ""}`,
          },
        ]);
      } else if (mode === "stream") {
        const uId = `u_${Date.now()}`;
        const aId = `a_${Date.now() + 1}`;
        setMessages((prev) => [
          ...prev,
          { message_id: uId, role: "user", content: userText },
          { message_id: aId, role: "assistant", content: "", model: "streaming..." },
        ]);
        await streamNeon(
          userText,
          "AGT-01",
          (delta) => {
            setMessages((prev) =>
              prev.map((m) => (m.message_id === aId ? { ...m, content: (m.content || "") + delta } : m))
            );
          },
          (meta) => {
            setMessages((prev) =>
              prev.map((m) => (m.message_id === aId ? { ...m, model: `${meta.model} (${meta.execution_mode})` } : m))
            );
          }
        );
      } else {
        let cid = activeId;
        if (!cid) {
          const created = await apiFetch<any>("/api/v1/neon/conversations", {
            method: "POST",
            body: { title: userText.slice(0, 48), agent_id: "AGT-01" },
          });
          cid = created.conversation_id;
          setActiveId(cid);
          await loadConversations();
        }
        const res = await apiFetch<any>(`/api/v1/neon/conversations/${cid}/messages`, {
          method: "POST",
          body: { content: userText },
        });
        if (res.secret_interception?.warnings?.length) {
          setWarning(res.secret_interception.warnings.join(" "));
        }
        await loadMessages(cid);
      }
      setInput("");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="card">
      <div className="card-title">
        <span>JARVIS Command Interface (NEON + ARGON)</span>
        <div className="row">
          <button className={`btn btn-sm ${mode === "chat" ? "" : "btn-secondary"}`} onClick={() => setMode("chat")}>Chat</button>
          <button className={`btn btn-sm ${mode === "stream" ? "" : "btn-secondary"}`} onClick={() => setMode("stream")}>SSE Stream</button>
          <button className={`btn btn-sm ${mode === "orchestrate" ? "" : "btn-secondary"}`} onClick={() => setMode("orchestrate")}>Orchestrate</button>
          <button className="btn btn-secondary btn-sm" onClick={createNewChat}>New Session</button>
        </div>
      </div>

      {conversations.length > 0 && mode === "chat" && (
        <div className="row" style={{ marginBottom: 10 }}>
          <select className="select" style={{ maxWidth: 340 }} value={activeId} onChange={(e) => setActiveId(e.target.value)}>
            {conversations.map((c) => (
              <option key={c.conversation_id} value={c.conversation_id}>{c.title} ({c.agent_id})</option>
            ))}
          </select>
        </div>
      )}

      {warning && <div className="alert-box alert-warn" style={{ marginBottom: 10 }}>{warning}</div>}
      {error && <div className="alert-box alert-error" style={{ marginBottom: 10 }}>{error}</div>}

      <div style={{ display: "flex", flexDirection: "column", gap: 10, minHeight: 280, maxHeight: 440, overflowY: "auto", marginBottom: 12 }}>
        {messages.length === 0 ? (
          <div className="muted">No messages yet. Any API key, password, or raw card number entered here is intercepted by VAULT before reaching external models.</div>
        ) : (
          messages.map((m) => (
            <div key={m.message_id} className="list-item" style={{ borderColor: m.role === "user" ? "#0891b2" : "#2c3b52" }}>
              <div className="row-between">
                <span className={`pill ${m.role === "user" ? "pill-cyan" : "pill-green"}`}>{m.role.toUpperCase()}</span>
                {m.model && <span className="muted">{m.model}</span>}
              </div>
              <div style={{ whiteSpace: "pre-wrap", fontSize: 13.5, lineHeight: 1.5 }}>{m.content}</div>
            </div>
          ))
        )}
      </div>

      <form onSubmit={handleSend} className="row">
        <input
          className="input"
          style={{ flex: 1 }}
          placeholder={mode === "orchestrate" ? "Give ARGON a multi-agent objective..." : mode === "stream" ? "Stream response via NEON SSE..." : "Speak or type to JARVIS..."}
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button className="btn" type="submit" disabled={loading}>{loading ? "Processing..." : "Send"}</button>
      </form>
    </div>
  );
}

/* 2. Voice Interaction (Web Speech API + Interruptible TTS + Live Indicator) */
export function VoiceView() {
  const [listening, setListening] = useState(false);
  const [continuous, setContinuous] = useState(false);
  const [transcript, setTranscript] = useState("");
  const [reply, setReply] = useState("");
  const [statusMsg, setStatusMsg] = useState("Microphone idle.");
  const [error, setError] = useState("");

  function stopSpeaking() {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
  }

  function speakText(text: string) {
    if ("speechSynthesis" in window) {
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      utter.rate = 1.05;
      window.speechSynthesis.speak(utter);
    }
  }

  function toggleListening() {
    setError("");
    const SpeechRec = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRec) {
      setError("Web Speech Recognition is not available in this browser context (requires iPhone Safari/Chrome HTTPS + mic permission). Use the transcript box below to invoke the live voice pipeline.");
      return;
    }
    if (listening) {
      setListening(false);
      setStatusMsg("Stopped listening.");
      return;
    }
    stopSpeaking();
    const rec = new SpeechRec();
    rec.continuous = continuous;
    rec.interimResults = false;
    rec.lang = "en-US";
    rec.onstart = () => {
      setListening(true);
      setStatusMsg("LIVE MICROPHONE ACTIVE — Recording speech...");
    };
    rec.onresult = async (ev: any) => {
      const spoken = ev.results[ev.results.length - 1][0].transcript;
      setTranscript(spoken);
      await sendVoiceTurn(spoken);
    };
    rec.onerror = (ev: any) => {
      setError(`Microphone error: ${ev.error}`);
      setListening(false);
    };
    rec.onend = () => {
      setListening(false);
      setStatusMsg("Microphone idle.");
    };
    rec.start();
  }

  async function sendVoiceTurn(textToSend?: string) {
    const clean = (textToSend ?? transcript).trim();
    if (!clean) return;
    setError("");
    try {
      const res = await apiFetch<any>("/api/v1/creative/voice/turn", {
        method: "POST",
        body: { transcript: clean, mode: continuous ? "continuous" : "push_to_talk" },
      });
      setReply(res.spoken_reply);
      speakText(res.spoken_reply);
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div className="card">
      <div className="card-title">
        <span>Voice Command Interface (AGT-46)</span>
        <span className={`pill ${listening ? "pill-danger" : "pill-cyan"}`}>
          {listening ? "MIC RECORDING" : "IDLE"}
        </span>
      </div>
      <div className="row" style={{ marginBottom: 12 }}>
        <button className="btn" onClick={toggleListening}>{listening ? "Stop Microphone" : "Start Voice Capture"}</button>
        <button className="btn btn-secondary" onClick={() => setContinuous((v) => !v)}>
          Mode: {continuous ? "Continuous" : "Push-to-Talk"}
        </button>
        <button className="btn btn-danger btn-sm" onClick={stopSpeaking}>Interrupt TTS</button>
      </div>
      <div className="muted" style={{ marginBottom: 10 }}>{statusMsg}</div>
      {error && <div className="alert-box alert-error" style={{ marginBottom: 10 }}>{error}</div>}
      <div className="row" style={{ marginBottom: 12 }}>
        <input className="input" style={{ flex: 1 }} value={transcript} onChange={(e) => setTranscript(e.target.value)} placeholder="Spoken transcript (or type to test voice turn)..." />
        <button className="btn" onClick={() => sendVoiceTurn()}>Send Voice Turn</button>
      </div>
      {reply && (
        <div className="list-item">
          <span className="pill pill-green">JARVIS VOICE RESPONSE</span>
          <div style={{ whiteSpace: "pre-wrap", fontSize: 13.5 }}>{reply}</div>
        </div>
      )}
    </div>
  );
}

/* 3. Agent Centre (All 60 Specialist Agents + Individual Agent Workspace) */
export function AgentsView() {
  const [agents, setAgents] = useState<any[]>([]);
  const [filter, setFilter] = useState("");
  const [tierFilter, setTierFilter] = useState<"ALL" | "CORE_25" | "EXTENSIBLE_35">("ALL");
  const [selected, setSelected] = useState<any>(null);
  const [prompt, setPrompt] = useState("");
  const [invoking, setInvoking] = useState(false);
  const [output, setOutput] = useState<any>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [targetAgent, setTargetAgent] = useState("AGT-02");
  const [msgSubject, setMsgSubject] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<any>("/api/v1/agents")
      .then((res) => setAgents(res.agents || []))
      .catch((e) => setError(e.message));
  }, []);

  async function inspectManifest(aid: string) {
    setOutput(null);
    setError("");
    try {
      const [m, msgs] = await Promise.all([
        apiFetch<any>(`/api/v1/agents/${aid}/manifest`),
        apiFetch<any>(`/api/v1/agents/messages?agent_id=${aid}`).catch(() => ({ messages: [] })),
      ]);
      setSelected(m);
      setMessages(msgs.messages || []);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function invokeSelected() {
    if (!selected || !prompt.trim()) return;
    setInvoking(true);
    setError("");
    try {
      const res = await apiFetch<any>(`/api/v1/agents/${selected.agent_id}/invoke`, {
        method: "POST",
        body: { prompt },
      });
      setOutput(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setInvoking(false);
    }
  }

  async function sendInterAgentMsg(e: React.FormEvent) {
    e.preventDefault();
    if (!selected || !msgSubject.trim()) return;
    setError("");
    try {
      await apiFetch("/api/v1/agents/messages", {
        method: "POST",
        body: {
          from_agent_id: selected.agent_id,
          to_agent_id: targetAgent,
          subject: msgSubject.trim(),
          payload: { initiated_from: "agent_workspace" },
        },
      });
      setMsgSubject("");
      const msgs = await apiFetch<any>(`/api/v1/agents/messages?agent_id=${selected.agent_id}`);
      setMessages(msgs.messages || []);
    } catch (err: any) {
      setError(err.message);
    }
  }

  const visible = agents.filter((a) => {
    if (tierFilter !== "ALL" && a.tier !== tierFilter) return false;
    const q = filter.toLowerCase();
    return (
      a.agent_id.toLowerCase().includes(q) ||
      a.name.toLowerCase().includes(q) ||
      a.domain.toLowerCase().includes(q)
    );
  });

  return (
    <div className="grid-2">
      <div className="card">
        <div className="card-title">
          <span>Specialist Agent Directory ({visible.length}/{agents.length})</span>
          <div className="row">
            {(["ALL", "CORE_25", "EXTENSIBLE_35"] as const).map((t) => (
              <button
                key={t}
                type="button"
                className={`btn btn-sm ${tierFilter === t ? "" : "btn-secondary"}`}
                onClick={() => setTierFilter(t)}
              >
                {t === "ALL" ? "All 60" : t === "CORE_25" ? "Core 25" : "Ext 35"}
              </button>
            ))}
          </div>
        </div>
        <input
          id="agents-search-input"
          className="input"
          style={{ marginBottom: 12 }}
          placeholder="Search by agent ID (AGT-01..AGT-60), name, or domain..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        {error && <div className="alert-box alert-error" style={{ marginBottom: 10 }}>{error}</div>}
        <div style={{ display: "flex", flexDirection: "column", gap: 8, maxHeight: 560, overflowY: "auto" }}>
          {visible.map((a) => (
            <button
              key={a.agent_id}
              id={`agent-row-${a.agent_id}`}
              type="button"
              className={`list-item list-item-btn ${selected?.agent_id === a.agent_id ? "list-item-active" : ""}`}
              onClick={() => inspectManifest(a.agent_id)}
            >
              <div className="row-between" style={{ width: "100%" }}>
                <span>
                  <span className="mono" style={{ color: "var(--accent)", marginRight: 8 }}>{a.agent_id}</span>
                  <strong>{a.name}</strong>
                </span>
                <span className="pill">T{a.default_reasoning_tier}</span>
              </div>
              <div className="muted">{a.domain} · {a.permission_scope}</div>
            </button>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-title"><span>Individual Agent Workspace</span></div>
        {!selected ? (
          <div className="muted">Select any specialist agent from AGT-01 to AGT-60 to inspect its independent contract, tools, workflow, and invoke it via NEON.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="row-between">
              <div>
                <div className="mono" style={{ color: "var(--accent)", fontSize: 12 }}>{selected.agent_id} · {selected.tier}</div>
                <strong style={{ fontSize: 16 }}>{selected.name}</strong>
              </div>
              <span className="pill pill-green">{selected.execution_backing}</span>
            </div>
            <div className="muted">{selected.role_description}</div>
            <div className="row">
              <span className="pill pill-cyan">{selected.permission_scope}</span>
              {(selected.tools || []).map((t: string) => <span key={t} className="pill mono">{t}</span>)}
            </div>
            {selected.contract?.execution_workflow && (
              <div className="list-item">
                <div className="telemetry-label">EXECUTION WORKFLOW</div>
                <div className="muted mono" style={{ fontSize: 11.5 }}>
                  {selected.contract.execution_workflow.join(" → ")}
                </div>
              </div>
            )}
            <textarea
              id="agent-invoke-prompt"
              className="textarea"
              rows={3}
              placeholder={`Issue specialist directive to ${selected.agent_id} (${selected.domain})...`}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
            />
            <button id="agent-invoke-submit" className="btn" onClick={invokeSelected} disabled={invoking || !prompt.trim()}>
              {invoking ? `Invoking ${selected.agent_id}...` : `Invoke ${selected.agent_id}`}
            </button>
            {output && (
              <div className="dispatch-output">
                <div className="row-between">
                  <span className="mono-tag">{output.agent_id} · {output.execution_mode}</span>
                  <span className="muted mono">{output.model}</span>
                </div>
                <div className="dispatch-text">{output.output}</div>
              </div>
            )}

            <form onSubmit={sendInterAgentMsg} className="list-item" style={{ gap: 8 }}>
              <div className="telemetry-label">INTER-AGENT MESSAGE BUS</div>
              <div className="row">
                <input
                  className="input"
                  style={{ width: 110 }}
                  value={targetAgent}
                  onChange={(e) => setTargetAgent(e.target.value.toUpperCase())}
                  placeholder="AGT-02"
                />
                <input
                  className="input"
                  style={{ flex: 1 }}
                  value={msgSubject}
                  onChange={(e) => setMsgSubject(e.target.value)}
                  placeholder={`Send handoff subject from ${selected.agent_id}...`}
                />
                <button type="submit" className="btn btn-secondary btn-sm">Send</button>
              </div>
              {messages.length > 0 && (
                <div className="muted mono" style={{ fontSize: 11.5 }}>
                  {messages.slice(0, 3).map((m) => `${m.from_agent_id}→${m.to_agent_id}: ${m.subject}`).join(" | ")}
                </div>
              )}
            </form>
          </div>
        )}
      </div>
    </div>
  );
}

/* 4. Agent Activity & ApprovalGate */
export function ActivityView() {
  const [tasks, setTasks] = useState<any[]>([]);
  const [approvals, setApprovals] = useState<any[]>([]);
  const [title, setTitle] = useState("");
  const [objective, setObjective] = useState("");
  const [amount, setAmount] = useState("0");
  const [error, setError] = useState("");

  async function load() {
    try {
      const [tRes, aRes] = await Promise.all([
        apiFetch<any>("/api/v1/tasks"),
        apiFetch<any>("/api/v1/approvals"),
      ]);
      setTasks(tRes.tasks || []);
      setApprovals(aRes.approvals || []);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => { load(); }, []);

  async function createTask(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim() || !objective.trim()) return;
    setError("");
    try {
      await apiFetch("/api/v1/tasks", {
        method: "POST",
        body: { title, objective, financial_amount_usd: Number(amount) || 0 },
      });
      setTitle("");
      setObjective("");
      setAmount("0");
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function taskAction(taskId: string, action: "execute" | "pause" | "resume" | "cancel") {
    setError("");
    try {
      await apiFetch(`/api/v1/tasks/${taskId}/${action}`, { method: "POST" });
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function decide(approvalId: string, decision: "APPROVED" | "REJECTED") {
    setError("");
    try {
      await apiFetch(`/api/v1/approvals/${approvalId}/decide`, {
        method: "POST",
        body: { decision, note: `Decided in ULTRON PWA (${decision})` },
      });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="card">
        <div className="card-title"><span>Plan New ARGON Task (ApprovalGate Triggered &gt; $50 or High Risk)</span></div>
        {error && <div className="alert-box alert-error" style={{ marginBottom: 10 }}>{error}</div>}
        <form onSubmit={createTask} className="row">
          <input className="input" style={{ flex: 1, minWidth: 180 }} value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Task Title" />
          <input className="input" style={{ flex: 2, minWidth: 220 }} value={objective} onChange={(e) => setObjective(e.target.value)} placeholder="Objective (e.g., Market research & marketing campaign)" />
          <input className="input" style={{ width: 110 }} type="number" step="1" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="$ USD" />
          <button className="btn" type="submit">Plan DAG</button>
        </form>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title">
            <span>ApprovalGate Queue ({approvals.filter((a) => a.status === "PENDING").length} Pending)</span>
            <button className="btn btn-secondary btn-sm" onClick={load}>Refresh</button>
          </div>
          {approvals.length === 0 ? (
            <div className="muted">No approval requests recorded yet.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {approvals.map((a) => (
                <div key={a.approval_id} className="list-item">
                  <div className="row-between">
                    <strong>{a.action_type}</strong>
                    <span className={`pill ${a.status === "PENDING" ? "pill-warn" : a.status === "APPROVED" ? "pill-green" : "pill-danger"}`}>{a.status}</span>
                  </div>
                  <div className="muted">{a.reason}</div>
                  {a.status === "PENDING" && (
                    <div className="row">
                      <button className="btn btn-sm" onClick={() => decide(a.approval_id, "APPROVED")}>Approve</button>
                      <button className="btn btn-danger btn-sm" onClick={() => decide(a.approval_id, "REJECTED")}>Reject</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="card">
          <div className="card-title"><span>ARGON Task Execution Activity ({tasks.length})</span></div>
          {tasks.length === 0 ? (
            <div className="muted">No ARGON tasks created yet.</div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {tasks.map((t) => (
                <div key={t.task_id} className="list-item">
                  <div className="row-between">
                    <strong>{t.title || t.objective?.slice(0, 60)}</strong>
                    <span className="pill pill-cyan">{t.lifecycle_state || t.status}</span>
                  </div>
                  <div className="muted">Agent: {t.assigned_agent_id} · Risk: {t.risk_level} · Steps: {(t.steps || []).map((s: any) => s.agent_id).join(" → ")}</div>
                  <div className="row">
                    {(t.lifecycle_state === "READY" || t.lifecycle_state === "APPROVED") && (
                      <button className="btn btn-sm" onClick={() => taskAction(t.task_id, "execute")}>Execute</button>
                    )}
                    {t.lifecycle_state === "EXECUTING" && (
                      <button className="btn btn-secondary btn-sm" onClick={() => taskAction(t.task_id, "pause")}>Pause</button>
                    )}
                    {t.lifecycle_state === "PAUSED" && (
                      <button className="btn btn-secondary btn-sm" onClick={() => taskAction(t.task_id, "resume")}>Resume</button>
                    )}
                    {!["COMPLETED", "CANCELLED"].includes(t.lifecycle_state) && (
                      <button className="btn btn-danger btn-sm" onClick={() => taskAction(t.task_id, "cancel")}>Cancel</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/* 5. File Hub (Upload PDF/Docs/Images, Secret Redaction, Generate, Download & Send to JARVIS) */
export function FileHubView({ onAnalyzeInJarvis }: { onAnalyzeInJarvis?: (prompt: string) => void }) {
  const [files, setFiles] = useState<any[]>([]);
  const [genName, setGenName] = useState("report.md");
  const [genContent, setGenContent] = useState("# ULTRON Report\nGenerated from File Hub.");
  const [detail, setDetail] = useState<any>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      const res = await apiFetch<any>("/api/v1/files");
      setFiles(res.files || []);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setError("");
    const fd = new FormData();
    fd.append("file", f);
    try {
      const res = await apiFetch<any>("/api/v1/files/upload", { method: "POST", body: fd, isFormData: true });
      setDetail(res);
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function handleGenerate(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await apiFetch("/api/v1/files/generate", {
        method: "POST",
        body: { filename: genName, content: genContent, mime_type: "text/markdown" },
      });
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="grid-2">
      <div className="card">
        <div className="card-title"><span>File Hub — Upload & Generate</span></div>
        {error && <div className="alert-box alert-error" style={{ marginBottom: 10 }}>{error}</div>}
        <label className="btn" style={{ marginBottom: 14, width: "100%" }}>
          Upload PDF / Document / Image / Code (AEGIS + VAULT Scanned)
          <input type="file" style={{ display: "none" }} onChange={handleUpload} />
        </label>
        <form onSubmit={handleGenerate} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <input className="input" value={genName} onChange={(e) => setGenName(e.target.value)} placeholder="Filename" />
          <textarea className="textarea" rows={3} value={genContent} onChange={(e) => setGenContent(e.target.value)} />
          <button className="btn btn-secondary" type="submit">Generate & Store File</button>
        </form>
      </div>

      <div className="card">
        <div className="card-title"><span>Stored Files ({files.length})</span></div>
        {files.length === 0 ? (
          <div className="muted">No files uploaded or generated yet.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {files.map((f) => (
              <div key={f.file_id} className="list-item">
                <div className="row-between">
                  <strong>{f.filename}</strong>
                  <span className={`pill ${f.scan_status === "CLEAN" ? "pill-green" : "pill-warn"}`}>{f.scan_status}</span>
                </div>
                <div className="muted">{f.direction} · {f.size_bytes} bytes · Secrets redacted: {f.secrets_redacted}</div>
                <div className="row">
                  <button className="btn btn-secondary btn-sm" onClick={async () => setDetail(await apiFetch(`/api/v1/files/${f.file_id}`))}>Inspect</button>
                  <button className="btn btn-secondary btn-sm" onClick={() => downloadAuthFile(f.download_url, f.filename).catch((e) => setError(e.message))}>Download</button>
                  {onAnalyzeInJarvis && (
                    <button
                      className="btn btn-sm"
                      onClick={async () => {
                        const full = await apiFetch<any>(`/api/v1/files/${f.file_id}`);
                        onAnalyzeInJarvis(`Analyze uploaded file '${full.filename}' (tagged untrusted):\n\n${(full.extracted_text || "(binary file)").slice(0, 3000)}`);
                      }}
                    >
                      Analyze in JARVIS
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        {detail && (
          <div style={{ marginTop: 12 }}>
            <div className="muted">Extracted Content ({detail.filename}, extractor={detail.metadata?.extractor || "n/a"}):</div>
            <pre className="code-block">{detail.extracted_text || "(binary/empty)"}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

/* 6. Forge Workspace & 7. Live Preview */
export function ForgeView({ onOpenPreview }: { onOpenPreview: (forgeId: string) => void }) {
  const [projects, setProjects] = useState<any[]>([]);
  const [name, setName] = useState("Caravan Mobile Portal");
  const [template, setTemplate] = useState("react_vite");
  const [prompt, setPrompt] = useState("Build a responsive founder dashboard with real status indicators.");
  const [selected, setSelected] = useState<any>(null);
  const [activeFile, setActiveFile] = useState<string>("");
  const [error, setError] = useState("");

  async function load() {
    try {
      const res = await apiFetch<any>("/api/v1/forge/projects");
      setProjects(res.projects || []);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => { load(); }, []);

  async function generate(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const res = await apiFetch<any>("/api/v1/forge/projects", {
        method: "POST",
        body: { name, template, prompt },
      });
      setSelected(res);
      setActiveFile(res.file_list?.[0] || "");
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div className="grid-2">
      <div className="card">
        <div className="card-title"><span>FORGE Multi-File Project Generator</span></div>
        {error && <div className="alert-box alert-error">{error}</div>}
        <form onSubmit={generate} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Project Name" />
          <select className="select" value={template} onChange={(e) => setTemplate(e.target.value)}>
            <option value="react_vite">React + Vite App</option>
            <option value="web_app">Responsive Web App</option>
            <option value="dashboard">Analytics Dashboard</option>
            <option value="landing_page">Landing Page</option>
            <option value="fastapi_service">FastAPI Microservice</option>
          </select>
          <textarea className="textarea" rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} />
          <button className="btn" type="submit">Generate & AEGIS Verify</button>
        </form>
      </div>

      <div className="card">
        <div className="card-title"><span>FORGE Projects ({projects.length})</span></div>
        {projects.length === 0 ? (
          <div className="muted">No FORGE projects generated yet.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {projects.map((p) => (
              <div key={p.forge_id} className="list-item">
                <div className="row-between">
                  <strong>{p.name}</strong>
                  <span className={`pill ${p.status === "VERIFIED" ? "pill-green" : "pill-danger"}`}>{p.status}</span>
                </div>
                <div className="muted">{p.template} · {p.file_list?.length || 0} files</div>
                <div className="row">
                  <button className="btn btn-sm" onClick={() => onOpenPreview(p.forge_id)}>Open Live Preview</button>
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={async () => {
                      const full = await apiFetch<any>(`/api/v1/forge/projects/${p.forge_id}`);
                      setSelected(full);
                      setActiveFile(full.file_list?.[0] || "");
                    }}
                  >
                    Inspect Files
                  </button>
                  {p.archive_download_url && (
                    <button
                      className="btn btn-secondary btn-sm"
                      onClick={() => downloadAuthFile(p.archive_download_url, `${p.name.toLowerCase().replace(/\s+/g, "_")}.zip`).catch((e) => setError(e.message))}
                    >
                      Download ZIP
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
        {selected && (
          <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="row">
              {(selected.file_list || []).map((fn: string) => (
                <button key={fn} className={`btn btn-sm ${activeFile === fn ? "" : "btn-secondary"}`} onClick={() => setActiveFile(fn)}>
                  {fn}
                </button>
              ))}
            </div>
            {activeFile && selected.files?.[activeFile] !== undefined && (
              <pre className="code-block">{selected.files[activeFile]}</pre>
            )}
            <div className="muted">Build & AEGIS Logs:</div>
            <pre className="code-block">{(selected.build_logs || []).join("\n")}</pre>
          </div>
        )}
      </div>
    </div>
  );
}

export function PreviewView({ forgeId }: { forgeId: string }) {
  const [projects, setProjects] = useState<any[]>([]);
  const [activeId, setActiveId] = useState(forgeId);
  const [project, setProject] = useState<any>(null);
  const [viewport, setViewport] = useState<"mobile" | "tablet" | "desktop">("mobile");

  useEffect(() => {
    apiFetch<any>("/api/v1/forge/projects").then((res) => {
      const list = res.projects || [];
      setProjects(list);
      if (!activeId && list.length) setActiveId(list[0].forge_id);
    });
  }, []);

  useEffect(() => {
    if (forgeId) setActiveId(forgeId);
  }, [forgeId]);

  useEffect(() => {
    if (activeId) {
      apiFetch<any>(`/api/v1/forge/projects/${activeId}`).then(setProject).catch(() => setProject(null));
    }
  }, [activeId]);

  const width = viewport === "mobile" ? 390 : viewport === "tablet" ? 768 : "100%";

  return (
    <div className="card">
      <div className="card-title">
        <span>Sandboxed Live Preview</span>
        <div className="row">
          <select className="select" style={{ width: 200 }} value={activeId} onChange={(e) => setActiveId(e.target.value)}>
            <option value="">Select FORGE project...</option>
            {projects.map((p) => <option key={p.forge_id} value={p.forge_id}>{p.name}</option>)}
          </select>
          <button className={`btn btn-sm ${viewport === "mobile" ? "" : "btn-secondary"}`} onClick={() => setViewport("mobile")}>iPhone</button>
          <button className={`btn btn-sm ${viewport === "tablet" ? "" : "btn-secondary"}`} onClick={() => setViewport("tablet")}>Tablet</button>
          <button className={`btn btn-sm ${viewport === "desktop" ? "" : "btn-secondary"}`} onClick={() => setViewport("desktop")}>Desktop</button>
        </div>
      </div>

      {!project?.preview_html ? (
        <div className="muted">Generate a verified project in FORGE Workspace to render its sandboxed Live Preview.</div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12, alignItems: "center" }}>
          <iframe
            title="ULTRON Live Preview"
            sandbox="allow-scripts"
            srcDoc={project.preview_html}
            style={{ width, maxWidth: "100%", height: 500, border: "1px solid #334155", borderRadius: 12, background: "#0f172a" }}
          />
          <div style={{ width: "100%" }}>
            <div className="muted">Verification & Build Logs:</div>
            <pre className="code-block">{(project.build_logs || []).join("\n")}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
