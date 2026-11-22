import React, { useEffect, useState } from "react";
import {
  Activity,
  Bell,
  Bot,
  Cpu,
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
} from "lucide-react";
import { apiFetch, AuthUser, clearSession, getStoredToken, getStoredUser, saveSession } from "./lib/api";
import { ActivityView, AgentsView, FileHubView, ForgeView, JarvisView, PreviewView, VoiceView } from "./components/CoreViews";
import { AtlasMapView, CaravanView, CreativeView, FinanceView, IntelligenceView, VaultView } from "./components/OpsViews";
import { DevicesView, IntegrationsView, MemoryView, NotificationsView, SecurityView, SettingsView } from "./components/SystemViews";

type ViewId =
  | "jarvis" | "voice" | "agents" | "activity" | "files" | "forge" | "preview"
  | "creative" | "finance" | "vault" | "atlas_map" | "intelligence" | "caravan"
  | "devices" | "integrations" | "memory" | "security" | "notifications" | "settings";

const NAV_ITEMS: { id: ViewId; label: string; group: string; icon: React.ReactNode }[] = [
  { id: "jarvis", label: "JARVIS Chat", group: "Command", icon: <MessageSquare size={16} /> },
  { id: "voice", label: "Voice Command", group: "Command", icon: <Mic size={16} /> },
  { id: "agents", label: "Agent Centre (60)", group: "Command", icon: <Bot size={16} /> },
  { id: "activity", label: "Activity & Approvals", group: "Command", icon: <Activity size={16} /> },
  { id: "files", label: "File Hub", group: "Workspace", icon: <FolderOpen size={16} /> },
  { id: "forge", label: "Forge Workspace", group: "Workspace", icon: <Hammer size={16} /> },
  { id: "preview", label: "Live Preview", group: "Workspace", icon: <Eye size={16} /> },
  { id: "creative", label: "Creative Studio", group: "Workspace", icon: <Palette size={16} /> },
  { id: "finance", label: "Finance Centre", group: "Operations", icon: <Wallet size={16} /> },
  { id: "vault", label: "Vault Secrets", group: "Operations", icon: <KeyRound size={16} /> },
  { id: "atlas_map", label: "Atlas Map & Orders", group: "Operations", icon: <Globe size={16} /> },
  { id: "intelligence", label: "World Intelligence", group: "Operations", icon: <Newspaper size={16} /> },
  { id: "caravan", label: "Caravan BI & Pulse", group: "Operations", icon: <TrendingUp size={16} /> },
  { id: "devices", label: "Device Centre (ORBIT)", group: "System", icon: <HardDrive size={16} /> },
  { id: "integrations", label: "Integrations", group: "System", icon: <Plug size={16} /> },
  { id: "memory", label: "Memory Settings", group: "System", icon: <Layers size={16} /> },
  { id: "security", label: "Security (AEGIS/EVOLVE)", group: "System", icon: <Shield size={16} /> },
  { id: "notifications", label: "Notifications", group: "System", icon: <Bell size={16} /> },
  { id: "settings", label: "User Settings", group: "System", icon: <Settings size={16} /> },
];

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(() => (getStoredToken() ? getStoredUser() : null));
  const [view, setView] = useState<ViewId>("jarvis");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [previewForgeId, setPreviewForgeId] = useState("");
  const [authMode, setAuthMode] = useState<"login" | "bootstrap">("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authErr, setAuthErr] = useState("");
  const [initialShare, setInitialShare] = useState<{ title: string; text: string; url: string } | null>(null);

  useEffect(() => {
    // Capture iOS / PWA Web Share Target query params (BRIDGE)
    const params = new URLSearchParams(window.location.search);
    const title = params.get("share_title") || "";
    const text = params.get("share_text") || "";
    const url = params.get("share_url") || "";
    if (title || text || url) {
      setInitialShare({ title, text, url });
      window.history.replaceState({}, "", "/");
    }
  }, []);

  async function handleAuth(e: React.FormEvent) {
    e.preventDefault();
    setAuthErr("");
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
    } catch (err: any) {
      setAuthErr(err.message);
    }
  }

  function logout() {
    clearSession();
    setUser(null);
  }

  if (!user) {
    return (
      <div className="auth-wrap">
        <form className="auth-card" onSubmit={handleAuth}>
          <div className="row">
            <div className="brand-mark">U</div>
            <div>
              <strong>ULTRON OS 2026</strong>
              <div className="muted">Zero-Trust Command Authentication</div>
            </div>
          </div>
          <div className="row">
            <button type="button" className={`btn btn-sm ${authMode === "login" ? "" : "btn-secondary"}`} onClick={() => setAuthMode("login")}>Sign In</button>
            <button type="button" className={`btn btn-sm ${authMode === "bootstrap" ? "" : "btn-secondary"}`} onClick={() => setAuthMode("bootstrap")}>First-Run Owner Setup</button>
          </div>
          {authErr && <div className="alert-box alert-error">{authErr}</div>}
          <input className="input" required placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} />
          {authMode === "bootstrap" && (
            <input className="input" required type="email" placeholder="Owner Email" value={email} onChange={(e) => setEmail(e.target.value)} />
          )}
          <input className="input" required type="password" placeholder="Password (min 12 chars for bootstrap)" value={password} onChange={(e) => setPassword(e.target.value)} />
          <button className="btn" type="submit">{authMode === "login" ? "Authenticate" : "Bootstrap Owner & Sign In"}</button>
        </form>
      </div>
    );
  }

  const groups = ["Command", "Workspace", "Operations", "System"];

  function renderView() {
    switch (view) {
      case "jarvis": return <JarvisView initialShare={initialShare} />;
      case "voice": return <VoiceView />;
      case "agents": return <AgentsView />;
      case "activity": return <ActivityView />;
      case "files": return <FileHubView />;
      case "forge": return <ForgeView onOpenPreview={(fid) => { setPreviewForgeId(fid); setView("preview"); }} />;
      case "preview": return <PreviewView forgeId={previewForgeId} />;
      case "creative": return <CreativeView />;
      case "finance": return <FinanceView />;
      case "vault": return <VaultView />;
      case "atlas_map": return <AtlasMapView />;
      case "intelligence": return <IntelligenceView />;
      case "caravan": return <CaravanView />;
      case "devices": return <DevicesView />;
      case "integrations": return <IntegrationsView />;
      case "memory": return <MemoryView />;
      case "security": return <SecurityView />;
      case "notifications": return <NotificationsView />;
      case "settings": return <SettingsView />;
    }
  }

  return (
    <div className="app-shell">
      {drawerOpen && <div className="drawer-backdrop" onClick={() => setDrawerOpen(false)} />}
      <aside className={`sidebar ${drawerOpen ? "open" : ""}`}>
        <div className="brand">
          <div className="brand-mark"><Cpu size={16} /></div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14 }}>ULTRON OS 2026</div>
            <div className="muted" style={{ fontSize: 11 }}>{user.username} · {user.role}</div>
          </div>
        </div>
        {groups.map((grp) => (
          <div key={grp}>
            <div className="nav-section">{grp}</div>
            {NAV_ITEMS.filter((n) => n.group === grp).map((n) => (
              <button
                key={n.id}
                className={`nav-btn ${view === n.id ? "active" : ""}`}
                onClick={() => { setView(n.id); setDrawerOpen(false); }}
              >
                {n.icon}
                <span>{n.label}</span>
              </button>
            ))}
          </div>
        ))}
        <div style={{ marginTop: "auto", paddingTop: 12 }}>
          <button className="nav-btn" onClick={logout}><LogOut size={16} /><span>Sign Out</span></button>
        </div>
      </aside>

      <div className="main-area">
        <header className="topbar">
          <div className="row">
            <button className="btn btn-secondary btn-sm mobile-menu-btn" onClick={() => setDrawerOpen(true)}>
              <Menu size={16} />
            </button>
            <strong>{NAV_ITEMS.find((n) => n.id === view)?.label}</strong>
          </div>
          <div className="row">
            <span className="pill pill-cyan">AEGIS ACTIVE</span>
            <button className="btn btn-secondary btn-sm" onClick={() => setView("notifications")}><Bell size={14} /></button>
          </div>
        </header>

        <main className="content">{renderView()}</main>
      </div>

      <nav className="mobile-nav">
        {([
          { id: "jarvis", label: "JARVIS", icon: <MessageSquare size={18} /> },
          { id: "voice", label: "Voice", icon: <Mic size={18} /> },
          { id: "agents", label: "Agents", icon: <Bot size={18} /> },
          { id: "forge", label: "Forge", icon: <Hammer size={18} /> },
          { id: "security", label: "AEGIS", icon: <Shield size={18} /> },
        ] as const).map((tab) => (
          <button key={tab.id} className={`mobile-tab ${view === tab.id ? "active" : ""}`} onClick={() => setView(tab.id)}>
            {tab.icon}
            <span>{tab.label}</span>
          </button>
        ))}
      </nav>
    </div>
  );
}
