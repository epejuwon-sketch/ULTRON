import React, { useEffect, useState } from "react";
import { Globe, RefreshCw, Search } from "lucide-react";
import { apiFetch } from "../lib/api";
import { getModule, getSubPage } from "../catalog/navigation";
import { ModulePageProps } from "./CommandModulePage";
import { AtlasMapView, CaravanView, IntelligenceView } from "../components/OpsViews";
import {
  ErrorState,
  MetricDisplay,
  PageHeader,
  ResponsiveWorkspace,
  useToast,
} from "../components/ui/DesignSystem";

export default function ResearchModulePage({ subPage, onSelectSubPage }: ModulePageProps) {
  const mod = getModule("research");
  const page = getSubPage("research", subPage);
  const { pushToast } = useToast();

  const [query, setQuery] = useState("");
  const [fetchUrl, setFetchUrl] = useState("");
  const [searchRes, setSearchRes] = useState<any>(null);
  const [fetchRes, setFetchRes] = useState<any>(null);
  const [compQuery, setCompQuery] = useState("");
  const [compRes, setCompRes] = useState<any>(null);
  const [forecast, setForecast] = useState<any>(null);
  const [turbo, setTurbo] = useState<any>(null);
  const [error, setError] = useState("");

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
  }, [subPage]);

  async function runWebSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    try {
      const res = await apiFetch<any>("/api/v1/research/search", {
        method: "POST",
        body: { query: query.trim(), max_results: 5 },
      });
      setSearchRes(res);
      pushToast("Web research query completed.", "success");
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

  return (
    <ResponsiveWorkspace subPages={mod.subPages} activeSubPage={page.id} onSelectSubPage={onSelectSubPage}>
      <PageHeader
        eyebrow={`RESEARCH & INTELLIGENCE // PAGE ${page.number}`}
        title={page.label}
        description={page.description}
        actions={
          <button type="button" className="btn btn-secondary btn-sm" onClick={loadPredictive}>
            <RefreshCw size={13} /> Refresh
          </button>
        }
      />

      {error && <ErrorState message={error} onRetry={loadPredictive} />}

      {/* 59. RESEARCH WORKSPACE */}
      {page.id === "workspace" && (
        <div className="grid-2">
          <div className="card">
            <div className="card-title"><span>Quick Web Search (/api/v1/research/search)</span></div>
            <form onSubmit={runWebSearch} className="row">
              <input className="input" style={{ flex: 1 }} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search live public web sources..." />
              <button type="submit" className="btn btn-sm"><Search size={13} /> Search</button>
            </form>
            {searchRes && <pre className="code-block" style={{ marginTop: 10 }}>{JSON.stringify(searchRes, null, 2)}</pre>}
          </div>
          <div className="card">
            <div className="card-title"><span>SSRF-Guarded URL Extraction (/api/v1/research/fetch)</span></div>
            <form onSubmit={runWebFetch} className="row">
              <input className="input" style={{ flex: 1 }} value={fetchUrl} onChange={(e) => setFetchUrl(e.target.value)} placeholder="https://example.com/article" />
              <button type="submit" className="btn btn-secondary btn-sm"><Globe size={13} /> Fetch</button>
            </form>
            {fetchRes && <pre className="code-block" style={{ marginTop: 10 }}>{JSON.stringify(fetchRes, null, 2)}</pre>}
          </div>
        </div>
      )}

      {/* 60. WEB RESEARCH */}
      {page.id === "web" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span>Public Web Research & Source Verification</span></div>
          <form onSubmit={runWebSearch} className="row">
            <input className="input" style={{ flex: 1 }} value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Research topic with citations..." />
            <button type="submit" className="btn">Run Search</button>
          </form>
          {searchRes && <pre className="code-block">{JSON.stringify(searchRes, null, 2)}</pre>}
        </div>
      )}

      {/* 61. MARKET INTELLIGENCE & 63. REPORTS / BRIEFINGS */}
      {(page.id === "market" || page.id === "reports") && <IntelligenceView />}

      {/* 62. COMPETITOR INTELLIGENCE */}
      {page.id === "competitor" && (
        <div className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <div className="card-title"><span>Product & Competitor Research (/api/v1/atlas/shopping/research)</span></div>
          <form onSubmit={runCompetitor} className="row">
            <input className="input" style={{ flex: 1 }} value={compQuery} onChange={(e) => setCompQuery(e.target.value)} placeholder="Compare competitor product, pricing, or vendor..." />
            <button type="submit" className="btn">Analyze</button>
          </form>
          {compRes && <pre className="code-block">{JSON.stringify(compRes, null, 2)}</pre>}
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
              <pre className="code-block">{JSON.stringify(forecast || { status: "No recorded ledger entries yet" }, null, 2)}</pre>
            </div>
            <div className="card">
              <div className="card-title"><span>TURBO Runtime Stats</span></div>
              <pre className="code-block">{JSON.stringify(turbo || { status: "Loading..." }, null, 2)}</pre>
            </div>
          </div>
        </div>
      )}
    </ResponsiveWorkspace>
  );
}
