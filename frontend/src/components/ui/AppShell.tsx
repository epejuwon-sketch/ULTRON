import React from "react";
import {
  Activity,
  Bell,
  Bot,
  Command,
  Compass,
  FolderOpen,
  Globe,
  Hammer,
  HardDrive,
  LogOut,
  Menu,
  MessageSquare,
  MoreHorizontal,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  PanelRight,
  Plug,
  Settings,
  Shield,
  Terminal,
  Wallet,
  Workflow,
  X,
} from "lucide-react";
import { AuthUser } from "../../lib/api";
import { DeviceProfile } from "../../lib/device";
import { MODULES, ModuleId } from "../../catalog/navigation";
import { UltronLogo } from "../UltronLogo";
import { StatusIndicator } from "./DesignSystem";

export function ModuleIcon({ id, size = 16 }: { id: ModuleId; size?: number }) {
  switch (id) {
    case "command": return <Compass size={size} />;
    case "neon": return <MessageSquare size={size} />;
    case "argon": return <Workflow size={size} />;
    case "agents": return <Bot size={size} />;
    case "connections": return <Plug size={size} />;
    case "files": return <FolderOpen size={size} />;
    case "projects": return <Hammer size={size} />;
    case "research": return <Globe size={size} />;
    case "creative": return <Palette size={size} />;
    case "pulse": return <Activity size={size} />;
    case "security": return <Shield size={size} />;
    case "devices": return <HardDrive size={size} />;
    case "finance": return <Wallet size={size} />;
    case "caravan": return <Compass size={size} />;
    case "settings": return <Settings size={size} />;
    case "terminal": return <Terminal size={size} />;
  }
}

export function DesktopSidebar({
  user,
  activeModule,
  collapsed,
  drawerOpen,
  onSelectModule,
  onToggleCollapse,
  onCloseDrawer,
  onLogout,
}: {
  user: AuthUser;
  activeModule: ModuleId;
  collapsed: boolean;
  drawerOpen: boolean;
  onSelectModule: (m: ModuleId) => void;
  onToggleCollapse: () => void;
  onCloseDrawer: () => void;
  onLogout: () => void;
}) {
  const groups = [
    "Core Command",
    "Intelligence & Execution",
    "Workspace & Media",
    "Operations & System",
  ] as const;

  return (
    <>
      {drawerOpen && <div className="drawer-backdrop" onClick={onCloseDrawer} />}
      <aside
        className={`sidebar ${collapsed ? "collapsed" : ""} ${drawerOpen ? "open" : ""}`}
        aria-label="ULTRON OS Primary Navigation"
      >
        <div className="brand row-between">
          <UltronLogo
            variant={collapsed && !drawerOpen ? "mark" : "full"}
            size={30}
            subtitle={`${user.username} · ${user.role}`}
          />
          {drawerOpen ? (
            <button type="button" className="btn btn-secondary btn-sm" onClick={onCloseDrawer} aria-label="Close navigation">
              <X size={14} />
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-secondary btn-sm desktop-only-btn"
              onClick={onToggleCollapse}
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            >
              {collapsed ? <PanelLeftOpen size={14} /> : <PanelLeftClose size={14} />}
            </button>
          )}
        </div>

        <div className="sidebar-scroll">
          {groups.map((grp) => (
            <div key={grp}>
              {(!collapsed || drawerOpen) && <div className="nav-section">{grp}</div>}
              {MODULES.filter((m) => m.group === grp).map((m) => (
                <button
                  key={m.id}
                  id={`nav-${m.id}`}
                  type="button"
                  title={m.label}
                  className={`nav-btn ${activeModule === m.id ? "active" : ""}`}
                  onClick={() => {
                    onSelectModule(m.id);
                    onCloseDrawer();
                  }}
                >
                  <ModuleIcon id={m.id} size={16} />
                  {(!collapsed || drawerOpen) && <span>{m.label}</span>}
                </button>
              ))}
            </div>
          ))}
        </div>

        <div className="sidebar-footer">
          <button id="nav-logout" type="button" className="nav-btn" onClick={onLogout} title="Sign Out">
            <LogOut size={15} />
            {(!collapsed || drawerOpen) && <span>Sign Out</span>}
          </button>
        </div>
      </aside>
    </>
  );
}

export function TopBar({
  title,
  device,
  backendReady,
  onOpenDrawer,
  onOpenPalette,
  onOpenNotifications,
  onToggleRightPanel,
  onOpenTerminal,
}: {
  title: string;
  device: DeviceProfile;
  backendReady: boolean | null;
  onOpenDrawer: () => void;
  onOpenPalette: () => void;
  onOpenNotifications: () => void;
  onToggleRightPanel: () => void;
  onOpenTerminal?: () => void;
}) {
  return (
    <header className="topbar">
      <div className="row">
        {!device.isDesktop && (
          <button
            id="mobile-drawer-open"
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onOpenDrawer}
            aria-label="Open navigation menu"
          >
            <Menu size={16} />
          </button>
        )}
        {device.isMobile && <UltronLogo variant="mark" size={24} />}
        <span className="topbar-title">{title}</span>
      </div>

      <div className="row">
        <button
          id="topbar-command-palette"
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={onOpenPalette}
          aria-label="Open Command Palette"
        >
          <Command size={13} />
          {!device.isMobile && <span className="mono" style={{ fontSize: 11 }}>⌘K</span>}
        </button>

        <StatusIndicator
          label={backendReady === false ? "DEGRADED" : backendReady === true ? "ONLINE" : "SYNCING"}
          tone={backendReady === false ? "warn" : backendReady === true ? "success" : "neutral"}
        />

        {onOpenTerminal && (
          <button
            id="topbar-terminal"
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onOpenTerminal}
            aria-label="Open Master Terminal (Page 112)"
            title="Open Master Terminal (Page 112)"
          >
            <Terminal size={13} />
            {!device.isMobile && <span className="mono" style={{ fontSize: 11, color: "#38bdf8" }}>112</span>}
          </button>
        )}

        <button
          id="topbar-notifications"
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={onOpenNotifications}
          aria-label="Notifications"
        >
          <Bell size={14} />
        </button>

        {device.isDesktop && (
          <button
            id="topbar-right-panel"
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={onToggleRightPanel}
            aria-label="Toggle contextual telemetry panel"
          >
            <PanelRight size={14} />
          </button>
        )}
      </div>
    </header>
  );
}

/**
 * Dedicated iPhone XR / Mobile 5-Destination Bottom Navigation:
 * 1. Home  2. NEON  3. Agents  4. Projects  5. More (opens complete secondary navigation)
 */
export function MobileNavigation({
  activeModule,
  onSelectModule,
  onOpenMore,
}: {
  activeModule: ModuleId;
  onSelectModule: (m: ModuleId) => void;
  onOpenMore: () => void;
}) {
  const isSecondary = !["command", "neon", "agents", "projects"].includes(activeModule);
  return (
    <nav className="mobile-nav" aria-label="Mobile primary navigation">
      <button
        id="mobile-tab-home"
        type="button"
        className={`mobile-tab ${activeModule === "command" ? "active" : ""}`}
        onClick={() => onSelectModule("command")}
      >
        <Compass size={19} />
        <span>Home</span>
      </button>
      <button
        id="mobile-tab-neon"
        type="button"
        className={`mobile-tab ${activeModule === "neon" ? "active" : ""}`}
        onClick={() => onSelectModule("neon")}
      >
        <MessageSquare size={19} />
        <span>NEON</span>
      </button>
      <button
        id="mobile-tab-agents"
        type="button"
        className={`mobile-tab ${activeModule === "agents" ? "active" : ""}`}
        onClick={() => onSelectModule("agents")}
      >
        <Bot size={19} />
        <span>Agents</span>
      </button>
      <button
        id="mobile-tab-projects"
        type="button"
        className={`mobile-tab ${activeModule === "projects" ? "active" : ""}`}
        onClick={() => onSelectModule("projects")}
      >
        <Hammer size={19} />
        <span>Projects</span>
      </button>
      <button
        id="mobile-tab-more"
        type="button"
        className={`mobile-tab ${isSecondary ? "active" : ""}`}
        onClick={onOpenMore}
      >
        <MoreHorizontal size={19} />
        <span>More</span>
      </button>
    </nav>
  );
}

export function AppShell({
  device,
  sidebar,
  topbar,
  mobileNav,
  rightPanel,
  children,
}: {
  device: DeviceProfile;
  sidebar: React.ReactNode;
  topbar: React.ReactNode;
  mobileNav: React.ReactNode;
  rightPanel?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className={`app-shell device-${device.deviceClass}`}>
      {sidebar}
      <div className="main-area">
        {topbar}
        <div className="workspace-split">
          <main className="content">{children}</main>
          {device.isDesktop && rightPanel && (
            <aside className="context-panel" aria-label="Contextual System Panel">
              {rightPanel}
            </aside>
          )}
        </div>
      </div>
      {!device.isDesktop && mobileNav}
    </div>
  );
}
