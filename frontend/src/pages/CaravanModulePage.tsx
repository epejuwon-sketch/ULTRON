import React, { useEffect, useState } from "react";
import {
  Bookmark,
  CheckCircle2,
  ClipboardList,
  Compass,
  ExternalLink,
  Plus,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  UserCheck,
} from "lucide-react";
import { apiFetch, CARAVAN_DEPLOYED_URL } from "../lib/api";
import { CaravanCommandCentre } from "../components/caravan/CaravanCommandCentre";
import { DataTable, Drawer, MetricDisplay, StatusIndicator, useToast } from "../components/ui/DesignSystem";

interface ModulePageProps {
  subPage: string;
  onSelectSubPage: (sub: string) => void;
}

function verificationTone(status: string): "success" | "warn" | "danger" | "neutral" {
  switch (status) {
    case "VERIFIED":
      return "success";
    case "UNVERIFIED":
      return "warn";
    case "EXPIRED":
    case "CLOSED":
      return "danger";
    default:
      return "neutral";
  }
}

export default function CaravanModulePage({ subPage, onSelectSubPage }: ModulePageProps) {
  const { pushToast } = useToast();
  const [overview, setOverview] = useState<any>(null);
  const [opportunities, setOpportunities] = useState<any[]>([]);
  const [recommendations, setRecommendations] = useState<any[]>([]);
  const [assessments, setAssessments] = useState<any[]>([]);
  const [applications, setApplications] = useState<any[]>([]);
  const [saved, setSaved] = useState<any[]>([]);
  const [tickets, setTickets] = useState<any[]>([]);
  const [notifications, setNotifications] = useState<any[]>([]);
  const [sources, setSources] = useState<any[]>([]);
  const [selectedOpp, setSelectedOpp] = useState<any>(null);

  // Filters & forms
  const [query, setQuery] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [geoFilter, setGeoFilter] = useState("");
  const [openDeadlinesOnly, setOpenDeadlinesOnly] = useState(false);

  // Create opportunity form (Admin)
  const [newTitle, setNewTitle] = useState("");
  const [newProvider, setNewProvider] = useState("");
  const [newType, setNewType] = useState("GRANT");
  const [newUrl, setNewUrl] = useState("");
  const [newReqs, setNewReqs] = useState("");
  const [newGeo, setNewGeo] = useState("Nigeria / Africa");
  const [newAmount, setNewAmount] = useState("");
  const [verifyEvidence, setVerifyEvidence] = useState("");

  // Account & Support forms
  const [orgName, setOrgName] = useState("");
  const [entityType, setEntityType] = useState("STARTUP");
  const [country, setCountry] = useState("Nigeria");
  const [stateLocation, setStateLocation] = useState("");
  const [sector, setSector] = useState("Technology");
  const [stage, setStage] = useState("SEED");
  const [fundingGoals, setFundingGoals] = useState("");
  const [selectedApp, setSelectedApp] = useState<any>(null);
  const [appNotes, setAppNotes] = useState("");
  const [newDocItem, setNewDocItem] = useState("");
  const [ticketSubject, setTicketSubject] = useState("");
  const [ticketMessage, setTicketMessage] = useState("");
  const [sourceName, setSourceName] = useState("");
  const [sourceUrl, setSourceUrl] = useState("");
  const [sourceType, setSourceType] = useState("PUBLIC_PORTAL");
  const [adminStageFilter, setAdminStageFilter] = useState("ALL");
  const [pricing, setPricing] = useState<any>(null);
  const [privacy, setPrivacy] = useState<any>(null);
  const [notifPrefs, setNotifPrefs] = useState<any>(null);

  async function loadAll() {
    try {
      const [ov, oppRes, recRes, assRes, appRes, savRes, tktRes, notRes, srcRes, prcRes, prvRes, npfRes] = await Promise.all([
        apiFetch<any>("/api/v1/caravan/overview"),
        apiFetch<any>(`/api/v1/caravan/opportunities?query=${encodeURIComponent(query)}&funding_type=${encodeURIComponent(typeFilter)}&verification_status=${encodeURIComponent(statusFilter)}`),
        apiFetch<any>("/api/v1/caravan/recommendations"),
        apiFetch<any>("/api/v1/caravan/assessments"),
        apiFetch<any>("/api/v1/caravan/applications"),
        apiFetch<any>("/api/v1/caravan/saved"),
        apiFetch<any>("/api/v1/caravan/support/tickets"),
        apiFetch<any>("/api/v1/caravan/notifications"),
        apiFetch<any>("/api/v1/caravan/sources"),
        apiFetch<any>("/api/v1/caravan/pricing").catch(() => null),
        apiFetch<any>("/api/v1/caravan/privacy").catch(() => null),
        apiFetch<any>("/api/v1/caravan/notifications/preferences").catch(() => null),
      ]);
      setOverview(ov);
      setOpportunities(oppRes.opportunities || []);
      setRecommendations(recRes.recommendations || []);
      setAssessments(assRes.assessments || []);
      setApplications(appRes.applications || []);
      setSaved(savRes.saved || []);
      setTickets(tktRes.tickets || []);
      setNotifications(notRes.notifications || []);
      setSources(srcRes.sources || []);
      setPricing(prcRes);
      setPrivacy(prvRes);
      setNotifPrefs(npfRes);
      if (ov?.account) {
        setOrgName(ov.account.organization_name || "");
        setEntityType(ov.account.entity_type || "STARTUP");
        setCountry(ov.account.country || "Nigeria");
        setStateLocation(ov.account.state_location || "");
        setSector(ov.account.sector || "Technology");
        setStage(ov.account.stage || "SEED");
        setFundingGoals(ov.account.funding_goals || "");
      }
    } catch (err: any) {
      pushToast(err.message || "Failed to load Caravan workspace.", "error");
    }
  }

  useEffect(() => {
    loadAll();
  }, [query, typeFilter, statusFilter]);

  async function handleRunEligibility(opportunityId: string) {
    try {
      const res = await apiFetch<any>("/api/v1/caravan/assessments", {
        method: "POST",
        body: { opportunity_id: opportunityId },
      });
      pushToast(`NEON Eligibility: ${res.verdict} (${res.score}/100)`, res.verdict === "ELIGIBLE" ? "success" : "info");
      await loadAll();
      onSelectSubPage("eligibility");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function handleSaveOpportunity(opportunityId: string) {
    try {
      await apiFetch("/api/v1/caravan/saved", {
        method: "POST",
        body: { opportunity_id: opportunityId },
      });
      pushToast("Saved to your Caravan shortlist.", "success");
      await loadAll();
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function handleStartApplication(opportunityId: string) {
    try {
      await apiFetch("/api/v1/caravan/applications", {
        method: "POST",
        body: { opportunity_id: opportunityId },
      });
      pushToast("Application draft created.", "success");
      await loadAll();
      onSelectSubPage("applications");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  const tabs = [
    { id: "overview", label: "Overview" },
    { id: "command-centre", label: "Operations Command Centre" },
    { id: "discover", label: "Discover Funding" },
    { id: "eligibility", label: "NEON Eligibility" },
    { id: "applications", label: "My Applications" },
    { id: "saved", label: "Saved" },
    { id: "account", label: "Account & Plan" },
    { id: "admin", label: "Admin & Verification" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="row-between" style={{ flexWrap: "wrap", gap: 10 }}>
        <div>
          <strong style={{ fontSize: 16 }}>Caravan — Funding Intelligence &amp; Applications</strong>
          <div className="muted" style={{ fontSize: 12 }}>
            First-party ULTRON product module powered by NEON, ARGON, Connections Centre, VAULT, AEGIS, and SENTINEL. Live payments disabled.
          </div>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={loadAll}>
          <RefreshCw size={12} /> Refresh
        </button>
      </div>

      {/* Responsive navigation tabs */}
      <div className="segmented" style={{ flexWrap: "wrap" }}>
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            className={`seg-btn ${subPage === t.id || (subPage === "details" && t.id === "discover") ? "active" : ""}`}
            onClick={() => onSelectSubPage(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Overview */}
      {subPage === "overview" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {/* Live Standalone Application Access Card */}
          <div
            className="card"
            style={{
              background: "linear-gradient(135deg, rgba(16, 21, 34, 0.95) 0%, rgba(20, 27, 45, 0.95) 100%)",
              border: "1px solid rgba(56, 189, 248, 0.25)",
              display: "flex",
              flexDirection: "column",
              gap: 12,
            }}
          >
            <div className="row-between" style={{ flexWrap: "wrap", gap: 12 }}>
              <div className="row" style={{ gap: 12 }}>
                <div
                  style={{
                    width: 40,
                    height: 40,
                    borderRadius: 8,
                    background: "linear-gradient(135deg, #38bdf8 0%, #818cf8 100%)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 800,
                    fontSize: 20,
                    color: "#050b14",
                    boxShadow: "0 0 16px rgba(56, 189, 248, 0.3)",
                  }}
                >
                  C
                </div>
                <div>
                  <div className="row" style={{ gap: 8, alignItems: "center" }}>
                    <strong style={{ fontSize: 15 }}>CARAVAN — Customer-Facing Platform</strong>
                    <span className="pill pill-emerald">READY / LIVE</span>
                    <span className="pill pill-cyan mono" style={{ fontSize: 10 }}>v1.0.0</span>
                  </div>
                  <div className="muted" style={{ fontSize: 12, marginTop: 2 }}>
                    Independent Deployment · Dedicated Repository: <span className="mono" style={{ color: "var(--accent-cyan)" }}>epejuwon-sketch/CARAVAN</span>
                  </div>
                </div>
              </div>

              <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
                <a
                  href={CARAVAN_DEPLOYED_URL}
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-sm"
                  style={{ fontWeight: 700 }}
                >
                  <ExternalLink size={13} /> Open CARAVAN
                </a>
                <a
                  href="https://github.com/epejuwon-sketch/CARAVAN"
                  target="_blank"
                  rel="noreferrer"
                  className="btn btn-secondary btn-sm"
                >
                  <ExternalLink size={13} /> GitHub Repository
                </a>
              </div>
            </div>
          </div>

          <div className="grid-4" style={{ gap: 10 }}>
            <MetricDisplay label="Verified Opportunities" value={String(overview?.verification_breakdown?.VERIFIED ?? 0)} sub={`Total tracked: ${overview?.opportunities_total ?? 0}`} tone="success" />
            <MetricDisplay label="My Applications" value={String(overview?.my_applications_count ?? 0)} sub="AEGIS approval-gated" tone="info" />
            <MetricDisplay label="Saved Shortlist" value={String(overview?.saved_opportunities_count ?? 0)} sub={`Plan: ${overview?.subscription?.plan_tier ?? "FREE"}`} tone="neutral" />
            <MetricDisplay label="Profile Completion" value={`${overview?.account?.profile_completion_pct ?? 0}%`} sub={`Unread Alerts: ${overview?.unread_notifications_count ?? 0}`} tone={overview?.account?.onboarding_completed ? "success" : "warn"} />
          </div>

          <div className="grid-2" style={{ gap: 10 }}>
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <strong style={{ fontSize: 13 }}>Upcoming Deadlines ({(overview?.upcoming_deadlines || []).length})</strong>
              {(overview?.upcoming_deadlines || []).length === 0 ? (
                <div className="muted" style={{ fontSize: 12 }}>No upcoming tracked deadlines.</div>
              ) : (
                (overview?.upcoming_deadlines || []).map((o: any) => (
                  <div key={o.opportunity_id} className="list-item row-between" style={{ gap: 6 }}>
                    <span style={{ fontSize: 12 }}><strong>{o.title}</strong></span>
                    <span className="pill mono">{String(o.deadline_at).slice(0, 10)}</span>
                  </div>
                ))
              )}
            </div>
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <strong style={{ fontSize: 13 }}>Recently Verified ({(overview?.recently_verified || []).length})</strong>
              {(overview?.recently_verified || []).length === 0 ? (
                <div className="muted" style={{ fontSize: 12 }}>No verified opportunities yet.</div>
              ) : (
                (overview?.recently_verified || []).map((o: any) => (
                  <div key={o.opportunity_id} className="list-item row-between" style={{ gap: 6 }}>
                    <span style={{ fontSize: 12 }}><strong>{o.title}</strong></span>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSelectedOpp(o)}>Inspect</button>
                  </div>
                ))
              )}
            </div>
          </div>

          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <strong><Sparkles size={14} /> Personalized Recommendations</strong>
            <div className="muted" style={{ fontSize: 12 }}>
              Ranked strictly from tracked opportunities matching your profile ({country}, {sector}, {stage}). Zero fabricated listings.
            </div>
            <DataTable
              rows={recommendations.slice(0, 6)}
              rowKey={(r) => r.opportunity_id}
              emptyTitle="No Tracked Opportunities Yet"
              emptyDescription="Add verified funding opportunities in Admin & Verification or sync an authorized Connections Centre source."
              columns={[
                {
                  key: "title",
                  header: "Opportunity",
                  render: (r) => (
                    <div>
                      <strong>{r.title}</strong>
                      <div className="muted" style={{ fontSize: 11 }}>{r.provider_org} · {r.funding_type}</div>
                    </div>
                  ),
                },
                {
                  key: "status",
                  header: "Verification",
                  render: (r) => <StatusIndicator label={r.verification_status} tone={verificationTone(r.verification_status)} />,
                },
                {
                  key: "match",
                  header: "Match",
                  render: (r) => <span className="mono">{r.match_score}%</span>,
                },
                {
                  key: "actions",
                  header: "Inspect",
                  render: (r) => (
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSelectedOpp(r)}>
                      Details
                    </button>
                  ),
                },
              ]}
            />
          </div>
        </div>
      )}

      {/* Discover Funding */}
      {(subPage === "discover" || subPage === "details") && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <div style={{ position: "relative", flex: 1, minWidth: 180 }}>
              <Search size={13} style={{ position: "absolute", left: 10, top: 10, opacity: 0.6 }} />
              <input className="input" style={{ paddingLeft: 28, width: "100%" }} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search grants, loans, scholarships, accelerators..." />
            </div>
            <select className="select" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} aria-label="Funding type">
              <option value="">All Funding Types</option>
              {["GRANT", "LOAN", "SCHOLARSHIP", "ACCELERATOR", "COMPETITION", "INVESTMENT", "OTHER"].map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} aria-label="Verification status">
              <option value="">All Statuses</option>
              {["VERIFIED", "NEEDS_REVIEW", "UNVERIFIED", "EXPIRED", "CLOSED"].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
            <select className="select" value={geoFilter} onChange={(e) => setGeoFilter(e.target.value)} aria-label="Market location">
              <option value="">All Locations</option>
              <option value="nigeria">Nigeria</option>
              <option value="africa">Africa</option>
              <option value="global">Global</option>
            </select>
            <label className="row" style={{ gap: 4, fontSize: 12 }}>
              <input type="checkbox" checked={openDeadlinesOnly} onChange={(e) => setOpenDeadlinesOnly(e.target.checked)} />
              Open Deadlines Only
            </label>
          </div>

          <DataTable
            rows={opportunities.filter((o) => {
              if (geoFilter && !(o.geographic_restrictions || "").toLowerCase().includes(geoFilter)) return false;
              if (openDeadlinesOnly && (o.verification_status === "EXPIRED" || o.freshness_status === "EXPIRED")) return false;
              return true;
            })}
            rowKey={(r) => r.opportunity_id}
            emptyTitle="No Matching Opportunities"
            emptyDescription="No tracked funding opportunities match the current filter."
            columns={[
              {
                key: "title",
                header: "Opportunity",
                render: (r) => (
                  <div>
                    <strong>{r.title}</strong>
                    <div className="muted" style={{ fontSize: 11 }}>{r.provider_org} · {r.funding_type} · {r.geographic_restrictions}</div>
                  </div>
                ),
              },
              {
                key: "amount",
                header: "Amount",
                render: (r) => <span className="mono" style={{ fontSize: 12 }}>{r.amount_display}</span>,
              },
              {
                key: "status",
                header: "Verification",
                render: (r) => <StatusIndicator label={r.verification_status} tone={verificationTone(r.verification_status)} />,
              },
              {
                key: "actions",
                header: "Actions",
                render: (r) => (
                  <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSelectedOpp(r)}>Details</button>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleRunEligibility(r.opportunity_id)}>Assess</button>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleSaveOpportunity(r.opportunity_id)}><Bookmark size={12} /></button>
                  </div>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* Eligibility Assessment */}
      {subPage === "eligibility" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <strong><UserCheck size={14} /> NEON Eligibility Assessments ({assessments.length})</strong>
          <div className="muted" style={{ fontSize: 12 }}>
            NEON scores and preparation recommendations are AI-assisted assessments; always confirm verified source facts (URL, deadline, and official requirements) before submitting.
          </div>
          <DataTable
            rows={assessments}
            rowKey={(r) => r.assessment_id}
            emptyTitle="No Assessments Yet"
            emptyDescription="Select any opportunity in Discover Funding and click Assess to run NEON eligibility evaluation."
            columns={[
              { key: "opp", header: "Opportunity ID", render: (r) => <span className="mono">{r.opportunity_id}</span> },
              { key: "verdict", header: "Verdict", render: (r) => <StatusIndicator label={`${r.verdict} (${r.score}%)`} tone={r.verdict === "ELIGIBLE" ? "success" : "warn"} /> },
              { key: "mode", header: "NEON Mode", render: (r) => <span className="pill mono">{r.neon_mode}</span> },
              { key: "gaps", header: "Gaps / Notes", render: (r) => <span className="muted" style={{ fontSize: 11 }}>{(r.gaps || []).join("; ") || "None"}</span> },
            ]}
          />
        </div>
      )}

      {/* My Applications & Application Workspace */}
      {subPage === "applications" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
              <strong><ClipboardList size={14} /> My Applications ({applications.length})</strong>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={async () => {
                  try {
                    const res = await apiFetch<any>("/api/v1/caravan/applications/deadline-reminders?within_days=14", { method: "POST" });
                    pushToast(`Deadline check: ${res.reminders_created} reminder(s) created.`, "info");
                    await loadAll();
                  } catch (err: any) {
                    pushToast(err.message, "error");
                  }
                }}
              >
                Check Approaching Deadlines
              </button>
            </div>
            <div className="muted" style={{ fontSize: 12 }}>
              Prepare checklists, required documents, and draft notes here. Users review and submit applications directly at the official source URL.
            </div>
            <DataTable
              rows={applications}
              rowKey={(r) => r.application_id}
              emptyTitle="No Applications Started"
              emptyDescription="Open any verified opportunity and click Start Application."
              columns={[
                { key: "id", header: "Application", render: (r) => <span className="mono">{r.application_id}</span> },
                { key: "opp", header: "Opportunity", render: (r) => <span className="mono">{r.opportunity_id}</span> },
                { key: "status", header: "Status", render: (r) => <StatusIndicator label={r.status} tone={r.status === "SUBMITTED" || r.status === "AWARDED" ? "success" : "info"} /> },
                { key: "progress", header: "Progress", render: (r) => <span className="mono">{r.progress_pct}%</span> },
                {
                  key: "submit",
                  header: "Workspace & Submit",
                  render: (r) => (
                    <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        onClick={() => {
                          setSelectedApp(r);
                          setAppNotes(r.notes || "");
                        }}
                      >
                        Open Workspace
                      </button>
                      {(r.status === "DRAFT" || r.status === "PREPARING") ? (
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={async () => {
                            const updated = await apiFetch<any>(`/api/v1/caravan/applications/${r.application_id}`, {
                              method: "PATCH",
                              body: { status: "SUBMITTED", progress_pct: 100 },
                            });
                            pushToast(`Application status: ${updated.status}`, "info");
                            await loadAll();
                          }}
                        >
                          Request Submit
                        </button>
                      ) : (
                        <span className="muted" style={{ fontSize: 11 }}>{r.approval_id || r.status}</span>
                      )}
                    </div>
                  ),
                },
              ]}
            />
          </div>

          {selectedApp && (
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <div className="row-between">
                <strong>Application Workspace · <span className="mono">{selectedApp.application_id}</span></strong>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => setSelectedApp(null)}>Close</button>
              </div>
              <div className="muted" style={{ fontSize: 11 }}>
                Reusable Profile Pre-fill: {orgName || "Org"} · {entityType} · {country}{stateLocation ? `, ${stateLocation}` : ""} · {sector} · {stage}
                {fundingGoals ? ` · Goals: ${fundingGoals}` : ""}
              </div>
              <div className="telemetry-label">PREPARATION &amp; REQUIRED DOCUMENTS CHECKLIST</div>
              {(selectedApp.checklist || []).map((c: any, idx: number) => (
                <label key={idx} className="list-item row" style={{ gap: 8, cursor: "pointer" }}>
                  <input
                    type="checkbox"
                    checked={Boolean(c.done)}
                    onChange={async () => {
                      const nextList = (selectedApp.checklist || []).map((it: any, i: number) =>
                        i === idx ? { ...it, done: !it.done } : it
                      );
                      const updated = await apiFetch<any>(`/api/v1/caravan/applications/${selectedApp.application_id}`, {
                        method: "PATCH",
                        body: { status: "PREPARING", checklist: nextList },
                      });
                      setSelectedApp(updated);
                      await loadAll();
                    }}
                  />
                  <span style={{ textDecoration: c.done ? "line-through" : "none" }}>{c.item}</span>
                </label>
              ))}
              <div className="row" style={{ gap: 6 }}>
                <input
                  className="input"
                  style={{ flex: 1 }}
                  placeholder="Add required document or checklist item..."
                  value={newDocItem}
                  onChange={(e) => setNewDocItem(e.target.value)}
                />
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={async () => {
                    if (!newDocItem.trim()) return;
                    const nextList = [...(selectedApp.checklist || []), { item: newDocItem.trim(), done: false }];
                    const updated = await apiFetch<any>(`/api/v1/caravan/applications/${selectedApp.application_id}`, {
                      method: "PATCH",
                      body: { checklist: nextList },
                    });
                    setNewDocItem("");
                    setSelectedApp(updated);
                    await loadAll();
                  }}
                >
                  Add Item
                </button>
              </div>
              <textarea
                className="input"
                rows={3}
                placeholder="Draft answers and preparation notes..."
                value={appNotes}
                onChange={(e) => setAppNotes(e.target.value)}
              />
              <button
                type="button"
                className="btn btn-sm"
                onClick={async () => {
                  const updated = await apiFetch<any>(`/api/v1/caravan/applications/${selectedApp.application_id}`, {
                    method: "PATCH",
                    body: { notes: appNotes, status: selectedApp.status === "DRAFT" ? "PREPARING" : undefined },
                  });
                  setSelectedApp(updated);
                  pushToast("Workspace notes saved.", "success");
                  await loadAll();
                }}
              >
                Save Workspace Notes
              </button>
            </div>
          )}
        </div>
      )}

      {/* Saved Opportunities */}
      {subPage === "saved" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <strong><Bookmark size={14} /> Saved Opportunities ({saved.length})</strong>
          <DataTable
            rows={saved}
            rowKey={(r) => r.saved_id}
            emptyTitle="No Saved Opportunities"
            emptyDescription="Bookmark opportunities in Discover Funding to track them here."
            columns={[
              { key: "opp", header: "Opportunity ID", render: (r) => <span className="mono">{r.opportunity_id}</span> },
              { key: "created", header: "Saved At", render: (r) => <span className="muted" style={{ fontSize: 11 }}>{r.created_at}</span> },
              {
                key: "actions",
                header: "Actions",
                render: (r) => (
                  <div className="row" style={{ gap: 6 }}>
                    <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleStartApplication(r.opportunity_id)}>Start App</button>
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={async () => {
                        await apiFetch(`/api/v1/caravan/saved/${r.saved_id}`, { method: "DELETE" });
                        await loadAll();
                      }}
                    >
                      Remove
                    </button>
                  </div>
                ),
              },
            ]}
          />
        </div>
      )}

      {/* Account, Subscription & Support */}
      {subPage === "account" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="row-between">
              <strong>Customer Profile &amp; Onboarding</strong>
              <span className="pill mono">{overview?.account?.profile_completion_pct ?? 0}% Complete</span>
            </div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <input className="input" style={{ flex: 2 }} placeholder="Organization or Applicant Name" value={orgName} onChange={(e) => setOrgName(e.target.value)} />
              <select className="select" style={{ flex: 1 }} value={entityType} onChange={(e) => setEntityType(e.target.value)} aria-label="Profile type">
                {["INDIVIDUAL", "STUDENT", "STARTUP", "BUSINESS", "NONPROFIT", "INSTITUTION"].map((et) => (
                  <option key={et} value={et}>{et}</option>
                ))}
              </select>
            </div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <input className="input" style={{ flex: 1 }} placeholder="Country" value={country} onChange={(e) => setCountry(e.target.value)} />
              <input className="input" style={{ flex: 1 }} placeholder="State / City (e.g. Lagos, Abuja)" value={stateLocation} onChange={(e) => setStateLocation(e.target.value)} />
              <input className="input" style={{ flex: 1 }} placeholder="Sector / Field" value={sector} onChange={(e) => setSector(e.target.value)} />
              <input className="input" style={{ flex: 1 }} placeholder="Stage" value={stage} onChange={(e) => setStage(e.target.value)} />
            </div>
            <input className="input" placeholder="Funding Goals (e.g. Seed grant for agritech pilot in Lagos)" value={fundingGoals} onChange={(e) => setFundingGoals(e.target.value)} />
            <button
              type="button"
              className="btn btn-sm"
              onClick={async () => {
                await apiFetch("/api/v1/caravan/account", {
                  method: "PUT",
                  body: {
                    organization_name: orgName,
                    entity_type: entityType,
                    country,
                    state_location: stateLocation,
                    sector,
                    stage,
                    funding_goals: fundingGoals,
                    onboarding_completed: true,
                  },
                });
                pushToast("Caravan customer profile saved.", "success");
                await loadAll();
              }}
            >
              Save Profile
            </button>
          </div>

          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <strong>Subscription &amp; Entitlements (Live Payments Disabled)</strong>
            <div className="muted" style={{ fontSize: 12 }}>
              Current Tier: <strong>{overview?.subscription?.plan_tier ?? "FREE"}</strong> · Live Payments Enabled:{" "}
              <strong>{String(overview?.subscription?.live_payments_enabled ?? false)}</strong>
            </div>
            {overview?.subscription?.entitlements && (
              <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                <span className="pill mono">Max Saved: {overview.subscription.entitlements.max_saved_opportunities}</span>
                <span className="pill mono">NEON/mo: {overview.subscription.entitlements.neon_assessments_per_month}</span>
                <span className="pill mono">ARGON Runs: {overview.subscription.entitlements.argon_research_runs}</span>
              </div>
            )}
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              {["FREE", "PRO", "INSTITUTIONAL"].map((tier) => (
                <button
                  key={tier}
                  type="button"
                  className={`btn btn-sm ${overview?.subscription?.plan_tier === tier ? "" : "btn-secondary"}`}
                  onClick={async () => {
                    await apiFetch("/api/v1/caravan/subscription", {
                      method: "PUT",
                      body: { plan_tier: tier, enable_live_payments: false },
                    });
                    pushToast(`Plan entitlements switched to ${tier} (sandbox).`, "success");
                    await loadAll();
                  }}
                >
                  {tier}
                </button>
              ))}
            </div>
            {Array.isArray(pricing?.plans) && (
              <div className="grid-3" style={{ gap: 8, paddingTop: 4 }}>
                {pricing.plans.map((pl: any) => (
                  <div key={pl.tier} className="list-item" style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <strong>{pl.label}</strong>
                    <div className="mono" style={{ fontSize: 12 }}>${pl.monthly_usd}/mo · NGN {Number(pl.monthly_ngn || 0).toLocaleString()}/mo</div>
                    <div className="muted" style={{ fontSize: 11 }}>{pl.target_audience}</div>
                  </div>
                ))}
              </div>
            )}
            <div className="muted" style={{ fontSize: 11 }}>
              {pricing?.cancellation_policy || "Cancel anytime; live payments disabled until explicitly authorized."}
            </div>
          </div>

          {privacy && (
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <strong>Privacy, Consent &amp; Account Controls</strong>
              <label className="row" style={{ gap: 8, fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={Boolean(privacy.analytics_consent)}
                  onChange={async () => {
                    await apiFetch("/api/v1/caravan/privacy", {
                      method: "PUT",
                      body: { analytics_consent: !privacy.analytics_consent },
                    });
                    await loadAll();
                  }}
                />
                Allow privacy-preserving product analytics
              </label>
              <label className="row" style={{ gap: 8, fontSize: 12 }}>
                <input
                  type="checkbox"
                  checked={Boolean(privacy.marketing_consent)}
                  onChange={async () => {
                    await apiFetch("/api/v1/caravan/privacy", {
                      method: "PUT",
                      body: { marketing_consent: !privacy.marketing_consent },
                    });
                    await loadAll();
                  }}
                />
                Allow funding alerts and product updates
              </label>
              <div className="row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                <button
                  type="button"
                  className="btn btn-danger btn-sm"
                  disabled={Boolean(privacy.deletion_requested)}
                  onClick={async () => {
                    await apiFetch("/api/v1/caravan/privacy", {
                      method: "PUT",
                      body: { deletion_requested: true, deletion_reason: "User requested account deletion from Caravan Account settings." },
                    });
                    pushToast("Account deletion request recorded for administrator review.", "info");
                    await loadAll();
                  }}
                >
                  {privacy.deletion_requested ? "Deletion Requested" : "Request Account Deletion"}
                </button>
                <span className="muted" style={{ fontSize: 11 }}>
                  {pricing?.legal_notice || "NDPR/GDPR consent & cancellation transparency."}
                </span>
              </div>
            </div>
          )}

          {notifPrefs && (
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <strong>Notification Preferences</strong>
              <div className="row" style={{ gap: 14, flexWrap: "wrap" }}>
                {[
                  ["in_app_enabled", "In-app alerts"],
                  ["email_enabled", "Email alerts"],
                  ["deadline_alerts", "Deadline reminders"],
                  ["saved_updates", "Saved opportunity updates"],
                  ["subscription_alerts", "Subscription status"],
                  ["support_updates", "Support responses"],
                ].map(([field, label]) => (
                  <label key={field} className="row" style={{ gap: 6, fontSize: 12 }}>
                    <input
                      type="checkbox"
                      checked={Boolean(notifPrefs[field])}
                      onChange={async () => {
                        await apiFetch("/api/v1/caravan/notifications/preferences", {
                          method: "PUT",
                          body: { [field]: !notifPrefs[field] },
                        });
                        await loadAll();
                      }}
                    />
                    {label}
                  </label>
                ))}
              </div>
              <div className="muted" style={{ fontSize: 11 }}>
                WhatsApp alerts remain disabled unless explicitly authorized and backed by a live-verified WhatsApp Business connection.
              </div>
            </div>
          )}

          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <strong>Alerts &amp; Notifications ({notifications.length})</strong>
            {notifications.length === 0 ? (
              <div className="muted" style={{ fontSize: 12 }}>No notifications yet.</div>
            ) : (
              notifications.slice(0, 8).map((n) => (
                <div key={n.notification_id} className="list-item row-between" style={{ gap: 8, flexWrap: "wrap" }}>
                  <div>
                    <strong>{n.title}</strong>
                    <div className="muted" style={{ fontSize: 11 }}>{n.body}</div>
                  </div>
                  {!n.read ? (
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={async () => {
                        await apiFetch(`/api/v1/caravan/notifications/${n.notification_id}/read`, { method: "POST" });
                        await loadAll();
                      }}
                    >
                      Mark Read
                    </button>
                  ) : (
                    <span className="pill mono">READ</span>
                  )}
                </div>
              ))
            )}
          </div>

          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <strong>Customer Support ({tickets.length})</strong>
            <input className="input" placeholder="Support Subject" value={ticketSubject} onChange={(e) => setTicketSubject(e.target.value)} />
            <input className="input" placeholder="Describe your question..." value={ticketMessage} onChange={(e) => setTicketMessage(e.target.value)} />
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={async () => {
                if (!ticketSubject.trim() || !ticketMessage.trim()) return;
                await apiFetch("/api/v1/caravan/support/tickets", {
                  method: "POST",
                  body: { subject: ticketSubject.trim(), message: ticketMessage.trim() },
                });
                setTicketSubject("");
                setTicketMessage("");
                pushToast("Support ticket created.", "success");
                await loadAll();
              }}
            >
              Submit Ticket
            </button>
            {tickets.slice(0, 5).map((t) => (
              <div key={t.ticket_id} className="list-item row-between" style={{ gap: 8 }}>
                <span>{t.subject}</span>
                <span className="pill mono">{t.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Admin & Funding Verification */}
      {subPage === "admin" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <strong><Plus size={14} /> Register Real Funding Opportunity (Starts UNVERIFIED)</strong>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <input className="input" style={{ flex: 1 }} placeholder="Opportunity Title" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} />
              <input className="input" style={{ flex: 1 }} placeholder="Provider Organization" value={newProvider} onChange={(e) => setNewProvider(e.target.value)} />
            </div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <select className="select" value={newType} onChange={(e) => setNewType(e.target.value)}>
                {["GRANT", "LOAN", "SCHOLARSHIP", "ACCELERATOR", "COMPETITION", "INVESTMENT", "OTHER"].map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <input className="input" style={{ flex: 1 }} placeholder="Official Source URL (https://...)" value={newUrl} onChange={(e) => setNewUrl(e.target.value)} />
            </div>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <input className="input" style={{ flex: 1 }} placeholder="Geographic Restrictions" value={newGeo} onChange={(e) => setNewGeo(e.target.value)} />
              <input className="input" style={{ flex: 1 }} placeholder="Amount (e.g. Up to $50,000)" value={newAmount} onChange={(e) => setNewAmount(e.target.value)} />
            </div>
            <input className="input" placeholder="Eligibility Requirements (exact source criteria)" value={newReqs} onChange={(e) => setNewReqs(e.target.value)} />
            <button
              type="button"
              className="btn btn-sm"
              onClick={async () => {
                try {
                  await apiFetch("/api/v1/caravan/opportunities", {
                    method: "POST",
                    body: {
                      title: newTitle.trim(),
                      provider_org: newProvider.trim(),
                      funding_type: newType,
                      source_url: newUrl.trim(),
                      eligibility_requirements: newReqs.trim(),
                      geographic_restrictions: newGeo.trim(),
                      amount_display: newAmount.trim() || "Not specified by source",
                    },
                  });
                  setNewTitle("");
                  setNewProvider("");
                  setNewUrl("");
                  setNewReqs("");
                  setNewAmount("");
                  pushToast("Funding opportunity registered (UNVERIFIED).", "success");
                  await loadAll();
                } catch (err: any) {
                  pushToast(err.message, "error");
                }
              }}
            >
              Register Opportunity
            </button>
          </div>

          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <strong><ShieldCheck size={14} /> Registered Sources ({sources.length}) &amp; ARGON Verification</strong>
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <input className="input" style={{ flex: 1 }} placeholder="Source Name (e.g. Tony Elumelu Foundation)" value={sourceName} onChange={(e) => setSourceName(e.target.value)} />
              <select className="select" value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
                {["PUBLIC_PORTAL", "RSS_FEED", "PARTNER_API", "OFFICIAL_REGISTRY"].map((st) => (
                  <option key={st} value={st}>{st}</option>
                ))}
              </select>
              <input className="input" style={{ flex: 1 }} placeholder="https://..." value={sourceUrl} onChange={(e) => setSourceUrl(e.target.value)} />
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={async () => {
                  try {
                    await apiFetch("/api/v1/caravan/sources", {
                      method: "POST",
                      body: { name: sourceName.trim(), source_type: sourceType, base_url: sourceUrl.trim() },
                    });
                    setSourceName("");
                    setSourceUrl("");
                    pushToast("Funding source registered.", "success");
                    await loadAll();
                  } catch (err: any) {
                    pushToast(err.message, "error");
                  }
                }}
              >
                Add Source
              </button>
            </div>
            {sources.map((s) => (
              <div key={s.source_id} className="list-item row-between" style={{ gap: 8, flexWrap: "wrap" }}>
                <div>
                  <strong>{s.name}</strong>
                  <div className="muted mono" style={{ fontSize: 11 }}>
                    {s.base_url} · {s.status} {s.last_checked_at ? `· Checked ${s.last_checked_at}` : ""}
                  </div>
                </div>
                <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={async () => {
                      try {
                        const res = await apiFetch<any>(`/api/v1/caravan/discovery/ingest/${s.source_id}`, { method: "POST" });
                        pushToast(`ARGON Ingestion: ${res.created_count} created (${res.duplicates_skipped} duplicates skipped).`, "success");
                        await loadAll();
                      } catch (err: any) {
                        pushToast(err.message, "error");
                      }
                    }}
                  >
                    Run ARGON Ingestion
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    onClick={async () => {
                      try {
                        const res = await apiFetch<any>(`/api/v1/caravan/sources/${s.source_id}/verify`, { method: "POST" });
                        pushToast(`ARGON Probe: ${res.detail}`, res.reachable ? "success" : "info");
                        await loadAll();
                      } catch (err: any) {
                        pushToast(err.message, "error");
                      }
                    }}
                  >
                    ARGON Live Probe
                  </button>
                </div>
              </div>
            ))}
          </div>

          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
              <strong><ShieldCheck size={14} /> Opportunity Verification Queue</strong>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={async () => {
                  try {
                    const res = await apiFetch<any>("/api/v1/caravan/opportunities/sweep-expired", { method: "POST" });
                    pushToast(`Expired sweep complete: ${res.expired_count} opportunity(s) marked EXPIRED.`, "info");
                    await loadAll();
                  } catch (err: any) {
                    pushToast(err.message, "error");
                  }
                }}
              >
                <RefreshCw size={12} /> Sweep Expired Deadlines
              </button>
            </div>
            <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
              {["ALL", "NEEDS_REVIEW", "DISCOVERED", "EXTRACTED", "VERIFIED", "REJECTED", "EXPIRED"].map((st) => (
                <button
                  key={st}
                  type="button"
                  className={`btn btn-sm ${adminStageFilter === st ? "" : "btn-secondary"}`}
                  onClick={() => setAdminStageFilter(st)}
                >
                  {st}
                </button>
              ))}
            </div>
            <input className="input" placeholder="Verification supporting evidence or rejection reason" value={verifyEvidence} onChange={(e) => setVerifyEvidence(e.target.value)} />
            {opportunities
              .filter((o) => adminStageFilter === "ALL" || o.verification_status === adminStageFilter)
              .slice(0, 15)
              .map((o) => (
                <div key={o.opportunity_id} className="list-item row-between" style={{ gap: 8, flexWrap: "wrap" }}>
                  <div>
                    <strong>{o.title}</strong>
                    <div className="muted" style={{ fontSize: 11 }}>{o.provider_org} · {o.verification_status} · {o.freshness_status || "UNVERIFIED"}</div>
                  </div>
                  <div className="row" style={{ gap: 6, flexWrap: "wrap" }}>
                    <button
                      type="button"
                      className="btn btn-sm"
                      onClick={async () => {
                        try {
                          await apiFetch(`/api/v1/caravan/discovery/opportunities/${o.opportunity_id}/review`, {
                            method: "POST",
                            body: { decision: "VERIFIED", supporting_evidence: verifyEvidence.trim() },
                          });
                          pushToast(`Verified '${o.title}'.`, "success");
                          await loadAll();
                        } catch (err: any) {
                          pushToast(err.message, "error");
                        }
                      }}
                    >
                      <CheckCircle2 size={12} /> Verify
                    </button>
                    <button
                      type="button"
                      className="btn btn-danger btn-sm"
                      onClick={async () => {
                        try {
                          await apiFetch(`/api/v1/caravan/discovery/opportunities/${o.opportunity_id}/review`, {
                            method: "POST",
                            body: { decision: "REJECTED", supporting_evidence: verifyEvidence.trim() || "Rejected by administrator review." },
                          });
                          pushToast(`Rejected '${o.title}'.`, "info");
                          await loadAll();
                        } catch (err: any) {
                          pushToast(err.message, "error");
                        }
                      }}
                    >
                      Reject
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary btn-sm"
                      onClick={async () => {
                        await apiFetch(`/api/v1/caravan/opportunities/${o.opportunity_id}/verify`, {
                          method: "POST",
                          body: { verification_status: "CLOSED", supporting_evidence: verifyEvidence.trim() || "Marked closed by reviewer." },
                        });
                        await loadAll();
                      }}
                    >
                      Mark Closed
                    </button>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {subPage === "command-centre" && <CaravanCommandCentre onNavigateSubPage={onSelectSubPage} />}

      {/* Opportunity Details Drawer */}
      <Drawer open={Boolean(selectedOpp)} title={selectedOpp ? selectedOpp.title : ""} onClose={() => setSelectedOpp(null)}>
        {selectedOpp && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 12 }}>
            <div className="row-between">
              <span className="pill mono">{selectedOpp.funding_type}</span>
              <StatusIndicator label={selectedOpp.verification_status} tone={verificationTone(selectedOpp.verification_status)} />
            </div>
            <div><strong>Provider:</strong> {selectedOpp.provider_org}</div>
            <div><strong>Amount:</strong> {selectedOpp.amount_display} ({selectedOpp.currency})</div>
            <div><strong>Geography:</strong> {selectedOpp.geographic_restrictions}</div>
            <div><strong>Deadline:</strong> {selectedOpp.deadline_at || "See official source"}</div>
            <div><strong>Last Verified:</strong> {selectedOpp.last_verified_at || "Not yet verified"}</div>
            <div><strong>Eligibility Requirements:</strong><div className="muted">{selectedOpp.eligibility_requirements}</div></div>
            {selectedOpp.supporting_evidence && <div><strong>Supporting Evidence:</strong><div className="muted">{selectedOpp.supporting_evidence}</div></div>}
            <a href={selectedOpp.source_url} target="_blank" rel="noopener noreferrer" className="row" style={{ gap: 4 }}>
              <ExternalLink size={12} /> Official Source URL
            </a>
            <div className="row" style={{ gap: 8, flexWrap: "wrap", paddingTop: 6 }}>
              <button type="button" className="btn btn-sm" onClick={() => handleRunEligibility(selectedOpp.opportunity_id)}>Run NEON Eligibility</button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleStartApplication(selectedOpp.opportunity_id)}>Start Application</button>
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => handleSaveOpportunity(selectedOpp.opportunity_id)}>Save</button>
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
