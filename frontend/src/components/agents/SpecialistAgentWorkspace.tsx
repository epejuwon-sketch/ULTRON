import React, { useEffect, useState } from "react";
import {
  Activity,
  Check,
  Code2,
  Copy,
  Download,
  FileText,
  Landmark,
  Layers,
  Play,
  Send,
  Shield,
  Sparkles,
  Terminal,
  Upload,
} from "lucide-react";
import { apiFetch } from "../../lib/api";
import { AgentIcon } from "../../catalog/agentIcons";
import type { ModuleId } from "../../catalog/navigation";
import {
  EmptyState,
  ErrorState,
  MetricDisplay,
  StatusIndicator,
  useToast,
} from "../ui/DesignSystem";
import { ProvenanceBar, TechnicalDiagnostics } from "../ui/HumanPresentation";
import { CodingAgentWorkspace } from "./CodingAgentWorkspace";

export type SpecialistArchetype =
  | "executive"
  | "engineering"
  | "finance"
  | "marketing"
  | "sales"
  | "creative"
  | "data"
  | "security"
  | "operations"
  | "research";

export interface ArchetypeConfig {
  id: SpecialistArchetype;
  label: string;
  subtitle: string;
  accentColor: string;
  templates: Array<{ label: string; prompt: string }>;
  contextFields: Array<{ key: string; label: string; placeholder: string; type?: "text" | "select"; options?: string[] }>;
}

const RESEARCH_AGENT_IDS = new Set(["AGT-02", "AGT-10", "AGT-35", "AGT-36", "AGT-50", "AGT-56"]);

export function getAgentArchetype(agent: any): SpecialistArchetype {
  const aid = String(agent?.agent_id || "").toUpperCase();
  if (RESEARCH_AGENT_IDS.has(aid)) return "research";

  if (["AGT-01", "AGT-26", "AGT-27", "AGT-54", "AGT-60"].includes(aid)) return "executive";
  if (["AGT-03", "AGT-04", "AGT-05", "AGT-25", "AGT-28", "AGT-29", "AGT-30", "AGT-31", "AGT-32", "AGT-34"].includes(aid)) {
    return "engineering";
  }
  if (["AGT-08", "AGT-57"].includes(aid)) return "finance";
  if (["AGT-06", "AGT-37", "AGT-38", "AGT-39", "AGT-40", "AGT-41", "AGT-42"].includes(aid)) return "marketing";
  if (["AGT-07", "AGT-16", "AGT-22", "AGT-53", "AGT-55"].includes(aid)) return "sales";
  if (["AGT-12", "AGT-13", "AGT-14", "AGT-24", "AGT-43", "AGT-44", "AGT-45", "AGT-46", "AGT-47"].includes(aid)) {
    return "creative";
  }
  if (["AGT-11", "AGT-23", "AGT-48", "AGT-49", "AGT-51"].includes(aid)) return "data";
  if (["AGT-20", "AGT-33", "AGT-58"].includes(aid)) return "security";
  return "operations";
}

const ARCHETYPE_CONFIGS: Record<SpecialistArchetype, ArchetypeConfig> = {
  executive: {
    id: "executive",
    label: "Executive & Strategic Command",
    subtitle: "Cross-domain synthesis, roadmap prioritization, and ARGON DAG delegation.",
    accentColor: "#38bdf8",
    templates: [
      { label: "Executive Brief", prompt: "Prepare an executive decision brief with key risks, resource trade-offs, and concrete 30-day milestones." },
      { label: "PRD & Release Gate", prompt: "Draft a structured Product Requirements summary with acceptance criteria, dependencies, and release readiness gates." },
      { label: "Operational SLA Review", prompt: "Audit current operational bottlenecks and propose an SOP with measurable SLA targets." },
    ],
    contextFields: [
      { key: "horizon", label: "Planning Horizon", placeholder: "Q2 2026", type: "select", options: ["Immediate (7 days)", "30-Day Sprint", "Quarterly (Q2/Q3)", "Annual Roadmap"] },
      { key: "stakeholder", label: "Target Audience", placeholder: "Executive / Board / Engineering" },
    ],
  },
  engineering: {
    id: "engineering",
    label: "Software Engineering Workbench",
    subtitle: "Full-stack implementation, stack-trace debugging, schema design, and AEGIS static code scanning.",
    accentColor: "#22d3ee",
    templates: [
      { label: "Implement Endpoint / Component", prompt: "Design and implement production-ready code with input validation, error handling, and unit tests." },
      { label: "Root-Cause Debug", prompt: "Diagnose the root cause of this failure, explain the exact mechanism, and provide a minimal regression-safe patch." },
      { label: "Security & Regression Tests", prompt: "Write comprehensive pytest / unit tests covering happy paths, edge cases, and tenant-isolation boundaries." },
    ],
    contextFields: [
      { key: "stack", label: "Target Stack", placeholder: "Python / FastAPI", type: "select", options: ["Python / FastAPI", "React / TypeScript", "PostgreSQL / SQL", "Docker / CI-CD", "Cloud / Terraform"] },
      { key: "repo_scope", label: "Module / File Scope", placeholder: "e.g., backend/app/routers/agents.py" },
    ],
  },
  finance: {
    id: "finance",
    label: "Finance, Treasury & Investment Desk",
    subtitle: "Cash-flow modeling, unit economics, NGN/USD treasury allocation, and ApprovalGate > $50 governance.",
    accentColor: "#34d399",
    templates: [
      { label: "Treasury & Runway Model", prompt: "Analyze current treasury reserves, monthly burn rate, and 6-month runway sensitivity scenarios." },
      { label: "Unit Economics Breakdown", prompt: "Calculate CAC, LTV, payback period, and gross margin sensitivity for our current pricing tiers." },
      { label: "Valuation & Dilution Check", prompt: "Model cap-table dilution and post-money ownership across seed and Series A scenarios." },
    ],
    contextFields: [
      { key: "currency", label: "Reporting Currency", placeholder: "USD", type: "select", options: ["USD ($)", "NGN (₦)", "GBP (£)", "EUR (€)"] },
      { key: "proposed_spend_usd", label: "Proposed Spend (USD)", placeholder: "0 (ApprovalGate triggers > $50)" },
    ],
  },
  marketing: {
    id: "marketing",
    label: "Marketing, Growth & Brand Studio",
    subtitle: "Campaign architecture, channel funnels, brand positioning, and conversion copy.",
    accentColor: "#a78bfa",
    templates: [
      { label: "Launch Campaign Plan", prompt: "Build a multi-channel launch plan with positioning hooks, primary KPIs, and weekly execution milestones." },
      { label: "Acquisition Funnel Audit", prompt: "Identify conversion drop-offs across landing, activation, and retention stages with concrete experiments." },
      { label: "Social & Editorial Threads", prompt: "Draft 3 high-signal executive threads tailored for founders and enterprise operators." },
    ],
    contextFields: [
      { key: "channel", label: "Primary Channel", placeholder: "LinkedIn / X", type: "select", options: ["Multi-Channel GTM", "LinkedIn & X", "Paid Search / Meta", "Lifecycle Email", "Brand & Positioning"] },
      { key: "region", label: "Target Market", placeholder: "Nigeria & UK", type: "select", options: ["Global", "Nigeria (Lagos / Abuja)", "United Kingdom (London)", "United States"] },
    ],
  },
  sales: {
    id: "sales",
    label: "Sales, Comms & Stakeholder Pipeline",
    subtitle: "B2B outreach, enterprise pitch structuring, ApprovalGate communications, and support playbooks.",
    accentColor: "#fbbf24",
    templates: [
      { label: "Enterprise Outreach Sequence", prompt: "Write a concise 3-touch enterprise outreach sequence focused on measurable operational ROI." },
      { label: "Support Triage Playbook", prompt: "Create a structured customer resolution playbook with diagnostic steps and escalation triggers." },
      { label: "Vendor / Role Scorecard", prompt: "Build a weighted evaluation scorecard with objective pass/fail criteria." },
    ],
    contextFields: [
      { key: "stage", label: "Pipeline / Ticket Stage", placeholder: "Discovery", type: "select", options: ["Outbound Discovery", "Proposal & Negotiation", "Executive Approval", "Customer Onboarding", "Escalation Triage"] },
      { key: "recipient", label: "Counterparty / Account", placeholder: "e.g., Enterprise CFO / Partner Lead" },
    ],
  },
  creative: {
    id: "creative",
    label: "Creative, Design & Multimodal Studio",
    subtitle: "Visual art direction, UI systems, storyboards, 3D WebGL specs, and audio/voice production.",
    accentColor: "#f472b6",
    templates: [
      { label: "Visual & UI Spec", prompt: "Specify layout hierarchy, typography scale, dark-slate surface tokens, and responsive mobile breakpoints." },
      { label: "Media Production Brief", prompt: "Create a production-ready visual/storyboard specification with lighting, framing, and asset deliverables." },
      { label: "Investor Pitch Narrative", prompt: "Structure a 10-slide executive narrative with clear slide headlines, visual direction, and proof points." },
    ],
    contextFields: [
      { key: "medium", label: "Target Medium", placeholder: "UI / Web", type: "select", options: ["UI / Design System", "Still Image Asset", "Video / Storyboard", "3D / Three.js WebGL", "Audio / Voice", "Executive Deck"] },
      { key: "aspect_ratio", label: "Viewport / Aspect", placeholder: "16:9 / Mobile-First" },
    ],
  },
  data: {
    id: "data",
    label: "Data, Analytics & Quantitative Desk",
    subtitle: "Cohort segmentation, ETL pipelines, statistical modeling, and mathematical verification.",
    accentColor: "#38bdf8",
    templates: [
      { label: "Cohort & Funnel Analysis", prompt: "Analyze retention cohorts and conversion bottlenecks, separating correlation from causal drivers." },
      { label: "ETL & Schema Pipeline", prompt: "Design a fault-tolerant ETL ingestion pipeline with schema validation and idempotent upserts." },
      { label: "Quantitative Proof / Model", prompt: "Formulate the mathematical optimization model, state assumptions explicitly, and verify edge bounds." },
    ],
    contextFields: [
      { key: "output_style", label: "Analysis Depth", placeholder: "Executive Summary + Tables", type: "select", options: ["Executive Summary + Tables", "SQL / Python Pipeline", "Formal Mathematical Proof"] },
      { key: "dataset", label: "Dataset / Metric Scope", placeholder: "e.g., Tenant retention & latency logs" },
    ],
  },
  security: {
    id: "security",
    label: "Security, AEGIS & Compliance Desk",
    subtitle: "Zero-trust threat modeling, OWASP hardening, audit-chain integrity, and policy verification.",
    accentColor: "#f87171",
    templates: [
      { label: "OWASP Threat Model", prompt: "Conduct a threat model covering SSRF, XSS, SQLi, broken access control, and secret leakage." },
      { label: "Compliance & Audit Check", prompt: "Review tenant isolation, RBAC enforcement, and ApprovalGate auditability against zero-trust policy." },
      { label: "Incident Containment Plan", prompt: "Provide immediate containment, evidence preservation, and remediation steps for an anomalous event." },
    ],
    contextFields: [
      { key: "surface", label: "Attack / Audit Surface", placeholder: "API & Auth", type: "select", options: ["API & Authentication", "Database & Tenant Isolation", "Frontend & PWA Storage", "External Integrations & Webhooks"] },
      { key: "severity", label: "Risk Focus", placeholder: "High / Critical" },
    ],
  },
  operations: {
    id: "operations",
    label: "Operations, Knowledge & Diagnostics",
    subtitle: "Executive writing, workflow automation, memory indexing, device telemetry, and system profiling.",
    accentColor: "#94a3b8",
    templates: [
      { label: "Technical Runbook / Memo", prompt: "Draft a clear, structured operational memo with concrete action items and verification steps." },
      { label: "Automation Workflow Spec", prompt: "Design an event-driven automation workflow with retry, idempotency, and dead-letter handling." },
      { label: "System & Memory Audit", prompt: "Inspect system readiness, memory recall structure, and actionable optimization steps." },
    ],
    contextFields: [
      { key: "mode", label: "Operational Mode", placeholder: "Standard", type: "select", options: ["Operational Runbook", "Automation Pipeline", "Knowledge Synthesis", "Live Diagnostics"] },
      { key: "reference", label: "System / Doc Reference", placeholder: "e.g., PostgreSQL pooler / File Hub" },
    ],
  },
  research: {
    id: "research",
    label: "Research & Market Intelligence",
    subtitle: "Live multi-provider web retrieval, citation verification, and grounded intelligence synthesis.",
    accentColor: "#38bdf8",
    templates: [
      { label: "Market & Source Brief", prompt: "Research this topic across multiple independent sources and provide clickable citations." },
    ],
    contextFields: [],
  },
};

function renderFormattedOutput(text: string, onCopyCode: (code: string) => void) {
  const parts = (text || "").split(/(```[\s\S]*?```)/g);
  return parts.map((part, idx) => {
    if (part.startsWith("```") && part.endsWith("```")) {
      const inner = part.slice(3, -3);
      const nl = inner.indexOf("\n");
      const lang = nl >= 0 ? inner.slice(0, nl).trim() : "code";
      const code = nl >= 0 ? inner.slice(nl + 1) : inner;
      return (
        <div key={idx} className="code-wrap">
          <div className="row-between code-header">
            <span className="mono">{lang || "code"}</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => onCopyCode(code)}>
              <Copy size={12} /> Copy
            </button>
          </div>
          <pre className="code-block">{code}</pre>
        </div>
      );
    }
    return (
      <div key={idx} style={{ whiteSpace: "pre-wrap", lineHeight: 1.65 }}>
        {part}
      </div>
    );
  });
}

export function SpecialistAgentWorkspace(props: {
  agent: any;
  manifest: any;
  allAgents: any[];
  onNavigate?: (moduleId: ModuleId, subPageId?: string) => void;
  onExecutionComplete?: () => void;
}) {
  const agentId = String(props.agent?.agent_id || props.manifest?.agent_id || "AGT-01");
  if (agentId === "AGT-03") {
    return (
      <CodingAgentWorkspace
        agent={props.agent}
        manifest={props.manifest}
        onNavigate={props.onNavigate}
        onExecutionComplete={props.onExecutionComplete}
      />
    );
  }
  return <DefaultSpecialistWorkspace {...props} />;
}

function DefaultSpecialistWorkspace({
  agent,
  manifest,
  allAgents,
  onNavigate,
  onExecutionComplete,
}: {
  agent: any;
  manifest: any;
  allAgents: any[];
  onNavigate?: (moduleId: ModuleId, subPageId?: string) => void;
  onExecutionComplete?: () => void;
}) {
  const { pushToast } = useToast();
  const agentId = String(agent?.agent_id || manifest?.agent_id || "AGT-01");
  const archetype = getAgentArchetype(agent || manifest);
  const cfg = ARCHETYPE_CONFIGS[archetype];

  const [prompt, setPrompt] = useState("");
  const [reasoningTier, setReasoningTier] = useState<number>(
    Number(agent?.default_reasoning_tier || manifest?.default_reasoning_tier || 2)
  );
  const [responseFormat, setResponseFormat] = useState<"text" | "json">("text");
  const [contextValues, setContextValues] = useState<Record<string, string>>({});
  const [codeSnippet, setCodeSnippet] = useState("");
  const [invoking, setInvoking] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<any>(null);
  const [history, setHistory] = useState<Array<{ id: string; prompt: string; result: any; timestamp: string }>>([]);
  const [copied, setCopied] = useState(false);

  // Live specialist auxiliary telemetry (real backend data only)
  const [filesList, setFilesList] = useState<any[]>([]);
  const [selectedFileIds, setSelectedFileIds] = useState<string[]>([]);
  const [financeSummary, setFinanceSummary] = useState<any>(null);
  const [aegisStatus, setAegisStatus] = useState<any>(null);
  const [codeScanResult, setCodeScanResult] = useState<any>(null);
  const [scanningCode, setScanningCode] = useState(false);
  const [handoffTarget, setHandoffTarget] = useState("AGT-01");

  useEffect(() => {
    setReasoningTier(Number(agent?.default_reasoning_tier || manifest?.default_reasoning_tier || 2));
    setError("");
    setResult(null);
    setCodeScanResult(null);
    setContextValues({});

    // Fetch real contextual backend telemetry for specialized desks
    apiFetch<any>("/api/v1/files")
      .then((r) => setFilesList(r.files || []))
      .catch(() => setFilesList([]));

    if (archetype === "finance") {
      apiFetch<any>("/api/v1/finance/summary")
        .then((r) => setFinanceSummary(r))
        .catch(() => setFinanceSummary(null));
    } else if (archetype === "security") {
      apiFetch<any>("/api/v1/aegis/status")
        .then((r) => setAegisStatus(r))
        .catch(() => setAegisStatus(null));
    }
  }, [agentId, archetype]);

  async function handleCopy(text: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      pushToast("Copied to clipboard.", "success");
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      pushToast("Clipboard access unavailable.", "error");
    }
  }

  function handleDownloadMarkdown(text: string) {
    const blob = new Blob([`# ${agentId} · ${manifest?.name || agent?.name}\n\n${text}\n`], {
      type: "text/markdown;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${agentId.toLowerCase()}-output.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function handleRunCodeScan() {
    const targetCode = codeSnippet.trim() || prompt.trim();
    if (!targetCode) {
      pushToast("Enter code or a snippet to scan with AEGIS.", "error");
      return;
    }
    setScanningCode(true);
    try {
      const res = await apiFetch<any>("/api/v1/aegis/scan-code", {
        method: "POST",
        body: { code: targetCode, language: contextValues.stack?.toLowerCase().includes("type") ? "typescript" : "python" },
      });
      setCodeScanResult(res);
      pushToast("AEGIS static code scan completed.", "success");
    } catch (e: any) {
      pushToast(e.message, "error");
    } finally {
      setScanningCode(false);
    }
  }

  async function handleDispatchToCreativeQueue() {
    if (!prompt.trim()) return;
    try {
      await apiFetch("/api/v1/creative/jobs", {
        method: "POST",
        body: {
          job_type: agentId === "AGT-14" || agentId === "AGT-47" ? "video" : agentId === "AGT-45" || agentId === "AGT-46" ? "audio" : "image",
          prompt: prompt.trim(),
          agent_id: agentId,
        },
      });
      pushToast(`Queued creative production job via ${agentId}.`, "success");
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function handleSendHandoff() {
    if (!result?.output) return;
    try {
      await apiFetch("/api/v1/agents/messages", {
        method: "POST",
        body: {
          from_agent_id: agentId,
          to_agent_id: handoffTarget,
          subject: `${agentId} → ${handoffTarget} Specialist Output Handoff`,
          payload: { summary: String(result.output).slice(0, 800), execution_id: result.execution_id },
        },
      });
      pushToast(`Handed off output from ${agentId} to ${handoffTarget}.`, "success");
      onExecutionComplete?.();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function handleExecute(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim() && !codeSnippet.trim()) return;
    setInvoking(true);
    setError("");

    const fullPromptParts = [prompt.trim()];
    if (codeSnippet.trim()) {
      fullPromptParts.push(`\nCode / Technical Input:\n\`\`\`\n${codeSnippet.trim()}\n\`\`\``);
    }
    const finalPrompt = fullPromptParts.filter(Boolean).join("\n\n");

    const ctxPayload: Record<string, any> = {};
    for (const [k, v] of Object.entries(contextValues)) {
      if (v && v.trim()) ctxPayload[k] = v.trim();
    }
    if (selectedFileIds.length > 0) {
      ctxPayload.attached_file_ids = selectedFileIds;
    }

    try {
      const res = await apiFetch<any>(`/api/v1/agents/${agentId}/invoke`, {
        method: "POST",
        body: {
          prompt: finalPrompt,
          reasoning_tier: reasoningTier,
          response_format: responseFormat,
          context: Object.keys(ctxPayload).length > 0 ? ctxPayload : undefined,
        },
      });
      setResult(res);
      setHistory((prev) => [
        {
          id: res.execution_id || String(Date.now()),
          prompt: prompt.trim() || "Code / Context Analysis",
          result: res,
          timestamp: new Date().toLocaleTimeString(),
        },
        ...prev.slice(0, 9),
      ]);
      pushToast(`${agentId} execution completed (${res.model || "NEON"}).`, "success");
      onExecutionComplete?.();
    } catch (err: any) {
      setError(err.message || "Agent execution failed.");
      pushToast(err.message || "Agent execution failed.", "error");
    } finally {
      setInvoking(false);
    }
  }

  const tools: string[] = manifest?.tools || agent?.tools || [];
  const workflowSteps: string[] = manifest?.contract?.execution_workflow || [];

  return (
    <div className="specialist-workbench" data-testid={`specialist-workspace-${agentId}`}>
      {/* 1. SPECIALIST IDENTITY & CAPABILITY HEADER */}
      <div className="card specialist-header">
        <div className="row-between" style={{ flexWrap: "wrap", gap: 12 }}>
          <div className="row" style={{ gap: 12, minWidth: 0 }}>
            <span
              className="agent-icon-badge"
              style={{
                width: 44,
                height: 44,
                borderColor: `${cfg.accentColor}44`,
                color: cfg.accentColor,
              }}
            >
              <AgentIcon agentId={agentId} size={20} />
            </span>
            <div style={{ minWidth: 0 }}>
              <div className="mono" style={{ fontSize: 11, color: cfg.accentColor, letterSpacing: "0.08em" }}>
                {agentId} · {cfg.label.toUpperCase()}
              </div>
              <h2 style={{ margin: "2px 0 0", fontSize: 18, fontWeight: 700 }}>
                {manifest?.name || agent?.name || agentId}
              </h2>
              <p className="muted" style={{ margin: "3px 0 0", fontSize: 12.5 }}>
                {manifest?.role_description || agent?.role_description || cfg.subtitle}
              </p>
            </div>
          </div>

          <div className="row" style={{ flexWrap: "wrap", gap: 6 }}>
            <StatusIndicator
              label={String(agent?.capability_state || "AVAILABLE").toUpperCase()}
              tone={agent?.capability_state === "DEGRADED" || agent?.capability_state === "DISABLED" ? "warn" : "success"}
            />
            <span className="pill mono">{manifest?.permission_scope || agent?.permission_scope || "TIER_2"}</span>
            <span className="pill pill-cyan mono">Tier T{reasoningTier}</span>
          </div>
        </div>

        {/* Live Telemetry & Authorized Tools Strip */}
        <div className="kpi-strip" style={{ marginTop: 12 }}>
          <MetricDisplay
            label="Domain"
            value={manifest?.domain || agent?.domain || "Specialist"}
          />
          <MetricDisplay
            label="Completed Tasks"
            value={agent?.tasks_completed ?? 0}
            sub={`${agent?.tasks_failed ?? 0} failed`}
            tone={(agent?.tasks_failed ?? 0) > 0 ? "warn" : "success"}
          />
          <MetricDisplay
            label="Execution Engine"
            value={manifest?.execution_backing || "NEON / Gemini"}
            sub={workflowSteps.length ? workflowSteps.slice(0, 3).join(" → ") : "Governed execution"}
            tone="info"
          />
        </div>

        {tools.length > 0 && (
          <div className="row" style={{ flexWrap: "wrap", gap: 6, marginTop: 10 }}>
            <span className="muted mono" style={{ fontSize: 11 }}>TOOLS:</span>
            {tools.map((t) => (
              <span key={t} className="pill mono">{t}</span>
            ))}
          </div>
        )}
      </div>

      {/* 2. SPECIALIST DOMAIN LIVE CONTEXT PANELS */}
      {archetype === "finance" && (
        <div className="card">
          <div className="card-title">
            <span><Landmark size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Live Treasury &amp; ApprovalGate Context</span>
            {onNavigate && (
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("finance", "summary")}>
                Open Finance Centre
              </button>
            )}
          </div>
          <div className="grid-3">
            <MetricDisplay
              label="Recorded Balance"
              value={financeSummary ? `$${Number(financeSummary.net_balance_usd ?? financeSummary.total_balance_usd ?? 0).toLocaleString()}` : "Ready"}
              tone="success"
            />
            <MetricDisplay
              label="ApprovalGate Limit"
              value="$50.00 USD"
              sub="Mandatory review above limit"
              tone="warn"
            />
            <MetricDisplay
              label="Scope"
              value={manifest?.permission_scope || "TIER_3_GATED"}
              sub="Financial mutation guard"
              tone="info"
            />
          </div>
        </div>
      )}

      {archetype === "security" && (
        <div className="card">
          <div className="card-title">
            <span><Shield size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Live AEGIS Security Posture</span>
            {onNavigate && (
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("security", "overview")}>
                Open Security Centre
              </button>
            )}
          </div>
          <div className="grid-3">
            <MetricDisplay
              label="AEGIS Status"
              value={aegisStatus?.status || "ACTIVE"}
              tone="success"
            />
            <MetricDisplay
              label="Risk Score"
              value={aegisStatus?.risk_score !== undefined ? `${aegisStatus.risk_score}/100` : "Verified"}
              tone="info"
            />
            <MetricDisplay
              label="Audit Integrity"
              value="SHA-256 Chain"
              sub="Tamper-evident ledger"
              tone="success"
            />
          </div>
        </div>
      )}

      {archetype === "research" && onNavigate && (
        <div className="alert-box" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8 }}>
          <span>
            <strong>Research Specialist:</strong> Full multi-provider web retrieval &amp; editorial product reports are active in Research &amp; Intel and NEON.
          </span>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigate("research", "workspace")}>
            Open Research &amp; Intel
          </button>
        </div>
      )}

      {/* 3. WORKBENCH SPLIT: STRUCTURED TASK COMPOSER + RESULTS */}
      <div className="split-workbench">
        {/* Left: Task Input, Parameters, Context & Tools */}
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title">
            <span>
              {archetype === "engineering" ? (
                <><Code2 size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Engineering Directive &amp; Code Context</>
              ) : (
                <><Sparkles size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Specialist Task Composer</>
              )}
            </span>
            <span className="muted mono" style={{ fontSize: 11 }}>NEON → Gemini</span>
          </div>

          {/* Quick Specialist Templates */}
          {cfg.templates.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {cfg.templates.map((tpl) => (
                <button
                  key={tpl.label}
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setPrompt(tpl.prompt)}
                >
                  {tpl.label}
                </button>
              ))}
            </div>
          )}

          {/* Domain-specific Parameter Fields */}
          {cfg.contextFields.length > 0 && (
            <div className="grid-2" style={{ gap: 8 }}>
              {cfg.contextFields.map((cf) => (
                <div key={cf.key} style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                  <label className="telemetry-label" htmlFor={`ctx-${agentId}-${cf.key}`}>
                    {cf.label}
                  </label>
                  {cf.type === "select" && cf.options ? (
                    <select
                      id={`ctx-${agentId}-${cf.key}`}
                      className="select"
                      value={contextValues[cf.key] || ""}
                      onChange={(e) => setContextValues((prev) => ({ ...prev, [cf.key]: e.target.value }))}
                    >
                      <option value="">Default ({cf.placeholder})</option>
                      {cf.options.map((opt) => (
                        <option key={opt} value={opt}>{opt}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      id={`ctx-${agentId}-${cf.key}`}
                      className="input"
                      value={contextValues[cf.key] || ""}
                      onChange={(e) => setContextValues((prev) => ({ ...prev, [cf.key]: e.target.value }))}
                      placeholder={cf.placeholder}
                    />
                  )}
                </div>
              ))}
            </div>
          )}

          <form onSubmit={handleExecute} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              <label className="telemetry-label" htmlFor="agent-workspace-prompt">
                Natural-Language Objective
              </label>
              <textarea
                id="agent-workspace-prompt"
                className="textarea"
                rows={4}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder={`Describe the task for ${manifest?.name || agentId}...`}
              />
            </div>

            {/* Code / Stack-Trace Input for Engineering & Security Agents */}
            {(archetype === "engineering" || archetype === "security" || archetype === "data") && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <label className="telemetry-label" htmlFor="agent-code-context">
                  Code / Stack Trace / SQL / Config Context (Optional)
                </label>
                <textarea
                  id="agent-code-context"
                  className="textarea mono"
                  rows={4}
                  style={{ fontSize: 12 }}
                  value={codeSnippet}
                  onChange={(e) => setCodeSnippet(e.target.value)}
                  placeholder="Paste Python, TypeScript, SQL, stack trace, or config snippet..."
                />
              </div>
            )}

            {/* Attached File Context Picker from File Hub */}
            {filesList.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                <span className="telemetry-label">Attach File Hub Context ({selectedFileIds.length} selected)</span>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6, maxHeight: 72, overflowY: "auto" }}>
                  {filesList.slice(0, 8).map((f) => {
                    const checked = selectedFileIds.includes(f.file_id);
                    return (
                      <button
                        key={f.file_id}
                        type="button"
                        className={`filter-chip ${checked ? "active" : ""}`}
                        onClick={() =>
                          setSelectedFileIds((prev) =>
                            checked ? prev.filter((id) => id !== f.file_id) : [...prev, f.file_id]
                          )
                        }
                      >
                        <FileText size={11} />
                        <span>{f.filename}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Reasoning Tier & Output Format Controls */}
            <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
              <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                <select
                  aria-label="Reasoning Tier"
                  className="select"
                  style={{ width: 130 }}
                  value={reasoningTier}
                  onChange={(e) => setReasoningTier(Number(e.target.value))}
                >
                  {[1, 2, 3, 4, 5].map((t) => (
                    <option key={t} value={t}>Tier T{t}</option>
                  ))}
                </select>
                <select
                  aria-label="Output Format"
                  className="select"
                  style={{ width: 140 }}
                  value={responseFormat}
                  onChange={(e) => setResponseFormat(e.target.value as "text" | "json")}
                >
                  <option value="text">Natural Language</option>
                  <option value="json">Structured JSON</option>
                </select>
              </div>

              <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                {(archetype === "engineering" || archetype === "security") && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={scanningCode}
                    onClick={handleRunCodeScan}
                  >
                    <Shield size={13} /> {scanningCode ? "Scanning..." : "AEGIS Code Scan"}
                  </button>
                )}
                {archetype === "creative" && ["AGT-13", "AGT-14", "AGT-24", "AGT-45", "AGT-46", "AGT-47"].includes(agentId) && (
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={!prompt.trim()}
                    onClick={handleDispatchToCreativeQueue}
                  >
                    <Upload size={13} /> Queue Media Job
                  </button>
                )}
                <button
                  id="agent-workspace-submit"
                  type="submit"
                  className="btn"
                  disabled={invoking || (!prompt.trim() && !codeSnippet.trim())}
                >
                  <Play size={14} /> {invoking ? `Executing ${agentId}...` : `Execute ${agentId}`}
                </button>
              </div>
            </div>
          </form>

          {error && <ErrorState message={error} />}

          {codeScanResult && (
            <div className="list-item" style={{ borderLeft: "3px solid var(--accent)" }}>
              <div className="row-between">
                <strong>AEGIS Static Code Scan</strong>
                <StatusIndicator
                  label={codeScanResult.safe ? "CLEAN" : "FINDINGS"}
                  tone={codeScanResult.safe ? "success" : "warn"}
                />
              </div>
              <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                {codeScanResult.summary || JSON.stringify(codeScanResult.findings || [])}
              </div>
            </div>
          )}
        </div>

        {/* Right: Specialist Execution Output, Output Management, Handoff & History */}
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="card-title">
              <span><Terminal size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Execution Output</span>
              {result && (
                <div className="row" style={{ gap: 6 }}>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleCopy(result.output || "")}>
                    {copied ? <Check size={12} /> : <Copy size={12} />} Copy
                  </button>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleDownloadMarkdown(result.output || "")}>
                    <Download size={12} /> Export .md
                  </button>
                </div>
              )}
            </div>

            {invoking ? (
              <div className="state-box" style={{ minHeight: 180 }}>
                <Activity size={24} className="muted" />
                <div className="state-title">Executing {agentId} via NEON...</div>
                <div className="muted">Routing through Tier T{reasoningTier} specialist contract.</div>
              </div>
            ) : result ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div className="row-between" style={{ flexWrap: "wrap", gap: 6 }}>
                  <StatusIndicator
                    label={result.execution_mode === "gemini_live" ? "LIVE VERIFIED" : String(result.execution_mode || "COMPLETED").toUpperCase()}
                    tone={result.execution_mode === "gemini_live" ? "success" : "info"}
                  />
                  <span className="muted mono" style={{ fontSize: 11 }}>
                    {result.model} · {result.latency_ms ?? 0}ms
                  </span>
                </div>

                <div className="dispatch-output" style={{ maxHeight: 420, overflowY: "auto" }}>
                  {result.structured_output ? (
                    <pre className="code-block" style={{ margin: 0 }}>
                      {JSON.stringify(result.structured_output, null, 2)}
                    </pre>
                  ) : (
                    renderFormattedOutput(result.output || "", handleCopy)
                  )}
                </div>

                {result.provenance && <ProvenanceBar provenance={result.provenance} />}

                {/* Inter-Agent Handoff Bar */}
                <div className="row-between" style={{ flexWrap: "wrap", gap: 8, paddingTop: 6, borderTop: "1px solid var(--border)" }}>
                  <div className="row" style={{ gap: 6 }}>
                    <span className="muted mono" style={{ fontSize: 11 }}>HANDOFF TO:</span>
                    <select
                      aria-label="Handoff target agent"
                      className="select"
                      style={{ width: 170 }}
                      value={handoffTarget}
                      onChange={(e) => setHandoffTarget(e.target.value)}
                    >
                      {allAgents.slice(0, 60).map((a) => (
                        <option key={a.agent_id} value={a.agent_id}>
                          {a.agent_id} · {a.name}
                        </option>
                      ))}
                    </select>
                  </div>
                  <button type="button" className="btn btn-secondary btn-sm" onClick={handleSendHandoff}>
                    <Send size={12} /> Send Handoff
                  </button>
                </div>

                <TechnicalDiagnostics title="Technical Diagnostics — Specialist Execution" data={result} />
              </div>
            ) : (
              <EmptyState
                title={`${agentId} Ready`}
                description={`Configure parameters or select a template on the left to execute ${manifest?.name || agentId}.`}
              />
            )}
          </div>

          {/* Session Execution History */}
          {history.length > 0 && (
            <div className="card">
              <div className="card-title">
                <span><Layers size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Session Execution History ({history.length})</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {history.map((h) => (
                  <button
                    key={h.id}
                    type="button"
                    className="list-item list-item-btn"
                    onClick={() => setResult(h.result)}
                  >
                    <div className="row-between" style={{ width: "100%" }}>
                      <strong style={{ fontSize: 12.5 }}>{h.prompt.slice(0, 72)}</strong>
                      <span className="muted mono" style={{ fontSize: 11 }}>{h.timestamp}</span>
                    </div>
                    <div className="muted mono" style={{ fontSize: 11 }}>
                      {h.result.model} · {h.result.latency_ms ?? 0}ms
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
