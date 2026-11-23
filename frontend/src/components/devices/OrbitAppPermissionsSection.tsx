import React, { useEffect, useState } from "react";
import { ExternalLink, Play, ShieldCheck, Smartphone, Trash2 } from "lucide-react";
import { apiFetch } from "../../lib/api";
import { DataTable, EmptyState, StatusIndicator, useToast } from "../ui/DesignSystem";

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

export function parseAppLaunchCommand(text: string): { appId: string; targetUri?: string } | null {
  const clean = text.trim();
  const lower = clean.toLowerCase();
  if (!/\b(open|launch|start)\b/.test(lower)) return null;
  if (lower.includes("spotify")) {
    return { appId: "spotify", targetUri: clean };
  }
  if (lower.includes("whatsapp")) return { appId: "whatsapp" };
  if (lower.includes("gmail")) return { appId: "gmail" };
  if (lower.includes("settings")) return { appId: "settings" };
  if (lower.includes("calendar")) return { appId: "google_calendar" };
  return null;
}

export function OrbitAppPermissionsSection() {
  const { pushToast } = useToast();
  const ctx = getClientDeviceContext();
  const [apps, setApps] = useState<any[]>([]);
  const [permissions, setPermissions] = useState<any[]>([]);
  const [spotifyTarget, setSpotifyTarget] = useState("");
  const [pendingApproval, setPendingApproval] = useState<any>(null);
  const [launchResult, setLaunchResult] = useState<any>(null);

  async function load() {
    try {
      const [cRes, pRes] = await Promise.all([
        apiFetch<any>("/api/v1/devices/apps/catalog").catch(() => ({ apps: [] })),
        apiFetch<any>("/api/v1/devices/apps/permissions").catch(() => ({ permissions: [] })),
      ]);
      setApps(cRes.apps || []);
      setPermissions(pRes.permissions || []);
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function requestLaunch(appId: string, allowOnce = false, targetUri?: string) {
    setLaunchResult(null);
    try {
      const res = await apiFetch<any>("/api/v1/devices/apps/launch", {
        method: "POST",
        body: {
          app_id: appId,
          device_id: ctx.deviceId,
          device_label: ctx.deviceLabel,
          platform: ctx.platform,
          target_uri: targetUri || (appId === "spotify" ? spotifyTarget : undefined),
          allow_once: allowOnce,
        },
      });
      if (res.status === "APPROVAL_REQUIRED") {
        setPendingApproval({ ...res, target_uri: targetUri || (appId === "spotify" ? spotifyTarget : undefined) });
      } else if (res.status === "DENIED") {
        setPendingApproval(null);
        pushToast(res.message || "Launch denied by device policy.", "error");
      } else if (res.status === "READY_TO_LAUNCH") {
        setPendingApproval(null);
        setLaunchResult(res);
        pushToast(`${res.app_name} launch prepared (${res.permission_mode}).`, "success");
        await load();
      }
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function decidePermission(decision: "ALLOW_ONCE" | "ALWAYS_ALLOW" | "DENIED") {
    if (!pendingApproval) return;
    if (decision === "ALLOW_ONCE") {
      await requestLaunch(pendingApproval.app_id, true, pendingApproval.target_uri);
      return;
    }
    try {
      await apiFetch("/api/v1/devices/apps/permissions", {
        method: "POST",
        body: {
          app_id: pendingApproval.app_id,
          device_id: ctx.deviceId,
          device_label: ctx.deviceLabel,
          decision,
        },
      });
      const appId = pendingApproval.app_id;
      const targetUri = pendingApproval.target_uri;
      setPendingApproval(null);
      await load();
      if (decision === "ALWAYS_ALLOW") {
        await requestLaunch(appId, false, targetUri);
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

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }} data-testid="orbit-app-permissions">
      {/* Quick App Launcher */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="card-title">
          <span><Smartphone size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />ORBIT Application Launcher</span>
          <span className="pill mono">{ctx.deviceLabel} ({ctx.platform})</span>
        </div>

        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <input
            className="input"
            style={{ flex: 1, minWidth: 200 }}
            value={spotifyTarget}
            onChange={(e) => setSpotifyTarget(e.target.value)}
            placeholder="Optional Spotify playlist, artist, track URL or URI..."
          />
        </div>

        <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
          {apps.map((a) => (
            <button
              key={a.app_id}
              id={`orbit-launch-${a.app_id}`}
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => requestLaunch(a.app_id, false)}
            >
              <Play size={12} /> Open {a.name}
            </button>
          ))}
        </div>

        {/* One-Time Approval Prompt */}
        {pendingApproval && (
          <div className="alert-box" data-testid="orbit-app-approval-prompt" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <strong>{pendingApproval.prompt}</strong>
            <div className="muted" style={{ fontSize: 12 }}>
              Device: {pendingApproval.device_label} · Scope: {pendingApproval.permission_scope} (applies only to {pendingApproval.app_name})
            </div>
            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
              <button id="orbit-allow-once-btn" type="button" className="btn btn-secondary btn-sm" onClick={() => decidePermission("ALLOW_ONCE")}>
                Allow once
              </button>
              <button id="orbit-always-allow-btn" type="button" className="btn btn-sm" onClick={() => decidePermission("ALWAYS_ALLOW")}>
                Always allow on this device
              </button>
              <button id="orbit-deny-app-btn" type="button" className="btn btn-danger btn-sm" onClick={() => decidePermission("DENIED")}>
                Deny
              </button>
            </div>
          </div>
        )}

        {/* Launch Dispatch & Honest Platform Fallback */}
        {launchResult && (
          <div className="list-item" data-testid="orbit-app-launch-result" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="row-between" style={{ flexWrap: "wrap", gap: 6 }}>
              <strong>{launchResult.app_name} Ready ({launchResult.permission_mode})</strong>
              <StatusIndicator label={launchResult.launch_status} tone="info" />
            </div>
            <div className="muted" style={{ fontSize: 12 }}>{launchResult.platform_limitation_note}</div>
            <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
              {launchResult.launch_url && (
                <a href={launchResult.launch_url} className="btn btn-sm">
                  <ExternalLink size={12} /> Open {launchResult.app_name} App
                </a>
              )}
              {launchResult.web_fallback_url && (
                <a
                  href={launchResult.web_fallback_url}
                  target={launchResult.web_fallback_url.startsWith("http") ? "_blank" : undefined}
                  rel="noopener noreferrer"
                  className="btn btn-secondary btn-sm"
                >
                  <ExternalLink size={12} /> Open Web Fallback
                </a>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Persistent Application Permissions Table */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="card-title">
          <span><ShieldCheck size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />Application Permissions ({permissions.length})</span>
        </div>
        <DataTable
          rows={permissions}
          rowKey={(p) => p.permission_id}
          emptyTitle="No Persistent App Permissions"
          emptyDescription="Launch an app above and choose 'Always allow on this device' to persist per-app approval."
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
              key: "last",
              header: "Last Launch",
              mono: true,
              render: (p) => (p.last_launch_at ? `${p.last_launch_at.slice(0, 16).replace("T", " ")} (${p.last_launch_status || ""})` : "Never"),
            },
            {
              key: "action",
              header: "Control",
              render: (p) =>
                p.status === "ALWAYS_ALLOW" ? (
                  <button type="button" className="btn btn-danger btn-sm" onClick={() => revokePermission(p.permission_id)}>
                    <Trash2 size={12} /> Revoke
                  </button>
                ) : (
                  <span className="muted">—</span>
                ),
            },
          ]}
        />
      </div>
    </div>
  );
}
