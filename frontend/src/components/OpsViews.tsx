import React, { useEffect, useState } from "react";
import { apiFetch, downloadAuthFile } from "../lib/api";

/* 8. Creative Studio + Photo/Video Upload & Visual Multimodal */
export function CreativeView() {
  const [jobs, setJobs] = useState<any[]>([]);
  const [mediaType, setMediaType] = useState("GRAPHIC");
  const [prompt, setPrompt] = useState("");
  const [visualResult, setVisualResult] = useState<any>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      const res = await apiFetch<any>("/api/v1/creative/jobs");
      setJobs(res.jobs || []);
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function createJob(e: React.FormEvent) {
    e.preventDefault();
    if (!prompt.trim()) return;
    setError("");
    try {
      await apiFetch("/api/v1/creative/jobs", { method: "POST", body: { media_type: mediaType, prompt } });
      setPrompt("");
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function handleMediaCapture(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setError("");
    if (f.type.startsWith("video/")) {
      const fd = new FormData();
      fd.append("file", f);
      try {
        const up = await apiFetch<any>("/api/v1/files/upload", { method: "POST", body: fd, isFormData: true });
        setVisualResult({
          status: "VIDEO_STORED_IN_FILE_HUB",
          file_id: up.file_id,
          filename: up.filename,
          size_bytes: up.size_bytes,
          note: "Video uploaded and SHA-256 verified in File Hub. Configure GEMINI_API_KEY for live multimodal video frame understanding.",
        });
      } catch (err: any) {
        setError(err.message);
      }
      return;
    }

    const reader = new FileReader();
    reader.onload = async () => {
      const b64 = String(reader.result || "").split(",")[1] || "";
      try {
        const res = await apiFetch<any>("/api/v1/creative/visual/analyze", {
          method: "POST",
          body: { prompt: "Analyze this visual frame for ULTRON.", image_base64: b64, mime_type: f.type || "image/png", source: "camera" },
        });
        setVisualResult(res);
      } catch (err: any) {
        setError(err.message);
      }
    };
    reader.readAsDataURL(f);
  }

  return (
    <div className="grid-2">
      <div className="card">
        <div className="card-title"><span>Creative Studio & Photo/Video Multimodal</span></div>
        {error && <div className="alert-box alert-error">{error}</div>}
        <form onSubmit={createJob} style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 14 }}>
          <select className="select" value={mediaType} onChange={(e) => setMediaType(e.target.value)}>
            <option value="GRAPHIC">Graphic / Brand Vector (AGT-43)</option>
            <option value="IMAGE">Image Concept (AGT-13)</option>
            <option value="3D">3D Scene Spec (AGT-24)</option>
            <option value="PRESENTATION">Presentation Deck (AGT-44)</option>
            <option value="VIDEO">Video Storyboard (AGT-14)</option>
            <option value="AUDIO">Audio Production Plan (AGT-45)</option>
          </select>
          <textarea className="textarea" rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Describe the visual, 3D scene, deck, or media workflow..." />
          <button className="btn" type="submit">Create Studio Job</button>
        </form>
        <label className="btn btn-secondary" style={{ width: "100%" }}>
          Capture / Upload Photo or Video (iPhone Camera &amp; Library)
          <input type="file" accept="image/*,video/*" style={{ display: "none" }} onChange={handleMediaCapture} />
        </label>
        {visualResult && <pre className="code-block" style={{ marginTop: 10 }}>{JSON.stringify(visualResult, null, 2)}</pre>}
      </div>

      <div className="card">
        <div className="card-title"><span>Studio Jobs ({jobs.length})</span></div>
        {jobs.length === 0 ? (
          <div className="muted">No Creative Studio jobs created yet.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {jobs.map((j) => (
              <div key={j.job_id} className="list-item">
                <div className="row-between">
                  <strong>{j.media_type} · {j.agent_id}</strong>
                  <span className={`pill ${j.status === "COMPLETED" ? "pill-green" : "pill-warn"}`}>{j.status}</span>
                </div>
                <div className="muted">{j.prompt}</div>
                {j.result?.download_url && (
                  <button
                    className="btn btn-secondary btn-sm"
                    onClick={() => downloadAuthFile(j.result.download_url, `studio_${j.job_id}`).catch((e) => setError(e.message))}
                  >
                    Download Artifact
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* 9. Finance Centre (Business/Personal Separation + Tokenized Payment Methods + Ledger + Forecast) */
export function FinanceView() {
  const [scope, setScope] = useState<string>("");
  const [summary, setSummary] = useState<any>(null);
  const [txs, setTxs] = useState<any[]>([]);
  const [methods, setMethods] = useState<any[]>([]);
  const [forecast, setForecast] = useState<any>(null);
  const [txType, setTxType] = useState("REVENUE");
  const [category, setCategory] = useState("saas");
  const [amount, setAmount] = useState("100");
  const [desc, setDesc] = useState("");
  const [txScope, setTxScope] = useState("BUSINESS");
  const [brand, setBrand] = useState("VERVE");
  const [last4, setLast4] = useState("4242");
  const [tokenRef, setTokenRef] = useState("AUTH_tok_paystack_001");
  const [error, setError] = useState("");

  async function load() {
    try {
      const qs = scope ? `?scope=${scope}` : "";
      const [s, t, pm, fc] = await Promise.all([
        apiFetch<any>(`/api/v1/finance/reports/summary${qs}`),
        apiFetch<any>(`/api/v1/finance/transactions${qs}`),
        apiFetch<any>(`/api/v1/finance/payment-methods${qs}`),
        apiFetch<any>("/api/v1/finance/forecast?months=3"),
      ]);
      setSummary(s);
      setTxs(t.transactions || []);
      setMethods(pm.payment_methods || []);
      setForecast(fc);
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => { load(); }, [scope]);

  async function recordTx(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await apiFetch("/api/v1/finance/transactions", {
        method: "POST",
        body: { entry_type: txType, category, amount_usd: Number(amount), description: desc || `${txType} entry`, scope: txScope },
      });
      setDesc("");
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function addCard(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await apiFetch("/api/v1/finance/payment-methods", {
        method: "POST",
        body: {
          provider: "paystack",
          provider_token_ref: tokenRef,
          brand,
          last4,
          exp_month: 12,
          exp_year: 2028,
          scope: txScope,
          is_preferred: true,
        },
      });
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="row-between">
        <div className="row">
          <button className={`btn btn-sm ${scope === "" ? "" : "btn-secondary"}`} onClick={() => setScope("")}>All Accounts</button>
          <button className={`btn btn-sm ${scope === "BUSINESS" ? "" : "btn-secondary"}`} onClick={() => setScope("BUSINESS")}>Business</button>
          <button className={`btn btn-sm ${scope === "PERSONAL" ? "" : "btn-secondary"}`} onClick={() => setScope("PERSONAL")}>Personal</button>
        </div>
        <span className="pill pill-warn">PCI Guard: Tokenized Masked Cards Only (No Raw PAN/CVV)</span>
      </div>
      {error && <div className="alert-box alert-error">{error}</div>}

      {summary && (
        <div className="grid-3">
          <div className="card"><div className="muted">Total Revenue</div><div className="stat-value">${summary.total_revenue_usd}</div></div>
          <div className="card"><div className="muted">Total Expenses</div><div className="stat-value">${summary.total_expenses_usd}</div></div>
          <div className="card"><div className="muted">Net Income</div><div className="stat-value">${summary.net_income_usd}</div></div>
        </div>
      )}

      <div className="grid-2">
        <div className="card">
          <div className="card-title"><span>Record Ledger Transaction</span></div>
          <form onSubmit={recordTx} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="row">
              <select className="select" style={{ flex: 1 }} value={txType} onChange={(e) => setTxType(e.target.value)}>
                <option value="REVENUE">REVENUE</option>
                <option value="EXPENSE">EXPENSE</option>
                <option value="HOSTING">HOSTING</option>
                <option value="API_SPEND">API_SPEND</option>
                <option value="OWNER_DISTRIBUTION">OWNER_DISTRIBUTION (ApprovalGate)</option>
              </select>
              <select className="select" style={{ width: 130 }} value={txScope} onChange={(e) => setTxScope(e.target.value)}>
                <option value="BUSINESS">BUSINESS</option>
                <option value="PERSONAL">PERSONAL</option>
              </select>
            </div>
            <div className="row">
              <input className="input" style={{ flex: 1 }} value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Category" />
              <input className="input" style={{ width: 120 }} type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="USD" />
            </div>
            <input className="input" value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="Description" />
            <button className="btn" type="submit">Record Transaction</button>
          </form>
        </div>

        <div className="card">
          <div className="card-title"><span>Tokenized Payment Methods ({methods.length})</span></div>
          <form onSubmit={addCard} className="row" style={{ marginBottom: 10 }}>
            <select className="select" style={{ width: 130 }} value={brand} onChange={(e) => setBrand(e.target.value)}>
              <option value="VERVE">VERVE</option>
              <option value="VISA">VISA</option>
              <option value="MASTERCARD">MASTERCARD</option>
              <option value="AMEX">AMEX</option>
            </select>
            <input className="input" style={{ width: 85 }} maxLength={4} value={last4} onChange={(e) => setLast4(e.target.value)} placeholder="Last 4" />
            <input className="input" style={{ flex: 1 }} value={tokenRef} onChange={(e) => setTokenRef(e.target.value)} placeholder="Provider Token Ref" />
            <button className="btn btn-sm" type="submit">Add Token</button>
          </form>
          {methods.length === 0 ? (
            <div className="muted">No tokenized payment methods stored yet.</div>
          ) : (
            methods.map((pm) => (
              <div key={pm.payment_method_id} className="list-item" style={{ marginBottom: 6 }}>
                <div className="row-between">
                  <strong>{pm.brand} {pm.masked_number}</strong>
                  <span className="pill pill-cyan">{pm.scope}</span>
                </div>
                <div className="muted">{pm.provider} · Exp {pm.exp_month}/{pm.exp_year} {pm.is_preferred ? "· PREFERRED" : ""}</div>
                <div className="row">
                  {!pm.is_preferred && (
                    <button className="btn btn-secondary btn-sm" onClick={async () => { await apiFetch(`/api/v1/finance/payment-methods/${pm.payment_method_id}/preferred`, { method: "PATCH" }); await load(); }}>Set Preferred</button>
                  )}
                  <button className="btn btn-danger btn-sm" onClick={async () => { await apiFetch(`/api/v1/finance/payment-methods/${pm.payment_method_id}`, { method: "DELETE" }); await load(); }}>Remove</button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title"><span>Recorded Ledger Entries ({txs.length})</span></div>
          {txs.length === 0 ? (
            <div className="muted">No ledger entries recorded yet.</div>
          ) : (
            txs.slice(0, 8).map((t) => (
              <div key={t.tx_id} className="list-item" style={{ marginBottom: 6 }}>
                <div className="row-between">
                  <strong>{t.entry_type} · ${t.amount_usd}</strong>
                  <span className="pill pill-cyan">{t.scope} · {t.status}</span>
                </div>
                <div className="muted">{t.category} — {t.description}</div>
              </div>
            ))
          )}
        </div>

        {forecast && (
          <div className="card">
            <div className="card-title"><span>3-Month Cash-Flow Projection (Recorded Ledger Only)</span></div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {(forecast.projections || []).map((p: any) => (
                <div key={p.month_offset} className="list-item">
                  <strong>Month +{p.month_offset}</strong>
                  <div className="muted">Projected Net: ${p.projected_net_usd} · Reserve: ${p.projected_reserve_balance_usd}</div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* 10. VAULT Encrypted Secrets */
export function VaultView() {
  const [secrets, setSecrets] = useState<any[]>([]);
  const [name, setName] = useState("");
  const [value, setValue] = useState("");
  const [provider, setProvider] = useState("custom");
  const [error, setError] = useState("");

  async function load() {
    try {
      const res = await apiFetch<any>("/api/v1/vault/secrets");
      setSecrets(res.secrets || []);
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function store(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !value.trim()) return;
    setError("");
    try {
      await apiFetch("/api/v1/vault/secrets", { method: "POST", body: { name, value, provider } });
      setName("");
      setValue("");
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function remove(secretName: string) {
    await apiFetch(`/api/v1/vault/secrets/${encodeURIComponent(secretName)}`, { method: "DELETE" });
    await load();
  }

  return (
    <div className="grid-2">
      <div className="card">
        <div className="card-title"><span>VAULT — Store AES-256-GCM Secret</span></div>
        {error && <div className="alert-box alert-error">{error}</div>}
        <form onSubmit={store} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Secret Name (e.g., STRIPE_WEBHOOK_KEY)" />
          <input className="input" type="password" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Secret Value (encrypted at rest, never echoed)" />
          <input className="input" value={provider} onChange={(e) => setProvider(e.target.value)} placeholder="Provider tag" />
          <button className="btn" type="submit">Encrypt & Store in VAULT</button>
        </form>
      </div>
      <div className="card">
        <div className="card-title"><span>Encrypted Vault Entries ({secrets.length})</span></div>
        {secrets.length === 0 ? (
          <div className="muted">No secrets stored yet. Secrets intercepted in JARVIS chat are automatically encrypted here.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {secrets.map((s) => (
              <div key={s.name} className="list-item">
                <div className="row-between">
                  <strong>{s.name}</strong>
                  <button className="btn btn-danger btn-sm" onClick={() => remove(s.name)}>Delete</button>
                </div>
                <div className="muted">Provider: {s.provider} · Updated: {s.updated_at}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* 11. ATLAS World Map + Authorized ORBIT Locations + Weather + 9-Status Order Tracker */
const ORDER_STATUSES = [
  "PLACED", "PROCESSING", "SHIPPED", "IN_TRANSIT", "OUT_FOR_DELIVERY", "DELIVERED", "DELAYED", "RETURNED", "CANCELLED"
];

export function AtlasMapView() {
  const [locations, setLocations] = useState<any[]>([]);
  const [orders, setOrders] = useState<any[]>([]);
  const [weather, setWeather] = useState<any>(null);
  const [vendor, setVendor] = useState("");
  const [itemSummary, setItemSummary] = useState("");
  const [amount, setAmount] = useState("50");
  const [error, setError] = useState("");

  async function load() {
    try {
      const [locRes, ordRes, wRes] = await Promise.all([
        apiFetch<any>("/api/v1/devices/locations"),
        apiFetch<any>("/api/v1/atlas/orders"),
        apiFetch<any>("/api/v1/atlas/intelligence/weather?latitude=6.5244&longitude=3.3792&city=Lagos"),
      ]);
      setLocations(locRes.locations || []);
      setOrders(ordRes.orders || []);
      setWeather(wRes);
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => { load(); }, []);

  async function createOrder(e: React.FormEvent) {
    e.preventDefault();
    if (!vendor.trim() || !itemSummary.trim()) return;
    setError("");
    try {
      await apiFetch("/api/v1/atlas/orders", {
        method: "POST",
        body: { vendor, item_summary: itemSummary, amount_usd: Number(amount), require_purchase_approval: true },
      });
      setVendor("");
      setItemSummary("");
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  async function updateOrderStatus(orderId: string, nextStatus: string) {
    setError("");
    try {
      await apiFetch(`/api/v1/atlas/orders/${orderId}/tracking`, {
        method: "PATCH",
        body: { status: nextStatus, tracking_source: "USER_RECORDED", note: `Updated to ${nextStatus} via Atlas UI` },
      });
      await load();
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="card">
        <div className="card-title">
          <span>ATLAS World Projection & Authorized ORBIT Device Locations</span>
          {weather && (
            <span className={`pill ${weather.status === "LIVE" ? "pill-green" : "pill-warn"}`}>
              {weather.city}: {weather.status === "LIVE" ? `${weather.temperature_c}°C` : "Weather Offline"}
            </span>
          )}
        </div>
        {error && <div className="alert-box alert-error">{error}</div>}
        <svg viewBox="0 0 720 320" style={{ width: "100%", height: "auto", background: "#090f1c", borderRadius: 10, border: "1px solid #2c3b52" }}>
          <line x1="0" y1="160" x2="720" y2="160" stroke="#1e293b" strokeDasharray="4 4" />
          <line x1="360" y1="0" x2="360" y2="320" stroke="#1e293b" strokeDasharray="4 4" />
          <text x="14" y="24" fill="#64748b" fontSize="11">EQUIRECTANGULAR PROJECTION // AUTHORIZED ORBIT PINS ONLY</text>
          {locations.map((loc) => {
            const x = ((loc.longitude + 180) / 360) * 720;
            const y = ((90 - loc.latitude) / 180) * 320;
            return (
              <g key={loc.location_id}>
                <circle cx={x} cy={y} r="7" fill="#06b6d4" opacity="0.3" />
                <circle cx={x} cy={y} r="3.5" fill="#22d3ee" />
                <text x={x + 8} y={y + 4} fill="#e2e8f0" fontSize="10">{loc.city || loc.device_id}</text>
              </g>
            );
          })}
        </svg>
        {locations.length === 0 && <div className="muted" style={{ marginTop: 8 }}>No authorized device locations recorded yet. Pair a device with location permission in Device Centre.</div>}
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title"><span>ATLAS Purchase Order (ApprovalGate Protected)</span></div>
          <form onSubmit={createOrder} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <input className="input" value={vendor} onChange={(e) => setVendor(e.target.value)} placeholder="Vendor" />
            <input className="input" value={itemSummary} onChange={(e) => setItemSummary(e.target.value)} placeholder="Item summary" />
            <input className="input" type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Amount USD" />
            <button className="btn" type="submit">Prepare Order & Request Approval</button>
          </form>
        </div>

        <div className="card">
          <div className="card-title"><span>9-Status Order Tracking ({orders.length})</span></div>
          {orders.length === 0 ? (
            <div className="muted">No orders recorded yet. Tracking is never fabricated.</div>
          ) : (
            orders.map((o) => (
              <div key={o.order_id} className="list-item" style={{ marginBottom: 6 }}>
                <div className="row-between">
                  <strong>{o.vendor} — {o.item_summary}</strong>
                  <select className="select" style={{ width: 170 }} value={o.status} onChange={(e) => updateOrderStatus(o.order_id, e.target.value)}>
                    {ORDER_STATUSES.map((st) => <option key={st} value={st}>{st}</option>)}
                  </select>
                </div>
                <div className="muted">${o.amount_usd} {o.currency} · Source: {o.tracking_source}</div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

/* 12. News & World Intelligence Daily Briefing */
export function IntelligenceView() {
  const [topics, setTopics] = useState<any[]>([]);
  const [briefings, setBriefings] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  async function load() {
    const [t, b] = await Promise.all([
      apiFetch<any>("/api/v1/atlas/intelligence/topics"),
      apiFetch<any>("/api/v1/atlas/briefings"),
    ]);
    setTopics(t.topics || []);
    setBriefings(b.briefings || []);
  }
  useEffect(() => { load(); }, []);

  async function toggleTopic(t: any) {
    await apiFetch("/api/v1/atlas/intelligence/topics", {
      method: "PUT",
      body: { slug: t.slug, label: t.label, region: t.region, enabled: !t.enabled, priority: t.priority },
    });
    await load();
  }

  async function generate(live: boolean) {
    setLoading(true);
    try {
      await apiFetch("/api/v1/atlas/briefings/generate", { method: "POST", body: { include_live_fetch: live } });
      await load();
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid-2">
      <div className="card">
        <div className="card-title"><span>Configured Briefing Topics</span></div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {topics.map((t) => (
            <div key={t.topic_id} className="list-item">
              <div className="row-between">
                <span><strong>{t.label}</strong> <span className="muted">({t.region})</span></span>
                <button className={`btn btn-sm ${t.enabled ? "" : "btn-secondary"}`} onClick={() => toggleTopic(t)}>
                  {t.enabled ? "Enabled" : "Disabled"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <div className="card-title">
          <span>Daily Briefings ({briefings.length})</span>
          <div className="row">
            <button className="btn btn-sm" disabled={loading} onClick={() => generate(true)}>Generate (Live)</button>
            <button className="btn btn-secondary btn-sm" disabled={loading} onClick={() => generate(false)}>Snapshot</button>
          </div>
        </div>
        {briefings.length === 0 ? (
          <div className="muted">No briefings generated yet. Click Generate to build today's briefing from real sources.</div>
        ) : (
          briefings.slice(0, 3).map((b) => (
            <div key={b.briefing_id} className="list-item" style={{ marginBottom: 8 }}>
              <strong>Briefing {b.briefing_date}</strong>
              <div className="muted">Topics: {(b.topics || []).join(", ")} · Sources cited: {(b.sources || []).length}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/* 13. CARAVAN Business Intelligence & PULSE Live Pages */
export function CaravanView() {
  const [summary, setSummary] = useState<any>(null);
  const [pages, setPages] = useState<any[]>([]);
  const [liveData, setLiveData] = useState<any>(null);
  const [eventType, setEventType] = useState("SIGNUP");
  const [country, setCountry] = useState("Nigeria");
  const [city, setCity] = useState("Lagos");
  const [amount, setAmount] = useState("0");
  const [pageTitle, setPageTitle] = useState("Caravan Growth Live");
  const [pageType, setPageType] = useState("CARAVAN");

  async function load() {
    const [s, p] = await Promise.all([
      apiFetch<any>("/api/v1/caravan/summary"),
      apiFetch<any>("/api/v1/pulse/pages"),
    ]);
    setSummary(s);
    setPages(p.pages || []);
  }
  useEffect(() => { load(); }, []);

  async function recordEvent(e: React.FormEvent) {
    e.preventDefault();
    await apiFetch("/api/v1/caravan/events", {
      method: "POST",
      body: { event_type: eventType, country, city, amount_usd: Number(amount), count_value: 1 },
    });
    await load();
  }

  async function createPulse(e: React.FormEvent) {
    e.preventDefault();
    const res = await apiFetch<any>("/api/v1/pulse/pages", { method: "POST", body: { title: pageTitle, page_type: pageType } });
    setLiveData(await apiFetch(`/api/v1/pulse/pages/${res.page_id}/live`));
    await load();
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="card">
        <div className="card-title">
          <span>CARAVAN Business Intelligence</span>
          <span className="pill pill-cyan">{summary?.has_data ? "LIVE RECORDED DATA" : "EMPTY STATE (ZERO MOCKS)"}</span>
        </div>
        {!summary?.has_data ? (
          <div className="muted">{summary?.empty_state || "No analytics events recorded yet."}</div>
        ) : (
          <div className="grid-3">
            <div className="list-item"><div className="muted">Signups</div><div className="stat-value">{summary.totals.signups}</div></div>
            <div className="list-item"><div className="muted">Conversion Rate</div><div className="stat-value">{summary.totals.conversion_rate_pct}%</div></div>
            <div className="list-item"><div className="muted">Revenue</div><div className="stat-value">${summary.totals.revenue_usd}</div></div>
          </div>
        )}
      </div>

      <div className="grid-2">
        <div className="card">
          <div className="card-title"><span>Ingest Verified Caravan Event</span></div>
          <form onSubmit={recordEvent} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <select className="select" value={eventType} onChange={(e) => setEventType(e.target.value)}>
              <option value="SIGNUP">SIGNUP</option>
              <option value="ACTIVE_USER">ACTIVE_USER</option>
              <option value="CONVERSION">CONVERSION</option>
              <option value="GRANT_APPLICATION">GRANT_APPLICATION</option>
              <option value="REVENUE">REVENUE</option>
            </select>
            <div className="row">
              <input className="input" style={{ flex: 1 }} value={country} onChange={(e) => setCountry(e.target.value)} placeholder="Country" />
              <input className="input" style={{ flex: 1 }} value={city} onChange={(e) => setCity(e.target.value)} placeholder="City" />
            </div>
            <input className="input" type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Revenue USD (if REVENUE)" />
            <button className="btn" type="submit">Record Event</button>
          </form>
        </div>

        <div className="card">
          <div className="card-title"><span>PULSE Live Data-Backed Pages ({pages.length})</span></div>
          <form onSubmit={createPulse} className="row" style={{ marginBottom: 10 }}>
            <input className="input" style={{ flex: 1 }} value={pageTitle} onChange={(e) => setPageTitle(e.target.value)} />
            <select className="select" style={{ width: 130 }} value={pageType} onChange={(e) => setPageType(e.target.value)}>
              <option value="CARAVAN">CARAVAN</option>
              <option value="FINANCE">FINANCE</option>
              <option value="ORDERS">ORDERS</option>
              <option value="AGENTS">AGENTS</option>
            </select>
            <button className="btn btn-sm" type="submit">Create</button>
          </form>
          {pages.map((p) => (
            <div key={p.page_id} className="list-item" style={{ marginBottom: 6 }}>
              <div className="row-between">
                <strong>{p.title} ({p.page_type})</strong>
                <button className="btn btn-secondary btn-sm" onClick={async () => setLiveData(await apiFetch(`/api/v1/pulse/pages/${p.page_id}/live`))}>Hydrate Live</button>
              </div>
            </div>
          ))}
          {liveData && (
            <div style={{ marginTop: 10 }}>
              <div className="muted">Live DB Hydration ({liveData.page?.title} · {liveData.hydrated_at}):</div>
              <pre className="code-block">{JSON.stringify(liveData.live_data, null, 2)}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
