import React, { useEffect, useState } from "react";
import {
  Activity,
  Bell,
  Bot,
  Compass,
  Eye,
  FolderOpen,
  Globe,
  HardDrive,
  Hammer,
  KeyRound,
  Layers,
  LogOut,
  Menu,
  MessageSquare,
  Mic,
  Newspaper,
  Palette,
  Plug,
  Settings,
  Shield,
  TrendingUp,
  Wallet,
  Workflow,
} from "lucide-react";
import { apiFetch, AuthUser, clearSession, getStoredToken, getStoredUser, saveSession } from "./lib/api";
import { ArgonOrchestrationView } from "./components/ArgonOrchestrationView";
import { CommandCenterView } from "./components/CommandCenterView";
import { ActivityView, AgentsView, FileHubView, ForgeView, JarvisView, PreviewView, VoiceView } from "./components/CoreViews";
import { EarthGlobe } from "./components/EarthGlobe";
import { AtlasMapView, CaravanView, CreativeView, FinanceView, IntelligenceView, VaultView } from "./components/OpsViews";
import { DevicesView, IntegrationsView, MemoryView, NotificationsView, SecurityView, SettingsView } from "./components/SystemViews";

type ViewId =
  | "command" | "jarvis" | "argon" | "agents" | "activity"
  | "forge" | "preview" | "intelligence" | "atlas_map" | "files" | "voice" | "creative"
  | "caravan" | "finance" | "vault"
  | "memory" | "integrations" | "devices" | "security" | "notifications" | "settings";

const NAV_ITEMS: { id: ViewId; label: string; group: string; icon: React.ReactNode }[] = [
  { id: "command", label: "Command Center", group: "Command", icon: <Compass size={15} /> },
  { id: "jarvis", label: "NEON Intelligence", group: "Command", icon: <MessageSquare size={15} /> },
  { id: "argon", label: "ARGON Orchestrator", group: "Command", icon: <Workflow size={15} /> },
  { id: "agents", label: "60-Agent Directory", group: "Command", icon: <Bot size={15} /> },
  { id: "activity", label: "Tasks & Activity", group: "Command", icon: <Activity size={15} /> },
  { id: "forge", label: "Projects & FORGE", group: "Workspace", icon: <Hammer size={15} /> },
  { id: "preview", label: "Live Preview", group: "Workspace", icon: <Eye size={15} /> },
  { id: "intelligence", label: "Research & Intel", group: "Workspace", icon: <Newspaper size={15} /> },
  { id: "atlas_map", label: "ATLAS & Orders", group: "Workspace", icon: <Globe size={15} /> },
  { id: "files", label: "File Hub", group: "Workspace", icon: <FolderOpen size={15} /> },
  { id: "voice", label: "Voice Interface", group: "Workspace", icon: <Mic size={15} /> },
  { id: "creative", label: "Creative Studio", group: "Workspace", icon: <Palette size={15} /> },
  { id: "caravan", label: "PULSE & Caravan BI", group: "Operations", icon: <TrendingUp size={15} /> },
  { id: "finance", label: "Finance Centre", group: "Operations", icon: <Wallet size={15} /> },
  { id: "vault", label: "VAULT Secrets", group: "Operations", icon: <KeyRound size={15} /> },
  { id: "memory", label: "Memory Controls", group: "System", icon: <Layers size={15} /> },
  { id: "integrations", label: "Integrations", group: "System", icon: <Plug size={15} /> },
  { id: "devices", label: "Devices (ORBIT)", group: "System", icon: <HardDrive size={15} /> },
  { id: "security", label: "Security & AEGIS", group: "System", icon: <Shield size={15} /> },
  { id: "notifications", label: "Notifications", group: "System", icon: <Bell size={15} /> },
  { id: "settings", label: "Settings", group: "System", icon: <Settings size={15} /> },
];

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(() => (getStoredToken() ? getStoredUser() : null));
  const [view, setView] = useState<ViewId>("command");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [previewForgeId, setPreviewForgeId] = useState("");
  const [authMode, setAuthMode] = useState<"login" | "bootstrap">("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authErr, setAuthErr] = useState("");
  const [initialShare, setInitialShare] = useState<{ title: string; text: string; url: string } | null>(null);
  const [pendingJarvisPrompt, setPendingJarvisPrompt] = useState("");
  const [backendReady, setBackendReady] = useState<boolean | null>(null);
  const [backendDetail, setBackendDetail] = useState<string>("");

  useEffect(() => {
    fetch("/health/ready")
      .then(async (r) => {
        if (!r.ok) {
          setBackendReady(false);
          setBackendDetail(`Backend readiness probe returned HTTP ${r.status}.`);
          return;
        }
        const data = await r.json().catch(() => null);
        const ready = Boolean(data && data.status === "ready");
        setBackendReady(ready);
        if (!ready) {
          setBackendDetail(data?.database?.detail || "Backend database is not ready.");
        } else {
          setBackendDetail("");
        }
      })
      .catch(() => {
        setBackendReady(false);
        setBackendDetail("Unable to reach backend /health/ready endpoint.");
      });

    // Capture iOS / PWA Web Share Target query params (BRIDGE)
    const params = new URLSearchParams(window.location.search);
    const title = params.get("share_title") || "";
    const text = params.get("share_text") || "";
    const url = params.get("share_url") || "";
    if (title || text || url) {
      setInitialShare({ title, text, url });
      setView("jarvis");
      window.history.replaceState({}, "", "/");
    }
  }, []);

  async function handleAuth(e: React.FormEvent) {
    e.preventDefault();
    setAuthErr("");
    setAuthSubmitting(true);
    try {
      if (authMode === "bootstrap") {
        await apiFetch("/api/v1/auth/bootstrap-owner", {
          method: "POST",
          body: { username, email, password },
        });
      }
      const login = await apiFetch<any>("/api/v1/auth/login", {
        method: "POST",
        body: { username, password },
      });
      saveSession(login.access_token, login.user);
      setUser(login.user);
      setView("command");
    } catch (err: any) {
      setAuthErr(err.message);
    } finally {
      setAuthSubmitting(false);
    }
  }

  function logout() {
    clearSession();
    setUser(null);
  }

  if (!user) {
    return (
      <div className="auth-wrap">
        <div className="auth-shell">
          <div className="auth-orbital">
            <EarthGlobe
              size={260}
              ambient
              status={backendReady === false ? "degraded" : backendReady === null ? "loading" : "ready"}
            />
            <div>
              <div className="eyebrow-mono">ULTRON OPERATING SYSTEM · 2026</div>
              <h1 style={{ fontSize: 22, marginTop: 4 }}>Autonomous Command Kernel</h1>
              <p className="muted" style={{ margin: "6px 0 0", maxWidth: 300 }}>
                NEON intelligence · ARGON orchestration · 60 specialist agents · Zero-trust tenant isolation.
              </p>
            </div>
          </div>

          <form className="auth-card" onSubmit={handleAuth}>
            <div className="row-between">
              <div>
                <div className="brand-title">ZERO-TRUST ACCESS</div>
                <div className="muted">SENTINEL &amp; Argon2id authentication</div>
              </div>
              <span className={`pill ${backendReady === false ? "pill-warn" : backendReady === true ? "pill-green" : ""}`}>
                {backendReady === false ? "DEGRADED" : backendReady === true ? "READY" : "PROBING"}
              </span>
            </div>

            <div className="row">
              <button
                id="auth-tab-login"
                type="button"
                className={`btn btn-sm ${authMode === "login" ? "" : "btn-secondary"}`}
                onClick={() => setAuthMode("login")}
              >
                Sign In
              </button>
              <button
                id="auth-tab-bootstrap"
                type="button"
                className={`btn btn-sm ${authMode === "bootstrap" ? "" : "btn-secondary"}`}
                onClick={() => setAuthMode("bootstrap")}
              >
                First-Run Owner Setup
              </button>
            </div>

            {backendReady === false && backendDetail && (
              <div className="alert-box alert-warn">{backendDetail}</div>
            )}
            {authErr && <div className="alert-box alert-error">{authErr}</div>}

            <input
              id="auth-username"
              className="input"
              required
              autoComplete="username"
              placeholder="Username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            {authMode === "bootstrap" && (
              <input
                id="auth-email"
                className="input"
                required
                type="email"
                autoComplete="email"
                placeholder="Owner Email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            )}
            <input
              id="auth-password"
              className="input"
              required
              type="password"
              autoComplete={authMode === "bootstrap" ? "new-password" : "current-password"}
              placeholder="Password (min 12 chars for bootstrap)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button id="auth-submit" className="btn" type="submit" disabled={authSubmitting}>
              {authSubmitting
                ? "Verifying..."
                : authMode === "login"
                ? "Authenticate"
                : "Bootstrap Owner & Sign In"}
            </button>
          </form>
        </div>
      </div>
    );
  }

  const groups = ["Command", "Workspace", "Operations", "System"];

  function renderView() {
    switch (view) {
      case "command":
        return (
          <CommandCenterView
            backendReady={backendReady}
            backendDetail={backendDetail}
            onNavigate={(id) => setView(id as ViewId)}
            onSendToNeon={(prompt) => setPendingJarvisPrompt(prompt)}
          />
        );
      case "jarvis":
        return (
          <JarvisView
            initialShare={initialShare}
            pendingPrompt={pendingJarvisPrompt}
            onClearPendingPrompt={() => setPendingJarvisPrompt("")}
          />
        );
      case "argon":
        return <ArgonOrchestrationView />;
      case "voice":
        return <VoiceView />;
      case "agents":
        return <AgentsView />;
      case "activity":
        return <ActivityView />;
      case "files":
        return (
          <FileHubView
            onAnalyzeInJarvis={(prompt) => {
              setPendingJarvisPrompt(prompt);
              setView("jarvis");
            }}
          />
        );
      case "forge":
        return (
          <ForgeView
            onOpenPreview={(fid) => {
              setPreviewForgeId(fid);
              setView("preview");
            }}
          />
        );
      case "preview":
        return <PreviewView forgeId={previewForgeId} />;
      case "creative":
        return <CreativeView />;
      case "finance":
        return <FinanceView />;
      case "vault":
        return <VaultView />;
      case "atlas_map":
        return <AtlasMapView />;
      case "intelligence":
        return <IntelligenceView />;
      case "caravan":
        return <CaravanView />;
      case "devices":
        return <DevicesView />;
      case "integrations":
        return <IntegrationsView />;
      case "memory":
        return <MemoryView />;
      case "security":
        return <SecurityView />;
      case "notifications":
        return <NotificationsView />;
      case "settings":
        return <SettingsView />;
    }
  }

  return (
    <div className="app-shell">
      {drawerOpen && <div className="drawer-backdrop" onClick={() => setDrawerOpen(false)} />}
      <aside className={`sidebar ${drawerOpen ? "open" : ""}`} aria-label="ULTRON OS Navigation">
        <div className="brand">
          <div className="brand-mark">U</div>
          <div>
            <div className="brand-title">ULTRON OS 2026</div>
            <div className="muted mono" style={{ fontSize: 10.5 }}>
              {user.username} · {user.role}
            </div>
          </div>
        </div>
        {groups.map((grp) => (
          <div key={grp}>
            <div className="nav-section">{grp}</div>
            {NAV_ITEMS.filter((n) => n.group === grp).map((n) => (
              <button
                key={n.id}
                id={`nav-${n.id}`}
                type="button"
                className={`nav-btn ${view === n.id ? "active" : ""}`}
                onClick={() => {
                  setView(n.id);
                  setDrawerOpen(false);
                }}
              >
                {n.icon}
                <span>{n.label}</span>
              </button>
            ))}
          </div>
        ))}
        <div style={{ marginTop: "auto", paddingTop: 14, borderTop: "1px solid var(--border)" }}>
          <button id="nav-logout" type="button" className="nav-btn" onClick={logout}>
            <LogOut size={15} />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <div className="row">
            <button
              id="mobile-drawer-open"
              type="button"
              className="btn btn-secondary btn-sm mobile-menu-btn"
              onClick={() => setDrawerOpen(true)}
              aria-label="Open navigation menu"
            >
              <Menu size={16} />
            </button>
            <span className="topbar-title">{NAV_ITEMS.find((n) => n.id === view)?.label}</span>
          </div>
          <div className="row">
            <span className={`pill ${backendReady === false ? "pill-warn" : "pill-green"}`}>
              {backendReady === false ? "DEGRADED" : "ONLINE"}
            </span>
            <button
              id="topbar-notifications"
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setView("notifications")}
              aria-label="Notifications"
            >
              <Bell size={14} />
            </button>
          </div>
        </header>

        <main className="content">{renderView()}</main>
      </div>

      <nav className="mobile-nav" aria-label="Mobile quick navigation">
        {([
          { id: "command", label: "Command", icon: <Compass size={17} /> },
          { id: "jarvis", label: "NEON", icon: <MessageSquare size={17} /> },
          { id: "argon", label: "ARGON", icon: <Workflow size={17} /> },
          { id: "agents", label: "Agents", icon: <Bot size={17} /> },
          { id: "security", label: "Security", icon: <Shield size={17} /> },
        ] as const).map((tab) => (
          <button
            key={tab.id}
            id={`mobile-tab-${tab.id}`}
            type="button"
            className={`mobile-tab ${view === tab.id ? "active" : ""}`}
            onClick={() => setView(tab.id)}
          >
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
