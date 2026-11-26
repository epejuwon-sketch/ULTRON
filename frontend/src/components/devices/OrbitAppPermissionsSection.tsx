import React, { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Compass, ExternalLink, Play, Plus, Search, ShieldCheck, Smartphone, Trash2, XCircle } from "lucide-react";
import { apiFetch } from "../../lib/api";
import { DataTable, StatusIndicator, useToast } from "../ui/DesignSystem";

export function getClientDeviceContext(): { deviceId: string; deviceLabel: string; platform: string } {
  let devId = localStorage.getItem("ultron_orbit_device_id");
  if (!devId) {
    devId = `client_${Math.random().toString(36).slice(2, 10)}`;
    localStorage.setItem("ultron_orbit_device_id", devId);
  }
  const ua = navigator.userAgent || "";
  if (/iPhone|iPad|iPod/i.test(ua)) {
    return { deviceId: devId, deviceLabel: "iPhone / iPad PWA", platform: "ios" };
  }
  if (/Android/i.test(ua)) {
    return { deviceId: devId, deviceLabel: "Android Browser / PWA", platform: "android" };
  }
  if (/Windows/i.test(ua)) {
    return { deviceId: devId, deviceLabel: "Windows Desktop", platform: "windows" };
  }
  if (/Macintosh|Mac OS/i.test(ua)) {
    return { deviceId: devId, deviceLabel: "macOS Desktop", platform: "macos" };
  }
  return { deviceId: devId, deviceLabel: "Web Browser", platform: "web" };
}

export interface ParsedAppLaunchIntent {
  appId: string;
  appName: string;
  targetUri?: string;
  preferredMethod?: string;
}

export function parseUniversalAppLaunchCommand(text: string): ParsedAppLaunchIntent | null {
  const clean = text.trim();
  if (!clean) return null;

  // Match natural phrases: "open YouTube", "launch my banking application", "start Spotify playlist ...", etc.
  const m = clean.match(/^(?:please\s+)?(?:can\s+you\s+)?(?:open|launch|start)\s+(?:up\s+)?(.+?)(?:\s+app(?:lication)?)?[.!?]*$/i);
  if (!m) return null;

  let body = m[1].trim();
  let preferredMethod: string | undefined;
  if (/\b(in|via|using)\s+(?:the\s+)?browser\b/i.test(body)) {
    preferredMethod = "web_fallback";
    body = body.replace(/\b(in|via|using)\s+(?:the\s+)?browser\b/i, "").trim();
  }

  // Extract optional destination/content after "and search", "to", "for", or Spotify/URL tokens
  let appPart = body;
  let targetUri: string | undefined;

  const urlMatch = body.match(/(https?:\/\/\S+|spotify:\S+)/i);
  if (urlMatch) {
    targetUri = urlMatch[1];
    appPart = body.replace(urlMatch[1], "").replace(/\b(on|in|with|to)\b/gi, " ").trim() || (urlMatch[1].includes("spotify") ? "spotify" : "browser");
  } else if (/\bspotify\b/i.test(body)) {
    appPart = "spotify";
    const rest = body.replace(/\bspotify\b/i, "").trim();
    if (rest) targetUri = clean;
  } else {
    const destMatch = body.match(/^(.+?)\s+(?:and\s+search(?:\s+for)?|search(?:\s+for)?|for|to)\s+(.+)$/i);
    if (destMatch) {
      appPart = destMatch[1].trim();
      targetUri = destMatch[2].trim();
    }
  }

  appPart = appPart.replace(/^(my|the)\s+/i, "").replace(/\s+application$/i, "").trim();
  if (!appPart || appPart.length > 80) return null;

  return {
    appId: appPart.toLowerCase(),
    appName: appPart,
    targetUri,
    preferredMethod,
  };
}

// Backward-compatible export
export function parseAppLaunchCommand(text: string): { appId: string; targetUri?: string } | null {
  const parsed = parseUniversalAppLaunchCommand(text);
  if (!parsed) return null;
  return { appId: parsed.appId, targetUri: parsed.targetUri };
}

export function monitorOrbitHandoff(
  appId: string,
  deviceId: string,
  isFallback: boolean,
  onUpdate: (patch: { handoff_tapped: boolean; handoff_note: string }) => void
): void {
  const report = (outcome: string, detail = "") => {
    apiFetch("/api/v1/devices/apps/handoff-report", {
      method: "POST",
      body: { app_id: appId, device_id: deviceId, outcome, detail },
    }).catch(() => {
      // best-effort telemetry
    });
  };

  if (isFallback) {
    onUpdate({
      handoff_tapped: true,
      handoff_note: "Opened Web Fallback in browser.",
    });
    report("WEB_FALLBACK_OPENED");
    return;
  }

  onUpdate({
    handoff_tapped: true,
    handoff_note: "Handoff attempted — waiting to see if the OS switches out of Safari/PWA...",
  });
  report("HANDOFF_TAPPED");

  let settled = false;
  const onVis = () => {
    if (document.hidden && !settled) {
      settled = true;
      document.removeEventListener("visibilitychange", onVis);
      onUpdate({
        handoff_tapped: true,
        handoff_note: "Browser switched away after tap — OS may have opened the app (PWA cannot independently confirm).",
      });
      report("HANDOFF_PAGE_HIDDEN");
    }
  };
  document.addEventListener("visibilitychange", onVis);

  window.setTimeout(() => {
    document.removeEventListener("visibilitychange", onVis);
    if (!settled && !document.hidden) {
      settled = true;
      onUpdate({
        handoff_tapped: true,
        handoff_note:
          "No app switch detected — the app may not be installed, or iOS blocked/declined the handoff. Use Web Fallback below if available.",
      });
      report("HANDOFF_NO_APP_SWITCH_TIMEOUT", "No visibilitychange within 1600ms");
    }
  }, 1600);
}

export function OrbitAppPermissionsSection() {
  const { pushToast } = useToast();
  const ctx = getClientDeviceContext();
  const [apps, setApps] = useState<any[]>([]);
  const [permissions, setPermissions] = useState<any[]>([]);
  const [devicePerm, setDevicePerm] = useState<any>(null);
  const [discovery, setDiscovery] = useState<any>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [quickLaunchInput, setQuickLaunchInput] = useState("");
  const [pendingApproval, setPendingApproval] = useState<any>(null);
  const [launchResult, setLaunchResult] = useState<any>(null);
  const [launchError, setLaunchError] = useState<string | null>(null);
  const [showRegisterForm, setShowRegisterForm] = useState(false);

  // Manual registration state
  const [regName, setRegName] = useState("");
  const [regAliases, setRegAliases] = useState("");
  const [regCategory, setRegCategory] = useState("Custom");
  const [regScheme, setRegScheme] = useState("");
  const [regUniversal, setRegUniversal] = useState("");
  const [regAndroidPkg, setRegAndroidPkg] = useState("");
  const [regDesktopKey, setRegDesktopKey] = useState("");
  const [regWebFallback, setRegWebFallback] = useState("");

  async function load() {
    try {
      const [libRes, pRes, discRes] = await Promise.all([
        apiFetch<any>(`/api/v1/devices/apps/library?device_id=${encodeURIComponent(ctx.deviceId)}`).catch(() => ({ apps: [], device_permission: null })),
        apiFetch<any>(`/api/v1/devices/apps/permissions?device_id=${encodeURIComponent(ctx.deviceId)}`).catch(() => ({ permissions: [] })),
        apiFetch<any>(`/api/v1/devices/apps/discovery?platform=${encodeURIComponent(ctx.platform)}&device_id=${encodeURIComponent(ctx.deviceId)}`).catch(() => null),
      ]);
      setApps(libRes.apps || []);
      setDevicePerm(libRes.device_permission || null);
      setPermissions(pRes.permissions || []);
      setDiscovery(discRes);
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    load();
  }, []);

  const filteredApps = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return apps;
    return apps.filter((a) => {
      const hay = [a.name, a.app_id, a.category, ...(a.aliases || [])].join(" ").toLowerCase();
      return hay.includes(q);
    });
  }, [apps, searchQuery]);

  async function requestLaunch(appIdOrName: string, allowOnce = false, targetUri?: string, preferredMethod?: string) {
    setLaunchResult(null);
    setLaunchError(null);
    try {
      const res = await apiFetch<any>("/api/v1/devices/apps/launch", {
        method: "POST",
        body: {
          app_id: appIdOrName,
          device_id: ctx.deviceId,
          device_label: ctx.deviceLabel,
          platform: ctx.platform,
          target_uri: targetUri,
          allow_once: allowOnce,
          preferred_method: preferredMethod,
        },
      });
      if (res.status === "APPROVAL_REQUIRED") {
        setPendingApproval({ ...res, target_uri: targetUri, preferred_method: preferredMethod });
      } else if (res.status === "DENIED") {
        setPendingApproval(null);
        setLaunchError(res.message || "Launch denied by device policy.");
        pushToast(res.message || "Launch denied by device policy.", "error");
      } else if (res.status === "READY_TO_LAUNCH") {
        setPendingApproval(null);
        setLaunchResult({ ...res, handoff_tapped: false, handoff_note: null });
        pushToast(`${res.app_name} launch prepared (${res.permission_mode}).`, "success");
        await load();
      }
    } catch (err: any) {
      const msg =
        err?.message && !/failed to fetch|network/i.test(err.message)
          ? err.message
          : "Network failure while contacting ORBIT launch resolver. Check your connection and retry.";
      setLaunchError(msg);
      pushToast(msg, "error");
    }
  }

  async function decideDeviceWide(decision: "ALWAYS_ALLOW" | "REVOKED") {
    try {
      await apiFetch("/api/v1/devices/apps/device-permission", {
        method: "POST",
        body: {
          device_id: ctx.deviceId,
          device_label: ctx.deviceLabel,
          decision,
        },
      });
      pushToast(
        decision === "ALWAYS_ALLOW"
          ? "ORBIT_APPLICATION_LAUNCH remembered for this device."
          : "ORBIT_APPLICATION_LAUNCH revoked for this device.",
        "success"
      );
      await load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function decidePermission(decision: "ALLOW_ONCE" | "ALWAYS_ALLOW_APP" | "ALWAYS_ALLOW_DEVICE" | "DENIED") {
    if (!pendingApproval) return;
    if (decision === "ALLOW_ONCE") {
      await requestLaunch(pendingApproval.app_id, true, pendingApproval.target_uri, pendingApproval.preferred_method);
      return;
    }
    try {
      const appId = pendingApproval.app_id;
      const targetUri = pendingApproval.target_uri;
      const preferredMethod = pendingApproval.preferred_method;
      if (decision === "ALWAYS_ALLOW_DEVICE") {
        await apiFetch("/api/v1/devices/apps/device-permission", {
          method: "POST",
          body: {
            device_id: ctx.deviceId,
            device_label: ctx.deviceLabel,
            decision: "ALWAYS_ALLOW",
          },
        });
      } else {
        await apiFetch("/api/v1/devices/apps/permissions", {
          method: "POST",
          body: {
            app_id: appId,
            device_id: ctx.deviceId,
            device_label: ctx.deviceLabel,
            decision: decision === "ALWAYS_ALLOW_APP" ? "ALWAYS_ALLOW" : "DENIED",
          },
        });
      }
      setPendingApproval(null);
      await load();
      if (decision === "ALWAYS_ALLOW_APP" || decision === "ALWAYS_ALLOW_DEVICE") {
        await requestLaunch(appId, false, targetUri, preferredMethod);
      } else {
        pushToast(`Denied ${appId} launch on this device.`, "info");
      }
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function revokePermission(permissionId: string) {
    try {
      await apiFetch(`/api/v1/devices/apps/permissions/${permissionId}/revoke`, { method: "POST" });
      pushToast("Application launch permission revoked.", "success");
      await load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function handleRegisterCustomApp(e: React.FormEvent) {
    e.preventDefault();
    if (!regName.trim()) return;
    try {
      await apiFetch("/api/v1/devices/apps/register", {
        method: "POST",
        body: {
          name: regName.trim(),
          aliases: regAliases.split(",").map((s) => s.trim()).filter(Boolean),
          category: regCategory.trim() || "Custom",
          ios_scheme: regScheme.trim(),
          universal_link: regUniversal.trim(),
          android_package: regAndroidPkg.trim(),
          desktop_app_key: regDesktopKey.trim(),
          web_fallback: regWebFallback.trim(),
        },
      });
      pushToast(`Registered ${regName.trim()} in ORBIT App Library.`, "success");
      setRegName("");
      setRegAliases("");
      setRegScheme("");
      setRegUniversal("");
      setRegAndroidPkg("");
      setRegDesktopKey("");
      setRegWebFallback("");
      setShowRegisterForm(false);
      await load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function handleDeleteCustomApp(appId: string) {
    try {
      await apiFetch(`/api/v1/devices/apps/register/${encodeURIComponent(appId)}`, { method: "DELETE" });
      pushToast("Removed custom application from library.", "info");
      await load();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  const deviceWideActive = devicePerm?.status === "ALWAYS_ALLOW";

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }} data-testid="orbit-app-permissions">
      {/* Device-Wide Remembered Permission Banner */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
          <div>
            <strong><ShieldCheck size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />ORBIT_APPLICATION_LAUNCH (Device-Wide)</strong>
            <div className="muted" style={{ fontSize: 12 }}>
              Scoped to {ctx.deviceLabel} ({ctx.platform}). Separate from microphone, camera, contacts, files, and financial permissions. OS prompts still apply.
            </div>
          </div>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <StatusIndicator
              label={deviceWideActive ? "REMEMBERED (ALWAYS_ALLOW)" : devicePerm?.status || "NOT_SET"}
              tone={deviceWideActive ? "success" : "neutral"}
            />
            {deviceWideActive ? (
              <button id="orbit-revoke-device-wide-btn" type="button" className="btn btn-danger btn-sm" onClick={() => decideDeviceWide("REVOKED")}>
                Revoke Device Permission
              </button>
            ) : (
              <button id="orbit-allow-device-wide-btn" type="button" className="btn btn-sm" onClick={() => decideDeviceWide("ALWAYS_ALLOW")}>
                Approve for This Device
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Universal Launcher */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="card-title">
          <span><Smartphone size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />ORBIT 2.0 Universal Application Launcher</span>
          <span className="pill mono">{ctx.deviceLabel} ({ctx.platform})</span>
        </div>

        <form
          className="row"
          style={{ gap: 8, flexWrap: "wrap" }}
          onSubmit={(e) => {
            e.preventDefault();
            if (!quickLaunchInput.trim()) return;
            const parsed = parseUniversalAppLaunchCommand(quickLaunchInput) || {
              appId: quickLaunchInput.trim(),
              appName: quickLaunchInput.trim(),
            };
            requestLaunch(parsed.appId, false, parsed.targetUri, parsed.preferredMethod);
          }}
        >
          <input
            id="orbit-universal-launch-input"
            className="input"
            style={{ flex: 1, minWidth: 220 }}
            value={quickLaunchInput}
            onChange={(e) => setQuickLaunchInput(e.target.value)}
            placeholder="Try: Open YouTube, Open Instagram, Open my banking application, Open Spotify playlist..."
          />
          <button type="submit" className="btn btn-sm">
            <Play size={12} /> Resolve &amp; Launch
          </button>
        </form>

        {/* Approval Prompt */}
        {pendingApproval && (
          <div className="alert-box" data-testid="orbit-app-approval-prompt" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <strong>{pendingApproval.prompt}</strong>
            <div className="muted" style={{ fontSize: 12 }}>
              Device: {pendingApproval.device_label} · Scope: {pendingApproval.permission_scope}
            </div>
            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
              <button id="orbit-allow-once-btn" type="button" className="btn btn-secondary btn-sm" onClick={() => decidePermission("ALLOW_ONCE")}>
                Allow once
              </button>
              <button id="orbit-always-allow-app-btn" type="button" className="btn btn-secondary btn-sm" onClick={() => decidePermission("ALWAYS_ALLOW_APP")}>
                Always allow {pendingApproval.app_name}
              </button>
              <button id="orbit-always-allow-btn" type="button" className="btn btn-sm" onClick={() => decidePermission("ALWAYS_ALLOW_DEVICE")}>
                Remember ORBIT_APPLICATION_LAUNCH on this device
              </button>
              <button id="orbit-deny-app-btn" type="button" className="btn btn-danger btn-sm" onClick={() => decidePermission("DENIED")}>
                Deny
              </button>
            </div>
          </div>
        )}

        {launchError && (
          <div className="alert-box" data-testid="orbit-app-launch-error" style={{ fontSize: 12 }}>
            <strong>Launch Error:</strong> {launchError}
          </div>
        )}

        {/* Honest Launch Status & Handoff Card */}
        {launchResult && (
          <div className="list-item" data-testid="orbit-app-launch-result" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="row-between" style={{ flexWrap: "wrap", gap: 6 }}>
              <strong>{launchResult.app_name} ({launchResult.permission_mode})</strong>
              <StatusIndicator label={launchResult.launch_status} tone={launchResult.launch_url_resolved ? "info" : "warn"} />
            </div>
            <div className="row" style={{ flexWrap: "wrap", gap: 8, fontSize: 12 }}>
              <span className="pill"><CheckCircle2 size={11} /> Recognised: Yes</span>
              <span className="pill">{launchResult.launch_url_resolved ? <CheckCircle2 size={11} /> : <XCircle size={11} />} URL Resolved: {launchResult.launch_url_resolved ? "Yes" : "No"}</span>
              <span className="pill">Handoff Attempted: {launchResult.handoff_tapped || launchResult.handoff_attempted ? "Yes" : "Awaiting Tap"}</span>
              <span className="pill">OS Confirmed: {launchResult.os_confirmed ? "Confirmed" : "Unconfirmed (PWA/OS limit)"}</span>
            </div>
            {launchResult.handoff_note && (
              <div className="alert-box" style={{ fontSize: 12, padding: "8px 10px" }}>{launchResult.handoff_note}</div>
            )}
            <div className="muted" style={{ fontSize: 12 }}>{launchResult.platform_limitation_note}</div>
            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
              {launchResult.launch_url && (
                <a
                  href={launchResult.launch_url}
                  className="btn btn-sm"
                  onClick={() =>
                    monitorOrbitHandoff(launchResult.app_id, ctx.deviceId, false, (patch) =>
                      setLaunchResult((prev: any) => (prev ? { ...prev, ...patch } : prev))
                    )
                  }
                >
                  <ExternalLink size={12} /> Open {launchResult.app_name} App
                </a>
              )}
              {launchResult.web_fallback_url && launchResult.web_fallback_url !== launchResult.launch_url && (
                <a
                  href={launchResult.web_fallback_url}
                  target={launchResult.web_fallback_url.startsWith("http") ? "_blank" : undefined}
                  rel="noopener noreferrer"
                  className="btn btn-secondary btn-sm"
                  onClick={() =>
                    monitorOrbitHandoff(launchResult.app_id, ctx.deviceId, true, (patch) =>
                      setLaunchResult((prev: any) => (prev ? { ...prev, ...patch } : prev))
                    )
                  }
                >
                  <ExternalLink size={12} /> Open Web Fallback
                </a>
              )}
              {!launchResult.is_registered && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => {
                    setRegName(launchResult.app_name);
                    setShowRegisterForm(true);
                  }}
                >
                  <Plus size={12} /> Register {launchResult.app_name}
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* ORBIT Application Library */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
          <div className="card-title" style={{ margin: 0 }}>
            <span><Compass size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />ORBIT Application Library ({filteredApps.length})</span>
          </div>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <div style={{ position: "relative" }}>
              <Search size={13} style={{ position: "absolute", left: 10, top: 10, opacity: 0.6 }} />
              <input
                className="input"
                style={{ paddingLeft: 28, minWidth: 180 }}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Filter apps..."
              />
            </div>
            <button
              id="orbit-toggle-register-btn"
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setShowRegisterForm((v) => !v)}
            >
              <Plus size={12} /> Register App
            </button>
          </div>
        </div>

        {showRegisterForm && (
          <form onSubmit={handleRegisterCustomApp} className="list-item" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <strong>Manual Application Registration</strong>
            <div className="grid-2" style={{ gap: 8 }}>
              <input className="input" placeholder="App Name (e.g. Monzo, Notion)" value={regName} onChange={(e) => setRegName(e.target.value)} required />
              <input className="input" placeholder="Aliases (comma-separated, e.g. my bank)" value={regAliases} onChange={(e) => setRegAliases(e.target.value)} />
              <input className="input" placeholder="iOS URL Scheme (e.g. monzo://)" value={regScheme} onChange={(e) => setRegScheme(e.target.value)} />
              <input className="input" placeholder="Universal Link (e.g. https://monzo.com)" value={regUniversal} onChange={(e) => setRegUniversal(e.target.value)} />
              <input className="input" placeholder="Android Package (e.g. co.uk.getmondo)" value={regAndroidPkg} onChange={(e) => setRegAndroidPkg(e.target.value)} />
              <input className="input" placeholder="Web Fallback URL" value={regWebFallback} onChange={(e) => setRegWebFallback(e.target.value)} />
              <input className="input" placeholder="Desktop App Key" value={regDesktopKey} onChange={(e) => setRegDesktopKey(e.target.value)} />
              <input className="input" placeholder="Category (Finance, Productivity, Custom)" value={regCategory} onChange={(e) => setRegCategory(e.target.value)} />
            </div>
            <div className="row" style={{ gap: 8 }}>
              <button type="submit" className="btn btn-sm">Save Application</button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => setShowRegisterForm(false)}>Cancel</button>
            </div>
          </form>
        )}

        <DataTable
          rows={filteredApps}
          rowKey={(a) => a.app_id}
          emptyTitle="No Matching Applications"
          emptyDescription="Register any custom application using the Register App button above."
          columns={[
            {
              key: "name",
              header: "Application",
              render: (a) => (
                <div>
                  <strong>{a.name}</strong>
                  <div className="muted" style={{ fontSize: 11 }}>{a.category} · {a.source === "CUSTOM_REGISTERED" ? "Custom" : "Catalog"}</div>
                </div>
              ),
            },
            {
              key: "methods",
              header: "Methods & Platforms",
              render: (a) => (
                <div style={{ fontSize: 11 }}>
                  <div>{[a.universal_link && "Universal", a.ios_scheme && "Scheme", a.android_package && "Android", a.web_fallback && "Web"].filter(Boolean).join(" · ") || "Manual"}</div>
                  <div className="muted">{(a.platforms || []).join(", ")}</div>
                </div>
              ),
            },
            {
              key: "status",
              header: "Last Attempt / Status",
              render: (a) => (
                <div style={{ fontSize: 11 }}>
                  <StatusIndicator label={a.last_launch_status || a.verification_status || "READY"} tone={a.last_launch_error ? "danger" : "neutral"} />
                  {a.last_launch_at && <div className="muted mono">{a.last_launch_at.slice(0, 16).replace("T", " ")}</div>}
                </div>
              ),
            },
            {
              key: "actions",
              header: "Actions",
              render: (a) => (
                <div className="row" style={{ gap: 6 }}>
                  <button
                    id={`orbit-launch-${a.app_id}`}
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={() => requestLaunch(a.app_id, false)}
                  >
                    <Play size={12} /> Open
                  </button>
                  {a.source === "CUSTOM_REGISTERED" && (
                    <button type="button" className="btn btn-danger btn-sm" onClick={() => handleDeleteCustomApp(a.app_id)}>
                      <Trash2 size={12} />
                    </button>
                  )}
                </div>
              ),
            },
          ]}
        />
      </div>

      {/* Platform Discovery Capabilities */}
      {discovery && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div className="card-title">
            <span>Platform Discovery &amp; Native Companion Boundaries</span>
            <span className="pill mono">{discovery.platform}</span>
          </div>
          <div className="grid-3" style={{ gap: 10, fontSize: 12 }}>
            <div className="list-item">
              <strong>iOS (PWA)</strong>
              <div className="muted">Auto-enumerate installed apps: No (iOS sandbox). Uses Universal Links, URL schemes, and manual registration.</div>
            </div>
            <div className="list-item">
              <strong>Android (PWA)</strong>
              <div className="muted">Auto-enumerate installed apps: No (Android &lt;queries&gt; visibility). Uses Intent URIs, App Links, and manual package registration.</div>
            </div>
            <div className="list-item">
              <strong>Desktop (Paired Agent)</strong>
              <div className="muted">Paired: {discovery.desktop_agent_paired ? "Yes" : "No"} · Authorized: {discovery.desktop_agent_authorized ? "Yes" : "No"}. Requires explicit device authorization.</div>
            </div>
          </div>
        </div>
      )}

      {/* Remembered Permissions Table */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="card-title">
          <span><ShieldCheck size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Remembered Permissions ({permissions.length})</span>
        </div>
        <DataTable
          rows={permissions}
          rowKey={(p) => p.permission_id}
          emptyTitle="No Remembered App Permissions"
          emptyDescription="Approve ORBIT_APPLICATION_LAUNCH above or per-app to persist launch permissions for this device."
          columns={[
            { key: "app", header: "Application", render: (p) => <strong>{p.app_name}</strong> },
            { key: "device", header: "Device", render: (p) => p.device_label },
            {
              key: "status",
              header: "Status",
              render: (p) => (
                <StatusIndicator
                  label={p.status}
                  tone={p.status === "ALWAYS_ALLOW" ? "success" : p.status === "DENIED" ? "danger" : "neutral"}
                />
              ),
            },
            { key: "scope", header: "Scope", mono: true, render: (p) => p.permission_scope },
            {
              key: "approved",
              header: "Approved",
              mono: true,
              render: (p) => (p.approved_at ? p.approved_at.slice(0, 16).replace("T", " ") : "—"),
            },
            {
              key: "actions",
              header: "Revoke",
              render: (p) =>
                p.status === "ALWAYS_ALLOW" ? (
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    onClick={() => revokePermission(p.permission_id)}
                  >
                    <Trash2 size={12} /> Revoke
                  </button>
                ) : (
                  <span className="muted" style={{ fontSize: 12 }}>—</span>
                ),
            },
          ]}
        />
      </div>
    </div>
  );
}
