import React, { Suspense, useCallback, useEffect, useState } from "react";
import {
  apiFetch,
  AUTH_STATE_EVENT,
  AuthUser,
  clearSession,
  getStoredRefreshToken,
  getStoredToken,
  getStoredUser,
  isAccessTokenExpiredOrExpiring,
  refreshAccessTokenSingleFlight,
  saveSession,
} from "./lib/api";
import { useDeviceProfile } from "./lib/device";
import { lazyWithRecovery } from "./lib/lazyWithRecovery";
import { usePreferences } from "./lib/preferences";
import { ALL_PAGES, getModule, getSubPage, MODULES, ModuleId } from "./catalog/navigation";
import { EarthGlobe } from "./components/EarthGlobe";
import { UltronLogo } from "./components/UltronLogo";
import { ErrorBoundary } from "./components/ui/ErrorBoundary";
import { AppShell, DesktopSidebar, MobileNavigation, ModuleIcon, TopBar } from "./components/ui/AppShell";
import { CommandPalette, Drawer, LoadingState, MetricDisplay, StatusIndicator } from "./components/ui/DesignSystem";

const CommandModulePage = lazyWithRecovery(() => import("./pages/CommandModulePage"), "Command Centre");
const NeonModulePage = lazyWithRecovery(() => import("./pages/NeonModulePage"), "NEON Intelligence");
const ArgonModulePage = lazyWithRecovery(() => import("./pages/ArgonModulePage"), "ARGON Orchestration");
const AgentsModulePage = lazyWithRecovery(() => import("./pages/AgentsModulePage"), "The 60 Agents");
const ConnectionsModulePage = lazyWithRecovery(() => import("./pages/ConnectionsModulePage"), "Connections Centre");
const FilesKnowledgeModulePage = lazyWithRecovery(() => import("./pages/FilesKnowledgeModulePage"), "Files & Knowledge");
const ProjectsModulePage = lazyWithRecovery(() => import("./pages/ProjectsModulePage"), "Projects & FORGE");
const ResearchModulePage = lazyWithRecovery(() => import("./pages/ResearchModulePage"), "Research & Intel");
const CreativeModulePage = lazyWithRecovery(() => import("./pages/CreativeModulePage"), "Creative Studio");
const PulseModulePage = lazyWithRecovery(() => import("./pages/PulseModulePage"), "PULSE & Automation");
const SecurityModulePage = lazyWithRecovery(() => import("./pages/SecurityModulePage"), "Security Centre");
const DevicesModulePage = lazyWithRecovery(() => import("./pages/DevicesModulePage"), "Device Management");
const FinanceModulePage = lazyWithRecovery(() => import("./pages/FinanceModulePage"), "Finance Centre");
const CaravanModulePage = lazyWithRecovery(() => import("./pages/CaravanModulePage"), "Caravan Funding");
const SettingsModulePage = lazyWithRecovery(() => import("./pages/SettingsModulePage"), "Settings");

const VALID_MODULE_IDS = new Set<string>(MODULES.map((m) => m.id));

function parseRouteFromPathname(pathname: string): { moduleId: ModuleId; subPageId: string } {
  const parts = pathname
    .replace(/^\/+|\/+$/g, "")
    .split("/")
    .filter(Boolean);
  const rawMod = parts[0]?.toLowerCase() || "";
  if (VALID_MODULE_IDS.has(rawMod)) {
    const mod = getModule(rawMod as ModuleId);
    const sub = parts[1] ? getSubPage(mod.id, parts[1]).id : mod.defaultSubPage;
    return { moduleId: mod.id, subPageId: sub };
  }
  return { moduleId: "command", subPageId: "home" };
}

function buildRoutePath(moduleId: ModuleId, subPageId: string): string {
  return `/${moduleId}/${subPageId}`;
}

export default function App() {
  const { prefs, updatePrefs } = usePreferences();
  const device = useDeviceProfile(prefs.layoutMode);

  const [user, setUser] = useState<AuthUser | null>(() => (getStoredToken() ? getStoredUser() : null));
  const initialRoute = parseRouteFromPathname(typeof window !== "undefined" ? window.location.pathname : "/");
  const [activeModule, setActiveModule] = useState<ModuleId>(initialRoute.moduleId);
  const [activeSubPage, setActiveSubPage] = useState<string>(initialRoute.subPageId);
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
  const [backendMeta, setBackendMeta] = useState<{
    errorCode?: string;
    backend?: string;
    port?: number | null;
    usesPooler?: boolean;
    sslEnforced?: boolean;
  } | null>(null);
  const [probingHealth, setProbingHealth] = useState(false);
  const [initialShare, setInitialShare] = useState<{ title: string; text: string; url: string } | null>(null);
  const [pendingNeonPrompt, setPendingNeonPrompt] = useState("");
  const [pendingNeonFiles, setPendingNeonFiles] = useState<Array<{ file_id: string; filename: string; mime_type: string; is_image?: boolean; size_bytes?: number }>>([]);

  const navigate = useCallback((moduleId: ModuleId, subPageId?: string, opts?: { replace?: boolean }) => {
    const mod = getModule(moduleId);
    const resolvedSub = subPageId ? getSubPage(moduleId, subPageId).id : mod.defaultSubPage;
    setActiveModule(moduleId);
    setActiveSubPage(resolvedSub);
    setDrawerOpen(false);
    setMoreDrawerOpen(false);
    const nextPath = buildRoutePath(moduleId, resolvedSub);
    if (typeof window !== "undefined" && window.location.pathname !== nextPath) {
      if (opts?.replace) {
        window.history.replaceState({}, "", nextPath);
      } else {
        window.history.pushState({}, "", nextPath);
      }
    }
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.location.pathname === "/oauth/callback") {
      const params = new URLSearchParams(window.location.search);
      const oauthError = params.get("error");
      const code = params.get("code");
      const state = params.get("state");
      const provider = params.get("provider") || sessionStorage.getItem("ultron_pending_oauth_provider");
      window.history.replaceState({}, document.title, "/command/integrations");
      if (oauthError) {
        sessionStorage.removeItem("ultron_pending_oauth_provider");
        const msg =
          oauthError === "access_denied"
            ? "Google authorization was cancelled or denied by the user."
            : `OAuth authorization failed: ${oauthError}`;
        sessionStorage.setItem("ultron_oauth_feedback", JSON.stringify({ type: "error", message: msg }));
        navigate("command", "integrations", { replace: true });
      } else if (code && state && provider) {
        apiFetch<any>(`/api/v1/integrations/oauth/${encodeURIComponent(provider)}/callback`, {
          method: "POST",
          body: {
            code,
            state,
            redirect_uri: `${window.location.origin}/oauth/callback`,
          },
        })
          .then((res) => {
            sessionStorage.removeItem("ultron_pending_oauth_provider");
            const msg = `${provider} connected${res?.live_verified ? " and Live Verified" : ""}.`;
            sessionStorage.setItem("ultron_oauth_feedback", JSON.stringify({ type: "success", message: msg }));
            navigate("command", "integrations", { replace: true });
          })
          .catch((err) => {
            sessionStorage.removeItem("ultron_pending_oauth_provider");
            sessionStorage.setItem(
              "ultron_oauth_feedback",
              JSON.stringify({ type: "error", message: err?.message || "OAuth callback exchange failed." })
            );
            navigate("command", "integrations", { replace: true });
          });
      } else {
        navigate("command", "integrations", { replace: true });
      }
    }
  }, [navigate]);

  useEffect(() => {
    const onPopState = () => {
      const next = parseRouteFromPathname(window.location.pathname);
      setActiveModule(next.moduleId);
      setActiveSubPage(next.subPageId);
      setDrawerOpen(false);
      setMoreDrawerOpen(false);
    };
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  async function probeBackendReadiness() {
    setProbingHealth(true);
    try {
      const r = await fetch("/health/ready", { cache: "no-store" });
      const data = await r.json().catch(() => null);
      const db = data?.database;
      const isReady = Boolean(r.ok && data?.status === "ready" && db?.healthy !== false);
      setBackendReady(isReady);
      if (isReady) {
        setBackendDetail("");
        setBackendMeta(null);
        // Clear any stale database-availability auth error once DB recovers
        setAuthErr((prev) =>
          prev && /postgresql|database|ultron_database_url|db_auth_failed/i.test(prev) ? "" : prev
        );
      } else {
        const detail =
          db?.detail ||
          data?.error?.message ||
          (!r.ok ? `Backend readiness probe returned HTTP ${r.status}.` : "Backend database is not ready.");
        setBackendDetail(detail);
        setBackendMeta(
          db
            ? {
                errorCode: db.error_code || undefined,
                backend: db.backend || undefined,
                port: db.port ?? null,
                usesPooler: Boolean(db.uses_pooler),
                sslEnforced: Boolean(db.sslmode_enforced),
              }
            : null
        );
      }
    } catch {
      setBackendReady(false);
      setBackendDetail("Unable to reach backend /health/ready endpoint.");
      setBackendMeta(null);
    } finally {
      setProbingHealth(false);
    }
  }

  useEffect(() => {
    probeBackendReadiness();

    // Capture iOS / PWA Web Share Target query params (BRIDGE)
    const params = new URLSearchParams(window.location.search);
    const title = params.get("share_title") || "";
    const text = params.get("share_text") || "";
    const url = params.get("share_url") || "";
    if (title || text || url) {
      setInitialShare({ title, text, url });
      navigate("neon", "chat", { replace: true });
    }
  }, [navigate]);

  // Auto-recheck readiness on window focus or every 20s while unauthenticated & degraded
  useEffect(() => {
    if (user || backendReady !== false) return;
    const onFocus = () => probeBackendReadiness();
    window.addEventListener("focus", onFocus);
    const timer = window.setInterval(() => probeBackendReadiness(), 20000);
    return () => {
      window.removeEventListener("focus", onFocus);
      window.clearInterval(timer);
    };
  }, [user, backendReady]);

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
  }, [user, navigate]);

  // Keep React auth state synchronized with shared API client token refreshes and session expirations
  useEffect(() => {
    const onAuthChanged = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail && "user" in detail) {
        setUser(detail.user || null);
        if (!detail.user && detail.reason === "session_expired") {
          setAuthErr("Your session expired. Please sign in again.");
        }
      } else {
        setUser(getStoredToken() ? getStoredUser() : null);
      }
    };
    window.addEventListener(AUTH_STATE_EVENT, onAuthChanged);
    return () => window.removeEventListener(AUTH_STATE_EVENT, onAuthChanged);
  }, []);

  // Validate or refresh session on initial boot and whenever the installed iOS PWA returns to foreground
  useEffect(() => {
    if (!user) return;
    const ensureFreshSession = async () => {
      const token = getStoredToken();
      if (!token) {
        clearSession("session_expired");
        return;
      }
      if (isAccessTokenExpiredOrExpiring(token, 45)) {
        if (getStoredRefreshToken()) {
          const refreshed = await refreshAccessTokenSingleFlight();
          if (!refreshed) {
            clearSession("session_expired");
          }
        } else {
          // Legacy session stored before refresh_token persistence whose JWT is already expired
          clearSession("session_expired");
        }
      }
    };
    ensureFreshSession();
    const onVisibility = () => {
      if (document.visibilityState === "visible") {
        ensureFreshSession();
      }
    };
    window.addEventListener("focus", ensureFreshSession);
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      window.removeEventListener("focus", ensureFreshSession);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [user]);

  async function handleAuth(e: React.FormEvent) {
    e.preventDefault();
    if (backendReady === false) {
      await probeBackendReadiness();
      return;
    }
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
      saveSession(login.access_token, login.user, login.refresh_token, login.expires_at);
      setUser(login.user);
      const target = parseRouteFromPathname(window.location.pathname);
      navigate(target.moduleId, target.subPageId, { replace: true });
    } catch (err: any) {
      const msg = String(err?.message || "Authentication failed.");
      // If auth failed due to database unavailability, refresh readiness so a single unified panel is shown
      if (/postgresql|database|ultron_database_url|db_auth_failed/i.test(msg)) {
        setBackendReady(false);
        setBackendDetail(msg);
        setAuthErr("");
      } else {
        setAuthErr(msg);
      }
    } finally {
      setAuthSubmitting(false);
    }
  }

  function logout() {
    apiFetch("/api/v1/auth/logout", { method: "POST" }).catch(() => {});
    clearSession("logged_out");
    setUser(null);
  }

  if (!user) {
    const normalizedBackend = backendDetail.trim().toLowerCase();
    const normalizedAuth = authErr.trim().toLowerCase();
    const showDistinctAuthErr = Boolean(
      normalizedAuth &&
        (!normalizedBackend ||
          (normalizedAuth !== normalizedBackend &&
            !normalizedAuth.includes(normalizedBackend) &&
            !normalizedBackend.includes(normalizedAuth)))
    );
    const dbUnavailable = backendReady === false;

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
                onClick={() => {
                  setAuthMode("login");
                  setAuthErr("");
                }}
              >
                Sign In
              </button>
              <button
                id="auth-tab-bootstrap"
                type="button"
                className={`btn btn-sm ${authMode === "bootstrap" ? "" : "btn-secondary"}`}
                onClick={() => {
                  setAuthMode("bootstrap");
                  setAuthErr("");
                }}
              >
                First-Run Owner Setup
              </button>
            </div>

            {dbUnavailable && backendDetail && (
              <div id="auth-diagnostic-banner" className="alert-box alert-warn auth-diagnostic" role="alert">
                <div className="row-between" style={{ marginBottom: 6 }}>
                  <strong className="mono" style={{ fontSize: 11.5 }}>
                    {backendMeta?.errorCode || "DATABASE_DEGRADED"}
                  </strong>
                  <button
                    id="auth-recheck-btn"
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={probingHealth}
                    onClick={probeBackendReadiness}
                  >
                    {probingHealth ? "Checking..." : "Re-check Status"}
                  </button>
                </div>
                <div className="auth-diagnostic-text">{backendDetail}</div>
                {backendMeta?.backend && (
                  <div className="muted mono" style={{ fontSize: 11, marginTop: 6 }}>
                    {backendMeta.backend.toUpperCase()}
                    {backendMeta.usesPooler ? " · POOLER" : ""}
                    {backendMeta.port ? ` · PORT ${backendMeta.port}` : ""}
                    {backendMeta.sslEnforced ? " · SSL" : ""}
                  </div>
                )}
              </div>
            )}

            {showDistinctAuthErr && (
              <div id="auth-error-banner" className="alert-box alert-error" role="alert">
                {authErr}
              </div>
            )}

            <input
              id="auth-username"
              className="input"
              required
              disabled={dbUnavailable}
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
                disabled={dbUnavailable}
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
              disabled={dbUnavailable}
              type="password"
              autoComplete={authMode === "bootstrap" ? "new-password" : "current-password"}
              placeholder="Password (min 12 chars for bootstrap)"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <button
              id="auth-submit"
              className="btn"
              type="submit"
              disabled={authSubmitting || probingHealth || dbUnavailable}
            >
              {dbUnavailable
                ? authMode === "bootstrap"
                  ? "Owner Setup Unavailable (Database Degraded)"
                  : "Sign In Unavailable (Database Degraded)"
                : authSubmitting
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
    onSelectSubPage: (sub: string) => navigate(activeModule, sub),
    onNavigate: navigate,
    user,
    device,
    pendingPrompt: pendingNeonPrompt,
    onClearPendingPrompt: () => setPendingNeonPrompt(""),
    onSendToNeon: (p: string) => setPendingNeonPrompt(p),
    pendingFiles: pendingNeonFiles,
    onAttachFileToNeon: (f: { file_id: string; filename: string; mime_type: string; is_image?: boolean; size_bytes?: number }) =>
      setPendingNeonFiles((prev) => (prev.some((x) => x.file_id === f.file_id) ? prev : [...prev, f])),
    onClearPendingFiles: () => setPendingNeonFiles([]),
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
      case "caravan": return <CaravanModulePage {...sharedProps} />;
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
