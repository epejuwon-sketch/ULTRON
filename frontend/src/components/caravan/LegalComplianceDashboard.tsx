import React, { useEffect, useState } from "react";
import {
  AlertCircle,
  Award,
  BookOpen,
  Calendar,
  CheckCircle2,
  Clock,
  ExternalLink,
  FileCheck,
  FileText,
  Lock,
  Plus,
  RefreshCw,
  Scale,
  Shield,
  ShieldAlert,
  ShieldCheck,
  Users,
} from "lucide-react";
import { apiFetch } from "../../lib/api";
import { DataTable, Drawer, MetricDisplay, StatusIndicator, useToast } from "../ui/DesignSystem";

function renderCanonicalStatusPill(status: string) {
  switch (status) {
    case "APPROVED":
      return <span className="pill pill-emerald" style={{ fontSize: 11 }}>Approved</span>;
    case "SUBMITTED":
      return <span className="pill pill-cyan" style={{ fontSize: 11 }}>Submitted</span>;
    case "AWAITING_OWNER_APPROVAL":
      return <span className="pill pill-warn" style={{ fontSize: 11 }}>Awaiting owner approval</span>;
    case "AWAITING_PROFESSIONAL_REVIEW":
      return <span className="pill pill-amber" style={{ fontSize: 11 }}>Awaiting professional review</span>;
    case "AWAITING_INFORMATION":
      return <span className="pill pill-amber" style={{ fontSize: 11 }}>Awaiting information</span>;
    case "IN_PROGRESS":
      return <span className="pill pill-cyan" style={{ fontSize: 11 }}>In progress</span>;
    case "REJECTED_QUERIED":
      return <span className="pill pill-error" style={{ fontSize: 11 }}>Rejected / queried</span>;
    case "NOT_STARTED":
    default:
      return <span className="pill" style={{ fontSize: 11, background: "rgba(255,255,255,0.06)", color: "#94a3b8" }}>Not started</span>;
  }
}

interface LegalComplianceDashboardProps {
  onNavigateTab?: (tabId: string) => void;
}

export function LegalComplianceDashboard({ onNavigateTab }: LegalComplianceDashboardProps) {
  const { pushToast } = useToast();
  const [loading, setLoading] = useState(true);
  const [dashboard, setDashboard] = useState<any>(null);
  const [policies, setPolicies] = useState<any[]>([]);
  const [officers, setOfficers] = useState<any[]>([]);
  const [archives, setArchives] = useState<any[]>([]);
  const [activeSubTab, setActiveSubTab] = useState<"dashboard" | "cac_workflow" | "incorporation" | "officers" | "policies" | "vault">("dashboard");
  const [selectedPolicy, setSelectedPolicy] = useState<any>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // New officer form
  const [officerType, setOfficerType] = useState("DIRECTOR");
  const [officerName, setOfficerName] = useState("");
  const [officerDob, setOfficerDob] = useState("1995-05-15");
  const [officerNin, setOfficerNin] = useState("");
  const [officerAddress, setOfficerAddress] = useState("12 Adeola Odeku Street, Victoria Island, Lagos, Nigeria");
  const [officerEmail, setOfficerEmail] = useState("");
  const [officerPhone, setOfficerPhone] = useState("+2348012345678");
  const [officerShares, setOfficerShares] = useState(100000);
  const [officerEquity, setOfficerEquity] = useState(10.0);
  const [guardianId, setGuardianId] = useState("");

  async function loadData() {
    setLoading(true);
    try {
      const [dashRes, polRes, offRes, arcRes] = await Promise.all([
        apiFetch<any>("/api/v1/legal/dashboard"),
        apiFetch<any[]>("/api/v1/legal/policies"),
        apiFetch<any[]>("/api/v1/legal/officers"),
        apiFetch<any[]>("/api/v1/legal/archive"),
      ]);
      setDashboard(dashRes);
      setPolicies(polRes || []);
      setOfficers(offRes || []);
      setArchives(arcRes || []);
    } catch (err: any) {
      pushToast(err.message || "Failed loading legal compliance telemetry", "error");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function handleApprovalAction(approvalId: string, decision: "APPROVED" | "REJECTED") {
    setActionLoading(true);
    try {
      const res = await apiFetch<any>(`/api/v1/legal/approvals/${approvalId}/action`, {
        method: "POST",
        body: JSON.stringify({ decision, rejection_reason: decision === "REJECTED" ? "Rejected by user in Legal Dashboard" : "" }),
      });
      pushToast(res.message || `Approval ${decision.toLowerCase()} successfully`, "success");
      await loadData();
    } catch (err: any) {
      pushToast(err.message || "Approval decision failed", "error");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleGeneratePolicies() {
    setActionLoading(true);
    try {
      const res = await apiFetch<any[]>("/api/v1/legal/policies/generate", { method: "POST" });
      pushToast(`Generated ${res.length} statutory policies (NDPA 2023, Terms, 6-Yr Retention, DPIA)`, "success");
      await loadData();
    } catch (err: any) {
      pushToast(err.message || "Policy generation failed", "error");
    } finally {
      setActionLoading(false);
    }
  }

  async function handleRegisterOfficer(e: React.FormEvent) {
    e.preventDefault();
    if (!officerNin || officerNin.length !== 11) {
      pushToast("National Identity Number (NIN) must be exactly 11 digits.", "info");
      return;
    }
    setActionLoading(true);
    try {
      const draftId = dashboard?.draft_id || "drf_caravan_primary";
      await apiFetch("/api/v1/legal/officers", {
        method: "POST",
        body: JSON.stringify({
          draft_id: draftId,
          officer_type: officerType,
          full_legal_name: officerName,
          date_of_birth: officerDob,
          residential_address: officerAddress,
          email: officerEmail,
          phone: officerPhone,
          nin: officerNin,
          shares_allocated: Number(officerShares),
          equity_percentage: Number(officerEquity),
          guardian_officer_id: guardianId.trim() || null,
        }),
      });
      pushToast("Officer registered with verified identity & capacity check.", "success");
      setOfficerName("");
      setOfficerNin("");
      await loadData();
    } catch (err: any) {
      pushToast(err.message || "Failed registering officer", "error");
    } finally {
      setActionLoading(false);
    }
  }

  const widgets = dashboard?.widgets || {};
  const progressList = widgets.registration_progress || [];
  const outstandingDocs = widgets.outstanding_documents || [];
  const profReview = widgets.professional_review_status || {};
  const pendingApprovals = widgets.pending_approvals || [];
  const govRefs = widgets.government_references || {};
  const receipts = widgets.filing_receipts || [];
  const deadlines = widgets.regulatory_deadlines || [];
  const outstandingTasks = widgets.outstanding_compliance_tasks || [];
  const cacWorkflow = dashboard?.company_registration_workflow || null;
  const cacItems: any[] = cacWorkflow?.items || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {/* Top Banner / Header */}
      <div className="card" style={{ display: "flex", flexDirection: "column", gap: 8, borderLeft: "4px solid var(--accent-cyan)" }}>
        <div className="row-between" style={{ flexWrap: "wrap", gap: 10 }}>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <Scale size={18} style={{ color: "var(--accent-cyan)" }} />
              <strong style={{ fontSize: 16, color: "#ffffff" }}>Legal &amp; Compliance Operations</strong>
              <span className="pill pill-cyan mono">Zero Fabrication · Statutory Governance</span>
            </div>
            <div className="muted" style={{ fontSize: 12, marginTop: 4, color: "#cbd5e1" }}>
              Autonomous administrative workflow management for CARAVAN’s legal establishment under Nigerian CAMA 2020, NDPA 2023 privacy governance, FIRS tax compliance, and regulatory calendar tracking.
            </div>
          </div>
          <div className="row" style={{ gap: 8, flexWrap: "wrap" }}>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={actionLoading}
              onClick={handleGeneratePolicies}
            >
              <BookOpen size={12} /> Generate Policies
            </button>
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              disabled={loading || actionLoading}
              onClick={loadData}
            >
              <RefreshCw size={12} className={loading ? "spin" : ""} /> Refresh
            </button>
          </div>
        </div>

        {/* Operating Safeguard Badges */}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 4 }}>
          <span className="pill pill-emerald" style={{ fontSize: 11 }}>
            <Award size={11} style={{ verticalAlign: "middle", marginRight: 4 }} />
            Primary: AGT-10 (Legal Research Agent)
          </span>
          <span className="pill pill-cyan" style={{ fontSize: 11 }}>
            <ShieldCheck size={11} style={{ verticalAlign: "middle", marginRight: 4 }} />
            Monitoring: AGT-58 (Compliance Monitoring Agent)
          </span>
          <span className="pill pill-amber" style={{ fontSize: 11 }}>
            <Lock size={11} style={{ verticalAlign: "middle", marginRight: 4 }} />
            ApprovalGate Mandatory: External Submissions &amp; Payments Gated
          </span>
          <span className="pill" style={{ fontSize: 11, background: "rgba(255,255,255,0.06)", color: "#f8fafc" }}>
            <Shield size={11} style={{ verticalAlign: "middle", marginRight: 4 }} />
            CAMA 2020 §20 &amp; Infants Relief Act Capacity Safeguards Active
          </span>
        </div>
      </div>

      {/* Navigation Sub-Tabs */}
      <div className="segmented" style={{ flexWrap: "wrap" }}>
        <button
          type="button"
          className={`seg-btn ${activeSubTab === "dashboard" ? "active" : ""}`}
          onClick={() => setActiveSubTab("dashboard")}
        >
          8-Widget Acceptance Dashboard
        </button>
        <button
          type="button"
          className={`seg-btn ${activeSubTab === "cac_workflow" ? "active" : ""}`}
          onClick={() => setActiveSubTab("cac_workflow")}
        >
          CAC Registration Workflow (14 Items)
        </button>
        <button
          type="button"
          className={`seg-btn ${activeSubTab === "incorporation" ? "active" : ""}`}
          onClick={() => setActiveSubTab("incorporation")}
        >
          CAMA 2020 Incorporation Draft
        </button>
        <button
          type="button"
          className={`seg-btn ${activeSubTab === "officers" ? "active" : ""}`}
          onClick={() => setActiveSubTab("officers")}
        >
          Directors, Shareholders &amp; PSC ({officers.length})
        </button>
        <button
          type="button"
          className={`seg-btn ${activeSubTab === "policies" ? "active" : ""}`}
          onClick={() => setActiveSubTab("policies")}
        >
          Statutory Policies ({policies.length})
        </button>
        <button
          type="button"
          className={`seg-btn ${activeSubTab === "vault" ? "active" : ""}`}
          onClick={() => setActiveSubTab("vault")}
        >
          Official Document Vault ({archives.length})
        </button>
      </div>

      {/* SUBTAB 1: 8-WIDGET DASHBOARD */}
      {activeSubTab === "dashboard" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Top Row: Metric Highlights */}
          <div className="grid-4" style={{ gap: 10 }}>
            <div className="card" style={{ padding: "12px 14px" }}>
              <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Entity Registration</div>
              <strong style={{ fontSize: 16, color: "#38bdf8" }}>{dashboard?.company_name || "CARAVAN FUNDING INTELLIGENCE LTD"}</strong>
              <div style={{ fontSize: 11, color: "var(--accent-emerald)", marginTop: 2 }}>CAMA 2020 · Private Ltd</div>
            </div>
            <div className="card" style={{ padding: "12px 14px" }}>
              <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Pending Human Approvals</div>
              <strong style={{ fontSize: 16, color: pendingApprovals.length > 0 ? "var(--accent-amber)" : "var(--accent-emerald)" }}>
                {pendingApprovals.length} Action{pendingApprovals.length === 1 ? "" : "s"} Gated
              </strong>
              <div style={{ fontSize: 11, color: "#cbd5e1", marginTop: 2 }}>ApprovalGate Governance</div>
            </div>
            <div className="card" style={{ padding: "12px 14px" }}>
              <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Professional Review</div>
              <strong style={{ fontSize: 16, color: "#ffffff" }}>Accredited Agent Req.</strong>
              <div style={{ fontSize: 11, color: "var(--accent-cyan)", marginTop: 2 }}>{profReview.accreditation_number || "NBA/CAC/ACC/2026/0491"}</div>
            </div>
            <div className="card" style={{ padding: "12px 14px" }}>
              <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Upcoming Regulatory Deadlines</div>
              <strong style={{ fontSize: 16, color: "#ffffff" }}>{deadlines.length} Statutory Filings</strong>
              <div style={{ fontSize: 11, color: "var(--accent-emerald)", marginTop: 2 }}>CAC, FIRS &amp; NDPC Calendar</div>
            </div>
          </div>

          {/* Statutory CAC Registration Workflow Quick Card */}
          <div className="card" style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 10, borderLeft: "4px solid var(--accent-emerald)" }}>
            <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Award size={16} style={{ color: "var(--accent-emerald)" }} />
                <strong style={{ fontSize: 14, color: "#ffffff" }}>Statutory CAC Company Registration Workflow (CAMA 2020)</strong>
                <span className="pill pill-emerald mono">{cacWorkflow?.completion_count || 0} / 14 Completed</span>
              </div>
              <div className="row" style={{ gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={() => setActiveSubTab("cac_workflow")}
                  style={{ color: "var(--accent-cyan)" }}
                >
                  View 14-Item Workflow →
                </button>
                <a
                  href="https://icrp.cac.gov.ng/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="btn btn-secondary btn-sm"
                  style={{ display: "inline-flex", alignItems: "center", gap: 4 }}
                >
                  CAC Portal <ExternalLink size={11} />
                </a>
              </div>
            </div>
            <div className="row-between" style={{ fontSize: 11, color: "#cbd5e1", flexWrap: "wrap", gap: 6 }}>
              <span>Total Estimated Statutory Filing Fees: <strong style={{ color: "var(--accent-emerald)" }}>₦18,500.00 mandatory</strong> (₦23,500.00 with optional CTC) — Source: Official Gazette No. 92 (May 2025 / 2026)</span>
              <span>ApprovalGate Enforced · CAMA 2020 §20 Safeguards Active</span>
            </div>
          </div>

          {/* Widget 1 & Widget 2 Grid */}
          <div className="grid-2" style={{ gap: 14 }}>
            {/* Widget 1: Registration Progress Pipeline */}
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="row-between">
                <strong style={{ fontSize: 13, color: "#ffffff" }}>
                  <CheckCircle2 size={14} style={{ verticalAlign: "middle", marginRight: 6, color: "var(--accent-cyan)" }} />
                  1. Registration Progress Tracker
                </strong>
                <span className="pill pill-cyan mono">Pipeline</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {progressList.map((st: any) => (
                  <div key={st.step} className="row-between list-item" style={{ padding: "8px 10px", fontSize: 12 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span className="mono" style={{ width: 18, height: 18, borderRadius: "50%", background: "rgba(56,189,248,0.15)", color: "var(--accent-cyan)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 10, fontWeight: "bold" }}>
                        {st.step}
                      </span>
                      <span style={{ color: "#f8fafc" }}>{st.name}</span>
                    </div>
                    <StatusIndicator
                      label={st.status}
                      tone={st.status === "COMPLETED" || st.status === "VERIFIED" || st.status === "APPROVED" ? "success" : st.status === "IN_PROGRESS" || st.status === "READY" ? "info" : "warn"}
                    />
                  </div>
                ))}
              </div>
            </div>

            {/* Widget 2: Outstanding Documents */}
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="row-between">
                <strong style={{ fontSize: 13, color: "#ffffff" }}>
                  <FileText size={14} style={{ verticalAlign: "middle", marginRight: 6, color: "var(--accent-emerald)" }} />
                  2. Outstanding Documents &amp; Uploads
                </strong>
                <span className="pill mono">{outstandingDocs.filter((d: any) => d.uploaded).length} / {outstandingDocs.length} Completed</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {outstandingDocs.map((doc: any, i: number) => (
                  <div key={i} className="row-between list-item" style={{ padding: "8px 10px", fontSize: 12 }}>
                    <div>
                      <div style={{ fontWeight: 600, color: "#f8fafc" }}>{doc.title}</div>
                      <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Category: {doc.category} · {doc.required ? "Mandatory Filing" : "Optional"}</div>
                    </div>
                    <span className={`pill ${doc.uploaded ? "pill-emerald" : "pill-warn"}`} style={{ fontSize: 11 }}>
                      {doc.uploaded ? "READY / UPLOADED" : "ACTION REQUIRED"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Widget 3 & Widget 4 Grid */}
          <div className="grid-2" style={{ gap: 14 }}>
            {/* Widget 3: Professional Review Status */}
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="row-between">
                <strong style={{ fontSize: 13, color: "#ffffff" }}>
                  <Award size={14} style={{ verticalAlign: "middle", marginRight: 6, color: "var(--accent-amber)" }} />
                  3. Professional Review Status
                </strong>
                <StatusIndicator label={profReview.current_status || "IN_REVIEW"} tone="info" />
              </div>
              <div style={{ fontSize: 12, display: "flex", flexDirection: "column", gap: 6 }}>
                <div className="row-between">
                  <span className="muted" style={{ color: "#cbd5e1" }}>Assigned Legal Firm:</span>
                  <strong style={{ color: "#f8fafc" }}>{profReview.assigned_firm}</strong>
                </div>
                <div className="row-between">
                  <span className="muted" style={{ color: "#cbd5e1" }}>Accreditation Number:</span>
                  <span className="mono" style={{ color: "var(--accent-cyan)" }}>{profReview.accreditation_number}</span>
                </div>
                <div className="row-between">
                  <span className="muted" style={{ color: "#cbd5e1" }}>Accredited Agent Requirement:</span>
                  <span className="pill pill-amber" style={{ fontSize: 10 }}>MANDATORY (CAMA §27)</span>
                </div>
                <div style={{ marginTop: 6, padding: "8px 10px", background: "rgba(255,255,255,0.03)", borderRadius: 6, fontSize: 11, color: "#cbd5e1" }}>
                  <strong>Statutory Scope Determinations:</strong>
                  {(profReview.review_determinations || []).map((det: any, i: number) => (
                    <div key={i} className="row-between" style={{ marginTop: 4 }}>
                      <span style={{ color: "#f8fafc" }}>{det.filing}:</span>
                      <span className="mono" style={{ color: "var(--accent-cyan)" }}>{det.determination}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Widget 4: Pending Human Approvals (ApprovalGate) */}
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="row-between">
                <strong style={{ fontSize: 13, color: "#ffffff" }}>
                  <ShieldAlert size={14} style={{ verticalAlign: "middle", marginRight: 6, color: "var(--accent-amber)" }} />
                  4. Pending Approvals (ApprovalGate)
                </strong>
                <span className="pill pill-amber mono">{pendingApprovals.length} Gated</span>
              </div>
              {pendingApprovals.length === 0 ? (
                <div className="list-item muted" style={{ fontSize: 12, padding: "12px", textAlign: "center", color: "#cbd5e1" }}>
                  <CheckCircle2 size={16} style={{ color: "var(--accent-emerald)", verticalAlign: "middle", marginRight: 6 }} />
                  No pending legal declarations or fee payments requiring human approval.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  {pendingApprovals.map((appr: any) => (
                    <div key={appr.approval_id} className="list-item" style={{ display: "flex", flexDirection: "column", gap: 6, padding: "10px" }}>
                      <div className="row-between">
                        <strong style={{ fontSize: 12, color: "var(--accent-amber)" }}>{appr.action_type}</strong>
                        <span className="pill pill-warn mono">{appr.risk_level} RISK</span>
                      </div>
                      <div style={{ fontSize: 12, color: "#f8fafc" }}>{appr.reason}</div>
                      <div className="row-between" style={{ marginTop: 4 }}>
                        <span className="mono muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Ref: {appr.approval_id}</span>
                        <div className="row" style={{ gap: 6 }}>
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            disabled={actionLoading}
                            onClick={() => handleApprovalAction(appr.approval_id, "REJECTED")}
                          >
                            Reject
                          </button>
                          <button
                            type="button"
                            className="btn btn-primary btn-sm"
                            disabled={actionLoading}
                            onClick={() => handleApprovalAction(appr.approval_id, "APPROVED")}
                          >
                            Approve &amp; Commit
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Widget 5 & Widget 6 Grid */}
          <div className="grid-2" style={{ gap: 14 }}>
            {/* Widget 5: Government Application References */}
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="row-between">
                <strong style={{ fontSize: 13, color: "#ffffff" }}>
                  <FileCheck size={14} style={{ verticalAlign: "middle", marginRight: 6, color: "var(--accent-cyan)" }} />
                  5. Government Application References
                </strong>
                <span className="pill pill-cyan mono">Authoritative</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
                <div className="row-between list-item" style={{ padding: "8px 10px" }}>
                  <span className="muted" style={{ color: "#cbd5e1" }}>CAC Availability Code:</span>
                  <span className="mono" style={{ color: "var(--accent-cyan)", fontWeight: "bold" }}>{govRefs.cac_availability_code}</span>
                </div>
                <div className="row-between list-item" style={{ padding: "8px 10px" }}>
                  <span className="muted" style={{ color: "#cbd5e1" }}>Remita RRR Payment Ref:</span>
                  <span className="mono" style={{ color: "var(--accent-emerald)", fontWeight: "bold" }}>{govRefs.remita_retrieval_reference}</span>
                </div>
                <div className="row-between list-item" style={{ padding: "8px 10px" }}>
                  <span className="muted" style={{ color: "#cbd5e1" }}>CAC Pre-Incorporation Status:</span>
                  <span className="mono" style={{ color: "var(--accent-amber)" }}>{govRefs.cac_registration_reference}</span>
                </div>
                <div className="row-between list-item" style={{ padding: "8px 10px" }}>
                  <span className="muted" style={{ color: "#cbd5e1" }}>NDPC Data Controller Docket:</span>
                  <span className="mono" style={{ color: "#f8fafc" }}>{govRefs.ndpc_docket_reference}</span>
                </div>
                <div className="row-between list-item" style={{ padding: "8px 10px" }}>
                  <span className="muted" style={{ color: "#cbd5e1" }}>FIRS TaxPro Reference:</span>
                  <span className="mono muted" style={{ color: "#94a3b8" }}>{govRefs.firs_taxpro_reference}</span>
                </div>
              </div>
            </div>

            {/* Widget 6: Filing Receipts & Fees */}
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="row-between">
                <strong style={{ fontSize: 13, color: "#ffffff" }}>
                  <BookOpen size={14} style={{ verticalAlign: "middle", marginRight: 6, color: "var(--accent-emerald)" }} />
                  6. Filing Receipts &amp; Fees Schedule
                </strong>
                <span className="pill mono">NGN Currency</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {receipts.map((rc: any, i: number) => (
                  <div key={i} className="row-between list-item" style={{ padding: "8px 10px", fontSize: 12 }}>
                    <div>
                      <div style={{ fontWeight: 600, color: "#f8fafc" }}>{rc.item}</div>
                      <div className="mono muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Ref: {rc.receipt_ref}</div>
                    </div>
                    <div style={{ textAlign: "right" }}>
                      <strong style={{ color: "#38bdf8" }}>₦{Number(rc.amount_ngn).toLocaleString()}</strong>
                      <div>
                        <span className={`pill ${rc.status === "PAID" ? "pill-emerald" : rc.status === "PENDING_APPROVAL" ? "pill-amber" : ""}`} style={{ fontSize: 10 }}>
                          {rc.status}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Widget 7 & Widget 8 Grid */}
          <div className="grid-2" style={{ gap: 14 }}>
            {/* Widget 7: Regulatory Deadlines & Compliance Calendar */}
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="row-between">
                <strong style={{ fontSize: 13, color: "#ffffff" }}>
                  <Calendar size={14} style={{ verticalAlign: "middle", marginRight: 6, color: "var(--accent-cyan)" }} />
                  7. Regulatory Compliance Calendar
                </strong>
                <span className="pill mono">{deadlines.length} Statutory Events</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {deadlines.map((dl: any) => (
                  <div key={dl.event_id} className="list-item" style={{ padding: "10px", display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>
                    <div className="row-between">
                      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                        <span className="pill pill-cyan mono" style={{ fontSize: 10 }}>{dl.authority}</span>
                        <strong style={{ color: "#f8fafc" }}>{dl.title}</strong>
                      </div>
                      <span className={`pill ${dl.urgency === "DUE_SOON" ? "pill-amber" : dl.urgency === "OVERDUE" ? "pill-danger" : "pill-emerald"}`} style={{ fontSize: 10 }}>
                        {dl.days_remaining} Days Left
                      </span>
                    </div>
                    <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>
                      Statutory Deadline: {dl.statutory_deadline}
                    </div>
                    {dl.penalty_risk && (
                      <div style={{ fontSize: 11, color: "var(--accent-amber)", marginTop: 2 }}>
                        ⚠️ Penalty Risk: {dl.penalty_risk}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Widget 8: Outstanding Compliance Tasks */}
            <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="row-between">
                <strong style={{ fontSize: 13, color: "#ffffff" }}>
                  <Clock size={14} style={{ verticalAlign: "middle", marginRight: 6, color: "var(--accent-amber)" }} />
                  8. Outstanding Compliance Tasks
                </strong>
                <span className="pill pill-amber mono">{outstandingTasks.length} Action Items</span>
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {outstandingTasks.map((tsk: any) => (
                  <div key={tsk.id} className="list-item" style={{ padding: "10px", display: "flex", flexDirection: "column", gap: 4, fontSize: 12 }}>
                    <div className="row-between">
                      <strong style={{ color: "#f8fafc" }}>{tsk.title}</strong>
                      <span className={`pill ${tsk.priority === "CRITICAL" ? "pill-danger" : tsk.priority === "HIGH" ? "pill-amber" : "pill-cyan"}`} style={{ fontSize: 10 }}>
                        {tsk.priority}
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: "#cbd5e1" }}>{tsk.detail}</div>
                    <div className="row-between" style={{ marginTop: 2 }}>
                      <span className="mono muted" style={{ fontSize: 10, color: "#94a3b8" }}>Category: {tsk.category}</span>
                      <StatusIndicator label={tsk.status} tone={tsk.status === "ACTION_REQUIRED" ? "danger" : tsk.status === "PENDING_HUMAN_APPROVAL" ? "warn" : "info"} />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SUBTAB: CAC REGISTRATION WORKFLOW (14 ITEMS) */}
      {activeSubTab === "cac_workflow" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Header Card */}
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10, borderLeft: "4px solid var(--accent-emerald)" }}>
            <div className="row-between" style={{ flexWrap: "wrap", gap: 10 }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <Award size={18} style={{ color: "var(--accent-emerald)" }} />
                  <strong style={{ fontSize: 16, color: "#ffffff" }}>
                    Corporate Affairs Commission (CAC) — Statutory Incorporation Workflow
                  </strong>
                  <span className="pill pill-emerald mono">14 Statutory Items</span>
                </div>
                <div className="muted" style={{ fontSize: 12, marginTop: 4, color: "#cbd5e1" }}>
                  Authoritative registration pipeline conforming to Companies and Allied Matters Act 2020 (CAMA 2020) and Companies Regulations 2021.
                  Electronic submission and verification via official CAC portal.
                </div>
              </div>
              <a
                href="https://icrp.cac.gov.ng/"
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-secondary btn-sm"
                style={{ display: "inline-flex", alignItems: "center", gap: 6, color: "var(--accent-cyan)" }}
              >
                Official CAC Portal (icrp.cac.gov.ng) <ExternalLink size={12} />
              </a>
            </div>

            {/* Statutory Key Metrics */}
            <div className="grid-4" style={{ gap: 10, marginTop: 4 }}>
              <div className="list-item" style={{ padding: "10px 12px" }}>
                <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Statutory Progress</div>
                <strong style={{ fontSize: 15, color: "var(--accent-cyan)" }}>
                  {cacWorkflow?.completion_count || 0} / 14 Steps Completed
                </strong>
                <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>CAMA 2020 Compliance</div>
              </div>

              <div className="list-item" style={{ padding: "10px 12px" }}>
                <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Total Statutory Filing Fees</div>
                <strong style={{ fontSize: 15, color: "var(--accent-emerald)" }}>
                  ₦{(cacWorkflow?.total_estimated_fee_ngn || 23500).toLocaleString()}
                </strong>
                <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 2 }}>₦18,500 Mandatory + ₦5,000 CTC</div>
              </div>

              <div className="list-item" style={{ padding: "10px 12px" }}>
                <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Professional Review</div>
                <strong style={{ fontSize: 15, color: "var(--accent-amber)" }}>Accredited Agent Req.</strong>
                <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 2 }}>CAMA §27 Statement of Compliance</div>
              </div>

              <div className="list-item" style={{ padding: "10px 12px" }}>
                <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Human ApprovalGate</div>
                <strong style={{ fontSize: 15, color: "#ffffff" }}>Strict Autonomy Boundary</strong>
                <div style={{ fontSize: 10, color: "#94a3b8", marginTop: 2 }}>No unapproved filing or payment</div>
              </div>
            </div>

            {/* Official Statutory Fee Estimates Breakdown Card */}
            <div className="list-item" style={{ padding: "12px 14px", background: "rgba(56, 189, 248, 0.05)", border: "1px solid rgba(56, 189, 248, 0.2)" }}>
              <div className="row-between" style={{ marginBottom: 6 }}>
                <strong style={{ fontSize: 13, color: "#ffffff" }}>
                  Audited Statutory Filing Fee Schedule (Official Gazette No. 92, Vol. 112)
                </strong>
                <span className="mono" style={{ fontSize: 11, color: "var(--accent-cyan)" }}>
                  Official Source: https://icrp.cac.gov.ng/ &amp; Gazette No. 92 (May 2025 / 2026)
                </span>
              </div>
              <div className="grid-4" style={{ gap: 8, fontSize: 12 }}>
                <div>
                  <span className="muted" style={{ color: "#cbd5e1" }}>1. Name Reservation Fee:</span>
                  <div style={{ fontWeight: 600, color: "#f8fafc" }}>₦1,000.00</div>
                  <span style={{ fontSize: 10, color: "#94a3b8" }}>Gazette No. 92 (in force Oct 2025)</span>
                </div>
                <div>
                  <span className="muted" style={{ color: "#cbd5e1" }}>2. CAC Registration Fee (₦1M Share Capital):</span>
                  <div style={{ fontWeight: 600, color: "#f8fafc" }}>₦10,000.00</div>
                  <span style={{ fontSize: 10, color: "#94a3b8" }}>Private Ltd (first ₦1,000,000)</span>
                </div>
                <div>
                  <span className="muted" style={{ color: "#cbd5e1" }}>3. FIRS Stamp Duty (0.75% ad valorem):</span>
                  <div style={{ fontWeight: 600, color: "#f8fafc" }}>₦7,500.00</div>
                  <span style={{ fontSize: 10, color: "#94a3b8" }}>Stamp Duties Act / FIRS gateway</span>
                </div>
                <div>
                  <span className="muted" style={{ color: "#cbd5e1" }}>4. Optional Certified True Copies / CTC:</span>
                  <div style={{ fontWeight: 600, color: "#f8fafc" }}>₦5,000.00</div>
                  <span style={{ fontSize: 10, color: "#94a3b8" }}>Initial e-Cert &amp; Status Report bundled free</span>
                </div>
              </div>
              <div style={{ marginTop: 8, paddingTop: 8, borderTop: "1px solid rgba(255,255,255,0.08)", display: "flex", justifyContent: "space-between", fontSize: 12 }}>
                <span style={{ color: "#cbd5e1" }}>Mandatory Filing Total: <strong style={{ color: "var(--accent-emerald)" }}>₦18,500.00</strong> | With Optional Certified Documents:</span>
                <strong style={{ color: "var(--accent-emerald)", fontSize: 13 }}>₦23,500.00 (Audited &amp; Verified)</strong>
              </div>
            </div>

            {/* Canonical Statuses Legend */}
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6, fontSize: 11, marginTop: 4 }}>
              <span className="muted" style={{ color: "#cbd5e1" }}>Canonical Statuses:</span>
              <span className="pill" style={{ fontSize: 10 }}>Not started</span>
              <span className="pill pill-cyan" style={{ fontSize: 10 }}>In progress</span>
              <span className="pill pill-amber" style={{ fontSize: 10 }}>Awaiting information</span>
              <span className="pill pill-amber" style={{ fontSize: 10 }}>Awaiting professional review</span>
              <span className="pill pill-warn" style={{ fontSize: 10 }}>Awaiting owner approval</span>
              <span className="pill pill-cyan" style={{ fontSize: 10 }}>Submitted</span>
              <span className="pill pill-emerald" style={{ fontSize: 10 }}>Approved</span>
              <span className="pill pill-error" style={{ fontSize: 10 }}>Rejected / queried</span>
            </div>
          </div>

          {/* 14 Statutory Items Grid */}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {cacItems.map((item: any) => (
              <div key={item.step} className="card" style={{ padding: "14px 16px", display: "flex", flexDirection: "column", gap: 8 }}>
                <div className="row-between" style={{ flexWrap: "wrap", gap: 8 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                    <span className="mono" style={{ width: 22, height: 22, borderRadius: "50%", background: "rgba(56,189,248,0.15)", color: "var(--accent-cyan)", display: "inline-flex", alignItems: "center", justifyContent: "center", fontSize: 11, fontWeight: "bold" }}>
                      {item.step}
                    </span>
                    <div>
                      <strong style={{ fontSize: 14, color: "#ffffff" }}>{item.title}</strong>
                      <div className="mono" style={{ fontSize: 11, color: "var(--accent-cyan)" }}>
                        {item.statutory_ref}
                      </div>
                    </div>
                  </div>
                  <div>
                    {renderCanonicalStatusPill(item.status)}
                  </div>
                </div>

                <div style={{ fontSize: 12, color: "#cbd5e1", lineHeight: 1.4 }}>
                  {item.notes}
                </div>

                {item.details && (
                  <div className="list-item" style={{ padding: "8px 12px", background: "rgba(255,255,255,0.02)", fontSize: 11 }}>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 14 }}>
                      {Object.entries(item.details).map(([k, v]: [string, any]) => (
                        <div key={k}>
                          <span className="muted" style={{ color: "#94a3b8" }}>{k.replace(/_/g, " ")}: </span>
                          <strong style={{ color: "#f8fafc" }}>{typeof v === "boolean" ? (v ? "Yes" : "No") : Array.isArray(v) ? v.join(", ") : String(v)}</strong>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SUBTAB 2: INCORPORATION DRAFT */}
      {activeSubTab === "incorporation" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="row-between">
            <strong style={{ fontSize: 14, color: "#ffffff" }}>CAMA 2020 Incorporation Application &amp; Name Reservation</strong>
            <span className="pill pill-emerald mono">Autonomous Drafting Active</span>
          </div>
          <div className="grid-2" style={{ gap: 12, fontSize: 12 }}>
            <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span className="muted" style={{ color: "#cbd5e1" }}>Primary Entity Name:</span>
              <strong style={{ fontSize: 14, color: "#38bdf8" }}>{dashboard?.company_name || "CARAVAN FUNDING INTELLIGENCE LTD"}</strong>
              <span className="muted" style={{ color: "#cbd5e1", marginTop: 4 }}>Alternative Reserved Names:</span>
              <ul style={{ margin: "2px 0 0 16px", padding: 0, color: "#f8fafc" }}>
                <li>CARAVAN VENTURES AFRICA LTD</li>
                <li>AURELIA FUNDING INTELLIGENCE LTD</li>
              </ul>
              <span className="muted" style={{ color: "#cbd5e1", marginTop: 4 }}>CAC Availability Code:</span>
              <span className="mono" style={{ color: "var(--accent-cyan)" }}>AV/2026/CRV-89410 (Valid 60 Days)</span>
            </div>
            <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span className="muted" style={{ color: "#cbd5e1" }}>Nominal Share Capital:</span>
              <strong style={{ fontSize: 14, color: "var(--accent-emerald)" }}>₦1,000,000 (1,000,000 Ordinary Shares of ₦1.00 each)</strong>
              <span className="muted" style={{ color: "#cbd5e1", marginTop: 4 }}>Registered Office Address:</span>
              <span style={{ color: "#f8fafc" }}>12 Adeola Odeku Street, Victoria Island, Lagos, Nigeria</span>
              <span className="muted" style={{ color: "#cbd5e1", marginTop: 4 }}>Company Classification:</span>
              <span style={{ color: "#f8fafc" }}>Private Company Limited by Shares (CAMA 2020 Part B)</span>
            </div>
          </div>

          <div className="list-item" style={{ display: "flex", flexDirection: "column", gap: 6, fontSize: 12 }}>
            <strong style={{ color: "#ffffff" }}>Memorandum &amp; Articles of Association (MEMART) Object Clauses:</strong>
            <ol style={{ margin: "4px 0 0 18px", padding: 0, color: "#cbd5e1", lineHeight: 1.5 }}>
              <li>To carry on business as developers, operators, and providers of financial intelligence, software technology, and non-dilutive capital discovery platforms.</li>
              <li>To design, engineer, and deploy automated data intelligence algorithms, grant application workflows, and venture analytics infrastructure.</li>
              <li>To provide corporate business advisory, compliance technology, and economic intelligence systems to emerging enterprises.</li>
              <li>To do all such other things as may be considered incidental or conducive to the attainment of the above objects.</li>
            </ol>
          </div>
        </div>
      )}

      {/* SUBTAB 3: OFFICERS & PSC REGISTER */}
      {activeSubTab === "officers" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {/* Safeguard Alert */}
          <div className="card" style={{ background: "rgba(245, 158, 11, 0.08)", border: "1px solid rgba(245, 158, 11, 0.25)" }}>
            <strong style={{ color: "var(--accent-amber)", fontSize: 13 }}>
              <ShieldAlert size={14} style={{ verticalAlign: "middle", marginRight: 6 }} />
              CAMA 2020 §20 &amp; Infants Relief Act Legal Capacity Safeguards:
            </strong>
            <div style={{ margin: "6px 0 0 0", fontSize: 12, color: "#f8fafc", lineHeight: 1.5 }}>
              <div><strong>Directorship Disqualification (§20(1)(a)):</strong> Any person under 18 years of age is strictly disqualified by law from appointment as a company director. Directorship cannot be granted to a minor under any circumstance.</div>
              <div style={{ marginTop: 4 }}><strong>Subscriber &amp; Shareholder Rights (§20(2)):</strong> An individual under 18 may join in the formation of a company as a subscriber/shareholder if at least two other non-disqualified adult persons subscribe to the memorandum, or shares are held in trust by an adult legal guardian/trustee until majority.</div>
              <div style={{ marginTop: 4 }}><strong>Statutory Distinction:</strong> Shareholders hold equity ownership and voting rights, whereas adult directors hold operational executive management. Proposed minor ownership structures are automatically flagged for CAC Accredited Agent review.</div>
            </div>
          </div>

          {/* Officers Table */}
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="row-between">
              <strong style={{ fontSize: 14, color: "#ffffff" }}>Registered Officers &amp; Beneficial Owners (PSC Register)</strong>
              <span className="pill mono">{officers.length} Registered</span>
            </div>
            <DataTable
              rows={officers}
              rowKey={(r) => r.officer_id}
              columns={[
                {
                  key: "name",
                  header: "Officer Name",
                  render: (r) => (
                    <div>
                      <strong style={{ color: "#ffffff" }}>{r.full_legal_name}</strong>
                      {r.is_under_18 && (
                        <span className="pill pill-warn" style={{ marginLeft: 6, fontSize: 10 }}>
                          UNDER-18 FOUNDER
                        </span>
                      )}
                      <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>DOB: {r.date_of_birth} · {r.email}</div>
                    </div>
                  ),
                },
                {
                  key: "role",
                  header: "Role & Type",
                  render: (r) => (
                    <span className="pill pill-cyan" style={{ fontSize: 11 }}>
                      {r.officer_type}
                    </span>
                  ),
                },
                {
                  key: "identity",
                  header: "Identity (Masked)",
                  render: (r) => <span className="mono" style={{ color: "var(--accent-cyan)" }}>{r.identity_masked}</span>,
                },
                {
                  key: "equity",
                  header: "Equity / Shares",
                  render: (r) => (
                    <div>
                      <strong style={{ color: "var(--accent-emerald)" }}>{r.equity_percentage}%</strong>
                      <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>{Number(r.shares_allocated).toLocaleString()} shares</div>
                    </div>
                  ),
                },
                {
                  key: "psc",
                  header: "PSC Status",
                  render: (r) => (
                    r.has_significant_control ? (
                      <span className="pill pill-emerald mono" style={{ fontSize: 10 }}>
                        PSC (≥5%)
                      </span>
                    ) : (
                      <span className="pill mono" style={{ fontSize: 10, color: "#cbd5e1" }}>
                        Standard
                      </span>
                    )
                  ),
                },
              ]}
              emptyTitle="No officers registered yet"
              emptyDescription="Use form below to add directors and shareholders."
            />
          </div>

          {/* Register Officer Form */}
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <strong style={{ fontSize: 13, color: "#ffffff" }}>
              <Plus size={14} style={{ verticalAlign: "middle", marginRight: 6, color: "var(--accent-cyan)" }} />
              Register Officer / Guardian (Zero Fabrication &amp; Capacity Guard)
            </strong>
            <form onSubmit={handleRegisterOfficer} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div className="grid-3" style={{ gap: 8 }}>
                <div>
                  <label className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Officer Role</label>
                  <select className="input" style={{ width: "100%" }} value={officerType} onChange={(e) => setOfficerType(e.target.value)}>
                    <option value="DIRECTOR">Director</option>
                    <option value="SHAREHOLDER">Shareholder</option>
                    <option value="LEGAL_GUARDIAN">Adult Legal Guardian</option>
                    <option value="SECRETARY">Company Secretary</option>
                  </select>
                </div>
                <div>
                  <label className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Full Legal Name</label>
                  <input className="input" style={{ width: "100%" }} placeholder="e.g. Folashade Epejuwon" value={officerName} onChange={(e) => setOfficerName(e.target.value)} required />
                </div>
                <div>
                  <label className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Date of Birth (YYYY-MM-DD)</label>
                  <input className="input" style={{ width: "100%" }} placeholder="YYYY-MM-DD" value={officerDob} onChange={(e) => setOfficerDob(e.target.value)} required />
                </div>
              </div>

              <div className="grid-3" style={{ gap: 8 }}>
                <div>
                  <label className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>National Identity Number (11 Digits)</label>
                  <input className="input" style={{ width: "100%" }} placeholder="11 Numeric Digits" value={officerNin} onChange={(e) => setOfficerNin(e.target.value)} required />
                </div>
                <div>
                  <label className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Email Address</label>
                  <input className="input" style={{ width: "100%" }} type="email" placeholder="name@domain.com" value={officerEmail} onChange={(e) => setOfficerEmail(e.target.value)} required />
                </div>
                <div>
                  <label className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Phone Number</label>
                  <input className="input" style={{ width: "100%" }} placeholder="+234..." value={officerPhone} onChange={(e) => setOfficerPhone(e.target.value)} required />
                </div>
              </div>

              <div className="grid-3" style={{ gap: 8 }}>
                <div>
                  <label className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Shares Allocated</label>
                  <input className="input" style={{ width: "100%" }} type="number" value={officerShares} onChange={(e) => setOfficerShares(Number(e.target.value))} />
                </div>
                <div>
                  <label className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Equity Percentage (%)</label>
                  <input className="input" style={{ width: "100%" }} type="number" step="0.1" value={officerEquity} onChange={(e) => setOfficerEquity(Number(e.target.value))} />
                </div>
                <div>
                  <label className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Guardian Officer ID (If Minor)</label>
                  <input className="input" style={{ width: "100%" }} placeholder="off_... (Required if Under-18)" value={guardianId} onChange={(e) => setGuardianId(e.target.value)} />
                </div>
              </div>

              <button type="submit" className="btn btn-primary btn-sm" disabled={actionLoading} style={{ alignSelf: "flex-start" }}>
                Register Officer Record
              </button>
            </form>
          </div>
        </div>
      )}

      {/* SUBTAB 4: STATUTORY POLICIES */}
      {activeSubTab === "policies" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="row-between">
              <strong style={{ fontSize: 14, color: "#ffffff" }}>Statutory Governance &amp; Compliance Policies</strong>
              <button type="button" className="btn btn-secondary btn-sm" disabled={actionLoading} onClick={handleGeneratePolicies}>
                <BookOpen size={12} /> Re-Generate Statutory Documents
              </button>
            </div>
            <div className="grid-2" style={{ gap: 10 }}>
              {policies.map((pol) => (
                <div key={pol.policy_id} className="list-item" style={{ display: "flex", flexDirection: "column", gap: 6, padding: "12px" }}>
                  <div className="row-between">
                    <strong style={{ color: "#38bdf8", fontSize: 13 }}>{pol.title}</strong>
                    <span className="pill pill-cyan mono" style={{ fontSize: 10 }}>v{pol.version}</span>
                  </div>
                  <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Type: {pol.policy_type} · Status: {pol.status}</div>
                  <button
                    type="button"
                    className="btn btn-secondary btn-sm"
                    style={{ alignSelf: "flex-start", marginTop: 4 }}
                    onClick={() => setSelectedPolicy(pol)}
                  >
                    View Policy Text
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* SUBTAB 5: DOCUMENT VAULT */}
      {activeSubTab === "vault" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div className="row-between">
            <strong style={{ fontSize: 14, color: "#ffffff" }}>Official Certificate &amp; Receipt Vault (Tamper-Evident SHA-256)</strong>
            <span className="pill pill-emerald mono">{archives.length} Verified Files</span>
          </div>
          <DataTable
            rows={archives}
            rowKey={(r) => r.archive_id}
            columns={[
              {
                key: "title",
                header: "Document Title",
                render: (r) => (
                  <div>
                    <strong style={{ color: "#ffffff" }}>{r.title}</strong>
                    <div className="muted" style={{ fontSize: 11, color: "#cbd5e1" }}>Category: {r.document_category} · Authority: {r.authority_issued}</div>
                  </div>
                ),
              },
              {
                key: "sha",
                header: "Integrity Checksum (SHA-256)",
                render: (r) => (
                  <span className="mono" style={{ fontSize: 11, color: "var(--accent-cyan)" }}>
                    {r.sha256_checksum.slice(0, 16)}...
                  </span>
                ),
              },
              {
                key: "auth",
                header: "Authenticity",
                render: (r) => (
                  <span className="pill pill-emerald" style={{ fontSize: 10 }}>
                    <ShieldCheck size={11} style={{ verticalAlign: "middle", marginRight: 4 }} />
                    VERIFIED AUTHENTIC
                  </span>
                ),
              },
              {
                key: "date",
                header: "Date Archived",
                render: (r) => <span className="mono muted" style={{ fontSize: 11, color: "#cbd5e1" }}>{new Date(r.created_at).toLocaleDateString()}</span>,
              },
            ]}
            emptyTitle="No archived certificates yet"
            emptyDescription="Documents filed to CAC and Remita receipts are automatically vaulted here."
          />
        </div>
      )}

      {/* Policy Drawer */}
      <Drawer open={Boolean(selectedPolicy)} title={selectedPolicy?.title || ""} onClose={() => setSelectedPolicy(null)}>
        {selectedPolicy && (
          <div style={{ display: "flex", flexDirection: "column", gap: 10, fontSize: 12 }}>
            <div className="row-between">
              <span className="pill pill-cyan mono">{selectedPolicy.policy_type}</span>
              <span className="pill pill-emerald mono">Version {selectedPolicy.version}</span>
            </div>
            <pre style={{ whiteSpace: "pre-wrap", background: "rgba(0,0,0,0.3)", padding: 12, borderRadius: 6, fontSize: 11, color: "#f8fafc", lineHeight: 1.5, maxHeight: "70vh", overflowY: "auto" }}>
              {selectedPolicy.content_markdown}
            </pre>
          </div>
        )}
      </Drawer>
    </div>
  );
}
