import React, { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";

/* 14. Device Centre (ORBIT Pairing, Permissions, Location Pause/Revoke) */
export function DevicesView() {
  const [devices, setDevices] = useState<any[]>([]);
  const [platform, setPlatform] = useState("ios");
  const [pairCode, setPairCode] = useState<any>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      const res = await apiFetch<any>("/api/v1/devices");
      setDevices(res.devices || []);
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function initPairing() {
    setError("");
    try {
      const res = await apiFetch<any>("/api/v1/devices/pair/init", {
        method: "POST",
        body: { target_platform: platform, requested_permissions: { location: true, notifications: true, file_read: false } },
      });
      setPairCode(res);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function locationControl(deviceId: string, action: "PAUSE" | "RESUME" | "REVOKE") {
    await apiFetch(`/api/v1/devices/${deviceId}/location/control`, { method: "POST", body: { action } });
    await load();
  }

  async function revoke(deviceId: string) {
    await apiFetch(`/api/v1/devices/${deviceId}/revoke`, { method: "POST" });
    await load();
  }

  return (
    <div className="grid-2">
      <div className="card">
        <div className="card-title"><span>ORBIT Device Pairing</span></div>
        {error && <div className="alert-box alert-error">{error}</div>}
        <div className="row" style={{ marginBottom: 12 }}>
          <select className="select" style={{ flex: 1 }} value={platform} onChange={(e) => setPlatform(e.target.value)}>
            <option value="ios">iPhone / iPad (iOS PWA)</option>
            <option value="windows">Windows Desktop Agent</option>
            <option value="macos">macOS Desktop Agent</option>
            <option value="android">Android</option>
          </select>
          <button className="btn" onClick={initPairing}>Generate Pairing Code</button>
        </div>
        {pairCode && (
          <div className="alert-box">
            <strong>Single-Use Pairing Code:</strong> <code>{pairCode.pairing_code}</code>
            <div className="muted">Expires: {pairCode.expires_at}</div>
          </div>
        )}
      </div>

      <div className="card">
        <div className="card-title"><span>Paired Devices ({devices.length})</span></div>
        {devices.length === 0 ? (
          <div className="muted">No devices paired yet.</div>
        ) : (
          devices.map((d) => (
            <div key={d.device_id} className="list-item" style={{ marginBottom: 8 }}>
              <div className="row-between">
                <strong>{d.name} ({d.platform})</strong>
                <span className={`pill ${d.status === "ONLINE" ? "pill-green" : "pill-danger"}`}>{d.status}</span>
              </div>
              <div className="row">
                <button className="btn btn-secondary btn-sm" onClick={() => locationControl(d.device_id, "PAUSE")}>Pause Location</button>
                <button className="btn btn-secondary btn-sm" onClick={() => locationControl(d.device_id, "RESUME")}>Resume</button>
                <button className="btn btn-danger btn-sm" onClick={() => revoke(d.device_id)}>Revoke Device</button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/* 15. Integrations (Unified IntegrationManager) */
export function IntegrationsView() {
  const [statusData, setStatusData] = useState<any>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setStatusData(await apiFetch<any>("/api/v1/integrations/status"));
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function verifyProvider(provider: string) {
    try {
      await apiFetch(`/api/v1/integrations/${provider}/verify`, { method: "POST" });
      await load();
    } catch (e: any) {
      setError(e.message);
    }
  }

  const providers = statusData?.providers ? Object.entries(statusData.providers) : [];

  return (
    <div className="card">
      <div className="card-title">
        <span>Unified IntegrationManager (Honest Live Readiness)</span>
        <button className="btn btn-secondary btn-sm" onClick={load}>Refresh</button>
      </div>
      {error && <div className="alert-box alert-error">{error}</div>}
      <div className="grid-2">
        {providers.map(([key, val]: [string, any]) => (
          <div key={key} className="list-item">
            <div className="row-between">
              <strong>{key.toUpperCase()}</strong>
              <span className={`pill ${val.status === "ACTIVE" || val.status === "CONNECTED" ? "pill-green" : "pill-warn"}`}>
                {val.status || "REQUIRES_CONFIGURATION"}
              </span>
            </div>
            <div className="muted">Auth: {val.auth_type || "API_KEY/OAUTH"} · {val.detail || val.last_error || "Ready to configure"}</div>
            <div className="row">
              <button className="btn btn-secondary btn-sm" onClick={() => verifyProvider(key)}>Verify Live</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

/* 16. Memory Settings & User Preferences */
export function MemoryView() {
  const [memories, setMemories] = useState<any[]>([]);
  const [content, setContent] = useState("");
  const [memType, setMemType] = useState("LONG_TERM");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      const res = await apiFetch<any>("/api/v1/memory");
      setMemories(res.memories || []);
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function store(e: React.FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    await apiFetch("/api/v1/memory", { method: "POST", body: { content, memory_type: memType } });
    setContent("");
    await load();
  }

  async function search(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) { await load(); return; }
    const res = await apiFetch<any>("/api/v1/memory/search", { method: "POST", body: { query, limit: 15 } });
    setMemories(res.results || []);
  }

  async function del(id: string) {
    await apiFetch(`/api/v1/memory/${id}`, { method: "DELETE" });
    await load();
  }

  return (
    <div className="grid-2">
      <div className="card">
        <div className="card-title"><span>Store Versioned Memory (Secret-Redacted)</span></div>
        {error && <div className="alert-box alert-error">{error}</div>}
        <form onSubmit={store} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <select className="select" value={memType} onChange={(e) => setMemType(e.target.value)}>
            <option value="LONG_TERM">LONG_TERM</option>
            <option value="EPISODIC">EPISODIC</option>
            <option value="SEMANTIC">SEMANTIC</option>
            <option value="PROJECT">PROJECT</option>
          </select>
          <textarea className="textarea" rows={3} value={content} onChange={(e) => setContent(e.target.value)} placeholder="Store preference, context, or operational fact..." />
          <button className="btn" type="submit">Store Memory</button>
        </form>
      </div>

      <div className="card">
        <div className="card-title"><span>Inspect & Search Memories ({memories.length})</span></div>
        <form onSubmit={search} className="row" style={{ marginBottom: 10 }}>
          <input className="input" style={{ flex: 1 }} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Semantic search..." />
          <button className="btn btn-secondary btn-sm" type="submit">Search</button>
        </form>
        {memories.length === 0 ? (
          <div className="muted">No memories stored yet.</div>
        ) : (
          memories.map((m) => (
            <div key={m.memory_id} className="list-item" style={{ marginBottom: 6 }}>
              <div className="row-between">
                <span className="pill pill-cyan">{m.memory_type} v{m.version || 1}</span>
                <button className="btn btn-danger btn-sm" onClick={() => del(m.memory_id)}>Delete</button>
              </div>
              <div style={{ fontSize: 13 }}>{m.content}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/* 17. Security Centre (AEGIS + Audit Chain + EVOLVE) */
export function SecurityView() {
  const [posture, setPosture] = useState<any>(null);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [proposals, setProposals] = useState<any[]>([]);
  const [chain, setChain] = useState<any>(null);
  const [scanning, setScanning] = useState(false);

  async function load() {
    const [p, inc, evo, ch] = await Promise.all([
      apiFetch<any>("/api/v1/aegis/posture"),
      apiFetch<any>("/api/v1/aegis/incidents"),
      apiFetch<any>("/api/v1/evolve/proposals"),
      apiFetch<any>("/api/v1/audit/verify"),
    ]);
    setPosture(p);
    setIncidents(inc.incidents || []);
    setProposals(evo.proposals || []);
    setChain(ch);
  }
  useEffect(() => { load(); }, []);

  async function triggerScan() {
    setScanning(true);
    try {
      await apiFetch("/api/v1/aegis/scans", { method: "POST", body: { scan_type: "FULL" } });
      await load();
    } finally {
      setScanning(false);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="grid-3">
        <div className="card">
          <div className="muted">AEGIS Risk Score</div>
          <div className="stat-value">{posture?.latest_risk_score ?? "—"} / 100</div>
        </div>
        <div className="card">
          <div className="muted">Open Incidents</div>
          <div className="stat-value">{posture?.open_incidents ?? 0}</div>
        </div>
        <div className="card">
          <div className="muted">Audit Hash Chain</div>
          <div className="stat-value" style={{ color: chain?.valid ? "#10b981" : "#ef4444" }}>
            {chain?.valid ? "INTACT" : "CHECK"}
          </div>
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          <span>AEGIS Autonomous Defence & Incidents ({incidents.length})</span>
          <button className="btn btn-sm" disabled={scanning} onClick={triggerScan}>{scanning ? "Scanning..." : "Run AEGIS Scan"}</button>
        </div>
        {incidents.length === 0 ? (
          <div className="muted">No security incidents detected.</div>
        ) : (
          incidents.map((i) => (
            <div key={i.incident_id} className="list-item" style={{ marginBottom: 6 }}>
              <div className="row-between">
                <strong>{i.title}</strong>
                <span className={`pill ${i.severity === "HIGH" || i.severity === "CRITICAL" ? "pill-danger" : "pill-warn"}`}>{i.severity} · {i.status}</span>
              </div>
            </div>
          ))
        )}
      </div>

      <div className="card">
        <div className="card-title"><span>EVOLVE Controlled Self-Development ({proposals.length})</span></div>
        {proposals.length === 0 ? (
          <div className="muted">No EVOLVE self-development proposals queued.</div>
        ) : (
          proposals.map((p) => (
            <div key={p.proposal_id} className="list-item" style={{ marginBottom: 6 }}>
              <div className="row-between">
                <strong>{p.title}</strong>
                <span className="pill pill-cyan">{p.status}</span>
              </div>
              <div className="muted">Target: {p.target_module}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/* 18. Notifications */
export function NotificationsView() {
  const [items, setItems] = useState<any[]>([]);
  async function load() {
    const res = await apiFetch<any>("/api/v1/notifications");
    setItems(res.notifications || []);
  }
  useEffect(() => { load(); }, []);

  async function markRead(id: string) {
    await apiFetch(`/api/v1/notifications/${id}/read`, { method: "POST" });
    await load();
  }

  return (
    <div className="card">
      <div className="card-title">
        <span>Notifications ({items.filter((i) => !i.read).length} Unread)</span>
        <button className="btn btn-secondary btn-sm" onClick={load}>Refresh</button>
      </div>
      {items.length === 0 ? (
        <div className="muted">No notifications yet.</div>
      ) : (
        items.map((n) => (
          <div key={n.notification_id} className="list-item" style={{ marginBottom: 8 }}>
            <div className="row-between">
              <strong>{n.title}</strong>
              {!n.read && <button className="btn btn-secondary btn-sm" onClick={() => markRead(n.notification_id)}>Mark Read</button>}
            </div>
            <div className="muted">{n.message}</div>
          </div>
        ))
      )}
    </div>
  );
}

/* 19. User Settings (SENTINEL Passkeys/Face ID, Recovery Codes, OWNER Kill Switch, TURBO Benchmarks) */
export function SettingsView() {
  const [passkeys, setPasskeys] = useState<any[]>([]);
  const [codes, setCodes] = useState<string[]>([]);
  const [bench, setBench] = useState<any>(null);
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const pk = await apiFetch<any>("/api/v1/sentinel/passkeys");
    setPasskeys(pk.passkeys || []);
  }
  useEffect(() => { load(); }, []);

  async function registerPasskey() {
    setError("");
    setStatusMsg("");
    try {
      const optsRes = await apiFetch<any>("/api/v1/sentinel/passkeys/register/options", {
        method: "POST",
        body: { rp_id: window.location.hostname || "localhost" },
      });
      if (!window.PublicKeyCredential) {
        setError("WebAuthn Passkeys are not supported on this browser/origin (HTTPS required on iPhone Safari for Face ID).");
        return;
      }
      setStatusMsg(`WebAuthn challenge issued (${optsRes.challenge_id}). Ready for platform authenticator (Face ID / Touch ID / Windows Hello).`);
    } catch (e: any) {
      setError(e.message);
    }
  }

  async function genRecovery() {
    const res = await apiFetch<any>("/api/v1/sentinel/recovery-codes/generate", { method: "POST" });
    setCodes(res.codes || []);
  }

  async function runBench() {
    setBench(await apiFetch<any>("/api/v1/turbo/benchmarks?iterations=15", { method: "POST" }));
  }

  return (
    <div className="grid-2">
      <div className="card">
        <div className="card-title"><span>SENTINEL Passkeys (Face ID / Touch ID) & Recovery</span></div>
        <div className="muted" style={{ marginBottom: 10 }}>Zero raw biometric data is ever transmitted or stored server-side.</div>
        {statusMsg && <div className="alert-box" style={{ marginBottom: 8 }}>{statusMsg}</div>}
        {error && <div className="alert-box alert-error" style={{ marginBottom: 8 }}>{error}</div>}
        <div className="row" style={{ marginBottom: 12 }}>
          <button className="btn btn-sm" onClick={registerPasskey}>Register Face ID Passkey</button>
          <button className="btn btn-secondary btn-sm" onClick={genRecovery}>Generate Recovery Codes</button>
        </div>
        {codes.length > 0 && (
          <pre className="code-block" style={{ marginBottom: 10 }}>{codes.join("\n")}</pre>
        )}
        <div className="muted">Registered Passkeys: {passkeys.length}</div>
      </div>

      <div className="card">
        <div className="card-title"><span>TURBO Performance Benchmarks</span></div>
        <button className="btn btn-sm" style={{ marginBottom: 12 }} onClick={runBench}>Run Real Latency Benchmark</button>
        {bench ? (
          <pre className="code-block">{JSON.stringify(bench, null, 2)}</pre>
        ) : (
          <div className="muted">Run live micro-benchmarks to measure real DB, NEON routing, embedding, and AES-256-GCM latencies.</div>
        )}
      </div>
    </div>
  );
}
