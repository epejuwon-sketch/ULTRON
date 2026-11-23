import React, { useEffect, useState } from "react";
import { Keyboard, Moon, RefreshCw, RotateCcw, ShieldAlert, Sun } from "lucide-react";
import { apiFetch } from "../lib/api";
import { AccentPreset, DensityMode, LayoutMode, usePreferences } from "../lib/preferences";
import { getModule, getSubPage } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import { MemoryView, NotificationsView, SettingsView } from "../components/SystemViews";
import { UltronLogo } from "../components/UltronLogo";
import {
  ConfirmationDialog,
  ErrorState,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";
import { ReadableSummary, TechnicalDiagnostics } from "../components/ui/HumanPresentation";

export default function SettingsModulePage({ subPage, onSelectSubPage, user, device }: ModulePageProps) {
  const mod = getModule("settings");
  const page = getSubPage("settings", subPage);
  const { prefs, updatePrefs, resetPrefs } = usePreferences();
  const { pushToast } = useToast();

  const [backendSettings, setBackendSettings] = useState<Record<string, any>>({});
  const [health, setHealth] = useState<any>(null);
  const [ready, setReady] = useState<any>(null);
  const [metricsText, setMetricsText] = useState("");
  const [storageStatus, setStorageStatus] = useState<any>(null);
  const [researchDiag, setResearchDiag] = useState<any>(null);
  const [probingResearch, setProbingResearch] = useState(false);
  const [settingKey, setSettingKey] = useState("workspace_timezone");
  const [settingVal, setSettingVal] = useState("UTC");
  const [error, setError] = useState("");
  const [confirmFlush, setConfirmFlush] = useState(false);

  async function runLiveResearchProbe() {
    setProbingResearch(true);
    try {
      const res = await apiFetch<any>("/api/v1/research/diagnostics?live=true&query=Lamborghini%20Aventador%20SVJ%20price");
      setResearchDiag(res);
      pushToast(`Live research probe completed (${res.available_providers_count || 0} provider(s) available).`, "success");
    } catch (e: any) {
      pushToast(e.message, "error");
    } finally {
      setProbingResearch(false);
    }
  }

  async function load() {
    setError("");
    try {
      const [st, h, r, stor] = await Promise.all([
        apiFetch<any>("/api/v1/settings").catch(() => ({ settings: {} })),
        apiFetch<any>("/health").catch(() => null),
        apiFetch<any>("/health/ready").catch(() => null),
        apiFetch<any>("/api/v1/files/storage/status").catch(() => null),
      ]);
      setBackendSettings(st.settings || {});
      setHealth(h);
      setReady(r);
      setStorageStatus(stor);
      if (subPage === "diagnostics") {
        apiFetch<string>("/api/v1/monitoring/metrics")
          .then((txt) => setMetricsText(typeof txt === "string" ? txt.slice(0, 3500) : JSON.stringify(txt)))
          .catch(() => {});
        apiFetch<any>("/api/v1/research/diagnostics?live=false")
          .then((d) => setResearchDiag(d))
          .catch(() => {});
      }
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, [subPage]);

  async function saveBackendSetting(e: React.FormEvent) {
    e.preventDefault();
    if (!settingKey.trim()) return;
    try {
      await apiFetch("/api/v1/settings", {
        method: "PUT",
        body: { key: settingKey.trim(), value: settingVal },
      });
      pushToast(`Saved setting '${settingKey}'.`, "success");
      load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`SETTINGS // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <button type="button" className="btn btn-secondary btn-sm" onClick={load}>
            <RefreshCw size={13} /> Refresh
          </button>
        }
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {/* 97. GENERAL SETTINGS */}
      {page.id === "general" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title"><span>Persist Tenant Setting (/api/v1/settings)</span></div>
            <form onSubmit={saveBackendSetting} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <input className="input" value={settingKey} onChange={(e) => setSettingKey(e.target.value)} placeholder="Setting key" />
              <input className="input" value={settingVal} onChange={(e) => setSettingVal(e.target.value)} placeholder="Value" />
              <button type="submit" className="btn">Save Setting</button>
            </form>
          </div>
          <div className="card">
            <div className="card-title"><span>Persisted Backend Settings</span></div>
            <ReadableSummary
              data={Object.keys(backendSettings || {}).length ? backendSettings : { status: "Using default tenant settings" }}
              diagnosticsTitle="Technical Diagnostics — Raw Settings Map"
            />
          </div>
        </div>
      )}

      {/* 98. APPEARANCE */}
      {page.id === "appearance" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 18, maxWidth: 760 }}>
          <div className="card-title">
            <span>Appearance & Responsive Layout</span>
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => { resetPrefs(); pushToast("UI preferences reset to obsidian defaults.", "info"); }}>
              <RotateCcw size={13} /> Reset Defaults
            </button>
          </div>

          <div className="list-item">
            <div className="row-between">
              <div>
                <strong>Color Mode</strong>
                <div className="muted">Switch between deep obsidian Dark Mode and clean institutional Light Mode.</div>
              </div>
              <div className="row">
                <button
                  id="pref-theme-dark"
                  type="button"
                  className={`btn btn-sm ${prefs.theme === "dark" ? "" : "btn-secondary"}`}
                  onClick={() => updatePrefs({ theme: "dark" })}
                >
                  <Moon size={13} /> Dark
                </button>
                <button
                  id="pref-theme-light"
                  type="button"
                  className={`btn btn-sm ${prefs.theme === "light" ? "" : "btn-secondary"}`}
                  onClick={() => updatePrefs({ theme: "light" })}
                >
                  <Sun size={13} /> Light
                </button>
              </div>
            </div>
          </div>

          <div className="list-item">
            <div className="row-between">
              <div>
                <strong>Layout Adaptation Mode</strong>
                <div className="muted">Auto detected: {device.deviceClass.toUpperCase()} ({device.width}×{device.height})</div>
              </div>
              <div className="row">
                {(["auto", "desktop", "mobile"] as LayoutMode[]).map((mode) => (
                  <button
                    key={mode}
                    id={`pref-layout-${mode}`}
                    type="button"
                    className={`btn btn-sm ${prefs.layoutMode === mode ? "" : "btn-secondary"}`}
                    onClick={() => updatePrefs({ layoutMode: mode })}
                  >
                    {mode.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="list-item">
            <div className="row-between">
              <div>
                <strong>Interface Density</strong>
                <div className="muted">Choose comfortable breathing room or compact operational telemetry density.</div>
              </div>
              <div className="row">
                {(["comfortable", "compact"] as DensityMode[]).map((d) => (
                  <button
                    key={d}
                    id={`pref-density-${d}`}
                    type="button"
                    className={`btn btn-sm ${prefs.density === d ? "" : "btn-secondary"}`}
                    onClick={() => updatePrefs({ density: d })}
                  >
                    {d.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="list-item">
            <div className="row-between">
              <div>
                <strong>Animations & Orbital Motion</strong>
                <div className="muted">Toggle smooth interface transitions and reduced-motion preference.</div>
              </div>
              <button
                type="button"
                className={`btn btn-sm ${prefs.animationsEnabled ? "" : "btn-secondary"}`}
                onClick={() => updatePrefs({ animationsEnabled: !prefs.animationsEnabled })}
              >
                {prefs.animationsEnabled ? "Enabled" : "Disabled"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 99. THEME CONFIGURATION */}
      {page.id === "theme" && (
        <div className="card" style={{ maxWidth: 680 }}>
          <div className="card-title"><span>Restrained Accent Palette</span></div>
          <div className="grid-2">
            {(
              [
                { id: "electric", label: "Electric Blue (Default)", hex: "#38bdf8" },
                { id: "cyan", label: "Orbital Cyan", hex: "#22d3ee" },
                { id: "silver", label: "Platinum Silver", hex: "#cbd5e1" },
                { id: "emerald", label: "Telemetry Emerald", hex: "#34d399" },
              ] as { id: AccentPreset; label: string; hex: string }[]
            ).map((a) => (
              <button
                key={a.id}
                type="button"
                className={`list-item list-item-btn ${prefs.accent === a.id ? "list-item-active" : ""}`}
                onClick={() => updatePrefs({ accent: a.id })}
              >
                <div className="row-between" style={{ width: "100%" }}>
                  <strong>{a.label}</strong>
                  <span style={{ width: 14, height: 14, borderRadius: 99, background: a.hex, display: "inline-block" }} />
                </div>
                <span className="muted mono">{a.hex}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* 100. ACCOUNT SETTINGS & 101. PROFILE */}
      {(page.id === "account" || page.id === "profile") && (
        <div className="card" style={{ maxWidth: 680 }}>
          <div className="card-title"><span>Operator Identity & Tenant Binding</span></div>
          <div className="grid-2">
            <MetricDisplay label="Username" value={user.username} />
            <MetricDisplay label="Role" value={user.role} tone="info" />
            <MetricDisplay label="Email" value={user.email} />
            <MetricDisplay label="Tenant ID" value={user.tenant_id} />
          </div>
        </div>
      )}

      {/* 102. SECURITY SETTINGS */}
      {page.id === "security-settings" && <SettingsView />}

      {/* 103. PRIVACY */}
      {page.id === "privacy" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10, maxWidth: 720 }}>
          <div className="card-title"><span><ShieldAlert size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Privacy & VAULT Data Protection</span></div>
          <div className="list-item"><strong>Automatic Secret Redaction</strong><div className="muted">API keys, passwords, and tokens entered in NEON chat are intercepted and stored in AES-256-GCM VAULT before external calls.</div></div>
          <div className="list-item"><strong>PCI Payment Guard</strong><div className="muted">Raw card PANs and CVVs are blocked across chat, memory, and Finance endpoints.</div></div>
          <div className="list-item"><strong>Zero Raw Biometrics</strong><div className="muted">SENTINEL WebAuthn passkeys keep Face ID / Touch ID credentials strictly on-device.</div></div>
        </div>
      )}

      {/* 104. MEMORY PREFERENCES */}
      {page.id === "memory-prefs" && <MemoryView />}

      {/* 105. NOTIFICATIONS */}
      {page.id === "notifications" && <NotificationsView />}

      {/* 106. LANGUAGE & REGION */}
      {page.id === "locale" && (
        <div className="card" style={{ maxWidth: 600, display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span>Language & Region</span></div>
          <select className="select" value={prefs.language} onChange={(e) => updatePrefs({ language: e.target.value })}>
            <option value="en-US">English (United States)</option>
            <option value="en-GB">English (United Kingdom)</option>
          </select>
          <select className="select" value={prefs.region} onChange={(e) => updatePrefs({ region: e.target.value })}>
            <option value="Global (UTC)">Global (UTC)</option>
            <option value="Africa/Lagos (WAT)">Africa/Lagos (WAT)</option>
            <option value="Europe/London (GMT/BST)">Europe/London (GMT/BST)</option>
            <option value="America/New_York (EST/EDT)">America/New_York (EST/EDT)</option>
          </select>
        </div>
      )}

      {/* 107. KEYBOARD SHORTCUTS */}
      {page.id === "shortcuts" && (
        <div className="card" style={{ maxWidth: 680 }}>
          <div className="card-title"><span><Keyboard size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Desktop Command Shortcuts</span></div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {[
              { keys: "⌘K / Ctrl+K", desc: "Open global Command Palette (search all 111+ pages)" },
              { keys: "Escape", desc: "Close open modal, drawer, or command palette" },
              { keys: "Alt+1", desc: "Jump to Command Centre (Home)" },
              { keys: "Alt+2", desc: "Jump to NEON Intelligence" },
              { keys: "Alt+3", desc: "Jump to ARGON Orchestration" },
              { keys: "Alt+4", desc: "Jump to The 60 Agents" },
              { keys: "Alt+5", desc: "Jump to Connections Centre" },
              { keys: "Alt+6", desc: "Jump to Settings" },
            ].map((s) => (
              <div key={s.keys} className="list-item row-between">
                <span>{s.desc}</span>
                <span className="pill mono">{s.keys}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 108. ACCESSIBILITY */}
      {page.id === "accessibility" && (
        <div className="card" style={{ maxWidth: 680, display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span>Accessibility Controls</span></div>
          <label className="list-item row-between" style={{ cursor: "pointer" }}>
            <span>Reduced Motion (disables non-essential animations)</span>
            <input type="checkbox" checked={prefs.reducedMotion} onChange={(e) => updatePrefs({ reducedMotion: e.target.checked })} />
          </label>
          <label className="list-item row-between" style={{ cursor: "pointer" }}>
            <span>High-Contrast Focus Rings (WCAG AAA keyboard visibility)</span>
            <input type="checkbox" checked={prefs.highContrastFocus} onChange={(e) => updatePrefs({ highContrastFocus: e.target.checked })} />
          </label>
        </div>
      )}

      {/* 109. DATA MANAGEMENT */}
      {page.id === "data" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title">
            <span>Storage & TURBO Cache Management</span>
            <button type="button" className="btn btn-danger btn-sm" onClick={() => setConfirmFlush(true)}>
              Flush TURBO Cache
            </button>
          </div>
          <ReadableSummary
            data={storageStatus || { status: "Active" }}
            diagnosticsTitle="Technical Diagnostics — Storage & Cache Status"
          />
        </div>
      )}

      {/* 110. ABOUT ULTRON */}
      {page.id === "about" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 14, maxWidth: 680 }}>
          <UltronLogo variant="full" size={44} subtitle="Personal Operating System · 2026 Edition" />
          <div className="grid-2">
            <MetricDisplay label="Frontend Release" value="ULTRON OS 2026 UI" sub="14 Modules · 111+ Pages" tone="info" />
            <MetricDisplay label="Locked Backend" value="ultron-backend-v1" sub="189 Verified OpenAPI Endpoints" tone="success" />
            <MetricDisplay label="Agent Registry" value="60 Specialists" sub="25 Core + 35 Extensible" />
            <MetricDisplay label="Detected Device" value={device.deviceClass.toUpperCase()} sub={`${device.width}×${device.height}`} />
          </div>
        </div>
      )}

      {/* 111. SYSTEM DIAGNOSTICS */}
      {page.id === "diagnostics" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="grid-2">
            <div className="card">
              <div className="card-title">
                <span>Readiness Status</span>
                <StatusIndicator label={ready?.status === "ready" || ready?.database?.connected ? "READY" : "DEGRADED"} tone={ready?.status === "ready" || ready?.database?.connected ? "success" : "warn"} />
              </div>
              <ReadableSummary data={ready || { status: "Loading..." }} diagnosticsTitle="Technical Diagnostics — /health/ready" />
            </div>
            <div className="card">
              <div className="card-title"><span>System &amp; Provider Health</span></div>
              <ReadableSummary data={health || { status: "Loading..." }} diagnosticsTitle="Technical Diagnostics — /health" />
            </div>
          </div>
          <div className="card">
            <div className="card-title">
              <span>Live Web Research Provider Connectivity</span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={probingResearch}
                onClick={runLiveResearchProbe}
              >
                <RefreshCw size={13} /> {probingResearch ? "Probing Live Providers..." : "Run Live Research Probe"}
              </button>
            </div>
            {researchDiag ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Provider</th>
                        <th>Configured</th>
                        <th>Live Connectivity</th>
                        <th>HTTP Status</th>
                        <th>Error Category</th>
                        <th>Results Returned</th>
                        <th>Pages Extracted</th>
                        <th>Duration</th>
                        <th>Mode</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(researchDiag.providers || []).map((p: any) => (
                        <tr key={p.provider_name}>
                          <td className="mono">{p.provider_name}</td>
                          <td>{p.configured ? "YES" : "NO"}</td>
                          <td className="mono">{p.live_connectivity_status}</td>
                          <td className="mono">{p.last_http_status ?? "—"}</td>
                          <td className="mono">{p.last_error_category ?? "—"}</td>
                          <td>{p.search_results_returned ?? 0}</td>
                          <td>{p.pages_extracted ?? 0}</td>
                          <td className="mono">{p.retrieval_duration_ms ? `${p.retrieval_duration_ms}ms` : "—"}</td>
                          <td>{p.cache_or_live_status || "live"}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <TechnicalDiagnostics title="Technical Diagnostics — /api/v1/research/diagnostics" data={researchDiag} />
              </div>
            ) : (
              <div className="muted">Loading research connectivity diagnostics...</div>
            )}
          </div>
          {metricsText && (
            <div className="card">
              <div className="card-title"><span>Runtime Metrics Snapshot</span></div>
              <TechnicalDiagnostics title="Technical Diagnostics — Prometheus Metrics Text" data={metricsText} />
            </div>
          )}
        </div>
      )}

      <ConfirmationDialog
        open={confirmFlush}
        title="Flush TURBO Runtime Cache"
        message="Clear in-memory TURBO cache entries? Subsequent requests will rebuild cleanly from PostgreSQL."
        confirmLabel="Flush Cache"
        onCancel={() => setConfirmFlush(false)}
        onConfirm={async () => {
          setConfirmFlush(false);
          await apiFetch("/api/v1/turbo/cache/flush", { method: "POST" });
          pushToast("TURBO cache flushed.", "success");
        }}
      />
    </ResponsiveWorkspace>
  );
}
