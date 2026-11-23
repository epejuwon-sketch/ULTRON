import React, { useEffect, useState } from "react";
import { Activity, Globe, RefreshCw, Search } from "lucide-react";
import { apiFetch } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import type { ModulePageProps } from "../types/module";
import { AtlasMapView, CaravanView, IntelligenceView } from "../components/OpsViews";
import {
  ErrorState,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  StatusIndicator,
  useToast,
} from "../components/ui/DesignSystem";
import {
  ProvenanceBar,
  ReadableSummary,
  SourcesList,
  TechnicalDiagnostics,
} from "../components/ui/HumanPresentation";

export default function ResearchModulePage({ subPage, onSelectSubPage }: ModulePageProps) {
  const mod = getModule("research");
  const page = getSubPage("research", subPage);
  const { pushToast } = useToast();

  const [query, setQuery] = useState("");
  const [fetchUrl, setFetchUrl] = useState("");
  const [searchRes, setSearchRes] = useState<any>(null);
  const [fetchRes, setFetchRes] = useState<any>(null);
  const [researchDiag, setResearchDiag] = useState<any>(null);
  const [probingDiag, setProbingDiag] = useState(false);
  const [compQuery, setCompQuery] = useState("");
  const [compRes, setCompRes] = useState<any>(null);
  const [forecast, setForecast] = useState<any>(null);
  const [turbo, setTurbo] = useState<any>(null);
  const [error, setError] = useState("");

  async function loadResearchDiagnostics(liveProbe = false) {
    if (liveProbe) setProbingDiag(true);
    try {
      const qs = liveProbe
        ? `?live=true&query=${encodeURIComponent(query.trim() || "Lamborghini Aventador SVJ price")}`
        : "?live=false";
      const res = await apiFetch<any>(`/api/v1/research/diagnostics${qs}`);
      setResearchDiag(res);
      if (liveProbe) {
        pushToast(
          `Live research connectivity probe completed (${res.available_providers_count || 0} provider(s) available).`,
          "success"
        );
      }
    } catch (e: any) {
      if (liveProbe) pushToast(e.message, "error");
    } finally {
      if (liveProbe) setProbingDiag(false);
    }
  }

  async function loadPredictive() {
    setError("");
    try {
      const [fc, tb] = await Promise.all([
        apiFetch<any>("/api/v1/finance/forecast?months=6").catch(() => null),
        apiFetch<any>("/api/v1/turbo/stats").catch(() => null),
      ]);
      setForecast(fc);
      setTurbo(tb);
    } catch (e: any) {
      setError(e.message);
    }
  }

  useEffect(() => {
    if (subPage === "predictive") loadPredictive();
    if (subPage === "workspace" || subPage === "web") {
      loadResearchDiagnostics(false);
    }
  }, [subPage]);

  async function runWebSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/research/search", {
        method: "POST",
        body: {
          query: query.trim(),
          max_results: 8,
          is_pricing_query: /price|cost|worth|msrp|for sale|listings|auction/i.test(query),
          fetch_source_pages: true,
        },
      });
      setSearchRes(res);
      loadResearchDiagnostics(false);
      pushToast(`Web research returned ${(res.verified_sources || []).length} verified source(s).`, "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function runWebFetch(e: React.FormEvent) {
    e.preventDefault();
    if (!fetchUrl.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/research/fetch", {
        method: "POST",
        body: { url: fetchUrl.trim() },
      });
      setFetchRes(res);
      pushToast("SSRF-guarded public page fetched.", "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  async function runCompetitor(e: React.FormEvent) {
    e.preventDefault();
    if (!compQuery.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/atlas/shopping/research", {
        method: "POST",
        body: { query: compQuery.trim(), max_budget_usd: 1000 },
      });
      setCompRes(res);
      pushToast("Competitive comparison research completed.", "success");
    } catch (err: any) {
      pushToast(err.message, "error");
    }
  }

  const renderDiagnosticsCard = () => (
    <div className="card" style={{ marginTop: 14 }}>
      <div className="card-title">
        <span>Live Research Connectivity Diagnostics</span>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={probingDiag}
          onClick={() => loadResearchDiagnostics(true)}
        >
          <Activity size={13} /> {probingDiag ? "Probing Live Providers..." : "Run Live Connectivity Probe"}
        </button>
      </div>
      {researchDiag ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div className="row" style={{ flexWrap: "wrap", gap: 10 }}>
            <StatusIndicator
              label={researchDiag.overall_status}
              tone={researchDiag.available_providers_count > 0 ? "success" : "warn"}
            />
            <span className="muted" style={{ fontSize: 12 }}>
              Available Providers: <strong>{researchDiag.available_providers_count}</strong> /{" "}
              {researchDiag.total_providers_count}
            </span>
            {researchDiag.last_search_trace && (
              <span className="muted" style={{ fontSize: 12 }}>
                Last Search: <strong>{researchDiag.last_search_trace.source_count}</strong> sources across{" "}
                <strong>{researchDiag.last_search_trace.independent_domains_count}</strong> domains (
                {researchDiag.last_search_trace.pages_fetched_count} pages extracted in{" "}
                {researchDiag.last_search_trace.retrieval_duration_ms}ms)
              </span>
            )}
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Provider</th>
                  <th>Configured</th>
                  <th>Connectivity</th>
                  <th>HTTP Status</th>
                  <th>Category</th>
                  <th>Results</th>
                  <th>Pages Extracted</th>
                  <th>Duration</th>
                  <th>Mode</th>
                </tr>
              </thead>
              <tbody>
                {(researchDiag.providers || []).map((p: any) => (
                  <tr key={p.provider_name}>
                    <td className="mono">{p.provider_name}</td>
                    <td>{p.configured ? "YES" : "NO"}</td>
                    <td>
                      <StatusIndicator
                        label={p.live_connectivity_status}
                        tone={
                          p.live_connectivity_status === "AVAILABLE"
                            ? "success"
                            : p.live_connectivity_status === "UNPROBED"
                            ? "neutral"
                            : "warn"
                        }
                      />
                    </td>
                    <td className="mono">{p.last_http_status ?? "—"}</td>
                    <td className="mono">{p.last_error_category ?? "—"}</td>
                    <td>{p.search_results_returned ?? 0}</td>
                    <td>{p.pages_extracted ?? 0}</td>
                    <td className="mono">{p.retrieval_duration_ms ? `${p.retrieval_duration_ms}ms` : "—"}</td>
                    <td>{p.cache_or_live_status || "live"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <TechnicalDiagnostics title="Technical Diagnostics — Research Provider Telemetry" data={researchDiag} />
        </div>
      ) : (
        <div className="muted">Loading research provider diagnostics...</div>
      )}
    </div>
  );

  const resolvedSources = searchRes?.verified_sources || searchRes?.results || [];

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`RESEARCH & INTELLIGENCE // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            onClick={() => {
              loadPredictive();
              loadResearchDiagnostics(false);
            }}
          >
            <RefreshCw size={13} /> Refresh
          </button>
        }
      />

      {error && <ErrorState message={error} onRetry={loadPredictive} />}

      {/* 59. RESEARCH WORKSPACE */}
      {page.id === "workspace" && (
        <div>
          <div className="grid-2">
            <div className="card">
              <div className="card-title"><span>Live Multi-Provider Web Search</span></div>
              <form onSubmit={runWebSearch} className="row">
                <input
                  className="input"
                  style={{ flex: 1 }}
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Search live public web sources (e.g. Lamborghini Aventador SVJ price)..."
                />
                <button type="submit" className="btn btn-sm"><Search size={13} /> Search</button>
              </form>
              {searchRes && (
                <div style={{ marginTop: 10 }}>
                  <SourcesList sources={resolvedSources} />
                  <ProvenanceBar provenance={searchRes.provenance} />
                  <TechnicalDiagnostics title="Technical Diagnostics — Web Search Payload" data={searchRes} />
                </div>
              )}
            </div>
            <div className="card">
              <div className="card-title"><span>SSRF-Guarded URL Extraction</span></div>
              <form onSubmit={runWebFetch} className="row">
                <input
                  className="input"
                  style={{ flex: 1 }}
                  value={fetchUrl}
                  onChange={(e) => setFetchUrl(e.target.value)}
                  placeholder="https://example.com/article"
                />
                <button type="submit" className="btn btn-secondary btn-sm"><Globe size={13} /> Fetch</button>
              </form>
              {fetchRes && (
                <div style={{ marginTop: 10 }}>
                  <ReadableSummary
                    title="Extracted Page Summary"
                    data={fetchRes}
                    diagnosticsTitle="Technical Diagnostics — URL Fetch Payload"
                  />
                </div>
              )}
            </div>
          </div>
          {renderDiagnosticsCard()}
        </div>
      )}

      {/* 60. WEB RESEARCH */}
      {page.id === "web" && (
        <div>
          <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="card-title"><span>Public Web Research &amp; Source Verification</span></div>
            <form onSubmit={runWebSearch} className="row">
              <input
                className="input"
                style={{ flex: 1 }}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Research topic with citations..."
              />
              <button type="submit" className="btn">Run Search</button>
            </form>
            {searchRes && (
              <div>
                {resolvedSources.length ? (
                  <SourcesList sources={resolvedSources} />
                ) : (
                  <div className="muted">No matching public sources returned for this query.</div>
                )}
                <ProvenanceBar provenance={searchRes.provenance} />
                <TechnicalDiagnostics title="Technical Diagnostics — Web Search Payload" data={searchRes} />
              </div>
            )}
          </div>
          {renderDiagnosticsCard()}
        </div>
      )}

      {/* 61. MARKET INTELLIGENCE & 63. REPORTS / BRIEFINGS */}
      {(page.id === "market" || page.id === "reports") && <IntelligenceView />}

      {/* 62. COMPETITOR INTELLIGENCE */}
      {page.id === "competitor" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span>Product &amp; Competitor Research</span></div>
          <form onSubmit={runCompetitor} className="row">
            <input
              className="input"
              style={{ flex: 1 }}
              value={compQuery}
              onChange={(e) => setCompQuery(e.target.value)}
              placeholder="Compare competitor product, pricing, or vendor..."
            />
            <button type="submit" className="btn">Analyze</button>
          </form>
          {compRes && (
            <ReadableSummary
              title="Competitive Research Summary"
              data={compRes}
              diagnosticsTitle="Technical Diagnostics — Competitor Payload"
            />
          )}
        </div>
      )}

      {/* 64. SAVED RESEARCH & ORDERS */}
      {page.id === "saved" && <AtlasMapView />}

      {/* 65. DATA ANALYSIS */}
      {page.id === "data-analysis" && <CaravanView />}

      {/* 66. PREDICTIVE ANALYTICS */}
      {page.id === "predictive" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          <div className="grid-3">
            <MetricDisplay label="Forecast Horizon" value="6 Months" sub="Recorded ledger only" tone="info" />
            <MetricDisplay label="TURBO Cache Hits" value={turbo?.cache_hits ?? 0} sub="Live runtime telemetry" tone="success" />
            <MetricDisplay label="TURBO Cache Misses" value={turbo?.cache_misses ?? 0} sub="Zero fabricated curves" tone="neutral" />
          </div>
          <div className="grid-2">
            <div className="card">
              <div className="card-title"><span>Financial Cash-Flow Forecast</span></div>
              <ReadableSummary
                data={forecast || { status: "No recorded ledger entries yet" }}
                diagnosticsTitle="Technical Diagnostics — Forecast Telemetry"
              />
            </div>
            <div className="card">
              <div className="card-title"><span>TURBO Runtime Stats</span></div>
              <ReadableSummary
                data={turbo || { status: "Ready" }}
                diagnosticsTitle="Technical Diagnostics — TURBO Stats"
              />
            </div>
          </div>
        </div>
      )}
    </ResponsiveWorkspace>
  );
}
