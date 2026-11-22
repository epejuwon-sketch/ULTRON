import React, { useEffect, useState } from "react";
import { Bell, HardDrive, Mic, RefreshCw } from "lucide-react";
import { apiFetch } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import { ModulePageProps } from "./CommandModulePage";
import {
  ConfirmationDialog,
  DataTable,
  EmptyState,
  ErrorState,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";

export default function DevicesModulePage({ subPage, onSelectSubPage, device }: ModulePageProps) {
  const mod = getModule("devices");
  const page = getSubPage("devices", subPage);
  const { pushToast } = useToast();

  const [devices, setDevices] = useState<any[]>([]);
  const [locations, setLocations] = useState<any[]>([]);
  const [alerts, setAlerts] = useState<any[]>([]);
  const [platform, setPlatform] = useState("ios");
  const [pairCode, setPairCode] = useState<any>(null);
  const [error, setError] = useState("");
  const [confirmRevokeId, setConfirmRevokeId] = useState<string | null>(null);

  async function load() {
    setError("");
    try {
      const [dRes, lRes, aRes] = await Promise.all([
        apiFetch<any>("/api/v1/devices").catch(() => ({ devices: [] })),
        apiFetch<any>("/api/v1/devices/locations").catch(() => ({ locations: [] })),
        apiFetch<any>("/api/v1/devices/location/alerts").catch(() => ({ alerts: [] })),
      ]);
      setDevices(dRes.devices || []);
      setLocations(lRes.locations || []);
      setAlerts(aRes.alerts || []);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    load();
  }, [subPage]);

  async function initPairing() {
    try {
      const res = await apiFetch<any>("/api/v1/devices/pair/init", {
        method: "POST",
        body: { target_platform: platform, requested_permissions: { location: true, notifications: true, file_read: false } },
      });
      setPairCode(res);
      pushToast("Single-use ORBIT pairing code generated.", "success");
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  async function updatePermissions(deviceId: string, permissions: Record<string, boolean>) {
    try {
      await apiFetch(`/api/v1/devices/${deviceId}/permissions`, {
        method: "PATCH",
        body: { permissions },
      });
      pushToast("Device permissions updated.", "success");
      load();
    } catch (e: any) {
      pushToast(e.message, "error");
    }
  }

  const speechAvailable =
    typeof window !== "undefined" && Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
  const ttsAvailable = typeof window !== "undefined" && "speechSynthesis" in window;

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`ORBIT DEVICE MANAGEMENT // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <button type="button" className="btn btn-secondary btn-sm" onClick={load}>
            <RefreshCw size={13} /> Refresh
          </button>
        }
      />

      {error && <ErrorState message={error} onRetry={load} />}

      {/* 91. ORBIT OVERVIEW */}
      {page.id === "overview" && (
        <div className="grid-3">
          <MetricDisplay label="Paired Nodes" value={devices.length} sub="ORBIT device mesh" tone="info" />
          <MetricDisplay label="Authorized Locations" value={locations.length} sub="Explicit opt-in telemetry" tone="success" />
          <MetricDisplay label="Current Viewport" value={`${device.width}×${device.height}`} sub={`${device.deviceClass.toUpperCase()} · ${device.isTouch ? "Touch" : "Pointer"}`} tone="neutral" />
        </div>
      )}

      {/* 92. CONNECTED DEVICES */}
      {page.id === "connected" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title"><span><HardDrive size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Pair New ORBIT Device</span></div>
            <div className="row" style={{ marginBottom: 12 }}>
              <select className="select" style={{ flex: 1 }} value={platform} onChange={(e) => setPlatform(e.target.value)}>
                <option value="ios">iPhone / iPad (iOS PWA)</option>
                <option value="macos">macOS Desktop</option>
                <option value="windows">Windows Desktop</option>
                <option value="android">Android</option>
              </select>
              <button type="button" className="btn" onClick={initPairing}>Generate Code</button>
            </div>
            {pairCode && (
              <div className="alert-box">
                <strong>Pairing Code:</strong> <code className="mono">{pairCode.pairing_code}</code>
                <div className="muted">Expires: {pairCode.expires_at}</div>
              </div>
            )}
          </div>
          <div className="card">
            <div className="card-title"><span>Paired Devices ({devices.length})</span></div>
            {devices.length === 0 ? (
              <EmptyState title="No Paired Devices" description="Generate a single-use pairing code to link a phone or workstation." />
            ) : (
              devices.map((d) => (
                <div key={d.device_id} className="list-item" style={{ marginBottom: 8 }}>
                  <div className="row-between">
                    <strong>{d.name} ({d.platform})</strong>
                    <StatusIndicator label={d.status || "ONLINE"} tone={d.status === "ONLINE" ? "success" : "warn"} />
                  </div>
                  <div className="row">
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={async () => {
                        await apiFetch(`/api/v1/devices/${d.device_id}/location/control`, { method: "POST", body: { action: "PAUSE" } });
                        pushToast("Location paused.", "info");
                        load();
                      }}
                    >
                      Pause Location
                    </button>
                    <button type="button" className="btn btn-danger btn-sm" onClick={() => setConfirmRevokeId(d.device_id)}>
                      Revoke Device
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>
      )}

      {/* 93. DEVICE PERMISSIONS */}
      {page.id === "permissions" && (
        <div className="card">
          <div className="card-title"><span>Device Permission Matrix</span></div>
          {devices.length === 0 ? (
            <EmptyState title="No Devices Paired" description="Pair a device to configure fine-grained read/write/location scopes." />
          ) : (
            devices.map((d) => (
              <div key={d.device_id} className="list-item" style={{ marginBottom: 8 }}>
                <div className="row-between">
                  <strong>{d.name}</strong>
                  <div className="row">
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => updatePermissions(d.device_id, { location: true, notifications: true, file_read: false })}>
                      Standard Scope
                    </button>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => updatePermissions(d.device_id, { location: false, notifications: true, file_read: false })}>
                      Privacy Scope
                    </button>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      )}

      {/* 94. DEVICE ACTIVITY & ALERTS */}
      {page.id === "activity" && (
        <div className="card">
          <div className="card-title"><span>Location & Device Alerts ({alerts.length})</span></div>
          <DataTable
            rows={alerts}
            rowKey={(a, i) => a.alert_id || String(i)}
            emptyTitle="No Location Alerts"
            emptyDescription="Geofence triggers and device telemetry alerts appear here."
            columns={[
              { key: "title", header: "Alert", render: (a) => <strong>{a.label || a.alert_type || "Alert"}</strong> },
              { key: "device", header: "Device", mono: true, render: (a) => a.device_id || "—" },
              { key: "status", header: "Status", render: (a) => <StatusIndicator label={a.status || "ACTIVE"} tone="info" /> },
            ]}
          />
        </div>
      )}

      {/* 95. VOICE & MICROPHONE SETTINGS */}
      {page.id === "voice-mic" && (
        <div className="card">
          <div className="card-title"><span><Mic size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Browser Voice & Microphone Capabilities</span></div>
          <div className="grid-2">
            <MetricDisplay label="Web Speech STT" value={speechAvailable ? "Supported" : "Unavailable"} sub="Requires HTTPS + mic permission" tone={speechAvailable ? "success" : "warn"} />
            <MetricDisplay label="Speech Synthesis TTS" value={ttsAvailable ? "Supported" : "Unavailable"} sub="Interruptible voice readout" tone={ttsAvailable ? "success" : "warn"} />
          </div>
        </div>
      )}

      {/* 96. NOTIFICATION SETTINGS */}
      {page.id === "notif-settings" && (
        <div className="card">
          <div className="card-title"><span><Bell size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Device Notification Delivery</span></div>
          <p className="muted">
            Push notification permission in this browser:{" "}
            <strong className="mono">
              {typeof Notification !== "undefined" ? Notification.permission.toUpperCase() : "UNSUPPORTED"}
            </strong>
          </p>
        </div>
      )}

      <ConfirmationDialog
        open={Boolean(confirmRevokeId)}
        title="Revoke Paired Device"
        message="Immediately revoke ORBIT credentials for this device? It must re-pair before accessing ULTRON."
        confirmLabel="Revoke Device"
        onCancel={() => setConfirmRevokeId(null)}
        onConfirm={async () => {
          if (confirmRevokeId) {
            await apiFetch(`/api/v1/devices/${confirmRevokeId}/revoke`, { method: "POST" });
            pushToast("Device revoked.", "success");
            load();
          }
          setConfirmRevokeId(null);
        }}
      />
    </ResponsiveWorkspace>
  );
}
