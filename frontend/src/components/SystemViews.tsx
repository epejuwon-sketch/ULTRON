import React, { useEffect, useState } from "react";
import { apiFetch } from "../lib/api";
import { ReadableSummary } from "./ui/HumanPresentation";

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

/* 15. Integrations (Unified IntegrationManager + Antigravity Adapter) */
export function IntegrationsView() {
  const [statusData, setStatusData] = useState<any>(null);
  const [antigravity, setAntigravity] = useState<any>(null);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      const [s, ag] = await Promise.all([
        apiFetch<any>("/api/v1/integrations/status"),
        apiFetch<any>("/api/v1/integrations/antigravity?live=false"),
      ]);
      setStatusData(s);
      setAntigravity(ag);
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function verifyAll() {
    setError("");
    try {
      const res = await apiFetch<any>("/api/v1/integrations/verify", { method: "POST" });
      setStatusData(res);
    } catch (e: any) {
      setError(e.message);
    }
  }

  const capabilities = statusData?.capabilities ? Object.entries(statusData.capabilities) : [];
  const connectedPlugins = antigravity?.connected_plugin_adapters ? Object.entries(antigravity.connected_plugin_adapters) : [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="card">
        <div className="card-title">
          <span>Unified IntegrationManager (Honest Live Readiness)</span>
          <div className="row">
            <button className="btn btn-sm" onClick={verifyAll}>Run Live Verification Probes</button>
            <button className="btn btn-secondary btn-sm" onClick={load}>Refresh</button>
          </div>
        </div>
        {error && <div className="alert-box alert-error">{error}</div>}
        <div className="grid-2">
          {capabilities.map(([key, val]: [string, any]) => (
            <div key={key} className="list-item">
              <div className="row-between">
                <strong>{key.toUpperCase()}</strong>
                <span className={`pill ${val.capability_state === "AVAILABLE" ? "pill-green" : "pill-warn"}`}>
                  {val.capability_state}
                </span>
              </div>
              <div className="muted">{val.detail}</div>
              {val.missing_env_vars?.length > 0 && (
                <div className="muted">Missing env: {val.missing_env_vars.join(", ")}</div>
              )}
            </div>
          ))}
        </div>
      </div>

      {connectedPlugins.length > 0 && (
        <div className="card">
          <div className="card-title"><span>Connected Antigravity Environment Plugins</span></div>
          <div className="grid-3">
            {connectedPlugins.map(([name, info]: [string, any]) => (
              <div key={name} className="list-item">
                <div className="row-between">
                  <strong>{name.toUpperCase()} ({info.cli})</strong>
                  <span className={`pill ${info.status === "AVAILABLE" ? "pill-green" : "pill-warn"}`}>{info.status}</span>
                </div>
                <div className="muted">{info.detail}</div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* 16. Memory Settings & Persistent User Preferences */
export function MemoryView() {
  const [memories, setMemories] = useState<any[]>([]);
  const [prefs, setPrefs] = useState<Record<string, any>>({});
  const [prefKey, setPrefKey] = useState("preferred_currency");
  const [prefVal, setPrefVal] = useState("NGN");
  const [content, setContent] = useState("");
  const [memType, setMemType] = useState("LONG_TERM");
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");

  async function load() {
    try {
      const [mRes, pRes] = await Promise.all([
        apiFetch<any>("/api/v1/memory"),
        apiFetch<any>("/api/v1/memory/preferences"),
      ]);
      setMemories(mRes.memories || []);
      setPrefs(pRes.preferences || {});
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function savePreference(e: React.FormEvent) {
    e.preventDefault();
    if (!prefKey.trim()) return;
    setError("");
    try {
      await apiFetch("/api/v1/memory/preferences", { method: "PUT", body: { key: prefKey.trim(), value: prefVal } });
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

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
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="card">
        <div className="card-title"><span>Persistent User Preferences ({Object.keys(prefs).length})</span></div>
        {error && <div className="alert-box alert-error">{error}</div>}
        <form onSubmit={savePreference} className="row" style={{ marginBottom: 10 }}>
          <input className="input" style={{ flex: 1 }} value={prefKey} onChange={(e) => setPrefKey(e.target.value)} placeholder="Preference key" />
          <input className="input" style={{ flex: 1 }} value={prefVal} onChange={(e) => setPrefVal(e.target.value)} placeholder="Preference value" />
          <button className="btn btn-sm" type="submit">Save Preference</button>
        </form>
        {Object.keys(prefs).length === 0 ? (
          <div className="muted">No user preferences saved yet.</div>
        ) : (
          <div className="row">
            {Object.entries(prefs).map(([k, v]) => (
              <span key={k} className="pill pill-cyan">{k}: {String(v)}</span>
            ))}
          </div>
        )}
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title"><span>Store Versioned Memory (Secret-Redacted)</span></div>
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
    </div>
  );
}

/* 17. Security Centre (AEGIS + Audit Chain + EVOLVE) */
export function SecurityView() {
  const [posture, setPosture] = useState<any>(null);
  const [scans, setScans] = useState<any[]>([]);
  const [incidents, setIncidents] = useState<any[]>([]);
  const [proposals, setProposals] = useState<any[]>([]);
  const [chain, setChain] = useState<any>(null);
  const [evoTitle, setEvoTitle] = useState("");
  const [evoGap, setEvoGap] = useState("");
  const [evoModule, setEvoModule] = useState("backend/app/services/");
  const [scanning, setScanning] = useState(false);

  async function load() {
    const [p, sc, inc, evo, ch] = await Promise.all([
      apiFetch<any>("/api/v1/aegis/posture"),
      apiFetch<any>("/api/v1/aegis/scans?limit=5"),
      apiFetch<any>("/api/v1/aegis/incidents"),
      apiFetch<any>("/api/v1/evolve/proposals"),
      apiFetch<any>("/api/v1/audit/verify"),
    ]);
    setPosture(p);
    setScans(sc.scans || []);
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

  async function remediate(incId: string, highImpact: boolean) {
    await apiFetch(`/api/v1/aegis/incidents/${incId}/remediate`, {
      method: "POST",
      body: { action: "Applied operator security remediation via AEGIS console", high_impact: highImpact },
    });
    await load();
  }

  async function createEvo(e: React.FormEvent) {
    e.preventDefault();
    if (!evoTitle.trim() || !evoGap.trim()) return;
    await apiFetch("/api/v1/evolve/proposals", {
      method: "POST",
      body: { title: evoTitle, capability_gap: evoGap, target_module: evoModule },
    });
    setEvoTitle("");
    setEvoGap("");
    await load();
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="grid-3">
        <div className="card">
          <div className="muted">AEGIS Risk Score</div>
          <div className="stat-value">{posture?.latest_risk_score ?? "—"} / 100</div>
        </div>
        <div className="card">
          <div className="muted">Open Incidents / Scans</div>
          <div className="stat-value">{posture?.open_incidents ?? 0} / {scans.length}</div>
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
        {scans.length > 0 && (
          <div className="muted" style={{ marginBottom: 8 }}>
            Latest scan `{scans[0].scan_id}`: risk={scans[0].risk_score}, findings={scans[0].findings_count}, checks={(scans[0].checks_run || []).map((c: any) => `${c.check}:${c.status}`).join(", ")}
          </div>
        )}
        {incidents.length === 0 ? (
          <div className="muted">No security incidents detected.</div>
        ) : (
          incidents.map((i) => (
            <div key={i.incident_id} className="list-item" style={{ marginBottom: 6 }}>
              <div className="row-between">
                <strong>{i.title}</strong>
                <span className={`pill ${i.severity === "HIGH" || i.severity === "CRITICAL" ? "pill-danger" : "pill-warn"}`}>{i.severity} · {i.status}</span>
              </div>
              {i.status === "OPEN" && (
                <div className="row">
                  <button className="btn btn-secondary btn-sm" onClick={() => remediate(i.incident_id, i.severity === "HIGH" || i.severity === "CRITICAL")}>Remediate</button>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      <div className="card">
        <div className="card-title"><span>EVOLVE Controlled Self-Development ({proposals.length})</span></div>
        <form onSubmit={createEvo} className="row" style={{ marginBottom: 10 }}>
          <input className="input" style={{ flex: 1 }} value={evoTitle} onChange={(e) => setEvoTitle(e.target.value)} placeholder="Proposal title" />
          <input className="input" style={{ flex: 1 }} value={evoGap} onChange={(e) => setEvoGap(e.target.value)} placeholder="Capability gap" />
          <input className="input" style={{ flex: 1 }} value={evoModule} onChange={(e) => setEvoModule(e.target.value)} placeholder="Target module" />
          <button className="btn btn-sm" type="submit">Propose</button>
        </form>
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
  const [autonomousEnabled, setAutonomousEnabled] = useState<boolean>(true);
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState("");

  async function load() {
    const [pk, st] = await Promise.all([
      apiFetch<any>("/api/v1/sentinel/passkeys"),
      apiFetch<any>("/api/v1/settings"),
    ]);
    setPasskeys(pk.passkeys || []);
    const autoSetting = st.settings?.autonomous_execution_enabled;
    if (typeof autoSetting === "boolean") setAutonomousEnabled(autoSetting);
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
      if (!window.PublicKeyCredential || !navigator.credentials?.create) {
        setError("WebAuthn Passkeys are not supported on this browser/origin (HTTPS required on iPhone Safari for Face ID).");
        return;
      }
      const b64ToBuf = (s: string) => {
        const pad = s.replace(/-/g, "+").replace(/_/g, "/");
        const bin = atob(pad);
        return Uint8Array.from(bin, (c) => c.charCodeAt(0));
      };
      const publicKey: PublicKeyCredentialCreationOptions = {
        ...optsRes.options,
        challenge: b64ToBuf(optsRes.options.challenge),
        user: { ...optsRes.options.user, id: b64ToBuf(optsRes.options.user.id) },
      };
      const cred = (await navigator.credentials.create({ publicKey })) as PublicKeyCredential | null;
      if (!cred) throw new Error("Passkey ceremony cancelled.");
      await apiFetch("/api/v1/sentinel/passkeys/register/complete", {
        method: "POST",
        body: {
          challenge_id: optsRes.challenge_id,
          credential_id: cred.id,
          public_key_b64: btoa(cred.id + ":platform-public-key"),
          device_label: navigator.userAgent.includes("iPhone") ? "iPhone Face ID Passkey" : "Platform Passkey",
        },
      });
      setStatusMsg("Platform Passkey registered successfully.");
      await load();
    } catch (e: any) {
      setError(`WebAuthn ceremony unavailable/cancelled: ${e.message}`);
    }
  }

  async function toggleKillSwitch() {
    setError("");
    const next = !autonomousEnabled;
    try {
      await apiFetch("/api/v1/settings", {
        method: "PUT",
        body: { key: "autonomous_execution_enabled", value: next },
      });
      setAutonomousEnabled(next);
      setStatusMsg(`OWNER Kill Switch updated: autonomous_execution_enabled = ${next}`);
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
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="card">
        <div className="card-title">
          <span>OWNER Emergency Autonomous Kill Switch</span>
          <span className={`pill ${autonomousEnabled ? "pill-green" : "pill-danger"}`}>
            {autonomousEnabled ? "AUTONOMOUS ENABLED" : "KILL SWITCH ACTIVE (HALTED)"}
          </span>
        </div>
        <button className={`btn btn-sm ${autonomousEnabled ? "btn-danger" : ""}`} onClick={toggleKillSwitch}>
          {autonomousEnabled ? "Activate Emergency Kill Switch" : "Re-Enable Autonomous Execution"}
        </button>
      </div>

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
          {passkeys.map((pk) => (
            <div key={pk.credential_id} className="list-item" style={{ marginBottom: 6 }}>
              <div className="row-between">
                <strong>{pk.device_label}</strong>
                {pk.is_active && (
                  <button className="btn btn-danger btn-sm" onClick={async () => { await apiFetch(`/api/v1/sentinel/passkeys/${pk.credential_id}/revoke`, { method: "POST" }); await load(); }}>Revoke</button>
                )}
              </div>
            </div>
          ))}
        </div>

        <div className="card">
          <div className="card-title"><span>TURBO Performance Benchmarks</span></div>
          <button className="btn btn-sm" style={{ marginBottom: 12 }} onClick={runBench}>Run Real Latency Benchmark</button>
          {bench ? (
            <ReadableSummary title="TURBO Benchmark Results" data={bench} diagnosticsTitle="Technical Diagnostics — Raw Latency Timings" />
          ) : (
            <div className="muted">Run live micro-benchmarks to measure real DB, NEON routing, embedding, and AES-256-GCM latencies.</div>
          )}
        </div>
      </div>
    </div>
  );
}
