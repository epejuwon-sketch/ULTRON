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
import { apiFetch } from "../lib/api";
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
  const [country, setCountry] = useState("Nigeria");
  const [sector, setSector] = useState("Technology");
  const [stage, setStage] = useState("SEED");
  const [ticketSubject, setTicketSubject] = useState("");
  const [ticketMessage, setTicketMessage] = useState("");

  async function loadAll() {
    try {
      const [ov, oppRes, recRes, assRes, appRes, savRes, tktRes, notRes, srcRes] = await Promise.all([
        apiFetch<any>("/api/v1/caravan/overview"),
        apiFetch<any>(`/api/v1/caravan/opportunities?query=${encodeURIComponent(query)}&funding_type=${encodeURIComponent(typeFilter)}&verification_status=${encodeURIComponent(statusFilter)}`),
        apiFetch<any>("/api/v1/caravan/recommendations"),
        apiFetch<any>("/api/v1/caravan/assessments"),
        apiFetch<any>("/api/v1/caravan/applications"),
        apiFetch<any>("/api/v1/caravan/saved"),
        apiFetch<any>("/api/v1/caravan/support/tickets"),
        apiFetch<any>("/api/v1/caravan/notifications"),
        apiFetch<any>("/api/v1/caravan/sources"),
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
      if (ov?.account) {
        setOrgName(ov.account.organization_name || "");
        setCountry(ov.account.country || "Nigeria");
        setSector(ov.account.sector || "Technology");
        setStage(ov.account.stage || "SEED");
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
          <div className="grid-4" style={{ gap: 10 }}>
            <MetricDisplay label="Verified Opportunities" value={String(overview?.verification_breakdown?.VERIFIED ?? 0)} sub={`Total tracked: ${overview?.opportunities_total ?? 0}`} tone="success" />
            <MetricDisplay label="My Applications" value={String(overview?.my_applications_count ?? 0)} sub="AEGIS approval-gated" tone="info" />
            <MetricDisplay label="Saved Shortlist" value={String(overview?.saved_opportunities_count ?? 0)} sub={`Plan: ${overview?.subscription?.plan_tier ?? "FREE"}`} tone="neutral" />
            <MetricDisplay label="Unread Alerts" value={String(overview?.unread_notifications_count ?? 0)} sub="Live payments: OFF" tone="warn" />
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
              {["VERIFIED", "UNVERIFIED", "EXPIRED", "CLOSED"].map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>

          <DataTable
            rows={opportunities}
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

      {/* My Applications */}
      {subPage === "applications" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <strong><ClipboardList size={14} /> My Applications ({applications.length})</strong>
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
                header: "Submit (AEGIS)",
                render: (r) =>
                  r.status === "DRAFT" || r.status === "PREPARING" ? (
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
                  ),
              },
            ]}
          />
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
            <strong>Customer Profile &amp; Onboarding</strong>
            <input className="input" placeholder="Organization Name" value={orgName} onChange={(e) => setOrgName(e.target.value)} />
            <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
              <input className="input" style={{ flex: 1 }} placeholder="Country" value={country} onChange={(e) => setCountry(e.target.value)} />
              <input className="input" style={{ flex: 1 }} placeholder="Sector" value={sector} onChange={(e) => setSector(e.target.value)} />
              <input className="input" style={{ flex: 1 }} placeholder="Stage" value={stage} onChange={(e) => setStage(e.target.value)} />
            </div>
            <button
              type="button"
              className="btn btn-sm"
              onClick={async () => {
                await apiFetch("/api/v1/caravan/account", {
                  method: "PUT",
                  body: { organization_name: orgName, country, sector, stage, onboarding_completed: true },
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
              Current Tier: <strong>{overview?.subscription?.plan_tier ?? "FREE"}</strong> · Live Payments Enabled: <strong>{String(overview?.subscription?.live_payments_enabled ?? false)}</strong>
            </div>
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
          </div>

          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <strong>Customer Support ({tickets.length}) &amp; Alerts ({notifications.length})</strong>
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
            <strong><ShieldCheck size={14} /> Registered Sources ({sources.length}) &amp; Verification Queue</strong>
            <input className="input" placeholder="Verification supporting evidence (required to mark VERIFIED)" value={verifyEvidence} onChange={(e) => setVerifyEvidence(e.target.value)} />
            {opportunities.slice(0, 10).map((o) => (
              <div key={o.opportunity_id} className="list-item row-between" style={{ gap: 8, flexWrap: "wrap" }}>
                <div>
                  <strong>{o.title}</strong>
                  <div className="muted" style={{ fontSize: 11 }}>{o.provider_org} · {o.verification_status}</div>
                </div>
                <div className="row" style={{ gap: 6 }}>
                  <button
                    type="button"
                    className="btn btn-sm"
                    onClick={async () => {
                      try {
                        await apiFetch(`/api/v1/caravan/opportunities/${o.opportunity_id}/verify`, {
                          method: "POST",
                          body: { verification_status: "VERIFIED", supporting_evidence: verifyEvidence.trim() },
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
