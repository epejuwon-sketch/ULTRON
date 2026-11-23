import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Database,
  Play,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Users,
} from "lucide-react";
import { apiFetch } from "../../lib/api";
import {
  ConfirmationDialog,
  DataTable,
  MetricDisplay,
  StatusIndicator,
  useToast,
} from "../ui/DesignSystem";

interface CaravanCommandCentreProps {
  onNavigateSubPage: (sub: string) => void;
}

export function CaravanCommandCentre({ onNavigateSubPage }: CaravanCommandCentreProps) {
  const { pushToast } = useToast();
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [days, setDays] = useState(30);
  const [search, setSearch] = useState("");
  const [reviewEvidence, setReviewEvidence] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    onConfirm: () => Promise<void>;
  } | null>(null);

  async function loadCommandCentre() {
    setLoading(true);
    setError("");
    try {
      const res = await apiFetch<any>(`/api/v1/caravan/command-centre?days=${days}`);
      setData(res);
    } catch (err: any) {
      const msg = err?.message || "Failed to load Caravan Command Centre.";
      setError(msg);
      pushToast(msg, "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadCommandCentre();
  }, [days]);

  const ov = data?.executive_overview || {};
  const neon = data?.neon_monitoring || {};
  const argon = data?.argon_monitoring || {};
  const fin = data?.financial_overview || {};
  const sup = data?.support_and_notifications || {};

  const filteredSources = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = data?.sources || [];
    if (!q) return list;
    return list.filter(
      (s: any) =>
        s.name.toLowerCase().includes(q) ||
        s.base_url.toLowerCase().includes(q) ||
        s.status.toLowerCase().includes(q)
    );
  }, [data, search]);

  const filteredTimeline = useMemo(() => {
    const q = search.trim().toLowerCase();
    const list = data?.activity_timeline || [];
    if (!q) return list;
    return list.filter(
      (l: any) =>
        l.action.toLowerCase().includes(q) ||
        (l.actor || "").toLowerCase().includes(q) ||
        (l.resource || "").toLowerCase().includes(q) ||
        (l.outcome || "").toLowerCase().includes(q)
    );
  }, [data, search]);

  if (loading && !data) {
    return (
      <div className="card muted" style={{ fontSize: 13 }}>
        Loading Caravan Command Centre telemetry...
      </div>
    );
  }

  if (error && !data) {
    return (
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <div style={{ color: "#f87171", fontSize: 13 }}>
          <AlertTriangle size={14} style={{ verticalAlign: "middle", marginRight: 4 }} />
          {error}
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={loadCommandCentre}>
          <RefreshCw size={12} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Executive Overview */}
      <div className="grid-4" style={{ gap: 10 }}>
        <MetricDisplay
          label="Sources (Healthy / Degraded)"
          value={`${ov.sources_total ?? 0} (${ov.sources_healthy ?? 0} / ${ov.sources_degraded ?? 0})`}
          sub={`${ov.sources_disabled ?? 0} Disabled`}
          tone={ov.sources_degraded > 0 ? "warn" : "info"}
        />
        <MetricDisplay
          label="Opportunities (Verified / Review)"
          value={`${ov.opportunities_total ?? 0} (${ov.verified_count ?? 0} / ${ov.awaiting_review_count ?? 0})`}
          sub={`Rejected ${ov.rejected_count ?? 0} · Expired ${ov.expired_count ?? 0} · Stale ${ov.stale_count ?? 0}`}
          tone="success"
        />
        <MetricDisplay
          label="Customers & Apps"
          value={`${ov.active_customers_count ?? 0} / ${ov.applications_count ?? 0}`}
          sub={`Saved ${ov.saved_opportunities_count ?? 0} · Open Tickets ${ov.open_support_tickets_count ?? 0}`}
          tone="info"
        />
        <MetricDisplay
          label="NEON & ARGON Ops"
          value={`${ov.neon_assessments_count ?? 0} / ${ov.argon_ingestions_count ?? 0}`}
          sub={`Checks ${ov.argon_source_checks_count ?? 0} · Payments ${fin.payment_integration_status || "NOT_CONNECTED"}`}
          tone="neutral"
        />
      </div>

      {/* Operational Alerts */}
      {Array.isArray(sup.operational_alerts) && sup.operational_alerts.length > 0 && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <strong style={{ fontSize: 13 }}>
            <AlertTriangle size={13} style={{ verticalAlign: "middle", marginRight: 4 }} />
            Operational Alerts ({sup.operational_alerts.length})
          </strong>
          {sup.operational_alerts.map((al: any, i: number) => (
            <div key={i} className="muted" style={{ fontSize: 12 }}>
              [{al.severity}] {al.message}
            </div>
          ))}
        </div>
      )}

      {/* Central Control Panel */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
          <div>
            <strong style={{ fontSize: 14 }}>
              <ShieldCheck size={14} style={{ verticalAlign: "middle", marginRight: 4 }} />
              Caravan Central Control Panel
            </strong>
            <div className="muted" style={{ fontSize: 12 }}>
              Authorized operational actions with SENTINEL RBAC, AEGIS approval gates, and audit logging.
            </div>
          </div>
          <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
            {[7, 30, 90].map((d) => (
              <button
                key={d}
                type="button"
                className={`btn btn-sm ${days === d ? "" : "btn-secondary"}`}
                onClick={() => setDays(d)}
              >
                {d}d
              </button>
            ))}
            <button type="button" className="btn btn-secondary btn-sm" onClick={loadCommandCentre} disabled={busy}>
              <RefreshCw size={12} /> Refresh
            </button>
          </div>
        </div>

        <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
          <button type="button" className="btn btn-sm" onClick={() => onNavigateSubPage("admin")}>
            <Play size={12} /> Open Discovery &amp; Verification Queue ({ov.awaiting_review_count ?? 0})
          </button>
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={busy}
            onClick={() =>
              setConfirmAction({
                title: "Sweep Expired Deadlines",
                message: "Mark all open opportunities whose deadline_at has passed as EXPIRED?",
                onConfirm: async () => {
                  setBusy(true);
                  try {
                    const res = await apiFetch<any>("/api/v1/caravan/opportunities/sweep-expired", { method: "POST" });
                    pushToast(`Expired sweep: ${res.expired_count} opportunity(s) marked EXPIRED.`, "info");
                    await loadCommandCentre();
                  } finally {
                    setBusy(false);
                  }
                },
              })
            }
          >
            Sweep Expired Deadlines
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={() => onNavigateSubPage("account")}>
            Support Cases ({ov.open_support_tickets_count ?? 0} Open)
          </button>
          <input
            className="input"
            style={{ minWidth: 200, flex: 1 }}
            placeholder="Filter sources or audit timeline..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
      </div>

      {/* Source Management */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <strong><Database size={14} /> Funding Source Management ({filteredSources.length})</strong>
        <DataTable
          rows={filteredSources}
          rowKey={(r: any) => r.source_id}
          emptyTitle="No Funding Sources Registered"
          emptyDescription="Register official Nigerian or international funding sources in Admin & Verification."
          columns={[
            {
              key: "name",
              header: "Source",
              render: (r: any) => (
                <div>
                  <strong>{r.name}</strong>
                  <div className="muted mono" style={{ fontSize: 11 }}>{r.base_url}</div>
                </div>
              ),
            },
            {
              key: "status",
              header: "Health",
              render: (r: any) => (
                <StatusIndicator
                  label={r.status}
                  tone={r.status === "ACTIVE" ? "success" : r.status === "DEGRADED" ? "warn" : "neutral"}
                />
              ),
            },
            {
              key: "checked",
              header: "Last Checked",
              render: (r: any) => <span className="muted mono" style={{ fontSize: 11 }}>{r.last_checked_at || "Never"}</span>,
            },
            {
              key: "actions",
              header: "Controls",
              render: (r: any) => (
                <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={busy || r.status === "DISABLED"}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        const res = await apiFetch<any>(`/api/v1/caravan/discovery/ingest/${r.source_id}`, { method: "POST" });
                        pushToast(`Ingested ${res.created_count} new (${res.duplicates_skipped} duplicates).`, "success");
                        await loadCommandCentre();
                      } catch (err: any) {
                        pushToast(err.message, "error");
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Ingest
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        const res = await apiFetch<any>(`/api/v1/caravan/sources/${r.source_id}/verify`, { method: "POST" });
                        pushToast(`Probe: ${res.detail}`, res.reachable ? "success" : "info");
                        await loadCommandCentre();
                      } catch (err: any) {
                        pushToast(err.message, "error");
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Probe
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    disabled={busy}
                    onClick={() => {
                      const nextEnabled = r.status === "DISABLED";
                      setConfirmAction({
                        title: `${nextEnabled ? "Enable" : "Disable"} Funding Source`,
                        message: `${nextEnabled ? "Enable" : "Disable"} '${r.name}' for ARGON discovery ingestion?`,
                        onConfirm: async () => {
                          setBusy(true);
                          try {
                            await apiFetch(`/api/v1/caravan/sources/${r.source_id}/toggle`, {
                              method: "POST",
                              body: { enabled: nextEnabled },
                            });
                            pushToast(`Source '${r.name}' ${nextEnabled ? "enabled" : "disabled"}.`, "info");
                            await loadCommandCentre();
                          } finally {
                            setBusy(false);
                          }
                        },
                      });
                    }}
                  >
                    {r.status === "DISABLED" ? "Enable" : "Disable"}
                  </button>
                </div>
              ),
            },
          ]}
        />
      </div>

      {/* Verification Queue */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <strong><CheckCircle2 size={14} /> Verification Queue ({(data?.verification_queue || []).length})</strong>
        <input
          className="input"
          placeholder="Supporting evidence or rejection reason (required for VERIFIED)"
          value={reviewEvidence}
          onChange={(e) => setReviewEvidence(e.target.value)}
        />
        <DataTable
          rows={data?.verification_queue || []}
          rowKey={(r: any) => r.opportunity_id}
          emptyTitle="Verification Queue Clear"
          emptyDescription="No discovered or unverified opportunities are currently awaiting review."
          columns={[
            {
              key: "title",
              header: "Opportunity",
              render: (r: any) => (
                <div>
                  <strong>{r.title}</strong>
                  <div className="muted" style={{ fontSize: 11 }}>{r.provider_org} · {r.funding_type}</div>
                </div>
              ),
            },
            {
              key: "status",
              header: "Stage",
              render: (r: any) => <StatusIndicator label={r.verification_status} tone="warn" />,
            },
            {
              key: "actions",
              header: "Review",
              render: (r: any) => (
                <div className="row" style={{ gap: 6 }}>
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        await apiFetch(`/api/v1/caravan/discovery/opportunities/${r.opportunity_id}/review`, {
                          method: "POST",
                          body: { decision: "VERIFIED", supporting_evidence: reviewEvidence.trim() },
                        });
                        pushToast(`Verified '${r.title}'.`, "success");
                        await loadCommandCentre();
                      } catch (err: any) {
                        pushToast(err.message, "error");
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Verify
                  </button>
                  <button
                    type="button"
                    className="btn btn-danger btn-sm"
                    disabled={busy}
                    onClick={async () => {
                      setBusy(true);
                      try {
                        await apiFetch(`/api/v1/caravan/discovery/opportunities/${r.opportunity_id}/review`, {
                          method: "POST",
                          body: { decision: "REJECTED", supporting_evidence: reviewEvidence.trim() || "Rejected in Command Centre." },
                        });
                        pushToast(`Rejected '${r.title}'.`, "info");
                        await loadCommandCentre();
                      } catch (err: any) {
                        pushToast(err.message, "error");
                      } finally {
                        setBusy(false);
                      }
                    }}
                  >
                    Reject
                  </button>
                </div>
              ),
            },
          ]}
        />
      </div>

      {/* NEON, ARGON & Financial Read-Only Row */}
      <div className="grid-2" style={{ gap: 10 }}>
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
          <strong><Sparkles size={13} /> NEON &amp; ARGON Monitoring</strong>
          <div>
            <strong>NEON Gemini Configured:</strong>{" "}
            <StatusIndicator label={neon.gemini_configured ? "CONFIGURED" : "DETERMINISTIC FALLBACK"} tone={neon.gemini_configured ? "success" : "info"} />
          </div>
          <div><strong>Total NEON Assessments:</strong> {neon.total_assessments ?? 0}</div>
          <div><strong>ARGON Ingestions / Checks:</strong> {argon.total_ingestions ?? 0} / {argon.total_source_checks ?? 0}</div>
          <div><strong>ARGON Failed Probes:</strong> {argon.failed_source_checks ?? 0}</div>
          <div><strong>AEGIS Pending Approvals:</strong> {argon.pending_aegis_approvals ?? 0}</div>
        </div>

        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
          <strong>Financial Overview (Read-Only)</strong>
          <div>
            <strong>Payment Integration:</strong>{" "}
            <StatusIndicator
              label={fin.payment_integration_status || "NOT_CONNECTED"}
              tone={fin.payment_integration_status === "CONNECTED" ? "success" : "warn"}
            />
          </div>
          <div><strong>Live Payments Enabled:</strong> {String(Boolean(fin.live_payments_enabled))}</div>
          <div><strong>Subscription Records:</strong> {fin.subscription_records_count ?? 0}</div>
          <div><strong>Actual Recorded Revenue:</strong> \${Number(fin.actual_revenue_usd || 0).toFixed(2)}</div>
          <div className="muted" style={{ fontSize: 11 }}>
            Financial execution, transfers, and live billing are disabled until explicitly authorized.
          </div>
        </div>
      </div>

      {/* Customer Operations */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <strong><Users size={14} /> Customer Operations ({(data?.customer_operations || []).length})</strong>
        <DataTable
          rows={data?.customer_operations || []}
          rowKey={(r: any) => r.account_id}
          emptyTitle="No Customer Accounts Yet"
          emptyDescription="Customer accounts appear here after onboarding in Caravan."
          columns={[
            { key: "org", header: "Organization", render: (r: any) => <strong>{r.organization_name}</strong> },
            { key: "loc", header: "Market / Sector", render: (r: any) => <span className="muted">{r.country} · {r.sector}</span> },
            { key: "tier", header: "Plan", render: (r: any) => <span className="pill mono">{r.plan_tier}</span> },
            {
              key: "usage",
              header: "Usage (NEON / Saved / Apps)",
              render: (r: any) => <span className="mono">{r.assessments_count} / {r.saved_count} / {r.applications_count}</span>,
            },
          ]}
        />
      </div>

      {/* Activity Timeline */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <strong><Activity size={14} /> Chronological Activity Timeline ({filteredTimeline.length})</strong>
        <DataTable
          rows={filteredTimeline}
          rowKey={(r: any) => String(r.id)}
          emptyTitle="No Audit Events in Window"
          emptyDescription="Caravan operational events and audit logs will appear here."
          columns={[
            { key: "ts", header: "Timestamp", render: (r: any) => <span className="muted mono" style={{ fontSize: 11 }}>{r.timestamp}</span> },
            { key: "actor", header: "Actor", render: (r: any) => <span className="mono">{r.actor}</span> },
            { key: "action", header: "Action", render: (r: any) => <span className="pill mono">{r.action}</span> },
            { key: "outcome", header: "Outcome", render: (r: any) => <span className="muted" style={{ fontSize: 11 }}>{r.outcome}</span> },
          ]}
        />
      </div>

      <ConfirmationDialog
        open={Boolean(confirmAction)}
        title={confirmAction?.title || "Confirm Action"}
        message={confirmAction?.message || ""}
        onCancel={() => setConfirmAction(null)}
        onConfirm={async () => {
          const fn = confirmAction?.onConfirm;
          setConfirmAction(null);
          if (fn) await fn();
        }}
      />
    </div>
  );
}
