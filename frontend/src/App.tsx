import React, { lazy, Suspense, useEffect, useState } from "react";
import { apiFetch, AuthUser, clearSession, getStoredToken, getStoredUser, saveSession } from "./lib/api";
import { useDeviceProfile } from "./lib/device";
import { usePreferences } from "./lib/preferences";
import { ALL_PAGES, getModule, getSubPage, MODULES, ModuleId } from "./catalog/navigation";
import { EarthGlobe } from "./components/EarthGlobe";
import { UltronLogo } from "./components/UltronLogo";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { AppShell, DesktopSidebar, MobileNavigation, ModuleIcon, TopBar } from "./components/ui/AppShell";
import { CommandPalette, Drawer, LoadingState, MetricDisplay, StatusIndicator } from "./components/ui/DesignSystem";

const CommandModulePage = lazy(() => import("./pages/CommandModulePage"));
const NeonModulePage = lazy(() => import("./pages/NeonModulePage"));
const ArgonModulePage = lazy(() => import("./pages/ArgonModulePage"));
const AgentsModulePage = lazy(() => import("./pages/AgentsModulePage"));
const ConnectionsModulePage = lazy(() => import("./pages/ConnectionsModulePage"));
const FilesKnowledgeModulePage = lazy(() => import("./pages/FilesKnowledgeModulePage"));
const ProjectsModulePage = lazy(() => import("./pages/ProjectsModulePage"));
const ResearchModulePage = lazy(() => import("./pages/ResearchModulePage"));
const CreativeModulePage = lazy(() => import("./pages/CreativeModulePage"));
const PulseModulePage = lazy(() => import("./pages/PulseModulePage"));
const SecurityModulePage = lazy(() => import("./pages/SecurityModulePage"));
const DevicesModulePage = lazy(() => import("./pages/DevicesModulePage"));
const FinanceModulePage = lazy(() => import("./pages/FinanceModulePage"));
const SettingsModulePage = lazy(() => import("./pages/SettingsModulePage"));

export default function App() {
  const { prefs, updatePrefs } = usePreferences();
  const device = useDeviceProfile(prefs.layoutMode);

  const [user, setUser] = useState<AuthUser | null>(() => (getStoredToken() ? getStoredUser() : null));
  const [activeModule, setActiveModule] = useState<ModuleId>("command");
  const [activeSubPage, setActiveSubPage] = useState<string>("home");
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [moreDrawerOpen, setMoreDrawerOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Auth form state
  const [authMode, setAuthMode] = useState<"login" | "bootstrap">("login");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authSubmitting, setAuthSubmitting] = useState(false);
  const [authErr, setAuthErr] = useState("");

  // Global backend health & cross-module state
  const [backendReady, setBackendReady] = useState<boolean | null>(null);
  const [backendDetail, setBackendDetail] = useState<string>("");
  const [initialShare, setInitialShare] = useState<{ title: string; text: string; url: string } | null>(null);
  const [pendingNeonPrompt, setPendingNeonPrompt] = useState("");

  function navigate(moduleId: ModuleId, subPageId?: string) {
    const mod = getModule(moduleId);
    setActiveModule(moduleId);
    setActiveSubPage(subPageId || mod.defaultSubPage);
    setDrawerOpen(false);
    setMoreDrawerOpen(false);
  }

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
        setBackendDetail(ready ? "" : data?.database?.detail || "Backend database is not ready.");
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
      navigate("neon", "chat");
      window.history.replaceState({}, "", "/");
    }
  }, []);

  // Global keyboard shortcuts (Cmd/Ctrl+K Command Palette & Alt+1..6 quick nav)
  useEffect(() => {
    if (!user) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
        return;
      }
      if (e.altKey) {
        if (e.key === "1") navigate("command", "home");
        if (e.key === "2") navigate("neon", "chat");
        if (e.key === "3") navigate("argon", "overview");
        if (e.key === "4") navigate("agents", "directory");
        if (e.key === "5") navigate("connections", "directory");
        if (e.key === "6") navigate("settings", "appearance");
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [user]);

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
      navigate("command", "home");
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
            <UltronLogo variant="compact" size={30} />
            <EarthGlobe
              size={device.isMobile ? 210 : 250}
              ambient
              status={backendReady === false ? "degraded" : backendReady === null ? "loading" : "ready"}
            />
            <div>
              <div className="eyebrow-mono">PERSONAL OPERATING SYSTEM · 2026</div>
              <h1 style={{ fontSize: 22, marginTop: 4 }}>Autonomous Command Kernel</h1>
              <p className="muted" style={{ margin: "6px 0 0", maxWidth: 320 }}>
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
              <StatusIndicator
                label={backendReady === false ? "DEGRADED" : backendReady === true ? "READY" : "PROBING"}
                tone={backendReady === false ? "warn" : backendReady === true ? "success" : "neutral"}
              />
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

  const currentMod = getModule(activeModule);
  const currentSub = getSubPage(activeModule, activeSubPage);

  const sharedProps = {
    subPage: currentSub.id,
    onSelectSubPage: (sub: string) => setActiveSubPage(sub),
    onNavigate: navigate,
    user,
    device,
    pendingPrompt: pendingNeonPrompt,
    onClearPendingPrompt: () => setPendingNeonPrompt(""),
    onSendToNeon: (p: string) => setPendingNeonPrompt(p),
    initialShare,
  };

  function renderModule() {
    switch (activeModule) {
      case "command": return <CommandModulePage {...sharedProps} />;
      case "neon": return <NeonModulePage {...sharedProps} />;
      case "argon": return <ArgonModulePage {...sharedProps} />;
      case "agents": return <AgentsModulePage {...sharedProps} />;
      case "connections": return <ConnectionsModulePage {...sharedProps} />;
      case "files": return <FilesKnowledgeModulePage {...sharedProps} />;
      case "projects": return <ProjectsModulePage {...sharedProps} />;
      case "research": return <ResearchModulePage {...sharedProps} />;
      case "creative": return <CreativeModulePage {...sharedProps} />;
      case "pulse": return <PulseModulePage {...sharedProps} />;
      case "security": return <SecurityModulePage {...sharedProps} />;
      case "devices": return <DevicesModulePage {...sharedProps} />;
      case "finance": return <FinanceModulePage {...sharedProps} />;
      case "settings": return <SettingsModulePage {...sharedProps} />;
    }
  }

  const rightPanelNode = prefs.rightPanelOpen ? (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <div className="eyebrow-mono">CONTEXTUAL TELEMETRY</div>
      <MetricDisplay label="Active Module" value={currentMod.shortLabel} sub={`Page ${currentSub.number} / ${ALL_PAGES.length}`} tone="info" />
      <MetricDisplay label="Viewport Profile" value={device.deviceClass.toUpperCase()} sub={`${device.width}×${device.height}`} tone="neutral" />
      <MetricDisplay label="Theme / Density" value={`${prefs.theme.toUpperCase()} · ${prefs.density.toUpperCase()}`} sub={`Accent: ${prefs.accent}`} tone="success" />
      <div className="list-item">
        <div className="telemetry-label">QUICK JUMP</div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 6 }}>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => setPaletteOpen(true)}>Open Command Palette (⌘K)</button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => navigate("connections", "directory")}>Connections Centre (38)</button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => navigate("settings", "appearance")}>Appearance &amp; Theme</button>
        </div>
      </div>
    </div>
  ) : undefined;

  return (
    <>
      <AppShell
        device={device}
        sidebar={
          <DesktopSidebar
            user={user}
            activeModule={activeModule}
            collapsed={prefs.sidebarCollapsed}
            drawerOpen={drawerOpen}
            onSelectModule={(m) => navigate(m)}
            onToggleCollapse={() => updatePrefs({ sidebarCollapsed: !prefs.sidebarCollapsed })}
            onCloseDrawer={() => setDrawerOpen(false)}
            onLogout={logout}
          />
        }
        topbar={
          <TopBar
            title={`${currentMod.label}${device.isDesktop ? ` · ${currentSub.label}` : ""}`}
            device={device}
            backendReady={backendReady}
            onOpenDrawer={() => setDrawerOpen(true)}
            onOpenPalette={() => setPaletteOpen(true)}
            onOpenNotifications={() => navigate("command", "notifications")}
            onToggleRightPanel={() => updatePrefs({ rightPanelOpen: !prefs.rightPanelOpen })}
          />
        }
        mobileNav={
          <MobileNavigation
            activeModule={activeModule}
            onSelectModule={(m) => navigate(m)}
            onOpenMore={() => setMoreDrawerOpen(true)}
          />
        }
        rightPanel={rightPanelNode}
      >
        <ErrorBoundary resetKey={`${activeModule}:${activeSubPage}`}>
          <Suspense fallback={<LoadingState label={`Loading ${currentMod.label}...`} />}>
            {renderModule()}
          </Suspense>
        </ErrorBoundary>
      </AppShell>

      {/* Mobile "More" Secondary Navigation Drawer (All 14 Modules + Quick Search) */}
      <Drawer open={moreDrawerOpen} title="All ULTRON Modules" onClose={() => setMoreDrawerOpen(false)}>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => {
              setMoreDrawerOpen(false);
              setPaletteOpen(true);
            }}
          >
            Search All 111+ Pages...
          </button>
          {MODULES.map((m) => (
            <button
              key={m.id}
              id={`more-nav-${m.id}`}
              type="button"
              className={`list-item list-item-btn ${activeModule === m.id ? "list-item-active" : ""}`}
              onClick={() => navigate(m.id)}
            >
              <div className="row-between" style={{ width: "100%" }}>
                <div className="row">
                  <ModuleIcon id={m.id} size={16} />
                  <strong>{m.label}</strong>
                </div>
                <span className="pill mono">{m.subPages.length}p</span>
              </div>
              <div className="muted">{m.description}</div>
            </button>
          ))}
        </div>
      </Drawer>

      {/* Global Cmd/Ctrl+K Command Palette */}
      <CommandPalette
        open={paletteOpen}
        onClose={() => setPaletteOpen(false)}
        onNavigate={(m, sub) => navigate(m, sub)}
      />
    </>
  );
}
