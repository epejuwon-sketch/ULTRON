import React, { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock,
  ExternalLink,
  Layers,
  Mic,
  MicOff,
  Play,
  RotateCcw,
  Send,
  Shield,
  Sparkles,
  Terminal,
} from "lucide-react";
import { apiFetch } from "../lib/api";
import { ModuleId } from "../catalog/navigation";
import { ModulePageProps } from "../types/module";

export type ExecutionState =
  | "IDLE"
  | "UNDERSTANDING"
  | "PLANNING"
  | "RESEARCHING"
  | "EXECUTING"
  | "AWAITING_APPROVAL"
  | "VERIFYING"
  | "COMPLETED"
  | "FAILED"
  | "BLOCKED";

interface TranscriptStep {
  state: ExecutionState;
  timestamp: string;
  message: string;
  details?: Record<string, any>;
}

interface CommandExecutionResult {
  command_id: string;
  prompt: string;
  voice_input: boolean;
  status: ExecutionState;
  assigned_agent: {
    agent_id: string;
    name: string;
    domain: string;
  };
  summary: string;
  transcript: TranscriptStep[];
  planned_steps: Array<{ step: number; action: string; agent: string }>;
  verification_checks: Array<{ check: string; status: string; details: string }>;
  relevant_page: {
    page_id: string;
    number: number;
    module: ModuleId;
    subpage: string;
    label: string;
  };
  duration_ms: number;
  executed_at: string;
}

export default function MasterTerminalPage({
  user,
  device,
  onNavigate,
  pendingPrompt,
  onClearPendingPrompt,
}: ModulePageProps) {
  const [prompt, setPrompt] = useState(pendingPrompt || "");
  const [currentState, setCurrentState] = useState<ExecutionState>("IDLE");
  const [activeResult, setActiveResult] = useState<CommandExecutionResult | null>(null);
  const [history, setHistory] = useState<CommandExecutionResult[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isListening, setIsListening] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (pendingPrompt) {
      setPrompt(pendingPrompt);
      if (onClearPendingPrompt) onClearPendingPrompt();
      handleExecuteCommand(pendingPrompt, false);
    }
  }, [pendingPrompt]);

  // Load history on mount
  useEffect(() => {
    loadHistory();
  }, []);

  const loadHistory = async () => {
    try {
      const data = await apiFetch<{ history: CommandExecutionResult[] }>("/api/v1/terminal/history");
      if (data && data.history) {
        setHistory(data.history);
        if (data.history.length > 0 && !activeResult) {
          setActiveResult(data.history[0]);
          setCurrentState(data.history[0].status);
        }
      }
    } catch {
      // Fallback empty history
    }
  };

  const handleExecuteCommand = async (inputPrompt?: string, voice: boolean = false) => {
    const textToRun = (inputPrompt || prompt).trim();
    if (!textToRun || isSubmitting) return;

    setIsSubmitting(true);
    setErrorMessage("");
    setCurrentState("UNDERSTANDING");

    try {
      // Transition states visually for responsiveness while backend processes
      const timer1 = setTimeout(() => setCurrentState("PLANNING"), 200);
      const timer2 = setTimeout(() => setCurrentState("EXECUTING"), 450);

      const res = await apiFetch<CommandExecutionResult>("/api/v1/terminal/command", {
        method: "POST",
        body: {
          prompt: textToRun,
          voice_input: voice,
        },
      });

      clearTimeout(timer1);
      clearTimeout(timer2);

      setActiveResult(res);
      setCurrentState(res.status);
      setHistory((prev) => [res, ...prev.filter((h) => h.command_id !== res.command_id)]);
      setPrompt("");
    } catch (err: any) {
      setCurrentState("FAILED");
      setErrorMessage(err.message || "Execution failed. Check backend connectivity or permissions.");
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleToggleVoice = () => {
    if (typeof window === "undefined") return;
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) {
      alert("Speech recognition is not supported in this browser. Please use keyboard input.");
      return;
    }

    if (isListening) {
      setIsListening(false);
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.lang = "en-US";
      recognition.interimResults = false;
      recognition.maxAlternatives = 1;

      setIsListening(true);
      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        setPrompt(transcript);
        setIsListening(false);
        handleExecuteCommand(transcript, true);
      };
      recognition.onerror = () => setIsListening(false);
      recognition.onend = () => setIsListening(false);
      recognition.start();
    } catch {
      setIsListening(false);
    }
  };

  const renderStateBadge = (state: ExecutionState) => {
    const config: Record<ExecutionState, { color: string; border: string; bg: string; dot: string }> = {
      IDLE: { color: "#94a3b8", border: "#475569", bg: "rgba(148, 163, 184, 0.1)", dot: "#94a3b8" },
      UNDERSTANDING: { color: "#38bdf8", border: "#0284c7", bg: "rgba(56, 189, 248, 0.15)", dot: "#38bdf8" },
      PLANNING: { color: "#818cf8", border: "#4f46e5", bg: "rgba(129, 140, 248, 0.15)", dot: "#818cf8" },
      RESEARCHING: { color: "#c084fc", border: "#9333ea", bg: "rgba(192, 132, 252, 0.15)", dot: "#c084fc" },
      EXECUTING: { color: "#facc15", border: "#ca8a04", bg: "rgba(250, 204, 21, 0.15)", dot: "#facc15" },
      AWAITING_APPROVAL: { color: "#fb923c", border: "#ea580c", bg: "rgba(251, 146, 60, 0.15)", dot: "#fb923c" },
      VERIFYING: { color: "#2dd4bf", border: "#0d9488", bg: "rgba(45, 212, 191, 0.15)", dot: "#2dd4bf" },
      COMPLETED: { color: "#4ade80", border: "#16a34a", bg: "rgba(74, 222, 128, 0.15)", dot: "#4ade80" },
      FAILED: { color: "#f87171", border: "#dc2626", bg: "rgba(248, 113, 113, 0.15)", dot: "#f87171" },
      BLOCKED: { color: "#f43f5e", border: "#e11d48", bg: "rgba(244, 63, 94, 0.15)", dot: "#f43f5e" },
    };

    const c = config[state] || config.IDLE;
    return (
      <div
        className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded font-mono text-[11px] font-bold tracking-wider"
        style={{
          color: c.color,
          border: `1px solid ${c.border}`,
          background: c.bg,
        }}
      >
        <span className="w-2 h-2 rounded-full" style={{ background: c.dot, boxShadow: `0 0 6px ${c.dot}` }} />
        {state}
      </div>
    );
  };

  return (
    <div
      className="master-terminal-page flex flex-col gap-4 w-full max-w-7xl mx-auto p-3 sm:p-5 text-zinc-100 rounded-xl"
      style={{
        background: "radial-gradient(circle at 50% 0%, #0d121d 0%, #05070c 100%)",
        border: "1px solid rgba(148, 163, 184, 0.2)",
        boxShadow: "0 8px 32px rgba(0, 0, 0, 0.8)",
      }}
    >
      {/* Top Banner with Navigation Route Back to Master Schematic */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-zinc-800">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => onNavigate("command", "home")}
            className="flex items-center gap-1 px-2.5 py-1 rounded bg-zinc-900 border border-zinc-700 hover:border-cyan-400 font-mono text-[11px] text-zinc-300 hover:text-cyan-400 transition-colors"
          >
            ← MASTER SCHEMATIC (112)
          </button>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold text-red-500 bg-red-950/40 border border-red-800/60 px-1.5 py-0.5 rounded">
                PAGE 112
              </span>
              <strong className="text-base text-zinc-100 tracking-wide">ULTRON MASTER TERMINAL</strong>
            </div>
            <div className="font-mono text-[10px] text-zinc-400">
              CENTRAL NATURAL-LANGUAGE INTERACTION // NEON &amp; ARGON EXECUTION TRUTH
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className="font-mono text-xs text-zinc-400">EXECUTION STATE:</span>
          {renderStateBadge(currentState)}
        </div>
      </div>

      {/* Suggested Quick Commands */}
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-[10px] text-zinc-400 font-bold mr-1">QUICK DIRECTIVES:</span>
        {[
          "Run full system diagnostics and check health probes",
          "Inspect CARAVAN funding opportunities and verify under-18 eligibility rules",
          "Evaluate AEGIS security posture and hash-chained audit ledger",
          "Inspect ORBIT multi-device mesh and connected desktop node",
          "Transfer 500,000 NGN to external vendor (Test ApprovalGate)",
        ].map((cmd, idx) => (
          <button
            key={idx}
            type="button"
            className="px-2.5 py-1 rounded bg-zinc-900/80 border border-zinc-800 hover:border-zinc-600 text-zinc-300 hover:text-cyan-300 font-mono text-[10px] transition-colors"
            onClick={() => {
              setPrompt(cmd);
              handleExecuteCommand(cmd, false);
            }}
          >
            {cmd}
          </button>
        ))}
      </div>

      {/* Main Terminal Split View */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Left Column: Command Transcript & Execution Evidence */}
        <div className="lg:col-span-8 flex flex-col gap-3">
          {/* Active Terminal Display Box */}
          <div
            className="p-4 rounded-lg flex flex-col gap-3 min-h-[360px] max-h-[560px] overflow-y-auto"
            style={{
              background: "rgba(10, 15, 26, 0.9)",
              border: "1px solid rgba(56, 189, 248, 0.25)",
              boxShadow: "inset 0 0 20px rgba(0, 0, 0, 0.8)",
            }}
          >
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <Terminal size={15} className="text-cyan-400" />
                <span className="font-mono text-xs font-bold text-zinc-200">TERMINAL EXECUTION LOG</span>
              </div>
              {activeResult && (
                <div className="font-mono text-[10px] text-zinc-400">
                  ID: {activeResult.command_id} · DURATION: {activeResult.duration_ms}ms
                </div>
              )}
            </div>

            {errorMessage && (
              <div className="flex items-center gap-2 p-3 rounded bg-red-950/60 border border-red-800 text-red-200 font-mono text-xs">
                <AlertCircle size={16} className="text-red-400 shrink-0" />
                <div>{errorMessage}</div>
              </div>
            )}

            {activeResult ? (
              <div className="flex flex-col gap-3">
                {/* Prompt Card */}
                <div className="p-3 rounded bg-zinc-950/80 border border-zinc-800 flex flex-col gap-1">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] text-zinc-400 uppercase tracking-wider">
                      DIRECTIVE / OBJECTIVE
                    </span>
                    {activeResult.voice_input && (
                      <span className="font-mono text-[9px] text-cyan-400 bg-cyan-950/60 border border-cyan-800 px-1 rounded">
                        VOICE INPUT
                      </span>
                    )}
                  </div>
                  <div className="font-sans text-sm font-semibold text-zinc-100">{activeResult.prompt}</div>
                </div>

                {/* Assigned Specialist Agent */}
                <div className="flex items-center justify-between p-2.5 rounded bg-zinc-900/60 border border-zinc-800">
                  <div className="flex items-center gap-2">
                    <Bot size={16} className="text-emerald-400" />
                    <div>
                      <div className="font-mono text-xs font-bold text-zinc-100">
                        {activeResult.assigned_agent.name} ({activeResult.assigned_agent.agent_id})
                      </div>
                      <div className="font-mono text-[9px] text-zinc-400">
                        DOMAIN: {activeResult.assigned_agent.domain}
                      </div>
                    </div>
                  </div>
                  {renderStateBadge(activeResult.status)}
                </div>

                {/* Truthful Transcript Steps Sequence */}
                <div className="flex flex-col gap-2 my-1">
                  <span className="font-mono text-[10px] text-zinc-400 font-bold uppercase tracking-wider">
                    STATE TRANSITIONS &amp; VERIFIED TIMELINE
                  </span>
                  {activeResult.transcript.map((step, sIdx) => (
                    <div
                      key={sIdx}
                      className="p-2.5 rounded bg-zinc-950/60 border border-zinc-800/80 flex flex-col gap-1 font-mono text-xs"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          {renderStateBadge(step.state)}
                          <span className="text-zinc-200">{step.message}</span>
                        </div>
                        <span className="text-[9px] text-zinc-500">
                          {new Date(step.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                      {step.details && Object.keys(step.details).length > 0 && (
                        <div className="text-[10px] text-zinc-400 bg-black/40 p-1.5 rounded overflow-x-auto">
                          {JSON.stringify(step.details)}
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {/* Verification Checks */}
                {activeResult.verification_checks.length > 0 && (
                  <div className="p-3 rounded bg-zinc-950/80 border border-emerald-900/40 flex flex-col gap-2">
                    <div className="flex items-center gap-2 text-emerald-400 font-mono text-xs font-bold">
                      <CheckCircle2 size={14} />
                      POST-EXECUTION VERIFICATION ASSERTIONS
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                      {activeResult.verification_checks.map((chk, cIdx) => (
                        <div key={cIdx} className="p-2 rounded bg-black/60 border border-zinc-800 font-mono text-[10px]">
                          <div className="text-zinc-300 font-bold">{chk.check}</div>
                          <div className="text-emerald-400">{chk.status}</div>
                          <div className="text-zinc-500 text-[9px] truncate">{chk.details}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Relevant System Page Handoff Link */}
                {activeResult.relevant_page && (
                  <div className="flex items-center justify-between p-3 rounded bg-cyan-950/30 border border-cyan-800/50">
                    <div>
                      <div className="font-mono text-[10px] text-cyan-400 uppercase tracking-wider font-bold">
                        RECOMMENDED SYSTEM PAGE
                      </div>
                      <div className="font-sans text-xs font-bold text-zinc-100">
                        Page {activeResult.relevant_page.page_id} — {activeResult.relevant_page.label}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        onNavigate(activeResult.relevant_page.module, activeResult.relevant_page.subpage)
                      }
                      className="px-3 py-1.5 rounded bg-cyan-500/20 border border-cyan-400 text-cyan-300 hover:bg-cyan-500/30 font-mono text-xs font-bold flex items-center gap-1 transition-colors"
                    >
                      OPEN PAGE {activeResult.relevant_page.page_id} <ArrowRight size={12} />
                    </button>
                  </div>
                )}
              </div>
            ) : (
              <div className="flex flex-col items-center justify-center my-auto py-12 text-center text-zinc-400 font-mono text-xs">
                <Terminal size={32} className="text-zinc-600 mb-2" />
                <div>MASTER TERMINAL READY FOR NATURAL-LANGUAGE DIRECTIVES</div>
                <div className="text-zinc-500 text-[10px] mt-1 max-w-md">
                  Ask questions, assign multi-agent tasks, request deep research, or execute system diagnostics.
                  All states are truthfully verified before reporting completion.
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Terminal Input Box with Speech Recognition */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleExecuteCommand();
            }}
            className="flex items-center gap-2 p-2 rounded-lg"
            style={{
              background: "linear-gradient(90deg, rgba(15, 23, 42, 0.95) 0%, rgba(30, 41, 59, 0.9) 100%)",
              border: "1px solid rgba(56, 189, 248, 0.35)",
            }}
          >
            <button
              type="button"
              onClick={handleToggleVoice}
              className={`p-2.5 rounded-full transition-all flex items-center justify-center ${
                isListening
                  ? "bg-red-500 text-white animate-pulse shadow-[0_0_12px_rgba(239,68,68,0.5)]"
                  : "bg-zinc-800 text-zinc-300 hover:text-cyan-400 hover:bg-zinc-700"
              }`}
              title={isListening ? "Listening... click to stop" : "Voice input / Speech command"}
            >
              {isListening ? <MicOff size={16} /> : <Mic size={16} />}
            </button>

            <input
              type="text"
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Enter objective, research question, or system directive for NEON & ARGON..."
              className="flex-1 bg-transparent border-none outline-none font-mono text-xs text-zinc-100 placeholder:text-zinc-500 px-2 py-1"
              disabled={isSubmitting}
            />

            <button
              type="submit"
              disabled={!prompt.trim() || isSubmitting}
              className="px-4 py-2 rounded font-mono text-xs font-bold text-black bg-cyan-400 hover:bg-cyan-300 disabled:opacity-40 disabled:cursor-not-allowed transition-all flex items-center gap-1.5 shadow-[0_0_12px_rgba(56,189,248,0.4)]"
            >
              {isSubmitting ? (
                <>
                  <span className="w-2.5 h-2.5 rounded-full bg-black animate-ping" />
                  VERIFYING...
                </>
              ) : (
                <>
                  <Send size={13} />
                  EXECUTE
                </>
              )}
            </button>
          </form>
        </div>

        {/* Right Column: Execution History & Telemetry */}
        <div className="lg:col-span-4 flex flex-col gap-3">
          <div
            className="p-3.5 rounded-lg flex flex-col gap-2.5"
            style={{
              background: "rgba(15, 23, 42, 0.6)",
              border: "1px solid rgba(148, 163, 184, 0.15)",
            }}
          >
            <div className="flex items-center justify-between pb-2 border-b border-zinc-800">
              <span className="font-mono text-xs font-bold text-zinc-200">RECENT COMMANDS</span>
              <button
                type="button"
                onClick={loadHistory}
                className="text-zinc-400 hover:text-zinc-200 p-1"
                title="Refresh history"
              >
                <RotateCcw size={12} />
              </button>
            </div>

            <div className="flex flex-col gap-2 max-h-[460px] overflow-y-auto">
              {history.map((h) => (
                <button
                  key={h.command_id}
                  type="button"
                  onClick={() => {
                    setActiveResult(h);
                    setCurrentState(h.status);
                  }}
                  className={`p-2.5 rounded text-left flex flex-col gap-1 transition-all ${
                    activeResult?.command_id === h.command_id
                      ? "bg-cyan-950/40 border border-cyan-400"
                      : "bg-zinc-950/60 border border-zinc-800 hover:border-zinc-600"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[9px] text-zinc-400">{h.command_id}</span>
                    {renderStateBadge(h.status)}
                  </div>
                  <div className="font-sans text-xs font-semibold text-zinc-100 truncate">{h.prompt}</div>
                  <div className="flex items-center justify-between font-mono text-[9px] text-zinc-400">
                    <span>{h.assigned_agent.agent_id}</span>
                    <span>{h.duration_ms}ms</span>
                  </div>
                </button>
              ))}

              {history.length === 0 && (
                <div className="py-8 text-center text-zinc-500 font-mono text-xs">
                  No previous commands recorded for this session.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
