import React, { useEffect, useState } from "react";
import {
  Bell,
  HardDrive,
  Mic,
  RefreshCw,
  Shield,
  Smartphone,
  Volume2,
  Wifi,
} from "lucide-react";
import { apiFetch } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import {
  ConfirmationDialog,
  DataTable,
  EmptyState,
  ErrorState,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  StatusIndicator,
  StatusTone,
  useToast,
} from "../components/ui/DesignSystem";
import { OrbitAppPermissionsSection } from "../components/devices/OrbitAppPermissionsSection";

interface CapabilityItem {
  id: string;
  name: string;
  supported: boolean;
  permissionStatus: string;
  tone: StatusTone;
  detail: string;
  iosGuide: string;
  actionLabel?: string;
  onAction?: () => void;
}

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

  // Live browser / iPhone permission statuses
  const [micPerm, setMicPerm] = useState<string>("prompt");
  const [camPerm, setCamPerm] = useState<string>("prompt");
  const [geoPerm, setGeoPerm] = useState<string>("prompt");
  const [notifPerm, setNotifPerm] = useState<string>(
    typeof Notification !== "undefined" ? Notification.permission : "unsupported"
  );
  const [swState, setSwState] = useState<string>("checking");
  const [standalonePwa, setStandalonePwa] = useState<boolean>(false);

  async function probeBrowserPermissions() {
    if (typeof window === "undefined") return;
    setStandalonePwa(
      Boolean(
        window.matchMedia?.("(display-mode: standalone)")?.matches ||
          (window.navigator as any).standalone === true
      )
    );
    if (typeof Notification !== "undefined") {
      setNotifPerm(Notification.permission);
    } else {
      setNotifPerm("unsupported");
    }
    const perms = (navigator as any).permissions;
    if (perms?.query) {
      for (const [name, setter] of [
        ["microphone", setMicPerm],
        ["camera", setCamPerm],
        ["geolocation", setGeoPerm],
      ] as const) {
        try {
          const st = await perms.query({ name: name as any });
          setter(st.state || "prompt");
        } catch {
          setter("ask_on_use");
        }
      }
    } else {
      setMicPerm("ask_on_use");
      setCamPerm("ask_on_use");
      setGeoPerm("ask_on_use");
    }
    if ("serviceWorker" in navigator) {
      try {
        const reg = await navigator.serviceWorker.getRegistration();
        setSwState(reg?.active ? "active" : reg ? "registered" : "not_registered");
      } catch {
        setSwState("unavailable");
      }
    } else {
      setSwState("unsupported");
    }
  }

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
    probeBrowserPermissions();
  }

  useEffect(() => {
    load();
  }, [subPage]);

  async function initPairing() {
    try {
      const res = await apiFetch<any>("/api/v1/devices/pair/init", {
        method: "POST",
        body: {
          target_platform: platform,
          requested_permissions: { location: true, notifications: true, file_read: false },
        },
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

  async function requestMicrophoneTest() {
    if (!navigator.mediaDevices?.getUserMedia) {
      pushToast("Microphone capture requires HTTPS and a supported browser.", "error");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      setMicPerm("granted");
      pushToast("Microphone permission granted and verified.", "success");
    } catch (err: any) {
      setMicPerm("denied");
      pushToast(`Microphone unavailable: ${err?.message || "Permission denied"}`, "error");
    }
  }

  async function requestCameraTest() {
    if (!navigator.mediaDevices?.getUserMedia) {
      pushToast("Camera API unavailable — use the native Photo/Camera picker in NEON or File Hub.", "info");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      stream.getTracks().forEach((t) => t.stop());
      setCamPerm("granted");
      pushToast("Camera permission granted and verified.", "success");
    } catch (err: any) {
      setCamPerm("denied");
      pushToast(`Camera unavailable: ${err?.message || "Permission denied"}`, "error");
    }
  }

  function testSpeechOutput() {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      pushToast("Speech Synthesis is not supported in this browser.", "error");
      return;
    }
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance("ULTRON voice output is active and ready.");
    window.speechSynthesis.speak(u);
    pushToast("Playing voice readout test.", "success");
  }

  async function requestNotifications() {
    if (typeof Notification === "undefined") {
      pushToast("Notifications require iOS 16.4+ installed to Home Screen or a desktop browser.", "error");
      return;
    }
    try {
      const result = await Notification.requestPermission();
      setNotifPerm(result);
      if (result === "granted") {
        try {
          new Notification("ULTRON OS", { body: "Notifications are enabled for this device." });
        } catch {
          // ServiceWorker-only notification environments (iOS standalone)
        }
        pushToast("Notification permission granted.", "success");
      } else {
        pushToast(`Notification permission is '${result}'.`, "info");
      }
    } catch (err: any) {
      pushToast(err?.message || "Notification permission request failed.", "error");
    }
  }

  async function testNativeShare() {
    if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
      try {
        await navigator.share({
          title: "ULTRON OS 2026",
          text: "Shared from ULTRON OS Mobile Command Centre.",
          url: window.location.origin,
        });
        pushToast("Native Share Sheet opened.", "success");
      } catch (err: any) {
        if (err?.name !== "AbortError") pushToast("Native share cancelled or unavailable.", "info");
      }
    } else {
      pushToast("Native Share Sheet is supported on iPhone Safari/PWA; desktop uses Copy Clipboard.", "info");
    }
  }

  function requestLocationTest() {
    if (!navigator.geolocation) {
      pushToast("Geolocation is not supported in this browser.", "error");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      () => {
        setGeoPerm("granted");
        pushToast("Location permission granted (coordinates kept private on device).", "success");
      },
      (err) => {
        setGeoPerm(err.code === 1 ? "denied" : "unavailable");
        pushToast(`Location not granted: ${err.message}`, "error");
      },
      { timeout: 6000 }
    );
  }

  async function checkServiceWorkerUpdate() {
    if (!("serviceWorker" in navigator)) {
      pushToast("Service Worker offline shell is not supported in this browser.", "error");
      return;
    }
    try {
      const reg = await navigator.serviceWorker.getRegistration();
      if (!reg) {
        pushToast("No Service Worker registered yet.", "info");
        return;
      }
      await reg.update();
      setSwState(reg.active ? "active" : "registered");
      pushToast("Checked for ULTRON PWA shell updates.", "success");
    } catch (err: any) {
      pushToast(err?.message || "Update check failed.", "error");
    }
  }

  const speechAvailable =
    typeof window !== "undefined" && Boolean((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition);
  const ttsAvailable = typeof window !== "undefined" && "speechSynthesis" in window;
  const mediaDevicesAvailable = typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);
  const shareAvailable = typeof navigator !== "undefined" && typeof navigator.share === "function";
  const notifSupported = typeof Notification !== "undefined";
  const geoSupported = typeof navigator !== "undefined" && "geolocation" in navigator;
  const swSupported = typeof navigator !== "undefined" && "serviceWorker" in navigator;
  const bgSyncSupported =
    typeof window !== "undefined" &&
    "serviceWorker" in navigator &&
    "SyncManager" in window;

  const toneForStatus = (status: string, supported: boolean): StatusTone => {
    if (!supported) return "neutral";
    if (["granted", "active", "installed", "ready"].includes(status)) return "success";
    if (["denied"].includes(status)) return "warn";
    return "info";
  };

  const capabilities: CapabilityItem[] = [
    {
      id: "microphone",
      name: "Microphone Access",
      supported: mediaDevicesAvailable,
      permissionStatus: mediaDevicesAvailable ? micPerm : "unsupported",
      tone: toneForStatus(micPerm, mediaDevicesAvailable),
      detail: "Used only when you explicitly tap the Voice button in NEON.",
      iosGuide: "iPhone: Settings → Safari (or ULTRON) → Microphone → Allow / Ask",
      actionLabel: "Request / Test Mic",
      onAction: requestMicrophoneTest,
    },
    {
      id: "stt",
      name: "Speech-to-Text (Voice Commands)",
      supported: speechAvailable,
      permissionStatus: speechAvailable ? "ready" : "unsupported",
      tone: speechAvailable ? "success" : "neutral",
      detail: "Dictates spoken commands directly into NEON chat on Safari/Chrome.",
      iosGuide: "iPhone: Settings → General → Keyboard → Enable Dictation + Safari Microphone",
    },
    {
      id: "tts",
      name: "Natural Voice Output (TTS)",
      supported: ttsAvailable,
      permissionStatus: ttsAvailable ? "ready" : "unsupported",
      tone: ttsAvailable ? "success" : "neutral",
      detail: "Reads NEON responses aloud with instant Stop control.",
      iosGuide: "iPhone: Ensure Silent switch is off and volume is up.",
      actionLabel: "Test Voice",
      onAction: testSpeechOutput,
    },
    {
      id: "camera",
      name: "Camera Capture",
      supported: true,
      permissionStatus: mediaDevicesAvailable ? camPerm : "native_picker_ready",
      tone: toneForStatus(mediaDevicesAvailable ? camPerm : "ready", true),
      detail: "Take a photo directly in NEON or File Hub for Gemini Vision analysis.",
      iosGuide: "iPhone: Settings → Safari (or ULTRON) → Camera → Allow / Ask",
      actionLabel: "Request / Test Camera",
      onAction: requestCameraTest,
    },
    {
      id: "file-picker",
      name: "Photo Library & File Picker",
      supported: true,
      permissionStatus: "ready",
      tone: "success",
      detail: "Multi-file upload for Photos, PDFs, Office docs, spreadsheets, and code.",
      iosGuide: "iOS prompts natively each time you choose Photo Library or Browse Files.",
    },
    {
      id: "notifications",
      name: "System Notifications",
      supported: notifSupported,
      permissionStatus: notifPerm,
      tone: toneForStatus(notifPerm, notifSupported),
      detail: "Explicit opt-in alerts for approvals, tasks, and system status.",
      iosGuide: "iPhone (iOS 16.4+): Add ULTRON to Home Screen, then Settings → Notifications → ULTRON",
      actionLabel: "Request Permission",
      onAction: requestNotifications,
    },
    {
      id: "share-sheet",
      name: "Native Share Sheet (Share Out)",
      supported: shareAvailable,
      permissionStatus: shareAvailable ? "ready" : "clipboard_fallback",
      tone: shareAvailable ? "success" : "info",
      detail: "Share NEON answers directly into Messages, Mail, Notes, or AirDrop.",
      iosGuide: "Built into iOS Safari & Home Screen apps — no separate permission needed.",
      actionLabel: "Test Share Sheet",
      onAction: testNativeShare,
    },
    {
      id: "share-target",
      name: "Share-to-ULTRON Target (BRIDGE)",
      supported: true,
      permissionStatus: standalonePwa ? "installed" : "pwa_install_recommended",
      tone: standalonePwa ? "success" : "info",
      detail: "Configured in manifest.webmanifest (/api/v1/bridge/share) with AEGIS URL inspection.",
      iosGuide: "Install ULTRON via Safari → Share → Add to Home Screen.",
    },
    {
      id: "geolocation",
      name: "Location Access (Strict Opt-In)",
      supported: geoSupported,
      permissionStatus: geoSupported ? geoPerm : "unsupported",
      tone: toneForStatus(geoPerm, geoSupported),
      detail: "Never collected silently. Used only when explicitly requested by operator.",
      iosGuide: "iPhone: Settings → Privacy & Security → Location Services → Safari Websites",
      actionLabel: "Request / Test Location",
      onAction: requestLocationTest,
    },
    {
      id: "offline-shell",
      name: "Offline App Shell & PWA Updates",
      supported: swSupported,
      permissionStatus: swSupported ? swState : "unsupported",
      tone: toneForStatus(swState, swSupported),
      detail: "Service Worker v2 caches offline shell while always fetching fresh app bundles.",
      iosGuide: "Pull to refresh or tap Check for Update after new deployments.",
      actionLabel: "Check for Update",
      onAction: checkServiceWorkerUpdate,
    },
    {
      id: "bg-sync",
      name: "Background Sync",
      supported: bgSyncSupported,
      permissionStatus: bgSyncSupported ? "ready" : "ios_webkit_not_supported",
      tone: bgSyncSupported ? "success" : "neutral",
      detail: bgSyncSupported
        ? "Supported in this browser for queued offline actions."
        : "iOS Safari/WebKit does not expose Web Background Sync; ULTRON retries on foreground reconnect.",
      iosGuide: "Keep ULTRON open briefly after reconnecting to sync queued changes.",
    },
  ];

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
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          <div className="grid-3">
            <MetricDisplay label="Paired Nodes" value={devices.length} sub="ORBIT device mesh" tone="info" />
            <MetricDisplay
              label="App Mode"
              value={standalonePwa ? "Home Screen PWA" : "Browser Tab"}
              sub={`${device.deviceClass.toUpperCase()} · ${device.isTouch ? "Touch" : "Pointer"}`}
              tone={standalonePwa ? "success" : "info"}
            />
            <MetricDisplay
              label="Current Viewport"
              value={`${device.width}×${device.height}`}
              sub={`Authorized locations: ${locations.length}`}
              tone="neutral"
            />
          </div>
          <div className="card">
            <div className="card-title">
              <span><Smartphone size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />iPhone &amp; Device Hardware Readiness</span>
              <button type="button" className="btn btn-sm" onClick={() => onSelectSubPage("permissions")}>
                <Shield size={13} /> Open Permission Centre
              </button>
            </div>
            <div className="muted">
              Manage microphone, voice, camera, photo/file uploads, notifications, native sharing, offline shell updates, and paired ORBIT device scopes with full user-initiated consent.
            </div>
          </div>
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

      {/* 93. DEVICE PERMISSIONS (iPhone & Browser Capability Centre + Paired Device Scopes) */}
      {page.id === "permissions" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <OrbitAppPermissionsSection />
          <div className="card">
            <div className="card-title">
              <span><Shield size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />iPhone &amp; Browser Hardware Permission Centre</span>
              <StatusIndicator
                label={standalonePwa ? "INSTALLED PWA" : "WEB SESSION"}
                tone={standalonePwa ? "success" : "info"}
              />
            </div>
            <div className="muted" style={{ marginBottom: 12 }}>
              ULTRON only requests device permissions when you explicitly tap a control below. Every capability reports its real support and permission state on this device.
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {capabilities.map((cap) => (
                <div key={cap.id} className="list-item" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                  <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
                    <div className="row" style={{ gap: 8 }}>
                      <strong>{cap.name}</strong>
                      <StatusIndicator
                        label={cap.supported ? cap.permissionStatus.replace(/_/g, " ").toUpperCase() : "NOT SUPPORTED"}
                        tone={cap.tone}
                      />
                    </div>
                    {cap.actionLabel && cap.onAction && (
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={cap.onAction}
                      >
                        {cap.actionLabel}
                      </button>
                    )}
                  </div>
                  <div style={{ fontSize: 13 }}>{cap.detail}</div>
                  <div className="muted" style={{ fontSize: 11.5 }}>{cap.iosGuide}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-title"><span>Paired ORBIT Device Scope Matrix</span></div>
            {devices.length === 0 ? (
              <EmptyState title="No Paired ORBIT Devices" description="Pair an iPhone or workstation in Connected Devices to manage remote read/write/location scopes." />
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
        </div>
      )}

      {/* 94. DEVICE ACTIVITY & ALERTS */}
      {page.id === "activity" && (
        <div className="card">
          <div className="card-title"><span>Location &amp; Device Alerts ({alerts.length})</span></div>
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
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span><Mic size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Browser Voice &amp; Microphone Capabilities</span></div>
          <div className="grid-2">
            <MetricDisplay label="Web Speech STT" value={speechAvailable ? "Supported" : "Unavailable"} sub={`Mic permission: ${micPerm}`} tone={speechAvailable ? "success" : "warn"} />
            <MetricDisplay label="Speech Synthesis TTS" value={ttsAvailable ? "Supported" : "Unavailable"} sub="Interruptible voice readout" tone={ttsAvailable ? "success" : "warn"} />
          </div>
          <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
            <button type="button" className="btn btn-sm" onClick={requestMicrophoneTest}>
              <Mic size={13} /> Request / Test Microphone
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={testSpeechOutput}>
              <Volume2 size={13} /> Test Voice Readout
            </button>
          </div>
        </div>
      )}

      {/* 96. NOTIFICATION SETTINGS */}
      {page.id === "notif-settings" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span><Bell size={15} style={{ verticalAlign: "middle", marginRight: 6 }} />Device Notification Delivery</span></div>
          <p className="muted">
            Push notification permission in this browser:{" "}
            <strong className="mono">{notifPerm.toUpperCase()}</strong>
          </p>
          <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
            <button type="button" className="btn btn-sm" onClick={requestNotifications}>
              <Bell size={13} /> Request Notification Permission
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={checkServiceWorkerUpdate}>
              <Wifi size={13} /> Check Offline App Update
            </button>
          </div>
          <div className="muted" style={{ fontSize: 12 }}>
            On iPhone (iOS 16.4+), notifications require opening ULTRON from your Home Screen icon. Manage anytime in iOS Settings → Notifications → ULTRON.
          </div>
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
