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
  | "devices"
  | "finance"
  | "caravan"
  | "settings";

export interface PageDef {
  id: string;
  number: number;
  module: ModuleId;
  label: string;
  description: string;
  keywords: string[];
}

export interface ModuleDef {
  id: ModuleId;
  label: string;
  shortLabel: string;
  group: "Core Command" | "Intelligence & Execution" | "Workspace & Media" | "Operations & System";
  description: string;
  defaultSubPage: string;
  subPages: PageDef[];
}

export const MODULES: ModuleDef[] = [
  {
    id: "command",
    label: "Command Centre",
    shortLabel: "Home",
    group: "Core Command",
    description: "Global orbital operating system command interface, live telemetry, activity, and health.",
    defaultSubPage: "home",
    subPages: [
      { id: "home", number: 1, module: "command", label: "Home / Command Center", description: "Central orbital Earth interface, live system telemetry, and universal NEON/ARGON command dispatch.", keywords: ["home", "earth", "globe", "command"] },
      { id: "overview", number: 2, module: "command", label: "Global System Overview", description: "Cross-subsystem operational summary across agents, tasks, storage, and providers.", keywords: ["overview", "metrics", "telemetry"] },
      { id: "activity", number: 3, module: "command", label: "Live Activity", description: "Real-time tenant activity feed across tasks, agent executions, and audit events.", keywords: ["activity", "feed", "events"] },
      { id: "notifications", number: 4, module: "command", label: "Notifications", description: "System alerts, approval triggers, and operational notifications.", keywords: ["alerts", "inbox", "bell"] },
      { id: "recent-tasks", number: 5, module: "command", label: "Recent Tasks", description: "Manage active and completed task lifecycles with execute, pause, resume, retry, and cancel controls.", keywords: ["tasks", "lifecycle"] },
      { id: "quick-actions", number: 6, module: "command", label: "Quick Actions", description: "Direct operational launchers for NEON, ARGON, AEGIS scans, TURBO benchmarks, and File Hub.", keywords: ["actions", "shortcuts", "launch"] },
      { id: "system-health", number: 7, module: "command", label: "System Health", description: "Live liveness/readiness probes, PostgreSQL pooler diagnostics, and Prometheus metrics.", keywords: ["health", "ready", "database", "prometheus"] },
      { id: "command-history", number: 8, module: "command", label: "Command History", description: "Auditable history of dispatched NEON sessions and ARGON orchestration runs.", keywords: ["history", "log", "commands"] },
      { id: "integrations", number: 120, module: "command", label: "Universal Integration Hub", description: "Discover, configure, authorize via OAuth 2.0 + PKCE, connect MCP/webhooks, and verify integrations.", keywords: ["integrations", "oauth", "hub", "configure"] },
    ],
  },
  {
    id: "neon",
    label: "NEON Intelligence",
    shortLabel: "NEON",
    group: "Core Command",
    description: "Shared intelligence layer powered by Gemini with streaming, multimodal analysis, and VAULT secret interception.",
    defaultSubPage: "chat",
    subPages: [
      { id: "chat", number: 9, module: "neon", label: "NEON Chat", description: "Streaming intelligence console with code formatting, file attachment, agent handoff, and VAULT protection.", keywords: ["chat", "jarvis", "stream", "gemini"] },
      { id: "conversations", number: 10, module: "neon", label: "Conversation History", description: "Browse, search, and resume persisted tenant conversations.", keywords: ["history", "threads"] },
      { id: "new-conversation", number: 11, module: "neon", label: "New Conversation", description: "Start a fresh session bound to any of the 60 specialist agents.", keywords: ["new", "session"] },
      { id: "models", number: 12, module: "neon", label: "Model Selection", description: "Inspect active Gemini models, reasoning tiers T1–T5, and latency/cost profiles.", keywords: ["models", "gemini", "tiers"] },
      { id: "providers", number: 13, module: "neon", label: "Provider Configuration", description: "Honest live readiness of Gemini primary and OpenAI, Anthropic, and Ollama failover providers.", keywords: ["providers", "llm", "failover"] },
      { id: "intelligence-settings", number: 14, module: "neon", label: "Intelligence Settings", description: "Default temperature, reasoning tier, structured output mode, and routing preferences.", keywords: ["settings", "temperature", "routing"] },
      { id: "execution-history", number: 15, module: "neon", label: "Execution History", description: "Token usage, latency, execution mode, and cost telemetry across NEON invocations.", keywords: ["usage", "tokens", "cost"] },
      { id: "multimodal", number: 16, module: "neon", label: "Multimodal Workspace", description: "Visual image analysis and document-grounded NEON intelligence.", keywords: ["vision", "image", "multimodal"] },
    ],
  },
  {
    id: "argon",
    label: "ARGON Orchestration",
    shortLabel: "ARGON",
    group: "Intelligence & Execution",
    description: "Multi-agent DAG orchestration, durable job queue, ApprovalGate governance, and dead-letter recovery.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 17, module: "argon", label: "ARGON Overview", description: "Orchestration health, queued jobs, pending approvals, and active schedules.", keywords: ["argon", "orchestration"] },
      { id: "orchestrate", number: 18, module: "argon", label: "Task Orchestration", description: "Plan and dispatch multi-agent objectives with live step tracking.", keywords: ["dispatch", "dag", "plan"] },
      { id: "running-jobs", number: 19, module: "argon", label: "Running Jobs", description: "Monitor queued and running background worker jobs and trigger manual drainage.", keywords: ["jobs", "worker", "queue"] },
      { id: "job-history", number: 20, module: "argon", label: "Job History", description: "Complete execution history, attempt counts, and worker outcomes.", keywords: ["history", "completed"] },
      { id: "schedules", number: 21, module: "argon", label: "Scheduled Tasks", description: "Create and monitor recurring interval schedules for autonomous execution.", keywords: ["cron", "schedules", "recurring"] },
      { id: "workflow-builder", number: 22, module: "argon", label: "Workflow Builder", description: "Preview NEON route assignments and financial thresholds before dispatching workflows.", keywords: ["workflow", "route", "builder"] },
      { id: "approvals", number: 23, module: "argon", label: "Approval Centre", description: "Review and decide high-impact or financial actions gated by ApprovalGate.", keywords: ["approval", "gate", "governance"] },
      { id: "dlq", number: 24, module: "argon", label: "Dead Letter Queue", description: "Inspect exhausted jobs and safely requeue or cancel failed runs.", keywords: ["dlq", "failed", "requeue"] },
      { id: "comms", number: 25, module: "argon", label: "Agent Communication", description: "Inspect and dispatch structured inter-agent handoff messages.", keywords: ["messages", "handoff", "bus"] },
    ],
  },
  {
    id: "agents",
    label: "The 60 Agents",
    shortLabel: "Agents",
    group: "Intelligence & Execution",
    description: "Complete 60-agent specialist registry (25 Core + 35 Extensible) with independent instructions, tools, and scopes.",
    defaultSubPage: "directory",
    subPages: [
      { id: "directory", number: 26, module: "agents", label: "Complete Agent Directory", description: "Search and filter all 60 specialist agents by tier, domain, and live status.", keywords: ["60", "directory", "agents"] },
      { id: "profile", number: 27, module: "agents", label: "Individual Agent Profile", description: "Role description, responsibilities, authorized tools, and independent contract.", keywords: ["profile", "manifest"] },
      { id: "workspace", number: 28, module: "agents", label: "Agent Workspace", description: "Direct specialist invocation via NEON with reasoning tier and structured output controls.", keywords: ["invoke", "workspace"] },
      { id: "performance", number: 29, module: "agents", label: "Agent Performance", description: "Live tasks completed, failure counts, success rate, and average latency telemetry.", keywords: ["performance", "latency", "metrics"] },
      { id: "permissions", number: 30, module: "agents", label: "Agent Permissions", description: "Permission scopes (TIER_1_EXEC, TIER_1_SEC, TIER_2, TIER_3_GATED) and ApprovalGate rules.", keywords: ["permissions", "scope", "rbac"] },
      { id: "activity", number: 31, module: "agents", label: "Agent Activity", description: "Recent inter-agent messages and invocation history for the selected specialist.", keywords: ["activity", "messages"] },
      { id: "configuration", number: 32, module: "agents", label: "Agent Configuration", description: "Manage capability state and propose ApprovalGate-governed extension agents.", keywords: ["config", "state", "extension"] },
      { id: "evaluation", number: 33, module: "agents", label: "Agent Evaluation", description: "Quality benchmarks, zero-fabrication policy, and TURBO evaluation diagnostics.", keywords: ["evaluation", "benchmarks"] },
    ],
  },
  {
    id: "connections",
    label: "Connections Centre",
    shortLabel: "Connect",
    group: "Intelligence & Execution",
    description: "Official integration directory, OAuth 2.0 + PKCE connections, honest 4-stage verification, and permissions.",
    defaultSubPage: "directory",
    subPages: [
      { id: "overview", number: 34, module: "connections", label: "Connections Overview", description: "4-stage honest connectivity breakdown: Supported, Configured, Authenticated, and Live Verified.", keywords: ["connections", "overview"] },
      { id: "directory", number: 35, module: "connections", label: "Integration Directory", description: "Searchable catalogue of AI, Google Workspace, Dev, Comms, Productivity, Storage, Payments, Media & Automation integrations.", keywords: ["marketplace", "catalogue", "logos"] },
      { id: "details", number: 36, module: "connections", label: "Integration Details", description: "Inspect capabilities, scopes, auth flow, and run live connection verification.", keywords: ["details", "inspect"] },
      { id: "accounts", number: 37, module: "connections", label: "Connected Accounts", description: "Tenant-scoped encrypted integration records stored via AES-256-GCM.", keywords: ["accounts", "connected"] },
      { id: "api-providers", number: 38, module: "connections", label: "API Provider Settings", description: "Connect supported API-key providers through secure backend encryption without browser secret exposure.", keywords: ["api", "keys", "providers"] },
      { id: "oauth", number: 39, module: "connections", label: "OAuth Connections", description: "Initiate OAuth 2.0 + PKCE flows, refresh tokens, and revoke upstream access.", keywords: ["oauth", "pkce", "google", "github"] },
      { id: "permissions", number: 40, module: "connections", label: "Integration Permissions", description: "Least-privilege scope review across Google Workspace, GitHub, and cloud providers.", keywords: ["scopes", "permissions"] },
      { id: "activity", number: 41, module: "connections", label: "Connection Activity", description: "Audit log trail of integration connections, verifications, refreshes, and revocations.", keywords: ["activity", "audit"] },
      { id: "webhooks", number: 42, module: "connections", label: "Webhook Management", description: "Webhook intake configuration for Vercel deployments and BRIDGE share payloads.", keywords: ["webhooks", "vercel", "bridge"] },
    ],
  },
  {
    id: "files",
    label: "Files & Knowledge",
    shortLabel: "Files",
    group: "Workspace & Media",
    description: "Tenant-isolated File Hub, Google Drive workspace, document parsing, and versioned long-term memory.",
    defaultSubPage: "hub",
    subPages: [
      { id: "hub", number: 43, module: "files", label: "File Hub", description: "Storage backend status, active files, and quick upload or generation workflows.", keywords: ["files", "hub", "storage"] },
      { id: "browser", number: 44, module: "files", label: "File Browser", description: "Search, filter, soft-delete, and restore tenant-isolated files.", keywords: ["browser", "trash", "restore"] },
      { id: "drive", number: 45, module: "files", label: "Google Drive Workspace", description: "Browse and search Google Drive when Google OAuth is authenticated.", keywords: ["gdrive", "google drive"] },
      { id: "upload", number: 46, module: "files", label: "Upload Centre", description: "Upload documents with VAULT secret scanning or generate structured files and ZIP bundles.", keywords: ["upload", "generate", "zip"] },
      { id: "downloads", number: 47, module: "files", label: "Downloads", description: "Authenticated direct downloads and short-lived signed URL generation.", keywords: ["download", "signed url"] },
      { id: "preview", number: 48, module: "files", label: "Document Preview", description: "Inspect extracted text, metadata, and send document context straight to NEON.", keywords: ["preview", "pdf", "text"] },
      { id: "knowledge", number: 49, module: "files", label: "Knowledge Base", description: "Semantic vector/cosine recall across stored tenant knowledge entries.", keywords: ["knowledge", "semantic", "search"] },
      { id: "memory", number: 50, module: "files", label: "Memory Management", description: "Create, edit, inspect version history, prune, and control sensitive-data memory safeguards.", keywords: ["memory", "versions", "prune"] },
    ],
  },
  {
    id: "projects",
    label: "Projects & FORGE",
    shortLabel: "Projects",
    group: "Workspace & Media",
    description: "Software engineering workspace uniting FORGE generation, live preview, AEGIS code scanning, and GitHub.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 51, module: "projects", label: "Projects Overview", description: "Manage engineering projects and FORGE generated workspaces.", keywords: ["projects", "forge"] },
      { id: "details", number: 52, module: "projects", label: "Project Details", description: "Inspect repository metadata and trigger automated project analysis.", keywords: ["details", "analyze"] },
      { id: "coding", number: 53, module: "projects", label: "Coding Workspace", description: "Inspect generated source files and open sandboxed FORGE live previews.", keywords: ["code", "preview", "sandbox"] },
      { id: "generation", number: 54, module: "projects", label: "Code Generation", description: "Generate full-stack FORGE artifacts or propose structured code patches.", keywords: ["generate", "proposals"] },
      { id: "debugging", number: 55, module: "projects", label: "Debugging Workspace", description: "Invoke AGT-04 Debugging Agent and run AEGIS static code vulnerability scans.", keywords: ["debug", "agt-04", "scan"] },
      { id: "repositories", number: 56, module: "projects", label: "Repository Connections", description: "Inspect connected GitHub repositories, branches, commits, and pull requests.", keywords: ["github", "repos", "git"] },
      { id: "dev-activity", number: 57, module: "projects", label: "Development Activity", description: "Engineering audit trail across project analyses, proposals, and scans.", keywords: ["activity", "engineering"] },
      { id: "deployments", number: 58, module: "projects", label: "Deployment History", description: "Track project deployments and ApprovalGate-governed rollback requests.", keywords: ["deploy", "rollback", "vercel"] },
    ],
  },
  {
    id: "research",
    label: "Research & Intel",
    shortLabel: "Research",
    group: "Workspace & Media",
    description: "ATLAS intelligence briefings, live web research, market & competitor analysis, Caravan BI, and TURBO analytics.",
    defaultSubPage: "workspace",
    subPages: [
      { id: "workspace", number: 59, module: "research", label: "Research Workspace", description: "Unified intelligence desk combining web search, ATLAS briefings, and specialist agents.", keywords: ["research", "atlas"] },
      { id: "web", number: 60, module: "research", label: "Web Research", description: "SSRF-protected public web search and content extraction via /api/v1/research.", keywords: ["web", "fetch", "search"] },
      { id: "market", number: 61, module: "research", label: "Market Intelligence", description: "Tracked intelligence topics, live weather, and AGT-35 market analysis.", keywords: ["market", "topics", "agt-35"] },
      { id: "competitor", number: 62, module: "research", label: "Competitor Intelligence", description: "Product comparison research and AGT-36 competitive intelligence.", keywords: ["competitor", "shopping", "agt-36"] },
      { id: "reports", number: 63, module: "research", label: "Reports & Briefings", description: "Generate and inspect structured ATLAS intelligence briefings.", keywords: ["reports", "briefings"] },
      { id: "saved", number: 64, module: "research", label: "Saved Research & Orders", description: "Review BRIDGE shared captures and tracked ATLAS orders.", keywords: ["saved", "bridge", "orders"] },
      { id: "data-analysis", number: 65, module: "research", label: "Data Analysis", description: "Caravan BI funnel analytics and AGT-11 data analysis.", keywords: ["caravan", "analytics", "data"] },
      { id: "predictive", number: 66, module: "research", label: "Predictive Analytics", description: "Financial forecasting, TURBO performance telemetry, and AGT-49 modeling.", keywords: ["predictive", "forecast", "turbo"] },
    ],
  },
  {
    id: "creative",
    label: "Creative Studio",
    shortLabel: "Creative",
    group: "Workspace & Media",
    description: "Image, video, audio, voice, and 3D creative production pipelines with honest provider status.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 67, module: "creative", label: "Creative Studio Overview", description: "Honest readiness of Gemini visual, audio, video, and 3D production workflows.", keywords: ["creative", "studio"] },
      { id: "image", number: 68, module: "creative", label: "Image Generation", description: "Submit image specification and generation jobs via /api/v1/creative/jobs.", keywords: ["image", "visual", "agt-13"] },
      { id: "video", number: 69, module: "creative", label: "Video Production", description: "Storyboard and video production pipeline via AGT-14.", keywords: ["video", "storyboard", "agt-14"] },
      { id: "audio", number: 70, module: "creative", label: "Audio Workspace", description: "Audio production and diarization jobs via AGT-45.", keywords: ["audio", "sound", "agt-45"] },
      { id: "voice", number: 71, module: "creative", label: "Voice Studio", description: "Push-to-talk and continuous Web Speech voice pipeline wired to AGT-46.", keywords: ["voice", "mic", "tts", "stt"] },
      { id: "3d", number: 72, module: "creative", label: "3D Modelling Workspace", description: "Invoke AGT-24 3D Modelling Agent for WebGL/Three.js scene specifications.", keywords: ["3d", "webgl", "agt-24"] },
      { id: "library", number: 73, module: "creative", label: "Generated Assets Library", description: "Inspect all persisted creative production jobs and honest execution states.", keywords: ["assets", "library", "jobs"] },
    ],
  },
  {
    id: "pulse",
    label: "PULSE & Automation",
    shortLabel: "PULSE",
    group: "Operations & System",
    description: "Live telemetry pages, tool execution registry, scheduled automation, and workflow history.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 74, module: "pulse", label: "PULSE Overview", description: "Live operational pages, registered tools, and autonomous schedules.", keywords: ["pulse", "automation"] },
      { id: "live-pages", number: 75, module: "pulse", label: "Live Pages", description: "Inspect active PULSE pages and pull real-time telemetry bindings.", keywords: ["live", "pages"] },
      { id: "builder", number: 76, module: "pulse", label: "Page Builder", description: "Create new PULSE operational pages bound to live backend endpoints.", keywords: ["builder", "create"] },
      { id: "analytics", number: 77, module: "pulse", label: "Page Analytics", description: "Caravan BI metrics and HTTP request telemetry from /api/v1/monitoring/overview.", keywords: ["analytics", "metrics"] },
      { id: "automation", number: 78, module: "pulse", label: "Automation Centre", description: "Browse authorized backend tools and execute safe or ApprovalGate-checked actions.", keywords: ["tools", "execute"] },
      { id: "workflows", number: 79, module: "pulse", label: "Workflow Automation", description: "Dispatch automated multi-agent workflows through ARGON.", keywords: ["workflows", "argon"] },
      { id: "scheduled", number: 80, module: "pulse", label: "Scheduled Automation", description: "Manage recurring interval jobs via /api/v1/argon/schedules.", keywords: ["scheduled", "interval"] },
      { id: "history", number: 81, module: "pulse", label: "Automation History", description: "Complete execution history of tool runs and background worker cycles.", keywords: ["history", "executions"] },
    ],
  },
  {
    id: "security",
    label: "Security Centre",
    shortLabel: "Security",
    group: "Operations & System",
    description: "AEGIS autonomous defense, SHA-256 hash-chained audit logs, RBAC access control, VAULT, and SENTINEL.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 82, module: "security", label: "AEGIS Security Overview", description: "Real-time AEGIS security posture, risk score, and on-demand security scans.", keywords: ["aegis", "security", "posture"] },
      { id: "events", number: 83, module: "security", label: "Security Events", description: "Inspect and remediate AEGIS incidents and review EVOLVE self-development proposals.", keywords: ["incidents", "evolve", "remediate"] },
      { id: "audit", number: 84, module: "security", label: "Audit Logs", description: "Tamper-evident SHA-256 hash-chained audit ledger with cryptographic integrity verification.", keywords: ["audit", "chain", "sha256"] },
      { id: "access", number: 85, module: "security", label: "Access Control", description: "Manage tenant users and RBAC role provisioning (OWNER/ADMIN/OPERATOR/VIEWER).", keywords: ["users", "rbac", "access"] },
      { id: "permissions", number: 86, module: "security", label: "Permissions", description: "Inspect active principal permissions and tenant isolation boundaries.", keywords: ["permissions", "scopes"] },
      { id: "policies", number: 87, module: "security", label: "Approval Policies", description: "ApprovalGate governance thresholds and pending mutation review.", keywords: ["policies", "approval"] },
      { id: "sessions", number: 88, module: "security", label: "Active Sessions & Passkeys", description: "SENTINEL WebAuthn passkeys, recovery codes, and session revocation.", keywords: ["sessions", "passkeys", "sentinel"] },
      { id: "vault", number: 89, module: "security", label: "Credential Vault", description: "AES-256-GCM encrypted tenant secrets with explicit reveal and deletion confirmation.", keywords: ["vault", "secrets", "aes"] },
      { id: "diagnostics", number: 90, module: "security", label: "Security Diagnostics", description: "FIM baseline integrity, SSRF URL inspector, and static code scanner.", keywords: ["fim", "url", "scan-code"] },
    ],
  },
  {
    id: "devices",
    label: "Device Management",
    shortLabel: "ORBIT",
    group: "Operations & System",
    description: "ORBIT multi-device mesh, encrypted pairing, device permissions, location telemetry, and voice/notification controls.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 91, module: "devices", label: "ORBIT Overview", description: "Multi-device telemetry, active heartbeats, and live location status.", keywords: ["orbit", "devices", "mesh"] },
      { id: "connected", number: 92, module: "devices", label: "Connected Devices", description: "Pair new desktop/mobile nodes and revoke compromised devices.", keywords: ["pair", "revoke"] },
      { id: "permissions", number: 93, module: "devices", label: "Device Permissions", description: "Fine-grained read/write/command scopes per paired device.", keywords: ["permissions", "scopes"] },
      { id: "activity", number: 94, module: "devices", label: "Device Activity & Alerts", description: "Dispatch remote device tasks and inspect geofence/location alerts.", keywords: ["tasks", "location", "alerts"] },
      { id: "voice-mic", number: 95, module: "devices", label: "Voice & Microphone Settings", description: "Inspect browser SpeechRecognition/TTS capabilities and voice dispatch modes.", keywords: ["microphone", "voice", "audio"] },
      { id: "notif-settings", number: 96, module: "devices", label: "Notification Settings", description: "Review device alerts and tenant notification delivery settings.", keywords: ["notifications", "alerts"] },
    ],
  },
  {
    id: "finance",
    label: "Finance Centre",
    shortLabel: "Finance",
    group: "Operations & System",
    description: "Treasury ledger, budgets, reserves, investments, payment methods, and ApprovalGate spend limits.",
    defaultSubPage: "summary",
    subPages: [
      { id: "summary", number: 112, module: "finance", label: "Financial Command", description: "Transactions, budgets, investments, reserves, payment methods, and forecast telemetry.", keywords: ["finance", "treasury", "budgets"] },
    ],
  },
  {
    id: "caravan",
    label: "Caravan Funding",
    shortLabel: "Caravan",
    group: "Operations & System",
    description: "First-party funding intelligence, verified grant/loan discovery, NEON eligibility, and application tracking.",
    defaultSubPage: "overview",
    subPages: [
      { id: "overview", number: 113, module: "caravan", label: "Caravan Overview", description: "Verified funding counts, personalized recommendations, applications, and governance.", keywords: ["caravan", "funding", "grants"] },
      { id: "discover", number: 114, module: "caravan", label: "Discover Funding", description: "Search grants, loans, scholarships, accelerators, competitions, and investments.", keywords: ["discover", "grants", "loans"] },
      { id: "eligibility", number: 115, module: "caravan", label: "NEON Eligibility", description: "NEON-powered eligibility scoring, gap analysis, and recommendations.", keywords: ["eligibility", "neon", "score"] },
      { id: "applications", number: 116, module: "caravan", label: "My Applications", description: "Track draft, preparing, approval-gated, and submitted funding applications.", keywords: ["applications", "tracking"] },
      { id: "saved", number: 117, module: "caravan", label: "Saved Opportunities", description: "Bookmarked funding opportunities shortlist.", keywords: ["saved", "bookmarks"] },
      { id: "account", number: 118, module: "caravan", label: "Account & Subscription", description: "Customer onboarding profile, plan entitlements, support tickets, and alerts.", keywords: ["account", "subscription", "support"] },
      { id: "admin", number: 119, module: "caravan", label: "Admin & Verification", description: "Register real funding sources/opportunities and verify with supporting evidence.", keywords: ["admin", "verification", "sources"] },
      { id: "command-centre", number: 120, module: "caravan", label: "Caravan Command Centre", description: "Executive overview, funding intelligence control, NEON/ARGON monitoring, customer ops, and audit timeline.", keywords: ["command centre", "caravan", "operations"] },
    ],
  },
  {
    id: "settings",
    label: "Settings",
    shortLabel: "Settings",
    group: "Operations & System",
    description: "System configuration, appearance, theme, account, security, privacy, memory, accessibility, and diagnostics.",
    defaultSubPage: "general",
    subPages: [
      { id: "general", number: 97, module: "settings", label: "General Settings", description: "Persisted tenant system settings synchronized with /api/v1/settings.", keywords: ["general", "settings"] },
      { id: "appearance", number: 98, module: "settings", label: "Appearance", description: "Automatic device layout, dark/light mode, comfortable/compact density, and motion controls.", keywords: ["appearance", "dark", "light", "density"] },
      { id: "theme", number: 99, module: "settings", label: "Theme Configuration", description: "Customize restrained accent palette and surface contrast.", keywords: ["theme", "accent", "color"] },
      { id: "account", number: 100, module: "settings", label: "Account Settings", description: "Active user identity, role binding, and tenant organization identifier.", keywords: ["account", "tenant"] },
      { id: "profile", number: 101, module: "settings", label: "Profile", description: "Operator profile metadata and permission summary.", keywords: ["profile", "user"] },
      { id: "security-settings", number: 102, module: "settings", label: "Security Settings", description: "SENTINEL WebAuthn passkeys and single-use recovery code generation.", keywords: ["passkey", "recovery", "2fa"] },
      { id: "privacy", number: 103, module: "settings", label: "Privacy", description: "VAULT automatic secret redaction, payment data blocking, and zero-leak logging.", keywords: ["privacy", "vault", "redaction"] },
      { id: "memory-prefs", number: 104, module: "settings", label: "Memory Preferences", description: "Configure tenant memory retention and personalization via /api/v1/memory/preferences.", keywords: ["memory", "preferences"] },
      { id: "notifications", number: 105, module: "settings", label: "Notifications", description: "Manage system notifications and unread queue.", keywords: ["notifications", "alerts"] },
      { id: "locale", number: 106, module: "settings", label: "Language & Region", description: "Configure interface language, region, and UTC timestamp display.", keywords: ["language", "region", "timezone"] },
      { id: "shortcuts", number: 107, module: "settings", label: "Keyboard Shortcuts", description: "Command palette (⌘K / Ctrl+K) and fast desktop navigation chords.", keywords: ["keyboard", "shortcuts", "hotkeys"] },
      { id: "accessibility", number: 108, module: "settings", label: "Accessibility", description: "Reduced motion, high-contrast focus rings, and screen-reader support.", keywords: ["accessibility", "a11y", "motion"] },
      { id: "data", number: 109, module: "settings", label: "Data Management", description: "Storage backend status, TURBO cache management, and safe data export controls.", keywords: ["data", "storage", "cache"] },
      { id: "about", number: 110, module: "settings", label: "About ULTRON", description: "ULTRON OS 2026 release version, locked backend baseline ultron-backend-v1, and architecture.", keywords: ["about", "version", "release"] },
      { id: "diagnostics", number: 111, module: "settings", label: "System Diagnostics", description: "Live /health/ready JSON, /health provider state, and Prometheus metrics inspection.", keywords: ["diagnostics", "health", "prometheus"] },
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
