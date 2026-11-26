export type ModuleId =
  | "command"
  | "neon"
  | "argon"
  | "agents"
  | "connections"
  | "files"
  | "projects"
  | "research"
  | "creative"
  | "pulse"
  | "security"
  | "finance"
  | "caravan"
  | "devices"
  | "settings"
  | "terminal";

export type PageCategory =
  | "Systems & Diagnostics"
  | "Orbit Device Management"
  | "Settings"
  | "Master Terminal";

export interface PageDef {
  id: string;
  number: number;
  pageId: string; // e.g., "001", "086", "112"
  module: ModuleId;
  label: string;
  category: PageCategory;
  subsystem: string;
  description: string;
  keywords: string[];
  status?: "VERIFIED" | "ONLINE" | "STANDBY" | "PROTECTED";
  primaryAgent?: string | null;
  supportingAgents?: string[];
  backendService?: string;
  tools?: string[];
  requiredPermissions?: string[];
  operationalStatus?: string;
  integrationStatus?: "VERIFIED" | "NOT VERIFIED";
}

export interface ModuleDef {
  id: ModuleId;
  label: string;
  shortLabel: string;
  category: PageCategory;
  group: "Core Command" | "Intelligence & Execution" | "Workspace & Media" | "Operations & System";
  description: string;
  defaultSubPage: string;
  subPages: PageDef[];
}

export const MODULES: ModuleDef[] = [
  // -------------------------------------------------------------
  // 01-90 SYSTEMS & DIAGNOSTICS
  // -------------------------------------------------------------
  {
    id: "command",
    label: "Command Centre",
    shortLabel: "Command",
    category: "Systems & Diagnostics",
    group: "Core Command",
    description: "Central orbital operating system command interface, live telemetry, activity, and health probes.",
    defaultSubPage: "home",
    subPages: [
      { id: "home", number: 1, pageId: "001", module: "command", label: "Command Center / Earth Globe", category: "Systems & Diagnostics", subsystem: "Core Command", description: "Central orbital Earth interface, live telemetry, and universal NEON/ARGON command dispatch.", keywords: ["home", "earth", "globe", "command", "telemetry"], status: "VERIFIED" , primaryAgent: "AGT-01", supportingAgents: ["AGT-59", "AGT-19"], backendService: "realtime_hub & neon_router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "overview", number: 2, pageId: "002", module: "command", label: "Global System Overview", category: "Systems & Diagnostics", subsystem: "Core Command", description: "Cross-subsystem operational summary across agents, tasks, storage, memory, and providers.", keywords: ["overview", "metrics", "summary", "system"], status: "VERIFIED" , primaryAgent: "AGT-59", supportingAgents: ["AGT-01", "AGT-23"], backendService: "platform_modules_service & monitoring", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "activity", number: 3, pageId: "003", module: "command", label: "Live Activity Feed", category: "Systems & Diagnostics", subsystem: "Core Command", description: "Real-time tenant activity feed across tasks, agent executions, and audit events.", keywords: ["activity", "feed", "events", "realtime"], status: "ONLINE" , primaryAgent: "AGT-20", supportingAgents: ["AGT-18", "AGT-58"], backendService: "realtime_hub & audit", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "notifications", number: 4, pageId: "004", module: "command", label: "System Notifications", category: "Systems & Diagnostics", subsystem: "Core Command", description: "System alerts, approval triggers, operational events, and unread queue.", keywords: ["alerts", "inbox", "bell", "notifications"], status: "ONLINE" , primaryAgent: "AGT-16", supportingAgents: ["AGT-01", "AGT-18"], backendService: "notification_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "recent-tasks", number: 5, pageId: "005", module: "command", label: "Recent Tasks Lifecycle", category: "Systems & Diagnostics", subsystem: "Core Command", description: "Active and completed task lifecycles with execute, pause, resume, retry, and cancel controls.", keywords: ["tasks", "lifecycle", "queue", "execution"], status: "VERIFIED" , primaryAgent: "AGT-27", supportingAgents: ["AGT-01", "AGT-25"], backendService: "argon_orchestrator", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "quick-actions", number: 6, pageId: "006", module: "command", label: "Quick Action Launchers", category: "Systems & Diagnostics", subsystem: "Core Command", description: "Direct operational launchers for NEON, ARGON, AEGIS scans, TURBO benchmarks, and File Hub.", keywords: ["actions", "shortcuts", "launch", "triggers"], status: "VERIFIED" , primaryAgent: "AGT-01", supportingAgents: ["AGT-18", "AGT-20"], backendService: "argon_orchestrator & neon_router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "system-health", number: 7, pageId: "007", module: "command", label: "System Health & Probes", category: "Systems & Diagnostics", subsystem: "Core Command", description: "Live liveness/readiness probes, PostgreSQL pooler diagnostics, and Prometheus metrics.", keywords: ["health", "ready", "database", "prometheus", "probes"], status: "VERIFIED" , primaryAgent: "AGT-59", supportingAgents: ["AGT-31", "AGT-30"], backendService: "health & monitoring", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },
  {
    id: "neon",
    label: "NEON Intelligence",
    shortLabel: "NEON",
    category: "Systems & Diagnostics",
    group: "Core Command",
    description: "Shared intelligence layer powered by Gemini with streaming, multimodal analysis, and VAULT secret interception.",
    defaultSubPage: "chat",
    subPages: [
      { id: "chat", number: 8, pageId: "008", module: "neon", label: "NEON Chat Console", category: "Systems & Diagnostics", subsystem: "Intelligence", description: "Streaming intelligence console with code formatting, file attachment, agent handoff, and VAULT protection.", keywords: ["chat", "stream", "gemini", "console"], status: "VERIFIED" , primaryAgent: "AGT-01", supportingAgents: ["AGT-02", "AGT-03", "AGT-21"], backendService: "neon_router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "conversations", number: 9, pageId: "009", module: "neon", label: "Conversation History", category: "Systems & Diagnostics", subsystem: "Intelligence", description: "Browse, search, and resume persisted tenant intelligence conversations.", keywords: ["history", "threads", "sessions"], status: "VERIFIED" , primaryAgent: "AGT-21", supportingAgents: ["AGT-01"], backendService: "neon_router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "new-conversation", number: 10, pageId: "010", module: "neon", label: "New Agent Conversation", category: "Systems & Diagnostics", subsystem: "Intelligence", description: "Start a fresh session bound directly to any of the 60 specialist agents.", keywords: ["new", "session", "specialist"], status: "VERIFIED" , primaryAgent: "AGT-01", supportingAgents: ["AGT-60"], backendService: "neon_router & agent_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "models", number: 11, pageId: "011", module: "neon", label: "Model Selection & Tiers", category: "Systems & Diagnostics", subsystem: "Intelligence", description: "Inspect active Gemini models, reasoning tiers T1–T5, and latency/cost profiles.", keywords: ["models", "gemini", "tiers", "reasoning"], status: "VERIFIED" , primaryAgent: "AGT-60", supportingAgents: ["AGT-59"], backendService: "neon_providers", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "providers", number: 12, pageId: "012", module: "neon", label: "Provider Health & Failover", category: "Systems & Diagnostics", subsystem: "Intelligence", description: "Honest live readiness of Gemini primary and OpenAI, Anthropic, Ollama failovers.", keywords: ["providers", "llm", "failover", "health"], status: "VERIFIED" , primaryAgent: "AGT-59", supportingAgents: ["AGT-60", "AGT-30"], backendService: "gemini_connection_service & neon_providers", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "intelligence-settings", number: 13, pageId: "013", module: "neon", label: "Intelligence & Routing Settings", category: "Systems & Diagnostics", subsystem: "Intelligence", description: "Default temperature, reasoning tier, structured output mode, and routing preferences.", keywords: ["settings", "temperature", "routing", "config"], status: "VERIFIED" , primaryAgent: "AGT-01", supportingAgents: ["AGT-60"], backendService: "settings_service & neon_router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "execution-history", number: 14, pageId: "014", module: "neon", label: "Execution Telemetry & Cost", category: "Systems & Diagnostics", subsystem: "Intelligence", description: "Token usage, latency, execution mode, and cost telemetry across NEON invocations.", keywords: ["usage", "tokens", "cost", "telemetry"], status: "VERIFIED" , primaryAgent: "AGT-23", supportingAgents: ["AGT-08", "AGT-59"], backendService: "neon_router & monitoring", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "multimodal", number: 15, pageId: "015", module: "neon", label: "Multimodal Vision Workspace", category: "Systems & Diagnostics", subsystem: "Intelligence", description: "Visual image analysis and document-grounded NEON multimodal intelligence.", keywords: ["vision", "image", "multimodal", "ocr"], status: "VERIFIED" , primaryAgent: "AGT-47", supportingAgents: ["AGT-13", "AGT-02"], backendService: "neon_router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },
  {
    id: "argon",
    label: "ARGON Orchestration",
    shortLabel: "ARGON",
    category: "Systems & Diagnostics",
    group: "Intelligence & Execution",
    description: "Multi-agent DAG orchestration, durable job queue, ApprovalGate governance, and dead-letter recovery.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 16, pageId: "016", module: "argon", label: "ARGON Orchestration Overview", category: "Systems & Diagnostics", subsystem: "Orchestration", description: "Orchestration health, queued jobs, pending approvals, and active worker schedules.", keywords: ["argon", "orchestration", "health"], status: "VERIFIED" , primaryAgent: "AGT-18", supportingAgents: ["AGT-01", "AGT-27"], backendService: "argon_orchestrator & job_scheduler", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "orchestrate", number: 17, pageId: "017", module: "argon", label: "Task & DAG Planner", category: "Systems & Diagnostics", subsystem: "Orchestration", description: "Plan and dispatch multi-agent objectives with live DAG dependency tracking.", keywords: ["dispatch", "dag", "plan", "steps"], status: "VERIFIED" , primaryAgent: "AGT-01", supportingAgents: ["AGT-05", "AGT-27"], backendService: "argon_orchestrator", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "running-jobs", number: 18, pageId: "018", module: "argon", label: "Running Jobs & Queue", category: "Systems & Diagnostics", subsystem: "Orchestration", description: "Monitor queued and running background worker jobs and trigger manual drainage.", keywords: ["jobs", "worker", "queue", "drain"], status: "ONLINE" , primaryAgent: "AGT-31", supportingAgents: ["AGT-18"], backendService: "job_scheduler", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "job-history", number: 19, pageId: "019", module: "argon", label: "Job History & Outcomes", category: "Systems & Diagnostics", subsystem: "Orchestration", description: "Complete execution history, attempt counts, and worker outcomes.", keywords: ["history", "completed", "outcomes"], status: "VERIFIED" , primaryAgent: "AGT-25", supportingAgents: ["AGT-32"], backendService: "job_scheduler", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "schedules", number: 20, pageId: "020", module: "argon", label: "Scheduled Automation", category: "Systems & Diagnostics", subsystem: "Orchestration", description: "Create and monitor recurring interval schedules for autonomous system execution.", keywords: ["cron", "schedules", "recurring", "interval"], status: "VERIFIED" , primaryAgent: "AGT-18", supportingAgents: ["AGT-31"], backendService: "job_scheduler", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "workflow-builder", number: 21, pageId: "021", module: "argon", label: "Workflow Builder & Thresholds", category: "Systems & Diagnostics", subsystem: "Orchestration", description: "Preview NEON route assignments and financial thresholds before dispatching workflows.", keywords: ["workflow", "route", "builder", "thresholds"], status: "VERIFIED" , primaryAgent: "AGT-05", supportingAgents: ["AGT-18", "AGT-08"], backendService: "argon_orchestrator & neon_router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "approvals", number: 22, pageId: "022", module: "argon", label: "Approval Centre & Governance", category: "Systems & Diagnostics", subsystem: "Orchestration", description: "Review and decide high-impact or financial actions gated by ApprovalGate.", keywords: ["approval", "gate", "governance", "review"], status: "VERIFIED" , primaryAgent: "AGT-01", supportingAgents: ["AGT-20", "AGT-08", "AGT-58"], backendService: "approval_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "dlq", number: 23, pageId: "023", module: "argon", label: "Dead Letter Queue (DLQ)", category: "Systems & Diagnostics", subsystem: "Orchestration", description: "Inspect exhausted jobs and safely requeue or cancel failed runs.", keywords: ["dlq", "failed", "requeue", "recovery"], status: "VERIFIED" , primaryAgent: "AGT-04", supportingAgents: ["AGT-31"], backendService: "job_scheduler", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },
  {
    id: "agents",
    label: "Specialist Agents",
    shortLabel: "Agents",
    category: "Systems & Diagnostics",
    group: "Intelligence & Execution",
    description: "Complete 60-agent specialist registry (25 Core + 35 Extensible) with independent contracts, tools, and RBAC scopes.",
    defaultSubPage: "directory",
    subPages: [
      { id: "directory", number: 24, pageId: "024", module: "agents", label: "Complete 60-Agent Directory", category: "Systems & Diagnostics", subsystem: "Agents", description: "Search and filter all 60 specialist agents by tier, domain, and live status.", keywords: ["60", "directory", "agents", "specialists"], status: "VERIFIED" , primaryAgent: "AGT-60", supportingAgents: ["AGT-01"], backendService: "agent_service & agent_catalog", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "profile", number: 25, pageId: "025", module: "agents", label: "Agent Profile & Contract", category: "Systems & Diagnostics", subsystem: "Agents", description: "Role description, responsibilities, authorized tools, and independent contract.", keywords: ["profile", "manifest", "contract"], status: "VERIFIED" , primaryAgent: "AGT-60", supportingAgents: ["AGT-34"], backendService: "agent_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "workspace", number: 26, pageId: "026", module: "agents", label: "Specialist Agent Workspace", category: "Systems & Diagnostics", subsystem: "Agents", description: "Direct specialist invocation via NEON with reasoning tier and structured output controls.", keywords: ["invoke", "workspace", "agent"], status: "VERIFIED" , primaryAgent: "AGT-01", supportingAgents: ["AGT-02", "AGT-03", "AGT-04", "AGT-06", "AGT-07", "AGT-08", "AGT-10", "AGT-11", "AGT-12", "AGT-20"], backendService: "neon_router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "performance", number: 27, pageId: "027", module: "agents", label: "Agent Performance & Latency", category: "Systems & Diagnostics", subsystem: "Agents", description: "Live tasks completed, failure counts, success rate, and average latency telemetry.", keywords: ["performance", "latency", "metrics", "rate"], status: "VERIFIED" , primaryAgent: "AGT-23", supportingAgents: ["AGT-59"], backendService: "agent_service & monitoring", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "permissions", number: 28, pageId: "028", module: "agents", label: "Agent Permissions & Scopes", category: "Systems & Diagnostics", subsystem: "Agents", description: "Permission scopes (TIER_1_EXEC, TIER_1_SEC, TIER_2, TIER_3_GATED) and ApprovalGate rules.", keywords: ["permissions", "scope", "rbac", "gates"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-58"], backendService: "auth_service & permissions", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "activity", number: 29, pageId: "029", module: "agents", label: "Agent Communications & Bus", category: "Systems & Diagnostics", subsystem: "Agents", description: "Recent inter-agent messages, bus communication, and specialist invocation history.", keywords: ["activity", "messages", "bus", "handoff"], status: "VERIFIED" , primaryAgent: "AGT-16", supportingAgents: ["AGT-18"], backendService: "realtime_hub & argon_orchestrator", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "configuration", number: 30, pageId: "030", module: "agents", label: "Capability State Configuration", category: "Systems & Diagnostics", subsystem: "Agents", description: "Manage capability state and propose ApprovalGate-governed extension agents.", keywords: ["config", "state", "extension", "lifecycle"], status: "VERIFIED" , primaryAgent: "AGT-60", supportingAgents: ["AGT-01"], backendService: "agent_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "evaluation", number: 31, pageId: "031", module: "agents", label: "Quality Benchmarks & Evals", category: "Systems & Diagnostics", subsystem: "Agents", description: "Quality benchmarks, zero-fabrication policy, and TURBO evaluation diagnostics.", keywords: ["evaluation", "benchmarks", "turbo", "quality"], status: "VERIFIED" , primaryAgent: "AGT-25", supportingAgents: ["AGT-32", "AGT-60"], backendService: "turbo_service & neon_router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },
  {
    id: "connections",
    label: "Connections Centre",
    shortLabel: "Connect",
    category: "Systems & Diagnostics",
    group: "Intelligence & Execution",
    description: "Official integration directory, OAuth 2.0 + PKCE connections, honest 4-stage verification, and permissions.",
    defaultSubPage: "directory",
    subPages: [
      { id: "overview", number: 32, pageId: "032", module: "connections", label: "Connections Overview & Gates", category: "Systems & Diagnostics", subsystem: "Integrations", description: "4-stage honest connectivity: Supported, Configured, Authenticated, and Live Verified.", keywords: ["connections", "overview", "stages"], status: "VERIFIED" , primaryAgent: "AGT-30", supportingAgents: ["AGT-20"], backendService: "universal_connections_service & integration_manager", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "directory", number: 33, pageId: "033", module: "connections", label: "Integration Directory & Hub", category: "Systems & Diagnostics", subsystem: "Integrations", description: "Catalogue of AI, Google Workspace, GitHub, Vercel, Supabase, Cloudflare, and Payment providers.", keywords: ["marketplace", "catalogue", "logos", "hub"], status: "VERIFIED" , primaryAgent: "AGT-30", supportingAgents: ["AGT-29"], backendService: "universal_connections_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "details", number: 34, pageId: "034", module: "connections", label: "Integration Inspector", category: "Systems & Diagnostics", subsystem: "Integrations", description: "Inspect capabilities, scopes, auth flow, and run live connection verification probes.", keywords: ["details", "inspect", "probe"], status: "VERIFIED" , primaryAgent: "AGT-29", supportingAgents: ["AGT-20"], backendService: "integration_manager", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "accounts", number: 35, pageId: "035", module: "connections", label: "Connected Accounts Vault", category: "Systems & Diagnostics", subsystem: "Integrations", description: "Tenant-scoped encrypted integration records stored via AES-256-GCM.", keywords: ["accounts", "connected", "vault", "aes"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-30"], backendService: "vault_service & integration_manager", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "api-providers", number: 36, pageId: "036", module: "connections", label: "API Provider Settings & Keys", category: "Systems & Diagnostics", subsystem: "Integrations", description: "Connect supported API-key providers through secure backend encryption without browser exposure.", keywords: ["api", "keys", "providers", "encryption"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-29"], backendService: "universal_connections_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "oauth", number: 37, pageId: "037", module: "connections", label: "OAuth 2.0 + PKCE Manager", category: "Systems & Diagnostics", subsystem: "Integrations", description: "Initiate OAuth 2.0 + PKCE flows, refresh tokens, and revoke upstream access cleanly.", keywords: ["oauth", "pkce", "google", "github"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-29"], backendService: "google & github routers", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "permissions", number: 38, pageId: "038", module: "connections", label: "Integration Scopes & Review", category: "Systems & Diagnostics", subsystem: "Integrations", description: "Least-privilege scope review across Google Workspace, GitHub, and cloud providers.", keywords: ["scopes", "permissions", "least-privilege"], status: "VERIFIED" , primaryAgent: "AGT-58", supportingAgents: ["AGT-20"], backendService: "integration_manager", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "webhooks", number: 39, pageId: "039", module: "connections", label: "Webhook Management & Intake", category: "Systems & Diagnostics", subsystem: "Integrations", description: "Webhook intake configuration for Vercel deployments and BRIDGE share payloads.", keywords: ["webhooks", "vercel", "bridge", "intake"], status: "VERIFIED" , primaryAgent: "AGT-18", supportingAgents: ["AGT-29"], backendService: "universal_connections_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },
  {
    id: "files",
    label: "Files & Knowledge",
    shortLabel: "Files",
    category: "Systems & Diagnostics",
    group: "Workspace & Media",
    description: "Tenant-isolated File Hub, Google Drive workspace, document parsing, and versioned long-term memory.",
    defaultSubPage: "hub",
    subPages: [
      { id: "hub", number: 40, pageId: "040", module: "files", label: "File Hub Storage Vault", category: "Systems & Diagnostics", subsystem: "Storage & Memory", description: "Storage backend status, active files, and quick upload or generation workflows.", keywords: ["files", "hub", "storage", "vault"], status: "VERIFIED" , primaryAgent: "AGT-21", supportingAgents: ["AGT-20"], backendService: "file_hub_service & storage_adapter", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "browser", number: 41, pageId: "041", module: "files", label: "File Browser & Trash", category: "Systems & Diagnostics", subsystem: "Storage & Memory", description: "Search, filter, soft-delete, and restore tenant-isolated files.", keywords: ["browser", "trash", "restore", "files"], status: "VERIFIED" , primaryAgent: "AGT-21", supportingAgents: ["AGT-17"], backendService: "file_hub_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "drive", number: 42, pageId: "042", module: "files", label: "Google Drive Workspace", category: "Systems & Diagnostics", subsystem: "Storage & Memory", description: "Browse and search Google Drive when Google OAuth is authenticated.", keywords: ["gdrive", "google drive", "cloud"], status: "VERIFIED" , primaryAgent: "AGT-21", supportingAgents: ["AGT-16"], backendService: "google router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "upload", number: 43, pageId: "043", module: "files", label: "Upload Centre & VAULT Scan", category: "Systems & Diagnostics", subsystem: "Storage & Memory", description: "Upload documents with VAULT secret scanning, malware heuristic inspection, or generate bundles.", keywords: ["upload", "generate", "zip", "scanner"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-33"], backendService: "file_hub_service & vault_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "downloads", number: 44, pageId: "044", module: "files", label: "Downloads Vault & Signed URLs", category: "Systems & Diagnostics", subsystem: "Storage & Memory", description: "Authenticated direct downloads and short-lived signed URL generation.", keywords: ["download", "signed url", "tokens"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-21"], backendService: "file_hub_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "preview", number: 45, pageId: "045", module: "files", label: "Document Preview & Extraction", category: "Systems & Diagnostics", subsystem: "Storage & Memory", description: "Inspect extracted text, metadata, and send document context straight to NEON.", keywords: ["preview", "pdf", "text", "extraction"], status: "VERIFIED" , primaryAgent: "AGT-15", supportingAgents: ["AGT-02"], backendService: "file_hub_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "knowledge", number: 46, pageId: "046", module: "files", label: "Knowledge Base & Embeddings", category: "Systems & Diagnostics", subsystem: "Storage & Memory", description: "Semantic vector/cosine recall across stored tenant knowledge entries.", keywords: ["knowledge", "semantic", "search", "embeddings"], status: "VERIFIED" , primaryAgent: "AGT-21", supportingAgents: ["AGT-02"], backendService: "memory_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "memory", number: 47, pageId: "047", module: "files", label: "Memory Management & History", category: "Systems & Diagnostics", subsystem: "Storage & Memory", description: "Create, edit, inspect version history, prune, and control sensitive-data safeguards.", keywords: ["memory", "versions", "prune", "safeguards"], status: "VERIFIED" , primaryAgent: "AGT-21", supportingAgents: ["AGT-20"], backendService: "memory_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },
  {
    id: "projects",
    label: "Projects & FORGE",
    shortLabel: "Projects",
    category: "Systems & Diagnostics",
    group: "Workspace & Media",
    description: "Software engineering workspace uniting FORGE generation, live preview, AEGIS code scanning, and GitHub.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 48, pageId: "048", module: "projects", label: "Projects Overview & Workspaces", category: "Systems & Diagnostics", subsystem: "Engineering", description: "Manage engineering projects and FORGE generated workspaces.", keywords: ["projects", "forge", "workspaces"], status: "VERIFIED" , primaryAgent: "AGT-27", supportingAgents: ["AGT-03", "AGT-05"], backendService: "dev_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "details", number: 49, pageId: "049", module: "projects", label: "Project Details & Architecture", category: "Systems & Diagnostics", subsystem: "Engineering", description: "Inspect repository metadata and trigger automated project analysis.", keywords: ["details", "analyze", "architecture"], status: "VERIFIED" , primaryAgent: "AGT-05", supportingAgents: ["AGT-03"], backendService: "dev_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "coding", number: 50, pageId: "050", module: "projects", label: "Coding Workspace & Live Preview", category: "Systems & Diagnostics", subsystem: "Engineering", description: "Inspect generated source files and open sandboxed FORGE live previews.", keywords: ["code", "preview", "sandbox", "workbench"], status: "VERIFIED" , primaryAgent: "AGT-03", supportingAgents: ["AGT-04", "AGT-12"], backendService: "forge_service & dev_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "generation", number: 51, pageId: "051", module: "projects", label: "Code Generation & Proposals", category: "Systems & Diagnostics", subsystem: "Engineering", description: "Generate full-stack FORGE artifacts or propose structured code patches.", keywords: ["generate", "proposals", "forge"], status: "VERIFIED" , primaryAgent: "AGT-03", supportingAgents: ["AGT-05"], backendService: "forge_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "debugging", number: 52, pageId: "052", module: "projects", label: "Debugging & AEGIS Code Scan", category: "Systems & Diagnostics", subsystem: "Engineering", description: "Invoke AGT-04 Debugging Agent and run AEGIS static code vulnerability scans.", keywords: ["debug", "agt-04", "scan", "vulnerabilities"], status: "VERIFIED" , primaryAgent: "AGT-04", supportingAgents: ["AGT-33"], backendService: "aegis_service & dev_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "repositories", number: 53, pageId: "053", module: "projects", label: "GitHub Repositories & Commits", category: "Systems & Diagnostics", subsystem: "Engineering", description: "Inspect connected GitHub repositories, branches, commits, and pull requests.", keywords: ["github", "repos", "git", "branches"], status: "VERIFIED" , primaryAgent: "AGT-31", supportingAgents: ["AGT-03"], backendService: "github router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "deployments", number: 54, pageId: "054", module: "projects", label: "Deployment History & Rollback", category: "Systems & Diagnostics", subsystem: "Engineering", description: "Track project deployments and ApprovalGate-governed rollback requests.", keywords: ["deploy", "rollback", "vercel", "status"], status: "VERIFIED" , primaryAgent: "AGT-31", supportingAgents: ["AGT-30"], backendService: "dev_service & integration_manager", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },
  {
    id: "research",
    label: "Research & Intel",
    shortLabel: "Research",
    category: "Systems & Diagnostics",
    group: "Workspace & Media",
    description: "ATLAS intelligence briefings, live web research, market & competitor analysis, Caravan BI, and TURBO analytics.",
    defaultSubPage: "workspace",
    subPages: [
      { id: "workspace", number: 55, pageId: "055", module: "research", label: "Research Workspace & Desk", category: "Systems & Diagnostics", subsystem: "Research & Intel", description: "Unified intelligence desk combining web search, ATLAS briefings, and specialist agents.", keywords: ["research", "atlas", "desk"], status: "VERIFIED" , primaryAgent: "AGT-02", supportingAgents: ["AGT-35", "AGT-36"], backendService: "atlas_service & research_intelligence", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "web", number: 56, pageId: "056", module: "research", label: "Web Research & Scraper", category: "Systems & Diagnostics", subsystem: "Research & Intel", description: "SSRF-protected public web search and content extraction via /api/v1/research.", keywords: ["web", "fetch", "search", "scraper"], status: "VERIFIED" , primaryAgent: "AGT-02", supportingAgents: ["AGT-50"], backendService: "research_intelligence", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "market", number: 57, pageId: "057", module: "research", label: "Market Intelligence (AGT-35)", category: "Systems & Diagnostics", subsystem: "Research & Intel", description: "Tracked intelligence topics, live weather, and AGT-35 market analysis.", keywords: ["market", "topics", "agt-35", "trends"], status: "VERIFIED" , primaryAgent: "AGT-35", supportingAgents: ["AGT-09"], backendService: "atlas_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "competitor", number: 58, pageId: "058", module: "research", label: "Competitor Intelligence (AGT-36)", category: "Systems & Diagnostics", subsystem: "Research & Intel", description: "Product comparison research and AGT-36 competitive intelligence.", keywords: ["competitor", "shopping", "agt-36", "analysis"], status: "VERIFIED" , primaryAgent: "AGT-36", supportingAgents: ["AGT-07", "AGT-09"], backendService: "atlas_service & research_intelligence", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "reports", number: 59, pageId: "059", module: "research", label: "Reports & ATLAS Briefings", category: "Systems & Diagnostics", subsystem: "Research & Intel", description: "Generate and inspect structured ATLAS intelligence briefings.", keywords: ["reports", "briefings", "atlas"], status: "VERIFIED" , primaryAgent: "AGT-15", supportingAgents: ["AGT-02"], backendService: "atlas_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "saved", number: 60, pageId: "060", module: "research", label: "Saved Research & Captures", category: "Systems & Diagnostics", subsystem: "Research & Intel", description: "Review BRIDGE shared captures and tracked ATLAS orders.", keywords: ["saved", "bridge", "orders", "captures"], status: "VERIFIED" , primaryAgent: "AGT-21", supportingAgents: ["AGT-02"], backendService: "bridge router & atlas_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "data-analysis", number: 61, pageId: "061", module: "research", label: "Data Analysis & Funnels", category: "Systems & Diagnostics", subsystem: "Research & Intel", description: "Caravan BI funnel analytics and AGT-11 data analysis.", keywords: ["caravan", "analytics", "data", "funnels"], status: "VERIFIED" , primaryAgent: "AGT-11", supportingAgents: ["AGT-23", "AGT-48"], backendService: "product_intelligence & caravan_growth_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },
  {
    id: "creative",
    label: "Creative Studio",
    shortLabel: "Creative",
    category: "Systems & Diagnostics",
    group: "Workspace & Media",
    description: "Image, video, audio, voice, and 3D creative production pipelines with honest provider status.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 62, pageId: "062", module: "creative", label: "Creative Studio Overview", category: "Systems & Diagnostics", subsystem: "Creative & Media", description: "Honest readiness of Gemini visual, audio, video, and 3D production workflows.", keywords: ["creative", "studio", "readiness"], status: "VERIFIED" , primaryAgent: "AGT-12", supportingAgents: ["AGT-13", "AGT-14", "AGT-24"], backendService: "creative router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "image", number: 63, pageId: "063", module: "creative", label: "Image Generation Studio", category: "Systems & Diagnostics", subsystem: "Creative & Media", description: "Submit image specification and generation jobs via /api/v1/creative/jobs.", keywords: ["image", "visual", "agt-13", "generation"], status: "VERIFIED" , primaryAgent: "AGT-13", supportingAgents: ["AGT-43"], backendService: "creative router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "video", number: 64, pageId: "064", module: "creative", label: "Video Production Pipeline", category: "Systems & Diagnostics", subsystem: "Creative & Media", description: "Storyboard and video production pipeline via AGT-14.", keywords: ["video", "storyboard", "agt-14", "production"], status: "VERIFIED" , primaryAgent: "AGT-14", supportingAgents: ["AGT-47"], backendService: "creative router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "audio", number: 65, pageId: "065", module: "creative", label: "Audio Workspace & Diarization", category: "Systems & Diagnostics", subsystem: "Creative & Media", description: "Audio production and diarization structuring via AGT-45.", keywords: ["audio", "sound", "agt-45", "diarization"], status: "VERIFIED" , primaryAgent: "AGT-45", supportingAgents: ["AGT-46"], backendService: "creative router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "voice", number: 66, pageId: "066", module: "creative", label: "Voice Studio & TTS/STT", category: "Systems & Diagnostics", subsystem: "Creative & Media", description: "Push-to-talk and continuous Web Speech voice pipeline wired to AGT-46.", keywords: ["voice", "mic", "tts", "stt", "speech"], status: "VERIFIED" , primaryAgent: "AGT-46", supportingAgents: ["AGT-16"], backendService: "orbit_app_service & creative router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "3d", number: 67, pageId: "067", module: "creative", label: "3D Modelling & WebGL", category: "Systems & Diagnostics", subsystem: "Creative & Media", description: "Invoke AGT-24 3D Modelling Agent for WebGL/Three.js scene specifications.", keywords: ["3d", "webgl", "agt-24", "threejs"], status: "VERIFIED" , primaryAgent: "AGT-24", supportingAgents: ["AGT-12"], backendService: "creative router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },
  {
    id: "pulse",
    label: "PULSE & Automation",
    shortLabel: "PULSE",
    category: "Systems & Diagnostics",
    group: "Operations & System",
    description: "Live telemetry pages, tool execution registry, scheduled automation, and workflow history.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 68, pageId: "068", module: "pulse", label: "PULSE Live Overview", category: "Systems & Diagnostics", subsystem: "Automation", description: "Live operational pages, registered tools, and autonomous schedules.", keywords: ["pulse", "automation", "telemetry"], status: "VERIFIED" , primaryAgent: "AGT-18", supportingAgents: ["AGT-59"], backendService: "pulse router & realtime_hub", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "live-pages", number: 69, pageId: "069", module: "pulse", label: "Operational Telemetry Pages", category: "Systems & Diagnostics", subsystem: "Automation", description: "Inspect active PULSE pages and pull real-time telemetry bindings.", keywords: ["live", "pages", "bindings"], status: "ONLINE" , primaryAgent: "AGT-59", supportingAgents: ["AGT-18"], backendService: "pulse router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "builder", number: 70, pageId: "070", module: "pulse", label: "Telemetry Page Builder", category: "Systems & Diagnostics", subsystem: "Automation", description: "Create new PULSE operational pages bound to live backend endpoints.", keywords: ["builder", "create", "pages"], status: "VERIFIED" , primaryAgent: "AGT-18", supportingAgents: ["AGT-03"], backendService: "pulse router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "analytics", number: 71, pageId: "071", module: "pulse", label: "System Analytics & Metrics", category: "Systems & Diagnostics", subsystem: "Automation", description: "Caravan BI metrics and HTTP request telemetry from /api/v1/monitoring/overview.", keywords: ["analytics", "metrics", "prometheus"], status: "VERIFIED" , primaryAgent: "AGT-23", supportingAgents: ["AGT-59"], backendService: "monitoring router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "automation", number: 72, pageId: "072", module: "pulse", label: "Backend Tool Execution Hub", category: "Systems & Diagnostics", subsystem: "Automation", description: "Browse authorized backend tools and execute safe or ApprovalGate-checked actions.", keywords: ["tools", "execute", "hub"], status: "VERIFIED" , primaryAgent: "AGT-18", supportingAgents: ["AGT-01", "AGT-20"], backendService: "tool_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "workflows", number: 73, pageId: "073", module: "pulse", label: "Workflow Automation Runner", category: "Systems & Diagnostics", subsystem: "Automation", description: "Dispatch automated multi-agent workflows through ARGON.", keywords: ["workflows", "argon", "runner"], status: "VERIFIED" , primaryAgent: "AGT-18", supportingAgents: ["AGT-27"], backendService: "argon_orchestrator", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "history", number: 74, pageId: "074", module: "pulse", label: "Automation Execution History", category: "Systems & Diagnostics", subsystem: "Automation", description: "Complete execution history of tool runs and background worker cycles.", keywords: ["history", "executions", "runs"], status: "VERIFIED" , primaryAgent: "AGT-25", supportingAgents: ["AGT-18"], backendService: "job_scheduler", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },
  {
    id: "security",
    label: "Security Centre",
    shortLabel: "Security",
    category: "Systems & Diagnostics",
    group: "Operations & System",
    description: "AEGIS autonomous defense, SHA-256 hash-chained audit logs, RBAC access control, VAULT, and SENTINEL.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 75, pageId: "075", module: "security", label: "AEGIS Security Posture", category: "Systems & Diagnostics", subsystem: "Security & AEGIS", description: "Real-time AEGIS security posture, risk score, and on-demand security scans.", keywords: ["aegis", "security", "posture", "risk"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-33"], backendService: "aegis_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "events", number: 76, pageId: "076", module: "security", label: "Security Events & Remediations", category: "Systems & Diagnostics", subsystem: "Security & AEGIS", description: "Inspect and remediate AEGIS incidents and review EVOLVE self-development proposals.", keywords: ["incidents", "evolve", "remediate", "events"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-33"], backendService: "aegis_service & evolve_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "audit", number: 77, pageId: "077", module: "security", label: "SHA-256 Hash-Chained Audit Logs", category: "Systems & Diagnostics", subsystem: "Security & AEGIS", description: "Tamper-evident SHA-256 hash-chained audit ledger with cryptographic integrity verification.", keywords: ["audit", "chain", "sha256", "ledger"], status: "VERIFIED" , primaryAgent: "AGT-58", supportingAgents: ["AGT-20"], backendService: "audit router & aegis_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "access", number: 78, pageId: "078", module: "security", label: "RBAC Access Control", category: "Systems & Diagnostics", subsystem: "Security & AEGIS", description: "Manage tenant users and RBAC role provisioning (OWNER/ADMIN/OPERATOR/VIEWER).", keywords: ["users", "rbac", "access", "roles"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-53"], backendService: "auth_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "sessions", number: 79, pageId: "079", module: "security", label: "Active Sessions & Passkeys", category: "Systems & Diagnostics", subsystem: "Security & AEGIS", description: "SENTINEL WebAuthn passkeys, recovery codes, and session revocation.", keywords: ["sessions", "passkeys", "sentinel", "webauthn"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-19"], backendService: "sentinel_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "vault", number: 80, pageId: "080", module: "security", label: "Credential Vault (AES-256)", category: "Systems & Diagnostics", subsystem: "Security & AEGIS", description: "AES-256-GCM encrypted tenant secrets with explicit reveal and deletion confirmation.", keywords: ["vault", "secrets", "aes", "credentials"], status: "PROTECTED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-01"], backendService: "vault_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "diagnostics", number: 81, pageId: "081", module: "security", label: "Security Diagnostics & SSRF Inspector", category: "Systems & Diagnostics", subsystem: "Security & AEGIS", description: "FIM baseline integrity, SSRF URL inspector, and static code scanner.", keywords: ["fim", "url", "scan-code", "ssrf"], status: "VERIFIED" , primaryAgent: "AGT-33", supportingAgents: ["AGT-20"], backendService: "aegis_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },
  {
    id: "finance",
    label: "Finance Centre",
    shortLabel: "Finance",
    category: "Systems & Diagnostics",
    group: "Operations & System",
    description: "Treasury ledger, transactions, budgets, reserves, investments, payment methods, and spend limits.",
    defaultSubPage: "summary",
    subPages: [
      { id: "summary", number: 82, pageId: "082", module: "finance", label: "Financial Command Centre", category: "Systems & Diagnostics", subsystem: "Finance & Treasury", description: "Transactions, budgets, investments, reserves, payment methods, and forecast telemetry.", keywords: ["finance", "treasury", "budgets", "command"], status: "VERIFIED" , primaryAgent: "AGT-08", supportingAgents: ["AGT-01", "AGT-57"], backendService: "finance_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "transactions", number: 83, pageId: "083", module: "finance", label: "Transactions & Invoicing", category: "Systems & Diagnostics", subsystem: "Finance & Treasury", description: "Live transaction streams, UBA/Flutterwave sandbox, and invoice records.", keywords: ["transactions", "invoicing", "uba", "flutterwave"], status: "VERIFIED" , primaryAgent: "AGT-08", supportingAgents: ["AGT-11"], backendService: "finance_cards_service & flutterwave_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "budgets", number: 84, pageId: "084", module: "finance", label: "Budgets & Reserve Allocations", category: "Systems & Diagnostics", subsystem: "Finance & Treasury", description: "Departmental budget caps, burn rates, and ApprovalGate thresholds.", keywords: ["budgets", "allocations", "burn", "reserves"], status: "VERIFIED" , primaryAgent: "AGT-08", supportingAgents: ["AGT-54"], backendService: "finance_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "predictive", number: 85, pageId: "085", module: "finance", label: "Predictive Finance & Cash Runway", category: "Systems & Diagnostics", subsystem: "Finance & Treasury", description: "Time-series revenue projections, cash runway simulations, and AGT-49 telemetry.", keywords: ["predictive", "runway", "forecast", "agt-49"], status: "VERIFIED" , primaryAgent: "AGT-49", supportingAgents: ["AGT-08", "AGT-51"], backendService: "finance_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },
  {
    id: "caravan",
    label: "CARAVAN Operations",
    shortLabel: "CARAVAN",
    category: "Systems & Diagnostics",
    group: "Operations & System",
    description: "Central operational management for the independent CARAVAN funding platform.",
    defaultSubPage: "command-centre",
    subPages: [
      { id: "command-centre", number: 86, pageId: "086", module: "caravan", label: "CARAVAN Command Centre", category: "Systems & Diagnostics", subsystem: "CARAVAN Business", description: "Executive operations, live telemetry, verified deployment launch destination, and audit timeline.", keywords: ["caravan", "command-centre", "operations", "telemetry"], status: "VERIFIED" , primaryAgent: "AGT-01", supportingAgents: ["AGT-56", "AGT-22", "AGT-08"], backendService: "caravan_command_service & caravan_product_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "admin", number: 87, pageId: "087", module: "caravan", label: "Funding Verification & Admin", category: "Systems & Diagnostics", subsystem: "CARAVAN Business", description: "Register real funding sources/opportunities and verify with primary supporting evidence.", keywords: ["admin", "verification", "sources", "evidence"], status: "VERIFIED" , primaryAgent: "AGT-56", supportingAgents: ["AGT-10", "AGT-58"], backendService: "caravan_product_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "eligibility", number: 88, pageId: "088", module: "caravan", label: "NEON Eligibility & Age Safeguards", category: "Systems & Diagnostics", subsystem: "CARAVAN Business", description: "NEON-powered eligibility scoring, gap analysis, and under-18 founder safeguards.", keywords: ["eligibility", "neon", "under-18", "gap-analysis"], status: "VERIFIED" , primaryAgent: "AGT-10", supportingAgents: ["AGT-56", "AGT-01"], backendService: "caravan_product_service & neon_router", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "applications", number: 89, pageId: "089", module: "caravan", label: "Applications & Document Vault", category: "Systems & Diagnostics", subsystem: "CARAVAN Business", description: "Track draft, preparing, approval-gated, and submitted funding applications and documents.", keywords: ["applications", "tracking", "vault", "documents"], status: "VERIFIED" , primaryAgent: "AGT-15", supportingAgents: ["AGT-56", "AGT-20"], backendService: "caravan_phase7_service & file_hub_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "discover", number: 90, pageId: "090", module: "caravan", label: "Funding Discovery Engine", category: "Systems & Diagnostics", subsystem: "CARAVAN Business", description: "Automated discovery engine, duplicate detection, expiry checks, and marketplace.", keywords: ["discover", "grants", "loans", "marketplace"], status: "VERIFIED" , primaryAgent: "AGT-56", supportingAgents: ["AGT-02", "AGT-48"], backendService: "caravan_discovery_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },

  // -------------------------------------------------------------
  // 91-96 ORBIT DEVICE MANAGEMENT
  // -------------------------------------------------------------
  {
    id: "devices",
    label: "Orbit Device Management",
    shortLabel: "ORBIT",
    category: "Orbit Device Management",
    group: "Operations & System",
    description: "ORBIT multi-device mesh, encrypted pairing, device permissions, location telemetry, and voice controls.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 91, pageId: "091", module: "devices", label: "ORBIT Multi-Device Mesh Overview", category: "Orbit Device Management", subsystem: "Device Mesh", description: "Multi-device telemetry, active heartbeats, and live device status.", keywords: ["orbit", "devices", "mesh", "telemetry"], status: "ONLINE" , primaryAgent: "AGT-19", supportingAgents: ["AGT-59"], backendService: "device_service & orbit_location_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "connected", number: 92, pageId: "092", module: "devices", label: "Connected Devices & Node Pairing", category: "Orbit Device Management", subsystem: "Device Mesh", description: "Pair new desktop/mobile nodes and revoke compromised devices.", keywords: ["pair", "revoke", "nodes", "connect"], status: "VERIFIED" , primaryAgent: "AGT-19", supportingAgents: ["AGT-20"], backendService: "device_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "permissions", number: 93, pageId: "093", module: "devices", label: "Device Permissions & Scopes", category: "Orbit Device Management", subsystem: "Device Mesh", description: "Fine-grained read/write/command scopes per paired device node.", keywords: ["permissions", "scopes", "device"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-19"], backendService: "orbit_app_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "activity", number: 94, pageId: "094", module: "devices", label: "Device Activity & Remote Dispatch", category: "Orbit Device Management", subsystem: "Device Mesh", description: "Dispatch remote device tasks and inspect geofence/location alerts.", keywords: ["tasks", "location", "alerts", "dispatch"], status: "VERIFIED" , primaryAgent: "AGT-19", supportingAgents: ["AGT-18"], backendService: "device_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "voice-mic", number: 95, pageId: "095", module: "devices", label: "Voice & Microphone Synchronization", category: "Orbit Device Management", subsystem: "Device Mesh", description: "Inspect browser SpeechRecognition/TTS capabilities and voice dispatch modes.", keywords: ["microphone", "voice", "audio", "sync"], status: "VERIFIED" , primaryAgent: "AGT-46", supportingAgents: ["AGT-19"], backendService: "orbit_app_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "notif-settings", number: 96, pageId: "096", module: "devices", label: "Device Alerts & Notification Routing", category: "Orbit Device Management", subsystem: "Device Mesh", description: "Review device alerts and tenant notification delivery settings.", keywords: ["notifications", "alerts", "routing"], status: "VERIFIED" , primaryAgent: "AGT-16", supportingAgents: ["AGT-19"], backendService: "notification_service & device_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },

  // -------------------------------------------------------------
  // 97-111 SETTINGS
  // -------------------------------------------------------------
  {
    id: "settings",
    label: "Settings",
    shortLabel: "Settings",
    category: "Settings",
    group: "Operations & System",
    description: "System configuration, appearance, theme, account, security, privacy, memory, accessibility, and diagnostics.",
    defaultSubPage: "general",
    subPages: [
      { id: "general", number: 97, pageId: "097", module: "settings", label: "General Settings", category: "Settings", subsystem: "Configuration", description: "Persisted tenant system settings synchronized with /api/v1/settings.", keywords: ["general", "settings", "tenant"], status: "VERIFIED" , primaryAgent: null, supportingAgents: ["AGT-01"], backendService: "settings_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "appearance", number: 98, pageId: "098", module: "settings", label: "Appearance & Layout Mode", category: "Settings", subsystem: "Configuration", description: "Automatic device layout, dark/light mode, density, and motion controls.", keywords: ["appearance", "dark", "light", "density"], status: "VERIFIED" , primaryAgent: null, supportingAgents: ["AGT-12"], backendService: "preferences_engine", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "theme", number: 99, pageId: "099", module: "settings", label: "Theme Configuration & Accents", category: "Settings", subsystem: "Configuration", description: "Customize restrained accent palette and metallic surface contrast.", keywords: ["theme", "accent", "color", "metallic"], status: "VERIFIED" , primaryAgent: null, supportingAgents: ["AGT-12"], backendService: "design_system_engine", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "account", number: 100, pageId: "100", module: "settings", label: "Account Settings & Tenant ID", category: "Settings", subsystem: "Configuration", description: "Active user identity, role binding, and tenant organization identifier.", keywords: ["account", "tenant", "user"], status: "VERIFIED" , primaryAgent: null, supportingAgents: ["AGT-01"], backendService: "auth_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "profile", number: 101, pageId: "101", module: "settings", label: "Operator Profile & Roles", category: "Settings", subsystem: "Configuration", description: "Operator profile metadata and permission summary.", keywords: ["profile", "user", "operator"], status: "VERIFIED" , primaryAgent: null, supportingAgents: ["AGT-53"], backendService: "auth_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "security-settings", number: 102, pageId: "102", module: "settings", label: "Security Settings & Passkeys", category: "Settings", subsystem: "Configuration", description: "SENTINEL WebAuthn passkeys and single-use recovery code generation.", keywords: ["passkey", "recovery", "2fa", "sentinel"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-33"], backendService: "sentinel_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "privacy", number: 103, pageId: "103", module: "settings", label: "Privacy & VAULT Redaction", category: "Settings", subsystem: "Configuration", description: "VAULT automatic secret redaction, payment data blocking, and zero-leak logging.", keywords: ["privacy", "vault", "redaction", "logging"], status: "VERIFIED" , primaryAgent: "AGT-20", supportingAgents: ["AGT-10"], backendService: "vault_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "memory-prefs", number: 104, pageId: "104", module: "settings", label: "Memory Preferences & Retention", category: "Settings", subsystem: "Configuration", description: "Configure tenant memory retention and personalization via /api/v1/memory/preferences.", keywords: ["memory", "preferences", "retention"], status: "VERIFIED" , primaryAgent: "AGT-21", supportingAgents: ["AGT-01"], backendService: "memory_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "notifications", number: 105, pageId: "105", module: "settings", label: "System Notification Delivery", category: "Settings", subsystem: "Configuration", description: "Manage system notifications and unread queue.", keywords: ["notifications", "alerts", "delivery"], status: "VERIFIED" , primaryAgent: null, supportingAgents: ["AGT-16"], backendService: "notification_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "locale", number: 106, pageId: "106", module: "settings", label: "Language, Region & Timezone", category: "Settings", subsystem: "Configuration", description: "Configure interface language, region, and UTC timestamp display.", keywords: ["language", "region", "timezone", "utc"], status: "VERIFIED" , primaryAgent: null, supportingAgents: ["AGT-10"], backendService: "settings_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "shortcuts", number: 107, pageId: "107", module: "settings", label: "Keyboard Shortcuts & Chords", category: "Settings", subsystem: "Configuration", description: "Command palette (⌘K / Ctrl+K) and fast desktop navigation chords.", keywords: ["keyboard", "shortcuts", "hotkeys", "palette"], status: "VERIFIED" , primaryAgent: null, supportingAgents: ["AGT-17"], backendService: "command_palette_engine", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "accessibility", number: 108, pageId: "108", module: "settings", label: "Accessibility & Motion Controls", category: "Settings", subsystem: "Configuration", description: "Reduced motion, high-contrast focus rings, and screen-reader support.", keywords: ["accessibility", "a11y", "motion", "contrast"], status: "VERIFIED" , primaryAgent: null, supportingAgents: ["AGT-12"], backendService: "design_system_engine", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "data", number: 109, pageId: "109", module: "settings", label: "Data Management & Storage Backend", category: "Settings", subsystem: "Configuration", description: "Storage backend status, TURBO cache management, and safe data export controls.", keywords: ["data", "storage", "cache", "export"], status: "VERIFIED" , primaryAgent: "AGT-28", supportingAgents: ["AGT-20"], backendService: "file_hub_service & storage_adapter", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "about", number: 110, pageId: "110", module: "settings", label: "About ULTRON OS 2026", category: "Settings", subsystem: "Configuration", description: "ULTRON OS 2026 release version, locked backend baseline ultron-backend-v1, and architecture.", keywords: ["about", "version", "release", "architecture"], status: "VERIFIED" , primaryAgent: null, supportingAgents: ["AGT-01"], backendService: "platform_modules_service", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
      { id: "diagnostics", number: 111, pageId: "111", module: "settings", label: "System Diagnostics & Telemetry", category: "Settings", subsystem: "Configuration", description: "Live /health/ready JSON, /health provider state, and Prometheus metrics inspection.", keywords: ["diagnostics", "health", "prometheus", "json"], status: "VERIFIED" , primaryAgent: "AGT-59", supportingAgents: ["AGT-31"], backendService: "monitoring & health", operationalStatus: "OPERATIONAL", integrationStatus: "VERIFIED" },
    ],
  },

  // -------------------------------------------------------------
  // 112 MASTER TERMINAL
  // -------------------------------------------------------------
  {
    id: "terminal",
    label: "Master Terminal",
    shortLabel: "Terminal",
    category: "Master Terminal",
    group: "Core Command",
    description: "Central natural-language interaction and command interface displaying truthful execution states.",
    defaultSubPage: "master-terminal",
    subPages: [
      {
        id: "master-terminal",
        number: 112,
        pageId: "112",
        module: "terminal",
        label: "ULTRON Master Terminal",
        category: "Master Terminal",
        subsystem: "Core Command",
        description: "Natural-language command dispatch, multi-agent coordination, voice input, and verified execution states.",
        keywords: ["terminal", "command", "voice", "objective", "argon", "neon", "master"],
        status: "VERIFIED",
        primaryAgent: "AGT-01",
        supportingAgents: ["AGT-60", "AGT-19", "AGT-26", "AGT-27"],
        backendService: "terminal_router & argon_dag & neon_router",
        operationalStatus: "OPERATIONAL",
        integrationStatus: "VERIFIED",
      },
    ],
  },
];

export const ALL_PAGES: PageDef[] = MODULES.flatMap((m) => m.subPages);

export function getModule(id: ModuleId): ModuleDef {
  return MODULES.find((m) => m.id === id) || MODULES[0];
}

export function getSubPage(moduleId: ModuleId, subPageId: string): PageDef {
  const mod = getModule(moduleId);
  return mod.subPages.find((p) => p.id === subPageId) || mod.subPages[0];
}

export function getPageByNumber(num: number): PageDef | undefined {
  return ALL_PAGES.find((p) => p.number === num);
}

export function getPageByPageId(pageId: string): PageDef | undefined {
  return ALL_PAGES.find((p) => p.pageId === pageId);
}

export function getPagesForAgent(agentId: string): { primary: PageDef[]; supporting: PageDef[] } {
  const aid = agentId.toUpperCase();
  const primary = ALL_PAGES.filter((p) => p.primaryAgent?.toUpperCase() === aid);
  const supporting = ALL_PAGES.filter((p) => p.supportingAgents?.some((s) => s.toUpperCase() === aid));
  return { primary, supporting };
}
